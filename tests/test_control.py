"""两段式暂停与终止：控制器本身、裁判在检查点的行为、掐断后的线程回滚与原样重发。全部不联网。"""

import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from avalon.config import Config
from avalon.control import PAUSED, PAUSING, RUNNING, TERMINATING, CallCancelled, GameAborted, GameControl
from avalon.llm import LLMClient
from avalon.player import Action, LLMPlayer
from avalon.recorder import Recorder, paused_seconds
from avalon.referee import Referee
from avalon.rules import PLAYER_IDS
from avalon.state import Phase
from tests.test_player import FakeClient, notice
from tests.test_referee import ScriptedPlayer


def wait_for(pred, timeout=5.0, what="条件"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(0.005)
    raise AssertionError(f"等待超时：{what}")


class GatedPlayer(ScriptedPlayer):
    """闸门关着时每次行动都卡住（模拟慢模型），卡住期间可被掐断。"""

    def __init__(self, pid, gate: threading.Event, **kw):
        super().__init__(pid, **kw)
        self.gate = gate
        self.cancelled = 0
        self.received: list = []
        """收到的每份通知，含被掐断的那次；notices 只记成功作答的。"""

    def act(self, notice):
        self.received.append(notice)
        while not self.gate.is_set():
            if self.cancel_event.wait(0.005):
                self.cancelled += 1
                raise CallCancelled()
        return super().act(notice)


def make_game(tmp_path, gate, on_status=None):
    players = {pid: GatedPlayer(pid, gate, rng=random.Random(i)) for i, pid in enumerate(PLAYER_IDS)}
    config = Config(api_key="", model="test", seed=3, games_dir=tmp_path, parallel=True)
    recorder = Recorder(tmp_path / "g")
    control = GameControl(on_status=on_status)
    referee = Referee(players, config, recorder, random.Random(3), control=control)
    return players, recorder, control, referee


def kinds(recorder):
    return [e["kind"] for e in recorder.events]


# ------------------------------------------------------------ 控制器


def test_control_pause_without_inflight_is_immediate():
    seen = []
    c = GameControl(on_status=seen.append)
    assert c.status == RUNNING
    assert c.request_pause() == PAUSED
    assert c.resume() == RUNNING
    assert seen == [PAUSED, RUNNING]


def test_control_second_press_cancels_inflight():
    cancelled = []
    c = GameControl()
    c.begin_call("P1", lambda: cancelled.append("P1"))
    assert c.request_pause() == PAUSING
    assert cancelled == []
    assert c.request_pause() == PAUSING  # 掐断已发出，等 P1 的线程退出登记
    assert cancelled == ["P1"]
    c.end_call("P1")
    assert c.status == PAUSED


def test_control_checkpoint_blocks_while_paused_and_raises_on_stop():
    c = GameControl()
    c.request_pause()
    passed = threading.Event()

    def worker():
        try:
            c.checkpoint()
            passed.set()
        except GameAborted:
            passed.set()
            worker.aborted = True

    worker.aborted = False
    threading.Thread(target=worker, daemon=True).start()
    time.sleep(0.05)
    assert not passed.is_set()
    c.resume()
    wait_for(passed.is_set, what="继续后放行")
    assert not worker.aborted

    c.request_pause()
    passed.clear()
    threading.Thread(target=worker, daemon=True).start()
    time.sleep(0.02)
    assert c.request_stop() == TERMINATING
    wait_for(passed.is_set, what="终止后抛出")
    assert worker.aborted


# ------------------------------------------------------------ 裁判


def test_soft_pause_waits_for_inflight_then_blocks_next_notice(tmp_path):
    gate = threading.Event()
    statuses = []
    players, recorder, control, referee = make_game(tmp_path, gate, on_status=statuses.append)
    t = threading.Thread(target=referee.run, daemon=True)
    t.start()
    wait_for(lambda: "ask" in kinds(recorder), what="第一条提问")
    assert control.request_pause() == PAUSING  # 有一路调用卡在闸门后
    asks_before = kinds(recorder).count("ask")
    gate.set()  # 让那一路返回
    wait_for(lambda: control.status == PAUSED, what="调用返回后自动进入 paused")
    time.sleep(0.05)
    # 暂停期间不再发出新的通知，但返回的那次已正常记录。
    assert kinds(recorder).count("ask") == asks_before
    assert kinds(recorder).count("turn") == asks_before
    assert "voided_call" not in kinds(recorder)
    control.resume()
    t.join(5)
    assert referee.state.phase == Phase.GAME_OVER
    assert statuses == [PAUSING, PAUSED, RUNNING]


def test_hard_pause_voids_inflight_and_resends_same_notice(tmp_path):
    gate = threading.Event()
    players, recorder, control, referee = make_game(tmp_path, gate)
    t = threading.Thread(target=referee.run, daemon=True)
    t.start()
    wait_for(lambda: "ask" in kinds(recorder), what="第一条提问")
    first_ask = next(e for e in recorder.events if e["kind"] == "ask")
    assert control.request_pause() == PAUSING
    control.request_pause()  # 第二下：掐断
    wait_for(lambda: control.status == PAUSED, what="掐断后进入 paused")
    voided = [e for e in recorder.events if e["kind"] == "voided_call"]
    assert len(voided) == 1 and voided[0]["player"] == first_ask["player"]
    assert kinds(recorder).count("turn") == 0
    assert players[first_ask["player"]].cancelled == 1
    gate.set()
    control.resume()
    t.join(5)
    assert referee.state.phase == Phase.GAME_OVER
    # 被掐断的那次通知原样重发：同一玩家同一行动出现两条 ask，且第一次收到的两份通知内容一致。
    asks = [e for e in recorder.events if e["kind"] == "ask" and e["player"] == first_ask["player"]]
    assert asks[0]["action"] == asks[1]["action"] == first_ask["action"]
    p = players[first_ask["player"]]
    assert p.received[0] == p.received[1]
    # 每条 turn 对应且仅对应一次成功作答。
    assert kinds(recorder).count("turn") == sum(len(pl.notices) for pl in players.values())


def test_terminate_aborts_referee_and_voids_inflight(tmp_path):
    gate = threading.Event()
    players, recorder, control, referee = make_game(tmp_path, gate)
    box = {}

    def run():
        try:
            referee.run()
        except GameAborted:
            box["aborted"] = True

    t = threading.Thread(target=run, daemon=True)
    t.start()
    wait_for(lambda: "ask" in kinds(recorder), what="第一条提问")
    assert control.request_stop() == TERMINATING
    t.join(5)
    assert box.get("aborted") is True
    assert kinds(recorder).count("voided_call") == 1
    assert referee.state.phase != Phase.GAME_OVER
    # 终止后落盘的结果标明状态，且暂停时长为零。
    recorder.event("terminated")
    recorder.save_result(referee.state, status="terminated")
    result = json.loads((tmp_path / "g" / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "terminated" and result["winner"] is None and result["voided_calls"] == 1


def test_pause_during_parallel_voting_blocks_unsent_and_finishes_inflight(tmp_path):
    """投票阶段五路并行：暂停时已发出的返回、未发出的挡住；继续后全部完成且票数齐全。"""
    gate = threading.Event()
    gate.set()
    players, recorder, control, referee = make_game(tmp_path, gate)
    t = threading.Thread(target=referee.run, daemon=True)
    t.start()
    wait_for(lambda: any(e["kind"] == "ask" and e["action"] == "vote" for e in recorder.events), what="投票提问")
    control.request_pause()
    wait_for(lambda: control.status == PAUSED, what="进入 paused")
    # 进入 paused 后裁判可能还在记录刚收齐的一轮投票，但不会再发出任何新通知。
    time.sleep(0.05)
    asks_before = kinds(recorder).count("ask")
    time.sleep(0.05)
    assert kinds(recorder).count("ask") == asks_before
    control.resume()
    t.join(5)
    assert referee.state.phase == Phase.GAME_OVER
    for e in recorder.events:
        if e["kind"] == "votes":
            assert set(e["votes"]) == set(PLAYER_IDS)


def test_paused_seconds_from_events():
    events = [
        {"kind": "game_start", "ts": "2026-09-15T00:00:00.000+00:00"},
        {"kind": "paused", "ts": "2026-09-15T00:00:10.000+00:00"},
        {"kind": "resumed", "ts": "2026-09-15T00:00:25.500+00:00"},
        {"kind": "paused", "ts": "2026-09-15T00:01:00.000+00:00"},
        {"kind": "terminated", "ts": "2026-09-15T00:01:04.000+00:00"},
    ]
    assert paused_seconds(events) == pytest.approx(19.5)


# ------------------------------------------------------------ 玩家与模型客户端


class CancellingClient(FakeClient):
    def complete(self, messages, *, cancel=None):
        self.seen.append([dict(m) for m in messages])
        raise CallCancelled()


def test_llm_player_rolls_back_thread_when_cancelled():
    p = LLMPlayer("P1", CancellingClient([]))
    p.brief("系统提示")
    with pytest.raises(CallCancelled):
        p.act(notice(Action.SPEAK))
    assert [m["role"] for m in p.messages] == ["system"]
    assert p.drain_calls() == []


class SlowHandler(BaseHTTPRequestHandler):
    """一个永远不回话的假接口，用来验证掐断不必等它。"""

    def do_POST(self):
        time.sleep(8)
        self.send_response(500)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_llm_client_cancel_returns_promptly_without_waiting_for_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = LLMClient("k", f"http://127.0.0.1:{server.server_port}/v1", "m", timeout_s=20, max_retries=0)
        cancel = threading.Event()
        threading.Timer(0.3, cancel.set).start()
        t0 = time.monotonic()
        with pytest.raises(CallCancelled):
            client.complete([{"role": "user", "content": "hi"}], cancel=cancel)
        assert time.monotonic() - t0 < 2.0
        assert client._client is None  # 底层客户端已被关闭并丢弃
    finally:
        server.shutdown()
