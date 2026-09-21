"""费用估算与配置默认值。"""

from avalon.config import PRICES_CNY_PER_MILLION, Config, estimate_cost_cny, load_config
from avalon.rules import PLAYER_IDS


def test_estimate_cost_uses_offpeak_prices():
    # 100 万命中 + 100 万未命中 + 100 万输出 = 0.02 + 1 + 4 元
    assert estimate_cost_cny("deepseek-flash", 1_000_000, 1_000_000, 1_000_000) == 5.02
    assert estimate_cost_cny("deepseek-v4-pro", 1_000_000, 0, 0) == 0.15
    assert estimate_cost_cny("unknown-model", 1, 1, 1) is None
    assert estimate_cost_cny("deepseek-flash", 0, 0, 0) == 0


def test_price_table_has_three_parts_for_every_model():
    for price in PRICES_CNY_PER_MILLION.values():
        assert set(price) == {"cache_hit", "cache_miss", "output"}


def test_config_fills_seat_models():
    c = Config(api_key="k")
    assert c.seat_models == {pid: c.model for pid in PLAYER_IDS}
    assert c.thinking is True and c.parallel is True


def test_thinking_defaults_on_and_env_can_turn_it_off(monkeypatch, tmp_path):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.delenv("DEEPSEEK_THINKING", raising=False)
    assert load_config(1, tmp_path).thinking is True
    for raw, expected in (("off", False), ("0", False), ("no", False), ("on", True), ("true", True), ("", True)):
        monkeypatch.setenv("DEEPSEEK_THINKING", raw)
        assert load_config(1, tmp_path).thinking is expected, raw
