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
