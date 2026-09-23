"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, API_KEY } from "./api";

export interface UserTelemetry {
  display_name: string | null;
  user_id: number | null;
  total_sessions: number | null;
  last_seen: string | null;
  is_guest: boolean;
}

export interface TelemetryPayload {
  risk_label: string | null;
  risk_level: number | null;
  confidence: number | null;
  uncertainty: number | null;
  uncertainty_category: string | null;
  risk_mode: string | null;
  spine_flexion: number | null;
  hip_hinge_angle: number | null;
  stability_index: number | null;
  fatigue_score: number | null;
  fatigue_alert: string | null;
  lifts_completed: number | null;
  injury_risk: number | null;
  injury_acute: number | null;
  injury_cumulative: number | null;
  injury_category: string | null;
  injury_ci_text: string | null;
  using_iri_v2: boolean;
  exercise_status: Record<string, unknown>;
  corrections: unknown[];
  feedback_message: string | null;
  user: UserTelemetry | null;
  id_state: string;
  camera_id: number | string;
  voice_enabled: boolean;
  voice_speaking: boolean;
  arduino_connected: boolean;
  arduino_calibrated: boolean;
  mirror_mode: boolean;
  calibration_mode: boolean;
  using_temporal: boolean;
  process_every_n: number;
  fps: number | null;
  frame_count: number;
}

export interface ToastMessage {
  id: string;
  text: string;
  tone: "info" | "error";
}

type ConnectionState = "idle" | "connecting" | "open" | "closed" | "error";

/**
 * Drives ws://.../ws/live/{sessionId}. The backend pushes {type:"frame"},
 * {type:"telemetry"}, and — new — {type:"control_ack"}/{type:"error"}
 * after each control message, so button presses get real feedback instead
 * of a silent no-op (the original app's controls only printed to a
 * console the web user never sees).
 */
export function useLiveSession(sessionId: string | null) {
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetryPayload | null>(null);
  const [state, setState] = useState<ConnectionState>("idle");
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  // Set when the stream ends for a reason the user must see (camera lost,
  // video file finished, engine error). Not cleared by toasts.
  const [fatalError, setFatalError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const lastObjectUrl = useRef<string | null>(null);
  // Controls someone is awaiting (requestControl): their ack resolves the
  // promise instead of showing a toast.
  const pending = useRef(new Map<string, (message: string) => void>());

  const pushToast = useCallback((text: string, tone: "info" | "error" = "info") => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((prev) => [...prev.slice(-3), { id, text, tone }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3200);
  }, []);

  useEffect(() => {
    // New or ended session: drop the previous session's last frame and
    // numbers so a stopped session doesn't look live.
    setTelemetry(null);
    setFrameUrl(null);
    if (!sessionId) {
      setState("idle");
      return;
    }

    const wsBase = API_BASE.replace(/^http/, "ws");
    const url = new URL(`${wsBase}/ws/live/${sessionId}`);
    if (API_KEY) url.searchParams.set("token", API_KEY);
    const ws = new WebSocket(url);
    wsRef.current = ws;
    setState("connecting");
    setFatalError(null);
    let closedByUs = false;

    ws.onopen = () => setState("open");
    ws.onerror = () => setState("error");
    ws.onclose = (event) => {
      setState("closed");
      if (closedByUs) return;
      if (event.code === 4401) {
        setFatalError("The backend refused the live stream: wrong or missing API key.");
      } else if (event.code === 4404) {
        setFatalError("The backend no longer has this session (it was stopped or the backend restarted).");
      } else if (event.code === 4429) {
        setFatalError("This session is already open in another tab or window.");
      } else if (event.code === 1006) {
        setFatalError("Lost the connection to the backend. Is it still running?");
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string);
        if (msg.type === "frame") {
          const bytes = atob(msg.data);
          const arr = new Uint8Array(bytes.length);
          for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
          const blob = new Blob([arr], { type: "image/jpeg" });
          const url = URL.createObjectURL(blob);
          if (lastObjectUrl.current) URL.revokeObjectURL(lastObjectUrl.current);
          lastObjectUrl.current = url;
          setFrameUrl(url);
        } else if (msg.type === "telemetry") {
          setTelemetry(msg as TelemetryPayload);
        } else if (msg.type === "control_ack") {
          const waiter = pending.current.get(msg.action);
          if (waiter) {
            pending.current.delete(msg.action);
            waiter(String(msg.message ?? ""));
          } else pushToast(msg.message, "info");
        } else if (msg.type === "error") {
          if (msg.fatal) setFatalError(msg.message);
          else pushToast(msg.message, "error");
        }
      } catch {
        // ignore malformed frame — next message will self-correct
      }
    };

    return () => {
      closedByUs = true;
      ws.close();
      if (lastObjectUrl.current) URL.revokeObjectURL(lastObjectUrl.current);
    };
  }, [sessionId, pushToast]);

  const sendControl = useCallback((action: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action }));
    }
  }, []);

  /** Send a control and wait for the backend's answer (no toast). Rejects after timeoutMs. */
  const requestControl = useCallback((action: string, timeoutMs = 10000) => {
    return new Promise<string>((resolve, reject) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        reject(new Error("The live connection isn't open"));
        return;
      }
      const timer = setTimeout(() => {
        pending.current.delete(action);
        reject(new Error("No answer from the backend"));
      }, timeoutMs);
      pending.current.set(action, (message) => {
        clearTimeout(timer);
        resolve(message);
      });
      ws.send(JSON.stringify({ action }));
    });
  }, []);

  return { frameUrl, telemetry, state, sendControl, requestControl, toasts, fatalError };
}
