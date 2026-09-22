"""多局管理：新开、排队、运行、暂停、终止；对局列表与跨局统计；事件订阅。

每局在本进程里是一个线程，跑裁判主循环；同一时刻最多 max_concurrent 局，多出的排队。
对局列表合并两处来源：本进程里的对局（含排队中的）与 games/ 目录里已落盘的对局；
同一局两处都有时以本进程为准。

命名约定：`players` 只用于座位名单（`game_start` 事件与 `public.json`）；人数一律叫 `player_count`。
新开一局的请求体沿用 `players` 表示人数，见 `server.py`。

状态取值：
- queued       排队等待开始（尚未建目录）
- running / pausing / paused / terminating   见 control.py
- finished     正常打完
- terminated   被管理员终止
- error        模型调用连续失败等异常导致中止
- interrupted  目录里没有 result.json 且本进程不认识它：上次服务进程在它跑完前退出了
- cancelled    排队中就被终止，没有建目录，只作为那一次操作的返回值出现
"""

from __future__ import annotations

import json
import queue
import random
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from avalon.config import DEFAULT_MODEL, PRICES_CNY_PER_MILLION, Config, ConfigError, load_config
from avalon.control import PAUSING, GameAborted, GameControl
from avalon.player import build_players
from avalon.recorder import Recorder, paused_seconds
from avalon.referee import Referee
from avalon.rules import DEFAULT_PLAYERS, MAX_PLAYERS, MIN_PLAYERS, player_ids

LIVE_STATUSES = ("running", "pausing", "paused", "terminating")
TERMINAL_STATUSES = ("finished", "terminated", "error", "interrupted")
GAME_ID_RE = re.compile(r"^\d{8}-\d{4}-[0-9a-f]{4}$")
ALL_SEATS = tuple(f"P{i}" for i in range(1, MAX_PLAYERS + 1))
"""接口认得的全部座位编号。某一局只放行它实际有的那几个。"""
DOWNLOADABLE = ("transcript.md", "events.jsonl", "public.json", "result.json", *(f"players/{pid}.json" for pid in ALL_SEATS))
CONTROL_EVENTS = {"pausing": "pause_requested", "paused": "paused", "running": "resumed", "terminating": "terminate_requested"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_game_id() -> str:
    return time.strftime("%Y%m%d-%H%M") + "-" + secrets.token_hex(2)


@dataclass(frozen=True)
class NewGameParams:
    seed: int | None = None
    """留空则每局随机；给定且局数大于一时依次加一。"""
    thinking: bool = False
    model: str = DEFAULT_MODEL
    random_players: bool = False
    """不联网的随机玩家，用于试界面。"""
    random_delay_s: float = 1.5
    """随机玩家每次行动模拟的思考秒数。"""
    players: int = DEFAULT_PLAYERS
    """每局人数，5 到 10。"""
    count: int = 1


class GameRun:
    """本进程里的一局：参数、控制器、记录器、裁判线程、订阅者。"""

    def __init__(self, game_id: str, params: NewGameParams, config: Config, manager: GameManager) -> None:
        self.id = game_id
        self.params = params
        self.config = config
        self.manager = manager
        self.status = "queued"
        self.created_at = now_iso()
        self.finished_at: str | None = None
        self.error: str | None = None
        self.control = GameControl(on_status=self._on_control_status)
        self.recorder: Recorder | None = None
        self.referee: Referee | None = None
        self.thread: threading.Thread | None = None
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------ 生命周期

    def start(self) -> None:
        self.recorder = Recorder(self.manager.games_dir / self.id, on_event=self._on_event)
        rng = random.Random(self.config.seed)
        players = build_players(self.config, rng, self.params.random_players, self.params.random_delay_s)
        self.referee = Referee(players, self.config, self.recorder, rng, control=self.control)
        self._set_status("running")
        self.thread = threading.Thread(target=self._run, name=f"game-{self.id}", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        assert self.referee is not None and self.recorder is not None
        final = "finished"
        try:
            self.referee.run()
        except GameAborted:
            final = "terminated"
            self.recorder.event("terminated")
            self._finalize(final)
        except Exception as e:  # noqa: BLE001 - 任何异常都要落盘并标记，不能让线程静默死掉
            final = "error"
            self.error = f"{type(e).__name__}: {e}"
            self.recorder.event("error", message=self.error)
            self._finalize(final, error=self.error)
        finally:
            self.finished_at = now_iso()
            self._set_status(final)
            self.manager._run_finished(self)

    def _finalize(self, status: str, error: str | None = None) -> None:
        """非正常结束时把该写的都写全，让目录和正常结束的一局一样完整。"""
        assert self.referee is not None and self.recorder is not None
        state = self.referee.state
        self.recorder.save_public(state)
        self.recorder.save_result(state, status=status, error=error)
        for pid in player_ids(self.config.players):
            messages = self.referee.players[pid].messages
            if messages:
                self.recorder.save_thread(pid, messages)
        self.recorder.write_transcript(state)

    # ------------------------------------------------------------ 控制

    def pause(self) -> str:
        if self.status not in LIVE_STATUSES:
            return self.status
        before = self.control.status
        self.control.request_pause()
        if before == PAUSING and self.recorder is not None:
            self.recorder.event("pause_forced")
        return self.status

    def resume(self) -> str:
        if self.status in ("pausing", "paused"):
            self.control.resume()
        return self.status

    def terminate(self) -> str:
        if self.status == "queued":
            self._set_status("cancelled")
            return self.status
        if self.status in LIVE_STATUSES:
            self.control.request_stop()
        return self.status

    def _on_control_status(self, status: str) -> None:
        if self.status in TERMINAL_STATUSES:
            return
        if self.recorder is not None:
            self.recorder.event(CONTROL_EVENTS[status])
        self._set_status(status)

    # ------------------------------------------------------------ 订阅

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def _broadcast(self, message: dict[str, Any]) -> None:
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            q.put(message)

    def _on_event(self, record: dict[str, Any]) -> None:
        self._broadcast({"type": "event", "event": record})
        if record["kind"] in ("llm_call", "quest_result", "votes", "leader", "game_over", "voided_call", "ask"):
            self.manager.broadcast({"type": "game", "game": self.summary()})

    def _set_status(self, status: str) -> None:
        self.status = status
        summary = self.summary()
        self._broadcast({"type": "status", "game": summary})
        self.manager.broadcast({"type": "game", "game": summary})

    # ------------------------------------------------------------ 查询

    def events(self, since: int = 0) -> list[dict[str, Any]]:
        if self.recorder is None:
            return []
        return self.recorder.events[since:]

    def summary(self) -> dict[str, Any]:
        events = self.recorder.events if self.recorder else []
        state = self.referee.state if self.referee else None
        now = datetime.now(timezone.utc)
        started = events[0]["ts"] if events else None
        paused_s = paused_seconds(events, until=now if self.status in LIVE_STATUSES else None)
        duration_s = None
        if started:
            end = datetime.fromisoformat(events[-1]["ts"]) if self.status in TERMINAL_STATUSES else now
            duration_s = int(round((end - datetime.fromisoformat(started)).total_seconds() - paused_s))
        calls = [e for e in events if e["kind"] == "llm_call"]
        quest = state.current_quest if state and state.quests else None
        proposal = quest.proposals[-1] if quest and quest.proposals else None
        return {
            "id": self.id,
            "seed": self.config.seed,
            "status": self.status,
            "player_count": self.config.players,
            "model": self.config.model,
            "thinking": self.config.thinking,
            "random_players": self.params.random_players,
            "created_at": self.created_at,
            "started_at": started,
            "finished_at": self.finished_at,
            "duration_s": duration_s,
            "paused_s": int(round(paused_s)),
            "phase": state.phase.value if state else None,
            "quests": [{"index": q.index, "size": q.size, "succeeded": q.succeeded} for q in state.quests] if state else [],
            "success_count": state.success_count if state else 0,
            "fail_count": state.fail_count if state else 0,
            "current_quest": quest.index if quest else None,
            "current_proposal": proposal.index if proposal else None,
            "leader": proposal.leader if proposal else None,
            "rejections": quest.rejections if quest else 0,
            "winner": state.winner.value if state and state.winner else None,
            "win_reason": state.win_reason if state else None,
            "assassination_target": state.assassination_target if state else None,
            "assignments": {pid: r.value for pid, r in state.assignments.items()} if state else {},
            "llm_calls": len(calls),
            "cost_cny": round(sum(e.get("cost_cny") or 0 for e in calls), 4),
            "events": len(events),
            "inflight": list(self.control.inflight),
            "error": self.error,
            "server_now": now.isoformat(timespec="milliseconds"),
        }


def summary_from_disk(game_dir: Path) -> dict[str, Any] | None:
    """从落盘文件拼出一局的摘要。没有事件文件的目录不算一局。"""
    events_path = game_dir / "events.jsonl"
    if not events_path.is_file():
        return None
    first: dict[str, Any] = {}
    count = 0
    last_ts = None
    with events_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            count += 1
            if count == 1:
                first = json.loads(line)
            last_ts = line
    if last_ts:
        try:
            last_ts = json.loads(last_ts).get("ts")
        except json.JSONDecodeError:
            last_ts = None
    result: dict[str, Any] = {}
    result_path = game_dir / "result.json"
    if result_path.is_file():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result = {}
    public: dict[str, Any] = {}
    public_path = game_dir / "public.json"
    if public_path.is_file():
        try:
            public = json.loads(public_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            public = {}
    seat_models = first.get("seat_models") or result.get("seat_models") or {}
    model = seat_models.get("P1") if seat_models else None
    quests = public.get("quests", [])
    current = quests[-1] if quests else None
    proposal = current["proposals"][-1] if current and current.get("proposals") else None
    status = result.get("status") or ("finished" if result else "interrupted")
    seats = first.get("players") or public.get("players") or []
    return {
        "id": game_dir.name,
        "seed": first.get("seed", result.get("seed")),
        "status": status,
        "player_count": len(seats) or DEFAULT_PLAYERS,
        "model": model or "?",
        "thinking": first.get("thinking", result.get("thinking")),
        "random_players": model == "random",
        "created_at": first.get("ts"),
        "started_at": first.get("ts"),
        "finished_at": result.get("finished_at") or last_ts,
        "duration_s": result.get("duration_s"),
        "paused_s": result.get("paused_s", 0),
        "phase": public.get("phase"),
        "quests": [{"index": q["index"], "size": q["size"], "succeeded": q.get("succeeded")} for q in quests],
        "success_count": public.get("success_count", result.get("success_count", 0)),
        "fail_count": public.get("fail_count", result.get("fail_count", 0)),
        "current_quest": current["index"] if current else None,
        "current_proposal": proposal["index"] if proposal else None,
        "leader": proposal["leader"] if proposal else None,
        "rejections": current.get("rejections", 0) if current else 0,
        "winner": result.get("winner", public.get("winner")),
        "win_reason": result.get("win_reason", public.get("win_reason")),
        "assassination_target": result.get("assassination_target", public.get("assassination_target")),
        "assignments": result.get("assignments") or first.get("assignments") or {},
        "llm_calls": result.get("llm_calls", 0),
        "cost_cny": result.get("cost_cny", 0.0),
        "events": count,
        "inflight": [],
        "error": result.get("error"),
        "server_now": now_iso(),
    }


class GameManager:
    def __init__(self, games_dir: Path, *, max_concurrent: int = 8) -> None:
        self.games_dir = games_dir
        self.games_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent
        self.runs: dict[str, GameRun] = {}
        self._queue: deque[GameRun] = deque()
        self._lock = threading.Lock()
        self._listeners: list[queue.Queue] = []
        self._disk_cache: dict[str, tuple[tuple[float, float], dict[str, Any]]] = {}

    # ------------------------------------------------------------ 新开与排队

    def defaults(self) -> dict[str, Any]:
        """新开一局表单的默认值与环境情况。"""
        api_key_present = True
        try:
            config = load_config(0, self.games_dir)
            model, thinking = config.model, config.thinking
        except ConfigError:
            api_key_present = False
            model, thinking = DEFAULT_MODEL, True
        return {
            "model": model,
            "thinking": thinking,
            "player_count": DEFAULT_PLAYERS,
            "min_player_count": MIN_PLAYERS,
            "max_player_count": MAX_PLAYERS,
            "api_key_present": api_key_present,
            "known_models": sorted(PRICES_CNY_PER_MILLION),
            "max_concurrent": self.max_concurrent,
            "running": self.running_count(),
            "queued": len(self._queue),
        }

    def create(self, params: NewGameParams) -> list[str]:
        """建 count 局并尽量立刻开始，返回局号。真实模型缺 API key 时抛 ConfigError。"""
        if params.random_players:
            base = Config(api_key="", model="random", seed=0, players=params.players, games_dir=self.games_dir, parallel=True)
        else:
            base = load_config(0, self.games_dir, players=params.players)
            base = replace(base, model=params.model or base.model, seat_models={}, thinking=params.thinking)
        ids: list[str] = []
        with self._lock:
            for i in range(max(1, params.count)):
                seed = (params.seed + i) if params.seed is not None else secrets.randbelow(2**31)
                game_id = new_game_id()
                while game_id in self.runs or (self.games_dir / game_id).exists():
                    game_id = new_game_id()
                run = GameRun(game_id, params, replace(base, seed=seed, seat_models={}), self)
                self.runs[game_id] = run
                self._queue.append(run)
                ids.append(game_id)
        self._pump()
        for game_id in ids:
            self.broadcast({"type": "game", "game": self.runs[game_id].summary()})
        return ids

    def running_count(self) -> int:
        return sum(1 for r in self.runs.values() if r.status in LIVE_STATUSES)

    def _pump(self) -> None:
        to_start: list[GameRun] = []
        with self._lock:
            while self._queue and self.running_count() + len(to_start) < self.max_concurrent:
                run = self._queue.popleft()
                if run.status == "queued":
                    to_start.append(run)
        for run in to_start:
            run.start()

    def _run_finished(self, run: GameRun) -> None:
        self._pump()

    # ------------------------------------------------------------ 控制

    def get(self, game_id: str) -> GameRun | None:
        return self.runs.get(game_id)

    def pause(self, game_id: str) -> dict[str, Any] | None:
        run = self.runs.get(game_id)
        if run is None:
            return None
        run.pause()
        return run.summary()

    def resume(self, game_id: str) -> dict[str, Any] | None:
        run = self.runs.get(game_id)
        if run is None:
            return None
        run.resume()
        return run.summary()

    def terminate(self, game_id: str) -> dict[str, Any] | None:
        run = self.runs.get(game_id)
        if run is None:
            return None
        was_queued = run.status == "queued"
        run.terminate()
        if was_queued:
            with self._lock:
                if run in self._queue:
                    self._queue.remove(run)
                self.runs.pop(game_id, None)
            self.broadcast({"type": "removed", "id": game_id})
            self._pump()
        return run.summary()

    # ------------------------------------------------------------ 查询

    def summary(self, game_id: str) -> dict[str, Any] | None:
        run = self.runs.get(game_id)
        if run is not None:
            return run.summary()
        if not GAME_ID_RE.match(game_id):
            return None
        return self._disk_summary(self.games_dir / game_id)

    def _disk_summary(self, game_dir: Path) -> dict[str, Any] | None:
        events_path = game_dir / "events.jsonl"
        result_path = game_dir / "result.json"
        if not events_path.is_file():
            return None
        key = (events_path.stat().st_mtime, result_path.stat().st_mtime if result_path.is_file() else 0.0)
        cached = self._disk_cache.get(game_dir.name)
        if cached and cached[0] == key:
            return cached[1]
        summary = summary_from_disk(game_dir)
        if summary is not None:
            self._disk_cache[game_dir.name] = (key, summary)
        return summary

    def list_games(self) -> list[dict[str, Any]]:
        games: dict[str, dict[str, Any]] = {}
        for d in self.games_dir.iterdir() if self.games_dir.is_dir() else []:
            if d.is_dir() and GAME_ID_RE.match(d.name) and d.name not in self.runs:
                s = self._disk_summary(d)
                if s is not None:
                    games[d.name] = s
        for run in list(self.runs.values()):
            games[run.id] = run.summary()
        return sorted(games.values(), key=lambda g: g["id"], reverse=True)

    @staticmethod
    def stats(games: list[dict[str, Any]]) -> dict[str, Any]:
        """跨局统计。胜负类只算正常打完的局；费用与调用数算所有有记录的局。"""
        finished = [g for g in games if g["status"] == "finished"]
        assassinations = [g for g in finished if g.get("assassination_target")]
        hits = [g for g in assassinations if g.get("win_reason") == "merlin_assassinated"]
        return {
            "total": len(games),
            "finished": len(finished),
            "live": sum(1 for g in games if g["status"] in LIVE_STATUSES),
            "queued": sum(1 for g in games if g["status"] == "queued"),
            "good_wins": sum(1 for g in finished if g.get("winner") == "good"),
            "evil_wins": sum(1 for g in finished if g.get("winner") == "evil"),
            "assassinations": len(assassinations),
            "assassination_hits": len(hits),
            "cost_cny": round(sum(g.get("cost_cny") or 0 for g in games), 4),
            "llm_calls": sum(g.get("llm_calls") or 0 for g in games),
            "duration_s": sum(g.get("duration_s") or 0 for g in finished),
        }

    def events(self, game_id: str, since: int = 0) -> list[dict[str, Any]] | None:
        run = self.runs.get(game_id)
        if run is not None:
            return run.events(since)
        path = self._file(game_id, "events.jsonl")
        if path is None:
            return None
        out: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= since and line.strip():
                    out.append(json.loads(line))
        return out

    def seats_of(self, game_id: str) -> tuple[str, ...]:
        """这一局实际有的座位。落盘的旧局没有座位名单时按 5 人。"""
        summary = self.summary(game_id)
        return player_ids(summary["player_count"]) if summary else ()

    def player_thread(self, game_id: str, pid: str) -> list[dict[str, str]] | None:
        run = self.runs.get(game_id)
        if run is not None and run.referee is not None:
            return list(run.referee.players[pid].messages) if pid in run.referee.players else None
        path = self._file(game_id, f"players/{pid}.json")
        if path is None:
            return [] if self.summary(game_id) else None
        return json.loads(path.read_text(encoding="utf-8"))

    def _file(self, game_id: str, name: str) -> Path | None:
        if not GAME_ID_RE.match(game_id) or name not in DOWNLOADABLE:
            return None
        path = self.games_dir / game_id / name
        return path if path.is_file() else None

    def file(self, game_id: str, name: str) -> Path | None:
        return self._file(game_id, name)

    # ------------------------------------------------------------ 列表订阅

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._listeners.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._listeners:
                self._listeners.remove(q)

    def broadcast(self, message: dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for q in listeners:
            q.put(message)
