# LiftGuard AI — Project Documentation

Real-time biomechanical injury-risk monitoring, redesigned from a single-process OpenCV
desktop app into a FastAPI backend + Next.js web dashboard, with USB or WiFi cameras and a
USB or WiFi (ESP32) pan-tilt laser pointer — all AI/CV logic preserved exactly.

This document is the master reference. Companion documents:

| File | Covers |
|---|---|
| `SOURCE_CODE.md` | Full listing of every backend, frontend, and firmware source file |
| `LiftGuard_AI_Architecture.md` | The original folder-structure/module-mapping plan this build followed |
| `backend/README.md` | Backend-specific setup and implementation notes |
| `frontend/README.md` | Frontend-specific setup and design notes |
| `firmware/README.md` | ESP32 wiring/flashing instructions |

---

## 1. What this is

LiftGuard AI tracks a person lifting weights via pose estimation and tells them, in real
time, how risky their form is — spine flexion, hip hinge angle, stability — and whether
fatigue is degrading their form as a set goes on. It optionally points a laser at the body
part that needs correcting and speaks feedback aloud.

The original version was a single Python script (`main.py`) that opened a webcam with
OpenCV, ran everything in one process, and drew its entire UI (skeleton, risk labels,
panels, gauges) directly into the video frame with `cv2.putText`/`cv2.rectangle`, displayed
via `cv2.imshow`. This project restructures that into:

- **A FastAPI backend** that runs the exact same AI pipeline, exposed over REST + WebSocket
- **A Next.js web dashboard** that any browser on the network can open — replacing the need
  for a physical secondary display wired to the rig
- **A hardware layer** that supports both USB and WiFi for the camera and the laser pointer,
  chosen at connect time rather than hardcoded

No prediction/classification logic, model weights, or algorithms were changed anywhere in
this process — every restructuring decision preserved the original computation and only
changed how input reaches it and how output is displayed.

---

## 2. Architecture

```
Camera (USB or WiFi/IP)
        |
        v
Laptop — FastAPI backend (Python)
  |- app/ml/          risk_classifier, TCN, uncertainty manager, IRI V2       (unchanged)
  |- app/tracking/     fatigue_engine, exercise_tracker                       (unchanged)
  |- app/identity/     user_manager_lite (LBPH face ID), user_ui, register_user (unchanged)
  |- app/hardware/     arduino_controller (USB serial, unchanged)
  |                    wifi_arduino_controller (new -- same protocol, over WiFi)
  |- app/core/         liftguard_engine (= old main.py), session_manager, settings_store
  |- app/api/          REST routes + WebSocket live stream
  \- app/db/           session history (SQLAlchemy) + settings persistence
        |
        | REST + WebSocket
        v
Web dashboard (Next.js) -- any browser, any device on the network
        |
        | REST/WS control commands
        v
Laser pointer -- USB Arduino OR WiFi ESP32 (picked at connect time)
```

There is no dedicated secondary display device in this architecture — the web dashboard
fills that role, and it works from a phone, tablet, or another laptop, not just a screen
physically wired to the rig.

### 2.1 Module mapping (original file → new location)

| Original file | New location | Changed? |
|---|---|---|
| `main.py` | `backend/app/core/liftguard_engine.py` | Only the module-loading `try/except` imports (flat filenames → relative package paths). Added: `render_mode` branch in `process_frame()`, `draw_border` param on `_draw_skeleton()`, `_draw_web_frame()`, `connect_usb_laser()`/`connect_wifi_laser()`/`_disconnect_current_laser()` — all additive, described in §3.4–3.5. |
| `risk_classifier.py`, `ml_trainer.py`, `tcn_model.py`, `train_tcn.py`, `temporal_risk_classifier_v2.py`, `uncertainty_manager.py`, `injury_predictor.py`, `injury_risk_index_v2.py` | `backend/app/ml/` | No changes (one import fixed in `train_tcn.py` to be package-relative) |
| `fatigue_engine.py`, `exercise_tracker.py` | `backend/app/tracking/` | Unchanged |
| `arduino_controller.py`, `laser_test.py` | `backend/app/hardware/` | Unchanged |
| `user_manager_lite.py`, `user_ui.py`, `register_user.py` | `backend/app/identity/` | Unchanged |
| `calibration_results.txt` | `backend/data/` | Unchanged |
| `diagnose.py` | `backend/` | Unchanged |

### 2.2 What's genuinely new

- `backend/app/main.py`, `core/config.py`, `core/settings_store.py` — FastAPI app + settings
- `backend/app/core/session_manager.py` — thin wrapper driving `LiftGuardAI` for the web path
- `backend/app/api/*.py`, `backend/app/schemas/*.py` — REST + WebSocket surface
- `backend/app/db/*.py` — session history persistence (SQLAlchemy)
- `backend/app/hardware/wifi_arduino_controller.py` — WiFi/ESP32 laser transport
- `backend/run_standalone.py` — preserves the original `cv2.imshow` desktop entry point
- `frontend/` — the entire Next.js dashboard
- `firmware/liftguard_wifi_laser/` — ESP32 sketch for WiFi laser transport

---

## 3. Backend

### 3.1 Setup

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Requires Python 3.8–3.11 (`mediapipe==0.10.3` doesn't support 3.12+ as of this build).

`requirements.txt` additions beyond the original file: `torch`, `matplotlib`, `pyserial`
(imported by the AI modules but missing from the original list), `sqlalchemy` (session
history), `fastapi`/`uvicorn`/`websockets`/`pydantic`/`python-multipart` (web layer).
`opencv-python` → `opencv-contrib-python` (face ID needs `cv2.face`, contrib-only).

### 3.2 REST API reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Backend liveness check |
| POST | `/api/sessions/start` | Start a session (camera + face ID), returns `session_id` |
| POST | `/api/sessions/{id}/stop` | Stop a session, persists final report to history |
| GET | `/api/sessions/{id}/report` | Live report for an active session |
| GET | `/api/sessions` | List active session IDs |
| GET | `/api/sessions/history` | List completed sessions (`limit`, `user_id` query params) |
| GET | `/api/sessions/history/{id}` | Full report for a completed session |
| GET | `/api/users` | List registered users |
| GET | `/api/users/{id}` | Get one user |
| POST | `/api/users/register` | Register a user from browser-captured webcam frames |
| GET | `/api/hardware/{session_id}/status` | Laser connection status |
| POST | `/api/hardware/{session_id}/connect` | Connect laser — `{transport: "usb"\|"wifi", host?, port?}` |
| POST | `/api/hardware/{session_id}/disconnect` | Disconnect laser |
| POST | `/api/hardware/{session_id}/toggle` | Legacy on/off toggle (USB auto-detect) |
| POST | `/api/hardware/{session_id}/calibrate` | Run laser calibration |
| GET | `/api/analytics/{session_id}/iri-timeline` | IRI values for an active session |
| GET | `/api/analytics/{session_id}/spine-timeline` | Spine flexion values for an active session |
| GET | `/api/analytics/{session_id}/summary` | Same as the session report |
| GET | `/api/settings` | Current session defaults |
| PATCH | `/api/settings` | Update session defaults (partial) |
| WS | `/ws/live/{session_id}` | Live frame (JPEG, base64) + telemetry (JSON) stream |

Interactive docs at `http://localhost:8000/docs` once the backend is running.

### 3.3 WebSocket protocol

The backend pushes two message types per processed frame:

```json
{"type": "frame", "data": "<base64 JPEG - skeleton + correction highlights only>"}
{"type": "telemetry", "risk_label": "...", "risk_level": 0, "confidence": 0.0}
```

The frontend sends control messages, mirroring the original keyboard shortcuts:

```json
{"action": "toggle_voice"}
{"action": "switch_camera:1"}
{"action": "connect_wifi_laser:192.168.1.42"}
```

Full telemetry field list and full control-action list are in `SOURCE_CODE.md` under
`session_manager.py` and `schemas/telemetry.py`.

### 3.4 The OpenCV-to-web UI split

The original `_draw_full_ui()` baked 10 panels of `cv2.rectangle`/`cv2.putText` directly
into the video frame. Two render paths now exist at the tail of `process_frame()`:

- **`_draw_full_ui()`** — untouched. Still runs for `run_standalone.py` (the desktop app).
- **`_draw_web_frame()`** — new. Draws *only* the pose skeleton and correction highlights
  (genuinely pixel-tied to landmark positions). Everything else — identity, risk detail,
  exercise reps, status badges, fatigue/IRI, FPS, the flashing high-risk border — is sent as
  JSON telemetry instead and rendered as HTML/CSS in the frontend's `VideoHUD` component.

Which path runs is controlled by `engine.render_mode` (default `"desktop"`, set to `"web"`
by `SessionManager`) — a one-line branch, not a rewrite.

### 3.5 Hardware transport (camera and laser)

**Camera**: USB (`cv2.VideoCapture(camera_id)`) or WiFi/IP camera (`connect_ip_camera`
control action) — both existed in the original code, now exposed as a session choice.

**Laser**: `ArduinoController` (USB serial, unchanged) and `WifiArduinoController` (new,
subclasses it) both expose the same interface. The entire serial protocol is one method,
`_send(command)`, writing short strings like `"L1"`, `"P90"`, `"C"`. `WifiArduinoController`
overrides only `connect()`, `disconnect()`, and `_send()` to talk HTTP to an ESP32 instead —
every higher-level method (`calibrate()`, `pixel_to_servo()`, `point_at_body_part()`,
`BODY_POSITIONS`) is inherited unchanged. See `firmware/README.md` for the ESP32 side.

### 3.6 Session persistence

Completed sessions are written to a `web_sessions` table (SQLAlchemy) in the same SQLite
file `user_manager_lite.py` already uses — named `web_sessions`, not `sessions`, because
that name is already taken by a table `user_manager_lite.py`'s own `DB_SCHEMA` creates with
different columns.

### 3.7 Editable settings

`core/settings_store.py` persists session defaults (camera, voice, Arduino, model
complexity, TCN on/off) to `backend/data/session_defaults.json`, distinct from
`core/config.py`'s environment-variable-only infra config (CORS, DB path, WS frame rate).
`POST /api/sessions/start` merges any field you omit from the request with these stored
defaults.

---

## 4. Frontend

### 4.1 Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE, points at the backend
npm run dev
```

### 4.2 Pages

| Route | Purpose |
|---|---|
| `/dashboard` | Overview — active sessions, registered users, quick-start |
| `/live` | Core screen — video + HUD, risk gauge, corrections, controls |
| `/analytics` | Per-session IRI/spine timelines |
| `/reports` | Session report detail (live or historical) |
| `/sessions` | Active + past sessions list |
| `/users` | Registered users table |
| `/register` | Browser-webcam face enrollment flow |
| `/hardware` | Laser connect (USB/WiFi picker), status, calibrate |
| `/settings` | Editable session defaults |

### 4.3 Design system

Dark, clinical-instrument aesthetic rather than a generic fitness-app look, since the
product is a clinical-grade injury index, not a rep counter.

- **Palette**: graphite base (`#0A0E13`), glass panels, clinical teal (`#4FD1C5`) for
  low/calm risk, amber → red → crimson escalation mapped directly to `risk_level` from the
  engine, violet (`#8B7FD1`) reserved for the MC-Dropout uncertainty band.
- **Type**: Space Grotesk (headings), Inter (UI text), JetBrains Mono (any live number —
  telemetry, FPS, gauge readouts).
- **Signature elements**: the radial risk gauge (270° instrument arc, shaded band = actual
  model uncertainty interval, not decoration), the circular capture-progress ring during
  face enrollment, the on-video HUD (identity chip, status badges, biomechanics readout)
  replacing what used to be OpenCV text panels.

### 4.4 Video HUD

`components/live/VideoHUD.tsx` overlays the video feed with what the OpenCV panels used to
draw as pixels: identity chip (top-left), status badges — camera/voice/laser/FPS (top-right),
biomechanics readout — spine/hip/stability (bottom-left), rep counter + phase (bottom-right).
High risk is a CSS glow on the video container, not a flashing border baked into the frame.

---

## 5. Firmware

`firmware/liftguard_wifi_laser/liftguard_wifi_laser.ino` — ESP32 sketch implementing the
same command protocol the USB Arduino uses (`L1`/`L0`, `P<angle>`/`T<angle>`, `C`, `B<n>`),
served over HTTP (`GET /ping`, `GET /cmd?c=...`) instead of a serial line. Wiring: pan servo
→ GPIO 13, tilt servo → GPIO 12, laser → GPIO 14, 2x SG90 + laser powered from the battery
pack (not the ESP32's 5V pin). Full instructions in `firmware/README.md`.

---

## 6. Known gaps

Being direct about what's built-and-verified vs. built-but-untested, since this whole
project was developed without physical camera/Arduino/ESP32 hardware available:

- **Never run against real hardware.** Every file compiles/type-checks and was manually
  cross-referenced for import correctness, but nothing here has been executed against an
  actual webcam, Arduino, or ESP32. That first real run is the priority before trusting any
  of it in a gym.
- **Dependency install & build: verified.** `frontend/package-lock.json` is committed and
  `npm ci` + `tsc` + `next build` pass in CI, as do backend unit tests
  (`backend/requirements-dev.txt`, no heavy CV stack needed — the web layer lazy-loads
  opencv/mediapipe/torch). The full `pip install -r requirements.txt` runtime set (torch,
  mediapipe, opencv-contrib-python) still needs a first-run check on your Python version.
- **API security: added after the fact.** REST/WS auth (optional `LIFTGUARD_API_KEY`
  bearer), ESP32 host allowlisting, and enrollment upload limits are new; they have unit
  tests but no production soak yet.
- **Multi-user concurrent enrollment** — each session has its own camera, so two people
  enrolling on two physical rigs already works. What's not done: a fully async rewrite of
  `identify_from_camera()` itself (still the original blocking call, just no longer blocking
  *other* sessions via `run_in_threadpool`).
- **Cross-session analytics** — history is persisted (`/api/sessions/history`), but there's
  no aggregate view yet (e.g. "average IRI across all sessions this month").

---

## 7. Build history (this session, chronological)

1. Read the uploaded source (19 files, ~10,466 lines), planned the target architecture.
2. Built the FastAPI backend skeleton wrapping the AI pipeline unchanged.
3. Built the full Next.js frontend (8 pages) against that backend.
4. Added session history persistence (SQLAlchemy), caught and fixed a table-name collision
   with `user_manager_lite.py`'s own schema in the process.
5. Made session defaults editable (`/api/settings`), fixed a real blocking-call bug
   (`manager.start()` was stalling the event loop for all clients during face ID).
6. Added browser-based user registration (webcam capture → same LBPH pipeline).
7. Split the OpenCV-baked UI into a skeleton-only video feed + HTML/CSS HUD.
8. Added USB/WiFi transport choice for both camera and laser pointer, including ESP32
   firmware for the WiFi laser path.
9. This document + `SOURCE_CODE.md`.
