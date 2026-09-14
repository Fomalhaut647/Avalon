"""命令行入口：uv run avalon --seed 42"""

from __future__ import annotations

import argparse
import random
import secrets
import sys
import time
from pathlib import Path

from avalon.config import Config, ConfigError, load_config
from avalon.llm import LLMClient
from avalon.player import LLMPlayer, Player, RandomPlayer
from avalon.recorder import Recorder
from avalon.referee import Referee
from avalon.rules import PLAYER_IDS


def new_game_id() -> str:
    return time.strftime("%Y%m%d-%H%M") + "-" + secrets.token_hex(2)


def build_players(config: Config, rng: random.Random, random_players: bool) -> dict[str, Player]:
    players: dict[str, Player] = {}
    for pid in PLAYER_IDS:
        if random_players:
            players[pid] = RandomPlayer(pid, random.Random(rng.randrange(2**31)))
        else:
            client = LLMClient(
                config.api_key,
                config.base_url,
                config.seat_models[pid],
                timeout_s=config.timeout_s,
                thinking=config.thinking,
            )
            players[pid] = LLMPlayer(pid, client)
    return players


def main() -> None:
    parser = argparse.ArgumentParser(prog="avalon", description="跑一局五个 AI 玩家的阿瓦隆")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，控制角色分配与队长随机")
    parser.add_argument("--games-dir", default="games", help="对局产物目录")
    parser.add_argument("--random-players", action="store_true", help="用随机玩家跑一局，不联网，用于自检")
    parser.add_argument("--sequential", action="store_true", help="投票等同时行动改为依次请求，不并发")
    parser.add_argument("--quiet", action="store_true", help="不在终端打印私下分析")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else secrets.randbelow(2**31)
    games_dir = Path(args.games_dir)
    if args.random_players:
        config = Config(api_key="", model="random", seed=seed, games_dir=games_dir, parallel=False)
    else:
        try:
            config = load_config(seed, games_dir, parallel=not args.sequential)
        except ConfigError as e:
            print(f"配置错误：{e}", file=sys.stderr)
            sys.exit(2)

    game_id = new_game_id()
    recorder = Recorder(games_dir / game_id)
    rng = random.Random(seed)
    players = build_players(config, rng, args.random_players)

    mode = "随机玩家" if args.random_players else f"模型 {config.model}，隐藏思考{'开' if config.thinking else '关'}"
    print(f"对局 {game_id}  种子 {seed}  {mode}  目录 {recorder.game_dir}")

    def on_public(text: str) -> None:
        print(text, flush=True)

    def on_private(pid: str, action: str, analysis: str) -> None:
        if not args.quiet:
            print(f"    🔒 {pid} 私下分析：{analysis.strip()}", flush=True)

    referee = Referee(players, config, recorder, rng, on_public=on_public, on_private=on_private)
    started = time.monotonic()
    try:
        state = referee.run()
    except KeyboardInterrupt:
        print("\n已中断，已落盘的内容在", recorder.game_dir, file=sys.stderr)
        sys.exit(130)
    elapsed = time.monotonic() - started
    print(f"\n用时 {elapsed / 60:.1f} 分钟。复盘：{recorder.game_dir / 'transcript.md'}")


if __name__ == "__main__":
    main()
