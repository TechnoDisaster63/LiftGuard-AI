"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { otherCameras, rememberCamera, startWithCamera } from "@/lib/camera";
import { useLiveSession, type TelemetryPayload } from "@/lib/ws";
import { unlockVoice, useVoiceCues, useVoiceSetting } from "@/lib/voice";
import { openDeviceCamera, stopDeviceCamera, useFrameUplink } from "@/lib/deviceCamera";
import { Alert, FLAG_CUE, Spinner } from "@/components/lg/ui";

type StageState = "idle" | "counting" | "clean" | "flagged" | "fatigue";
type LastRep = { rep?: number; form_flags?: string[] } | null;

// How long a rep's result owns the screen: a clean rep flashes, a flagged
// rep holds until the next rep starts going down.
const CLEAN_HOLD_MS = 1600;
const REP_PRIORITY_MS = 2500;

function readStatus(t: TelemetryPayload | null) {
  const s = (t?.exercise_status ?? {}) as Record<string, unknown>;
  const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const fi = (t as unknown as { fatigue_indicator?: { signals?: Record<string, number> } } | null)?.fatigue_indicator ?? null;
  return {
    repCount: num(s.rep_count) ?? 0,
    warmingUp: !t || s.calibration_mode === undefined || s.calibration_mode === "WARMING_UP",
    phase: typeof s.phase === "string" ? s.phase : "idle",
    knee: num(s.knee_angle),
    bottom: num(s.bottom_knee_deg),
    standing: num(s.standing_knee_deg),
    lastRep: (s.last_rep ?? null) as LastRep,
    fatigueScore: t?.fatigue_score ?? null,
    fatigueStatus: t?.fatigue_alert ?? null,
    durationDrift: fi?.signals?.rep_duration_drift_pct ?? null,
  };
}

const KEY_HELP: [string, string][] = [
  ["Space", "Stop and save"],
  ["V", "Voice cues on / off"],
  ["K", "Switch to the next camera"],
  ["M", "Mirror the camera"],
  ["C", "Recalibrate depth"],
  ["R", "Reset the rep count"],
  ["Esc", "Menu: laser, speed, camera, export"],
];

const LEGEND: [string, string, string][] = [
  ["var(--lg-idle)", "Grey, dashed frame", "Learning your depth: do 3 slow squats"],
  ["var(--lg-ink)", "White frame", "Counting"],
  ["var(--lg-mint)", "Mint flash", "Clean rep"],
  ["var(--lg-amber)", "Amber, holds", "Rep flagged, with a short command"],
  ["var(--lg-mag)", "Magenta pulse", "Fatigue indicator elevated"],
];

function LiveInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [trying, setTrying] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedSessionId, setSavedSessionId] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const { frameUrl, telemetry, state, sendControl, sendFrame, requestControl, toasts, fatalError } = useLiveSession(sessionId);
  // Set while a session analyses this device's camera (streamed from the
  // browser) instead of a camera on the backend machine.
  const [deviceStream, setDeviceStream] = useState<MediaStream | null>(null);
  const deviceStreamRef = useRef<MediaStream | null>(null);
  deviceStreamRef.current = deviceStream;
  const deviceMode = deviceStream !== null;
  useFrameUplink(deviceStream, sendFrame, state === "open");
  // The session ended (stopped, lost, or never started): turn the camera light off.
  useEffect(() => {
    if (!sessionId && !starting && deviceStream) {
      stopDeviceCamera(deviceStream);
      setDeviceStream(null);
    }
  }, [sessionId, starting, deviceStream]);
  useEffect(() => () => stopDeviceCamera(deviceStreamRef.current), []);
  // One-tap camera switch: cycle to the next camera that actually sends video.
  const [camStatus, setCamStatus] = useState<{ text: string; busy: boolean; tone?: "ok" | "warn" } | null>(null);
  const switchingRef = useRef(false);
  const switchCamera = useCallback(async () => {
    if (switchingRef.current) return;
    switchingRef.current = true;
    const current = Number(telemetry?.camera_id ?? 0);
    const order = otherCameras(Number.isFinite(current) ? current : 0);
    let found: number | null = null;
    try {
      for (let i = 0; i < order.length; i++) {
        setCamStatus({ text: i === 0 ? "Looking for another camera" : `Looking for another camera · try ${i + 1} of ${order.length}`, busy: true });
        const msg = await requestControl(`switch_camera:${order[i]}`).catch(() => "");
        if (msg.startsWith("Switched")) {
          found = order[i];
          break;
        }
      }
    } finally {
      switchingRef.current = false;
    }
    if (found !== null) {
      rememberCamera(found);
      setCamStatus({ text: `Camera ${found} found`, busy: false, tone: "ok" });
    } else {
      setCamStatus({ text: "No other camera found · staying on this one", busy: false, tone: "warn" });
    }
    setTimeout(() => setCamStatus((s) => (s && !s.busy ? null : s)), 3000);
  }, [telemetry?.camera_id, requestControl]);

  const handleStart = useCallback(async () => {
    if (starting || sessionId) return;
    unlockVoice(); // still inside the click / key press, so speech is allowed later
    setStarting(true);
    setError(null);
    setSavedSessionId(null);
    try {
      // Zero choices: find the camera that actually sends video.
      const res = await startWithCamera((_index, attempt, total) =>
        setTrying(attempt === 1 ? "Looking for your camera" : `Looking for your camera · try ${attempt} of ${total}`)
      );
      setSessionId(res.sessionId);
    } catch (e) {
      // The backend's message already says what went wrong and what to check.
      setError(e instanceof Error && /^(No camera found|Camera \d)/.test(e.message) ? e.message : `Couldn't start the session. ${e instanceof Error ? e.message : ""}`.trim());
    } finally {
      setStarting(false);
      setTrying(null);
    }
  }, [starting, sessionId]);

  const handleStartDevice = useCallback(async () => {
    if (starting || sessionId) return;
    unlockVoice();
    setStarting(true);
    setError(null);
    setSavedSessionId(null);
    let stream: MediaStream | null = null;
    try {
      setTrying("Asking for camera permission");
      stream = await openDeviceCamera();
      setTrying("Camera on · starting the analysis");
      const res = await api.sessions.start({ camera_id: "browser", voice_enabled: false });
      setDeviceStream(stream);
      setSessionId(res.session_id);
    } catch (e) {
      stopDeviceCamera(stream);
      const msg = e instanceof Error ? e.message : "";
      setError(stream ? `Couldn't start the session. ${msg}`.trim() : msg);
    } finally {
      setStarting(false);
      setTrying(null);
    }
  }, [starting, sessionId]);

  const stopSession = useCallback(async (id: string) => {
    setStopping(true);
    setMenuOpen(false);
    try {
      await api.sessions.stop(id);
      setSavedSessionId(id);
    } catch (e) {
      // 404: the backend already dropped it (e.g. restarted) - nothing to save.
      setError(`The session stopped, but it may not have been saved. ${e instanceof Error ? e.message : ""}`.trim());
    } finally {
      setSessionId(null);
      setStopping(false);
    }
  }, []);

  const handleStop = useCallback(() => {
    if (sessionId && !stopping) void stopSession(sessionId);
  }, [sessionId, stopping, stopSession]);

  // Camera lost / video finished / engine error: show why, and stop the
  // session so the camera is freed and what was recorded is saved.
  useEffect(() => {
    if (fatalError && sessionId) {
      setError(fatalError);
      void stopSession(sessionId);
    }
  }, [fatalError, sessionId, stopSession]);

  // /live?start=1 (from Home) starts straight away.
  const autostarted = useRef(false);
  useEffect(() => {
    if (params.get("start") === "1" && !autostarted.current) {
      autostarted.current = true;
      router.replace("/live");
      void handleStart();
    }
  }, [params, router, handleStart]);

  // ---- derived live state ----
  const st = readStatus(telemetry);
  const { voiceOn, toggleVoice } = useVoiceSetting();
  const manualCalNow = telemetry?.calibration_mode ?? false;
  const voiceStatus = useMemo(
    () => (telemetry && sessionId ? { warmingUp: st.warmingUp, manualCal: manualCalNow, lastRep: st.lastRep, fatigueStatus: st.fatigueStatus } : null),
    [telemetry, sessionId]
  );
  useVoiceCues(voiceStatus, voiceOn);
  const [ledger, setLedger] = useState<{ rep: number; flagged: boolean }[]>([]);
  const [repAt, setRepAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const lastRepNo = st.lastRep?.rep ?? null;
  const lastFlags = useMemo(() => st.lastRep?.form_flags ?? [], [st.lastRep]);
  const flagKey = lastFlags.join(",");

  useEffect(() => {
    setLedger([]);
    setRepAt(0);
  }, [sessionId]);

  useEffect(() => {
    if (lastRepNo == null) return;
    setLedger((prev) => (prev.some((r) => r.rep === lastRepNo) ? prev : [...prev, { rep: lastRepNo, flagged: flagKey !== "" }]));
    setRepAt(Date.now());
  }, [lastRepNo, flagKey]);

  // Reset (R) drops the engine count to 0: clear the ledger too.
  useEffect(() => {
    if (st.repCount === 0 && lastRepNo == null) setLedger((prev) => (prev.length ? [] : prev));
  }, [st.repCount, lastRepNo]);

  useEffect(() => {
    if (!repAt) return;
    const a = setTimeout(() => setNow(Date.now()), CLEAN_HOLD_MS + 50);
    const b = setTimeout(() => setNow(Date.now()), REP_PRIORITY_MS + 50);
    return () => {
      clearTimeout(a);
      clearTimeout(b);
    };
  }, [repAt]);
  useEffect(() => setNow(Date.now()), [telemetry]);

  const sinceRep = repAt ? now - repAt : Infinity;
  const manualCal = telemetry?.calibration_mode ?? false;
  const elevated = st.fatigueStatus === "ELEVATED";
  let stage: StageState = "counting";
  if (!telemetry || st.warmingUp || manualCal) stage = "idle";
  else if (lastRepNo != null && lastFlags.length > 0 && (sinceRep < REP_PRIORITY_MS || !elevated)) stage = "flagged";
  else if (lastRepNo != null && sinceRep < CLEAN_HOLD_MS) stage = "clean";
  else if (elevated) stage = "fatigue";
  if (stage === "flagged" && sinceRep > REP_PRIORITY_MS && st.phase === "down") stage = elevated ? "fatigue" : "counting";

  const depthPct =
    st.knee != null && st.bottom != null && st.standing != null && st.standing > st.bottom
      ? Math.max(0, Math.min(100, ((st.standing - st.knee) / (st.standing - st.bottom)) * 100))
      : 0;

  // ---- keyboard: nothing to click mid-movement ----
  useEffect(() => {
    const typing = (e: KeyboardEvent) => e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement;
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || typing(e)) return;
      if (!sessionId) {
        if (e.code === "Space" && !starting) {
          e.preventDefault();
          void handleStart();
        }
        return;
      }
      const k = e.key.toLowerCase();
      if (e.code === "Space") {
        e.preventDefault();
        handleStop();
      } else if (k === "escape") setMenuOpen((m) => !m);
      else if (k === "v") toggleVoice();
      else if (k === "m") sendControl("toggle_mirror");
      else if (k === "c") sendControl(manualCal ? "complete_calibration" : "start_calibration");
      else if (k === "r") sendControl("reset_reps");
      else if (k === "k" && !deviceMode) void switchCamera();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sessionId, starting, handleStart, handleStop, sendControl, manualCal, switchCamera, deviceMode, toggleVoice]);

  // ---------------- READY (no session) ----------------
  if (!sessionId && !starting) {
    return (
      <div className="lg-fade grid gap-6" style={{ gridTemplateColumns: "minmax(0,1.35fr) minmax(0,1fr)", minHeight: "calc(100vh - 150px)" }}>
        <div className="relative rounded-[18px] overflow-hidden flex flex-col justify-end p-9" style={{ background: "radial-gradient(120% 90% at 20% 10%, #1c1c20, #0b0b0c)" }}>
          <div style={{ fontSize: 26, fontWeight: 600, maxWidth: 560, lineHeight: 1.2 }}>Real-time movement analysis for injury prevention.</div>
          <div className="lg-m lg-dim mt-2.5">Movement mode: squat · watches depth, trunk lean, range of motion</div>
          <div className="lg-d mt-3" style={{ fontSize: "clamp(120px, 17vw, 240px)" }}>
            Ready
          </div>
          <div className="flex gap-3 mt-5">
            <button className="lg-btn lg" onClick={handleStart}>
              Start session <kbd>Space</kbd>
            </button>
            <button className="lg-btn" onClick={handleStartDevice}>
              Use this device&apos;s camera
            </button>
          </div>
          <div className="lg-m lg-faint mt-3" style={{ fontSize: 11, maxWidth: 560 }}>
            Start session uses the camera on the LiftGuard computer. &ldquo;Use this device&apos;s camera&rdquo; streams the camera of the phone or laptop you&apos;re holding.
          </div>
        </div>
        <div className="flex flex-col gap-4">
          {error && <Alert>{error}</Alert>}
          {savedSessionId && (
            <div className="lg-card lg-fade">
              <div className="lg-m" style={{ color: "var(--lg-mint)" }}>
                ✓ Session saved
              </div>
              <div className="flex gap-2.5 mt-4">
                <Link className="lg-btn" href={`/reports?history=${savedSessionId}`}>
                  Open the report
                </Link>
                <Link className="lg-btn g" href="/sessions">
                  All sessions
                </Link>
              </div>
            </div>
          )}
          <div className="lg-card">
            <div className="lg-m lg-dim mb-3">During a session</div>
            {KEY_HELP.map(([k, v]) => (
              <div key={k} className="lg-row flex items-center justify-between py-3" style={{ fontSize: 16 }}>
                <span>{v}</span>
                <span className="lg-kbd">{k}</span>
              </div>
            ))}
          </div>
          <div className="lg-card">
            <div className="lg-m lg-dim mb-2">Reading the screen from 3 m</div>
            {LEGEND.map(([c, a, b]) => (
              <div key={a} className="lg-row flex items-center gap-3 py-2.5" style={{ fontSize: 14 }}>
                <span style={{ width: 12, height: 12, borderRadius: 3, background: c, flexShrink: 0 }} />
                <span className="w-40 shrink-0">{a}</span>
                <span className="lg-dim">{b}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ---------------- STAGE (session running) ----------------
  const cue = lastFlags.length ? FLAG_CUE[lastFlags[0]] : null;
  const connecting = starting || (!frameUrl && !stopping);
  const stateLabel = stopping
    ? "Saving session"
    : connecting
      ? state === "error"
        ? "Can't reach the stream"
        : "Starting camera"
      : stage === "idle"
        ? manualCal
          ? "Recalibrating"
          : "Calibrating"
        : stage === "counting"
          ? `Counting · ${st.phase === "down" ? "going down" : "standing"}`
          : stage === "clean"
            ? `Rep ${lastRepNo} · clean`
            : stage === "flagged"
              ? `Rep ${lastRepNo} · flagged`
              : "Fatigue · elevated";
  const glass = { background: "rgba(0,0,0,.35)", borderColor: "rgba(255,255,255,.25)", color: "var(--lg-ink)" };

  return (
    <div className="lg-stage" data-state={connecting || stopping ? "idle" : stage}>
      {frameUrl && !stopping && (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="lg-stage-feed" src={frameUrl} alt="Live camera with pose overlay" />
      )}
      <div className="lg-stage-shade" />
      <div className="lg-stage-frame" key={stage === "clean" ? `c${lastRepNo}` : stage} />

      <div className="absolute left-10 right-10 top-8 flex items-center gap-4">
        <span className="lg-word">LIFTGUARD</span>
        <span className="lg-chip lg-m" style={glass}>
          <span className="lg-dot" style={{ background: connecting ? "var(--lg-faint)" : "#FF5A1F" }} />
          {connecting ? "Connecting camera" : deviceMode ? "Live · this device's camera" : "Live · camera found"}
        </span>
        {!deviceMode && (
        <button
          className="lg-chip lg-m"
          style={{ ...glass, color: camStatus?.tone === "ok" ? "var(--lg-mint)" : camStatus?.tone === "warn" ? "var(--lg-amber)" : undefined }}
          onClick={() => void switchCamera()}
          disabled={connecting || stopping || !!camStatus?.busy}
          aria-live="polite"
        >
          {camStatus?.busy && <Spinner />}
          {camStatus ? camStatus.text : "Switch camera"} {!camStatus && <span style={{ opacity: 0.6 }}>K</span>}
        </button>
        )}
        <span className="lg-chip lg-m" style={glass}>
          Movement analysis · Squat mode
        </span>
        <button className="lg-chip lg-m" style={glass} onClick={() => setMenuOpen((m) => !m)} disabled={stopping}>
          Menu <span style={{ opacity: 0.6 }}>Esc</span>
        </button>
        <span className="lg-m ml-auto" style={{ color: "var(--lg-c)", fontSize: 12, fontWeight: 500 }} aria-live="polite">
          {stateLabel}
        </span>
      </div>
      <div className="absolute left-10 lg-m" style={{ top: 62, fontSize: 10, color: "rgba(244,243,238,.45)" }}>
        Not a medical diagnosis
      </div>

      {connecting || stopping ? (
        <div className="lg-d lg-stage-idle flex flex-col items-end gap-6">
          <span>{stopping ? "Saving" : "Starting"}</span>
          <span className="lg-m flex items-center gap-2.5" style={{ fontSize: 12, color: "rgba(244,243,238,.7)", fontStretch: "normal" }}>
            <Spinner /> {stopping ? "Writing the session report" : starting ? trying ?? "Looking for your camera" : "Camera found · loading the pose model"}
          </span>
        </div>
      ) : stage === "idle" ? (
        <>
          <div className="lg-d lg-stage-idle">
            {manualCal ? "Recalibrating" : <>Do 3 slow<br />squats</>}
          </div>
          <div className="lg-m lg-stage-sub" style={{ top: "62vh" }}>
            {manualCal ? "Press C again to finish" : "Learning your depth · counting starts after"}
          </div>
        </>
      ) : (
        <>
          <div className="lg-d lg-stage-num">{String(st.repCount).padStart(2, "0")}</div>
          {stage === "clean" && <div className="lg-d lg-stage-cue">Clean</div>}
          {stage === "flagged" && cue && (
            <>
              <div className="lg-d lg-stage-cue">{cue.cue}</div>
              <div className="lg-m lg-stage-sub">{lastFlags.map((f) => FLAG_CUE[f]?.why ?? f).join(" · ")}</div>
            </>
          )}
          {stage === "fatigue" && (
            <>
              <div className="lg-d lg-stage-cue">Slowing down</div>
              <div className="lg-m lg-stage-sub">
                {st.durationDrift != null ? `Reps ${Math.round(st.durationDrift)}% slower than your first reps` : "Rep time, depth or trunk lean drifting"}
              </div>
            </>
          )}
          {stage === "counting" && (
            <div className="lg-m lg-stage-sub" style={{ top: "72vh" }}>
              Rep {st.repCount + 1} {st.phase === "down" ? "in progress" : "next"}
            </div>
          )}
        </>
      )}

      {!connecting && !stopping && (
        <>
          <div className="lg-depth" role="img" aria-label={`Depth ${Math.round(depthPct)}% of your calibrated bottom`}>
            <i style={{ height: `${depthPct}%` }} />
          </div>
          <div className="absolute lg-m" style={{ right: 44, top: "79vh", width: 36, textAlign: "center", fontSize: 10 }}>
            Depth
          </div>
        </>
      )}

      <div className="absolute left-10 right-10 flex items-end gap-7" style={{ bottom: 30 }}>
        <div>
          <div className="lg-m mb-2" style={{ color: "rgba(244,243,238,.6)" }}>
            This session
          </div>
          <div className="flex gap-1.5 items-end" style={{ maxWidth: "46vw", flexWrap: "wrap" }}>
            {ledger.slice(-16).map((r) => (
              <div key={r.rep} className="relative">
                <div className={`lg-tile new ${r.flagged ? "f" : ""}`} title={`Rep ${r.rep}: ${r.flagged ? "flagged" : "clean"}`} />
                <span className="lg-m absolute left-0 right-0 text-center" style={{ bottom: -18, fontSize: 10, color: "rgba(244,243,238,.6)" }}>
                  {r.rep}
                </span>
              </div>
            ))}
            <div className="lg-tile n" />
          </div>
        </div>
        <div style={{ minWidth: 220 }}>
          <div className="lg-m" style={{ color: "rgba(244,243,238,.6)" }}>
            Fatigue indicator
          </div>
          <div className="lg-d" style={{ fontSize: 34, fontStretch: "75%", textTransform: "none", marginTop: 4 }}>
            {st.fatigueScore != null ? `${Math.round(st.fatigueScore)} · ${(st.fatigueStatus ?? "").toLowerCase()}` : "needs more reps"}
          </div>
        </div>
        <div className="ml-auto flex gap-3.5 lg-m" style={{ color: "rgba(244,243,238,.75)" }}>
          {[
            ["Space", "Stop"],
            ["V", voiceOn ? "Voice on" : "Voice off"],
            ["M", "Mirror"],
            ["C", manualCal ? "Finish cal" : "Calibrate"],
            ["R", "Reset"],
          ].map(([k, v]) => (
            <span key={k}>
              <span className="lg-kbd mr-1.5">{k}</span>
              {v}
            </span>
          ))}
        </div>
      </div>

      {menuOpen && sessionId && !stopping && (
        <LiveMenu telemetry={telemetry} deviceMode={deviceMode} voiceOn={voiceOn} onAction={(a) => (a === "toggle_voice" ? toggleVoice() : sendControl(a))} onStop={handleStop} onClose={() => setMenuOpen(false)} />
      )}

      <div className="absolute left-1/2 -translate-x-1/2 flex flex-col items-center gap-2" style={{ bottom: 110 }} aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="lg-chip lg-fade" style={{ background: "rgba(0,0,0,.75)", color: t.tone === "error" ? "var(--lg-amber)" : "var(--lg-ink)", borderColor: "rgba(255,255,255,.2)", fontSize: 14 }}>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}

function LiveMenu({ telemetry, deviceMode, voiceOn, onAction, onStop, onClose }: { telemetry: TelemetryPayload | null; deviceMode: boolean; voiceOn: boolean; onAction: (a: string) => void; onStop: () => void; onClose: () => void }) {
  const laser = telemetry?.arduino_connected ?? false;
  const cam = Number(telemetry?.camera_id ?? 0);
  const every = telemetry?.process_every_n ?? 1;
  const rows: { label: string; value: string; action: string; key?: string; muted?: boolean }[] = [
    { label: "Voice cues (this device)", value: voiceOn ? "On" : "Off", action: "toggle_voice", key: "V" },
    { label: "Mirror camera", value: telemetry?.mirror_mode ? "On" : "Off", action: "toggle_mirror", key: "M" },
    { label: "Recalibrate depth", value: telemetry?.calibration_mode ? "Finish" : "Start", action: telemetry?.calibration_mode ? "complete_calibration" : "start_calibration", key: "C" },
    { label: "Reset rep count", value: "Reset", action: "reset_reps", key: "R" },
    { label: "Laser pointer", value: laser ? "Turn off" : "Not found · try USB", action: "toggle_arduino", muted: !laser },
    { label: "Skip more frames (lighter on CPU)", value: `Every ${every}`, action: "speed_up" },
    { label: "Skip fewer frames (smoother)", value: `Every ${every}`, action: "speed_down" },
    { label: "Export session data", value: "Files saved on the backend", action: "export_data" },
  ];
  return (
    <div className="absolute inset-0 z-10 grid place-items-center lg-fade" style={{ background: "rgba(0,0,0,.72)" }} onClick={onClose}>
      <div className="lg-card" style={{ width: 580, background: "#111113" }} onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Session menu">
        <div className="flex items-center justify-between mb-3">
          <div className="lg-d" style={{ fontSize: 44 }}>
            Menu
          </div>
          <button className="lg-btn g" onClick={onClose}>
            Close <kbd>Esc</kbd>
          </button>
        </div>
        {rows.map((r) => (
          <button key={r.label} className="lg-row lg-hoverrow w-full flex items-center justify-between py-3 px-1 text-left" onClick={() => onAction(r.action)}>
            <span style={{ fontSize: 16 }}>{r.label}</span>
            <span className="flex items-center gap-3">
              <span className="lg-m" style={{ color: r.muted ? "var(--lg-faint)" : "var(--lg-dim)" }}>
                {r.value}
              </span>
              {r.key && <span className="lg-kbd">{r.key}</span>}
            </span>
          </button>
        ))}
        {!deviceMode && (
        <div className="lg-row flex items-center justify-between py-3 px-1">
          <span style={{ fontSize: 16 }}>Switch camera <span className="lg-m lg-faint" style={{ fontSize: 11 }}>advanced</span></span>
          <div className="lg-seg" role="radiogroup" aria-label="Camera">
            {[0, 1, 2, 3].map((i) => (
              <button key={i} role="radio" aria-checked={cam === i} onClick={() => cam !== i && onAction(`switch_camera:${i}`)}>
                {i}
              </button>
            ))}
          </div>
        </div>
        )}
        <button className="lg-btn warn w-full mt-4" onClick={onStop}>
          Stop and save <kbd>Space</kbd>
        </button>
      </div>
    </div>
  );
}

export default function LivePage() {
  return (
    <Suspense fallback={null}>
      <LiveInner />
    </Suspense>
  );
}
