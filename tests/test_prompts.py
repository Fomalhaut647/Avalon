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
    text = prompts.system_prompt("P1", Role.MERLIN, HiddenInfo(evil_players=("P2", "P5")))
    assert "你是 P1" in text and "梅林" in text and "P2 和 P5" in text
    text = prompts.system_prompt("P3", Role.PERCIVAL, HiddenInfo(merlin_or_morgana=("P1", "P5")))
    assert "P1 和 P5" in text
    text = prompts.system_prompt("P2", Role.ASSASSIN, HiddenInfo(fellow_evil="P5"))
    assert "P5" in text and "莫甘娜" in text
    text = prompts.system_prompt("P4", Role.LOYAL_SERVANT, HiddenInfo())
    assert "没有任何隐藏信息" in text
    for mark in prompts.ALL_MARKS:
        assert mark in text


def test_system_prompt_does_not_leak_other_roles():
    text = prompts.system_prompt("P4", Role.LOYAL_SERVANT, HiddenInfo())
    # 忠臣的 system prompt 不应包含任何具体座位的角色断言。
    for pid in ("P1", "P2", "P3", "P5"):
        assert f"{pid} 是" not in text
