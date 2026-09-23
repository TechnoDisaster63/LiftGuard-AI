"use client";

import type { CSSProperties, ReactNode } from "react";

/** Clean vs flagged share of a set: the ledger motif used on every page. */
export function Split({ clean, flagged, height = 14, className = "" }: { clean: number; flagged: number; height?: number; className?: string }) {
  const empty = clean + flagged === 0;
  return (
    <div className={`lg-split ${className}`} style={{ height }} role="img" aria-label={empty ? "No reps" : `${clean} clean, ${flagged} flagged`}>
      {clean > 0 && <i style={{ flex: clean }} />}
      {flagged > 0 && <b style={{ flex: flagged }} />}
      {empty && <s />}
    </div>
  );
}

export function Label({ children, className = "", style }: { children: ReactNode; className?: string; style?: CSSProperties }) {
  return (
    <div className={`lg-m lg-dim ${className}`} style={style}>
      {children}
    </div>
  );
}

export function Segmented({ label, options, value, onChange, disabled }: { label: string; options: string[]; value: number; onChange: (i: number) => void; disabled?: boolean }) {
  return (
    <div role="radiogroup" aria-label={label} className="lg-seg">
      {options.map((opt, i) => (
        <button key={opt} type="button" role="radio" aria-checked={value === i} disabled={disabled} onClick={() => value !== i && onChange(i)}>
          {opt}
        </button>
      ))}
    </div>
  );
}

export function Switch({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return <button type="button" role="switch" aria-label={label} aria-checked={checked} className="lg-switch" onClick={() => onChange(!checked)} />;
}

export function Spinner() {
  return <span className="lg-spin" aria-hidden />;
}

export function Alert({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="lg-alert">
      {children}
    </div>
  );
}

export function initialsOf(name: string) {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join("") || "?"
  );
}

export function fmtDate(iso: string | null | undefined, withTime = true) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const date = d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  if (!withTime) return date;
  return `${date}, ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
}

export function fmtDuration(start: string | null | undefined, end: string | null | undefined) {
  if (!start || !end) return "—";
  const s = Math.max(0, Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Live form flags (backend _form_flags) -> short on-screen commands. */
export const FLAG_CUE: Record<string, { cue: string; why: string }> = {
  LIMITED_DEPTH: { cue: "Go deeper", why: "Knee stayed above 110° at the bottom" },
  EXCESSIVE_TRUNK_LEAN: { cue: "Chest up", why: "Trunk leaned past 45°" },
  LOW_RANGE_OF_MOTION: { cue: "Full range", why: "Knee moved less than 45° in the rep" },
};
