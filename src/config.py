"""Carga de config.yaml con valores por defecto."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

DEFAULTS: dict = {
    "camera": {"index": 0, "width": 1280, "height": 720, "fps": 30, "backend": "auto"},
    "output": {"virtual_camera": True, "vcam_backend": "auto", "mirror": False},
    "detection": {"width": 640, "max_fps": 30, "min_confidence": 0.5, "num_hands": 2},
    "gesture": {"hold_frames": 8, "cooldown_s": 2.0},
    "background": {"countdown_s": 5, "frames": 30, "match_exposure": True, "beep": True},
    "segmentation": {},
    "effects": {"disappear_s": 0.4, "appear_s": 0.4},
    "sound": {"enabled": True, "disappear": "assets/teleport.wav", "appear": "assets/teleport.wav",
              "volume": 0.8},
    "hotkeys": {"toggle": "<f9>", "recapture_background": "<f8>"},
    "logging": {"level": "INFO"},
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def local_path(path: str | Path) -> Path:
    """config.yaml → config.local.yaml (ajustes personales, fuera de git)."""
    path = Path(path)
    return path.with_name(f"{path.stem}.local{path.suffix}")


def load_config(path: str | Path) -> dict:
    """Valores por defecto ← config.yaml ← config.local.yaml (si existe)."""
    path = Path(path)
    return _merge(_merge(DEFAULTS, _read(path)), _read(local_path(path)))
