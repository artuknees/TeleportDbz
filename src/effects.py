"""Animación de desaparición estilo anime (la reaparición es la misma en reversa).

`TeleportEffect.render(frame, fondo, máscara, t)` con t = 0 (persona normal) →
t = 1 (persona desaparecida). Capas, de abajo hacia arriba:
  1. base: el frame con la persona reemplazada por el fondo
  2. la persona estirada a lo largo del eje del efecto (y comprimida en el
     otro), con motion blur y bandas de distorsión, parpadeando (on/off cada
     vez más rápido) y desvaneciéndose hasta alpha 0
  3. líneas de velocidad
  4. un destello breve alrededor de la silueta
El eje es vertical (como en el anime) u horizontal, según `direction`. Solo se
procesa el rectángulo que ocupa la persona, para que sea barato. Internamente
todo se calcula como si el eje fuera horizontal; para el vertical se transpone
el recorte.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from segmentation import composite


@dataclass
class EffectParams:
    direction: str = "vertical"       # eje del estiramiento, blur y líneas: vertical | horizontal
    flicker_cycles: float = 5.0       # cantidad de parpadeos durante la animación
    flicker_accel: float = 2.0        # >1 = los parpadeos se aceleran hacia el final
    flicker_duty: float = 0.6         # fracción de cada ciclo con la silueta "on"
    flicker_off_alpha: float = 0.15   # opacidad de la silueta en la fase "off"
    stretch_max: float = 0.35         # estiramiento a lo largo del eje al final (+35%)
    squeeze_max: float = 0.6          # compresión en el otro eje al final (-60%: queda un haz)
    shift_px: float = 25.0            # sacudón aleatorio máximo a lo largo del eje
    motion_blur_px: float = 70.0      # largo máximo del motion blur
    glitch_bands: int = 7             # bandas desplazadas por frame
    glitch_shift_px: float = 45.0     # desplazamiento máximo de cada banda
    speed_lines: int = 14             # líneas de velocidad por frame
    speed_line_alpha: float = 0.7
    flash_at: float = 0.7             # momento del destello (0..1)
    flash_width: float = 0.1          # duración del destello (en fracción de la animación)
    flash_intensity: float = 0.75
    flash_color: tuple = (255, 245, 225)  # BGR: blanco levemente azulado

    @classmethod
    def from_config(cls, cfg: dict) -> "EffectParams":
        out = cls()
        for k, v in cfg.items():
            if k in cls.__dataclass_fields__:
                default = getattr(out, k)
                setattr(out, k, tuple(v) if isinstance(default, tuple) else type(default)(v))
        return out


def _shift(a: np.ndarray, s: int, axis: int) -> np.ndarray:
    """Desplaza `s` píxeles a lo largo de `axis` rellenando con ceros (sin dar
    la vuelta como np.roll, que traería pedazos del otro extremo)."""
    if s == 0:
        return a
    out = np.zeros_like(a)
    src = [slice(None)] * a.ndim
    dst = [slice(None)] * a.ndim
    if s > 0:
        src[axis], dst[axis] = slice(0, -s), slice(s, None)
    else:
        src[axis], dst[axis] = slice(-s, None), slice(0, s)
    out[tuple(dst)] = a[tuple(src)]
    return out


def flicker_alpha(t: float, p: EffectParams) -> float:
    """Opacidad de la silueta: parpadeo acelerado × desvanecimiento, 0 en t=1."""
    if t >= 1.0:
        return 0.0
    n = p.flicker_cycles * t ** p.flicker_accel
    on = (n % 1.0) < p.flicker_duty
    return (1.0 - t) * (1.0 if on else p.flicker_off_alpha)


class TeleportEffect:
    def __init__(self, params: EffectParams, seed: int | None = None):
        self.p = params
        self.rng = np.random.default_rng(seed)

    def render(self, frame: np.ndarray, background: np.ndarray, mask: np.ndarray, t: float) -> np.ndarray:
        p, rng = self.p, self.rng
        t = min(max(t, 0.0), 1.0)
        base = composite(frame, background, mask)
        if t >= 1.0:
            return base

        h, w = mask.shape
        step = 8
        coarse = mask[::step, ::step] > 0.1
        if not coarse.any():
            return base
        ys, xs = np.nonzero(coarse)
        by0, by1 = int(ys.min()) * step, min((int(ys.max()) + 1) * step, h)
        bx0, bx1 = int(xs.min()) * step, min((int(xs.max()) + 1) * step, w)

        # Coordenadas "a lo largo" (a) y "a través" (c) del eje del efecto.
        vertical = p.direction == "vertical"
        a0, a1, c0, c1 = (by0, by1, bx0, bx1) if vertical else (bx0, bx1, by0, by1)
        a_len, c_len = (h, w) if vertical else (w, h)
        s_al = 1.0 + p.stretch_max * t * t
        s_ac = max(1.0 - p.squeeze_max * t * t, 0.05)
        dx = float(rng.uniform(-1, 1)) * p.shift_px * t
        half_a = (a1 - a0) / 2.0 * s_al
        glow_sigma = 0.06 * max(a1 - a0, c1 - c0)
        glow_margin = 2.5 * glow_sigma
        margin = max(p.motion_blur_px * t + p.glitch_shift_px + abs(dx), glow_margin) + 4
        ca, cc = (a0 + a1) / 2.0, (c0 + c1) / 2.0
        ra0, ra1 = int(max(0, ca - half_a - margin)), int(min(a_len, ca + half_a + margin))
        rc0, rc1 = int(max(0, c0 - glow_margin)), int(min(c_len, c1 + glow_margin))
        if ra1 - ra0 < 8 or rc1 - rc0 < 8:
            return base
        roi = (slice(ra0, ra1), slice(rc0, rc1)) if vertical else (slice(rc0, rc1), slice(ra0, ra1))

        out = self._render_crop(frame[roi], base[roi], mask[roi], vertical, t=t, lca=ca - ra0,
                                lcc=cc - rc0, half_a=half_a, half_c=(c1 - c0) / 2.0 * s_ac,
                                s_al=s_al, s_ac=s_ac, dx=dx, glow_sigma=glow_sigma)
        base[roi] = out
        return base

    def _render_crop(self, frame, base, m_src, vertical: bool, *, t, lca, lcc, half_a, half_c,
                     s_al, s_ac, dx, glow_sigma) -> np.ndarray:
        """Efecto sobre el recorte. `lca`/`lcc` son el centro de la persona a lo
        largo / a través del eje, en coordenadas del recorte."""
        p, rng = self.p, self.rng
        rh, rw = m_src.shape
        along = 0 if vertical else 1                  # eje NumPy "a lo largo"
        a_len, c_len = (rh, rw) if vertical else (rw, rh)

        def pt(a: int, c: int) -> tuple[int, int]:    # (a lo largo, a través) → (x, y) de OpenCV
            return (c, a) if vertical else (a, c)

        # 2. persona estirada/comprimida + motion blur + bandas de distorsión.
        # Se deforman por separado el color (frame) y la máscara; todo en
        # operaciones de OpenCV, que son mucho más rápidas que NumPy acá.
        row_a = [s_al, (1.0 - s_al) * lca + dx]
        row_c = [s_ac, (1.0 - s_ac) * lcc]
        if vertical:
            M = np.float32([[row_c[0], 0, row_c[1]], [0, row_a[0], row_a[1]]])
        else:
            M = np.float32([[row_a[0], 0, row_a[1]], [0, row_c[0], row_c[1]]])
        person = cv2.warpAffine(frame, M, (rw, rh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        m = cv2.warpAffine(m_src, M, (rw, rh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        k = int(p.motion_blur_px * t)
        if k >= 3:
            ksize = (1, k) if vertical else (k, 1)
            person = cv2.blur(person, ksize)
            m = cv2.blur(m, ksize)
        g = int(p.glitch_shift_px)
        for _ in range(int(p.glitch_bands)):
            bw = int(rng.integers(3, max(4, c_len // 14)))
            b0 = int(rng.integers(0, max(1, c_len - bw)))
            shift = int(rng.integers(-g, g + 1) * min(1.0, 4.0 * t))  # sin saltos cerca de t=0
            band = (slice(None), slice(b0, b0 + bw)) if vertical else (slice(b0, b0 + bw), slice(None))
            person[band] = _shift(person[band], shift, along)
            m[band] = _shift(m[band], shift, along)

        weight = m * flicker_alpha(t, p)
        out = cv2.blendLinear(base, person, 1.0 - weight, weight)

        # 3 y 4. líneas de velocidad + destello: se suman en un solo peso hacia el color del destello
        light = np.zeros((rh, rw), np.float32)
        line_a = p.speed_line_alpha * 4.0 * t * (1.0 - t)  # más intensas a mitad de la animación
        if p.speed_lines > 0 and line_a > 0.02:
            la0, la1 = int(max(0, lca - half_a)), int(min(a_len - 1, lca + half_a))
            span = max(la1 - la0, 2)
            lc0, lc1 = int(max(0, lcc - half_c)), int(min(c_len, lcc + half_c))
            lc1 = max(lc1, lc0 + 1)
            for _ in range(int(p.speed_lines)):
                c = int(rng.integers(lc0, lc1))
                aa = la0 + int(rng.integers(0, span // 2 + 1))
                ab = min(aa + int(rng.integers(span // 4, span + 1)), a_len - 1)
                cv2.line(light, pt(aa, c), pt(ab, c), line_a, int(rng.integers(1, 3)))
        bump = p.flash_intensity * math.exp(-((t - p.flash_at) / max(p.flash_width, 1e-3)) ** 2)
        if bump > 0.01:
            small = cv2.resize(m, (max(rw // 4, 1), max(rh // 4, 1)), interpolation=cv2.INTER_AREA)
            glow = cv2.GaussianBlur(small, (0, 0), sigmaX=max(glow_sigma / 4.0, 0.5))
            glow = cv2.resize(glow, (rw, rh), interpolation=cv2.INTER_LINEAR)
            cv2.scaleAdd(glow, 1.5 * bump, light, dst=light)
        if light.any():
            np.clip(light, 0.0, 1.0, out=light)
            color = np.empty_like(out)
            color[:] = p.flash_color
            out = cv2.blendLinear(out, color, 1.0 - light, light)
        return out
