"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { CONTRIB_EVENT, contrib, contributing, setContributing } from "@/lib/contrib";

/** Tracks the local on/off switch (re-renders when it changes anywhere). */
export function useContributing(): boolean {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const read = () => setOn(contributing());
    read();
    window.addEventListener(CONTRIB_EVENT, read);
    window.addEventListener("storage", read);
    return () => {
      window.removeEventListener(CONTRIB_EVENT, read);
      window.removeEventListener("storage", read);
    };
  }, []);
  return on;
}

const SAVED = [
  "Your body points as numbers: 22 points from shoulders to feet, about 15 times a second",
  "Squat mode, rep count and what LiftGuard flagged",
  "Phone or laptop, which camera, frame size",
  "Your rating after the set, if you give one",
];
const NEVER = ["Video or photos", "Your face (face points are dropped on the server before anything is kept)", "Your name, account or location"];

/** Ready-screen control for "Help train LiftGuard", off by default.
 * variant="card": the switch card beside the hero (desktop, My contributions).
 * variant="button": a full-width labelled button for the phone hero, where a
 * small switch below the fold was easy to miss. Both open the same consent. */
export function ContributeCard({ showLink = true, variant = "card" }: { showLink?: boolean; variant?: "card" | "button" }) {
  const on = useContributing();
  const [asking, setAsking] = useState(false);
  const [adult, setAdult] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const agree = async () => {
    setBusy(true);
    setError(null);
    try {
      await contrib.giveConsent(adult);
      setContributing(true);
      setAsking(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save your choice.");
    } finally {
      setBusy(false);
    }
  };

  const toggle = () => (on ? setContributing(false) : setAsking(true));
  const sheet = (
    <>
      {asking && createPortal(
        <div className="lg-sheet-backdrop" role="dialog" aria-modal="true" aria-labelledby="lg-consent-title" onClick={() => !busy && setAsking(false)}>
          <div className="lg-sheet lg-fade" onClick={(e) => e.stopPropagation()}>
            <div id="lg-consent-title" style={{ fontSize: 22, fontWeight: 600, lineHeight: 1.25 }}>
              Help train LiftGuard with your squats?
            </div>
            <p className="lg-dim mt-2" style={{ fontSize: 14 }}>
              LiftGuard learns to count and check reps better from real sets. If you turn this on, each set you do is saved to a private LiftGuard dataset.
            </p>
            <div className="lg-m lg-dim mt-5 mb-2">What is saved</div>
            <ul className="lg-consent-list">{SAVED.map((s) => <li key={s}>{s}</li>)}</ul>
            <div className="lg-m lg-dim mt-4 mb-2">Never saved</div>
            <ul className="lg-consent-list no">{NEVER.map((s) => <li key={s}>{s}</li>)}</ul>
            <p className="lg-dim mt-4" style={{ fontSize: 13 }}>
              Your sets are tied to a random code on this device, not to you. You can see and delete them any time on My contributions, and turning this off stops saving straight away. LiftGuard is not a medical diagnosis.
            </p>
            <label className="lg-check mt-5">
              <input type="checkbox" checked={adult} onChange={(e) => setAdult(e.target.checked)} />
              <span>I am 18 or older</span>
            </label>
            {error && <div className="mt-3" style={{ color: "var(--lg-amber)", fontSize: 13 }}>{error}</div>}
            <div className="lg-sheet-actions flex flex-wrap gap-3">
              <button className="lg-btn" disabled={!adult || busy} onClick={agree}>
                {busy ? "Saving" : "I agree · turn on"}
              </button>
              <button className="lg-btn g" disabled={busy} onClick={() => setAsking(false)}>
                Not now
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );

  if (variant === "button") {
    return (
      <>
        <button
          type="button"
          aria-pressed={on}
          className={`lg-btn lg-contrib-btn ${on ? "on" : ""}`}
          onClick={toggle}
        >
          <span className="lg-dot" style={{ background: on ? "var(--lg-mint)" : "var(--lg-faint)" }} />
          <span>Help train LiftGuard</span>
          <span className="lg-contrib-state">{on ? "On" : "Off"}</span>
        </button>
        {on && showLink && (
          <Link href="/contributions" className="lg-m lg-dim" style={{ fontSize: 11 }}>
            On · body points only, never video · My contributions →
          </Link>
        )}
        {sheet}
      </>
    );
  }

  return (
    <div className="lg-card lg-contrib">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>Help train LiftGuard</div>
          <div className="lg-dim mt-1" style={{ fontSize: 13 }}>
            {on ? "On · your sets save body points only, never video." : "Off · nothing from your sessions is kept for training."}
          </div>
        </div>
        <button
          role="switch"
          aria-checked={on}
          aria-label="Help train LiftGuard"
          className={`lg-switch ${on ? "on" : ""}`}
          onClick={toggle}
        />
      </div>
      {showLink && (
        <Link href="/contributions" className="lg-m lg-dim inline-block mt-3" style={{ fontSize: 11 }}>
          My contributions →
        </Link>
      )}

      {sheet}
    </div>
  );
}
