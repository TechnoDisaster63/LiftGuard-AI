"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Folder from "@/components/reactbits/Folder";
import { api, SessionHistoryItem } from "@/lib/api";

function initialsOf(name: string) {
  return name
    .split(" ")
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
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
      <span className="text-[8px] text-ink leading-tight line-clamp-1 font-body">
        {item.display_name}
      </span>
      <span className="text-[7px] text-ink-faint font-mono leading-tight">
        {item.started_at ? new Date(item.started_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—"}
      </span>
    </button>
  );
}

export function RecentReportsFolder() {
  const router = useRouter();
  const [history, setHistory] = useState<SessionHistoryItem[]>([]);

  useEffect(() => {
    api.sessions.history({ limit: 3 }).then((r) => setHistory(r.sessions)).catch(() => {});
  }, []);

  const items = history.map((h) => (
    <PaperContent key={h.session_id} item={h} onOpen={() => router.push(`/reports?history=${h.session_id}`)} />
  ));

  return (
    <div className="glass-panel accent-bar rounded-panel p-6 flex flex-col items-center">
      <p className="text-[11px] font-mono uppercase tracking-wider text-ink-faint self-start mb-1">
        Recent Session Reports
      </p>
      <p className="text-xs text-ink-muted self-start mb-8">
        Click the folder, then a paper, to open that session&apos;s report
      </p>

      <div className="flex-1 flex items-center justify-center py-6" style={{ minHeight: 180 }}>
        {history.length === 0 ? (
          <p className="text-sm text-ink-faint font-mono">No completed sessions yet</p>
        ) : (
          <Folder size={2.1} color="#7C5CFF" items={items} />
        )}
      </div>
    </div>
  );
}
