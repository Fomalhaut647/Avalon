"""裁判：状态机主循环。

推进阶段、决定轮到谁、组装 Notice、校验 Reply、兜底、把公开动作写入公开记录。
阶段与转移见 docs/architecture.md 第四节，规则见 docs/rules.md。
"""

from __future__ import annotations

import random

from avalon.config import Config
from avalon.player import Player
from avalon.recorder import Recorder
from avalon.state import GameState


class Referee:
    def __init__(
        self,
        players: dict[str, Player],
        config: Config,
        recorder: Recorder,
        rng: random.Random,
    ) -> None:
        self.players = players
        self.config = config
        self.recorder = recorder
        self.rng = rng

    def run(self) -> GameState:
        """跑完一局，返回终局状态。"""
        raise NotImplementedError

    # 以下每个方法对应一个阶段。

    def _init(self) -> None:
        raise NotImplementedError

    def _discussion(self) -> None:
        raise NotImplementedError

    def _proposal(self) -> None:
        raise NotImplementedError

    def _voting(self) -> None:
        raise NotImplementedError

    def _quest_execution(self) -> None:
        raise NotImplementedError

    def _quest_result(self) -> None:
        raise NotImplementedError

    def _assassination(self) -> None:
        raise NotImplementedError

    def _game_over(self) -> None:
        raise NotImplementedError
