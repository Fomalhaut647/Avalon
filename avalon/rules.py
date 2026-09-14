"""纯规则：无状态、无副作用。

角色与阵营、任务人数表、隐藏信息生成、投票判定、任务判定、胜负判定。
本模块不依赖项目内任何其他模块。所有常量与 docs/rules.md 一一对应。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
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
"""同一次行动中连续不合法答案达到此数即使用兜底值（docs/rules.md 第十一节）。"""


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
    i = PLAYER_IDS.index(player_id)
    return PLAYER_IDS[(i + 1) % len(PLAYER_IDS)]


def seats_from(player_id: str) -> tuple[str, ...]:
    """从某人开始顺时针一圈，含起点，共 5 人。"""
    i = PLAYER_IDS.index(player_id)
    return PLAYER_IDS[i:] + PLAYER_IDS[:i]


def assign_roles(rng: random.Random) -> dict[str, Role]:
    """随机分配角色，每个角色恰好一人。"""
    roles = list(Role)
    rng.shuffle(roles)
    return dict(zip(PLAYER_IDS, roles))


def players_with_side(assignments: dict[str, Role], side: Side) -> tuple[str, ...]:
    """按座位顺序返回属于某阵营的玩家。"""
    return tuple(pid for pid in PLAYER_IDS if side_of(assignments[pid]) == side)


def player_with_role(assignments: dict[str, Role], role: Role) -> str:
    return next(pid for pid, r in assignments.items() if r == role)


def hidden_info_for(player_id: str, assignments: dict[str, Role]) -> HiddenInfo:
    """按 docs/rules.md 第三节生成该玩家的隐藏信息。多人信息按座位顺序给出，不泄露谁是谁。"""
    role = assignments[player_id]
    if role == Role.MERLIN:
        return HiddenInfo(evil_players=players_with_side(assignments, Side.EVIL))
    if role == Role.PERCIVAL:
        pair = {player_with_role(assignments, Role.MERLIN), player_with_role(assignments, Role.MORGANA)}
        return HiddenInfo(merlin_or_morgana=tuple(pid for pid in PLAYER_IDS if pid in pair))
    if side_of(role) == Side.EVIL:
        others = [pid for pid in players_with_side(assignments, Side.EVIL) if pid != player_id]
        return HiddenInfo(fellow_evil=others[0])
    return HiddenInfo()


def is_approved(votes: dict[str, bool]) -> bool:
    """赞成票 >= VOTES_TO_APPROVE 即通过。"""
    return sum(1 for v in votes.values() if v) >= VOTES_TO_APPROVE


def quest_failed(fail_count: int) -> bool:
    return fail_count >= FAILS_TO_FAIL_QUEST


def winner_after_quests(success_count: int, fail_count: int) -> Side | None:
    """仅由任务比分判断：邪恶 3 败则邪恶胜；好人 3 胜返回 None，需进入刺杀；均未到 3 也返回 None。"""
    if fail_count >= WINS_NEEDED:
        return Side.EVIL
    return None


def good_reached_wins(success_count: int) -> bool:
    return success_count >= WINS_NEEDED


def winner_after_assassination(target: str, assignments: dict[str, Role]) -> Side:
    return Side.EVIL if assignments[target] == Role.MERLIN else Side.GOOD


def is_legal_team(team: tuple[str, ...], size: int) -> bool:
    return len(team) == size and len(set(team)) == size and all(pid in PLAYER_IDS for pid in team)
