"""命令行入口。

- uv run avalon --seed 42            在终端跑一局
- uv run avalon serve                启动网页服务（裁判席），浏览器里开局与监控
"""

from __future__ import annotations

import argparse
import json
import random
import secrets
import sys
import time
from pathlib import Path

from avalon.config import Config, ConfigError, load_config
from avalon.player import build_players
from avalon.recorder import Recorder
from avalon.referee import Referee


def new_game_id() -> str:
    return time.strftime("%Y%m%d-%H%M") + "-" + secrets.token_hex(2)


def play(args: argparse.Namespace) -> None:
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
        referee.run()
    except KeyboardInterrupt:
        print("\n已中断，已落盘的内容在", recorder.game_dir, file=sys.stderr)
        sys.exit(130)
    elapsed = time.monotonic() - started

    result = json.loads((recorder.game_dir / "result.json").read_text(encoding="utf-8"))
    cost = f"，预计费用 {result['cost_cny']:.3f} 元（空闲时段价）" if result.get("llm_calls") else ""
    print(f"\n用时 {elapsed / 60:.1f} 分钟{cost}。复盘：{recorder.game_dir / 'transcript.md'}")


def serve(args: argparse.Namespace) -> None:
    import uvicorn

    from avalon.web.manager import GameManager
    from avalon.web.server import create_app

    manager = GameManager(Path(args.games_dir), max_concurrent=args.max_games)
    app = create_app(manager)
    print(f"裁判席：http://{args.host}:{args.port}/   对局目录 {Path(args.games_dir).resolve()}   同时最多 {args.max_games} 局")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


def main() -> None:
    parser = argparse.ArgumentParser(prog="avalon", description="五个 AI 玩家的阿瓦隆：终端跑一局，或启动网页裁判席")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，控制角色分配与队长随机")
    parser.add_argument("--games-dir", default="games", help="对局产物目录")
    parser.add_argument("--random-players", action="store_true", help="用随机玩家跑一局，不联网，用于自检")
    parser.add_argument("--sequential", action="store_true", help="投票等同时行动改为依次请求，不并发")
    parser.add_argument("--quiet", action="store_true", help="不在终端打印私下分析")
    sub = parser.add_subparsers(dest="command")
    sp = sub.add_parser("serve", help="启动网页服务（裁判席）")
    sp.add_argument("--host", default="127.0.0.1", help="监听地址，默认只监听本机；局域网访问用 0.0.0.0")
    sp.add_argument("--port", type=int, default=8000)
    sp.add_argument("--games-dir", default="games", help="对局产物目录")
    sp.add_argument("--max-games", type=int, default=8, help="同时进行的对局上限，多出的排队")
    args = parser.parse_args()
    if args.command == "serve":
        serve(args)
    else:
        play(args)


if __name__ == "__main__":
    main()
