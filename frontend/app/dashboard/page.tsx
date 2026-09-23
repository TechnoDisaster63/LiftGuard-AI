"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Activity, Users, ListVideo, ArrowUpRight } from "lucide-react";
import { api, UserOut } from "@/lib/api";
import MagicBento from "@/components/reactbits/MagicBento";
import { RecentReportsFolder } from "@/components/dashboard/RecentReportsFolder";
import { SparklesCore } from "@/components/ui/sparkles";
import { Card, CardHeader, CardTitle, CardEyebrow } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const cardVariants = {
  hidden: { opacity: 0, y: 12 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.06, duration: 0.35 } }),
};

export default function DashboardPage() {
  const [activeSessions, setActiveSessions] = useState<string[]>([]);
  const [users, setUsers] = useState<UserOut[]>([]);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  useEffect(() => {
    api.health()
      .then(() => setBackendOnline(true))
      .catch(() => setBackendOnline(false));
    api.sessions.list().then((r) => setActiveSessions(r.active_sessions)).catch(() => {});
    api.users.list().then(setUsers).catch(() => {});
  }, []);

  const stats = [
    { label: "Active Sessions", value: activeSessions.length.toString(), icon: Activity },
    { label: "Registered Users", value: users.length.toString(), icon: Users },
    {
      label: "Backend",
      value: backendOnline === null ? "Checking…" : backendOnline ? "Online" : "Offline",
      icon: ListVideo,
      dim: !backendOnline,
    },
  ];

  return (
    <div className="space-y-8">
      {/* Hero */}
      <div className="relative h-40 rounded-panel border border-border overflow-hidden bg-panel">
        <div className="absolute inset-0">
          <SparklesCore
            background="transparent"
            minSize={0.3}
            maxSize={1}
            particleDensity={50}
            particleColor="#7C5CFF"
            speed={1.5}
            className="w-full h-full"
          />
        </div>
        <div className="absolute inset-0 [mask-image:radial-gradient(ellipse_at_center,transparent_10%,black)]" />
        <div className="relative h-full flex flex-col items-center justify-center text-center px-6 pointer-events-none">
          <motion.h1
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="font-display text-3xl md:text-4xl gradient-brand-text"
          >
            LiftGuard AI
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 }}
            className="text-sm text-ink-muted mt-2"
          >
            Real-time pose tracking and squat rep counting
          </motion.p>
        </div>
      </div>

      {backendOnline === false && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="rounded-control border border-risk-high/30 bg-risk-high/5 px-4 py-3 text-sm text-risk-high"
        >
          Can&apos;t reach the backend at the configured API URL. Start it with{" "}
          <code className="font-mono">uvicorn app.main:app --reload</code> from{" "}
          <code className="font-mono">backend/</code>.
        </motion.div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {stats.map((s, i) => (
          <motion.div key={s.label} custom={i} initial="hidden" animate="show" variants={cardVariants}>
            <Card>
              <CardHeader>
                <CardEyebrow>{s.label}</CardEyebrow>
                <s.icon size={16} className="text-brand" strokeWidth={1.75} />
              </CardHeader>
              <p className={`font-display text-3xl tabular ${s.dim ? "text-ink-faint" : "text-ink"}`}>
                {s.value}
              </p>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Feature grid */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16 }}>
        <CardEyebrow className="mb-3">Explore</CardEyebrow>
        <MagicBento
          textAutoHide
          enableStars
          enableSpotlight
          enableBorderGlow
          enableTilt={false}
          enableMagnetism
          clickEffect
          spotlightRadius={280}
          particleCount={8}
          glowColor="124, 92, 255"
        />
      </motion.div>

      {/* Users + recent reports */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.28 }}>
          <Card className="p-6 h-full">
            <div className="flex items-center justify-between mb-4">
              <CardTitle>Registered Users</CardTitle>
              <Link href="/register">
                <Button variant="outline-brand" size="sm">
                  <ArrowUpRight size={13} /> Register
                </Button>
              </Link>
            </div>
            {users.length === 0 ? (
              <p className="text-sm text-ink-muted">
                No users registered yet —{" "}
                <Link href="/register" className="text-brand hover:underline">
                  register the first one
                </Link>
                .
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {users.map((u) => (
                  <li key={u.user_id} className="py-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm text-ink">{u.display_name}</p>
                      <p className="text-[11px] font-mono text-ink-faint">@{u.username}</p>
                    </div>
                    <p className="text-xs text-ink-muted tabular">
                      {u.total_sessions} session{u.total_sessions === 1 ? "" : "s"}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.34 }}>
          <RecentReportsFolder />
        </motion.div>
      </div>
    </div>
  );
}
