"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ArduinoStatus } from "@/lib/api";
import { Alert, Segmented, Spinner } from "@/components/lg/ui";

export default function HardwarePage() {
  const [activeSessions, setActiveSessions] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState<string>("");
  const [status, setStatus] = useState<ArduinoStatus | null>(null);
  const [transport, setTransport] = useState<"usb" | "wifi">("usb");
  const [host, setHost] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.sessions.list().then((r) => {
      setActiveSessions(r.active_sessions);
      if (r.active_sessions.length > 0) setSessionId(r.active_sessions[0]);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    api.hardware.status(sessionId).then(setStatus).catch(() => setStatus(null));
  }, [sessionId]);

  const refreshStatus = async () => {
    if (!sessionId) return;
    const s = await api.hardware.status(sessionId).catch(() => null);
    if (s) setStatus(s);
  };

  const connect = async () => {
    if (!sessionId) return;
    if (transport === "wifi" && !host.trim()) {
      setError("Enter the ESP32's IP address or hostname (e.g. 192.168.1.42 or liftguard-laser.local)");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.hardware.connect(sessionId, transport, transport === "wifi" ? { host: host.trim() } : undefined);
      await refreshStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't connect");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!sessionId) return;
    setBusy(true);
    await api.hardware.disconnect(sessionId).catch(() => {});
    await refreshStatus();
    setBusy(false);
  };

  const calibrate = async () => {
    if (!sessionId) return;
    setBusy(true);
    await api.hardware.calibrate(sessionId).catch(() => {});
    setBusy(false);
  };

  const connected = !!status?.connected;
  return (
    <div className="lg-fade grid gap-10" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)" }}>
      <div>
        <div className="lg-m lg-dim">Laser pointer · Arduino or ESP32 pan-tilt</div>
        <div className="lg-d mt-1.5" style={{ fontSize: 120, color: activeSessions.length === 0 ? "var(--lg-faint)" : connected ? "var(--lg-mint)" : "var(--lg-ink)" }}>
          {activeSessions.length === 0 ? "No session" : connected ? "Connected" : "Not connected"}
        </div>
        <p className="lg-dim mt-4" style={{ fontSize: 16, maxWidth: 520, lineHeight: 1.45 }}>
          {activeSessions.length === 0
            ? "The laser connects per live session. Start a session, then come back here to connect it."
            : connected
              ? `Talking to the laser on ${status?.port ?? "an unknown port"} over ${status?.transport.toUpperCase()}.`
              : "Plug the Arduino in over USB, or point this at an ESP32 on the same WiFi."}
        </p>
        {activeSessions.length === 0 && (
          <Link href="/live" className="lg-btn lg mt-6">
            Go to Live
          </Link>
        )}
        <p className="lg-faint mt-10" style={{ fontSize: 13, maxWidth: 520 }}>
          WiFi mode talks to an ESP32 running firmware/liftguard_wifi_laser/, with the same pan, tilt and laser commands as the USB Arduino.
        </p>
      </div>
      {activeSessions.length > 0 && (
        <div>
          <div className="lg-row flex items-center justify-between py-5">
            <div className="lg-d" style={{ fontSize: 42 }}>
              Session
            </div>
            <select
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              aria-label="Session"
              className="lg-m"
              style={{ background: "var(--lg-p2)", color: "var(--lg-ink)", border: "none", borderRadius: 10, padding: "10px 12px" }}
            >
              {activeSessions.map((id) => (
                <option key={id} value={id}>
                  {id.slice(0, 8)}
                </option>
              ))}
            </select>
          </div>
          {!connected && (
            <>
              <div className="lg-row flex items-center justify-between py-5">
                <div>
                  <div className="lg-d" style={{ fontSize: 42 }}>
                    Connection
                  </div>
                  <div className="lg-dim mt-1.5" style={{ fontSize: 14 }}>
                    {transport === "usb" ? "Finds the Arduino's port automatically." : "ESP32 IP address or hostname."}
                  </div>
                </div>
                <Segmented label="Connection" options={["USB", "WiFi"]} value={transport === "usb" ? 0 : 1} onChange={(i) => setTransport(i === 0 ? "usb" : "wifi")} />
              </div>
              {transport === "wifi" && (
                <input
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="192.168.1.42 or liftguard-laser.local"
                  aria-label="ESP32 address"
                  className="lg-input lg-m mb-4"
                  style={{ fontSize: 16, textTransform: "none", letterSpacing: 0 }}
                />
              )}
            </>
          )}
          {error && (
            <div className="my-4">
              <Alert>{error}</Alert>
            </div>
          )}
          <div className="flex gap-3 mt-6">
            <button className="lg-btn lg" onClick={connected ? disconnect : connect} disabled={busy}>
              {busy ? <Spinner /> : null}
              {connected ? "Disconnect" : `Connect over ${transport === "usb" ? "USB" : "WiFi"}`}
            </button>
            <button className="lg-btn g lg" onClick={calibrate} disabled={busy || !connected} title={connected ? "Re-centre the pan-tilt" : "Connect the laser first"}>
              Calibrate
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
