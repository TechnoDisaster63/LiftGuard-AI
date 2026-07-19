# LiftGuard AI — Target Architecture & Folder Structure

**Principle:** every class below is *moved, not rewritten*. Files get wrapped in a thin service/route layer; internal logic, model weights, math, and algorithms stay byte-for-byte identical.

---

## 1. Key architectural decision: where does the camera live?

Your current app (`main.py` → `LiftGuardAI`) owns `cv2.VideoCapture` directly — local webcam **and** IP camera streams, plus serial access to the Arduino. Both webcam capture and serial ports are host-machine resources a browser can't reach directly.

**Decision:** the backend keeps owning the camera and the Arduino, exactly as today. It runs the full pipeline (MediaPipe → risk models → fatigue → IRI) server-side, then pushes two things to the browser over one WebSocket:
- annotated JPEG frames (skeleton overlay drawn server-side, same as your current `cv2.imshow` overlay logic)
- a JSON telemetry payload per frame (risk, confidence, rep count, fatigue, IRI, alerts)

This preserves 100% of your current data flow — the only thing that changes is `cv2.imshow()` becomes "encode frame → send over WebSocket."

---

## 2. Folder structure

```
liftguard-ai/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI app, router registration, startup/shutdown
│   │   ├── core/
│   │   │   ├── config.py               # settings (camera source, Arduino port, etc.)
│   │   │   └── session_manager.py      # wraps LiftGuardAI orchestration loop (was main.py)
│   │   ├── ml/                         # === UNCHANGED LOGIC, moved as-is ===
│   │   │   ├── risk_classifier.py
│   │   │   ├── ml_trainer.py
│   │   │   ├── tcn_model.py
│   │   │   ├── train_tcn.py
│   │   │   ├── temporal_risk_classifier_v2.py
│   │   │   ├── uncertainty_manager.py
│   │   │   ├── injury_predictor.py
│   │   │   └── injury_risk_index_v2.py
│   │   ├── tracking/
│   │   │   ├── fatigue_engine.py
│   │   │   └── exercise_tracker.py
│   │   ├── hardware/
│   │   │   ├── arduino_controller.py
│   │   │   └── laser_test.py           # kept as standalone CLI calibration utility
│   │   ├── identity/
│   │   │   ├── user_manager_lite.py
│   │   │   ├── user_ui.py              # overlay-drawing logic reused, not deleted
│   │   │   └── register_user.py
│   │   ├── api/
│   │   │   ├── routes_sessions.py      # REST: start/stop/list sessions, reports
│   │   │   ├── routes_users.py         # REST: register/list/get users
│   │   │   ├── routes_hardware.py      # REST: Arduino connect/calibrate/status
│   │   │   ├── routes_analytics.py     # REST: historical charts, exports
│   │   │   └── ws_live.py              # WebSocket: live frame + telemetry stream
│   │   ├── schemas/                    # Pydantic models (typed contracts for frontend)
│   │   └── db/
│   │       └── models.py               # SQLite via SQLAlchemy (was raw sqlite3 in user_manager_lite)
│   ├── models/                         # saved .pkl / .pt weights (risk model, TCN, etc.)
│   ├── data/
│   │   └── calibration_results.txt
│   ├── requirements.txt
│   └── diagnose.py                     # kept as-is, ops utility
│
├── frontend/
│   ├── app/                            # Next.js app router
│   │   ├── dashboard/page.tsx
│   │   ├── live/page.tsx               # Live Analysis (camera + skeleton + gauges)
│   │   ├── analytics/page.tsx
│   │   ├── reports/page.tsx
│   │   ├── users/page.tsx
│   │   ├── sessions/page.tsx
│   │   ├── hardware/page.tsx           # Arduino connect/calibrate UI
│   │   └── settings/page.tsx
│   ├── components/
│   │   ├── live/                       # VideoCanvas, SkeletonOverlay, RiskGauge, RepCounter
│   │   ├── charts/                     # Recharts wrappers: RiskTimeline, FatigueGraph, IRIGraph
│   │   ├── layout/                     # TopNav, Sidebar
│   │   └── ui/                         # shadcn/ui primitives
│   ├── lib/
│   │   ├── api.ts                      # REST client
│   │   └── ws.ts                       # WebSocket client + reconnect logic
│   └── styles/
│
└── shared/
    └── types/                          # OpenAPI-generated or hand-mirrored TS types matching Pydantic schemas
```

---

## 3. Module → service mapping

| Current file | New home | Exposed via |
|---|---|---|
| `main.py` (`LiftGuardAI` orchestration) | `core/session_manager.py` | `ws_live.py` drives its per-frame `update()` loop |
| `risk_classifier.py`, `temporal_risk_classifier_v2.py`, `tcn_model.py`, `uncertainty_manager.py` | `ml/` (untouched) | consumed internally by session manager |
| `injury_predictor.py`, `injury_risk_index_v2.py` | `ml/` (untouched) | `routes_sessions.py` (`get_session_report`), streamed live via WS |
| `fatigue_engine.py`, `exercise_tracker.py` | `tracking/` (untouched) | live WS payload + `routes_analytics.py` for history |
| `arduino_controller.py` | `hardware/` (untouched) | `routes_hardware.py` (connect/calibrate/point-at-body-part) |
| `user_manager_lite.py`, `user_ui.py`, `register_user.py` | `identity/` (untouched) | `routes_users.py`; identification runs inside the live loop as before |
| `ml_trainer.py`, `train_tcn.py` | `ml/` (untouched) | offline scripts, run via CLI — not exposed as API (training isn't a runtime feature) |

Nothing in this table changes internal logic — it's purely "which folder + which route calls it."

---

## 4. API surface (draft)

**REST**
- `POST /api/sessions/start` / `POST /api/sessions/{id}/stop`
- `GET /api/sessions/{id}/report` → wraps `get_session_report()` (fatigue + exercise + IRI)
- `GET /api/sessions` → history for Analytics/Reports pages
- `POST /api/users/register`, `GET /api/users`, `GET /api/users/{id}`
- `POST /api/hardware/arduino/connect`, `POST /api/hardware/arduino/calibrate`, `GET /api/hardware/arduino/status`
- `GET /api/analytics/risk-timeline?session_id=`, `/fatigue`, `/iri` — chart data
- `GET /api/reports/{id}/export.pdf`, `/export.csv`

**WebSocket**
- `WS /ws/live` — backend pushes `{type: "frame", data: base64jpeg}` and `{type: "telemetry", risk, confidence, rep_count, fatigue_score, iri, alerts, fps, latency_ms}` per processed frame; frontend can send `{type: "control", action: "pause"|"resume"|"switch_exercise"}`.

---

## 5. What stays exactly the same

- All model weights, training code, feature extraction math (`extract_biomechanical_features`, TCN forward pass, MC Dropout, IRI acute/cumulative sub-models).
- Face identification logic (Haar Cascade + ORB matching in `user_manager_lite.py`).
- Arduino serial protocol and pan-tilt math in `arduino_controller.py`.
- Voice feedback (`SimpleSpeaker`) — runs server-side, unchanged; frontend just shows a "speaking" indicator via telemetry.

## 6. What changes

- `cv2.imshow()` → WebSocket frame push.
- Keyboard shortcuts in `main.py` → REST/WS control messages from the dashboard.
- Raw `sqlite3` calls in `user_manager_lite.py` → same SQLite file, accessed through SQLAlchemy models for cleaner typed queries (schema unchanged).

---

## Next step

Once you're happy with this shape, next stage is the FastAPI skeleton: `core/session_manager.py` wrapping `LiftGuardAI`, plus `ws_live.py` streaming its first live frame end-to-end — that's the piece everything else depends on.
