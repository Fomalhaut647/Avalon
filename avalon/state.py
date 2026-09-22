"""游戏状态的数据结构。只有数据，没有流程。

裁判持有唯一的 GameState 实例并在推进阶段时修改它；记录器把它序列化为 public.json。
凡标注"私有"的字段不得出现在任何发给玩家的内容中。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from avalon.rules import DEFAULT_PLAYERS, Role, Side


class Phase(str, Enum):
    INIT = "INIT"
    DISCUSSION = "DISCUSSION"
    PROPOSAL = "PROPOSAL"
    VOTING = "VOTING"
    QUEST_EXECUTION = "QUEST_EXECUTION"
    QUEST_RESULT = "QUEST_RESULT"
    ASSASSINATION = "ASSASSINATION"
    GAME_OVER = "GAME_OVER"


@dataclass
class Speech:
    speaker: str
    content: str
    quest_index: int
    proposal_index: int


@dataclass
class Proposal:
    """一次提案：一位队长、一支队伍、一轮投票。"""

    index: int
    leader: str
    team: tuple[str, ...] = ()
    votes: dict[str, bool] = field(default_factory=dict)
    """player_id -> True 赞成 / False 反对。公开。"""
    approved: bool | None = None


@dataclass
class Quest:
    """一次任务：若干次提案，最多一次执行。"""

    index: int
    size: int
    proposals: list[Proposal] = field(default_factory=list)
    team: tuple[str, ...] = ()
    cards: dict[str, bool] = field(default_factory=dict)
    """player_id -> True 成功 / False 失败。私有：只进裁判日志。"""
    fail_count: int | None = None
    """公开。"""
    succeeded: bool | None = None

    @property
    def rejections(self) -> int:
        return sum(1 for p in self.proposals if p.approved is False)


@dataclass
class GameState:
    game_id: str
    seed: int
    players: int = DEFAULT_PLAYERS
    """本局人数，5 到 10。座位是 P1 到 P{players}。"""
    phase: Phase = Phase.INIT
    assignments: dict[str, Role] = field(default_factory=dict)
    """私有，GAME_OVER 时公开。"""
    quests: list[Quest] = field(default_factory=list)
    speeches: list[Speech] = field(default_factory=list)
    """全部公开发言，全程保留。"""
    assassination_target: str | None = None
    winner: Side | None = None
    win_reason: str | None = None
    """three_successes_and_merlin_safe / three_failures / five_rejections / merlin_assassinated"""

    @property
    def current_quest(self) -> Quest:
        return self.quests[-1]

    @property
    def current_proposal(self) -> Proposal:
        return self.current_quest.proposals[-1]

    @property
    def success_count(self) -> int:
        return sum(1 for q in self.quests if q.succeeded is True)

    @property
    def fail_count(self) -> int:
        return sum(1 for q in self.quests if q.succeeded is False)
