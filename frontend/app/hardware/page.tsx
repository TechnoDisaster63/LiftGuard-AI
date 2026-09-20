"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Zap, ZapOff, Crosshair, Usb, Wifi, Cable } from "lucide-react";
import clsx from "clsx";
import { api, ArduinoStatus } from "@/lib/api";
import { Card, CardEyebrow } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";

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

  if (activeSessions.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<Cable size={22} strokeWidth={1.5} />}
          message="No active sessions — the laser connects per live session."
          actionLabel="Start one from Live Analysis"
          actionHref="/live"
        />
      </Card>
    );
  }

  return (
    <div className="space-y-6 max-w-lg">
      <Card className="p-4 flex items-center gap-3">
        <CardEyebrow>Session</CardEyebrow>
        <select
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
          className="bg-panel-raised border border-border rounded-control px-3 py-1.5 text-sm text-ink font-mono focus:outline-none focus:border-brand/40"
        >
          {activeSessions.map((id) => (
            <option key={id} value={id}>
              {id.slice(0, 8)}…
            </option>
          ))}
        </select>
      </Card>

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <Card>
          <div className="flex items-center gap-3 mb-6">
            <div
              className={clsx(
                "w-11 h-11 rounded-control grid place-items-center shrink-0",
                status?.connected ? "bg-brand/10 border border-brand/25" : "bg-panel-raised border border-border"
              )}
            >
              {status?.connected ? (
                <Zap size={20} className="text-brand" />
              ) : (
                <ZapOff size={20} className="text-ink-faint" />
              )}
            </div>
            <div className="flex-1">
              <p className="font-display text-lg">
                {status?.connected ? "Laser Connected" : "Laser Disconnected"}
              </p>
              <p className="text-[11px] font-mono text-ink-faint">
                {status?.connected ? status.port : "no active connection"}
              </p>
            </div>
            {status?.connected && (
              <Badge tone="brand">{status.transport.toUpperCase()}</Badge>
            )}
          </div>

          {!status?.connected && (
            <>
              <div className="flex gap-2 mb-4">
                <button
                  onClick={() => setTransport("usb")}
                  className={clsx(
                    "press-scale flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-control border text-sm transition-colors",
                    transport === "usb"
                      ? "border-brand/40 bg-brand/10 text-brand"
                      : "border-border text-ink-muted hover:text-ink"
                  )}
                >
                  <Usb size={15} /> USB
                </button>
                <button
                  onClick={() => setTransport("wifi")}
                  className={clsx(
                    "press-scale flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-control border text-sm transition-colors",
                    transport === "wifi"
                      ? "border-brand/40 bg-brand/10 text-brand"
                      : "border-border text-ink-muted hover:text-ink"
                  )}
                >
                  <Wifi size={15} /> WiFi
                </button>
              </div>

              {transport === "usb" ? (
                <p className="text-xs text-ink-faint mb-4">
                  Auto-detects the Arduino&apos;s COM port — same as the desktop app.
                </p>
              ) : (
                <input
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="192.168.1.42 or liftguard-laser.local"
                  className="w-full mb-4 bg-panel-raised border border-border rounded-control px-3 py-2 text-sm text-ink placeholder:text-ink-faint font-mono focus:outline-none focus:border-brand/40"
                />
              )}

              {error && (
                <div className="rounded-control border border-risk-high/30 bg-risk-high/5 px-3 py-2 text-xs text-risk-high mb-4">
                  {error}
                </div>
              )}
            </>
          )}

          <div className="flex gap-3">
            <Button
              variant="secondary"
              onClick={status?.connected ? disconnect : connect}
              disabled={busy}
              className="flex-1 justify-center"
            >
              {status?.connected ? "Disconnect" : `Connect via ${transport.toUpperCase()}`}
            </Button>
            <Button
              variant="outline-brand"
              onClick={calibrate}
              disabled={busy || !status?.connected}
              className="flex-1 justify-center"
            >
              <Crosshair size={15} /> Calibrate
            </Button>
          </div>
        </Card>
      </motion.div>

      <Card>
        <p className="text-xs text-ink-faint">
          WiFi mode talks to an ESP32 running the firmware in{" "}
          <code className="font-mono">firmware/liftguard_wifi_laser/</code> — same pan/tilt/
          laser command protocol as the USB Arduino, just delivered over HTTP instead of a
          serial port.
        </p>
      </Card>
    </div>
  );
}
