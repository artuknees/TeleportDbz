"""Reglas del gesto de teletransportación + debounce/cooldown.

Todo acá es lógica pura sobre arrays de NumPy (sin MediaPipe), para poder
testearlo con landmarks sintéticos.

Índices de landmarks de la mano (MediaPipe):
    0 muñeca
    índice  5 MCP, 6 PIP, 7 DIP, 8 punta
    mayor   9 MCP, 10 PIP, 11 DIP, 12 punta
    anular 13 MCP, 14 PIP, 15 DIP, 16 punta
    meñique 17 MCP, 18 PIP, 19 DIP, 20 punta
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

WRIST = 0
FINGERS = {  # nombre: (MCP, PIP, punta)
    "index": (5, 6, 8),
    "middle": (9, 10, 12),
    "ring": (13, 14, 16),
    "pinky": (17, 18, 20),
}

# Landmarks de cara (Face Landmarker, malla de 478 puntos)
FACE_FOREHEAD = 151
FACE_EYE_OUTER_L = 33
FACE_EYE_OUTER_R = 263

# Landmarks de pose (Pose Landmarker, 33 puntos)
POSE_NOSE = 0
POSE_EYE_OUTER_L = 3
POSE_EYE_OUTER_R = 6


@dataclass
class GestureParams:
    ext_pip_ratio: float = 1.15     # extendido: d(punta,muñeca) > r * d(PIP,muñeca)
    ext_mcp_ratio: float = 1.6      # extendido: d(punta,muñeca) > r * d(MCP,muñeca)
    flex_mcp_ratio: float = 1.35    # flexionado: d(punta,muñeca) < r * d(MCP,muñeca)
    flex_pip_ratio: float = 1.0     #   … o d(punta,muñeca) < r * d(PIP,muñeca)
    together_ratio: float = 0.4     # juntos: d(punta índice, punta mayor) < r * tamaño de palma
    forehead_ratio: float = 0.55    # cerca: d(punta, frente) < r * distancia entre ojos
    pose_forehead_k: float = 1.0    # frente desde pose = ojos + k * (ojos - nariz)

    @classmethod
    def from_config(cls, cfg: dict) -> "GestureParams":
        names = cls.__dataclass_fields__.keys()
        return cls(**{k: float(v) for k, v in cfg.items() if k in names})


@dataclass
class Forehead:
    point: np.ndarray       # (x, y) en píxeles
    scale: float            # distancia entre comisuras externas de los ojos, en píxeles
    source: str             # "face" | "pose"


@dataclass
class GestureEval:
    index_extended: bool = False
    middle_extended: bool = False
    ring_flexed: bool = False
    pinky_flexed: bool = False
    together: bool = False
    near_forehead: bool = False
    forehead_dist: float = float("inf")   # en múltiplos de forehead.scale

    @property
    def hand_shape(self) -> bool:
        return (self.index_extended and self.middle_extended and self.ring_flexed
                and self.pinky_flexed and self.together)

    @property
    def ok(self) -> bool:
        return self.hand_shape and self.near_forehead


def _d(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def finger_ratios(pts: np.ndarray, finger: str) -> tuple[float, float]:
    """Devuelve (d(punta,muñeca)/d(PIP,muñeca), d(punta,muñeca)/d(MCP,muñeca))."""
    mcp, pip, tip = FINGERS[finger]
    w = pts[WRIST]
    d_tip = _d(pts[tip], w)
    return d_tip / max(_d(pts[pip], w), 1e-6), d_tip / max(_d(pts[mcp], w), 1e-6)


def is_extended(pts: np.ndarray, finger: str, p: GestureParams) -> bool:
    r_pip, r_mcp = finger_ratios(pts, finger)
    return r_pip > p.ext_pip_ratio and r_mcp > p.ext_mcp_ratio


def is_flexed(pts: np.ndarray, finger: str, p: GestureParams) -> bool:
    r_pip, r_mcp = finger_ratios(pts, finger)
    return r_mcp < p.flex_mcp_ratio or r_pip < p.flex_pip_ratio


def evaluate(
    hand_px: np.ndarray,
    forehead: Forehead | None,
    p: GestureParams,
    hand_world: np.ndarray | None = None,
) -> GestureEval:
    """Evalúa el gesto para una mano.

    hand_px:    (21, 2) landmarks en píxeles de la imagen (para la posición).
    hand_world: (21, 3) landmarks en metros (opcional). Si están, se usan para la
                forma de la mano porque no sufren escorzo ni dependen de la rotación.
    """
    shape = hand_world if hand_world is not None else hand_px
    palm = max(_d(shape[WRIST], shape[FINGERS["middle"][0]]), 1e-6)
    ev = GestureEval(
        index_extended=is_extended(shape, "index", p),
        middle_extended=is_extended(shape, "middle", p),
        ring_flexed=is_flexed(shape, "ring", p),
        pinky_flexed=is_flexed(shape, "pinky", p),
        together=_d(shape[FINGERS["index"][2]], shape[FINGERS["middle"][2]]) < p.together_ratio * palm,
    )
    if forehead is not None and forehead.scale > 0:
        tips = hand_px[[FINGERS["index"][2], FINGERS["middle"][2]], :2]
        dist = min(_d(t, forehead.point) for t in tips) / forehead.scale
        ev.forehead_dist = dist
        ev.near_forehead = dist < p.forehead_ratio
    return ev


def forehead_from_face(face_px: np.ndarray) -> Forehead:
    """face_px: (478, 2) landmarks de cara en píxeles."""
    scale = _d(face_px[FACE_EYE_OUTER_L], face_px[FACE_EYE_OUTER_R])
    return Forehead(face_px[FACE_FOREHEAD].astype(float), scale, "face")


def forehead_from_pose(pose_px: np.ndarray, k: float) -> Forehead:
    """pose_px: (33, 2) landmarks de pose en píxeles. La frente se extrapola
    desde la nariz a través del punto medio de los ojos, así sigue la
    inclinación de la cabeza."""
    eye_l, eye_r = pose_px[POSE_EYE_OUTER_L], pose_px[POSE_EYE_OUTER_R]
    eyes = (eye_l + eye_r) / 2.0
    point = eyes + k * (eyes - pose_px[POSE_NOSE])
    return Forehead(point.astype(float), _d(eye_l, eye_r), "pose")


@dataclass
class GestureTrigger:
    """Debounce: el gesto tiene que verse `hold_frames` frames de detección
    seguidos. Después de disparar hay un cooldown, y además hay que soltar el
    gesto antes de que pueda volver a disparar."""

    hold_frames: int = 8
    cooldown_s: float = 2.0
    count: int = 0
    _cooldown_until: float = field(default=float("-inf"), repr=False)
    _needs_release: bool = field(default=False, repr=False)

    def update(self, detected: bool, now: float) -> bool:
        if not detected:
            self.count = 0
            self._needs_release = False
            return False
        if self._needs_release or now < self._cooldown_until:
            self.count = 0
            return False
        self.count += 1
        if self.count >= self.hold_frames:
            self.count = 0
            self._cooldown_until = now + self.cooldown_s
            self._needs_release = True
            return True
        return False

    def reset(self) -> None:
        self.count = 0

    def in_cooldown(self, now: float) -> bool:
        return now < self._cooldown_until

    @property
    def needs_release(self) -> bool:
        return self._needs_release
