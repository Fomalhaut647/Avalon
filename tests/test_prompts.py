"""答案解析：格式不全、多余内容、非法值、markdown 包裹。"""

import pytest

from avalon import prompts
from avalon.player import Action
from avalon.prompts import (
    MARK_ASSASSINATE,
    MARK_PRIVATE,
    MARK_QUEST,
    MARK_SPEECH,
    MARK_TEAM,
    MARK_VOTE,
)
from avalon import rules
from avalon.rules import HiddenInfo, Role


def test_parse_speak():
    text = f"{MARK_PRIVATE}\n我觉得 P3 可疑。\n\n{MARK_SPEECH}\n大家好，我先说两句。"
    r = prompts.parse_reply(text, Action.SPEAK)
    assert r.private_analysis == "我觉得 P3 可疑。"
    assert r.public_speech == "大家好，我先说两句。"
    assert r.raw == text


def test_parse_speak_without_private_marker_uses_leading_text():
    r = prompts.parse_reply(f"先想一想。\n{MARK_SPEECH}\n发言内容", Action.SPEAK)
    assert r.private_analysis == "先想一想。"
    assert r.public_speech == "发言内容"


def test_parse_speak_missing_speech_raises():
    with pytest.raises(ValueError):
        prompts.parse_reply(f"{MARK_PRIVATE}\n只有分析", Action.SPEAK)
    with pytest.raises(ValueError):
        prompts.parse_reply("完全没有标记的文本", Action.SPEAK)
    with pytest.raises(ValueError):
        prompts.parse_reply(f"{MARK_PRIVATE}\n分析\n{MARK_SPEECH}\n", Action.SPEAK)


def test_parse_propose_team_dedup_and_markdown():
    text = f"**{MARK_PRIVATE}**\n分析\n**{MARK_SPEECH}**\n我选 P2 和 P4。\n**{MARK_TEAM}** P2、P4，P2\n多余的话"
    r = prompts.parse_reply(text, Action.PROPOSE)
    assert r.team == ("P2", "P4")
    assert r.public_speech == "我选 P2 和 P4。"


def test_parse_propose_without_team_raises():
    with pytest.raises(ValueError):
        prompts.parse_reply(f"{MARK_PRIVATE}\n分析\n{MARK_SPEECH}\n发言", Action.PROPOSE)
    with pytest.raises(ValueError):
        prompts.parse_reply(f"{MARK_PRIVATE}\n分析\n{MARK_SPEECH}\n发言\n{MARK_TEAM}\n没有编号", Action.PROPOSE)


@pytest.mark.parametrize(
    "value,expected",
    [("赞成", True), ("反对", False), ("同意。理由略", True), ("我反对这支队伍", False), ("approve", True), ("Reject", False)],
)
def test_parse_vote(value, expected):
    r = prompts.parse_reply(f"{MARK_PRIVATE}\n分析\n{MARK_VOTE}{value}", Action.VOTE)
    assert r.vote is expected


def test_parse_vote_first_keyword_wins():
    r = prompts.parse_reply(f"{MARK_PRIVATE}\n分析\n{MARK_VOTE}反对，虽然我本想赞成", Action.VOTE)
    assert r.vote is False


def test_parse_vote_invalid_raises():
    with pytest.raises(ValueError):
        prompts.parse_reply(f"{MARK_PRIVATE}\n分析\n{MARK_VOTE}弃权", Action.VOTE)
    with pytest.raises(ValueError):
        prompts.parse_reply(f"{MARK_PRIVATE}\n分析", Action.VOTE)


@pytest.mark.parametrize("value,expected", [("成功", True), ("失败", False), ("Fail", False)])
def test_parse_quest(value, expected):
    r = prompts.parse_reply(f"{MARK_PRIVATE}\n分析\n{MARK_QUEST}{value}", Action.EXECUTE_QUEST)
    assert r.quest_success is expected


def test_parse_assassinate():
    r = prompts.parse_reply(f"{MARK_PRIVATE}\n分析\n{MARK_ASSASSINATE}我刺 P 3", Action.ASSASSINATE)
    assert r.target == "P3"
    with pytest.raises(ValueError):
        prompts.parse_reply(f"{MARK_PRIVATE}\n分析\n{MARK_ASSASSINATE}不知道", Action.ASSASSINATE)


def test_duplicate_private_sections_are_joined():
    text = f"{MARK_PRIVATE}\n一\n{MARK_SPEECH}\n发言\n{MARK_PRIVATE}\n二"
    r = prompts.parse_reply(text, Action.SPEAK)
    assert r.private_analysis == "一\n二"


def test_system_prompt_contains_identity_and_hidden_info():
    text = prompts.system_prompt("P1", Role.MERLIN, HiddenInfo(evil_players=("P2", "P5")), 5)
    assert "你是 P1" in text and "梅林" in text and "P2 和 P5" in text
    text = prompts.system_prompt("P3", Role.PERCIVAL, HiddenInfo(merlin_or_morgana=("P1", "P5")), 5)
    assert "P1 和 P5" in text
    text = prompts.system_prompt("P2", Role.ASSASSIN, HiddenInfo(fellow_evils=("P5",)), 5)
    assert "P5" in text and "莫甘娜" in text
    text = prompts.system_prompt("P4", Role.LOYAL_SERVANT, HiddenInfo(), 5)
    assert "没有任何隐藏信息" in text


def test_system_prompt_format_section_matches_role():
    common = (MARK_PRIVATE, MARK_SPEECH, MARK_TEAM, MARK_VOTE)
    servant = prompts.system_prompt("P4", Role.LOYAL_SERVANT, HiddenInfo(), 5)
    morgana = prompts.system_prompt("P1", Role.MORGANA, HiddenInfo(fellow_evils=("P2",)), 5)
    assassin = prompts.system_prompt("P2", Role.ASSASSIN, HiddenInfo(fellow_evils=("P1",)), 5)
    for text in (servant, morgana, assassin):
        for mark in common:
            assert mark in text
    # 好人不会被要求出任务牌或刺杀，格式说明里不列这两项；规则段仍提到刺客与失败牌。
    assert f"{MARK_QUEST}成功" not in servant and f"{MARK_ASSASSINATE}P3" not in servant
    assert f"{MARK_QUEST}成功" in morgana and f"{MARK_ASSASSINATE}P3" not in morgana
    assert f"{MARK_QUEST}成功" in assassin and f"{MARK_ASSASSINATE}P3" in assassin


def test_system_prompt_does_not_leak_other_roles():
    text = prompts.system_prompt("P4", Role.LOYAL_SERVANT, HiddenInfo(), 5)
    # 忠臣的 system prompt 不应包含任何具体座位的角色断言。
    for pid in ("P1", "P2", "P3", "P5"):
        assert f"{pid} 是" not in text


# ---------------------------------------------------------------- 5 到 10 人


def test_parse_team_reads_two_digit_seats():
    text = f"{MARK_PRIVATE}\n分析\n{MARK_SPEECH}\n我选 P1 和 P10。\n{MARK_TEAM}P1, P10"
    assert prompts.parse_reply(text, Action.PROPOSE).team == ("P1", "P10")


def test_parse_assassinate_reads_two_digit_seat():
    r = prompts.parse_reply(f"{MARK_PRIVATE}\n分析\n{MARK_ASSASSINATE}P10", Action.ASSASSINATE)
    assert r.target == "P10"


def test_parse_team_keeps_single_digit_seats_apart():
    text = f"{MARK_PRIVATE}\n分析\n{MARK_SPEECH}\n发言\n{MARK_TEAM}P10、P1、P9、P10"
    assert prompts.parse_reply(text, Action.PROPOSE).team == ("P10", "P1", "P9")


@pytest.mark.parametrize("players", [5, 6, 7, 8, 9, 10])
def test_system_prompt_describes_this_game_only(players):
    text = prompts.system_prompt("P1", Role.MERLIN, HiddenInfo(evil_players=("P2",)), players)
    last = f"P{players}"
    assert f"你正在参加一局 {players} 人阿瓦隆桌游" in text
    assert f"座位编号 P1 到 {last}" in text and f"{last} 的下一位是 P1" in text
    assert "、".join(str(n) for n in rules.quest_sizes(players)) in text
    assert f"赞成达到 {rules.votes_to_approve(players)} 票则通过" in text
    assert f"全体 {players} 人同时对队伍投赞成或反对" in text
    assert f"其余 {players - 1} 人各发言一次" in text
    # 不留写死的人数措辞。
    for stale in ("五人阿瓦隆", "五名玩家", "其余三人都是好人", "其余四人", "全体五人"):
        assert stale not in text
    # 不在场的角色一个都不提。
    absent = [r for r in rules.Role if r not in set(rules.roles_for(players))]
    for role in absent:
        assert prompts.ROLE_SHORT_ZH[role] not in text, role


@pytest.mark.parametrize("players", [7, 8, 9, 10])
def test_system_prompt_states_the_fourth_quest_threshold(players):
    text = prompts.system_prompt("P1", Role.LOYAL_SERVANT, HiddenInfo(), players)
    assert "第 4 次任务是例外，需要 2 张失败牌才失败" in text


@pytest.mark.parametrize("players", [5, 6])
def test_system_prompt_has_no_threshold_exception_below_seven(players):
    text = prompts.system_prompt("P1", Role.LOYAL_SERVANT, HiddenInfo(), players)
    assert "出现 1 张失败牌任务即失败。" in text and "例外" not in text


def test_system_prompt_tells_merlin_about_mordred_without_naming_a_seat():
    text = prompts.system_prompt("P1", Role.MERLIN, HiddenInfo(evil_players=("P2", "P3")), 9)
    assert "莫德雷德" in text and "但你看不到他" in text
    assert "P2 和 P3" in text


def test_system_prompt_tells_oberon_he_is_alone():
    text = prompts.system_prompt("P5", Role.OBERON, HiddenInfo(), 7)
    assert "你不知道任何同伴" in text and "梅林能看到你" in text


def test_system_prompt_lists_every_fellow_for_evil_in_a_big_game():
    text = prompts.system_prompt("P1", Role.MORGANA, HiddenInfo(fellow_evils=("P4", "P7", "P9")), 10)
    assert "P4、P7 和 P9" in text
    assert "本局还有奥伯伦" in text


@pytest.mark.parametrize("players", [5, 6, 7, 8, 9, 10])
def test_execute_quest_instruction_carries_the_threshold(players):
    for quest_index in (1, 4):
        needed = rules.fails_to_fail_quest(players, quest_index)
        text = prompts.instruction(Action.EXECUTE_QUEST, team=("P1", "P2"), fails_needed=needed)
        assert f"本次任务出现 {needed} 张失败牌即失败" in text
