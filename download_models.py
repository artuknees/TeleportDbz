"""Descarga los modelos oficiales de MediaPipe a models/.

Uso:  python download_models.py [--force]
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

BASE = "https://storage.googleapis.com/mediapipe-models"
MODELS = {
    "hand_landmarker.task": f"{BASE}/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
    "face_landmarker.task": f"{BASE}/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
    "pose_landmarker_lite.task": f"{BASE}/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    "selfie_segmenter_landscape.tflite": f"{BASE}/image_segmenter/selfie_segmenter_landscape/float16/latest/selfie_segmenter_landscape.tflite",
}

MODELS_DIR = Path(__file__).resolve().parent / "models"


def download(name: str, url: str, force: bool) -> None:
    dest = MODELS_DIR / name
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"  ya existe  {name}")
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  bajando    {name} …", end="", flush=True)
    with urllib.request.urlopen(url, timeout=60) as resp, tmp.open("wb") as f:
        while chunk := resp.read(1 << 16):
            f.write(chunk)
    tmp.replace(dest)
    print(f" {dest.stat().st_size / 1e6:.1f} MB")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true", help="vuelve a bajar aunque ya existan")
    args = p.parse_args()
    MODELS_DIR.mkdir(exist_ok=True)
    print(f"Modelos en {MODELS_DIR}")
    try:
        for name, url in MODELS.items():
            download(name, url, args.force)
    except OSError as e:
        print(f"\nError descargando: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
