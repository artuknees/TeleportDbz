"""Hotkeys globales (funcionan aunque el foco esté en Meet o en otra app)."""
from __future__ import annotations

import logging
import queue
import sys

log = logging.getLogger(__name__)


class GlobalHotkeys:
    """Cada hotkey encola su nombre; el loop principal los consume con `poll()`,
    así toda la lógica corre en el hilo principal."""

    def __init__(self, bindings: dict[str, str]):
        from pynput import keyboard

        self.events: queue.SimpleQueue[str] = queue.SimpleQueue()
        mapping = {combo: (lambda name=name: self.events.put(name))
                   for name, combo in bindings.items() if combo}
        self.listener = keyboard.GlobalHotKeys(mapping)
        self.listener.start()
        log.info("Hotkeys globales: %s", ", ".join(f"{c} = {n}" for n, c in bindings.items() if c))
        if sys.platform == "darwin":
            self.listener.wait()
            if not getattr(self.listener, "IS_TRUSTED", True):
                log.warning("macOS no deja leer el teclado: las hotkeys no van a andar. Dale permiso "
                            "a la Terminal / VS Code en Ajustes del Sistema → Privacidad y seguridad → "
                            "Monitoreo de entrada (y Accesibilidad), y reiniciá la app.")
            log.info("En teclados de Mac las F se aprietan con Fn (Fn+F9, Fn+F8).")

    def poll(self) -> list[str]:
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    def stop(self) -> None:
        self.listener.stop()
