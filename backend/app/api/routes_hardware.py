from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.security import validate_esp32_host
from ..hardware.wifi_arduino_controller import WifiArduinoController
from ..schemas.hardware import ArduinoStatus, ArduinoConnectResponse, LaserConnectRequest
from .routes_sessions import get_session_manager

router = APIRouter(prefix="/api/hardware", tags=["hardware"])


def _transport_of(arduino) -> str:
    if not getattr(arduino, "connected", False):
        return "none"
    return "wifi" if isinstance(arduino, WifiArduinoController) else "usb"


@router.get("/{session_id}/status", response_model=ArduinoStatus)
def arduino_status(session_id: str):
    manager = get_session_manager(session_id)
    arduino = manager.engine.arduino
    return ArduinoStatus(
        connected=getattr(arduino, "connected", False),
        port=getattr(arduino, "port", None),
        laser_on=getattr(arduino, "laser_on", False),
        transport=_transport_of(arduino),
    )


@router.post("/{session_id}/connect", response_model=ArduinoConnectResponse)
def connect_laser(session_id: str, req: LaserConnectRequest):
    """Pick USB or WiFi at connect time — mirrors switch_camera's hot-swap
    pattern. WiFi requires `host` (the ESP32's IP or mDNS hostname, e.g.
    192.168.1.42 or liftguard-laser.local)."""
    manager = get_session_manager(session_id)

    if req.transport == "wifi":
        if not req.host:
            raise HTTPException(status_code=400, detail="host is required for WiFi transport")
        try:
            host = validate_esp32_host(req.host)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        ok = manager.engine.connect_wifi_laser(host)
    else:
        ok = manager.engine.connect_usb_laser(req.port)

    if not ok:
        target = req.host if req.transport == "wifi" else (req.port or "auto-detected port")
        raise HTTPException(
            status_code=400,
            detail=f"Couldn't connect to the laser over {req.transport} ({target}).",
        )

    arduino = manager.engine.arduino
    return ArduinoConnectResponse(
        connected=True,
        port=getattr(arduino, "port", None),
        transport=_transport_of(arduino),
        message=f"Connected via {req.transport}",
    )


@router.post("/{session_id}/disconnect", response_model=ArduinoConnectResponse)
def disconnect_laser(session_id: str):
    manager = get_session_manager(session_id)
    manager.engine._disconnect_current_laser()
    return ArduinoConnectResponse(connected=False, port=None, transport="none", message="Disconnected")


@router.post("/{session_id}/toggle", response_model=ArduinoConnectResponse)
def toggle_arduino(session_id: str):
    """Legacy on/off toggle — mirrors the original [A] keyboard shortcut,
    always attempts USB (auto-detect port). Use /connect for WiFi or an
    explicit port."""
    manager = get_session_manager(session_id)
    manager.handle_control("toggle_arduino")
    arduino = manager.engine.arduino
    return ArduinoConnectResponse(
        connected=getattr(arduino, "connected", False),
        port=getattr(arduino, "port", None),
        transport=_transport_of(arduino),
        message="Arduino toggled",
    )


@router.post("/{session_id}/calibrate")
def calibrate_laser(session_id: str):
    """Mirrors the [K] keyboard shortcut — runs the same calibrate() routine,
    unchanged, regardless of which transport is active underneath."""
    manager = get_session_manager(session_id)
    if not manager.cap:
        raise HTTPException(status_code=400, detail="Session has no open camera")
    manager.cap = manager.engine.calibrate_laser(manager.cap)
    return {"status": "calibration triggered"}
