"""落盘。每局一个自包含目录 games/<id>/，文件清单见 docs/architecture.md 第六节。

线程安全：并发投票时多名玩家会同时写事件，所有写操作加锁。
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from avalon.rules import PLAYER_IDS
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
        "players": list(PLAYER_IDS),
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


class Recorder:
    def __init__(self, game_dir: Path) -> None:
        self.game_dir = game_dir
        self.players_dir = game_dir / "players"
        self.players_dir.mkdir(parents=True, exist_ok=True)
        self.events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._events_path = game_dir / "events.jsonl"

    def event(self, kind: str, **payload: Any) -> None:
        """追加一行到 events.jsonl。"""
        with self._lock:
            record = {
                "seq": len(self.events) + 1,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "kind": kind,
                **payload,
            }
            self.events.append(record)
            with self._events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def save_public(self, state: GameState) -> None:
        with self._lock:
            (self.game_dir / "public.json").write_text(_json(public_view(state)), encoding="utf-8")

    def save_thread(self, player_id: str, messages: list[dict[str, str]]) -> None:
        with self._lock:
            (self.players_dir / f"{player_id}.json").write_text(_json(messages), encoding="utf-8")

    def save_result(self, state: GameState) -> None:
        started = self.events[0]["ts"] if self.events else None
        finished = self.events[-1]["ts"] if self.events else None
        duration_s = None
        if started and finished:
            duration_s = int((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds())
        result = {
            "game_id": state.game_id,
            "seed": state.seed,
            "started_at": started,
            "finished_at": finished,
            "duration_s": duration_s,
            "thinking": self.events[0].get("thinking") if self.events else None,
            "assignments": {pid: role.value for pid, role in state.assignments.items()},
            "winner": state.winner.value if state.winner else None,
            "win_reason": state.win_reason,
            "assassination_target": state.assassination_target,
            "success_count": state.success_count,
            "fail_count": state.fail_count,
            "quests_played": len(state.quests),
            "fallbacks": sum(1 for e in self.events if e["kind"] == "fallback"),
            "invalid_replies": sum(1 for e in self.events if e["kind"] == "invalid_reply"),
            "prompt_tokens": sum(e.get("prompt_tokens", 0) for e in self.events if e["kind"] == "llm_call"),
            "completion_tokens": sum(
                e.get("completion_tokens", 0) for e in self.events if e["kind"] == "llm_call"
            ),
            "llm_calls": sum(1 for e in self.events if e["kind"] == "llm_call"),
        }
        with self._lock:
            (self.game_dir / "result.json").write_text(_json(result), encoding="utf-8")

    # ------------------------------------------------------------ transcript

    def write_transcript(self, state: GameState) -> None:
        """人可读的复盘稿 transcript.md。私下分析以引用块加锁标记区分。"""
        lines: list[str] = [f"# 对局 {state.game_id}", ""]
        lines.append(f"- 随机种子：{state.seed}")
        if state.assignments:
            roles = "，".join(f"{pid} = {state.assignments[pid].value}" for pid in PLAYER_IDS)
            lines.append(f"- 角色：{roles}")
        if state.winner:
            lines.append(f"- 结果：{state.winner.value} 获胜（{state.win_reason}）")
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
                parts = "，".join(f"{pid} {'赞成' if votes[pid] else '反对'}" for pid in PLAYER_IDS if pid in votes)
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
