#!/usr/bin/env bash
# One command to run LiftGuard locally (Linux, macOS, GitHub Codespaces).
#
#   ./start.sh                 install what's missing, start backend + frontend, open the app
#   ./start.sh --install-only  just install dependencies (used by the Codespaces setup)
#   ./stop.sh                  stop both
#
# First run downloads the Python ML stack (MediaPipe, OpenCV, PyTorch CPU) and
# the frontend packages - expect several minutes. Later runs start in seconds.
#
# Optional environment:
#   LIFTGUARD_BACKEND_PORT   default 8000
#   LIFTGUARD_FRONTEND_PORT  default 3000
#   LIFTGUARD_CAMERA_SOURCE  a video file or stream URL to analyse instead of a webcam
#   PYTHON                   Python to build the backend venv with (3.11 recommended)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$ROOT/.liftguard"
BACKEND_PORT="${LIFTGUARD_BACKEND_PORT:-8000}"
FRONTEND_PORT="${LIFTGUARD_FRONTEND_PORT:-3000}"
VENV="$ROOT/backend/.venv"
mkdir -p "$STATE"

say()  { printf '\033[1;36m[liftguard]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[liftguard]\033[0m %s\n' "$*" >&2; exit 1; }

# Some minimal images ship without sha256sum; fall back to shasum/md5sum.
fingerprint() { (sha256sum "$@" 2>/dev/null || shasum -a 256 "$@" 2>/dev/null || md5sum "$@") | awk '{print $1}' | tr -d '\n'; }

pick_python() {
  if [ -n "${PYTHON:-}" ]; then echo "$PYTHON"; return; fi
  for p in python3.11 python3.12 python3; do
    if command -v "$p" >/dev/null 2>&1; then echo "$p"; return; fi
  done
  fail "Python 3.11 not found. Install it from https://www.python.org/downloads/ and run again."
}

install_backend() {
  if [ ! -x "$VENV/bin/python" ]; then
    local py; py="$(pick_python)"
    local ver; ver="$("$py" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    case "$ver" in
      3.11|3.12) ;;
      *) fail "Found Python $ver at $py. LiftGuard needs 3.11 (or 3.12). Set PYTHON=/path/to/python3.11." ;;
    esac
    say "Creating backend virtualenv with Python $ver"
    "$py" -m venv "$VENV"
  fi
  local want; want="$(fingerprint "$ROOT/backend/requirements.txt")"
  if [ "$(cat "$VENV/.liftguard-requirements" 2>/dev/null)" != "$want" ]; then
    say "Installing backend packages (first run takes a few minutes)"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    if [ "$(uname -s)" = "Linux" ]; then
      # CPU-only PyTorch: the default Linux wheel pulls ~2 GB of CUDA libraries
      # that LiftGuard never uses.
      "$VENV/bin/python" -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
    fi
    "$VENV/bin/python" -m pip install --quiet -r "$ROOT/backend/requirements.txt"
    echo "$want" > "$VENV/.liftguard-requirements"
  fi
}

install_frontend() {
  command -v npm >/dev/null 2>&1 || fail "Node.js not found. Install Node 20 LTS from https://nodejs.org and run again."
  local want; want="$(fingerprint "$ROOT/frontend/package-lock.json")"
  if [ ! -d "$ROOT/frontend/node_modules" ] || [ "$(cat "$ROOT/frontend/node_modules/.liftguard-lock" 2>/dev/null)" != "$want" ]; then
    say "Installing frontend packages"
    (cd "$ROOT/frontend" && npm ci --no-audit --no-fund --loglevel=error)
    echo "$want" > "$ROOT/frontend/node_modules/.liftguard-lock"
  fi
}

# launch NAME DIR CMD... : run CMD in DIR as the leader of a new process
# group, detached from this terminal. The pid file holds the group id, so
# stop.sh can stop the server and everything it spawned.
launch() {
  local name="$1" dir="$2"; shift 2
  rm -f "$STATE/$name.pid"
  local detach="nohup"   # macOS has no setsid; stop.sh then stops children by parent pid
  command -v setsid >/dev/null 2>&1 && detach="setsid"
  # exec: no shell is left behind holding this terminal (or a pipe) open.
  (cd "$dir" && exec $detach sh -c 'echo $$ > "$0"; exec "$@"' "$STATE/$name.pid" "$@") \
      > "$STATE/$name.log" 2>&1 < /dev/null &
  for _ in $(seq 1 50); do [ -s "$STATE/$name.pid" ] && return 0; sleep 0.1; done
  fail "Couldn't start the $name (no pid). See $STATE/$name.log."
}

running() { [ -f "$STATE/$1.pid" ] && kill -0 "$(cat "$STATE/$1.pid")" 2>/dev/null; }
http_ok() { curl -fsS --max-time 3 "$1" >/dev/null 2>&1; }

# Wait until $1 answers, while process $2 is alive. $3 = seconds, $4 = log.
wait_for() {
  local url="$1" name="$2" secs="$3" log="$4" i=0
  until http_ok "$url"; do
    if ! running "$name"; then
      echo; tail -n 25 "$log" >&2
      fail "The $name stopped while starting. Last lines of $log are above."
    fi
    i=$((i + 1)); [ "$i" -ge "$secs" ] && fail "The $name didn't answer at $url within ${secs}s. See $log."
    sleep 1
  done
}

command -v curl >/dev/null 2>&1 || fail "curl is required (sudo apt install curl)."
install_backend
install_frontend
[ "${1:-}" = "--install-only" ] && { say "Dependencies installed."; exit 0; }

# ── Backend ─────────────────────────────────────────────────────────
if http_ok "http://127.0.0.1:$BACKEND_PORT/api/health"; then
  say "Backend already running on port $BACKEND_PORT"
else
  say "Starting backend on 127.0.0.1:$BACKEND_PORT"
  launch backend "$ROOT/backend" "$VENV/bin/python" -m uvicorn app.main:app \
      --host 127.0.0.1 --port "$BACKEND_PORT"
  wait_for "http://127.0.0.1:$BACKEND_PORT/api/health" backend 90 "$STATE/backend.log"
  say "Backend healthy"
fi

# ── Frontend ────────────────────────────────────────────────────────
# In Codespaces the browser can only reach forwarded ports, so the frontend
# proxies /api and /ws to the backend (see frontend/next.config.js) and the
# backend itself stays on localhost, never exposed.
if [ "${CODESPACES:-}" = "true" ]; then
  export NEXT_PUBLIC_API_BASE=""
  export LIFTGUARD_BACKEND_URL="http://127.0.0.1:$BACKEND_PORT"
else
  export NEXT_PUBLIC_API_BASE="${NEXT_PUBLIC_API_BASE:-http://localhost:$BACKEND_PORT}"
fi

if http_ok "http://127.0.0.1:$FRONTEND_PORT/"; then
  say "Frontend already running on port $FRONTEND_PORT"
else
  say "Starting frontend on port $FRONTEND_PORT"
  launch frontend "$ROOT/frontend" npx next dev -p "$FRONTEND_PORT"
  wait_for "http://127.0.0.1:$FRONTEND_PORT/" frontend 120 "$STATE/frontend.log"
  # The dev server compiles each page on first visit. Warm the main pages
  # now so the first click in a demo isn't a multi-second wait.
  say "Preparing pages"
  for page in dashboard live register users sessions reports settings; do
    curl -fsS --max-time 90 "http://127.0.0.1:$FRONTEND_PORT/$page" >/dev/null 2>&1 || true
  done
fi

URL="http://localhost:$FRONTEND_PORT"
if [ "${CODESPACES:-}" = "true" ]; then
  URL="https://${CODESPACE_NAME}-${FRONTEND_PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  say "LiftGuard is running: $URL (also under the Ports tab)"
else
  say "LiftGuard is running: $URL"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then open "$URL" || true
  fi
fi
say "Logs: .liftguard/backend.log, .liftguard/frontend.log   Stop: ./stop.sh"
