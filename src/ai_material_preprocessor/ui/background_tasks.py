from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from PySide6.QtCore import QThread, Signal

ResultT = TypeVar("ResultT")


class BackgroundCall(QThread):
    """Run a non-Qt callable outside the GUI thread and safely drop cancelled results."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, call: Callable[[], ResultT]) -> None:
        super().__init__()
        self._call = call

    def cancel(self) -> None:
        self.requestInterruption()

    def run(self) -> None:
        try:
            result = self._call()
        except Exception as exc:  # pragma: no cover - callers cover their error presentation.
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))
            return
        if not self.isInterruptionRequested():
            self.succeeded.emit(result)


_live_calls: set[BackgroundCall] = set()


def start_background_call(call: BackgroundCall) -> BackgroundCall:
    """Retain an unparented worker until it has stopped, including after dialog close."""

    _live_calls.add(call)

    def release() -> None:
        _live_calls.discard(call)
        call.deleteLater()

    call.finished.connect(release)
    call.start()
    return call
