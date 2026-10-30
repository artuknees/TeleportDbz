"""Genera un sonido de teletransportación sintético (original, sin copyright)
en assets/teleport.wav. Podés reemplazarlo por tu propio archivo (wav/ogg/mp3)
y apuntarlo en config.yaml (o config.local.yaml) → sound.

Uso:  python make_sound.py [--out assets/teleport.wav]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from synth_sound import write_wav  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=str(ROOT / "assets" / "teleport.wav"))
    out = Path(p.parse_args().out)
    print(f"Sonido generado: {out} ({write_wav(out):.2f} s)")


if __name__ == "__main__":
    main()
