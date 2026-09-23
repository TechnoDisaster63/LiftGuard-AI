# Running LiftGuard in GitHub Codespaces

Codespaces runs the full app in the cloud. Nothing is installed on the demo laptop, and a free GitHub account's monthly core-hours cover demos.

## One-click start

1. On the repository page, click **Code → Codespaces → Create codespace on main**.
2. The first build installs the Python ML stack and the dashboard packages. It takes about 10 minutes on the default 2-core machine and only happens once per codespace.
3. When setup finishes, `./start.sh` runs by itself and the **LiftGuard dashboard** opens in a new browser tab. If the tab was blocked, open the **Ports** tab and click the globe icon next to port 3000.

Reopening a stopped codespace starts the app again automatically. To restart by hand, run `./stop.sh && ./start.sh` in the terminal.

## What works differently in the cloud

A codespace is a server in a data centre. It has no webcam, so:

| Feature | In Codespaces |
|---|---|
| Register User | Works. It uses **your browser's** camera, and the browser asks for permission. |
| Live analysis | Needs a video file, because the backend can't see your webcam (see below). |
| Voice cues | No sound (the server has no speakers). |
| Laser hardware | Not available. |

### Live analysis from a recorded clip

1. Drag a side-view squat recording (your own) into the Explorer panel, for example `demo/squat.mp4`.
2. In the terminal:

   ```bash
   ./stop.sh
   LIFTGUARD_CAMERA_SOURCE="$PWD/demo/squat.mp4" ./start.sh
   ```

3. On the Live page, press **Start**. The clip plays through the same squat counter as a webcam would. When the clip ends, the page says so and saves the session.

Recordings dropped into the codespace stay in that codespace. Don't commit clips of other people.

## Privacy and access

- Port 3000 is forwarded as **private**: only your GitHub account can open it. Leave it private. Making it public would let anyone with the link use the dashboard and its registration camera.
- The backend (port 8000) is never forwarded. The dashboard server passes `/api` and `/ws` requests to it inside the codespace (`frontend/next.config.js`, turned on when `LIFTGUARD_BACKEND_URL` is set).
- Stop the codespace after a demo (**Codespaces → … → Stop**) so it doesn't use up free hours.

## If something goes wrong

- Logs: `.liftguard/backend.log` and `.liftguard/frontend.log`.
- "Couldn't open camera": expected in the cloud without `LIFTGUARD_CAMERA_SOURCE`.
- Setup failed during the first build: run `./start.sh` in the terminal to retry. It picks up where it stopped.
