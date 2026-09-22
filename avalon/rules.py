"""纯规则：无状态、无副作用。

角色与阵营、任务人数表、隐藏信息生成、投票判定、任务判定、胜负判定。
本模块不依赖项目内任何其他模块。所有常量与 docs/rules.md 一一对应。

人数一律作为参数传入，模块内不保存"当前这一局是几个人"。
模块末尾的 PLAYER_IDS / QUEST_SIZES / VOTES_TO_APPROVE / FAILS_TO_FAIL_QUEST
是 5 人局的取值，只作为文档与默认值参考，规则计算一律走函数。
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
    OBERON = "Oberon"
    MINION = "Minion"
    MORDRED = "Mordred"


ROLE_SIDE: dict[Role, Side] = {
    Role.MERLIN: Side.GOOD,
    Role.PERCIVAL: Side.GOOD,
    Role.LOYAL_SERVANT: Side.GOOD,
    Role.MORGANA: Side.EVIL,
    Role.ASSASSIN: Side.EVIL,
    Role.OBERON: Side.EVIL,
    Role.MINION: Side.EVIL,
    Role.MORDRED: Side.EVIL,
}

MIN_PLAYERS = 5
MAX_PLAYERS = 10
DEFAULT_PLAYERS = 5

BASE_ROLES: tuple[Role, ...] = (Role.MERLIN, Role.PERCIVAL, Role.LOYAL_SERVANT, Role.MORGANA, Role.ASSASSIN)
"""5 人局的五个角色。人数更多时在此基础上追加。"""

EXTRA_ROLES: dict[int, tuple[Role, ...]] = {
    5: (),
    6: (Role.LOYAL_SERVANT,),
    7: (Role.LOYAL_SERVANT, Role.OBERON),
    8: (Role.LOYAL_SERVANT, Role.LOYAL_SERVANT, Role.MINION),
    9: (Role.LOYAL_SERVANT, Role.LOYAL_SERVANT, Role.LOYAL_SERVANT, Role.MORDRED),
    10: (Role.LOYAL_SERVANT, Role.LOYAL_SERVANT, Role.LOYAL_SERVANT, Role.OBERON, Role.MORDRED),
}
"""相对 5 人局追加的角色，见 docs/decisions/0011。"""

QUEST_SIZES_BY_COUNT: dict[int, tuple[int, ...]] = {
    5: (2, 3, 2, 3, 3),
    6: (2, 3, 4, 3, 4),
    7: (2, 3, 3, 4, 4),
    8: (3, 4, 4, 5, 5),
    9: (3, 4, 4, 5, 5),
    10: (3, 4, 4, 5, 5),
}
"""第 1 到第 5 次任务的队伍人数。"""

TWO_FAILS_FROM_PLAYERS = 7
"""人数达到此值时，第 4 次任务需要两张失败牌才失败。"""

TWO_FAILS_QUEST_INDEX = 4

MUTUALLY_KNOWN_EVIL: tuple[Role, ...] = (Role.MORGANA, Role.ASSASSIN, Role.MINION, Role.MORDRED)
"""互相知道身份的邪恶角色。奥伯伦不在其中：他不知道同伴，同伴也不知道他。"""

HIDDEN_FROM_MERLIN: tuple[Role, ...] = (Role.MORDRED,)
"""梅林看不到的邪恶角色。"""

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
    """Merlin：他能看到的邪恶玩家，不含莫德雷德，含奥伯伦。"""

    merlin_or_morgana: tuple[str, ...] = ()
    """Percival：Merlin 与 Morgana 两人，不知谁是谁。"""

    fellow_evils: tuple[str, ...] = ()
    """互知的邪恶同伴，按座位顺序。奥伯伦为空，他的同伴名单里也没有他。"""


# ---------------------------------------------------------------- 人数与座位


def check_player_count(players: int) -> int:
    """人数必须在 5 到 10 之间，否则抛 ValueError。"""
    if players not in QUEST_SIZES_BY_COUNT:
        raise ValueError(f"人数必须在 {MIN_PLAYERS} 到 {MAX_PLAYERS} 之间，收到 {players}")
    return players


def player_ids(players: int) -> tuple[str, ...]:
    """座位为环形，最后一位的下一位是 P1。"""
    return tuple(f"P{i}" for i in range(1, check_player_count(players) + 1))


def seat_count(assignments: dict[str, Role]) -> int:
    """从一份角色分配里读出这一局的人数。"""
    return len(assignments)


def next_seat(player_id: str, players: int) -> str:
    """顺时针下一位。"""
    ids = player_ids(players)
    i = ids.index(player_id)
    return ids[(i + 1) % len(ids)]


def seats_from(player_id: str, players: int) -> tuple[str, ...]:
    """从某人开始顺时针一圈，含起点，共 players 人。"""
    ids = player_ids(players)
    i = ids.index(player_id)
    return ids[i:] + ids[:i]


# ---------------------------------------------------------------- 按人数的规则表


def roles_for(players: int) -> tuple[Role, ...]:
    """本局的角色构成，按 BASE_ROLES 加 EXTRA_ROLES 的顺序。"""
    return BASE_ROLES + EXTRA_ROLES[check_player_count(players)]


def role_counts(players: int) -> dict[Role, int]:
    """本局每个角色各几人，按 Role 的声明顺序。"""
    roles = roles_for(players)
    return {role: roles.count(role) for role in Role if role in roles}


def quest_sizes(players: int) -> tuple[int, ...]:
    """第 1 到第 5 次任务的队伍人数。"""
    return QUEST_SIZES_BY_COUNT[check_player_count(players)]


def quest_size(players: int, quest_index: int) -> int:
    """第 quest_index 次任务的队伍人数，quest_index 从 1 数起。"""
    return quest_sizes(players)[quest_index - 1]


def fails_to_fail_quest(players: int, quest_index: int) -> int:
    """本次任务需要几张失败牌才算失败。7 人及以上的第 4 次任务需要 2 张，其余都是 1 张。"""
    check_player_count(players)
    if players >= TWO_FAILS_FROM_PLAYERS and quest_index == TWO_FAILS_QUEST_INDEX:
        return 2
    return 1


def votes_to_approve(players: int) -> int:
    """提案通过所需的赞成票数：过半数，平票否决。"""
    return check_player_count(players) // 2 + 1


# ---------------------------------------------------------------- 角色与隐藏信息


def side_of(role: Role) -> Side:
    return ROLE_SIDE[role]


def assign_roles(rng: random.Random, players: int) -> dict[str, Role]:
    """把本局的角色随机分到座位上。"""
    roles = list(roles_for(players))
    rng.shuffle(roles)
    return dict(zip(player_ids(players), roles))


def players_with_side(assignments: dict[str, Role], side: Side) -> tuple[str, ...]:
    """按座位顺序返回属于某阵营的玩家。"""
    return tuple(pid for pid in player_ids(seat_count(assignments)) if side_of(assignments[pid]) == side)


def players_with_role(assignments: dict[str, Role], role: Role) -> tuple[str, ...]:
    """按座位顺序返回担任某角色的玩家。忠臣可能有多人，其余角色至多一人。"""
    return tuple(pid for pid in player_ids(seat_count(assignments)) if assignments[pid] == role)


def player_with_role(assignments: dict[str, Role], role: Role) -> str:
    """取担任某唯一角色的玩家。用于梅林、莫甘娜、刺客这类每局至多一人的角色。"""
    return next(pid for pid, r in assignments.items() if r == role)


def hidden_info_for(player_id: str, assignments: dict[str, Role]) -> HiddenInfo:
    """按 docs/rules.md 第三节生成该玩家的隐藏信息。多人信息按座位顺序给出，不泄露谁是谁。"""
    role = assignments[player_id]
    if role == Role.MERLIN:
        seen = tuple(pid for pid in players_with_side(assignments, Side.EVIL) if assignments[pid] not in HIDDEN_FROM_MERLIN)
        return HiddenInfo(evil_players=seen)
    if role == Role.PERCIVAL:
        pair = {player_with_role(assignments, Role.MERLIN), player_with_role(assignments, Role.MORGANA)}
        return HiddenInfo(merlin_or_morgana=tuple(pid for pid in player_ids(seat_count(assignments)) if pid in pair))
    if role in MUTUALLY_KNOWN_EVIL:
        fellows = tuple(
            pid
            for pid in players_with_side(assignments, Side.EVIL)
            if pid != player_id and assignments[pid] in MUTUALLY_KNOWN_EVIL
        )
        return HiddenInfo(fellow_evils=fellows)
    return HiddenInfo()


# ---------------------------------------------------------------- 判定


def is_approved(votes: dict[str, bool], players: int) -> bool:
    """赞成票达到过半数即通过，平票否决。"""
    return sum(1 for v in votes.values() if v) >= votes_to_approve(players)


def quest_failed(fail_count: int, fails_needed: int) -> bool:
    """失败牌达到本次任务的门槛即失败。门槛由 fails_to_fail_quest 给出。"""
    return fail_count >= fails_needed


def winner_after_quests(success_count: int, fail_count: int) -> Side | None:
    """仅由任务比分判断：邪恶 3 败则邪恶胜；好人 3 胜返回 None，需进入刺杀；均未到 3 也返回 None。"""
    if fail_count >= WINS_NEEDED:
        return Side.EVIL
    return None


def good_reached_wins(success_count: int) -> bool:
    return success_count >= WINS_NEEDED


def winner_after_assassination(target: str, assignments: dict[str, Role]) -> Side:
    return Side.EVIL if assignments[target] == Role.MERLIN else Side.GOOD


def is_legal_team(team: tuple[str, ...], size: int, players: int) -> bool:
    ids = player_ids(players)
    return len(team) == size and len(set(team)) == size and all(pid in ids for pid in team)


# ---------------------------------------------------------------- 5 人局的取值

PLAYER_IDS: tuple[str, ...] = player_ids(DEFAULT_PLAYERS)
QUEST_SIZES: tuple[int, ...] = quest_sizes(DEFAULT_PLAYERS)
VOTES_TO_APPROVE = votes_to_approve(DEFAULT_PLAYERS)
FAILS_TO_FAIL_QUEST = fails_to_fail_quest(DEFAULT_PLAYERS, 1)
