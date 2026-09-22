"""落盘。每局一个自包含目录 games/<id>/，文件清单见 docs/architecture.md 第六节。

线程安全：并发投票时多名玩家会同时写事件，所有写操作加锁。
每条事件写入后可以通过 on_event 回调转交给订阅者（网页服务据此实时推送）。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from avalon.rules import player_ids
from avalon.state import GameState, Phase


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def public_view(state: GameState) -> dict[str, Any]:
    """公开状态。角色只在 GAME_OVER 时出现，任务牌从不出现。"""
    quests = []
    for q in state.quests:
        quests.append(
            {
                "index": q.index,
                "size": q.size,
                "proposals": [asdict(p) for p in q.proposals],
                "team": list(q.team),
                "fail_count": q.fail_count,
                "succeeded": q.succeeded,
                "rejections": q.rejections,
            }
        )
    view: dict[str, Any] = {
        "game_id": state.game_id,
        "seed": state.seed,
        "phase": state.phase.value,
        "players": list(player_ids(state.players)),
        "success_count": state.success_count,
        "fail_count": state.fail_count,
        "quests": quests,
        "speeches": [asdict(s) for s in state.speeches],
        "assassination_target": state.assassination_target,
        "winner": state.winner.value if state.winner else None,
        "win_reason": state.win_reason,
    }
    if state.phase == Phase.GAME_OVER:
        view["assignments"] = {pid: role.value for pid, role in state.assignments.items()}
    return view


def paused_seconds(events: list[dict[str, Any]], until: datetime | None = None) -> float:
    """从 paused / resumed 事件对累计"没有任何调用在跑、纯等待"的秒数。

    仍在暂停中时，算到 until；未给 until 则算到最后一条事件（终止时的情形）。
    """
    total = 0.0
    since: datetime | None = None
    for e in events:
        if e["kind"] == "paused" and since is None:
            since = datetime.fromisoformat(e["ts"])
        elif e["kind"] == "resumed" and since is not None:
            total += (datetime.fromisoformat(e["ts"]) - since).total_seconds()
            since = None
    if since is not None and events:
        end = until or datetime.fromisoformat(events[-1]["ts"])
        total += (end - since).total_seconds()
    return total


class Recorder:
    def __init__(self, game_dir: Path, on_event: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.game_dir = game_dir
        self.players_dir = game_dir / "players"
        self.players_dir.mkdir(parents=True, exist_ok=True)
        self.events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._events_path = game_dir / "events.jsonl"
        self.on_event = on_event

    def event(self, kind: str, **payload: Any) -> None:
        """追加一行到 events.jsonl，然后交给订阅者。回调在锁内执行以保证顺序，必须很快返回。"""
        with self._lock:
            record = {
                "seq": len(self.events) + 1,
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "kind": kind,
                **payload,
            }
            self.events.append(record)
            with self._events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            if self.on_event is not None:
                self.on_event(record)

    def save_public(self, state: GameState) -> None:
        with self._lock:
            (self.game_dir / "public.json").write_text(_json(public_view(state)), encoding="utf-8")

    def save_thread(self, player_id: str, messages: list[dict[str, str]]) -> None:
        with self._lock:
            (self.players_dir / f"{player_id}.json").write_text(_json(messages), encoding="utf-8")

    def save_result(self, state: GameState, status: str = "finished", error: str | None = None) -> None:
        """status 取 finished / terminated / error。用时不含暂停时长。"""
        started = self.events[0]["ts"] if self.events else None
        finished = self.events[-1]["ts"] if self.events else None
        paused_s = paused_seconds(self.events)
        duration_s = None
        if started and finished:
            total = (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
            duration_s = int(round(total - paused_s))
        calls = [e for e in self.events if e["kind"] == "llm_call"]
        result = {
            "game_id": state.game_id,
            "seed": state.seed,
            "status": status,
            "error": error,
            "started_at": started,
            "finished_at": finished,
            "duration_s": duration_s,
            "paused_s": int(round(paused_s)),
            "thinking": self.events[0].get("thinking") if self.events else None,
            "seat_models": self.events[0].get("seat_models") if self.events else None,
            "assignments": {pid: role.value for pid, role in state.assignments.items()},
            "winner": state.winner.value if state.winner else None,
            "win_reason": state.win_reason,
            "assassination_target": state.assassination_target,
            "success_count": state.success_count,
            "fail_count": state.fail_count,
            "quests_played": len(state.quests),
            "fallbacks": sum(1 for e in self.events if e["kind"] == "fallback"),
            "invalid_replies": sum(1 for e in self.events if e["kind"] == "invalid_reply"),
            "voided_calls": sum(1 for e in self.events if e["kind"] == "voided_call"),
            "llm_calls": len(calls),
            "prompt_tokens": sum(e.get("prompt_tokens", 0) for e in calls),
            "completion_tokens": sum(e.get("completion_tokens", 0) for e in calls),
            "reasoning_tokens": sum(e.get("reasoning_tokens", 0) for e in calls),
            "cache_hit_tokens": sum(e.get("cache_hit_tokens", 0) for e in calls),
            "cache_miss_tokens": sum(e.get("cache_miss_tokens", 0) for e in calls),
            "cost_cny": round(sum(e.get("cost_cny") or 0 for e in calls), 4),
            "cost_note": "按 DeepSeek 空闲时段价格估算，高峰时段约为两倍",
        }
        with self._lock:
            (self.game_dir / "result.json").write_text(_json(result), encoding="utf-8")

    # ------------------------------------------------------------ transcript

    def write_transcript(self, state: GameState) -> None:
        """人可读的复盘稿 transcript.md。私下分析以引用块加锁标记区分。"""
        ids = player_ids(state.players)
        lines: list[str] = [f"# 对局 {state.game_id}", ""]
        lines.append(f"- 随机种子：{state.seed}")
        lines.append(f"- 人数：{state.players} 人（{ids[0]} 到 {ids[-1]}）")
        if state.assignments:
            roles = "，".join(f"{pid} = {state.assignments[pid].value}" for pid in ids)
            lines.append(f"- 角色：{roles}")
        if state.winner:
            lines.append(f"- 结果：{state.winner.value} 获胜（{state.win_reason}）")
        elif any(e["kind"] == "terminated" for e in self.events):
            lines.append("- 结果：对局被管理员终止，无胜方")
        elif any(e["kind"] == "error" for e in self.events):
            lines.append("- 结果：对局因出错中止，无胜方")
        lines.append("")

        for e in self.events:
            kind = e["kind"]
            if kind == "quest_start":
                lines += ["", f"## 第 {e['quest']} 次任务（{e['size']} 人）", ""]
            elif kind == "leader":
                how = "顺延" if e.get("rotated") else "随机"
                lines += [f"### 第 {e['quest']} 次任务 · 第 {e['proposal']} 次提案 · 队长 {e['leader']}（{how}）", ""]
            elif kind == "turn":
                lines += self._turn_lines(e)
            elif kind == "invalid_reply":
                lines.append(f"> ⚠️ {e['player']} 第 {e['attempt']} 次答案不合法：{e['reason']}")
                lines.append("")
            elif kind == "fallback":
                lines.append(f"> ⚠️ {e['player']} 连续不合法，裁判兜底：{e['value']}")
                lines.append("")
            elif kind == "votes":
                votes = e["votes"]
                parts = "，".join(f"{pid} {'赞成' if votes[pid] else '反对'}" for pid in ids if pid in votes)
                verdict = "通过" if e["approved"] else "否决"
                lines += [f"**投票**：{parts} → {verdict}", ""]
            elif kind == "quest_result":
                cards = "，".join(f"{pid} {'成功' if v else '失败'}" for pid, v in e["cards"].items())
                outcome = "成功" if e["succeeded"] else "失败"
                lines += [
                    f"**任务结果**：{outcome}，失败牌 {e['fail_count']} 张",
                    f"> 🔒 每张牌：{cards}",
                    "",
                ]
            elif kind == "assassination":
                lines += ["", "## 刺杀", "", f"刺客 {e['assassin']} 刺杀 {e['target']}，{'命中梅林' if e['hit'] else '未中'}。", ""]
            elif kind == "game_over":
                lines += ["", "## 结果", "", f"{e['winner']} 获胜：{e['win_reason']}", ""]
            elif kind == "voided_call":
                lines += [f"> ⏹ {e['player']} 的一次调用被管理员掐断（已等 {e['waited_s']:.0f} 秒），稍后原样重发", ""]
            elif kind == "paused":
                lines += ["> ⏸ 管理员暂停了对局", ""]
            elif kind == "resumed":
                lines += ["> ▶ 管理员继续了对局", ""]
            elif kind == "terminated":
                lines += ["", "## 结果", "", "对局被管理员终止，无胜方。", ""]
            elif kind == "error":
                lines += ["", "## 结果", "", f"对局因出错中止：{e.get('message')}", ""]
        (self.game_dir / "transcript.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    @staticmethod
    def _turn_lines(e: dict[str, Any]) -> list[str]:
        pid, action = e["player"], e["action"]
        out: list[str] = []
        if action in ("speak", "propose"):
            label = "总结并指派" if action == "propose" else "发言"
            out.append(f"**{pid} {label}**：{e.get('speech', '')}")
            if e.get("team"):
                out.append(f"**队伍**：{', '.join(e['team'])}")
        elif action == "vote":
            out.append(f"**{pid} 投票**：{'赞成' if e.get('vote') else '反对'}")
        elif action == "execute_quest":
            out.append(f"**{pid} 出牌**：{'成功' if e.get('card') else '失败'}")
        elif action == "assassinate":
            out.append(f"**{pid} 刺杀**：{e.get('target')}")
        analysis = (e.get("private_analysis") or "").strip()
        if analysis:
            quoted = "\n".join("> " + line for line in analysis.splitlines())
            out.append(f"> 🔒 {pid} 私下分析：\n{quoted}")
        out.append("")
        return out
