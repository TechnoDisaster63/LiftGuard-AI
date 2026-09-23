"use client";

import { useState } from "react";
import type { ContributionSet } from "@/lib/api";
import { contrib, type Feel } from "@/lib/contrib";

const FEELS: [Feel, string][] = [
  ["easy", "Easy"],
  ["ok", "OK"],
  ["hard", "Hard"],
  ["hurt", "Something hurt"],
];

/** After a contributed set: optional self-label, or drop the set. */
export function SetRatingCard({ set }: { set: ContributionSet }) {
  const [feel, setFeel] = useState<Feel | null>(null);
  const [counting, setCounting] = useState<boolean | null>(null);
  const [state, setState] = useState<"open" | "deleted" | "error">("open");
  const [busy, setBusy] = useState(false);

  const save = async (next: { feel?: Feel | null; counting_right?: boolean | null }) => {
    const body = { feel: next.feel !== undefined ? next.feel : feel, counting_right: next.counting_right !== undefined ? next.counting_right : counting };
    setBusy(true);
    try {
      await contrib.label(set.set_id, body);
      setFeel(body.feel ?? null);
      setCounting(body.counting_right ?? null);
    } catch {
      setState("error");
    } finally {
      setBusy(false);
    }
  };

  const drop = async () => {
    setBusy(true);
    try {
      await contrib.remove(set.set_id);
      setState("deleted");
    } catch {
      setState("error");
    } finally {
      setBusy(false);
    }
  };

  if (state === "deleted") {
    return (
      <div className="lg-card lg-fade">
        <div className="lg-m lg-dim">This set was not saved for training.</div>
      </div>
    );
  }

  return (
    <div className="lg-card lg-fade" aria-busy={busy}>
      <div className="lg-m lg-dim">Saved for training · body points only</div>
      <div className="mt-3" style={{ fontSize: 18, fontWeight: 600 }}>How did that set feel?</div>
      <div className="lg-choice-row mt-3" role="group" aria-label="How did that set feel?">
        {FEELS.map(([k, label]) => (
          <button key={k} className={`lg-choice ${feel === k ? "on" : ""} ${k === "hurt" ? "hurt" : ""}`} aria-pressed={feel === k} disabled={busy} onClick={() => void save({ feel: feel === k ? null : k })}>
            {label}
          </button>
        ))}
      </div>
      <div className="lg-dim mt-2" style={{ fontSize: 12 }}>
        LiftGuard is not a medical diagnosis.{feel === "hurt" ? " If something hurts, stop and have it checked by a professional." : ""}
      </div>
      <div className="mt-5" style={{ fontSize: 16 }}>
        Was the counting right? <span className="lg-dim">({set.total_reps} rep{set.total_reps === 1 ? "" : "s"})</span>
      </div>
      <div className="lg-choice-row mt-3" role="group" aria-label="Was the counting right?">
        {([
          [true, "Yes"],
          [false, "No"],
        ] as const).map(([v, label]) => (
          <button key={label} className={`lg-choice ${counting === v ? "on" : ""}`} aria-pressed={counting === v} disabled={busy} onClick={() => void save({ counting_right: counting === v ? null : v })}>
            {label}
          </button>
        ))}
      </div>
      {state === "error" && <div className="mt-3" style={{ color: "var(--lg-amber)", fontSize: 13 }}>Couldn&apos;t save that. You can still delete the set on My contributions.</div>}
      <button className="lg-btn g mt-5" disabled={busy} onClick={drop}>
        Don&apos;t save this set
      </button>
    </div>
  );
}
