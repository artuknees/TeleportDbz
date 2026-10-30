import cv2
import numpy as np

from effects import EffectParams, TeleportEffect, flicker_alpha
from segmentation import composite

H, W = 180, 320


def scene():
    frame = np.full((H, W, 3), 40, np.uint8)
    background = np.full((H, W, 3), 120, np.uint8)
    mask = np.zeros((H, W), np.float32)
    cv2.ellipse(mask, (W // 2, H // 2 + 20), (40, 70), 0, 0, 360, 1.0, -1)
    frame[mask > 0.5] = (30, 200, 230)
    return frame, background, mask


def test_flicker_ends_at_zero_and_starts_full():
    p = EffectParams()
    assert flicker_alpha(0.0, p) == 1.0
    assert flicker_alpha(1.0, p) == 0.0
    assert all(flicker_alpha(t, p) <= 1.0 - t + 1e-9 for t in np.linspace(0, 1, 50))


def test_flicker_accelerates():
    p = EffectParams(flicker_cycles=6, flicker_accel=2.0)
    ts = np.linspace(0, 0.999, 2000)
    on = np.array([flicker_alpha(t, p) > (1 - t) * 0.5 for t in ts])
    edges = np.flatnonzero(np.diff(on.astype(int)) != 0)
    gaps = np.diff(edges)
    assert len(gaps) >= 4 and gaps[-1] < gaps[0]


def test_render_endpoints():
    frame, bg, mask = scene()
    fx = TeleportEffect(EffectParams(), seed=0)
    start = fx.render(frame, bg, mask, 0.0)
    assert np.abs(start.astype(int) - frame.astype(int)).mean() < 3
    end = fx.render(frame, bg, mask, 1.0)
    np.testing.assert_array_equal(end, composite(frame, bg, mask))


def test_render_midway_shapes_and_changes():
    frame, bg, mask = scene()
    fx = TeleportEffect(EffectParams(), seed=1)
    for t in (0.2, 0.5, 0.7, 0.95):
        out = fx.render(frame, bg, mask, t)
        assert out.shape == frame.shape and out.dtype == np.uint8
    # el estiramiento lleva color de la persona fuera de su contorno original
    out = TeleportEffect(EffectParams(flicker_cycles=0, glitch_bands=0, speed_lines=0, flash_intensity=0),
                         seed=2).render(frame, bg, mask, 0.6)
    outside = (mask == 0)
    assert (np.abs(out.astype(int) - composite(frame, bg, mask).astype(int))[outside].max()) > 20


def test_both_directions_render_and_differ():
    frame, bg, mask = scene()
    outs = {}
    for d in ("vertical", "horizontal"):
        fx = TeleportEffect(EffectParams(direction=d), seed=5)
        outs[d] = fx.render(frame, bg, mask, 0.5)
        assert outs[d].shape == frame.shape
    assert np.abs(outs["vertical"].astype(int) - outs["horizontal"].astype(int)).mean() > 1


def test_vertical_lines_are_vertical():
    frame, bg, mask = scene()
    only_lines = EffectParams(direction="vertical", flicker_cycles=0, flicker_off_alpha=0, glitch_bands=0,
                              flash_intensity=0, motion_blur_px=0, speed_lines=10, speed_line_alpha=1.0)
    fx = TeleportEffect(only_lines, seed=4)
    out = fx.render(frame, bg, mask, 0.5).astype(int)
    ref = TeleportEffect(EffectParams(**{**only_lines.__dict__, "speed_lines": 0}), seed=4).render(
        frame, bg, mask, 0.5).astype(int)
    diff = np.abs(out - ref).sum(axis=2) > 30
    # Las líneas cubren más filas que columnas
    assert diff.any(axis=1).sum() > 3 * diff.any(axis=0).sum()


def test_render_without_person_is_base():
    frame, bg, _ = scene()
    empty = np.zeros((H, W), np.float32)
    out = TeleportEffect(EffectParams(), seed=0).render(frame, bg, empty, 0.5)
    np.testing.assert_array_equal(out, frame)


def test_params_from_config():
    p = EffectParams.from_config({"glitch_bands": "3", "flash_color": [1, 2, 3], "nope": 1})
    assert p.glitch_bands == 3 and p.flash_color == (1, 2, 3)
