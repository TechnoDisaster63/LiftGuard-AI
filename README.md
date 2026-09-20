# LiftGuard AI

Real-time lifting injury-risk analysis: MediaPipe pose tracking, ML risk
classification (TCN + MC-Dropout uncertainty + IRI v2), fatigue tracking,
and a pan-tilt laser that points at the body part that needs correcting.
FastAPI backend, Next.js dashboard, ESP32/Arduino laser firmware.

**Status: implemented, validation pending.** The backend, frontend, and
firmware are complete and pass CI (type-check, production build, unit
tests, lint, byte-compile). Real camera, Arduino, ESP32, and laser behavior
still need an on-hardware verification pass before gym use. See
`SECURITY.md` before exposing the backend to any network.

See `LiftGuard_AI_Architecture.md` for the architecture and
`DOCUMENTATION.md` for the full component-by-component writeup.

- `backend/` - FastAPI wrapper around the original AI pipeline. See `backend/README.md`.
- `frontend/` - Next.js dashboard. See `frontend/README.md`.
- `firmware/` - ESP32 sketch for WiFi laser transport (alternative to USB Arduino). See `firmware/README.md`.
- `shared/` - notes on the types decision. See `shared/types/README.md`.

## Hardware architecture

```
Camera (USB or WiFi/IP)  --->  Laptop (FastAPI backend + AI pipeline)  --->  Laser pointer (USB Arduino OR WiFi ESP32, picked at connect time)
                                        |
                                        v
                          Web dashboard (any browser, any device)
```

No dedicated secondary display device - the web dashboard (phone, tablet,
another laptop, anything with a browser on the network) replaces that role.

## Quickstart

```bash
# Terminal 1
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload

# Terminal 2
cd frontend && npm ci && npm run dev
```

Then open http://localhost:3000 - it redirects to the dashboard.

## Security

When `LIFTGUARD_API_KEY` is set on the backend, set the same value as `NEXT_PUBLIC_LIFTGUARD_API_KEY` in `frontend/.env.local`. The dashboard sends it with REST requests and WebSocket handshakes. Because `NEXT_PUBLIC_*` values are embedded in browser code, deploy the dashboard only as a trusted operator UI and never publish a build containing a production key.


The backend can read user data, enroll face profiles, and drive a physical
laser, so it ships with an opt-in API key and an ESP32 host allowlist:

- Set `LIFTGUARD_API_KEY` and clients must send `Authorization: Bearer <key>`
  (the dashboard passes `?token=<key>` on the WebSocket). Empty means open
  development mode - localhost only.
- `/api/hardware/{id}/connect` only accepts private-network IPs or local
  hostnames, or an explicit `LIFTGUARD_ESP32_ALLOWED_HOSTS` allowlist.
- Face-enrollment uploads are limited in count and size.

Copy `backend/.env.example` to `backend/.env` to configure. Full threat
notes, biometric-data guidance, and laser-safety rules: `SECURITY.md`.

## Development

```bash
# Backend: fast test suite (no opencv/mediapipe/torch needed)
cd backend && pip install -r requirements-dev.txt && pytest -q && ruff check app tests

# Frontend: type-check + production build
cd frontend && npm ci && npx tsc --noEmit && npm run build
```

CI (`.github/workflows/ci.yml`) runs all of the above on every push to
`main` and every pull request. `frontend/package-lock.json` is committed,
so installs are reproducible.

## Current engineering limits

- Live sessions are process-local and support one frame-driving WebSocket viewer per camera session. Run a single backend worker; multi-worker deployment needs an external session coordinator and a broadcast stream.
- Browser frames are sent as base64 JPEG inside JSON. This is simple and portable, but binary WebSocket frames or WebRTC would reduce bandwidth and CPU overhead for higher resolutions or remote viewing.
- The camera, face-recognition, ML, Arduino, ESP32, and laser paths still require physical validation. Automated checks cover the web/API layer, not real-world biomechanical accuracy or hardware safety.
- `liftguard_engine.py` remains a large compatibility module. Split rendering, inference, identity, feedback, and hardware orchestration behind typed interfaces before adding major features.

## Installation

### Prerequisites

- Python 3.8-3.11 (the pinned MediaPipe build does not support Python 3.12+)
- Node.js 20 or newer
- A supported camera for live sessions
- Optional: USB Arduino or WiFi ESP32 laser hardware

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

The full requirements include OpenCV, MediaPipe, PyTorch, and hardware libraries. For API tests and linting without the camera/ML stack, install `requirements-dev.txt` instead.

### Frontend

```bash
cd frontend
npm ci
cp .env.local.example .env.local
npm run dev
```

Open <http://localhost:3000>. The frontend expects the API at `http://localhost:8000` unless `NEXT_PUBLIC_API_BASE` is changed.

## Usage examples

### Web dashboard

1. Open **Users** to register a face profile, or continue as a guest when starting a session.
2. Open **Live** and select **Start Session** to start the configured camera and live telemetry stream.
3. Use **Hardware** only after connecting and validating the USB Arduino or ESP32 setup described in `firmware/README.md`.
4. Stop the session before reviewing saved results in **Sessions**, **Analytics**, or **Reports**.

### REST API

With the backend running in open local-development mode:

```bash
# Health check
curl http://localhost:8000/api/health

# Read the current session defaults
curl http://localhost:8000/api/settings

# Start a session using the stored defaults
curl -X POST http://localhost:8000/api/sessions/start \
  -H 'Content-Type: application/json' \
  -d '{}'
```

When `LIFTGUARD_API_KEY` is configured, add `-H "Authorization: Bearer $LIFTGUARD_API_KEY"` to REST requests and configure the trusted dashboard as described above. Interactive API documentation is available at <http://localhost:8000/docs>.

### Standalone desktop mode

```bash
cd backend
python run_standalone.py
```

This preserves the native OpenCV display path. Camera, model, speech, firmware, servo calibration, and laser behavior require real-device validation before use.

## Project layout

- `backend/app/api/` - FastAPI REST and WebSocket routes
- `backend/app/core/` - application configuration, session orchestration, and compatibility engine
- `backend/app/ml/` and `backend/app/tracking/` - inference and movement/fatigue logic
- `backend/app/hardware/` - USB and WiFi laser transports
- `frontend/app/` and `frontend/components/` - Next.js dashboard routes and UI
- `firmware/` - ESP32 firmware and hardware notes
- `.github/workflows/ci.yml` - backend and frontend validation

## Validation boundary

CI checks Python byte-compilation, Ruff, API/unit tests, TypeScript, and a production frontend build. It does not prove biomechanical accuracy or real camera, Arduino, ESP32, servo, speech, or laser safety. Complete a supervised hardware validation pass before gym use.
