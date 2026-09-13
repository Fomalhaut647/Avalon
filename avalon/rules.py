"""纯规则：无状态、无副作用。

角色与阵营、任务人数表、隐藏信息生成、投票判定、任务判定、胜负判定。
本模块不依赖项目内任何其他模块。所有常量与 docs/rules.md 一一对应。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Side(str, Enum):
    GOOD = "good"
    EVIL = "evil"


class Role(str, Enum):
    MERLIN = "Merlin"
    PERCIVAL = "Percival"
    LOYAL_SERVANT = "Loyal Servant"
    MORGANA = "Morgana"
    ASSASSIN = "Assassin"


ROLE_SIDE: dict[Role, Side] = {
    Role.MERLIN: Side.GOOD,
    Role.PERCIVAL: Side.GOOD,
    Role.LOYAL_SERVANT: Side.GOOD,
    Role.MORGANA: Side.EVIL,
    Role.ASSASSIN: Side.EVIL,
}

PLAYER_IDS: tuple[str, ...] = ("P1", "P2", "P3", "P4", "P5")
"""座位为环形，P5 的下一位是 P1。"""

QUEST_SIZES: tuple[int, ...] = (2, 3, 2, 3, 3)
"""第 1 到第 5 次任务的队伍人数。"""

FAILS_TO_FAIL_QUEST = 1
"""任务中出现多少张失败牌即失败。五人局全部为 1。"""

VOTES_TO_APPROVE = 3
"""提案通过所需的赞成票数。"""

MAX_PROPOSALS_PER_QUEST = 5
"""一次任务内的提案上限。第 5 次被否决则邪恶获胜。"""

WINS_NEEDED = 3
"""任一阵营达到 3 次任务成功/失败即触发终局流程。"""

MAX_INVALID_RETRIES = 3
"""非法答案连续重试次数，超过后使用兜底值。"""


@dataclass(frozen=True)
class HiddenInfo:
    """一名玩家开局私下得知的信息。字段为空表示该角色没有对应信息。"""

    evil_players: tuple[str, ...] = ()
    """Merlin：两名邪恶玩家。"""

    merlin_or_morgana: tuple[str, ...] = ()
    """Percival：Merlin 与 Morgana 两人，不知谁是谁。"""

    fellow_evil: str | None = None
    """Morgana / Assassin：另一名邪恶玩家。"""


def side_of(role: Role) -> Side:
    return ROLE_SIDE[role]


def next_seat(player_id: str) -> str:
    """顺时针下一位。"""
    raise NotImplementedError


def hidden_info_for(player_id: str, assignments: dict[str, Role]) -> HiddenInfo:
    """按 docs/rules.md 第三节生成该玩家的隐藏信息。"""
    raise NotImplementedError


def is_approved(votes: dict[str, bool]) -> bool:
    """赞成票 >= VOTES_TO_APPROVE 即通过。"""
    raise NotImplementedError


def quest_failed(fail_count: int) -> bool:
    raise NotImplementedError


def winner_after_quests(success_count: int, fail_count: int) -> Side | None:
    """仅由任务比分判断：邪恶 3 败则邪恶胜；好人 3 胜返回 None，需进入刺杀。"""
    raise NotImplementedError


def winner_after_assassination(target: str, assignments: dict[str, Role]) -> Side:
    raise NotImplementedError
