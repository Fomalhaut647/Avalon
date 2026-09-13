"""命令行入口：uv run avalon --seed 42"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="avalon", description="跑一局五个 AI 玩家的阿瓦隆")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，控制角色分配与队长随机")
    parser.add_argument("--games-dir", default="games", help="对局产物目录")
    args = parser.parse_args()
    raise NotImplementedError("尚未实现，见 docs/architecture.md")


if __name__ == "__main__":
    main()
