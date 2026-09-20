"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { UserPlus, Users as UsersIcon } from "lucide-react";
import { api, UserOut } from "@/lib/api";
import { Card, CardEyebrow } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import MagicBento from "@/components/reactbits/MagicBento";

const QUICK_ACTIONS = [
  { title: "Register User", description: "Enroll a new face via webcam", label: "Identity", href: "/register" },
  { title: "Sessions", description: "Active and past sessions for everyone", label: "History", href: "/sessions" },
  { title: "Hardware", description: "Connect or recalibrate the laser pointer", label: "Laser", href: "/hardware" },
  { title: "Settings", description: "Session defaults for the next login", label: "Config", href: "/settings" },
];

function initialsOf(name: string) {
  return name.split(" ").slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");
}

export default function UsersPage() {
  const [users, setUsers] = useState<UserOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.users.list().then(setUsers).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-ink-muted max-w-lg">
          New users enroll via face capture — right here in the browser, no physical camera
          rig required for registration itself.
        </p>
        <Link href="/register">
          <Button variant="primary">
            <UserPlus size={15} /> Register User
          </Button>
        </Link>
      </div>

      {error && (
        <div className="rounded-control border border-risk-high/30 bg-risk-high/5 px-4 py-3 text-sm text-risk-high">
          {error}
        </div>
      )}

      {users.length === 0 && !error ? (
        <Card>
          <EmptyState
            icon={<UsersIcon size={22} strokeWidth={1.5} />}
            message="No users registered yet"
            actionLabel="Register the first user"
            actionHref="/register"
          />
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-wider text-ink-faint">
                  User
                </th>
                <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-wider text-ink-faint">
                  Sessions
                </th>
                <th className="px-5 py-3 font-mono text-[11px] uppercase tracking-wider text-ink-faint">
                  Last Seen
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((u, i) => (
                <motion.tr
                  key={u.user_id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.04 }}
                  className="hover:bg-white/[0.02] transition-colors"
                >
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-3">
                      <span className="w-8 h-8 rounded-full bg-brand/15 border border-brand/25 grid place-items-center text-[11px] font-display text-brand shrink-0">
                        {initialsOf(u.display_name)}
                      </span>
                      <div>
                        <p className="text-ink">{u.display_name}</p>
                        <p className="text-[11px] font-mono text-ink-faint">@{u.username}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-3 text-ink tabular">{u.total_sessions}</td>
                  <td className="px-5 py-3 text-ink-muted font-mono text-xs">{u.last_seen ?? "—"}</td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <div>
        <CardEyebrow className="mb-3">Quick Actions</CardEyebrow>
        <MagicBento
          cards={QUICK_ACTIONS}
          variant="compact"
          textAutoHide={false}
          enableStars
          enableSpotlight
          enableBorderGlow
          enableTilt={false}
          enableMagnetism
          particleCount={6}
          spotlightRadius={220}
          glowColor="124, 92, 255"
        />
      </div>
    </div>
  );
}
