"""运行配置。从 .env 与命令行读取。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from avalon.rules import MAX_INVALID_RETRIES, PLAYER_IDS


@dataclass
class Config:
    api_key: str
    base_url: str
    model: str
    seat_models: dict[str, str] = field(default_factory=dict)
    """座位 -> 模型 ID。v1 五项相同，结构上允许各不相同。"""
    seed: int = 0
    games_dir: Path = Path("games")
    max_invalid_retries: int = MAX_INVALID_RETRIES

    def __post_init__(self) -> None:
        if not self.seat_models:
            self.seat_models = {pid: self.model for pid in PLAYER_IDS}


def load_config(seed: int, games_dir: Path | None = None) -> Config:
    """读取 .env 中的 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL。"""
    raise NotImplementedError
