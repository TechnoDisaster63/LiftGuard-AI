/*
  LiftGuard AI — WiFi Pan-Tilt Laser Pointer (ESP32)
  ====================================================
  Speaks the EXACT SAME command protocol app/hardware/arduino_controller.py
  already sends over USB serial — just delivered over HTTP instead of a
  COM port, so app/hardware/wifi_arduino_controller.py's Python-side logic
  (calibration math, pixel_to_servo, point_at_body_part, BODY_POSITIONS)
  needed zero changes to work with this.

  Protocol (single command per request, in the "c" query param):
    L1        laser on
    L0        laser off
    B<n>      blink n times (n omitted defaults to 3)
    P<angle>  set pan servo,  0-180
    T<angle>  set tilt servo, 0-180
    C         center (DEFAULT_PAN, DEFAULT_TILT below — keep these in sync
              with ArduinoController.DEFAULT_PAN / DEFAULT_TILT in
              app/hardware/arduino_controller.py)

  Endpoints:
    GET /ping        -> "OK"   (connect() health check)
    GET /cmd?c=P90    -> "OK"   (runs one command)

  Hardware (matches the block diagram: ESP32 + Battery + 2x SG90 + Laser):
    Pan servo  signal -> GPIO 13
    Tilt servo signal -> GPIO 12
    Laser module       -> GPIO 14 (through a transistor/MOSFET if the
                          laser draws more current than a GPIO can source —
                          most small laser diode modules are fine direct)
    Servos + laser share the battery's ground with the ESP32 (common ground)
    Servos are powered from the battery directly, NOT from the ESP32's 5V
    pin, unless your battery/BEC can supply both comfortably — SG90 stall
    current can brown out the ESP32 if shared carelessly.

  Libraries (Arduino IDE -> Tools -> Manage Libraries):
    - ESP32Servo (madhephaestus/ESP32Servo)
    (WiFi.h and WebServer.h ship with the ESP32 Arduino core)

  Setup:
    1. Fill in WIFI_SSID / WIFI_PASSWORD below — same network the laptop's
       WiFi Router/Hotspot from the diagram is on.
    2. Flash this to the ESP32 (Board: "ESP32 Dev Module" or your specific
       board).
    3. Open Serial Monitor at 115200 baud — it prints the IP address once
       connected. That's the `host` value the LiftGuard AI web dashboard's
       Hardware page asks for when you choose WiFi transport.
    4. Optional: set up mDNS (below, enabled by default) so you can use
       liftguard-laser.local instead of a raw IP.
*/

#include <WiFi.h>
#include <WebServer.h>
#include <ESP32Servo.h>
#include <ESPmDNS.h>

// ── WiFi credentials ─────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* MDNS_NAME     = "liftguard-laser";  // -> liftguard-laser.local

// ── Pins ──────────────────────────────────────────────────────
const int PAN_PIN   = 13;
const int TILT_PIN  = 12;
const int LASER_PIN = 14;

// ── Defaults — keep in sync with arduino_controller.py ───────
const int DEFAULT_PAN  = 108;
const int DEFAULT_TILT = 139;

Servo panServo;
Servo tiltServo;
WebServer server(80);

bool laserState = false;

void setLaser(bool on) {
  laserState = on;
  digitalWrite(LASER_PIN, on ? HIGH : LOW);
}

void blinkLaser(int times) {
  bool wasOn = laserState;
  for (int i = 0; i < times; i++) {
    setLaser(true);
    delay(80);
    setLaser(false);
    delay(80);
  }
  setLaser(wasOn);
}

void centerServos() {
  panServo.write(DEFAULT_PAN);
  tiltServo.write(DEFAULT_TILT);
}

// Parses and runs ONE command — same grammar as the USB serial firmware.
void runCommand(const String& cmd) {
  if (cmd.length() == 0) return;

  char type = cmd.charAt(0);
  String arg = cmd.substring(1);

  switch (type) {
    case 'L':
      setLaser(arg == "1");
      break;
    case 'B': {
      int n = arg.length() ? arg.toInt() : 3;
      blinkLaser(n);
      break;
    }
    case 'P': {
      int angle = constrain(arg.toInt(), 0, 180);
      panServo.write(angle);
      break;
    }
    case 'T': {
      int angle = constrain(arg.toInt(), 0, 180);
      tiltServo.write(angle);
      break;
    }
    case 'C':
      centerServos();
      break;
    default:
      // unknown command — ignore, matches the permissive USB firmware
      break;
  }
}

void handlePing() {
  server.send(200, "text/plain", "OK");
}

void handleCmd() {
  if (!server.hasArg("c")) {
    server.send(400, "text/plain", "missing c param");
    return;
  }
  runCommand(server.arg("c"));
  server.send(200, "text/plain", "OK");
}

void setup() {
  Serial.begin(115200);

  pinMode(LASER_PIN, OUTPUT);
  setLaser(false);

  panServo.attach(PAN_PIN);
  tiltServo.attach(TILT_PIN);
  centerServos();

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Connected. IP address: ");
  Serial.println(WiFi.localIP());

  if (MDNS.begin(MDNS_NAME)) {
    Serial.print("mDNS ready: http://");
    Serial.print(MDNS_NAME);
    Serial.println(".local");
  }

  server.on("/ping", HTTP_GET, handlePing);
  server.on("/cmd", HTTP_GET, handleCmd);
  server.begin();
  Serial.println("HTTP server started");
}

void loop() {
  server.handleClient();
}
