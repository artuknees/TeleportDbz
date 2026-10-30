"""Sonido de teletransportación sintético (original, sin copyright).

Lo usan make_sound.py y, si falta assets/teleport.wav, la app al arrancar.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100


def envelope(t: np.ndarray, attack: float, decay: float) -> np.ndarray:
    return np.minimum(t / attack, 1.0) * np.exp(-np.maximum(t - attack, 0) / decay)


def synth(duration: float = 0.55, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * duration)) / SR

    # "zip": barrido ascendente exponencial
    f0, f1, sweep = 350.0, 3200.0, 0.22
    freq = f0 * (f1 / f0) ** np.minimum(t / sweep, 1.0)
    zip_ = np.sin(2 * np.pi * np.cumsum(freq) / SR) * envelope(t, 0.008, 0.09)

    # "whoosh": ruido filtrado (pasa-banda casero) que crece y se apaga
    noise = rng.standard_normal(t.size)
    k = 24
    low = np.convolve(noise, np.ones(k) / k, mode="same")
    band = low - np.convolve(low, np.ones(k * 6) / (k * 6), mode="same")
    whoosh = band / (np.abs(band).max() + 1e-9) * np.sin(np.pi * np.minimum(t / 0.42, 1.0)) ** 2

    # "ting": destello metálico corto
    t2 = np.maximum(t - 0.2, 0)
    ting = (np.sin(2 * np.pi * 1900 * t2) + 0.5 * np.sin(2 * np.pi * 2870 * t2)) * envelope(t2, 0.003, 0.08)
    ting[t < 0.2] = 0

    mono = 0.55 * zip_ + 0.45 * whoosh + 0.35 * ting
    fade = np.minimum((duration - t) / 0.03, 1.0)  # sin clic al final
    mono *= fade
    mono /= np.abs(mono).max() + 1e-9
    mono *= 0.85

    # un poco de paneo para que tenga cuerpo
    pan = 0.5 + 0.35 * np.sin(2 * np.pi * 3.0 * t)
    stereo = np.stack([mono * (1.2 - pan), mono * (0.2 + pan)], axis=1)
    stereo /= np.abs(stereo).max() + 1e-9
    return (stereo * 0.85 * 32767).astype(np.int16)


def write_wav(path: Path) -> float:
    """Genera el sonido en `path` (WAV estéreo 16 bit) y devuelve su duración."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = synth()
    with wave.open(str(path), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(data.tobytes())
    return data.shape[0] / SR
