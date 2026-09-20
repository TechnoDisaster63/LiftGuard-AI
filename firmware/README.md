# LiftGuard AI — WiFi Pan-Tilt Laser Firmware

Flash this onto an ESP32 to use WiFi transport instead of a USB-tethered Arduino, matching
the "Wireless Pan-Tilt Laser Pointer" box in the architecture diagram.

## What this is

A tiny HTTP server that speaks the exact command protocol
`backend/app/hardware/arduino_controller.py` already sends over USB serial — `L1`/`L0`
(laser), `P<angle>`/`T<angle>` (pan/tilt), `C` (center), `B<n>` (blink). Only the transport
changed (WiFi HTTP GET instead of a serial line); the command grammar is identical, so
`backend/app/hardware/wifi_arduino_controller.py` reuses 100% of the original Python
calibration/pointing logic.

## Hardware

- ESP32 dev board
- 2x SG90 micro servos (pan + tilt)
- Small laser diode module
- Battery pack (servos + laser draw more current than the ESP32 can source alone — power
  them from the battery directly, common ground with the ESP32)

| Component | ESP32 Pin |
|---|---|
| Pan servo signal | GPIO 13 |
| Tilt servo signal | GPIO 12 |
| Laser module | GPIO 14 |

## Libraries

Arduino IDE → Tools → Manage Libraries → install **ESP32Servo** (by madhephaestus).
`WiFi.h`, `WebServer.h`, `ESPmDNS.h` ship with the ESP32 board core already.

## Flashing

1. Open `liftguard_wifi_laser.ino` in the Arduino IDE.
2. Set `WIFI_SSID`/`WIFI_PASSWORD` to the same network your laptop (running the LiftGuard AI
   backend) is on.
3. Board: your specific ESP32 dev board (or "ESP32 Dev Module" as a safe default).
4. Upload.
5. Open Serial Monitor at 115200 baud — it prints the IP once connected, e.g.
   `192.168.1.42`. That's the `host` you'll enter on the Hardware page when choosing WiFi
   transport. mDNS is also enabled (`liftguard-laser.local`) if your network supports it.

## Testing without the dashboard

```bash
curl http://192.168.1.42/ping                 # should return OK
curl "http://192.168.1.42/cmd?c=L1"            # laser on
curl "http://192.168.1.42/cmd?c=P90"           # pan to 90°
curl "http://192.168.1.42/cmd?c=C"             # center
```

## Not tested against real hardware

Written to match the protocol exactly, but there's no physical ESP32/servo rig in the
sandbox this was built in to flash and verify against. Budget time to check servo angle
directions match `arduino_controller.py`'s `invert_pan` assumption, and the `DEFAULT_PAN`/
`DEFAULT_TILT` constants match your physical mounting before trusting `calibrate()`.
