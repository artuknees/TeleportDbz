"""Teletransportación para videollamadas — loop principal.

Uso:
    python src/main.py [--debug] [--config config.yaml] [--no-vcam] [--list-cameras]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")  # silencia warnings de backends de video

import cv2

from capture import VirtualCamera, Webcam, list_cameras
from config import load_config
from background import Background, ExposureMatch
from debug_view import (CYAN, GREEN, RED, WHITE, YELLOW, draw_hud, draw_landmarks, draw_mask_inset,
                        fit_to_window, rule_lines)
from detectors import DetectorThread
from gesture import GestureParams, GestureTrigger, evaluate
from hotkeys import GlobalHotkeys
from effects import EffectParams, TeleportEffect
from segmentation import PersonSegmenter, composite
from sound import EffectSound
from state import State, TeleportState

ROOT = Path(__file__).resolve().parent.parent
DEBUG_WINDOW = "Teleport debug"
# Ajuste en vivo de la máscara desde la ventana de debug: tecla → (atributo, paso)
# (números: funcionan igual en cualquier distribución de teclado)
MASK_KEYS = {ord("1"): ("dilate_px", -2), ord("2"): ("dilate_px", 2),
             ord("3"): ("feather_px", -2), ord("4"): ("feather_px", 2)}

MIN_FPS = 25  # por debajo de esto se avisa en el log cómo aliviar el CPU

log = logging.getLogger("teleport")


class FpsCounter:
    def __init__(self, window: float = 1.0):
        self.window = window
        self.count = 0
        self.t0 = time.perf_counter()
        self.fps = 0.0

    def tick(self) -> float:
        self.count += 1
        dt = time.perf_counter() - self.t0
        if dt >= self.window:
            self.fps = self.count / dt
            self.count = 0
            self.t0 = time.perf_counter()
        return self.fps


def silence_native_stderr() -> None:
    """MediaPipe/TFLite (C++) escriben avisos inofensivos directo al stderr del
    proceso (`W0000 …`, `INFO: Created TensorFlow Lite …`) y no respetan
    variables de entorno. Se manda el descriptor 2 a NUL y Python sigue
    escribiendo sus logs (y tracebacks) en una copia del stderr original."""
    try:
        original = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)
        os.close(devnull)
        sys.stderr = os.fdopen(original, "w", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        pass  # sin consola real (p. ej. pythonw): no hay nada que silenciar


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Teletransportación para videollamadas")
    p.add_argument("--config", default=str(ROOT / "config.yaml"), help="ruta a config.yaml")
    p.add_argument("--debug", action="store_true", help="muestra la ventana de debug")
    p.add_argument("--no-vcam", action="store_true", help="no publica la cámara virtual")
    p.add_argument("--list-cameras", action="store_true", help="lista las webcams y sale")
    return p.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if not cfg["logging"].get("native_logs", False):
        silence_native_stderr()
    logging.basicConfig(
        level=getattr(logging, str(cfg["logging"]["level"]).upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cam_cfg, out_cfg = cfg["camera"], cfg["output"]

    if args.list_cameras:
        cams = list_cameras(backend=cam_cfg["backend"])
        if not cams:
            print("No se encontraron cámaras.")
        for idx, w, h in cams:
            print(f"  índice {idx}: {w}x{h}")
        return 0

    gesture_cfg = cfg["gesture"]
    params = GestureParams.from_config(gesture_cfg)
    trigger = GestureTrigger(int(gesture_cfg["hold_frames"]), float(gesture_cfg["cooldown_s"]))
    fx_cfg, bg_cfg = cfg["effects"], cfg["background"]
    state = TeleportState(float(fx_cfg["disappear_s"]), float(fx_cfg["appear_s"]))
    effect = TeleportEffect(EffectParams.from_config(fx_cfg))

    exposure = ExposureMatch() if bg_cfg["match_exposure"] else None

    def on_background_event(event: str) -> None:
        if event == "done" and exposure is not None:
            exposure.reset()
        if bg_cfg["beep"] and sound is not None:
            sound.beep(*((660, 120) if event == "tick" else (1320, 300)))

    background = Background(float(bg_cfg["countdown_s"]), int(bg_cfg["frames"]), on_background_event)
    sound = None

    def request_toggle(now: float, reason: str) -> None:
        if state.state is State.VISIBLE and (not background.ready or background.busy):
            log.warning("Toggle ignorado (%s): el fondo todavía no está capturado", reason)
            return
        if state.toggle(now, reason) and sound is not None:
            sound.play("disappear" if state.state in (State.DISAPPEARING, State.INVISIBLE) else "appear")

    webcam = vcam = detector = segmenter = hotkeys = None
    try:
        sound = EffectSound(cfg["sound"], ROOT)
        webcam = Webcam(cam_cfg["index"], cam_cfg["width"], cam_cfg["height"],
                        cam_cfg["fps"], cam_cfg["backend"])
        detector = DetectorThread(webcam, ROOT / "models", cfg["detection"], params.pose_forehead_k)
        segmenter = PersonSegmenter(ROOT / "models", cfg["segmentation"])
        fps_target = int(cam_cfg["fps"])
        if out_cfg["virtual_camera"] and not args.no_vcam:
            vcam = VirtualCamera(webcam.width, webcam.height, fps_target, out_cfg["vcam_backend"])
        else:
            log.info("Cámara virtual desactivada")
        try:
            hotkeys = GlobalHotkeys(cfg["hotkeys"])
        except Exception as e:  # sin hotkeys la app sigue andando con el gesto
            log.warning("No se pudieron registrar las hotkeys globales: %s", e)

        if args.debug:
            cv2.namedWindow(DEBUG_WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(DEBUG_WINDOW, 960, 540)
        log.info("Corriendo. Ctrl+C para salir%s.",
                 " (en la ventana de debug: Q/Esc salir, B fondo, T toggle, 1/2 dilate, 3/4 feather)"
                 if args.debug else "")
        background.start(time.perf_counter())

        fps = FpsCounter()
        frame_period = 1.0 / fps_target
        last_log = time.perf_counter()
        frames_since_log, last_slow_warning = 0, float("-inf")
        det, evals, best = None, [], None
        last_det_seq = last_seg_seq = -1
        fired_at = float("-inf")
        mask = None
        while True:
            t_start = time.perf_counter()
            frame, seq = webcam.read()

            for event in hotkeys.poll() if hotkeys else []:
                if event == "toggle":
                    request_toggle(t_start, "hotkey")
                elif event == "recapture_background":
                    background.start(t_start)

            background.feed(frame, seq, t_start)

            # --- gesto: se evalúa una vez por cada resultado nuevo de detección ---
            new_det = detector.latest()
            if new_det is not None and new_det.seq != last_det_seq:
                det, last_det_seq = new_det, new_det.seq
                evals = [evaluate(h.px, det.forehead, params, h.world) for h in det.hands]
                best = max(evals, key=lambda e: (e.ok, e.hand_shape, -e.forehead_dist), default=None)
                if trigger.update(best is not None and best.ok, t_start):
                    fired_at = t_start
                    log.info("GESTO (frente vía %s)", det.forehead.source if det.forehead else "?")
                    request_toggle(t_start, "gesto")

            # --- segmentación + composición ---
            if seq != last_seg_seq:
                mask = segmenter.process(frame)
                last_seg_seq = seq
                if background.ready and not background.busy and exposure is not None:
                    exposure.update(frame, background.image, mask)
            state.update(t_start)
            if not background.ready or state.state is State.VISIBLE:
                composed = frame
            else:
                bg_img = exposure.apply(background.image) if exposure is not None else background.image
                if state.state is State.INVISIBLE:
                    composed = composite(frame, bg_img, mask)
                else:
                    # t: 0 = visible, 1 = desaparecido; la reaparición recorre lo mismo al revés
                    p = state.progress(t_start)
                    t = p if state.state is State.DISAPPEARING else 1.0 - p
                    composed = effect.render(frame, bg_img, mask, t)

            out = cv2.flip(composed, 1) if out_cfg["mirror"] else composed

            if vcam is not None:
                vcam.send(out)

            current_fps = fps.tick()
            frames_since_log += 1
            elapsed = time.perf_counter() - last_log
            if elapsed >= 10:
                avg = frames_since_log / elapsed
                det_fps = det.fps if det else 0.0
                log.info("FPS de salida: %.1f | detección: %.1f", avg, det_fps)
                if avg < MIN_FPS and time.perf_counter() - last_slow_warning > 60:
                    log.warning(
                        "Van menos de %d FPS. Para aliviar el CPU, en config.yaml bajá "
                        "detection.width (p. ej. 480), detection.max_fps (p. ej. 15) o "
                        "segmentation.input_width (p. ej. 384); o usá camera 960x540.", MIN_FPS)
                    last_slow_warning = time.perf_counter()
                last_log, frames_since_log = time.perf_counter(), 0

            if args.debug:
                dbg = composed.copy()
                draw_landmarks(dbg, det, evals, params.forehead_ratio)
                if out_cfg["mirror"]:
                    dbg = cv2.flip(dbg, 1)  # el texto se dibuja después, para que no salga espejado
                if trigger.needs_release:
                    status = ("soltá el gesto", YELLOW)
                elif trigger.in_cooldown(t_start):
                    status = ("cooldown", YELLOW)
                else:
                    status = (f"gesto {trigger.count}/{trigger.hold_frames}", GREEN if trigger.count else WHITE)
                src = det.forehead.source if det and det.forehead else "-"
                lines = [
                    (f"estado: {state.state.value}", CYAN),
                    (background.status(t_start), WHITE if background.ready and not background.busy else YELLOW),
                    (f"mascara: dilate {segmenter.dilate_px:.0f} (1/2)  feather {segmenter.feather_px:.0f} (3/4)",
                     WHITE),
                    (f"FPS salida {current_fps:4.1f} | deteccion {det.fps if det else 0:4.1f}", WHITE),
                    (f"frente: {src}", WHITE if src != "-" else RED),
                    status,
                    *rule_lines(best, params.forehead_ratio),
                ]
                if t_start - fired_at < 1.0:
                    lines.insert(0, ("*** GESTO ***", GREEN))
                draw_hud(dbg, lines)
                draw_mask_inset(dbg, mask)
                cv2.imshow(DEBUG_WINDOW, fit_to_window(dbg, DEBUG_WINDOW))
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key in (ord("b"), ord("B")):
                    background.start(t_start)
                if key in (ord("t"), ord("T")):
                    request_toggle(t_start, "tecla T")
                if key in MASK_KEYS:
                    attr, delta = MASK_KEYS[key]
                    setattr(segmenter, attr, max(0.0, getattr(segmenter, attr) + delta))
                    log.info("Máscara: dilate_px=%.0f feather_px=%.0f (copialos a config.yaml para que queden)",
                             segmenter.dilate_px, segmenter.feather_px)
                if cv2.getWindowProperty(DEBUG_WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break

            if vcam is not None:
                vcam.sleep_until_next_frame()
            else:
                remaining = frame_period - (time.perf_counter() - t_start)
                if remaining > 0:
                    time.sleep(remaining)
    except KeyboardInterrupt:
        log.info("Ctrl+C recibido, cerrando…")
    except RuntimeError as e:
        log.error("%s", e)
        return 1
    finally:
        if hotkeys is not None:
            hotkeys.stop()
        if detector is not None:
            detector.release()
        if segmenter is not None:
            segmenter.close()
        if sound is not None:
            sound.close()
        if vcam is not None:
            vcam.release()
        if webcam is not None:
            webcam.release()
        cv2.destroyAllWindows()
    log.info("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(run(parse_args()))
