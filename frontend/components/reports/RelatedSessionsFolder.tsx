"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Folder from "@/components/reactbits/Folder";
import { api, SessionHistoryItem } from "@/lib/api";

function initialsOf(name: string) {
  return name.split(" ").slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");
}

function PaperContent({ item, onOpen }: { item: SessionHistoryItem; onOpen: () => void }) {
  const riskColor =
    item.peak_risk >= 3 ? "#FF1F5C" : item.peak_risk === 2 ? "#EF4444" : item.peak_risk === 1 ? "#F5A524" : "#16D97B";

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onOpen();
      }}
      className="w-full h-full flex flex-col items-center justify-center gap-1 px-1 text-center"
    >
      <span
        className="w-6 h-6 rounded-full grid place-items-center text-[9px] font-display shrink-0"
        style={{ background: riskColor, color: "#050608" }}
      >
        {initialsOf(item.display_name)}
      </span>
      <span className="text-[7px] text-ink-faint font-mono leading-tight">
        {item.started_at ? new Date(item.started_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—"}
      </span>
    </button>
  );
}

/** Only renders anything once there are OTHER sessions from the same user
 * to show — a user's very first session, or a guest session, has nothing
 * to relate to. */
export function RelatedSessionsFolder({
  userId,
  excludeSessionId,
}: {
  userId: number | null | undefined;
  excludeSessionId: string;
}) {
  const router = useRouter();
  const [history, setHistory] = useState<SessionHistoryItem[]>([]);

  useEffect(() => {
    if (userId == null) return;
    api.sessions
      .history({ limit: 5, userId })
      .then((r) => setHistory(r.sessions.filter((s) => s.session_id !== excludeSessionId).slice(0, 3)))
      .catch(() => {});
  }, [userId, excludeSessionId]);

  if (userId == null || history.length === 0) return null;

  const items = history.map((h) => (
    <PaperContent key={h.session_id} item={h} onOpen={() => router.push(`/reports?history=${h.session_id}`)} />
  ));

  return (
    <div className="glass-panel accent-bar rounded-panel p-6 flex flex-col items-center">
      <p className="text-[11px] font-mono uppercase tracking-wider text-ink-faint self-start mb-1">
        Related Sessions
      </p>
      <p className="text-xs text-ink-muted self-start mb-8">
        Other sessions from the same user
      </p>
      <div className="py-4">
        <Folder size={1.7} color="#7C5CFF" items={items} />
      </div>
    </div>
  );
}
