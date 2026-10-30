# Teleport: instant transmission for video calls

Do the **instant transmission** gesture (index and middle fingers extended,
held together and touching your forehead) and you **vanish from the video**
with an anime-style animation. Do it again and you reappear.

Teleport reads your webcam and publishes the result as a **virtual camera**.
In Google Meet (or Zoom, Teams…) you pick that camera instead of your real one.
Everything runs locally on your computer and nothing is uploaded anywhere.

> Fan project, not affiliated with or endorsed by the owners of Dragon Ball.
> This repository includes a Dragon Ball sound clip for **private use only**:
> keep the repo private, or remove `assets/teleportDbz.*` before making it public.

**Contents**
1. [Requirements](#1-requirements)
2. [Installation on macOS](#2a-installation-on-macos)
3. [Installation on Windows](#2b-installation-on-windows)
4. [First test](#3-first-test)
5. [Using it in a meeting](#4-using-it-in-a-meeting)
6. [Controls](#5-controls)
7. [Sound](#6-sound)
8. [Troubleshooting](#7-troubleshooting)
9. [Tuning](#8-tuning)
10. [Technical details](#9-technical-details)

---

## 1. Requirements

| | **macOS** | **Windows** |
|---|---|---|
| OS | macOS 13 (Ventura) or newer | Windows 10 or 11 |
| Computer | **Apple silicon Mac** (M1, M2, M3, M4…) | any laptop or PC from the last few years |
| Webcam | built-in or USB | built-in or USB |
| Software | Python 3.13 and OBS Studio (free) | Python 3.13 and OBS Studio (free) |

> **Does my Mac have Apple silicon?** Apple menu  → *About This Mac*. If
> "Chip" says *Apple M…*, yes. If it says *Intel*, this version won't work:
> the detection library (MediaPipe) no longer ships builds for Intel Macs.

### Getting the project

- With git: `git clone <this repo's URL>`
- Without git: on GitHub, **Code → Download ZIP**, then unzip it.

Put it in a simple path, for example `Documents/Teleport`. If someone copies
you their folder instead, copy everything **except `.venv`**: that folder only
works on the computer where it was created, and the installation builds a new
one.

---

## 2a. Installation on macOS

You only do this once. You'll use the **Terminal** app (⌘ + Space, type
"Terminal", Enter).

### Step 1: Python 3.13

1. Download the macOS installer from https://www.python.org/downloads/ (the
   *Download Python 3.13.x* button) and run it.
2. **Important:** when it finishes, a *Python 3.13* folder opens. Double-click
   **`Install Certificates.command`**. Without this step, downloading the
   models fails with an SSL certificate error.
3. Check it in the Terminal:
   ```bash
   python3.13 --version
   ```
   It should print `Python 3.13.x`.

> If you use Homebrew, `brew install python@3.13` also works, and you don't
> need the certificates step.

### Step 2: OBS Studio (provides the virtual camera)

1. Download it from https://obsproject.com/ (the *macOS Apple Silicon* build)
   or run `brew install --cask obs`. Move it to *Applications*.
2. Open OBS. If it offers the auto-configuration wizard, cancel it.
3. Click **"Start Virtual Camera"** (bottom right). macOS will ask you to allow
   a **system extension**:
   - **macOS 15 or newer:** *System Settings → General → Login Items &
     Extensions → Camera Extensions* → turn on **OBS Virtual Camera**.
   - **macOS 13 / 14:** *System Settings → Privacy & Security* → near the
     bottom you'll see "System software from OBS was blocked" → **Allow**.
4. Back in OBS, click **"Stop Virtual Camera"** and **quit OBS** (⌘Q).

You only do this once. After that you don't need to open OBS to use Teleport.
In fact, **OBS must be closed** while Teleport is running.

### Step 3: the project

In the Terminal, go to the project folder. Type `cd ` (with a trailing space),
drag the *Teleport* folder from Finder into the Terminal window and press
Enter. Then run:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python download_models.py
```

- The second command takes a couple of minutes.
- The third one downloads ~18 MB of official models from Google.

### Step 4: macOS permissions

- **Camera:** the first time you start Teleport, macOS asks whether
  **Terminal** may use the camera → **Allow**. If you said no, change it in
  *System Settings → Privacy & Security → Camera*.
- **Hotkeys (F9 / F8):** for them to work while another app (like Meet) has
  focus, macOS must let Terminal read the keyboard:
  1. Go to *System Settings → Privacy & Security*.
  2. Under **Input Monitoring**, turn on **Terminal** (add it with **+** if
     it's not listed).
  3. Do the same under **Accessibility**.
  4. Quit Terminal completely (⌘Q) and open it again.

  If you run Teleport from VS Code instead of Terminal, grant these
  permissions to **Visual Studio Code**.
- On Mac keyboards the F keys need **Fn**: **Fn + F9**.

Done. Continue with the [first test](#3-first-test).

---

## 2b. Installation on Windows

You only do this once. You'll use **PowerShell**: right-click the project
folder → *Open in Terminal*.

### Step 1: Python 3.13

1. Download the installer from https://www.python.org/downloads/ and run it.
   **Tick "Add python.exe to PATH"** on the first screen.
2. Check it:
   ```powershell
   py -3.13 --version
   ```

### Step 2: OBS Studio (provides the virtual camera)

```powershell
winget install -e --id OBSProject.OBSStudio
```

You can also download it from https://obsproject.com/. **Open it once and
close it**: that registers the *OBS Virtual Camera*. You don't need to open it
again.

### Step 3: the project

From the project folder:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe download_models.py
```

Windows doesn't need any special permissions.

---

## 3. First test

Try it on your own first, with the **debug window**, which shows what the app
detects.

| macOS | Windows |
|---|---|
| `.venv/bin/python src/main.py --debug --no-vcam` | `.\.venv\Scripts\python.exe src\main.py --debug --no-vcam` |

(`--no-vcam` means no virtual camera, just for testing.)

1. **5-second countdown**, one beep per second: **step out of the frame**.
   This saves a photo of the background without you. A higher-pitched beep
   tells you you can come back.
2. **Do the gesture:** index and middle fingers straight and together, ring
   and pinky fingers curled, and the fingertips on your forehead. Hold it for
   a moment. You'll vanish with the animation.
3. Do the gesture again to reappear.
4. Also try **F9** (on Mac **Fn + F9**): it does the same as the gesture.
5. To quit: **Q** or **Esc** with the window focused, or **Ctrl + C** in the
   Terminal.

**Reading the debug window:**

- **The hand:**
  - red: the hand doesn't have the shape of the gesture;
  - yellow: the shape is right, but it's not on your forehead;
  - green: the gesture is complete.
- **The yellow circle** is the forehead area where your fingertips need to be.
- **Top left** shows the state (`VISIBLE`, `INVISIBLE`…) and one line per
  gesture rule: `[x]` when it's met, `[ ]` when it isn't. If the gesture
  doesn't trigger, this tells you what's missing.
- **The thumbnail at the bottom right** is the person mask: white is what the
  app thinks is "you".

The drawings (circle, lines, text) **only appear in this window**. They're
never sent to the meeting.

---

## 4. Using it in a meeting

1. **Start Teleport before joining the meeting**, with no window:

   | macOS | Windows |
   |---|---|
   | `.venv/bin/python src/main.py` | `.\.venv\Scripts\python.exe src\main.py` |

   Add `--debug` if you want to see what's happening.
2. Do the countdown: **step out of the frame for 5 seconds**.
3. In **Google Meet**, go to **⋮ (more options) → Settings → Video → Camera**
   and choose **OBS Virtual Camera**.
   - During a call you can also switch it with the small arrow next to the
     camera button.
   - Zoom, Teams and Discord work the same way: pick *OBS Virtual Camera* as
     your camera.
4. Pull the prank. 🫡 Keep **F9** handy in case the gesture doesn't trigger on
   the spot.
5. When you're done: **Ctrl + C** in the Terminal.

> Meet shows your own preview mirrored, but everyone else sees you the right
> way round. There's nothing to change.

> **Mac:** if *OBS Virtual Camera* isn't listed in Meet, quit Chrome
> completely (⌘Q) and reopen it while Teleport is running.

---

## 5. Controls

| Action | macOS | Windows |
|---|---|---|
| Vanish / reappear | gesture, or **Fn + F9** | gesture, or **F9** |
| Recapture the background | **Fn + F8**, or **B** in the debug window | **F8**, or **B** in the debug window |
| Vanish / reappear from the debug window | **T** | **T** |
| Adjust the mask edge (debug window) | **1 / 2** and **3 / 4** | **1 / 2** and **3 / 4** |
| Quit | **Ctrl + C** in the Terminal, or **Q / Esc** in the debug window | same |

**F9 and F8 work even when another window has focus**, such as Meet. On a Mac
this needs the *Input Monitoring* permission from step 4.

Recapture the background (**F8**) whenever the lighting changes or something
behind you moves. Pressing it starts the 5-second countdown again.

---

## 6. Sound

The effect plays **through your speakers**, and your microphone picks it up
like any other sound in the room:

- **With speakers:** people hear it (quieter and with some room echo). That's
  enough for the joke.
  - If they can't hear it, turn off Meet's **noise cancellation**: ⋮ →
    Settings → Audio → *Noise cancellation*.
  - You can also raise `sound.volume` in your config (max `1.0`).
- **With headphones:** nothing reaches the meeting. For that you need a
  virtual audio cable that mixes your microphone with the effect:
  - **macOS:** [BlackHole](https://existential.audio/blackhole/), with an
    *Aggregate Device* set up in the *Audio MIDI Setup* app.
  - **Windows:** [VB-Cable](https://vb-audio.com/Cable/) +
    [Voicemeeter](https://vb-audio.com/Voicemeeter/).

**The default sound** is the Dragon Ball clip `assets/teleportDbz.wav`, already
trimmed. If it's missing, the app falls back to an original synthetic effect,
which it generates automatically in `assets/teleport.wav`.

**Using your own sound clip:**
1. Put your file (mp3/wav/ogg) in `assets/`.
2. Trim the silence at the start and end:

   | macOS | Windows |
   |---|---|
   | `.venv/bin/python trim_sound.py assets/my_sound.mp3` | `.\.venv\Scripts\python.exe trim_sound.py assets\my_sound.mp3` |

   This creates `assets/my_sound.wav`.
3. Point to it in `config.local.yaml` (see [Tuning](#8-tuning)):
   ```yaml
   sound:
     disappear: assets/my_sound.wav
     appear: assets/my_sound.wav
   ```

Clips in `assets/` are tracked by git. **Don't push audio you don't have the
rights to to a public repository.**

---

## 7. Troubleshooting

**"Could not open the camera"** (*No se pudo abrir la cámara*)
- Another app is using the camera (Meet, Zoom, FaceTime, Photo Booth, OBS…).
  Close it, start Teleport, and **only then** choose *OBS Virtual Camera* in
  Meet.
- **macOS:** the camera permission may be missing. Go to *System Settings →
  Privacy & Security → Camera* and turn on *Terminal* (or *VS Code*).
- If you have more than one camera, run `src/main.py --list-cameras` and set
  the right number in `camera.index`.

**"Could not start the virtual camera"** (*No se pudo iniciar la cámara virtual*)
- **macOS:**
  - the "Start Virtual Camera" step in OBS wasn't done, or the extension
    wasn't allowed (see [step 2](#step-2-obs-studio-provides-the-virtual-camera));
  - or OBS is open: quit it.
- **Windows:** OBS was never opened (open it once and close it), or it's open
  and using its own virtual camera.

**Meet shows a black image, or the camera isn't listed**
Teleport has to be running first. Reload the Meet page. On a Mac, if it still
isn't listed, quit Chrome with ⌘Q and reopen it.

**F9 / F8 do nothing**
- **macOS:**
  - remember **Fn**;
  - check the *Input Monitoring* and *Accessibility* permissions (step 4) and
    restart Terminal;
  - Teleport prints a warning at startup if macOS denied the permission.
- **Windows:** another app may be using that key. Change it under `hotkeys`
  (e.g. `"<ctrl>+<alt>+t"`).
- In the meantime, the gesture and the **T** key in the debug window still
  work.

**While invisible, my silhouette still shows a little**
- If the lighting changed, recapture the background with **F8**. Even lighting
  helps, and so does not having a window behind you.
- If you see an **outline or halo**, run with `--debug`, go invisible and press
  **2** a few times (it grows the covered area) until it's gone. If the edge
  looks hard, press **4**. The values are shown on screen: copy them to
  `segmentation.dilate_px` and `segmentation.feather_px` in your config so they
  stick.

**Someone walks behind me, or I moved something**
The app stores a photo of the background, so if something changed behind you,
the spot where you are shows "how it used to be". Recapture with **F8** once
everything is still. If another person enters the frame, they vanish too when
you go invisible.

**The gesture isn't detected (or it's hard to trigger)**
Run with `--debug` and see which rule stays at `[ ]`:
- `en la frente` (on the forehead): touch your forehead, read the `d=` value,
  and set `gesture.forehead_ratio` a bit above it;
- `juntos` (together): raise `gesture.together_ratio` (e.g. `0.5`);
- `anular / meñique flexionado` (ring / pinky curled): raise
  `gesture.flex_mcp_ratio` (e.g. `1.5`).

A well-lit hand, with the palm roughly facing the camera, helps.

**The gesture triggers on its own**
Raise `gesture.hold_frames` (e.g. `12`) or lower `gesture.forehead_ratio`.

**It's slow or choppy**
The Terminal warns you when the FPS drops and suggests what to change. In
order:
1. In `detection`, set `width: 480` and `max_fps: 15`.
2. In `segmentation`, set `input_width: 384`.
3. In `camera`, set `width: 960` and `height: 540`.

**Ctrl + C doesn't stop it**
Click the Terminal first, or close the debug window with **Q**.

**SSL / certificate error when running `download_models.py` (macOS)**
The `Install Certificates.command` step is missing (step 1 for macOS).

> The app's on-screen texts and log messages are in Spanish. The quoted Spanish
> phrases above are what you'll see.

---

## 8. Tuning

All settings live in **`config.yaml`**, and every option has a comment that
explains it.

**Put your personal changes in `config.local.yaml`.** Create that file next
to `config.yaml` with only the keys you want to change. It overrides
`config.yaml` and is ignored by git. Example:

```yaml
sound:
  disappear: assets/my_sound.wav
  appear: assets/my_sound.wav
  volume: 1.0
segmentation:
  dilate_px: 18
```

Restart Teleport after changing the config.

| What you want to change | Where |
|---|---|
| Which camera | `camera.index` |
| How long to hold the gesture | `gesture.hold_frames` (8 ≈ ⅓ s) |
| How close to the forehead | `gesture.forehead_ratio` |
| Countdown length / beeps | `background.countdown_s`, `background.beep` |
| Animation length | `effects.disappear_s`, `effects.appear_s` |
| Animation look | the rest of `effects` (direction, flicker, flash…) |
| Sound and volume | `sound` |
| Hotkeys | `hotkeys` (pynput format) |
| Mirror the output | `output.mirror` |

---

## 9. Technical details

- **Stack:**
  - OpenCV for capture and compositing, plus NumPy;
  - MediaPipe Tasks: Hand Landmarker, Face Landmarker, Pose Landmarker as a
    fallback when the hand covers the face, and Image Segmenter with the
    selfie model;
  - `pyvirtualcam` for the virtual camera, `pynput` for global hotkeys and
    `pygame` for sound.
- **Gesture:** detected with rules, no trained model.
  - The hand shape is measured on the 3D hand landmarks, so rotation doesn't
    matter.
  - The distance to the forehead is measured in "eye distances", so it doesn't
    depend on how far you are from the camera.
  - The gesture must be held for N frames. After it fires there's a cooldown,
    and you also have to release the gesture before it can fire again.
- **States:** `VISIBLE → DISAPPEARING → INVISIBLE → APPEARING → VISIBLE`.
  Gestures are ignored during the animations.
- **Invisible:** your silhouette is replaced with the stored background, and
  the rest of the image stays live.
  - The mask is grown and feathered outside your body.
  - The background is corrected for brightness and color so it blends with the
    live video, because webcams change their exposure automatically.
- **Performance (~30 FPS at 1280x720 without a dedicated GPU):**
  - the webcam and the detection run in separate threads;
  - face and pose are only searched when a hand is visible;
  - the animation only processes the rectangle around the person.
- **VS Code:** *Run and Debug* → **Teleport** or **Teleport (debug window)**.
  Works on macOS and Windows.
- **Tests:** `python -m pytest`, using the Python inside `.venv`.
- **Linux** (untested): use `v4l2loopback` as the virtual camera
  (`sudo modprobe v4l2loopback devices=1 exclusive_caps=1`). The `auto`
  settings already pick the right backends. Global hotkeys need X11.

```
src/
  main.py          main loop and CLI (--debug, --config, --no-vcam, --list-cameras)
  capture.py       webcam (in its own thread) + virtual camera
  detectors.py     MediaPipe: hand, face, pose (in another thread)
  gesture.py       gesture rules + debounce/cooldown
  segmentation.py  person mask + compositing
  background.py    background capture + exposure matching
  effects.py       vanish/reappear animation
  state.py         state machine
  hotkeys.py       global hotkeys
  sound.py         effect sound and beeps
  synth_sound.py   synthetic default sound
  debug_view.py    debug window drawing
  config.py        loads config.yaml + config.local.yaml
config.yaml        settings (config.local.yaml overrides it, not tracked by git)
assets/            sound clips (teleportDbz.wav is the trimmed clip in use)
download_models.py downloads the MediaPipe models into models/
make_sound.py      regenerates the synthetic sound in assets/
trim_sound.py      trims silence from an audio clip
tests/             tests (pytest)
```
