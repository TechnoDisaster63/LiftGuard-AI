#!/usr/bin/env bash
# Stop the backend and frontend started by ./start.sh.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$ROOT/.liftguard"

stop_one() {
  local name="$1" pidfile="$STATE/$1.pid"
  if [ -f "$pidfile" ]; then
    local pid; pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      # start.sh launches each server in its own process group (setsid), so
      # this also stops the children (Next's worker, uvicorn's reloader).
      # Without setsid (macOS), fall back to the process and its children.
      kill -TERM -- "-$pid" 2>/dev/null || { pkill -TERM -P "$pid" 2>/dev/null; kill -TERM "$pid" 2>/dev/null; }
      for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
      if kill -0 "$pid" 2>/dev/null; then
        kill -KILL -- "-$pid" 2>/dev/null || { pkill -KILL -P "$pid" 2>/dev/null; kill -KILL "$pid" 2>/dev/null; }
      fi
      echo "[liftguard] Stopped $name"
    else
      echo "[liftguard] $name was not running"
    fi
    rm -f "$pidfile"
  else
    echo "[liftguard] $name was not started by start.sh (nothing to stop)"
  fi
}

stop_one frontend
stop_one backend
