"""Player 接口与两种实现。

Player 是裁判与外界之间唯一的接缝：给一份 Notice，收回一个 Reply。
- LLMPlayer：维护整局的对话线程，调用 llm，解析两段式回复。
- RandomPlayer：随机给出合法答案，供状态机测试，不联网。
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from avalon.llm import LLMClient


class Action(str, Enum):
    SPEAK = "speak"
    PROPOSE = "propose"
    VOTE = "vote"
    EXECUTE_QUEST = "execute_quest"
    ASSASSINATE = "assassinate"


@dataclass(frozen=True)
class Notice:
    """裁判发给一名玩家的一次通知。三部分内容见 docs/architecture.md 第二节。"""

    player_id: str
    action: Action
    public_events: tuple[str, ...]
    """自该玩家上次行动以来的公开事件，已渲染为文本。"""
    scoreboard: str
    instruction: str
    team_size: int | None = None
    """PROPOSE 时的队伍人数。"""
    candidates: tuple[str, ...] = ()
    """PROPOSE / ASSASSINATE 时可选的玩家。"""
    rejection_reason: str | None = None
    """上一答案不合法时的原因，要求重答。"""


@dataclass
class Reply:
    """玩家的一次答案。private_analysis 绝不进入其他玩家的上下文。"""

    private_analysis: str
    public_speech: str | None = None
    team: tuple[str, ...] | None = None
    vote: bool | None = None
    quest_success: bool | None = None
    target: str | None = None
    raw: str = ""
    """模型原始输出，仅供日志。"""


class Player(ABC):
    def __init__(self, player_id: str) -> None:
        self.player_id = player_id

    @abstractmethod
    def brief(self, system_prompt: str) -> None:
        """INIT 阶段：告知角色、隐藏信息、规则与输出格式。"""

    @abstractmethod
    def act(self, notice: Notice) -> Reply:
        """收到通知，返回答案。"""


class LLMPlayer(Player):
    """一条持续整局的对话线程。messages 只增不删。"""

    def __init__(self, player_id: str, client: LLMClient) -> None:
        super().__init__(player_id)
        self.client = client
        self.messages: list[dict[str, str]] = []

    def brief(self, system_prompt: str) -> None:
        raise NotImplementedError

    def act(self, notice: Notice) -> Reply:
        raise NotImplementedError


class RandomPlayer(Player):
    """随机合法答案。给定 rng 可复现。"""

    def __init__(self, player_id: str, rng: random.Random) -> None:
        super().__init__(player_id)
        self.rng = rng

    def brief(self, system_prompt: str) -> None:
        raise NotImplementedError

    def act(self, notice: Notice) -> Reply:
        raise NotImplementedError
