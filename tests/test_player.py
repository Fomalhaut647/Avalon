"""LLMPlayer 的线程维护，用假客户端替代真实 API。"""

import pytest

from avalon.llm import LLMResult
from avalon.player import Action, InvalidReply, LLMPlayer, Notice
from avalon.prompts import MARK_PRIVATE, MARK_SPEECH, MARK_VOTE


class FakeClient:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.seen: list[list[dict[str, str]]] = []

    def complete(self, messages, *, cancel=None):
        self.seen.append([dict(m) for m in messages])
        return LLMResult(text=self.replies.pop(0), prompt_tokens=10, completion_tokens=5, latency_s=0.1, reasoning="隐藏推理")


def notice(action: Action, reason: str | None = None) -> Notice:
    return Notice(
        player_id="P1",
        action=action,
        public_events=("事件甲", "事件乙"),
        scoreboard="比分",
        instruction="请发言",
        rejection_reason=reason,
    )


def test_thread_grows_by_two_per_turn_and_keeps_system_prompt():
    client = FakeClient([f"{MARK_PRIVATE}\n想法\n{MARK_SPEECH}\n你好", f"{MARK_PRIVATE}\n想法二\n{MARK_VOTE}赞成"])
    p = LLMPlayer("P1", client)
    p.brief("系统提示")
    r1 = p.act(notice(Action.SPEAK))
    r2 = p.act(notice(Action.VOTE))
    assert r1.public_speech == "你好" and r2.vote is True
    assert [m["role"] for m in p.messages] == ["system", "user", "assistant", "user", "assistant"]
    assert p.messages[0]["content"] == "系统提示"
    assert "事件甲" in p.messages[1]["content"] and "请发言" in p.messages[1]["content"]
    # 第二次调用发送的是整条线程。
    assert len(client.seen[1]) == 4
    calls = p.drain_calls()
    assert [c.prompt_tokens for c in calls] == [10, 10]
    assert all(c.reasoning == "隐藏推理" for c in calls)
    assert p.drain_calls() == []
    # 隐藏推理不进线程。
    assert all("隐藏推理" not in m["content"] for m in p.messages)


def test_invalid_reply_is_kept_in_thread_and_raised():
    client = FakeClient(["乱七八糟"])
    p = LLMPlayer("P1", client)
    p.brief("系统提示")
    with pytest.raises(InvalidReply):
        p.act(notice(Action.SPEAK))
    assert p.messages[-1] == {"role": "assistant", "content": "乱七八糟"}


def test_rejection_notice_renders_reason():
    client = FakeClient([f"{MARK_PRIVATE}\n想法\n{MARK_SPEECH}\n改好了"])
    p = LLMPlayer("P1", client)
    p.brief("系统提示")
    p.act(notice(Action.SPEAK, reason="缺少发言"))
    assert "缺少发言" in p.messages[1]["content"]
    assert "事件甲" not in p.messages[1]["content"]
