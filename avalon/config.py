"""运行配置。从 .env 与命令行读取。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from avalon.rules import MAX_INVALID_RETRIES, PLAYER_IDS

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"
"""DeepSeek 接口上 V4.1 Flash 的模型 ID。"""

PRICES_CNY_PER_MILLION: dict[str, dict[str, float]] = {
    "deepseek-flash": {"cache_hit": 0.02, "cache_miss": 1.0, "output": 4.0},
    "deepseek-v4-pro": {"cache_hit": 0.15, "cache_miss": 4.5, "output": 13.5},
}
"""DeepSeek 空闲时段价格，元/百万 token，2026-09 价目表。高峰时段为两倍。输出价含隐藏推理 token。"""


def estimate_cost_cny(model: str, cache_hit: int, cache_miss: int, output: int) -> float | None:
    """按空闲时段价格估算一次调用的费用。未知模型返回 None。"""
    price = PRICES_CNY_PER_MILLION.get(model)
    if price is None:
        return None
    return (cache_hit * price["cache_hit"] + cache_miss * price["cache_miss"] + output * price["output"]) / 1_000_000


class ConfigError(RuntimeError):
    pass


@dataclass
class Config:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    seat_models: dict[str, str] = field(default_factory=dict)
    """座位 -> 模型 ID。v1 五项相同，结构上允许各不相同。"""
    seed: int = 0
    games_dir: Path = Path("games")
    max_invalid_retries: int = MAX_INVALID_RETRIES
    parallel: bool = True
    """投票、执行任务这类逻辑上同时的行动是否并发请求。测试用假玩家时关闭以保证可复现。"""
    timeout_s: float = 120.0
    thinking: bool = True
    """是否开启模型的隐藏思考。默认开，见 docs/decisions/0010；关闭时模型只有可见的私下分析可用，更快更省。"""

    def __post_init__(self) -> None:
        if not self.seat_models:
            self.seat_models = {pid: self.model for pid in PLAYER_IDS}


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def _thinking_from_env() -> bool:
    """DEEPSEEK_THINKING 未设置时默认开；写 off/false/0/no 关闭。"""
    raw = os.environ.get("DEEPSEEK_THINKING", "").strip()
    return True if not raw else _truthy(raw)


def load_config(seed: int, games_dir: Path | None = None, *, parallel: bool = True) -> Config:
    """读取 .env 中的 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL / DEEPSEEK_THINKING。"""
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise ConfigError("未找到 DEEPSEEK_API_KEY，请在 .env 中填写（参考 .env.example）")
    return Config(
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        model=os.environ.get("DEEPSEEK_MODEL", "").strip() or DEFAULT_MODEL,
        seed=seed,
        games_dir=games_dir or Path("games"),
        parallel=parallel,
        thinking=_thinking_from_env(),
    )
