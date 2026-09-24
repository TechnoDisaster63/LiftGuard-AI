"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, FaceStatus, UserOut } from "@/lib/api";
import IdentifyPanel from "@/components/lg/IdentifyPanel";
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
  const [face, setFace] = useState<FaceStatus | null>(null);

  const load = () =>
    api.users
      .list()
      .then((u) => setUsers(u.filter((x) => !x.is_guest)))
      .catch((e) => {
        setUsers([]);
        setError(e instanceof Error ? e.message : "Couldn't load users");
      });

  useEffect(() => {
    load();
    api.users.faceStatus().then(setFace).catch(() => setFace(null));
  }, []);

  const forget = async (u: UserOut) => {
    if (!window.confirm(`Delete ${u.display_name}'s face signature? Their account and history stay.`)) return;
    try {
      await api.users.forgetFace(u.user_id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't delete the face signature");
    }
  };
  const faceLocal = !!face && face.local && face.available;

  return (
    <div className="lg-fade">
      <div className="lg-m lg-dim">People LiftGuard recognises at session start</div>
      <div className="lg-d mt-1.5" style={{ fontSize: 92 }}>
        {users === null ? "…" : `${users.length} enrolled`}
      </div>
      <div className="mt-3" style={{ fontSize: 15 }}>
        {face === null ? null : faceLocal ? (
          <span className="lg-m" style={{ color: "var(--lg-mint)" }}>
            Face ID runs on this computer. Your face never leaves this device: only a face signature (128 numbers, not a photo) is stored here.
          </span>
        ) : !face.local ? (
          <span className="lg-m lg-dim">Face ID is not available from this device. It only works in a browser on the computer running LiftGuard.</span>
        ) : (
          <span className="lg-m lg-dim">Face ID is not available on this machine (face model files missing: run python fetch_face_models.py in backend/).</span>
        )}
      </div>
      {faceLocal && (face?.enrolled_count ?? 0) > 0 && (
        <div className="mt-4" style={{ maxWidth: 560 }}>
          <IdentifyPanel />
        </div>
      )}
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
            <div className="flex items-center gap-2 mt-2">
              <span className="lg-chip lg-m" data-testid="face-chip" style={u.face_enrolled ? { color: "var(--lg-mint)", borderColor: "var(--lg-mint)" } : undefined}>
                {u.face_enrolled ? "Face ID on" : "No face ID"}
              </span>
              {faceLocal && !u.face_enrolled && (
                <Link href={`/register?user=${u.user_id}`} className="lg-m" style={{ fontSize: 12, textDecoration: "underline" }}>
                  Set up
                </Link>
              )}
              {u.face_enrolled && (
                <button className="lg-m lg-faint" style={{ fontSize: 12, textDecoration: "underline" }} onClick={() => forget(u)}>
                  Delete face
                </button>
              )}
            </div>
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
            About 6 seconds in front of this computer&apos;s webcam. Only a face signature is kept, on this machine.
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
