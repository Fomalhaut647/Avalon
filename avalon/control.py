"""对局的运行控制：两段式暂停与终止。

裁判在每次向玩家发通知前调用 checkpoint()；进行中的模型调用通过 begin_call / end_call 登记。
状态：
- running      正常运行
- pausing      已请求暂停，但还有调用在进行中；等它们返回后自动进入 paused
- paused       没有任何调用在进行，所有将要发出的通知都被挡在 checkpoint 前
- terminating  已请求终止，等裁判线程退出

暂停按两下：第一下进入 pausing，不掐断进行中的调用，等它们返回；在 pausing 期间再按一下，
立刻掐断所有进行中的调用，直接进入 paused。终止总是立刻掐断进行中的调用。
本模块不含任何游戏逻辑，也不写日志；状态变化通过回调交给调用方记录。
"""

from __future__ import annotations

import threading
from collections.abc import Callable

RUNNING = "running"
PAUSING = "pausing"
PAUSED = "paused"
TERMINATING = "terminating"


class GameAborted(Exception):
    """对局被终止。由 checkpoint() 抛出，裁判主循环据此退出。"""


class CallCancelled(Exception):
    """一次进行中的模型调用被掐断。玩家据此回滚线程，裁判据此记一条作废调用并重发通知。"""


class GameControl:
    def __init__(self, on_status: Callable[[str], None] | None = None) -> None:
        self._cond = threading.Condition()
        self._pause_requested = False
        self._stop_requested = False
        self._cancel_all = False
        """已下达"掐断一切"：此后登记的调用也立刻掐断，直到继续。堵住 checkpoint 与 begin_call 之间的窄缝。"""
        self._inflight: dict[str, Callable[[], None]] = {}
        """进行中的调用：玩家 -> 掐断它的函数。"""
        self._on_status = on_status
        self._status = RUNNING

    # ------------------------------------------------------------ 查询

    @property
    def status(self) -> str:
        with self._cond:
            return self._status

    @property
    def inflight(self) -> tuple[str, ...]:
        with self._cond:
            return tuple(self._inflight)

    def _update_locked(self) -> str | None:
        """持锁时按标志算出状态；有变化则返回新状态，由调用方在锁外触发回调。"""
        if self._stop_requested:
            status = TERMINATING
        elif self._pause_requested:
            status = PAUSING if self._inflight else PAUSED
        else:
            status = RUNNING
        if status == self._status:
            return None
        self._status = status
        return status

    def _notify(self, status: str | None) -> None:
        if status is not None and self._on_status is not None:
            self._on_status(status)

    # ------------------------------------------------------------ 裁判侧

    def checkpoint(self) -> None:
        """发通知前调用。已请求终止则抛 GameAborted；已请求暂停则阻塞到继续为止。"""
        with self._cond:
            while True:
                if self._stop_requested:
                    raise GameAborted()
                if not self._pause_requested:
                    return
                self._cond.wait()

    def begin_call(self, player_id: str, cancel: Callable[[], None]) -> None:
        with self._cond:
            self._inflight[player_id] = cancel
            cancel_now = self._cancel_all
            changed = self._update_locked()
        if cancel_now:
            cancel()
        self._notify(changed)

    def end_call(self, player_id: str) -> None:
        with self._cond:
            self._inflight.pop(player_id, None)
            changed = self._update_locked()
            self._cond.notify_all()
        self._notify(changed)

    # ------------------------------------------------------------ 操作侧

    def request_pause(self) -> str:
        """第一下：软暂停。处于 pausing 时再按：掐断进行中的调用。返回新状态。"""
        with self._cond:
            if self._stop_requested:
                return self._status
            if self._pause_requested and self._inflight:
                self._cancel_inflight_locked()
            self._pause_requested = True
            changed = self._update_locked()
            status = self._status
        self._notify(changed)
        return status

    def resume(self) -> str:
        with self._cond:
            self._pause_requested = False
            if not self._stop_requested:
                self._cancel_all = False
            changed = self._update_locked()
            self._cond.notify_all()
            status = self._status
        self._notify(changed)
        return status

    def request_stop(self) -> str:
        """终止：掐断进行中的调用，让所有等在 checkpoint 的线程抛出 GameAborted。"""
        with self._cond:
            self._stop_requested = True
            self._cancel_inflight_locked()
            changed = self._update_locked()
            self._cond.notify_all()
            status = self._status
        self._notify(changed)
        return status

    def _cancel_inflight_locked(self) -> None:
        self._cancel_all = True
        for cancel in list(self._inflight.values()):
            try:
                cancel()
            except Exception:
                pass
