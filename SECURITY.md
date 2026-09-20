# Security

LiftGuard AI is a personal, single-rig system, but its backend can read
biometric profiles, change settings, and drive a physical laser pointer.
Treat it accordingly.

## Threat model and defaults

- **Open by default for localhost development.** With no `LIFTGUARD_API_KEY`
  set, every REST route and the live WebSocket are unauthenticated. That is
  only acceptable when the backend binds to localhost on a machine you
  control.
- **Set `LIFTGUARD_API_KEY` before any network exposure.** Once set, REST
  clients must send `Authorization: Bearer <key>` and the dashboard appends
  `?token=<key>` to the WebSocket URL. Without a key on a reachable port,
  anyone on the network could list users and sessions, change settings,
  enroll face data, or connect and calibrate the laser.
- **Bind deliberately.** `uvicorn app.main:app` defaults to localhost. Only
  pass `--host 0.0.0.0` when the dashboard must be reached from another
  device - and set the API key first.

## ESP32 host validation

`POST /api/hardware/{id}/connect` takes a user-supplied ESP32 host, and the
backend then makes HTTP requests to it. To keep that from becoming an
internal-network request proxy, the host must be a private/loopback/link-local
IP or a local (`.local` / single-label) hostname, unless you pin an explicit
`LIFTGUARD_ESP32_ALLOWED_HOSTS` allowlist. Note the ESP32 link itself is
unauthenticated plain HTTP - anyone on the same LAN who can reach the ESP32
can send it commands. Keep the rig on a trusted network.

## Upload limits

Face enrollment accepts browser-captured frames as base64. Requests are
capped by count (`LIFTGUARD_MAX_REGISTER_IMAGES`, default 30) and per-image
decoded size (`LIFTGUARD_MAX_IMAGE_BYTES`, default 5 MB).

## Biometric data

Face images and LBPH templates are biometric data stored in the local SQLite
database (`backend/data/liftguard_users.db`). If you enroll anyone other than
yourself: get their consent first, tell them what is stored and why, delete
their profile when they ask, and never commit or share the database file
(it is gitignored). A retention/deletion routine belongs in your normal
workflow, not as an afterthought.

## Laser safety

- The system controls a real laser diode. Never point it at eyes - yours,
  other people's, pets', or reflective surfaces that can bounce it.
- Verify `laser_off()` behavior, the center/safe position, and the emergency
  disconnect (`/api/hardware/{id}/disconnect`) on first hardware setup,
  before any session.
- Keep laser power within Class 1/2 limits for any environment with other
  people, and supervise every calibration run.

## Reporting

Found a vulnerability? Open a private security advisory on the repository
rather than a public issue.
