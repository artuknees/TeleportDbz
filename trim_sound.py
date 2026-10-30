"""Recorta el silencio del principio y del final de un audio (wav/ogg/mp3) y lo
guarda como WAV, para que el sonido arranque justo con la animación.

Uso:  python trim_sound.py assets/mi_sonido.mp3 [--out assets/mi_sonido.wav]
                                                 [--threshold-db -50] [--fade-ms 40]
El archivo original no se modifica.
"""
from __future__ import annotations

import argparse
import os
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100


def load(path: Path) -> np.ndarray:
    """Devuelve las muestras int16 (n, 2) a 44.1 kHz."""
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    pygame.mixer.init(frequency=SR, size=-16, channels=2)
    try:
        return pygame.sndarray.array(pygame.mixer.Sound(str(path))).copy()
    finally:
        pygame.mixer.quit()


def trim(samples: np.ndarray, threshold_db: float, pre_ms: float, fade_ms: float) -> tuple[np.ndarray, int, int]:
    level = np.abs(samples.astype(np.float32)).max(axis=1) / 32768.0
    loud = np.flatnonzero(level > 10 ** (threshold_db / 20))
    if not len(loud):
        raise ValueError("el archivo es todo silencio con ese umbral")
    start = max(int(loud[0] - pre_ms * SR / 1000), 0)
    end = int(loud[-1]) + 1
    out = samples[start:end].astype(np.float32)
    n_fade = min(int(fade_ms * SR / 1000), len(out))
    if n_fade:
        out[-n_fade:] *= np.linspace(1.0, 0.0, n_fade)[:, None]   # sin clic al cortar la cola
    return np.clip(out, -32768, 32767).astype(np.int16), start, end


def save(path: Path, samples: np.ndarray) -> None:
    with wave.open(str(path), "wb") as f:
        f.setnchannels(samples.shape[1])
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(np.ascontiguousarray(samples).tobytes())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src")
    p.add_argument("--out", help="por defecto: mismo nombre con extensión .wav")
    p.add_argument("--threshold-db", type=float, default=-50.0, help="nivel considerado silencio (dBFS)")
    p.add_argument("--pre-ms", type=float, default=5.0, help="margen antes del primer sonido")
    p.add_argument("--fade-ms", type=float, default=40.0, help="fade-out al final")
    args = p.parse_args()

    src = Path(args.src)
    out = Path(args.out) if args.out else src.with_suffix(".wav")
    if out.resolve() == src.resolve():
        print("La salida no puede pisar el original; usá --out", file=sys.stderr)
        return 1
    samples = load(src)
    trimmed, start, end = trim(samples, args.threshold_db, args.pre_ms, args.fade_ms)
    save(out, trimmed)
    print(f"{src.name}: {len(samples) / SR:.2f} s → {out.name}: {len(trimmed) / SR:.2f} s "
          f"(recorté {start / SR:.2f} s al principio y {(len(samples) - end) / SR:.2f} s al final)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
