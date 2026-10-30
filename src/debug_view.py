"""Dibujo de la ventana de debug (landmarks, frente, reglas, contadores)."""
from __future__ import annotations

import cv2
import numpy as np

from detectors import Detection
from gesture import (FACE_EYE_OUTER_L, FACE_EYE_OUTER_R, POSE_EYE_OUTER_L, POSE_EYE_OUTER_R,
                     POSE_NOSE, GestureEval)

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
]
GREEN, RED, YELLOW, CYAN, WHITE = (0, 220, 0), (0, 0, 230), (0, 220, 255), (255, 220, 0), (255, 255, 255)


def _pt(p) -> tuple[int, int]:
    return int(p[0]), int(p[1])


def draw_landmarks(img: np.ndarray, det: Detection | None, evals: list[GestureEval],
                   forehead_ratio: float) -> None:
    """Dibuja en coordenadas del frame sin espejar."""
    if det is None:
        return
    # Solo los puntos que usa la regla: comisuras de los ojos (escala) y nariz (pose).
    if det.face_px is not None:
        a, b = det.face_px[FACE_EYE_OUTER_L], det.face_px[FACE_EYE_OUTER_R]
        cv2.line(img, _pt(a), _pt(b), YELLOW, 1, cv2.LINE_AA)
    elif det.pose_px is not None:
        a, b = det.pose_px[POSE_EYE_OUTER_L], det.pose_px[POSE_EYE_OUTER_R]
        cv2.line(img, _pt(a), _pt(b), CYAN, 1, cv2.LINE_AA)
        cv2.circle(img, _pt(det.pose_px[POSE_NOSE]), 4, CYAN, -1)
    if det.forehead is not None:
        f = det.forehead
        cv2.circle(img, _pt(f.point), 6, YELLOW, -1)
        cv2.circle(img, _pt(f.point), int(f.scale * forehead_ratio), YELLOW, 1, cv2.LINE_AA)
    for hand, ev in zip(det.hands, evals):
        color = GREEN if ev.ok else (YELLOW if ev.hand_shape else RED)
        for a, b in HAND_CONNECTIONS:
            cv2.line(img, _pt(hand.px[a]), _pt(hand.px[b]), color, 2, cv2.LINE_AA)
        for p in hand.px:
            cv2.circle(img, _pt(p), 3, WHITE, -1)


def draw_hud(img: np.ndarray, lines: list[tuple[str, tuple[int, int, int]]]) -> None:
    x, y = 16, 32
    for text, color in lines:
        cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
        y += 28


def fit_to_window(img: np.ndarray, window: str) -> np.ndarray:
    """Escala la imagen al tamaño actual de la ventana manteniendo la
    proporción (con bandas negras), así redimensionar no la deforma."""
    try:
        _, _, ww, wh = cv2.getWindowImageRect(window)
    except cv2.error:
        return img
    h, w = img.shape[:2]
    if ww <= 0 or wh <= 0 or (ww, wh) == (w, h):
        return img
    s = min(ww / w, wh / h)
    nw, nh = max(int(w * s), 1), max(int(h * s), 1)
    canvas = np.zeros((wh, ww, 3), np.uint8)
    x0, y0 = (ww - nw) // 2, (wh - nh) // 2
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
    canvas[y0:y0 + nh, x0:x0 + nw] = cv2.resize(img, (nw, nh), interpolation=interp)
    return canvas


def draw_mask_inset(img: np.ndarray, mask: np.ndarray | None, width: int = 256) -> None:
    """Miniatura de la máscara de persona en la esquina inferior derecha."""
    if mask is None:
        return
    h, w = img.shape[:2]
    th = round(mask.shape[0] * width / mask.shape[1])
    thumb = cv2.resize(mask, (width, th), interpolation=cv2.INTER_AREA)
    thumb = cv2.cvtColor((thumb * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    x0, y0 = w - width - 12, h - th - 12
    img[y0:y0 + th, x0:x0 + width] = thumb
    cv2.rectangle(img, (x0 - 1, y0 - 1), (x0 + width, y0 + th), WHITE, 1)


def rule_lines(ev: GestureEval | None, forehead_ratio: float) -> list[tuple[str, tuple[int, int, int]]]:
    if ev is None:
        return [("mano: -", RED)]
    def mark(ok: bool, label: str):
        return (f"[{'x' if ok else ' '}] {label}", GREEN if ok else RED)
    dist = "-" if ev.forehead_dist == float("inf") else f"{ev.forehead_dist:.2f}"
    return [
        mark(ev.index_extended, "indice extendido"),
        mark(ev.middle_extended, "mayor extendido"),
        mark(ev.ring_flexed, "anular flexionado"),
        mark(ev.pinky_flexed, "menique flexionado"),
        mark(ev.together, "indice y mayor juntos"),
        mark(ev.near_forehead, f"en la frente (d={dist} < {forehead_ratio:.2f})"),
    ]
