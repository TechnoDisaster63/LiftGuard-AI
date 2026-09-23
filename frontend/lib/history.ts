"use client";

import { useEffect, useState } from "react";
import { api, SessionHistoryItem, SessionReport } from "./api";

export interface SessionRow extends SessionHistoryItem {
  reps: number | null;
  flagged: number | null;
  fatigueStatus: string | null;
  fatigueScore: number | null;
  report: SessionReport | null;
}

/** Reads the honest fields of a saved report (exercise + fatigue summaries). */
export function exerciseOf(r: SessionReport | null) {
  const ex = (r?.exercise ?? {}) as Record<string, unknown>;
  const fa = (r?.fatigue ?? {}) as Record<string, unknown>;
  const n = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  return {
    reps: n(ex.total_reps),
    flagged: n(ex.reps_with_form_flags),
    avgRepSeconds: n(ex.avg_rep_seconds),
    avgDeepestKnee: n(ex.avg_deepest_knee_angle_deg),
    avgRom: n(ex.avg_range_of_motion_deg),
    rejected: n(ex.rejected_candidates),
    calibration: typeof ex.calibration_mode === "string" ? ex.calibration_mode : null,
    fatigueStatus: typeof fa.status === "string" ? fa.status : null,
    fatigueScore: n(fa.score),
  };
}

/** Saved sessions plus each one's saved report (for rep counts and flags). */
export function useSessionRows(params?: { limit?: number; userId?: number }) {
  const [rows, setRows] = useState<SessionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const limit = params?.limit;
  const userId = params?.userId;
  useEffect(() => {
    let alive = true;
    api.sessions
      .history({ limit, userId })
      .then(async ({ sessions }) => {
        const reports = await Promise.all(sessions.map((s) => api.sessions.historyReport(s.session_id).catch(() => null)));
        if (!alive) return;
        setRows(
          sessions.map((s, i) => {
            const e = exerciseOf(reports[i]);
            return { ...s, reps: e.reps, flagged: e.flagged, fatigueStatus: e.fatigueStatus, fatigueScore: e.fatigueScore, report: reports[i] };
          })
        );
        setError(null);
      })
      .catch((e) => {
        if (!alive) return;
        setRows([]);
        setError(e instanceof Error ? e.message : "Couldn't load sessions");
      });
    return () => {
      alive = false;
    };
  }, [limit, userId, nonce]);
  return { rows, error, reload: () => setNonce((n) => n + 1) };
}

export const FATIGUE_LABEL: Record<string, { text: string; color: string }> = {
  STABLE: { text: "Steady", color: "var(--lg-mint)" },
  WATCH: { text: "Watch", color: "var(--lg-amber)" },
  ELEVATED: { text: "Elevated", color: "var(--lg-mag)" },
  INSUFFICIENT_REPS: { text: "Too few reps", color: "var(--lg-faint)" },
};
