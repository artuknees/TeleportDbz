import numpy as np
import pytest

from gesture import (
    FINGERS, POSE_EYE_OUTER_L, POSE_EYE_OUTER_R, POSE_NOSE, Forehead, GestureParams,
    GestureTrigger, evaluate, forehead_from_pose,
)

P = GestureParams()

# Mano sintética en "metros", muñeca en el origen, dedos hacia arriba (-y).
MCP = {"index": (-0.03, -0.09), "middle": (-0.01, -0.092), "ring": (0.01, -0.09), "pinky": (0.03, -0.08)}


def make_hand(extended=("index", "middle"), spread=0.0):
    pts = np.zeros((21, 3), dtype=np.float32)
    for name, (mcp_i, pip_i, tip_i) in FINGERS.items():
        mx, my = MCP[name]
        mcp = np.array([mx, my, 0.0])
        if name in extended:
            # `spread` abre el índice hacia la izquierda y el mayor hacia la derecha
            dx = {"index": -spread, "middle": spread}.get(name, 0.0)
            pip = mcp + (dx * 0.4, -0.04, 0)
            dip = pip + (dx * 0.3, -0.025, 0)
            tip = dip + (dx * 0.3, -0.02, 0)
        else:
            pip = mcp + (0, -0.03, -0.02)
            dip = pip + (0, 0.015, -0.01)
            tip = mcp + (0, 0.0, -0.03)
        pts[mcp_i], pts[pip_i], pts[pip_i + 1], pts[tip_i] = mcp, pip, dip, tip
    pts[1:5] = [(-0.03, -0.02, 0), (-0.045, -0.04, 0), (-0.05, -0.06, 0), (-0.05, -0.075, 0)]  # pulgar
    return pts


def to_px(world, origin=(640.0, 500.0), scale=1500.0):
    return world[:, :2] * scale + np.array(origin)


def forehead_at_tips(world, offset=(0.0, 0.0), scale=90.0):
    px = to_px(world)
    tip = (px[8] + px[12]) / 2
    return Forehead(tip + np.array(offset), scale, "face")


def test_goku_gesture_detected():
    w = make_hand()
    ev = evaluate(to_px(w), forehead_at_tips(w), P, hand_world=w)
    assert ev.index_extended and ev.middle_extended
    assert ev.ring_flexed and ev.pinky_flexed
    assert ev.together and ev.near_forehead
    assert ev.ok


def test_works_with_pixels_only():
    w = make_hand()
    assert evaluate(to_px(w), forehead_at_tips(w), P).hand_shape


def test_rotation_invariant():
    w = make_hand()
    a = np.deg2rad(35)
    rot = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    wr = (w @ rot.T).astype(np.float32)
    assert evaluate(to_px(wr), forehead_at_tips(wr), P, hand_world=wr).ok


def test_open_hand_rejected():
    w = make_hand(extended=("index", "middle", "ring", "pinky"))
    ev = evaluate(to_px(w), forehead_at_tips(w), P, hand_world=w)
    assert not ev.ring_flexed and not ev.pinky_flexed
    assert not ev.ok


def test_fist_rejected():
    w = make_hand(extended=())
    ev = evaluate(to_px(w), forehead_at_tips(w), P, hand_world=w)
    assert not ev.index_extended and not ev.middle_extended
    assert not ev.ok


def test_single_finger_rejected():
    w = make_hand(extended=("index",))
    assert not evaluate(to_px(w), forehead_at_tips(w), P, hand_world=w).ok


def test_peace_sign_rejected():
    w = make_hand(spread=0.06)
    ev = evaluate(to_px(w), forehead_at_tips(w), P, hand_world=w)
    assert ev.index_extended and ev.middle_extended
    assert not ev.together
    assert not ev.ok


def test_far_from_forehead_rejected():
    w = make_hand()
    ev = evaluate(to_px(w), forehead_at_tips(w, offset=(0, 400)), P, hand_world=w)
    assert ev.hand_shape and not ev.near_forehead
    assert ev.forehead_dist == pytest.approx(400 / 90, rel=0.01)


def test_threshold_scales_with_face_size():
    w = make_hand()
    # A 100 px de la frente: lejos para una cara chica, cerca para una grande.
    assert not evaluate(to_px(w), forehead_at_tips(w, (0, 100), scale=50), P, w).near_forehead
    assert evaluate(to_px(w), forehead_at_tips(w, (0, 100), scale=250), P, w).near_forehead


def test_no_forehead_means_not_near():
    w = make_hand()
    ev = evaluate(to_px(w), None, P, hand_world=w)
    assert ev.hand_shape and not ev.near_forehead and not ev.ok


def test_forehead_from_pose_follows_head():
    pose = np.zeros((33, 2), dtype=np.float32)
    pose[POSE_EYE_OUTER_L] = (600, 300)
    pose[POSE_EYE_OUTER_R] = (700, 300)
    pose[POSE_NOSE] = (650, 350)
    f = forehead_from_pose(pose, k=1.0)
    assert f.source == "pose"
    assert f.scale == pytest.approx(100)
    np.testing.assert_allclose(f.point, (650, 250))


def test_params_from_config_ignores_unknown_keys():
    p = GestureParams.from_config({"together_ratio": 0.3, "hold_frames": 8})
    assert p.together_ratio == 0.3


# --- debounce / cooldown ---

def test_trigger_needs_n_consecutive_frames():
    t = GestureTrigger(hold_frames=8, cooldown_s=2.0)
    fired = [t.update(True, now=i * 0.03) for i in range(8)]
    assert fired == [False] * 7 + [True]


def test_trigger_miss_resets_count():
    t = GestureTrigger(hold_frames=3, cooldown_s=0)
    assert not t.update(True, 0.0)
    assert not t.update(True, 0.1)
    assert not t.update(False, 0.2)
    assert not t.update(True, 0.3)
    assert not t.update(True, 0.4)
    assert t.update(True, 0.5)


def test_trigger_cooldown_and_release():
    t = GestureTrigger(hold_frames=2, cooldown_s=2.0)
    t.update(True, 0.0)
    assert t.update(True, 0.1)
    # Sostener el gesto no vuelve a disparar, ni siquiera pasado el cooldown.
    assert not any(t.update(True, 0.2 + i * 0.1) for i in range(40))
    # Soltar dentro del cooldown y repetir: todavía no.
    t.update(False, 1.0)
    assert not t.update(True, 1.1) and not t.update(True, 1.2)
    # Soltar y repetir después del cooldown: dispara.
    t.update(False, 2.2)
    assert not t.update(True, 2.3)
    assert t.update(True, 2.4)
