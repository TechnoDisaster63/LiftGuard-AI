"""
WebSocket route that replaces the original cv2.imshow() display loop.

Per connected frontend client, we drive SessionManager.step() in a loop —
the exact same LiftGuardAI.process_frame() call the desktop app made — and
push {type: "frame", ...} / {type: "telemetry", ...} messages instead of
drawing to a native window. Control messages (toggle voice, switch camera,
etc.) arrive the same way keyboard shortcuts used to.
"""
import asyncio
import base64
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.config import settings
from ..core.security import check_ws_api_key
from .routes_sessions import get_session_manager

router = APIRouter(tags=["live"])


@router.websocket("/ws/live/{session_id}")
async def ws_live(websocket: WebSocket, session_id: str):
    if not check_ws_api_key(websocket):
        await websocket.close(code=4401, reason="Unauthorized")
        return
    await websocket.accept()

    try:
        manager = get_session_manager(session_id)
    except Exception:
        await websocket.close(code=4404, reason="Session not found")
        return

    frame_interval = 1.0 / max(settings.WS_TARGET_FPS, 1)

    async def receive_controls():
        """Listen for control messages without blocking the frame loop."""
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                    # handle_control() can block briefly (e.g. connecting to
                    # a laser) — run it off the event loop so it doesn't
                    # stall frame delivery to this or other sessions.
                    result_message = await asyncio.to_thread(manager.handle_control, msg["action"])
                    await websocket.send_text(json.dumps({
                        "type": "control_ack",
                        "action": msg["action"],
                        "message": result_message,
                    }))
                except (ValueError, KeyError) as exc:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": str(exc)})
                    )
        except WebSocketDisconnect:
            pass

    control_task = asyncio.create_task(receive_controls())

    try:
        while manager.active:
            loop_start = asyncio.get_event_loop().time()

            # process_frame() is CPU-bound (MediaPipe/sklearn/torch), so run
            # it off the event loop thread to avoid blocking other clients.
            jpeg_bytes, telemetry = await asyncio.to_thread(manager.step)

            if jpeg_bytes is not None:
                await websocket.send_text(json.dumps({
                    "type": "frame",
                    "data": base64.b64encode(jpeg_bytes).decode("ascii"),
                }))
                await websocket.send_text(json.dumps({
                    "type": "telemetry",
                    **telemetry,
                }))

            elapsed = asyncio.get_event_loop().time() - loop_start
            await asyncio.sleep(max(0, frame_interval - elapsed))
    except WebSocketDisconnect:
        pass
    finally:
        control_task.cancel()
