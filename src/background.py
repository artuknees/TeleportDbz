"""Captura del fondo (cuenta regresiva + promedio de N frames) e igualación de
exposición entre el fondo guardado y el video en vivo."""
from __future__ import annotations

import logging
import math
from typing import Callable

import cv2
import numpy as np

log = logging.getLogger(__name__)


class Background:
    IDLE, COUNTDOWN, CAPTURING = "idle", "countdown", "capturing"

    def __init__(self, countdown_s: float = 5.0, frames: int = 30,
                 on_event: Callable[[str], None] | None = None):
        """`on_event` recibe "tick" en cada segundo de la cuenta regresiva y
        "done" al terminar la captura (para los pitidos)."""
        self.on_event = on_event or (lambda _event: None)
        self.countdown_s = countdown_s
        self.frames = max(1, int(frames))
        self.phase = self.IDLE
        self.image: np.ndarray | None = None      # fondo actual (uint8, BGR)
        self._acc: np.ndarray | None = None
        self._n = 0
        self._t_end = 0.0
        self._last_seq = -1
        self._last_announced = None

    @property
    def ready(self) -> bool:
        return self.image is not None

    @property
    def busy(self) -> bool:
        return self.phase != self.IDLE

    def start(self, now: float) -> None:
        """Arranca la cuenta regresiva. El fondo anterior (si hay) se sigue
        usando hasta que el nuevo esté listo."""
        self.phase = self.COUNTDOWN
        self._t_end = now + self.countdown_s
        self._last_announced = None
        log.info("Fondo: salí de cuadro, capturando en %.0f s…", self.countdown_s)

    def status(self, now: float) -> str:
        if self.phase == self.COUNTDOWN:
            return f"fondo: sali de cuadro {math.ceil(max(self._t_end - now, 0))}"
        if self.phase == self.CAPTURING:
            return f"fondo: capturando {self._n}/{self.frames}"
        return "fondo: listo" if self.ready else "fondo: sin capturar"

    def feed(self, frame: np.ndarray, seq: int, now: float) -> None:
        if self.phase == self.COUNTDOWN:
            left = math.ceil(self._t_end - now)
            if left > 0 and left != self._last_announced:
                if left < self.countdown_s:
                    log.info("Fondo: %d…", left)
                self.on_event("tick")
            self._last_announced = left
            if now >= self._t_end:
                self.phase = self.CAPTURING
                self._acc = np.zeros(frame.shape, np.float32)
                self._n = 0
                self._last_seq = -1
        if self.phase == self.CAPTURING and seq != self._last_seq:
            self._last_seq = seq
            cv2.accumulate(frame, self._acc)
            self._n += 1
            if self._n >= self.frames:
                self.image = cv2.convertScaleAbs(self._acc / self._n)
                self._acc = None
                self.phase = self.IDLE
                log.info("Fondo capturado (%d frames). Ya podés volver a cuadro.", self._n)
                self.on_event("done")


class ExposureMatch:
    """Corrige el brillo/color del fondo guardado para que coincida con el video
    en vivo.

    La webcam ajusta sola la exposición y el balance de blancos: con vos fuera
    de cuadro (cuando se captura el fondo) la imagen queda distinta que con vos
    adelante, y al hacerte invisible se nota tu silueta como una mancha más
    clara u oscura. Además, estando adelante proyectás sombra y reflejos sobre
    la pared que el fondo guardado no tiene.

    Por eso la corrección es *local* cerca del borde y *global* adentro: a baja
    resolución se calcula la relación video/fondo en los píxeles visibles
    alrededor de la persona y se la extiende un poco hacia adentro de la
    silueta (convolución normalizada), así empalma sin costura con el video en
    vivo justo en el contorno; hacia el centro pasa suavemente a la exposición
    general de la escena, para no dibujar una "sombra" con tu forma.
    """

    def __init__(self, work_width: int = 160, edge_sigma: float = 0.035,
                 exclude: float = 0.005, smoothing: float = 0.3, max_gain: float = 2.0):
        self.work_w = work_width        # se mide a baja resolución: es barato
        self.edge_sigma = edge_sigma    # alcance de la corrección del borde (fracción del ancho)
        self.exclude = exclude          # franja junto a la máscara que no se usa para medir
        self.smoothing = smoothing      # peso de la medición nueva (estabilidad temporal)
        self.max_gain = max_gain
        self.gain_map: np.ndarray | None = None   # (sh, sw, 3) float32
        self._bbox: tuple[int, int, int, int] | None = None
        self._bg_key: np.ndarray | None = None
        self._bg_small: np.ndarray | None = None
        self._bg_ok: np.ndarray | None = None

    def reset(self) -> None:
        self.gain_map = None
        self._bg_key = None

    def update(self, frame: np.ndarray, background: np.ndarray, mask: np.ndarray) -> None:
        h, w = mask.shape
        sw, sh = self.work_w, max(round(h * self.work_w / w), 1)
        if self._bg_key is not background:   # el fondo cambia poco: su versión chica se cachea
            b = cv2.resize(background, (sw, sh), interpolation=cv2.INTER_AREA)
            # ignorar píxeles quemados o casi negros (no informan la ganancia)
            self._bg_ok = (b.min(axis=2) > 8) & (b.max(axis=2) < 250)
            self._bg_small = np.maximum(b.astype(np.float32), 1.0)
            self._bg_key = background
        b = self._bg_small
        f8 = cv2.resize(frame, (sw, sh), interpolation=cv2.INTER_AREA)
        f = f8.astype(np.float32)
        m = cv2.resize(mask, (sw, sh), interpolation=cv2.INTER_AREA)
        person = (m > 0.02).astype(np.uint8)
        k = max(3, int(self.exclude * sw * 2) | 1)
        near = cv2.dilate(person, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        valid = (near == 0) & self._bg_ok & (f8.max(axis=2) < 250)
        if valid.sum() < 50:
            return
        ratio = np.clip(f / b, 1.0 / self.max_gain, self.max_gain)
        v = valid.astype(np.float32)

        def normalized_blur(sigma_frac: float) -> tuple[np.ndarray, np.ndarray]:
            s = max(sigma_frac * sw, 0.5)
            den = cv2.GaussianBlur(v, (0, 0), s)
            num = cv2.GaussianBlur(ratio * v[..., None], (0, 0), s)
            return num / np.maximum(den, 1e-6)[..., None], den

        edge, den = normalized_blur(self.edge_sigma)
        # Interior: la exposición general de la escena (mediana, así no la tiran
        # para abajo las sombras que proyecta la persona alrededor suyo).
        g_global = np.median(ratio[valid], axis=0)
        wgt = np.clip(den / 0.15, 0.0, 1.0)[..., None]
        gain = (wgt * edge + (1.0 - wgt) * g_global).astype(np.float32)

        if self.gain_map is None or self.gain_map.shape != gain.shape:
            self.gain_map = gain
        else:
            cv2.addWeighted(gain, self.smoothing, self.gain_map, 1.0 - self.smoothing, 0.0, dst=self.gain_map)

        # Solo hace falta corregir donde la máscara reemplaza al video.
        ys, xs = np.nonzero(person)
        if len(ys):
            sx, sy = w / sw, h / sh
            pad = 2
            self._bbox = (int(max(0, (ys.min() - pad) * sy)), int(min(h, (ys.max() + 1 + pad) * sy)),
                          int(max(0, (xs.min() - pad) * sx)), int(min(w, (xs.max() + 1 + pad) * sx)))
        else:
            self._bbox = None

    def apply(self, background: np.ndarray) -> np.ndarray:
        if self.gain_map is None or self._bbox is None:
            return background
        h, w = background.shape[:2]
        y0, y1, x0, x1 = self._bbox
        sh, sw = self.gain_map.shape[:2]
        # Escala el mapa chico solo sobre el bbox: píxel (x, y) del recorte →
        # coordenada del mapa chico (mismo muestreo que un resize bilineal).
        kx, ky = sw / w, sh / h
        M = np.float32([[kx, 0, (x0 + 0.5) * kx - 0.5], [0, ky, (y0 + 0.5) * ky - 0.5]])
        g = cv2.warpAffine(self.gain_map, M, (x1 - x0, y1 - y0),
                           flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
        out = background.copy()
        out[y0:y1, x0:x1] = cv2.multiply(out[y0:y1, x0:x1], g, dtype=cv2.CV_8U)
        return out
