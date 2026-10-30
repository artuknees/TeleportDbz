"""Sonido del efecto y pitidos de la cuenta regresiva (pygame.mixer, en
cualquier sistema operativo; winsound como respaldo en Windows).

Todo se reproduce en la salida de audio local. Para que lo escuche la reunión
hace falta un cable de audio virtual (ver README).
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

SR = 44100
DEFAULT_SOUND = "assets/teleport.wav"


class EffectSound:
    def __init__(self, cfg: dict, root: Path):
        self.sounds: dict[str, object] = {}
        self._tones: dict[tuple[int, int], object] = {}
        self.mixer_ok = False
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        try:
            import pygame
            pygame.mixer.init(frequency=SR, size=-16, channels=2, buffer=512)
            self.mixer_ok = True
        except Exception as e:
            log.warning("No se pudo iniciar el audio (%s); sigo sin sonido", e)
            return
        if not cfg.get("enabled", True):
            log.info("Sonido del efecto desactivado en la config")
            return
        volume = float(cfg.get("volume", 0.8))
        default = root / DEFAULT_SOUND
        for name in ("disappear", "appear"):
            rel = cfg.get(name)
            if not rel:
                continue
            path = Path(rel) if Path(rel).is_absolute() else root / rel
            if not path.exists() and path != default:
                log.warning("No encontré el sonido %s (%s); uso el sintético %s.", name, path, DEFAULT_SOUND)
                path = default
            if not path.exists():
                # El sonido sintético se genera la primera vez (no se versiona en git).
                from synth_sound import write_wav
                write_wav(path)
                log.info("Generé el sonido sintético %s", DEFAULT_SOUND)
            try:
                snd = pygame.mixer.Sound(str(path))
            except Exception as e:
                log.warning("No se pudo cargar %s: %s", path, e)
                continue
            snd.set_volume(volume)
            self.sounds[name] = snd
        if self.sounds:
            log.info("Sonidos cargados: %s", ", ".join(self.sounds))

    def play(self, name: str) -> None:
        snd = self.sounds.get(name)
        if snd is not None:
            snd.play()

    def beep(self, freq: int, ms: int) -> None:
        """Pitido sin bloquear."""
        if self.mixer_ok:
            import pygame
            key = (freq, ms)
            if key not in self._tones:
                t = np.arange(int(SR * ms / 1000)) / SR
                env = np.minimum(1.0, np.minimum(t, t[-1] - t) / 0.005)   # sin clics
                wave = (0.35 * 32767 * np.sin(2 * np.pi * freq * t) * env).astype(np.int16)
                self._tones[key] = pygame.sndarray.make_sound(np.column_stack([wave, wave]))
            self._tones[key].play()
        elif sys.platform == "win32":
            import winsound
            threading.Thread(target=winsound.Beep, args=(freq, ms), daemon=True).start()

    def close(self) -> None:
        if self.mixer_ok:
            import pygame
            pygame.mixer.quit()
