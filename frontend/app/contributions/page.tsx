"use client";

import { useCallback, useEffect, useState } from "react";
import type { ContributionSet } from "@/lib/api";
import { adoptContributorCode, contrib, contributorId, setContributing } from "@/lib/contrib";
import { ContributeCard } from "@/components/contrib/ContributeCard";
import { Alert } from "@/components/lg/ui";

const FEEL: Record<string, string> = { easy: "Easy", ok: "OK", hard: "Hard", hurt: "Something hurt" };

function when(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function ContributionsPage() {
  const [sets, setSets] = useState<ContributionSet[] | null>(null);
  const [code, setCode] = useState("");
  const [other, setOther] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setCode(contributorId());
    try {
      setSets((await contrib.list()).sets);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load your contributions.");
    }
  }, []);
  useEffect(() => void load(), [load]);

  const remove = async (id: string) => {
    setBusy(id);
    try {
      await contrib.remove(id);
      setSets((s) => s?.filter((x) => x.set_id !== id) ?? null);
      setNote("Set deleted.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't delete that set.");
    } finally {
      setBusy(null);
    }
  };

  const withdraw = async () => {
    if (!window.confirm("Delete every set saved with this code and turn contributing off?")) return;
    setBusy("all");
    try {
      const r = await contrib.withdraw();
      setContributing(false);
      setSets([]);
      setNote(`Deleted ${r.deleted_sets} set${r.deleted_sets === 1 ? "" : "s"}. Contributing is off.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't delete your sets.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="lg-fade grid gap-6 max-w-3xl">
      <div>
        <div className="lg-m lg-dim">Training data</div>
        <h1 style={{ fontSize: 32, fontWeight: 600, marginTop: 6 }}>My contributions</h1>
        <p className="lg-dim mt-2" style={{ fontSize: 14 }}>
          Sets saved to help train LiftGuard: body points as numbers, never video or face. Deleting a set removes it from the dataset, including its history.
        </p>
      </div>
      <ContributeCard showLink={false} />
      {error && <Alert>{error}</Alert>}
      {note && <div className="lg-m" style={{ color: "var(--lg-mint)" }}>{note}</div>}

      <div className="lg-card">
        <div className="lg-m lg-dim mb-2">Saved sets</div>
        {sets === null && !error && <div className="lg-dim py-3">Loading…</div>}
        {sets?.length === 0 && <div className="lg-dim py-3">No sets saved with this code.</div>}
        {sets?.map((s) => (
          <div key={s.set_id} className="lg-row flex flex-wrap items-center justify-between gap-3 py-3">
            <div>
              <div style={{ fontSize: 15 }}>{when(s.created_at)}</div>
              <div className="lg-dim" style={{ fontSize: 13 }}>
                Squat · {s.total_reps} rep{s.total_reps === 1 ? "" : "s"}
                {s.seconds != null ? ` · ${Math.round(s.seconds)} s` : ""}
                {s.self_label?.feel ? ` · felt ${FEEL[s.self_label.feel] ?? s.self_label.feel}` : ""}
              </div>
            </div>
            <button className="lg-btn g" disabled={busy !== null} onClick={() => remove(s.set_id)}>
              {busy === s.set_id ? "Deleting" : "Delete"}
            </button>
          </div>
        ))}
        {!!sets?.length && (
          <button className="lg-btn g mt-4" style={{ color: "var(--lg-amber)" }} disabled={busy !== null} onClick={withdraw}>
            Delete all and stop contributing
          </button>
        )}
      </div>

      <div className="lg-card">
        <div className="lg-m lg-dim mb-2">Your delete code</div>
        <p className="lg-dim" style={{ fontSize: 13 }}>
          Your sets are tied to this random code, not to your name. Keep it if you want to delete your sets from another device or after clearing this browser.
        </p>
        <div className="flex flex-wrap items-center gap-3 mt-3">
          <code className="lg-code">{code}</code>
          <button className="lg-btn g" onClick={() => void navigator.clipboard?.writeText(code).then(() => setNote("Code copied."))}>
            Copy
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-3 mt-4">
          <input className="lg-input" placeholder="Paste a code from another device" value={other} onChange={(e) => setOther(e.target.value)} />
          <button
            className="lg-btn g"
            onClick={() => {
              if (adoptContributorCode(other)) {
                setOther("");
                void load();
              } else setError("That doesn't look like a LiftGuard code.");
            }}
          >
            Use this code
          </button>
        </div>
      </div>
    </div>
  );
}
