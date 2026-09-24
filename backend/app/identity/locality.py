"""Is this request from a browser on the same machine as the backend?

Face data (camera frames sent for enrollment or identification) is only
accepted when the answer is yes, so "your face never leaves this device" stays
true: the frames travel from the browser to a backend on the same computer and
nowhere else. A browser on a phone reaching a laptop, a Codespace, or a tunnel
is refused.

Rules, all required:
- the TCP peer is a loopback address;
- no X-Forwarded-For / Forwarded chain naming a non-loopback client
  (the local Next.js proxy in start.sh adds loopback entries, which pass);
- X-Forwarded-Host, when present, is localhost/127.0.0.1/[::1];
- the browser's Origin (or Referer), when present, is a localhost URL.
  Browsers set Origin themselves; page scripts cannot change it.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}

NOT_LOCAL_DETAIL = (
    "Face ID only works when the browser runs on the same computer as LiftGuard, "
    "so your face never leaves that device. Open LiftGuard on that computer "
    "(http://localhost:3000) to enroll or identify."
)


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    host = host.strip().strip('"').strip("[]")
    if host.lower() == "localhost":
        return True
    if host.lower().startswith("for="):
        host = host[4:].strip('"').strip("[]")
    # drop a port from "1.2.3.4:5678" (not from bare IPv6)
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _host_of(url_or_host: str) -> str:
    v = url_or_host.strip()
    if "://" not in v:
        v = "//" + v
    return (urlsplit(v).hostname or "").lower()


def is_local_request(request: Request) -> bool:
    client = request.client.host if request.client else None
    if not _is_loopback(client):
        return False
    h = request.headers
    for entry in h.get("x-forwarded-for", "").split(","):
        if entry.strip() and not _is_loopback(entry):
            return False
    for part in h.get("forwarded", "").split(","):
        for kv in part.split(";"):
            if kv.strip().lower().startswith("for=") and not _is_loopback(kv.strip()):
                return False
    for name in ("x-forwarded-host", "origin", "referer"):
        value = h.get(name)
        if value and value != "null" and _host_of(value.split(",")[0]) not in LOCAL_HOSTNAMES:
            return False
    return True


def require_local(request: Request) -> None:
    """FastAPI dependency for every endpoint that receives face frames."""
    if not is_local_request(request):
        raise HTTPException(status_code=403, detail=NOT_LOCAL_DETAIL)
