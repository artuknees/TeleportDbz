"""Máquina de estados VISIBLE → DISAPPEARING → INVISIBLE → APPEARING → VISIBLE."""
from __future__ import annotations

import enum
import logging

log = logging.getLogger(__name__)


class State(enum.Enum):
    VISIBLE = "VISIBLE"
    DISAPPEARING = "DISAPPEARING"
    INVISIBLE = "INVISIBLE"
    APPEARING = "APPEARING"


_NEXT = {State.DISAPPEARING: State.INVISIBLE, State.APPEARING: State.VISIBLE}


class TeleportState:
    def __init__(self, disappear_s: float, appear_s: float):
        self.durations = {State.DISAPPEARING: disappear_s, State.APPEARING: appear_s}
        self.state = State.VISIBLE
        self._t0 = 0.0

    def _set(self, new: State, now: float, reason: str = "") -> None:
        log.info("Estado: %s → %s%s", self.state.value, new.value, f" ({reason})" if reason else "")
        self.state = new
        self._t0 = now

    @property
    def animating(self) -> bool:
        return self.state in _NEXT

    def toggle(self, now: float, reason: str = "") -> bool:
        """Arranca la animación correspondiente. Devuelve False si se ignoró
        porque ya hay una animación en curso."""
        if self.animating:
            log.debug("Toggle ignorado durante %s", self.state.value)
            return False
        self._set(State.DISAPPEARING if self.state is State.VISIBLE else State.APPEARING, now, reason)
        self.update(now)
        return True

    def update(self, now: float) -> None:
        if self.animating and self.progress(now) >= 1.0:
            self._set(_NEXT[self.state], now)

    def progress(self, now: float) -> float:
        """0→1 dentro de la animación actual (1 fuera de una animación)."""
        if not self.animating:
            return 1.0
        dur = self.durations[self.state]
        if dur <= 0:
            return 1.0
        p = (now - self._t0) / dur
        return 1.0 if p >= 1.0 - 1e-9 else max(p, 0.0)

    def visibility(self, now: float) -> float:
        """1 = persona visible, 0 = invisible. Lineal durante las animaciones
        (los efectos de la etapa 4 la reinterpretan)."""
        p = self.progress(now)
        return {
            State.VISIBLE: 1.0,
            State.INVISIBLE: 0.0,
            State.DISAPPEARING: 1.0 - p,
            State.APPEARING: p,
        }[self.state]
