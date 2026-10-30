import numpy as np

from background import Background, ExposureMatch
from segmentation import composite
from state import State, TeleportState


def test_full_cycle_with_animations():
    s = TeleportState(disappear_s=0.4, appear_s=0.4)
    assert s.state is State.VISIBLE and s.visibility(0) == 1.0
    assert s.toggle(1.0)
    assert s.state is State.DISAPPEARING
    s.update(1.2)
    assert s.state is State.DISAPPEARING and abs(s.visibility(1.2) - 0.5) < 1e-6
    s.update(1.4)
    assert s.state is State.INVISIBLE and s.visibility(1.4) == 0.0
    assert s.toggle(2.0)
    assert s.state is State.APPEARING
    s.update(2.5)
    assert s.state is State.VISIBLE


def test_toggle_ignored_during_animation():
    s = TeleportState(0.4, 0.4)
    s.toggle(0.0)
    assert not s.toggle(0.1)
    assert s.state is State.DISAPPEARING


def test_instant_toggle_with_zero_duration():
    s = TeleportState(0.0, 0.0)
    s.toggle(0.0)
    assert s.state is State.INVISIBLE
    s.toggle(0.1)
    assert s.state is State.VISIBLE


def test_background_countdown_and_average():
    bg = Background(countdown_s=1.0, frames=3)
    bg.start(0.0)
    frame = np.full((4, 4, 3), 10, np.uint8)
    bg.feed(frame, 1, 0.5)
    assert not bg.ready and bg.busy
    for seq, value in zip((2, 3, 4), (10, 20, 30)):
        bg.feed(np.full((4, 4, 3), value, np.uint8), seq, 1.0 + seq * 0.03)
    assert bg.ready and not bg.busy
    assert int(bg.image[0, 0, 0]) == 20


def test_background_ignores_repeated_frames():
    bg = Background(countdown_s=0.0, frames=2)
    bg.start(0.0)
    f = np.zeros((2, 2, 3), np.uint8)
    bg.feed(f, 7, 0.0)
    bg.feed(f, 7, 0.1)
    assert not bg.ready
    bg.feed(f, 8, 0.2)
    assert bg.ready


def test_exposure_match_corrects_darker_live_video():
    rng = np.random.default_rng(0)
    background = rng.integers(60, 200, (360, 640, 3)).astype(np.uint8)
    frame = (background * np.array([0.8, 0.7, 0.9])).astype(np.uint8)   # la cámara bajó la exposición
    mask = np.zeros((360, 640), np.float32)
    mask[80:360, 220:420] = 1.0
    frame[mask > 0] = (20, 200, 20)                                    # la persona
    em = ExposureMatch(smoothing=1.0)
    em.update(frame, background, mask)
    np.testing.assert_allclose(em.gain_map.reshape(-1, 3).mean(axis=0), (0.8, 0.7, 0.9), atol=0.03)
    fixed = em.apply(background).astype(int)
    expected = (background * np.array([0.8, 0.7, 0.9])).astype(int)
    inside = mask > 0
    assert np.abs(fixed - expected)[inside].mean() < 3


def test_exposure_match_follows_local_shadow():
    # Fondo uniforme; en vivo hay una sombra a la izquierda de la persona.
    background = np.full((360, 640, 3), 200, np.uint8)
    frame = background.copy()
    frame[:, :320] = 140
    mask = np.zeros((360, 640), np.float32)
    mask[100:360, 260:380] = 1.0
    frame[mask > 0] = (30, 30, 30)
    em = ExposureMatch(smoothing=1.0)
    em.update(frame, background, mask)
    fixed = em.apply(background)
    # junto al borde izquierdo de la silueta el fondo corregido se parece a la sombra,
    # junto al derecho a la pared iluminada
    assert abs(int(fixed[250, 265, 0]) - 140) < 20
    assert abs(int(fixed[250, 375, 0]) - 200) < 20


def test_composite_hides_only_masked_pixels():
    frame = np.full((2, 2, 3), 200, np.uint8)
    background = np.full((2, 2, 3), 50, np.uint8)
    hide = np.array([[1.0, 0.0], [0.5, 0.0]], np.float32)
    out = composite(frame, background, hide)
    assert out[0, 0, 0] == 50 and out[0, 1, 0] == 200 and out[1, 0, 0] == 125
