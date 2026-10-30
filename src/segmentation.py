"""Máscara de persona (MediaPipe Image Segmenter, modelo selfie) + suavizado,
y composición persona/fondo."""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

MODEL = "selfie_segmenter_landscape.tflite"


def _odd(n: float) -> int:
    n = max(int(round(n)), 1)
    return n if n % 2 else n + 1


class PersonSegmenter:
    """Devuelve una máscara float32 0..1 del tamaño del frame (1 = persona).

    Pipeline (todo a la resolución chica del modelo, que es barato):
      confianza → rampa low/high (bordes más definidos) → dilatación de
      dilate_px + feather_px (cubre el halo del contorno y deja el degradé
      afuera) → promedio temporal (evita parpadeo) → blur (feather) → se
      escala al tamaño del frame.
    """

    def __init__(self, models_dir: Path, cfg: dict):
        path = models_dir / MODEL
        if not path.exists():
            raise RuntimeError(f"Falta {path}. Corré: python download_models.py")
        self.segmenter = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.VIDEO,
            output_confidence_masks=True, output_category_mask=False,
        ))
        self.low = float(cfg.get("low", 0.3))
        self.high = float(cfg.get("high", 0.7))
        self.temporal = float(cfg.get("temporal", 0.6))
        self.dilate_px = float(cfg.get("dilate_px", 14))
        self.feather_px = float(cfg.get("feather_px", 12))
        self.input_width = int(cfg.get("input_width", 512))
        self._prev: np.ndarray | None = None
        self._last_ts = -1
        self.mask: np.ndarray | None = None   # última máscara a tamaño completo

    def _ts(self) -> int:
        ts = int(time.perf_counter() * 1000)
        self._last_ts = max(ts, self._last_ts + 1)
        return self._last_ts

    def process(self, frame_bgr: np.ndarray) -> np.ndarray:
        h, w = frame_bgr.shape[:2]
        small = cv2.resize(frame_bgr, (self.input_width, round(h * self.input_width / w)),
                           interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        res = self.segmenter.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), self._ts())
        conf = res.confidence_masks[0].numpy_view()
        conf = np.squeeze(conf).astype(np.float32, copy=True)

        mh, mw = conf.shape[:2]
        px_scale = mw / w   # píxeles de máscara por píxel de frame
        m = np.clip((conf - self.low) / max(self.high - self.low, 1e-6), 0.0, 1.0)
        # Se dilata también lo que va a ocupar el feather: así el degradé del
        # borde queda todo por fuera de la persona y ningún píxel suyo se
        # filtra a medias (eso dejaba un contorno oscuro al estar invisible).
        grow = self.dilate_px + self.feather_px
        if grow > 0:
            k = _odd(grow * px_scale * 2)
            m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        if self._prev is not None and self._prev.shape == m.shape and self.temporal < 1.0:
            m = cv2.addWeighted(m, self.temporal, self._prev, 1.0 - self.temporal, 0.0)
        self._prev = m
        if self.feather_px > 0:
            k = _odd(self.feather_px * px_scale * 2)
            m = cv2.GaussianBlur(m, (k, k), 0)
        self.mask = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
        return self.mask

    def close(self) -> None:
        self.segmenter.close()


def composite(frame: np.ndarray, background: np.ndarray, hide: np.ndarray) -> np.ndarray:
    """salida = frame * (1 - hide) + fondo * hide.

    `hide` = máscara de persona * (1 - visibilidad): con visibilidad 1 la salida
    es el frame tal cual; con 0 la persona se reemplaza por el fondo y el resto
    de la imagen sigue en vivo.
    """
    keep = 1.0 - hide
    return cv2.blendLinear(frame, background, keep, hide)
