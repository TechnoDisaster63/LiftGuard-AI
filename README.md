# LiftGuard AI — Redesign

See `LiftGuard_AI_Architecture.md` for the full plan.

- `backend/` — FastAPI wrapper around the original AI pipeline. **Built.** See backend/README.md.
- `frontend/` — Next.js dashboard. **Built.** See frontend/README.md.
- `shared/` — notes on the types decision. See shared/types/README.md.

## Quickstart

```bash
# Terminal 1
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload

# Terminal 2
cd frontend && npm install && npm run dev
```

Then open http://localhost:3000 — it redirects to the dashboard.
