# LiftGuard AI - Backend

FastAPI wrapper around the original LiftGuard AI pipeline. Every AI module
(risk classification, TCN, uncertainty, IRI V2, fatigue, exercise tracking,
Arduino laser guidance, face ID) is moved into `app/` **unchanged** - see
`../LiftGuard_AI_Architecture.md` for the full file-by-file mapping.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Note: `torch`, `matplotlib`, `pyserial`, and `sqlalchemy` were added to requirements.txt -
the first three are imported by `tcn_model.py`/`train_tcn.py` and `arduino_controller.py`
but were missing from the original `requirements.txt`; `sqlalchemy` backs the session
history table. Settings persistence uses stdlib `json` and Starlette's threadpool helper
(already bundled with `fastapi`), so no extra dependency there. `opencv-python` was swapped
for `opencv-contrib-python` because `user_manager_lite.py` uses
`cv2.face.LBPHFaceRecognizer_create()`, which only ships in the contrib build.

## Run the web API (new)

```bash
uvicorn app.main:app --reload --port 8000
```

- REST docs: http://localhost:8000/docs
- Live session: `POST /api/sessions/start` → returns `session_id` → connect
  to `ws://localhost:8000/ws/live/{session_id}` for the video/telemetry stream.

## Run the classic desktop app (unchanged behavior)

If you just want the original cv2.imshow / keyboard-driven experience:

```bash
python run_standalone.py
```

## What's genuinely new here vs. carried over unchanged

| New (this stage) | Unchanged (moved as-is) |
|---|---|
| `app/main.py`, `app/core/config.py` | everything in `app/ml/` |
| `app/core/session_manager.py` (thin wrapper around `LiftGuardAI`) | everything in `app/tracking/`, `app/hardware/`, `app/identity/` |
| `app/api/*.py`, `app/schemas/*.py` | `app/core/liftguard_engine.py` (= old `main.py`, only import paths changed) |

## Laser: USB or WiFi, chosen at connect time

`ArduinoController` (USB serial, unchanged) and the new `WifiArduinoController` (ESP32 over
HTTP, in `app/hardware/wifi_arduino_controller.py`) both expose the same interface -
`WifiArduinoController` subclasses `ArduinoController` and overrides only `connect()`,
`disconnect()`, and `_send()`. Every command `arduino_controller.py` sends is a short
plain-text line ("L1", "P90", "C", ...) written to `self.serial` - the WiFi version sends
the identical string as an HTTP GET to an ESP32 instead. Because all the higher-level logic
(`calibrate()`, `pixel_to_servo()`, `point_at_body_part()`, the whole `BODY_POSITIONS` map)
funnels through that one `_send()` call, none of it needed to change.

`LiftGuardAI.connect_usb_laser()` / `.connect_wifi_laser(host)` hot-swap `self.arduino`
between the two, same pattern as the existing `switch_camera()`/`connect_ip_camera()`.
`POST /api/hardware/{session_id}/connect` exposes the choice: `{"transport": "usb"}` or
`{"transport": "wifi", "host": "192.168.1.42"}`.

ESP32 firmware implementing the WiFi side of the protocol is in
`../firmware/liftguard_wifi_laser/` at the repo root, with wiring/flashing instructions -
not tested against real hardware in this environment, see that folder's README for what to
verify first.

## Control feedback (was silent before)

`SessionManager.handle_control()` now returns a status string instead of just calling the
engine method. `ws_live.py` sends it back as `{"type": "control_ack", "action", "message"}`
after every control message, so the frontend can show a toast - the original methods
(`toggle_voice()`, `save_model()`, etc.) only ever `print()`ed to a console the web user
can't see. `GET /api/analytics/{session_id}/uncertainty` does the same for the `[U]`
shortcut's `show_uncertainty_summary()`, which was also print-only.

## OpenCV UI moved to the webpage

`liftguard_engine.py` now has two render paths at the tail of `process_frame()`:

- **`_draw_full_ui()`** - untouched, the exact original OpenCV HUD (10 panels of
  `cv2.rectangle`/`cv2.putText`) baked into the frame. Still runs for `run_standalone.py`.
- **`_draw_web_frame()`** - new, used when `SessionManager` sets `engine.render_mode = "web"`.
  Draws *only* the pose skeleton and correction highlights (the parts genuinely tied to
  landmark pixel positions). Every panel that was pure text/chrome - user identity, risk
  detail, exercise reps, status badges, fatigue/IRI, FPS, the flashing high-risk border - is
  no longer baked into pixels. It's sent as JSON via `SessionManager._collect_telemetry()`
  (now much larger - mirrors every field those panels used to read) and rendered as real
  HTML/CSS in the frontend's `VideoHUD` component instead.

The only change to existing drawing code: `_draw_skeleton()` gained an optional
`draw_border=True` parameter (default preserves the original behavior exactly) so web mode
can skip the flashing red border - that becomes a CSS glow on the video container in the
browser instead. No prediction/classification logic was touched.

## Registration troubleshooting (fixed two real bugs here)

If `/register` wasn't working: two concrete bugs were found and fixed.

1. **CORS only matched `http://localhost:3000` exactly.** Browsers treat `localhost` and
   `127.0.0.1` as different origins even on the same machine - if the frontend happened to
   be opened via `127.0.0.1:3000` (or `next dev` picked port 3001 because 3000 was busy),
   every API call from it was silently blocked, including the registration POST. Default
   origins now include both hosts on ports 3000 and 3001. Set `LIFTGUARD_CORS_ORIGINS`
   (comma-separated) if you're serving the frontend from somewhere else.
2. **`USER_DB_PATH` was a bare relative path** (`"data/liftguard_users.db"`). sqlite3 doesn't
   create missing directories, so if `uvicorn` was launched from anywhere other than
   `backend/` itself, `UserManager()` - constructed at import time in `routes_users.py` -
   would fail immediately and take the whole app down. Now resolved to an absolute path
   under `backend/` regardless of working directory, with the directory guaranteed to exist.

The `/register` page's error messages are also more specific now - camera permission denied
vs. no camera found vs. camera already in use vs. can't reach the backend (CORS/network) vs.
a validation error from the backend (not enough clear face samples) all show different,
actionable text instead of one generic "something went wrong."

## Browser-based user registration

`POST /api/users/register` accepts `display_name` + a list of base64 JPEG frames captured
from the browser's webcam and feeds them through the exact same
`FaceMatcher.detect_faces()` / `extract_face_region()` / `UserManager.register_user()` calls
`_enroll_new_user()` used from a live `cv2.VideoCapture` loop - only the frame *source*
changed, not the recognition algorithm. Needs at least 10 frames with a clearly detected
face (same floor the original code used); returns a clear error with the count otherwise so
the frontend can tell the person to retry with better lighting.

## Known gaps

- **Table naming**: `app/db/models.py`'s `web_sessions` table is deliberately NOT named
  `sessions` - `user_manager_lite.py`'s own `DB_SCHEMA` already creates a `sessions` table
  with different columns in the same SQLite file. Worth knowing if you ever add more tables
  to this file: check `DB_SCHEMA` at the top of `user_manager_lite.py` first.
- **Multi-user concurrent enrollment**: `SessionManager.start()` still calls the original
  blocking `identify_from_camera()` per session - each session has its own camera, so two
  people enrolling on two physical rigs already works; the fix in this stage was making sure
  one person's ~25s face-ID wait no longer blocks the FastAPI event loop for everyone else
  (`start`/`stop` now run in a threadpool via Starlette's `run_in_threadpool`). What's *not*
  done: a fully async/non-blocking `identify_from_camera()` rewrite, which would touch the
  original face-ID algorithm and wasn't part of "preserve every feature."
- **Frontend design QA against real hardware** - built and statically verified (no live
  camera/Arduino in this environment to test against), so budget a real pass once you're
  running it against actual hardware.

## Session defaults (editable settings)

`app/core/settings_store.py` persists session defaults (camera, voice, Arduino, model
complexity, TCN on/off) to `data/session_defaults.json`, separate from `core/config.py`'s
env-var-only infra settings (CORS, DB path, WS frame rate). `GET/PATCH /api/settings` reads
and writes it; `POST /api/sessions/start` merges any fields you omit from the request with
the current stored defaults, so the frontend Settings page's changes actually take effect on
the next session.

## Session persistence

Completed sessions are now written to a `sessions` table (SQLAlchemy) in the same SQLite
file `user_manager_lite.py` already uses, so session records can be joined to users by
`user_id`. See `app/db/models.py` for the schema and `app/api/routes_sessions.py` for the
`/api/sessions/history` and `/api/sessions/history/{id}` endpoints this unlocks.

## Configuration

All infra settings are env vars (see `app/core/config.py`); copy `.env.example`
to `.env` and edit. Highlights: `LIFTGUARD_API_KEY` (REST/WS auth - empty means
open localhost dev mode), `LIFTGUARD_CORS_ORIGINS`, `LIFTGUARD_ESP32_ALLOWED_HOSTS`,
and the enrollment upload limits `LIFTGUARD_MAX_REGISTER_IMAGES` /
`LIFTGUARD_MAX_IMAGE_BYTES`. See `../SECURITY.md` before exposing this to a network.

## Tests, lint, CI

```bash
pip install -r requirements-dev.txt
pytest -q              # unit tests (FastAPI app, security rules, upload limits)
ruff check app tests   # error-level lint (E9 + Pyflakes)
python -m compileall app
```

`requirements-dev.txt` is deliberately light: the web layer lazy-loads the
CV/ML stack (`session_manager.py`, `routes_users.py`, `arduino_controller.py`),
so tests run without opencv/mediapipe/torch. CI runs this plus the frontend
type-check/build on every PR (`.github/workflows/ci.yml`). Real camera/ML/
hardware behavior still needs the full `requirements.txt` install and
physical hardware.
