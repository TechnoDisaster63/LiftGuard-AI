# LiftGuard on a Hugging Face Docker Space (free CPU tier).
# One container: FastAPI + the analysis engine, serving the exported
# Next.js dashboard on the same origin (port 7860).

# ---- dashboard: static export ----
FROM node:20-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV LIFTGUARD_STATIC_EXPORT=1 NEXT_PUBLIC_API_BASE="" NEXT_TELEMETRY_DISABLED=1
RUN npx next build

# ---- backend + engine ----
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Spaces run the container as uid 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --user torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir --user -r backend/requirements.txt

COPY --chown=user backend/ backend/
COPY --chown=user deploy/huggingface/serve.py backend/serve.py
COPY --chown=user --from=web /web/out frontend/out

# Demo clip for "Start session": a Space has no camera of its own. It is the
# fallback only; "Use this device's camera" streams the visitor's camera.
# "Squat - exercise demonstration video" by FitnessScape, CC BY 3.0, via
# Wikimedia Commons (credited in the Space README).
RUN mkdir -p demo && curl -fsSL -o demo/squat.webm \
    "https://upload.wikimedia.org/wikipedia/commons/5/5c/Squat_-_exercise_demonstration_video.webm"

ENV LIFTGUARD_CAMERA_SOURCE=/home/user/app/demo/squat.webm \
    LIFTGUARD_STATIC_DIR=/home/user/app/frontend/out \
    LIFTGUARD_USER_DB=/home/user/app/data/liftguard_users.db \
    LIFTGUARD_ARDUINO_ENABLED=false \
    LIFTGUARD_VOICE_ENABLED=false

WORKDIR /home/user/app/backend
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
