"use client";

import { useState } from "react";
import { Play, Square } from "lucide-react";
import { api } from "@/lib/api";
import { useLiveSession } from "@/lib/ws";
import { VideoCanvas } from "@/components/live/VideoCanvas";
import { StatCard } from "@/components/live/StatCard";
import { CorrectionsFeed } from "@/components/live/CorrectionsFeed";
import { ControlBar } from "@/components/live/ControlBar";
import { ToastStack } from "@/components/live/ToastStack";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";

const statVariants = {
  hidden: { opacity: 0, y: 10 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.05 } }),
};

export default function LivePage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { frameUrl, telemetry, state, sendControl, toasts } = useLiveSession(sessionId);

  const handleStart = async () => {
    setStarting(true);
    setError(null);
    try {
      const res = await api.sessions.start({});
      setSessionId(res.session_id);
    } catch (e) {
      setError(
        e instanceof Error
          ? `Couldn't start session — is the backend running? (${e.message})`
          : "Couldn't start session"
      );
    } finally {
      setStarting(false);
    }
  };

  const handleStop = async () => {
    if (!sessionId) return;
    await api.sessions.stop(sessionId).catch(() => null);
    setSessionId(null);
  };

  // Only validated outputs are shown: the calibrated squat counter and the
  // rep-based fatigue indicator. TCN confidence, MC-dropout uncertainty and
  // the injury risk index are not validated (docs/REVIVAL_SCOPE.md).
  const status = (telemetry?.exercise_status ?? {}) as Record<string, unknown>;
  const calibration = typeof status.calibration_mode === "string" ? status.calibration_mode : null;
  const lastRep = (status.last_rep ?? null) as { rep?: number; form_flags?: string[] } | null;
  const fatigueScore = telemetry?.fatigue_score ?? null;
  const fatigueAlert = telemetry?.fatigue_alert;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-6">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {!sessionId ? (
              <Button variant="primary" onClick={handleStart} disabled={starting}>
                <Play size={15} /> {starting ? "Starting…" : "Start Session"}
              </Button>
            ) : (
              <Button variant="danger" onClick={handleStop}>
                <Square size={15} /> Stop Session
              </Button>
            )}
            {calibration && (
              <span className="text-[11px] font-mono text-ink-faint">SQUAT COUNTER · {calibration.replace("_", " ")}</span>
            )}
          </div>
          {telemetry && (
            <p className="text-[11px] font-mono text-ink-faint tabular">
              FRAME {telemetry.frame_count} · {telemetry.fps ?? "—"} FPS
            </p>
          )}
        </div>

        {error && (
          <div className="rounded-control border border-risk-high/30 bg-risk-high/5 px-4 py-3 text-sm text-risk-high">
            {error}
          </div>
        )}

        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
          <VideoCanvas frameUrl={frameUrl} connectionState={state} telemetry={telemetry} />
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {[
            <StatCard key="reps" label="Reps Completed" value={telemetry?.lifts_completed ?? 0} accent="clinical" />,
            <StatCard
              key="fatigue"
              label="Fatigue indicator"
              value={fatigueScore !== null ? fatigueScore.toFixed(0) : "needs more reps"}
              unit={fatigueScore !== null ? fatigueAlert ?? "" : ""}
              accent={fatigueScore === null ? "neutral" : fatigueScore >= 35 ? "red" : fatigueScore >= 15 ? "amber" : "clinical"}
            />,
            <StatCard
              key="lastrep"
              label="Last rep form"
              value={lastRep ? (lastRep.form_flags?.length ? lastRep.form_flags.join(", ").replaceAll("_", " ").toLowerCase() : "OK") : "—"}
              accent={lastRep?.form_flags?.length ? "amber" : "clinical"}
            />,
          ].map((card, i) => (
            <motion.div key={i} custom={i} initial="hidden" animate="show" variants={statVariants}>
              {card}
            </motion.div>
          ))}
        </div>

        {sessionId && (
          <ControlBar
            voiceEnabled={telemetry?.voice_enabled ?? false}
            arduinoConnected={telemetry?.arduino_connected ?? false}
            mirrorMode={telemetry?.mirror_mode ?? false}
            calibrationMode={telemetry?.calibration_mode ?? false}
            usingTemporal={telemetry?.using_temporal ?? false}
            processEveryN={telemetry?.process_every_n ?? 1}
            onAction={sendControl}
          />
        )}
      </div>

      <div className="space-y-4">
        <CorrectionsFeed corrections={(telemetry?.corrections as never[]) ?? []} repFlags={lastRep?.form_flags ?? []} />
      </div>

      <ToastStack toasts={toasts} />
    </div>
  );
}
