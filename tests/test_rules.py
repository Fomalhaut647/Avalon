"""规则函数与 docs/rules.md 的一致性。"""

import random
from itertools import permutations

import pytest

from avalon import rules
from avalon.rules import Role, Side

COUNTS = (5, 6, 7, 8, 9, 10)


def test_quest_sizes_match_rules_doc():
    assert rules.QUEST_SIZES == (2, 3, 2, 3, 3)


def test_five_players_in_ring():
    assert rules.PLAYER_IDS == ("P1", "P2", "P3", "P4", "P5")
    assert rules.next_seat("P1", 5) == "P2"
    assert rules.next_seat("P5", 5) == "P1"
    assert rules.seats_from("P4", 5) == ("P4", "P5", "P1", "P2", "P3")


def test_three_good_two_evil():
    sides = [rules.side_of(r) for r in rules.roles_for(5)]
    assert sides.count(Side.GOOD) == 3
    assert sides.count(Side.EVIL) == 2


def test_thresholds():
    assert rules.VOTES_TO_APPROVE == 3
    assert rules.MAX_PROPOSALS_PER_QUEST == 5
    assert rules.WINS_NEEDED == 3
    assert rules.FAILS_TO_FAIL_QUEST == 1


def test_assign_roles_is_a_permutation_and_reproducible():
    a = rules.assign_roles(random.Random(7), 5)
    b = rules.assign_roles(random.Random(7), 5)
    assert a == b
    assert set(a) == set(rules.PLAYER_IDS)
    assert sorted(a.values(), key=str) == sorted(rules.roles_for(5), key=str)


ASSIGN = {
    "P1": Role.MERLIN,
    "P2": Role.ASSASSIN,
    "P3": Role.PERCIVAL,
    "P4": Role.LOYAL_SERVANT,
    "P5": Role.MORGANA,
}


def test_hidden_info_merlin_sees_both_evil_in_seat_order():
    info = rules.hidden_info_for("P1", ASSIGN)
    assert info.evil_players == ("P2", "P5")
    assert info.merlin_or_morgana == () and info.fellow_evils == ()


def test_hidden_info_percival_sees_merlin_and_morgana_unordered():
    info = rules.hidden_info_for("P3", ASSIGN)
    assert info.merlin_or_morgana == ("P1", "P5")
    assert info.evil_players == () and info.fellow_evils == ()


def test_hidden_info_servant_sees_nothing():
    assert rules.hidden_info_for("P4", ASSIGN) == rules.HiddenInfo()


def test_hidden_info_evil_see_each_other():
    assert rules.hidden_info_for("P2", ASSIGN).fellow_evils == ("P5",)
    assert rules.hidden_info_for("P5", ASSIGN).fellow_evils == ("P2",)


def test_hidden_info_holds_for_every_assignment():
    for perm in permutations(rules.roles_for(5)):
        assignments = dict(zip(rules.PLAYER_IDS, perm))
        for pid, role in assignments.items():
            info = rules.hidden_info_for(pid, assignments)
            if role == Role.MERLIN:
                assert all(rules.side_of(assignments[p]) == Side.EVIL for p in info.evil_players)
                assert len(info.evil_players) == 2
            elif role == Role.PERCIVAL:
                assert {assignments[p] for p in info.merlin_or_morgana} == {Role.MERLIN, Role.MORGANA}
            elif rules.side_of(role) == Side.EVIL:
                assert len(info.fellow_evils) == 1 and info.fellow_evils[0] != pid
                assert rules.side_of(assignments[info.fellow_evils[0]]) == Side.EVIL
            else:
                assert info == rules.HiddenInfo()


@pytest.mark.parametrize(
    "approves,expected",
    [(5, True), (4, True), (3, True), (2, False), (1, False), (0, False)],
)
def test_is_approved(approves, expected):
    votes = {pid: i < approves for i, pid in enumerate(rules.PLAYER_IDS)}
    assert rules.is_approved(votes, 5) is expected


def test_quest_failed_on_single_fail_card():
    assert rules.quest_failed(0, 1) is False
    assert rules.quest_failed(1, 1) is True
    assert rules.quest_failed(2, 1) is True


def test_winner_after_quests():
    assert rules.winner_after_quests(0, 3) == Side.EVIL
    assert rules.winner_after_quests(2, 3) == Side.EVIL
    assert rules.winner_after_quests(3, 0) is None
    assert rules.winner_after_quests(2, 2) is None
    assert rules.good_reached_wins(3) is True
    assert rules.good_reached_wins(2) is False


def test_winner_after_assassination():
    assert rules.winner_after_assassination("P1", ASSIGN) == Side.EVIL
    for pid in ("P2", "P3", "P4", "P5"):
        assert rules.winner_after_assassination(pid, ASSIGN) == Side.GOOD


def test_is_legal_team():
    assert rules.is_legal_team(("P1", "P2"), 2, 5)
    assert not rules.is_legal_team(("P1", "P1"), 2, 5)
    assert not rules.is_legal_team(("P1", "P2", "P3"), 2, 5)
    assert not rules.is_legal_team(("P1", "P9"), 2, 5)


# ---------------------------------------------------------------- 5 到 10 人


def test_player_count_range_is_checked():
    for bad in (0, 1, 4, 11, 20, -5):
        with pytest.raises(ValueError):
            rules.check_player_count(bad)
    for n in COUNTS:
        assert rules.check_player_count(n) == n


@pytest.mark.parametrize("players", COUNTS)
def test_player_ids_and_ring(players):
    ids = rules.player_ids(players)
    assert len(ids) == players
    assert ids[0] == "P1" and ids[-1] == f"P{players}"
    assert rules.next_seat(ids[-1], players) == "P1"
    assert rules.next_seat("P1", players) == "P2"
    assert rules.seats_from(ids[-1], players) == (ids[-1],) + ids[:-1]
    assert set(rules.seats_from("P3", players)) == set(ids)


@pytest.mark.parametrize(
    "players,expected",
    [
        (5, (2, 3, 2, 3, 3)),
        (6, (2, 3, 4, 3, 4)),
        (7, (2, 3, 3, 4, 4)),
        (8, (3, 4, 4, 5, 5)),
        (9, (3, 4, 4, 5, 5)),
        (10, (3, 4, 4, 5, 5)),
    ],
)
def test_quest_sizes_by_player_count(players, expected):
    assert rules.quest_sizes(players) == expected
    for i, size in enumerate(expected, start=1):
        assert rules.quest_size(players, i) == size
        assert size <= players


@pytest.mark.parametrize("players,expected", [(5, 3), (6, 4), (7, 4), (8, 5), (9, 5), (10, 6)])
def test_votes_to_approve_is_a_majority(players, expected):
    assert rules.votes_to_approve(players) == expected
    tie = {f"P{i}": i <= players // 2 for i in range(1, players + 1)}
    assert rules.is_approved(tie, players) is False, "平票必须否决"
    one_more = dict(tie)
    one_more[f"P{players // 2 + 1}"] = True
    assert rules.is_approved(one_more, players) is True


@pytest.mark.parametrize("players", COUNTS)
def test_fourth_quest_needs_two_fails_from_seven_players(players):
    for quest_index in (1, 2, 3, 5):
        assert rules.fails_to_fail_quest(players, quest_index) == 1
    expected = 2 if players >= 7 else 1
    assert rules.fails_to_fail_quest(players, 4) == expected
    assert rules.quest_failed(1, expected) is (expected == 1)
    assert rules.quest_failed(2, expected) is True


@pytest.mark.parametrize(
    "players,extra",
    [
        (5, ()),
        (6, (Role.LOYAL_SERVANT,)),
        (7, (Role.LOYAL_SERVANT, Role.OBERON)),
        (8, (Role.LOYAL_SERVANT, Role.LOYAL_SERVANT, Role.MINION)),
        (9, (Role.LOYAL_SERVANT,) * 3 + (Role.MORDRED,)),
        (10, (Role.LOYAL_SERVANT,) * 3 + (Role.OBERON, Role.MORDRED)),
    ],
)
def test_role_table_matches_the_decided_setup(players, extra):
    roles = rules.roles_for(players)
    assert len(roles) == players
    assert roles == rules.BASE_ROLES + extra
    assert roles.count(Role.MERLIN) == 1 and roles.count(Role.PERCIVAL) == 1
    assert roles.count(Role.MORGANA) == 1 and roles.count(Role.ASSASSIN) == 1


@pytest.mark.parametrize("players,good,evil", [(5, 3, 2), (6, 4, 2), (7, 4, 3), (8, 5, 3), (9, 6, 3), (10, 6, 4)])
def test_side_split_per_player_count(players, good, evil):
    sides = [rules.side_of(r) for r in rules.roles_for(players)]
    assert sides.count(Side.GOOD) == good
    assert sides.count(Side.EVIL) == evil


@pytest.mark.parametrize("players", COUNTS)
def test_assign_roles_covers_every_seat(players):
    a = rules.assign_roles(random.Random(11), players)
    b = rules.assign_roles(random.Random(11), players)
    assert a == b
    assert set(a) == set(rules.player_ids(players))
    assert sorted(a.values(), key=str) == sorted(rules.roles_for(players), key=str)


@pytest.mark.parametrize("players", COUNTS)
def test_hidden_info_over_300_random_assignments(players):
    """每种人数随机 300 组分配，逐条核对 docs/rules.md 第三节的可见性。"""
    rng = random.Random(players * 1000 + 7)
    for _ in range(300):
        assignments = rules.assign_roles(rng, players)
        ids = rules.player_ids(players)
        evil = {pid for pid in ids if rules.side_of(assignments[pid]) == Side.EVIL}
        mordred = {pid for pid in ids if assignments[pid] == Role.MORDRED}
        oberon = {pid for pid in ids if assignments[pid] == Role.OBERON}
        merlin = rules.player_with_role(assignments, Role.MERLIN)
        morgana = rules.player_with_role(assignments, Role.MORGANA)
        for pid in ids:
            role = assignments[pid]
            info = rules.hidden_info_for(pid, assignments)
            if role == Role.MERLIN:
                seen = set(info.evil_players)
                assert seen == evil - mordred, "梅林看到全部邪恶，除莫德雷德外"
                assert seen & oberon == oberon, "梅林能看到奥伯伦"
                assert not seen & mordred
                assert info.merlin_or_morgana == () and info.fellow_evils == ()
            elif role == Role.PERCIVAL:
                assert set(info.merlin_or_morgana) == {merlin, morgana}
                assert info.evil_players == () and info.fellow_evils == ()
            elif role == Role.OBERON:
                assert info.fellow_evils == (), "奥伯伦不知道任何同伴"
                assert info.evil_players == () and info.merlin_or_morgana == ()
            elif role in rules.MUTUALLY_KNOWN_EVIL:
                fellows = set(info.fellow_evils)
                assert fellows == (evil - oberon) - {pid}, "互知的邪恶彼此可见，且看不到奥伯伦"
                assert pid not in fellows
                assert info.evil_players == () and info.merlin_or_morgana == ()
            else:
                assert role == Role.LOYAL_SERVANT
                assert info == rules.HiddenInfo(), "忠臣没有任何隐藏信息"


@pytest.mark.parametrize("players", COUNTS)
def test_nobody_sees_himself_or_a_wrong_side(players):
    rng = random.Random(players)
    for _ in range(50):
        assignments = rules.assign_roles(rng, players)
        for pid in rules.player_ids(players):
            info = rules.hidden_info_for(pid, assignments)
            for seen in info.evil_players + info.fellow_evils:
                assert seen != pid
                assert rules.side_of(assignments[seen]) == Side.EVIL
            assert pid not in info.merlin_or_morgana or assignments[pid] == Role.PERCIVAL


@pytest.mark.parametrize("players", COUNTS)
def test_is_legal_team_rejects_seats_outside_this_game(players):
    ids = rules.player_ids(players)
    size = rules.quest_size(players, 1)
    assert rules.is_legal_team(ids[:size], size, players)
    assert not rules.is_legal_team(ids[:size - 1] + (f"P{players + 1}",), size, players)
    assert not rules.is_legal_team(ids[:size - 1] + (ids[0],), size, players)
