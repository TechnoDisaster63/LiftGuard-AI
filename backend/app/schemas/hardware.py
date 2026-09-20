from __future__ import annotations
from typing import Optional, Literal
from pydantic import BaseModel


class ArduinoStatus(BaseModel):
    connected: bool
    port: Optional[str] = None  # COM port for USB, host/IP for WiFi
    laser_on: bool = False
    transport: Literal["usb", "wifi", "none"] = "none"


class ArduinoConnectResponse(BaseModel):
    connected: bool
    port: Optional[str] = None
    transport: Literal["usb", "wifi", "none"] = "none"
    message: str


class LaserConnectRequest(BaseModel):
    transport: Literal["usb", "wifi"]
    host: Optional[str] = None   # required when transport == "wifi"
    port: Optional[str] = None   # optional explicit COM port when transport == "usb"
