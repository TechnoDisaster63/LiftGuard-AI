"""
WiFi transport for the pan-tilt laser pointer — talks to an ESP32 over
HTTP instead of a USB-serial Arduino.

This subclasses the ORIGINAL ArduinoController unchanged. Every method that
matters — calibrate(), pixel_to_servo(), point_at_body_part(), the whole
BODY_POSITIONS map, the pan/tilt scaling math — is inherited as-is, because
all of it funnels through one place: self._send(command), which writes a
short plain-text command ("L1", "L0", "P90", "T139", "C", "B3") to
self.serial. Override just three methods — connect(), disconnect(), and
_send() — and the entire rest of the class works over WiFi with zero
duplicated logic.

Matches the same command protocol the USB firmware expects, so a single
ESP32 sketch (see firmware/liftguard_wifi_laser/liftguard_wifi_laser.ino)
can serve both: parse the query string the same way the USB firmware
parses serial bytes.
"""
from __future__ import annotations

import time
import urllib.request
import urllib.parse

from .arduino_controller import ArduinoController


class WifiArduinoController(ArduinoController):
    def __init__(self, host: str, timeout: float = 0.35):
        super().__init__()
        self.host = host.strip()
        self.timeout = timeout
        # self.serial stays None always — WiFi never uses it. self.port is
        # reused (set to the host/IP) purely so existing status code that
        # reads controller.port for display keeps working unchanged.

    def _base_url(self) -> str:
        host = self.host
        if not host.startswith("http://") and not host.startswith("https://"):
            host = f"http://{host}"
        return host.rstrip("/")

    def connect(self, host: str | None = None) -> bool:
        if host:
            self.host = host.strip()
        try:
            req = urllib.request.Request(f"{self._base_url()}/ping")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    self.connected = False
                    return False
            self.connected = True
            self.port = self.host  # reused field, now holds the IP/hostname
            self.center()
            time.sleep(0.1)
            print(f"WiFi laser connected at {self.host}")
            return True
        except Exception as e:
            print(f"WiFi laser connection error: {e}")
            self.connected = False
            return False

    def disconnect(self):
        if self.connected:
            try:
                self.laser_off()
                self.center()
            except Exception:
                pass
        self.connected = False
        print("WiFi laser disconnected")

    def _send(self, command: str):
        """Same semantics as the USB version: fire-and-forget, short
        timeout so a dropped WiFi packet never stalls the frame loop (the
        USB version has the equivalent risk with a wedged serial port,
        same tradeoff, just a different failure mode)."""
        if not self.connected:
            return None
        try:
            qs = urllib.parse.urlencode({"c": command})
            req = urllib.request.Request(f"{self._base_url()}/cmd?{qs}")
            with urllib.request.urlopen(req, timeout=self.timeout):
                return True
        except Exception:
            return None
