"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, FileText } from "lucide-react";
import { api, SessionReport } from "@/lib/api";
import { StatCard } from "@/components/live/StatCard";
import { TimelineChart } from "@/components/charts/TimelineChart";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { RelatedSessionsFolder } from "@/components/reports/RelatedSessionsFolder";

function ReportContent() {
  const params = useSearchParams();
  const liveId = params.get("session");
  const historyId = params.get("history");
  const [report, setReport] = useState<SessionReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isHistorical, setIsHistorical] = useState(false);

  useEffect(() => {
    if (liveId) {
      setIsHistorical(false);
      api.sessions
        .report(liveId)
        .then(setReport)
        .catch(() =>
          // The session ended since the link was made: show the saved report.
          api.sessions.historyReport(liveId).then((r) => {
            setIsHistorical(true);
            setReport(r);
          })
        )
        .catch((e) => setError(e.message));
    } else if (historyId) {
      setIsHistorical(true);
      api.sessions.historyReport(historyId).then(setReport).catch((e) => setError(e.message));
    }
  }, [liveId, historyId]);

  const sessionId = liveId ?? historyId;

  if (!sessionId) {
    return (
      <Card>
        <EmptyState
          icon={<FileText size={22} strokeWidth={1.5} />}
          message="Pick a session to view its report"
          actionLabel="Go to Sessions"
          actionHref="/sessions"
        />
      </Card>
    );
  }

  if (error) {
    return (
      <div className="rounded-control border border-risk-high/30 bg-risk-high/5 px-4 py-3 text-sm text-risk-high">
        {error}
      </div>
    );
  }

  if (!report) {
    return (
      <div className="flex items-center gap-2 text-sm text-ink-faint font-mono py-10 justify-center">
        <Loader2 size={15} className="animate-spin" /> Loading report…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[11px] font-mono uppercase tracking-wider text-ink-faint mb-1">
                Session
              </p>
              <p className="font-mono text-sm text-ink">{sessionId}</p>
            </div>
            <Badge tone={isHistorical ? "neutral" : "brand"} dot={!isHistorical}>
              {isHistorical ? "Completed" : "Live"}
            </Badge>
          </div>
          {report.user && (
            <p className="text-sm text-ink-muted mt-2">
              {report.user.display_name} {report.user.is_guest && "(guest)"}
            </p>
          )}
        </Card>
      </motion.div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Peak Risk Level" value={report.peak_risk} accent="red" />
        <StatCard label="Model" value={report.using_temporal ? "TCN" : "Frame-level"} />
        <StatCard label="IRI Version" value={report.using_iri_v2 ? "V2" : "Legacy"} />
        <StatCard label="Camera" value={`#${report.camera_id}`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="p-5">
          <p className="font-display text-base mb-3">Injury Risk Index</p>
          <TimelineChart data={report.iri_history ?? []} color="#EF4444" />
        </Card>
        <Card className="p-5">
          <p className="font-display text-base mb-3">Spine Flexion</p>
          <TimelineChart data={report.spine_history ?? []} color="#16D97B" unit="°" />
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="p-5">
          <p className="font-display text-base mb-3">Exercise Summary</p>
          <dl className="space-y-2">
            {Object.entries(report.exercise ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between text-sm">
                <dt className="text-ink-faint font-mono">{k}</dt>
                <dd className="text-ink tabular">{String(v)}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card className="p-5">
          <p className="font-display text-base mb-3">Fatigue Summary</p>
          <dl className="space-y-2">
            {Object.entries(report.fatigue ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between text-sm">
                <dt className="text-ink-faint font-mono">{k}</dt>
                <dd className="text-ink tabular">{String(v)}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <RelatedSessionsFolder userId={report.user?.user_id} excludeSessionId={sessionId} />
      </div>

      {!isHistorical && (
        <Card className="p-4">
          <p className="text-xs text-ink-faint">
            PDF/CSV export runs the same <code className="font-mono">export_data()</code> the
            desktop app used — trigger it from the Export button on the Live Analysis page while
            the session is running; files are written server-side.
          </p>
        </Card>
      )}
    </div>
  );
}

export default function ReportsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 text-sm text-ink-faint font-mono py-10 justify-center">
          <Loader2 size={15} className="animate-spin" /> Loading…
        </div>
      }
    >
      <ReportContent />
    </Suspense>
  );
}
