"""Player 接口与两种实现。

Player 是裁判与外界之间唯一的接缝：给一份 Notice，收回一个 Reply。
- LLMPlayer：维护整局的对话线程，调用 llm，解析两段式回复。
- RandomPlayer：随机给出合法答案，供状态机测试，不联网。
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from avalon.llm import LLMClient, LLMResult


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
    fallback: bool = False
    """是否为裁判兜底生成，而非玩家所答。"""


class InvalidReply(ValueError):
    """答案无法解析或不合法。裁判据此把原因退回给玩家重答。"""


class Player(ABC):
    def __init__(self, player_id: str) -> None:
        self.player_id = player_id
        self.messages: list[dict[str, str]] = []
        """对话线程。非 LLM 玩家保持为空。"""
        self._calls: list[LLMResult] = []

    @abstractmethod
    def brief(self, system_prompt: str) -> None:
        """INIT 阶段：告知角色、隐藏信息、规则与输出格式。"""

    @abstractmethod
    def act(self, notice: Notice) -> Reply:
        """收到通知，返回答案。格式不合法时抛 InvalidReply。"""

    def drain_calls(self) -> list[LLMResult]:
        """取走自上次取走以来的 API 调用记录，供裁判记日志。"""
        calls, self._calls = self._calls, []
        return calls


class LLMPlayer(Player):
    """一条持续整局的对话线程。messages 只增不删。"""

    def __init__(self, player_id: str, client: LLMClient) -> None:
        super().__init__(player_id)
        self.client = client

    def brief(self, system_prompt: str) -> None:
        self.messages = [{"role": "system", "content": system_prompt}]

    def act(self, notice: Notice) -> Reply:
        # prompts 依赖本模块的数据类型，这里在函数内导入以避免循环导入。
        from avalon import prompts

        self.messages.append({"role": "user", "content": prompts.render_notice(notice)})
        result = self.client.complete(self.messages)
        self._calls.append(result)
        self.messages.append({"role": "assistant", "content": result.text})
        try:
            return prompts.parse_reply(result.text, notice.action)
        except ValueError as e:
            raise InvalidReply(str(e)) from e


class RandomPlayer(Player):
    """随机合法答案。给定 rng 可复现。"""

    def __init__(self, player_id: str, rng: random.Random) -> None:
        super().__init__(player_id)
        self.rng = rng

    def brief(self, system_prompt: str) -> None:
        pass

    def act(self, notice: Notice) -> Reply:
        pid = self.player_id
        if notice.action == Action.SPEAK:
            return Reply(private_analysis="", public_speech=f"{pid} 的随机发言。")
        if notice.action == Action.PROPOSE:
            team = tuple(sorted(self.rng.sample(notice.candidates, notice.team_size or 0)))
            return Reply(private_analysis="", public_speech=f"{pid} 的随机总结。", team=team)
        if notice.action == Action.VOTE:
            return Reply(private_analysis="", vote=self.rng.random() < 0.5)
        if notice.action == Action.EXECUTE_QUEST:
            return Reply(private_analysis="", quest_success=self.rng.random() < 0.5)
        if notice.action == Action.ASSASSINATE:
            return Reply(private_analysis="", target=self.rng.choice(notice.candidates))
        raise ValueError(f"未知行动 {notice.action}")
