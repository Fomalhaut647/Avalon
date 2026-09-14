"""规则函数与 docs/rules.md 的一致性。"""

import random
from itertools import permutations

import pytest

from avalon import rules
from avalon.rules import Role, Side


def test_quest_sizes_match_rules_doc():
    assert rules.QUEST_SIZES == (2, 3, 2, 3, 3)


def test_five_players_in_ring():
    assert rules.PLAYER_IDS == ("P1", "P2", "P3", "P4", "P5")
    assert rules.next_seat("P1") == "P2"
    assert rules.next_seat("P5") == "P1"
    assert rules.seats_from("P4") == ("P4", "P5", "P1", "P2", "P3")


def test_three_good_two_evil():
    sides = [rules.side_of(r) for r in Role]
    assert sides.count(Side.GOOD) == 3
    assert sides.count(Side.EVIL) == 2


def test_thresholds():
    assert rules.VOTES_TO_APPROVE == 3
    assert rules.MAX_PROPOSALS_PER_QUEST == 5
    assert rules.WINS_NEEDED == 3
    assert rules.FAILS_TO_FAIL_QUEST == 1


def test_assign_roles_is_a_permutation_and_reproducible():
    a = rules.assign_roles(random.Random(7))
    b = rules.assign_roles(random.Random(7))
    assert a == b
    assert set(a) == set(rules.PLAYER_IDS)
    assert sorted(a.values(), key=str) == sorted(Role, key=str)


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
    assert info.merlin_or_morgana == () and info.fellow_evil is None


def test_hidden_info_percival_sees_merlin_and_morgana_unordered():
    info = rules.hidden_info_for("P3", ASSIGN)
    assert info.merlin_or_morgana == ("P1", "P5")
    assert info.evil_players == () and info.fellow_evil is None


def test_hidden_info_servant_sees_nothing():
    assert rules.hidden_info_for("P4", ASSIGN) == rules.HiddenInfo()


def test_hidden_info_evil_see_each_other():
    assert rules.hidden_info_for("P2", ASSIGN).fellow_evil == "P5"
    assert rules.hidden_info_for("P5", ASSIGN).fellow_evil == "P2"


def test_hidden_info_holds_for_every_assignment():
    for perm in permutations(Role):
        assignments = dict(zip(rules.PLAYER_IDS, perm))
        for pid, role in assignments.items():
            info = rules.hidden_info_for(pid, assignments)
            if role == Role.MERLIN:
                assert all(rules.side_of(assignments[p]) == Side.EVIL for p in info.evil_players)
                assert len(info.evil_players) == 2
            elif role == Role.PERCIVAL:
                assert {assignments[p] for p in info.merlin_or_morgana} == {Role.MERLIN, Role.MORGANA}
            elif rules.side_of(role) == Side.EVIL:
                assert info.fellow_evil != pid
                assert rules.side_of(assignments[info.fellow_evil]) == Side.EVIL
            else:
                assert info == rules.HiddenInfo()


@pytest.mark.parametrize(
    "approves,expected",
    [(5, True), (4, True), (3, True), (2, False), (1, False), (0, False)],
)
def test_is_approved(approves, expected):
    votes = {pid: i < approves for i, pid in enumerate(rules.PLAYER_IDS)}
    assert rules.is_approved(votes) is expected


def test_quest_failed_on_single_fail_card():
    assert rules.quest_failed(0) is False
    assert rules.quest_failed(1) is True
    assert rules.quest_failed(2) is True


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
    assert rules.is_legal_team(("P1", "P2"), 2)
    assert not rules.is_legal_team(("P1", "P1"), 2)
    assert not rules.is_legal_team(("P1", "P2", "P3"), 2)
    assert not rules.is_legal_team(("P1", "P9"), 2)
