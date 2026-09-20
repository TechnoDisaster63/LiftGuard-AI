"""API-key auth and ESP32 host validation.

Deliberately stdlib + FastAPI only - no CV/ML imports - so the web layer
(and its test suite) loads without opencv/mediapipe/torch installed.
"""
from __future__ import annotations

import ipaddress
import re

from fastapi import HTTPException, Request, WebSocket, status

from .config import settings

_HOST_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_api_key(request: Request) -> None:
    """FastAPI dependency for REST routers.

    No-op while LIFTGUARD_API_KEY is unset (open localhost development
    mode). Once a key is configured, every REST route requires
    `Authorization: Bearer <key>`.
    """
    if not settings.API_KEY:
        return
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or token != settings.API_KEY:
        raise _unauthorized()


def check_ws_api_key(websocket: WebSocket) -> bool:
    """WebSocket variant of require_api_key.

    Browsers cannot set headers on WebSocket handshakes, so the dashboard
    passes the same key as `?token=`. Returns True when the connection may
    proceed; the caller closes the socket otherwise.
    """
    if not settings.API_KEY:
        return True
    return websocket.query_params.get("token") == settings.API_KEY


def validate_esp32_host(host: str) -> str:
    """Normalize and validate the user-supplied ESP32 target.

    The backend issues an HTTP request to whatever host is passed to
    /api/hardware/{id}/connect, so an unrestricted value would let anyone
    who can reach the API turn the server into an internal-network request
    proxy. Rules:
      * an explicit allowlist (LIFTGUARD_ESP32_ALLOWED_HOSTS) wins;
      * otherwise the host must be a private/loopback/link-local IP, or a
        local hostname (single label or *.local mDNS);
      * credentials, ports, and non-default URL parts are rejected.
    Returns the bare host on success; raises ValueError otherwise.
    """
    if not host or not host.strip():
        raise ValueError("host is required")
    h = host.strip()
    h = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", h)
    h = h.split("/")[0].split("?")[0]
    if "@" in h:
        raise ValueError("host must not contain credentials")
    if ":" in h:
        raise ValueError("host must not include a port")
    if not h:
        raise ValueError("host is required")

    if settings.ESP32_ALLOWED_HOSTS:
        if h in settings.ESP32_ALLOWED_HOSTS:
            return h
        raise ValueError("host is not in LIFTGUARD_ESP32_ALLOWED_HOSTS")

    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return h
        raise ValueError("ESP32 host must be a private-network address")

    labels = h.split(".")
    if len(labels) > 2 or (len(labels) == 2 and labels[1].lower() != "local"):
        raise ValueError("only local (.local or single-label) hostnames are allowed")
    if not all(_HOST_LABEL.match(label) for label in labels):
        raise ValueError("invalid hostname")
    return h
