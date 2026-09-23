"""Production entry point for the Hugging Face Space image.

Runs the unchanged FastAPI app and also serves the statically exported
Next.js dashboard from the same origin, so the browser reaches the pages,
/api and /ws/live at one HTTPS address. The device camera works there
because the Space URL is HTTPS (a secure context for getUserMedia).

    LIFTGUARD_STATIC_DIR=/path/to/frontend/out uvicorn serve:app --port 7860
"""
import os
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.main import app

static_dir = Path(os.getenv("LIFTGUARD_STATIC_DIR", "/home/user/app/frontend/out"))
if not static_dir.is_dir():
    raise SystemExit(f"Built dashboard not found at {static_dir}. Run the frontend static export first.")

# Mounted last, so every /api and /ws route registered by app.main wins.
app.mount("/", StaticFiles(directory=static_dir, html=True), name="dashboard")
