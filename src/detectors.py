"""Detección con MediaPipe Tasks API (mano, cara, pose) en un hilo aparte.

El hilo toma siempre el último frame de la webcam, lo achica a la resolución de
detección y publica un `Detection`. Así el FPS de salida no depende del costo de
los modelos: si la detección va más lenta, simplemente se saltea frames.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from gesture import Forehead, forehead_from_face, forehead_from_pose

log = logging.getLogger(__name__)


@dataclass
class Hand:
    px: np.ndarray              # (21, 2) en píxeles del frame original
    world: np.ndarray | None    # (21, 3) en metros
    handedness: str             # "Left" | "Right" según MediaPipe (imagen sin espejar)


@dataclass
class Detection:
    seq: int                    # número de frame de la webcam
    hands: list[Hand] = field(default_factory=list)
    forehead: Forehead | None = None
    face_px: np.ndarray | None = None
    pose_px: np.ndarray | None = None
    fps: float = 0.0


def _to_px(landmarks, w: int, h: int) -> np.ndarray:
    return np.array([(lm.x * w, lm.y * h) for lm in landmarks], dtype=np.float32)


class Landmarkers:
    """Agrupa los tres landmarkers en modo VIDEO."""

    def __init__(self, models_dir: Path, cfg: dict):
        mode = vision.RunningMode.VIDEO
        conf = float(cfg.get("min_confidence", 0.5))

        def opts(name: str) -> BaseOptions:
            path = models_dir / name
            if not path.exists():
                raise RuntimeError(f"Falta {path}. Corré: python download_models.py")
            return BaseOptions(model_asset_path=str(path))

        self.hand = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=opts("hand_landmarker.task"), running_mode=mode,
            num_hands=int(cfg.get("num_hands", 2)),
            min_hand_detection_confidence=conf, min_hand_presence_confidence=conf,
            min_tracking_confidence=conf,
        ))
        self.face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=opts("face_landmarker.task"), running_mode=mode, num_faces=1,
            min_face_detection_confidence=conf, min_face_presence_confidence=conf,
            min_tracking_confidence=conf,
        ))
        self.pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=opts("pose_landmarker_lite.task"), running_mode=mode, num_poses=1,
            min_pose_detection_confidence=conf, min_pose_presence_confidence=conf,
            min_tracking_confidence=conf,
        ))
        self.face_only_with_hand = bool(cfg.get("face_only_with_hand", True))
        self._last_ts = -1

    def _ts(self) -> int:
        # VIDEO exige timestamps estrictamente crecientes (ms).
        ts = int(time.perf_counter() * 1000)
        self._last_ts = max(ts, self._last_ts + 1)
        return self._last_ts

    def process(self, frame_bgr: np.ndarray, det_width: int, pose_k: float) -> Detection:
        h, w = frame_bgr.shape[:2]
        if det_width and w > det_width:
            small = cv2.resize(frame_bgr, (det_width, round(h * det_width / w)), interpolation=cv2.INTER_AREA)
        else:
            small = frame_bgr
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts = self._ts()

        det = Detection(seq=0)
        # Las coordenadas normalizadas valen igual para el frame original.
        hr = self.hand.detect_for_video(image, ts)
        for i, lms in enumerate(hr.hand_landmarks):
            world = None
            if i < len(hr.hand_world_landmarks):
                world = np.array([(p.x, p.y, p.z) for p in hr.hand_world_landmarks[i]], dtype=np.float32)
            side = hr.handedness[i][0].category_name if i < len(hr.handedness) and hr.handedness[i] else "?"
            det.hands.append(Hand(_to_px(lms, w, h), world, side))

        if not det.hands and self.face_only_with_hand:
            # Sin mano no puede haber gesto: no hace falta buscar la frente.
            # Ahorra más de la mitad del CPU de detección casi todo el tiempo.
            return det
        fr = self.face.detect_for_video(image, ts)
        if fr.face_landmarks:
            det.face_px = _to_px(fr.face_landmarks[0], w, h)
            det.forehead = forehead_from_face(det.face_px)
        else:
            # Respaldo: la mano tapa la cara y el Face Landmarker la pierde.
            pr = self.pose.detect_for_video(image, ts)
            if pr.pose_landmarks:
                det.pose_px = _to_px(pr.pose_landmarks[0], w, h)
                det.forehead = forehead_from_pose(det.pose_px, pose_k)
        return det

    def close(self) -> None:
        for lm in (self.hand, self.face, self.pose):
            lm.close()


class DetectorThread:
    def __init__(self, webcam, models_dir: Path, det_cfg: dict, pose_k: float):
        self.webcam = webcam
        self.det_width = int(det_cfg.get("width", 640))
        self.min_period = 1.0 / float(det_cfg.get("max_fps", 30))
        self.pose_k = pose_k
        self.landmarkers = Landmarkers(models_dir, det_cfg)
        self._latest: Detection | None = None
        self._lock = threading.Lock()
        self._running = True
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._loop, name="detector", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        last_seq = -1
        fps = 0.0
        t_prev = time.perf_counter()
        try:
            while self._running:
                frame, seq = self.webcam.read()
                if seq == last_seq:
                    time.sleep(0.002)
                    continue
                t0 = time.perf_counter()
                det = self.landmarkers.process(frame, self.det_width, self.pose_k)
                det.seq = seq
                last_seq = seq
                now = time.perf_counter()
                fps = 0.9 * fps + 0.1 * (1.0 / max(now - t_prev, 1e-6)) if fps else 1.0 / max(now - t_prev, 1e-6)
                t_prev = now
                det.fps = fps
                with self._lock:
                    self._latest = det
                spare = self.min_period - (time.perf_counter() - t0)
                if spare > 0:
                    time.sleep(spare)
        except BaseException as e:  # se reporta en el hilo principal
            self._error = e
            log.exception("El hilo de detección falló")

    def latest(self) -> Detection | None:
        if self._error is not None:
            raise RuntimeError(f"Detección caída: {self._error}")
        with self._lock:
            return self._latest

    def release(self) -> None:
        self._running = False
        self._thread.join(timeout=2.0)
        self.landmarkers.close()
        log.info("Detectores cerrados")
