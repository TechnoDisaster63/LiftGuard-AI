"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, SessionReport } from "@/lib/api";
import { exerciseOf, FATIGUE_LABEL, useSessionRows } from "@/lib/history";
import { Alert, Split, fmtDate } from "@/components/lg/ui";

function SpineTrace({ values }: { values: number[] }) {
  if (values.length < 2) {
    return <div className="lg-dim py-16 text-center">Not enough frames recorded for a trace.</div>;
  }
  const W = 820;
  const H = 300;
  const max = Math.max(10, ...values);
  const step = W / (values.length - 1);
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(H - (v / max) * (H - 20)).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H + 24}`} className="w-full" style={{ height: "auto", maxHeight: 340 }} role="img" aria-label={`Spine flexion over ${values.length} samples, peak ${max.toFixed(0)} degrees`}>
      <line x1="0" y1={H - (H - 20)} x2={W} y2={H - (H - 20)} stroke="rgba(244,243,238,.07)" />
      <text x="0" y={H - (H - 20) - 5} fill="rgba(244,243,238,.4)" fontSize="10" fontFamily="var(--font-geist-mono)">
        {max.toFixed(0)}°
      </text>
      <line x1="0" y1={H} x2={W} y2={H} stroke="rgba(244,243,238,.15)" />
      <polyline points={pts} fill="none" stroke="#F4F3EE" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

function PickSession() {
  const { rows } = useSessionRows({ limit: 8 });
  return (
    <div className="lg-fade">
      <div className="lg-m lg-dim">Reports</div>
      <div className="lg-d mt-1.5" style={{ fontSize: 92 }}>
        Pick a session
      </div>
      <div className="mt-6">
        {rows === null && <div className="lg-skel" style={{ height: 120 }} />}
        {rows?.length === 0 && (
          <p className="lg-dim" style={{ fontSize: 16 }}>
            No saved sessions yet. <Link href="/live" className="underline">Start one</Link>.
          </p>
        )}
        {rows?.map((r) => (
          <Link key={r.session_id} href={`/reports?history=${r.session_id}`} className="lg-row lg-hoverrow grid items-center gap-5 py-4" style={{ gridTemplateColumns: "150px 180px minmax(0,1fr) 90px" }}>
            <span className="lg-m">{fmtDate(r.started_at)}</span>
            <span style={{ fontSize: 16 }}>{r.is_guest ? "Guest" : r.display_name}</span>
            <Split clean={(r.reps ?? 0) - (r.flagged ?? 0)} flagged={r.flagged ?? 0} />
            <span className="lg-d text-right" style={{ fontSize: 36 }}>
              {r.reps ?? "—"}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function ReportContent() {
  const params = useSearchParams();
  const liveId = params.get("session");
  const historyId = params.get("history");
  const [report, setReport] = useState<SessionReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isHistorical, setIsHistorical] = useState(false);
  const [startedAt, setStartedAt] = useState<string | null>(null);

  useEffect(() => {
    setReport(null);
    setError(null);
    if (liveId) {
      setIsHistorical(false);
      api.sessions
        .report(liveId)
        .then(setReport)
        .catch(() =>
          // The session ended since the link was made: show the saved report.
          api.sessions.historyReport(liveId).then((r) => {
            setIsHistorical(true);
            setReport(r);
          })
        )
        .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load the report"));
    } else if (historyId) {
      setIsHistorical(true);
      api.sessions
        .historyReport(historyId)
        .then(setReport)
        .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load the report"));
      api.sessions
        .history({ limit: 100 })
        .then(({ sessions }) => setStartedAt(sessions.find((s) => s.session_id === historyId)?.started_at ?? null))
        .catch(() => {});
    }
  }, [liveId, historyId]);

  const sessionId = liveId ?? historyId;
  if (!sessionId) return <PickSession />;
  if (error)
    return (
      <div className="lg-fade max-w-xl">
        <Alert>{error}</Alert>
        <Link href="/sessions" className="lg-btn g mt-4">
          Back to sessions
        </Link>
      </div>
    );
  if (!report)
    return (
      <div className="grid gap-7" style={{ gridTemplateColumns: "minmax(0,1.6fr) minmax(0,1fr)" }}>
        <div className="lg-skel" style={{ height: 520 }} />
        <div className="lg-skel" style={{ height: 520 }} />
      </div>
    );

  const e = exerciseOf(report);
  const reps = e.reps ?? 0;
  const flagged = e.flagged ?? 0;
  const who = report.user ? (report.user.is_guest ? "Guest" : report.user.display_name) : "Unknown";
  const fat = FATIGUE_LABEL[e.fatigueStatus ?? ""];
  const avgs: [string, string][] = [
    ["Rep time", e.avgRepSeconds != null ? `${e.avgRepSeconds.toFixed(1)}s` : "—"],
    ["Deepest knee angle", e.avgDeepestKnee != null ? `${Math.round(e.avgDeepestKnee)}°` : "—"],
    ["Range of motion", e.avgRom != null ? `${Math.round(e.avgRom)}°` : "—"],
    ["Movements not counted", e.rejected != null ? String(e.rejected) : "—"],
  ];

  return (
    <div className="lg-fade grid gap-7" style={{ gridTemplateColumns: "minmax(0,1.6fr) minmax(0,1fr)" }}>
      <div className="min-w-0">
        <div className="flex items-end gap-7">
          <div className="lg-d" style={{ fontSize: 200 }}>
            {reps}
          </div>
          <div style={{ paddingBottom: 18 }}>
            <div className="lg-m lg-dim">
              Squat reps · {startedAt ? fmtDate(startedAt) : isHistorical ? "saved" : "live now"} · {who} · camera {report.camera_id}
            </div>
            <div className="lg-d mt-2" style={{ fontSize: 64, color: reps === 0 ? "var(--lg-faint)" : flagged ? "var(--lg-amber)" : "var(--lg-mint)" }}>
              {reps === 0 ? "No reps counted" : flagged ? `${flagged} flagged` : "All clean"}
            </div>
            <div className="mt-2" style={{ fontSize: 15 }}>
              {reps === 0
                ? e.calibration && e.calibration !== "CALIBRATED"
                  ? "Counting never started: calibration needs 3 slow squats first."
                  : "Movements that did not pass the rep checks were not counted."
                : `${reps - flagged} reps clean. Flags come from depth, trunk lean and range of motion.`}
            </div>
          </div>
        </div>
        <Split clean={reps - flagged} flagged={flagged} height={20} className="mt-3" />
        <div className="lg-card mt-4">
          <div className="flex justify-between lg-m lg-dim mb-2">
            <span>Spine flexion over the session</span>
            <span>Degrees</span>
          </div>
          <SpineTrace values={report.spine_history ?? []} />
        </div>
      </div>
      <div className="flex flex-col gap-4">
        <div className="lg-card">
          <div className="lg-m lg-dim mb-2">Averages per rep</div>
          {avgs.map(([a, b]) => (
            <div key={a} className="lg-row flex items-center justify-between py-3">
              <span style={{ fontSize: 16 }}>{a}</span>
              <span className="lg-d" style={{ fontSize: 40 }}>
                {b}
              </span>
            </div>
          ))}
        </div>
        <div className="lg-card" style={{ boxShadow: `inset 0 0 0 2px ${fat?.color ?? "var(--lg-line)"}` }}>
          <div className="flex justify-between lg-m">
            <span className="lg-dim">Fatigue indicator</span>
            <span style={{ color: fat?.color ?? "var(--lg-faint)" }}>{fat?.text ?? "—"}</span>
          </div>
          <div className="flex items-end gap-2 mt-2">
            <span className="lg-d" style={{ fontSize: 72, color: e.fatigueScore == null ? "var(--lg-faint)" : undefined }}>
              {e.fatigueScore != null ? Math.round(e.fatigueScore) : "—"}
            </span>
            <span className="lg-m lg-dim pb-2">/ 100</span>
          </div>
          <p className="lg-dim mt-2" style={{ fontSize: 13 }}>
            Drift in rep time, depth and trunk lean against your first reps. Higher means more drift.
          </p>
        </div>
        <div className="flex gap-2.5">
          <Link href="/sessions" className="lg-btn g">
            All sessions
          </Link>
          {!isHistorical && (
            <Link href="/live" className="lg-btn g">
              Back to live
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ReportsPage() {
  return (
    <Suspense fallback={null}>
      <ReportContent />
    </Suspense>
  );
}
