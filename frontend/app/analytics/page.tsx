"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { TimelineChart } from "@/components/charts/TimelineChart";
import { Card, CardEyebrow } from "@/components/ui/card";
import { Loader2 } from "lucide-react";

export default function AnalyticsPage() {
  const [activeSessions, setActiveSessions] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState<string>("");
  const [iri, setIri] = useState<number[]>([]);
  const [spine, setSpine] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.sessions.list().then((r) => {
      setActiveSessions(r.active_sessions);
      if (r.active_sessions.length > 0) setSessionId(r.active_sessions[0]);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    Promise.all([
      api.analytics.iriTimeline(sessionId).then((r) => setIri(r.values)),
      api.analytics.spineTimeline(sessionId).then((r) => setSpine(r.values)),
    ])
      .catch(() => {
        setIri([]);
        setSpine([]);
      })
      .finally(() => setLoading(false));
  }, [sessionId]);

  return (
    <div className="space-y-6">
      <Card className="p-4 flex items-center gap-3">
        <CardEyebrow>Session</CardEyebrow>
        {activeSessions.length > 0 ? (
          <select
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            className="bg-panel-raised border border-border rounded-control px-3 py-1.5 text-sm text-ink font-mono focus:outline-none focus:border-brand/40"
          >
            {activeSessions.map((id) => (
              <option key={id} value={id}>
                {id.slice(0, 8)}…
              </option>
            ))}
          </select>
        ) : (
          <p className="text-sm text-ink-muted">
            No active sessions — start one from the Live Analysis page
          </p>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-6">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 }}>
          <Card className="p-5">
            <p className="font-display text-base mb-1">Spine Flexion</p>
            <p className="text-[11px] font-mono text-ink-faint mb-4">
              Degrees of spinal flexion over the session
            </p>
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-ink-faint font-mono py-10 justify-center">
                <Loader2 size={15} className="animate-spin" /> Loading…
              </div>
            ) : (
              <TimelineChart data={spine} color="#16D97B" unit="°" />
            )}
          </Card>
        </motion.div>
      </div>

      <Card className="p-4">
        <p className="text-xs text-ink-faint">
          This page charts one session&apos;s frame-by-frame data. For completed sessions, see{" "}
          <Link href="/sessions" className="text-brand hover:underline">
            Sessions
          </Link>{" "}
          → Past Sessions, now persisted to the database rather than lost when a session ends.
        </p>
      </Card>
    </div>
  );
}
