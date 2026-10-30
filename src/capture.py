"""Webcam (lectura en un hilo aparte) y salida a cámara virtual."""
from __future__ import annotations

import logging
import sys
import threading
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)

_BACKENDS = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "avfoundation": cv2.CAP_AVFOUNDATION,
             "v4l2": cv2.CAP_V4L2, "any": cv2.CAP_ANY}


def _capture_api(backend: str) -> int:
    """"auto" elige el backend de captura según el sistema operativo."""
    if backend == "auto":
        backend = {"win32": "dshow", "darwin": "avfoundation"}.get(sys.platform, "v4l2")
    return _BACKENDS.get(backend, cv2.CAP_ANY)


class Webcam:
    """Lee frames en un hilo para que el loop principal nunca espere a la cámara.

    `read()` devuelve el último frame disponible (y un número de secuencia, para
    saber si es nuevo).
    """

    def __init__(self, index: int, width: int, height: int, fps: int, backend: str = "auto"):
        self.cap = cv2.VideoCapture(index, _capture_api(backend))
        if not self.cap.isOpened():
            hint = (" En Mac: dale permiso de Cámara a la Terminal / VS Code en Ajustes del "
                    "Sistema → Privacidad y seguridad → Cámara." if sys.platform == "darwin" else "")
            raise RuntimeError(
                f"No se pudo abrir la cámara {index}. ¿Está ocupada por otra app "
                f"(Meet, Teams, OBS)? Probá otro índice con --list-cameras.{hint}"
            )
        # MJPG permite 720p a 30 FPS en la mayoría de las webcams USB.
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        ok, frame = self.cap.read()
        if not ok:
            self.cap.release()
            raise RuntimeError(f"La cámara {index} se abrió pero no entrega imagen.")
        self.height, self.width = frame.shape[:2]
        log.info("Webcam %d abierta: %dx%d @ %.0f FPS pedidos",
                 index, self.width, self.height, self.cap.get(cv2.CAP_PROP_FPS) or fps)
        if (self.width, self.height) != (width, height):
            log.warning("La cámara no soporta %dx%d; usando %dx%d", width, height, self.width, self.height)

        self._frame = frame
        self._seq = 1
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="webcam", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            with self._lock:
                self._frame = frame
                self._seq += 1

    def read(self) -> tuple[np.ndarray, int]:
        with self._lock:
            return self._frame, self._seq

    def release(self) -> None:
        self._running = False
        self._thread.join(timeout=1.0)
        self.cap.release()
        log.info("Webcam liberada")


class VirtualCamera:
    def __init__(self, width: int, height: int, fps: int, backend: str = "auto"):
        import pyvirtualcam

        try:
            self.cam = pyvirtualcam.Camera(
                width=width, height=height, fps=fps, fmt=pyvirtualcam.PixelFormat.BGR,
                backend=None if backend == "auto" else backend,   # auto: OBS en Windows/Mac, v4l2loopback en Linux
            )
        except RuntimeError as e:
            if sys.platform == "darwin":
                hint = ("En Mac: abrí OBS, tocá «Iniciar cámara virtual» una vez (instala la "
                        "extensión de cámara y macOS pide permitirla), detenela y cerrá OBS.")
            elif sys.platform == "win32":
                hint = "Instalá OBS Studio y abrilo una vez."
            else:
                hint = "Cargá v4l2loopback (ver README)."
            raise RuntimeError(
                f"No se pudo iniciar la cámara virtual ({e}). {hint} Si sigue fallando, "
                "cerrá OBS: no puede estar usando la cámara virtual al mismo tiempo."
            ) from e
        log.info("Cámara virtual iniciada: %s (%dx%d @ %d FPS)", self.cam.device, width, height, fps)

    def send(self, frame_bgr: np.ndarray) -> None:
        self.cam.send(frame_bgr)

    def sleep_until_next_frame(self) -> None:
        self.cam.sleep_until_next_frame()

    def release(self) -> None:
        self.cam.close()
        log.info("Cámara virtual cerrada")


def list_cameras(max_index: int = 6, backend: str = "auto") -> list[tuple[int, int, int]]:
    """Prueba índices 0..max_index-1 y devuelve los que entregan imagen."""
    api = _capture_api(backend)
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, api)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok:
                found.append((i, frame.shape[1], frame.shape[0]))
        cap.release()
    return found
