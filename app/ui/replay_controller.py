from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal


@dataclass
class ReplayState:
    mode: str | None = None
    active_frame: int = 0
    running: bool = False


class ReplayController(QObject):
    state_changed = Signal(str, int, bool)

    def __init__(self, delay_ms: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._advance)
        self._state = ReplayState()
        self._max_frame = 0

    def start(self, mode: str, max_frame: int) -> None:
        self._max_frame = max(max_frame, 0)
        self._state.mode = mode
        self._state.active_frame = -1
        self._state.running = self._max_frame > 0
        if self._state.running:
            self._timer.start()
        else:
            self._timer.stop()
        self._emit_state()

    def pause(self) -> None:
        self._timer.stop()
        self._state.running = False
        self._emit_state()

    def resume(self) -> None:
        if self._state.mode is None or self._state.active_frame >= self._max_frame:
            return
        self._state.running = True
        self._timer.start()
        self._emit_state()

    def step(self) -> None:
        self._timer.stop()
        self._state.running = False
        self._advance()

    def reset(self) -> None:
        self._timer.stop()
        self._state.active_frame = -1
        self._state.running = False
        self._emit_state()

    @property
    def mode(self) -> str | None:
        return self._state.mode

    @property
    def active_frame(self) -> int:
        return self._state.active_frame

    def _advance(self) -> None:
        if self._state.mode is None:
            return
        if self._state.active_frame >= self._max_frame:
            self._timer.stop()
            self._state.running = False
            self._emit_state()
            return

        self._state.active_frame += 1
        if self._state.active_frame >= self._max_frame:
            self._timer.stop()
            self._state.running = False
        self._emit_state()

    def _emit_state(self) -> None:
        self.state_changed.emit(
            self._state.mode or "",
            self._state.active_frame,
            self._state.running,
        )
