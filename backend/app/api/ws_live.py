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
    # Accept first so the close code reaches the browser; a close before
    # accept shows up client-side only as a generic 1006 failure.
    await websocket.accept()
    if not check_ws_api_key(websocket):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    try:
        manager = get_session_manager(session_id)
    except Exception:
        await websocket.close(code=4404, reason="Session not found")
        return

    if not manager.acquire_stream():
        await websocket.close(code=4429, reason="Session already has a live viewer")
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
                except (ValueError, KeyError, TypeError) as exc:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": str(exc)})
                    )
                except WebSocketDisconnect:
                    raise
                except Exception as exc:  # a failing control must not kill the listener
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"{msg.get('action', 'control') if isinstance(msg, dict) else 'control'} failed: {exc}",
                    }))
        except WebSocketDisconnect:
            pass

    control_task = asyncio.create_task(receive_controls())

    loop = asyncio.get_event_loop()
    last_frame_at = loop.time()
    close_code, close_reason = 1000, "Session ended"
    try:
        while manager.active:
            loop_start = loop.time()

            # process_frame() is CPU-bound (MediaPipe/sklearn/torch), so run
            # it off the event loop thread to avoid blocking other clients.
            try:
                jpeg_bytes, telemetry = await asyncio.to_thread(manager.step)
            except Exception as exc:  # engine bug: tell the viewer, don't just drop
                await _send_stream_error(
                    websocket, f"The analysis engine stopped on an error ({type(exc).__name__}: {exc}). "
                    "Stop the session and start it again."
                )
                close_code, close_reason = 1011, "Engine error"
                break

            if jpeg_bytes is None:
                if not manager.active:
                    break
                if loop.time() - last_frame_at > NO_FRAME_TIMEOUT_S:
                    source = getattr(manager, "camera_id", None)
                    message = (
                        "The video file finished." if isinstance(source, str) and not source.isdigit()
                        else "The camera stopped sending video (unplugged, or taken by another app). "
                        "Stop the session and start it again."
                    )
                    await _send_stream_error(websocket, message)
                    close_code, close_reason = 4410, "No video"
                    break
                await asyncio.sleep(0.05)
                continue
            last_frame_at = loop.time()

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
        manager.release_stream()
    try:
        await websocket.close(code=close_code, reason=close_reason)
    except Exception:
        pass  # already closed by the client


NO_FRAME_TIMEOUT_S = 3.0


async def _send_stream_error(websocket: WebSocket, message: str) -> None:
    try:
        await websocket.send_text(json.dumps({"type": "error", "fatal": True, "message": message}))
    except Exception:
        pass
