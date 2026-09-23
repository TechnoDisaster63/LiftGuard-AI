"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useSessionRows, FATIGUE_LABEL } from "@/lib/history";
import { Alert, Split, Spinner, fmtDate, fmtDuration } from "@/components/lg/ui";

const COLS = "150px 180px minmax(0,1fr) 110px 150px 80px";

export default function SessionsPage() {
  const router = useRouter();
  const [active, setActive] = useState<string[]>([]);
  const [stoppingId, setStoppingId] = useState<string | null>(null);
  const [stopError, setStopError] = useState<string | null>(null);
  const { rows, error, reload } = useSessionRows({ limit: 30 });

  const refreshActive = useCallback(() => api.sessions.list().then((r) => setActive(r.active_sessions)).catch(() => {}), []);
  useEffect(() => {
    refreshActive();
    const t = setInterval(refreshActive, 5000);
    return () => clearInterval(t);
  }, [refreshActive]);

  const stop = async (id: string) => {
    setStoppingId(id);
    setStopError(null);
    try {
      await api.sessions.stop(id);
    } catch (e) {
      setStopError(`Couldn't stop ${id.slice(0, 8)}: ${e instanceof Error ? e.message : ""}`);
    }
    setStoppingId(null);
    refreshActive();
    reload();
  };

  const totalReps = (rows ?? []).reduce((a, r) => a + (r.reps ?? 0), 0);

  return (
    <div className="lg-fade">
      <div className="flex items-end justify-between">
        <div>
          <div className="lg-m lg-dim">Saved sessions</div>
          <div className="lg-d mt-1.5" style={{ fontSize: 92 }}>
            {rows === null ? "…" : `${rows.length} ${rows.length === 1 ? "session" : "sessions"} · ${totalReps} reps`}
          </div>
        </div>
        <Link href="/live" className="lg-btn">
          New session
        </Link>
      </div>

      {active.length > 0 && (
        <div className="lg-card mt-6" style={{ borderLeft: "4px solid var(--lg-amber)" }}>
          <div className="lg-m" style={{ color: "var(--lg-amber)" }}>
            Running now · holds the camera until stopped
          </div>
          {active.map((id) => (
            <div key={id} className="flex items-center justify-between mt-3">
              <span className="lg-m">{id}</span>
              <div className="flex gap-2">
                <Link className="lg-btn g" href={`/reports?session=${id}`}>
                  Live report
                </Link>
                <button className="lg-btn warn" onClick={() => stop(id)} disabled={stoppingId === id}>
                  {stoppingId === id ? (
                    <>
                      <Spinner /> Stopping
                    </>
                  ) : (
                    "Stop and save"
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {(error || stopError) && (
        <div className="mt-4">
          <Alert>{stopError ?? error}</Alert>
        </div>
      )}

      <div className="mt-7">
        <div className="grid gap-5 pb-2.5 lg-m lg-faint" style={{ gridTemplateColumns: COLS }}>
          <span>Started</span>
          <span>Person</span>
          <span>Clean vs flagged</span>
          <span>Reps</span>
          <span>Fatigue</span>
          <span>Length</span>
        </div>
        {rows === null &&
          [0, 1, 2, 3].map((i) => (
            <div key={i} className="lg-row py-4">
              <div className="lg-skel" style={{ height: 22 }} />
            </div>
          ))}
        {rows?.length === 0 && !error && (
          <div className="lg-row py-12 text-center">
            <div className="lg-d" style={{ fontSize: 56, color: "var(--lg-faint)" }}>
              No sessions yet
            </div>
            <Link href="/live" className="lg-btn mt-5">
              Start the first one
            </Link>
          </div>
        )}
        {rows?.map((r) => {
          const reps = r.reps ?? 0;
          const flagged = r.flagged ?? 0;
          const fat = FATIGUE_LABEL[r.fatigueStatus ?? ""];
          return (
            <div
              key={r.session_id}
              role="link"
              tabIndex={0}
              onClick={() => router.push(`/reports?history=${r.session_id}`)}
              onKeyDown={(e) => e.key === "Enter" && router.push(`/reports?history=${r.session_id}`)}
              className="lg-row lg-hoverrow grid items-center gap-5 py-4 cursor-pointer"
              style={{ gridTemplateColumns: COLS }}
            >
              <span className="lg-m">{fmtDate(r.started_at)}</span>
              <span style={{ fontSize: 16 }}>{r.is_guest ? "Guest" : r.display_name}</span>
              <div>
                <Split clean={reps - flagged} flagged={flagged} />
                <div className="lg-m lg-faint mt-1.5" style={{ fontSize: 10 }}>
                  {r.report ? (reps ? `${reps - flagged} clean · ${flagged} flagged` : "No reps counted") : "Report unavailable"}
                </div>
              </div>
              <span className="lg-d" style={{ fontSize: 40 }}>
                {r.reps ?? "—"}
              </span>
              <span className="lg-m" style={{ color: fat?.color ?? "var(--lg-faint)" }}>
                {fat?.text ?? "—"}
              </span>
              <span className="lg-m lg-dim">{fmtDuration(r.started_at, r.ended_at)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
