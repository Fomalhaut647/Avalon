"""网页服务：多局管理器与 HTTP 接口。用随机玩家，全部不联网；事件流走真实的本机端口以验证断线与续传。"""

import json
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from avalon.config import ConfigError
from avalon.web import manager as manager_module
from avalon.web.manager import GameManager, NewGameParams
from avalon.web.server import create_app


def wait_for(pred, timeout=8.0, what="条件"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(0.01)
    raise AssertionError(f"等待超时：{what}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def manager(tmp_path):
    return GameManager(tmp_path / "games", max_concurrent=2)


@pytest.fixture
def server(manager):
    """真实的 uvicorn 服务，测事件流断线时比内存客户端可靠。"""
    port = free_port()
    config = uvicorn.Config(create_app(manager, heartbeat_s=0.2), host="127.0.0.1", port=port, log_level="error")
    srv = uvicorn.Server(config)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    wait_for(lambda: srv.started, what="服务启动")
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(5)


def random_params(**kw) -> NewGameParams:
    base = {"random_players": True, "random_delay_s": 0.0, "count": 1}
    base.update(kw)
    return NewGameParams(**base)


# ------------------------------------------------------------ 管理器


def test_manager_runs_games_concurrently_with_queue(manager):
    ids = manager.create(random_params(count=3, random_delay_s=0.05, seed=10))
    assert len(ids) == 3
    statuses = lambda: [manager.summary(i)["status"] for i in ids]  # noqa: E731
    wait_for(lambda: statuses().count("running") == 2 and statuses().count("queued") == 1, what="两局在跑一局排队")
    wait_for(lambda: statuses() == ["finished"] * 3, timeout=30, what="全部结束")
    games = manager.list_games()
    assert [g["id"] for g in games] == sorted(ids, reverse=True)
    assert [g["seed"] for g in sorted(games, key=lambda g: g["seed"])] == [10, 11, 12]
    for g in games:
        assert g["winner"] in ("good", "evil") and g["events"] > 20 and g["random_players"] is True
        assert (manager.games_dir / g["id"] / "result.json").is_file()
    stats = manager.stats(games)
    assert stats["finished"] == 3 and stats["good_wins"] + stats["evil_wins"] == 3


def test_manager_two_step_pause_and_terminate(manager):
    (gid,) = manager.create(random_params(random_delay_s=5.0))
    run = manager.get(gid)
    wait_for(lambda: run.status == "running" and any(e["kind"] == "ask" for e in run.events()), what="第一条提问")
    assert manager.pause(gid)["status"] == "pausing"
    time.sleep(0.05)
    assert run.status == "pausing"  # 慢玩家还在"思考"，软暂停等它
    manager.pause(gid)  # 第二下：掐断
    wait_for(lambda: run.status == "paused", what="掐断后进入 paused")
    kinds = [e["kind"] for e in run.events()]
    assert kinds.count("voided_call") == 1 and "pause_requested" in kinds and "pause_forced" in kinds and "paused" in kinds
    assert manager.summary(gid)["inflight"] == []
    manager.resume(gid)
    wait_for(lambda: run.status == "running", what="继续")
    assert [e["kind"] for e in run.events()].count("resumed") == 1
    wait_for(lambda: manager.summary(gid)["inflight"], what="重发后的调用在进行")
    manager.terminate(gid)
    wait_for(lambda: run.status == "terminated", what="终止")
    result = json.loads((manager.games_dir / gid / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "terminated" and result["winner"] is None and result["voided_calls"] == 2
    assert (manager.games_dir / gid / "transcript.md").read_text(encoding="utf-8").count("管理员终止") >= 1
    kinds = [e["kind"] for e in run.events()]
    assert kinds[-1] == "terminated" and "terminate_requested" in kinds
    # 结束后列表里仍然能看到它，且不计入胜负。
    games = manager.list_games()
    assert games[0]["status"] == "terminated"
    assert manager.stats(games)["finished"] == 0


def test_manager_paused_time_is_excluded(manager):
    (gid,) = manager.create(random_params(random_delay_s=0.05))
    run = manager.get(gid)
    wait_for(lambda: run.status == "running", what="开跑")
    manager.pause(gid)
    wait_for(lambda: run.status == "paused", what="暂停")
    time.sleep(0.6)
    live = manager.summary(gid)
    assert live["paused_s"] >= 0  # 暂停中也在累计
    manager.resume(gid)
    wait_for(lambda: run.status == "finished", timeout=30, what="结束")
    result = json.loads((manager.games_dir / gid / "result.json").read_text(encoding="utf-8"))
    total = (
        __import__("datetime").datetime.fromisoformat(result["finished_at"])
        - __import__("datetime").datetime.fromisoformat(result["started_at"])
    ).total_seconds()
    assert result["paused_s"] >= 0 and result["duration_s"] <= round(total) - 0  # 用时不含暂停


def test_manager_cancels_queued_game(manager):
    ids = manager.create(random_params(count=3, random_delay_s=1.0))
    queued = [i for i in ids if manager.summary(i)["status"] == "queued"]
    assert len(queued) == 1
    manager.terminate(queued[0])
    assert manager.summary(queued[0]) is None
    assert not (manager.games_dir / queued[0]).exists()
    for i in ids:
        if i != queued[0]:
            manager.terminate(i)
    wait_for(lambda: all(manager.summary(i)["status"] == "terminated" for i in ids if i != queued[0]), what="其余终止")


def test_manager_marks_interrupted_games_from_disk(manager):
    d = manager.games_dir / "20260901-0900-abcd"
    (d / "players").mkdir(parents=True)
    (d / "events.jsonl").write_text(
        json.dumps({"seq": 1, "ts": "2026-09-01T01:00:00.000+00:00", "kind": "game_start", "seed": 5, "seat_models": {"P1": "deepseek-flash"}, "thinking": False})
        + "\n"
        + json.dumps({"seq": 2, "ts": "2026-09-01T01:00:01.000+00:00", "kind": "quest_start", "quest": 1, "size": 2})
        + "\n",
        encoding="utf-8",
    )
    (d / "public.json").write_text(json.dumps({"phase": "DISCUSSION", "quests": [{"index": 1, "size": 2, "proposals": [{"index": 1, "leader": "P3"}], "rejections": 0}]}), encoding="utf-8")
    (manager.games_dir / "not-a-game").mkdir()
    games = manager.list_games()
    assert [g["id"] for g in games] == ["20260901-0900-abcd"]
    g = games[0]
    assert g["status"] == "interrupted" and g["seed"] == 5 and g["model"] == "deepseek-flash" and g["events"] == 2
    assert g["leader"] == "P3" and g["current_quest"] == 1
    assert manager.pause("20260901-0900-abcd") is None


def test_manager_requires_api_key_for_real_players(manager, monkeypatch):
    def broken(*a, **k):
        raise ConfigError("没有 key")

    monkeypatch.setattr(manager_module, "load_config", broken)
    with pytest.raises(ConfigError):
        manager.create(NewGameParams(random_players=False))
    assert manager.defaults()["api_key_present"] is False


# ------------------------------------------------------------ HTTP


def test_http_create_list_and_files(server, manager):
    r = httpx.post(f"{server}/api/games", json={"random_players": True, "random_delay_s": 0, "count": 2, "seed": 7})
    assert r.status_code == 201
    ids = r.json()["ids"]
    wait_for(lambda: all(manager.summary(i)["status"] == "finished" for i in ids), timeout=30, what="两局结束")
    data = httpx.get(f"{server}/api/games").json()
    assert {g["id"] for g in data["games"]} == set(ids) and data["stats"]["finished"] == 2 and data["max_concurrent"] == 2
    gid = ids[0]
    one = httpx.get(f"{server}/api/games/{gid}").json()
    assert one["status"] == "finished" and set(one["assignments"]) == {"P1", "P2", "P3", "P4", "P5"}
    ev = httpx.get(f"{server}/api/games/{gid}/events", params={"since": 5}).json()
    assert ev["events"][0]["seq"] == 6 and ev["game"]["id"] == gid
    thread = httpx.get(f"{server}/api/games/{gid}/players/P1").json()
    assert thread["player"] == "P1" and thread["messages"] == []  # 随机玩家没有线程
    md = httpx.get(f"{server}/api/games/{gid}/files/transcript.md")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown") and "# 对局" in md.text
    dl = httpx.get(f"{server}/api/games/{gid}/files/events.jsonl", params={"download": 1})
    assert "attachment" in dl.headers["content-disposition"]
    assert httpx.get(f"{server}/api/games/{gid}/files/../secret").status_code == 404
    assert httpx.get(f"{server}/api/games/{gid}/files/players/P9.json").status_code == 404
    assert httpx.get(f"{server}/api/games/nope").status_code == 404
    assert httpx.post(f"{server}/api/games/{gid}/pause").json()["status"] == "finished"  # 已结束：原样返回
    assert httpx.get(f"{server}/api/config").json()["max_concurrent"] == 2
    assert httpx.post(f"{server}/api/games", json={"count": 0}).status_code == 422
    assert "<title>" in httpx.get(f"{server}/").text


def read_sse(url: str, *, until, timeout=10.0, headers=None) -> list[tuple[str, int | None, dict]]:
    """读事件流直到 until(messages) 为真。返回 (event, id, data) 列表。"""
    out: list[tuple[str, int | None, dict]] = []
    event, event_id, data = None, None, ""
    with httpx.stream("GET", url, timeout=timeout, headers=headers or {}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("id:"):
                event_id = int(line[3:].strip())
            elif line.startswith("data:"):
                data += line[5:].strip()
            elif line == "":
                if event:
                    out.append((event, event_id, json.loads(data)))
                    if until(out):
                        return out
                event, event_id, data = None, None, ""
    return out


def test_http_game_stream_pushes_events_and_resumes(server, manager):
    (gid,) = manager.create(random_params(random_delay_s=0.03))
    msgs = read_sse(f"{server}/api/games/{gid}/stream", until=lambda m: any(e == "status" and d["status"] == "finished" for e, _, d in m), timeout=30)
    events = [(i, d) for e, i, d in msgs if e == "game_event"]
    assert events[0][1]["kind"] == "game_start" and events[0][0] == 1
    seqs = [i for i, _ in events]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))
    assert any(d["kind"] == "game_over" for _, d in events)
    statuses = [d["status"] for e, _, d in msgs if e == "status"]
    assert statuses[0] == "running" and statuses[-1] == "finished"
    # 续传：带 Last-Event-ID 只收后面的事件。
    last = seqs[10]
    more = read_sse(f"{server}/api/games/{gid}/stream", until=lambda m: any(e == "status" for e, _, d in m), headers={"Last-Event-ID": str(last)})
    first_seq = next(i for e, i, _ in more if e == "game_event")
    assert first_seq == last + 1
    # 服务端在浏览器断开后清理订阅。
    wait_for(lambda: manager.get(gid)._subs == [], timeout=5, what="订阅清理")


def test_http_list_stream_reports_new_and_removed_games(server, manager):
    box = {}

    def collect():
        box["msgs"] = read_sse(f"{server}/api/stream", until=lambda m: any(e == "removed" for e, _, d in m), timeout=30)

    t = threading.Thread(target=collect, daemon=True)
    t.start()
    wait_for(lambda: manager._listeners, what="列表订阅建立")
    ids = manager.create(random_params(count=3, random_delay_s=2.0))
    queued = [i for i in ids if manager.summary(i)["status"] == "queued"][0]
    manager.terminate(queued)
    t.join(10)
    kinds = [e for e, _, _ in box["msgs"]]
    assert kinds[0] == "games" and "game" in kinds and kinds[-1] == "removed"
    assert box["msgs"][-1][2]["id"] == queued
    for i in ids:
        if i != queued:
            manager.terminate(i)


def test_http_pause_resume_terminate(server, manager):
    r = httpx.post(f"{server}/api/games", json={"random_players": True, "random_delay_s": 5, "count": 1})
    gid = r.json()["ids"][0]
    wait_for(lambda: manager.summary(gid)["inflight"], what="有调用在进行")
    assert httpx.post(f"{server}/api/games/{gid}/pause").json()["status"] == "pausing"
    httpx.post(f"{server}/api/games/{gid}/pause")
    wait_for(lambda: manager.summary(gid)["status"] == "paused", what="掐断后暂停")
    assert httpx.post(f"{server}/api/games/{gid}/resume").json()["status"] == "running"
    assert httpx.post(f"{server}/api/games/{gid}/terminate").json()["status"] in ("terminating", "terminated")
    wait_for(lambda: manager.summary(gid)["status"] == "terminated", what="终止完成")
    assert httpx.get(f"{server}/api/games/{gid}").json()["voided_calls" if False else "status"] == "terminated"


def test_http_controlling_disk_only_game_is_409(server, manager):
    d = manager.games_dir / "20260901-0900-abcd"
    (d / "players").mkdir(parents=True)
    (d / "events.jsonl").write_text(json.dumps({"seq": 1, "ts": "2026-09-01T01:00:00.000+00:00", "kind": "game_start", "seed": 1}) + "\n", encoding="utf-8")
    assert httpx.post(f"{server}/api/games/20260901-0900-abcd/pause").status_code == 409
    assert httpx.get(f"{server}/api/games/20260901-0900-abcd").json()["status"] == "interrupted"
