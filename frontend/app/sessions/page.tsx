"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Square, FileText, ListVideo, History } from "lucide-react";
import { api, SessionHistoryItem } from "@/lib/api";
import { Card, CardEyebrow } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, riskToneFromLevel } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { RecentReportsFolder } from "@/components/dashboard/RecentReportsFolder";

export default function SessionsPage() {
  const [sessions, setSessions] = useState<string[]>([]);
  const [history, setHistory] = useState<SessionHistoryItem[]>([]);

  const refresh = () => api.sessions.list().then((r) => setSessions(r.active_sessions)).catch(() => {});
  const refreshHistory = () => api.sessions.history({ limit: 20 }).then((r) => setHistory(r.sessions)).catch(() => {});

  useEffect(() => {
    refresh();
    refreshHistory();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);

  const stop = async (id: string) => {
    await api.sessions.stop(id).catch(() => {});
    refresh();
    refreshHistory();
  };

  return (
    <div className="space-y-8">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <RecentReportsFolder />
      </motion.div>

      <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 }} className="space-y-3">
        <div className="flex items-center justify-between">
          <CardEyebrow>Active Sessions</CardEyebrow>
          <p className="text-xs text-ink-faint">Live, from backend memory</p>
        </div>

        {sessions.length === 0 ? (
          <Card>
            <EmptyState
              icon={<ListVideo size={22} strokeWidth={1.5} />}
              message="No active sessions"
              actionLabel="Start one from Live Analysis"
              actionHref="/live"
            />
          </Card>
        ) : (
          <Card className="p-0 divide-y divide-border overflow-hidden">
            {sessions.map((id, i) => (
              <motion.div
                key={id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex items-center justify-between px-5 py-4"
              >
                <div>
                  <p className="text-sm text-ink font-mono">{id}</p>
                  <Badge tone="brand" dot className="mt-1.5">
                    Active
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  <Link href={`/reports?session=${id}`}>
                    <Button variant="ghost" size="icon" aria-label="View report">
                      <FileText size={16} />
                    </Button>
                  </Link>
                  <Button variant="danger" size="icon" onClick={() => stop(id)} aria-label="Stop session">
                    <Square size={16} />
                  </Button>
                </div>
              </motion.div>
            ))}
          </Card>
        )}
      </motion.section>

      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="space-y-3"
      >
        <CardEyebrow>Past Sessions</CardEyebrow>

        {history.length === 0 ? (
          <Card>
            <EmptyState icon={<History size={22} strokeWidth={1.5} />} message="No completed sessions yet" />
          </Card>
        ) : (
          <Card className="p-0 divide-y divide-border overflow-hidden">
            {history.map((h, i) => (
              <Link key={h.session_id} href={`/reports?history=${h.session_id}`}>
                <motion.div
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className="flex items-center justify-between px-5 py-4 hover:bg-white/[0.02] transition-colors"
                >
                  <div>
                    <p className="text-sm text-ink">
                      {h.display_name} {h.is_guest && <span className="text-ink-faint">(guest)</span>}
                    </p>
                    <p className="text-[11px] font-mono text-ink-faint mt-0.5">
                      {h.started_at ? new Date(h.started_at).toLocaleString() : "—"}
                    </p>
                  </div>
                  <Badge tone={riskToneFromLevel(h.peak_risk)}>Peak Risk {h.peak_risk}</Badge>
                </motion.div>
              </Link>
            ))}
          </Card>
        )}
      </motion.section>
    </div>
  );
}
