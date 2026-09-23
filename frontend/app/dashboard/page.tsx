"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, SessionDefaults, UserOut } from "@/lib/api";
import { useBackendOnline } from "@/components/layout/TopNav";
import { useSessionRows, FATIGUE_LABEL } from "@/lib/history";
import { Split, fmtDate } from "@/components/lg/ui";
import { getCameraPin } from "@/lib/camera";
import { MovementLine } from "@/components/lg/MovementPicker";
import { useMovementMode } from "@/lib/movement";

export default function DashboardPage() {
  const online = useBackendOnline();
  const [defaults, setDefaults] = useState<SessionDefaults | null>(null);
  const [users, setUsers] = useState<UserOut[] | null>(null);
  const [active, setActive] = useState<string[]>([]);
  const [camPin, setCamPin] = useState<number | null>(null);
  const { rows } = useSessionRows({ limit: 1 });
  const last = rows?.[0] ?? null;
  const movement = useMovementMode();

  useEffect(() => {
    api.settings.get().then(setDefaults).catch(() => {});
    setCamPin(getCameraPin());
    api.users.list().then(setUsers).catch(() => setUsers(null));
    api.sessions.list().then((r) => setActive(r.active_sessions)).catch(() => {});
  }, []);

  const pre: [string, string, string][] = [
    ["Movement mode", movement.current.label, "var(--lg-ink)"],
    ["Backend", online === null ? "Checking" : online ? "Online" : "Offline", online ? "var(--lg-mint)" : online === false ? "var(--lg-amber)" : "var(--lg-faint)"],
    ["Camera", camPin !== null ? `Fixed to camera ${camPin}` : "Finds it automatically at start", camPin !== null ? "var(--lg-amber)" : "var(--lg-dim)"],
    ["Voice cues", defaults ? (defaults.voice_enabled ? "On" : "Off") : "—", defaults?.voice_enabled ? "var(--lg-mint)" : "var(--lg-faint)"],
    ["Laser pointer", defaults ? (defaults.arduino_enabled ? "Tries to connect at start" : "Off") : "—", defaults?.arduino_enabled ? "var(--lg-dim)" : "var(--lg-faint)"],
    ["Face ID", users ? (users.length ? `${users.length} ${users.length === 1 ? "person" : "people"} enrolled` : "Nobody enrolled · guest") : "—", users?.length ? "var(--lg-mint)" : "var(--lg-faint)"],
  ];

  return (
    <div className="lg-fade grid gap-7" style={{ gridTemplateColumns: "minmax(0,1.35fr) minmax(0,1fr)", minHeight: "calc(100vh - 150px)" }}>
      <div className="relative rounded-[18px] overflow-hidden flex flex-col justify-end p-9" style={{ background: "radial-gradient(120% 90% at 20% 10%, #1c1c20, #0b0b0c)" }}>
        {active.length > 0 && (
          <Link href="/sessions" className="lg-chip lg-m absolute left-6 top-6" style={{ color: "var(--lg-amber)", borderColor: "color-mix(in srgb, var(--lg-amber) 40%, transparent)" }}>
            {active.length} session running · manage
          </Link>
        )}
        <div style={{ fontSize: 26, fontWeight: 600, maxWidth: 560, lineHeight: 1.2 }}>Real-time movement analysis for injury prevention.</div>
        <MovementLine />
        <div className="lg-d mt-3" style={{ fontSize: "clamp(120px, 17vw, 240px)", color: online === false ? "var(--lg-idle)" : undefined }}>
          {online === false ? "Offline" : "Ready"}
        </div>
        <div className="flex gap-3 mt-5">
          <Link href="/live?start=1" className="lg-btn lg" aria-disabled={online === false}>
            Start session
          </Link>
          <Link href="/settings" className="lg-btn g lg">
            Session settings
          </Link>
        </div>
      </div>
      <div className="flex flex-col gap-4">
        <div className="lg-card">
          <div className="lg-m lg-dim mb-3.5">Pre-flight</div>
          {pre.map(([a, b, c]) => (
            <div key={a} className="lg-row flex justify-between py-2.5" style={{ fontSize: 16 }}>
              <span>{a}</span>
              <span className="lg-m" style={{ color: c }}>
                {b}
              </span>
            </div>
          ))}
        </div>
        <div className="lg-card flex-1">
          {rows === null ? (
            <div className="lg-skel" style={{ height: 180 }} />
          ) : !last ? (
            <>
              <div className="lg-m lg-dim">Last session</div>
              <div className="lg-d mt-4" style={{ fontSize: 64, color: "var(--lg-faint)" }}>
                None yet
              </div>
              <p className="lg-dim mt-3" style={{ fontSize: 15 }}>
                Start a session and its reps, flags and fatigue indicator land here.
              </p>
            </>
          ) : (
            <>
              <div className="lg-m lg-dim">
                Last session · {fmtDate(last.started_at)} · {last.is_guest ? "Guest" : last.display_name}
              </div>
              <div className="flex items-end gap-5 mt-2.5">
                <div className="lg-d" style={{ fontSize: 150 }}>
                  {last.reps ?? "—"}
                </div>
                <div style={{ paddingBottom: 18 }}>
                  <div className="lg-m lg-dim">Reps</div>
                  <div style={{ fontSize: 15, marginTop: 6 }}>
                    {last.flagged ?? 0} flagged · fatigue {(FATIGUE_LABEL[last.fatigueStatus ?? ""]?.text ?? "—").toLowerCase()}
                  </div>
                </div>
              </div>
              <Split clean={(last.reps ?? 0) - (last.flagged ?? 0)} flagged={last.flagged ?? 0} className="mt-2.5" />
              <div className="flex gap-2.5 mt-5">
                <Link className="lg-btn g" href={`/reports?history=${last.session_id}`}>
                  Open report
                </Link>
                <Link className="lg-btn g" href="/sessions">
                  All sessions
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
