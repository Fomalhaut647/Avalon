"""规则常量与 docs/rules.md 的一致性。规则函数实现后在此补充用例。"""

from avalon import rules
from avalon.rules import Role, Side


def test_quest_sizes_match_rules_doc():
    assert rules.QUEST_SIZES == (2, 3, 2, 3, 3)


def test_five_players_in_ring():
    assert rules.PLAYER_IDS == ("P1", "P2", "P3", "P4", "P5")


def test_three_good_two_evil():
    sides = [rules.side_of(r) for r in Role]
    assert sides.count(Side.GOOD) == 3
    assert sides.count(Side.EVIL) == 2


def test_thresholds():
    assert rules.VOTES_TO_APPROVE == 3
    assert rules.MAX_PROPOSALS_PER_QUEST == 5
    assert rules.WINS_NEEDED == 3
    assert rules.FAILS_TO_FAIL_QUEST == 1
