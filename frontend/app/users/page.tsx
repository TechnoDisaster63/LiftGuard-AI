"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, UserOut } from "@/lib/api";
import { useSessionRows } from "@/lib/history";
import { Alert, Split, fmtDate, initialsOf } from "@/components/lg/ui";

function RecentStrip({ user }: { user: UserOut }) {
  const { rows } = useSessionRows({ userId: user.user_id, limit: 6 });
  return (
    <div className="lg-row grid items-center gap-3.5 py-3.5" style={{ gridTemplateColumns: "200px repeat(6, minmax(0,1fr))" }}>
      <div style={{ fontSize: 16 }}>{user.display_name}</div>
      {rows === null
        ? Array.from({ length: 6 }).map((_, i) => <div key={i} className="lg-skel" style={{ height: 12 }} />)
        : Array.from({ length: 6 }).map((_, i) => {
            const r = rows[i];
            if (!r) return <div key={i} />;
            return (
              <Link key={r.session_id} href={`/reports?history=${r.session_id}`} title={`${fmtDate(r.started_at)}: ${r.reps ?? 0} reps, ${r.flagged ?? 0} flagged`}>
                <Split clean={(r.reps ?? 0) - (r.flagged ?? 0)} flagged={r.flagged ?? 0} height={12} />
                <div className="lg-m lg-faint mt-1.5" style={{ fontSize: 10 }}>
                  {r.reps ?? 0} reps
                </div>
              </Link>
            );
          })}
    </div>
  );
}

export default function UsersPage() {
  const [users, setUsers] = useState<UserOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.users
      .list()
      .then((u) => setUsers(u.filter((x) => !x.is_guest)))
      .catch((e) => {
        setUsers([]);
        setError(e instanceof Error ? e.message : "Couldn't load users");
      });
  }, []);

  return (
    <div className="lg-fade">
      <div className="lg-m lg-dim">People LiftGuard recognises at session start</div>
      <div className="lg-d mt-1.5" style={{ fontSize: 92 }}>
        {users === null ? "…" : `${users.length} enrolled`}
      </div>
      {error && (
        <div className="mt-4">
          <Alert>{error}</Alert>
        </div>
      )}
      <div className="grid gap-4 mt-6" style={{ gridTemplateColumns: "repeat(4, minmax(0,1fr))" }}>
        {users === null &&
          [0, 1, 2].map((i) => <div key={i} className="lg-skel" style={{ height: 280, borderRadius: 14 }} />)}
        {users?.map((u) => (
          <div key={u.user_id} className="lg-card" style={{ minHeight: 280 }}>
            <div className="lg-d" style={{ fontSize: 120 }}>
              {initialsOf(u.display_name)}
            </div>
            <div className="mt-3.5" style={{ fontSize: 22, fontWeight: 600 }}>
              {u.display_name}
            </div>
            <div className="lg-m lg-faint mt-1">@{u.username}</div>
            <div className="flex gap-7 mt-4">
              <div>
                <div className="lg-d" style={{ fontSize: 36 }}>
                  {u.total_sessions}
                </div>
                <div className="lg-m lg-faint" style={{ fontSize: 10 }}>
                  Sessions
                </div>
              </div>
              <div>
                <div className="lg-d" style={{ fontSize: 36 }}>
                  {fmtDate(u.last_seen, false)}
                </div>
                <div className="lg-m lg-faint" style={{ fontSize: 10 }}>
                  Last seen
                </div>
              </div>
            </div>
          </div>
        ))}
        <div className="lg-card flex flex-col justify-end" style={{ minHeight: 280, background: "transparent", border: "2px dashed var(--lg-line)" }}>
          <div className="lg-d" style={{ fontSize: 120, color: "var(--lg-faint)" }}>
            +
          </div>
          <div className="mt-3.5" style={{ fontSize: 22, fontWeight: 600 }}>
            Register someone
          </div>
          <div className="lg-dim mt-1.5" style={{ fontSize: 14 }}>
            About 6 seconds in front of the webcam. Stored on this machine.
          </div>
          <Link href="/register" className="lg-btn mt-4 self-start">
            Start face capture
          </Link>
        </div>
      </div>
      {users && users.length > 0 && (
        <div className="mt-8">
          <div className="lg-m lg-dim mb-1.5">Last six sessions each · clean vs flagged reps</div>
          {users.map((u) => (
            <RecentStrip key={u.user_id} user={u} />
          ))}
        </div>
      )}
      {users?.length === 0 && !error && (
        <p className="lg-dim mt-6" style={{ fontSize: 15 }}>
          Nobody is enrolled yet, so every session is saved as Guest.
        </p>
      )}
    </div>
  );
}
