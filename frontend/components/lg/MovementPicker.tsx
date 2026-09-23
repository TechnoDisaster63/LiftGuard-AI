"use client";

import { Segmented } from "@/components/lg/ui";
import { useMovementMode } from "@/lib/movement";

/** Pick the movement mode. Modes not checked on a recorded clip yet show as "coming". */
export function MovementPicker({ showPending = true, align = "end" }: { showPending?: boolean; align?: "start" | "end" }) {
  const { modes, mode, setMode, error } = useMovementMode();
  const selectable = modes.filter((m) => m.selectable);
  const pending = modes.filter((m) => !m.selectable);
  const index = Math.max(0, selectable.findIndex((m) => m.id === mode));
  return (
    <div className={`grid gap-2 ${align === "end" ? "justify-items-end" : "justify-items-start"}`}>
      <Segmented label="Movement mode" options={selectable.map((m) => m.label.replace("-", "\u2011"))} value={index} onChange={(i) => setMode(selectable[i].id)} />
      {showPending && pending.length > 0 && (
        <div className={`lg-m lg-faint ${align === "end" ? "text-right" : ""}`} style={{ fontSize: 11 }}>
          Coming: {pending.map((m) => m.label).join(", ")}
        </div>
      )}
      {error && <div className="lg-m" style={{ color: "var(--lg-amber)", fontSize: 11 }}>{error}</div>}
    </div>
  );
}

/** One line for the Ready screens: "Movement mode: squat · watches ..." */
export function MovementLine() {
  const { current } = useMovementMode();
  return (
    <div className="lg-m lg-dim mt-2.5">
      Movement mode: {current.label.toLowerCase()} · watches {current.watches}
    </div>
  );
}
