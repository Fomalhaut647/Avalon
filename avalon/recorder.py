"""落盘。每局一个自包含目录 games/<id>/，文件清单见 docs/architecture.md 第六节。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from avalon.state import GameState


class Recorder:
    def __init__(self, game_dir: Path) -> None:
        self.game_dir = game_dir

    def event(self, kind: str, **payload: Any) -> None:
        """追加一行到 events.jsonl。"""
        raise NotImplementedError

    def save_public(self, state: GameState) -> None:
        raise NotImplementedError

    def save_thread(self, player_id: str, messages: list[dict[str, str]]) -> None:
        raise NotImplementedError

    def save_result(self, state: GameState) -> None:
        raise NotImplementedError

    def write_transcript(self, state: GameState) -> None:
        """人可读的复盘稿 transcript.md。"""
        raise NotImplementedError
