"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  Activity,
  LineChart,
  FileText,
  Users,
  UserPlus,
  ListVideo,
  Cpu,
  Settings,
} from "lucide-react";
import clsx from "clsx";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/live", label: "Live Analysis", icon: Activity },
  { href: "/analytics", label: "Analytics", icon: LineChart },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/users", label: "Users", icon: Users },
  { href: "/register", label: "Register User", icon: UserPlus },
  { href: "/sessions", label: "Sessions", icon: ListVideo },
  { href: "/hardware", label: "Hardware", icon: Cpu },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-border glass-panel px-3 py-6">
      <div className="px-3 mb-8">
        <div className="flex items-center gap-2">
          <motion.span
            className="w-2 h-2 rounded-full bg-brand shadow-glow-brand"
            animate={{ opacity: [1, 0.5, 1] }}
            transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
          />
          <span className="font-display text-sm tracking-[0.2em] text-ink uppercase">
            LiftGuard
          </span>
        </div>
        <p className="mt-1 text-[11px] text-ink-faint font-mono tracking-wide pl-4">
          Biomechanics AI
        </p>
      </div>

      <nav className="flex-1 space-y-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname?.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "relative flex items-center gap-3 px-3 py-2.5 rounded-control text-sm transition-colors overflow-hidden",
                active
                  ? "text-brand"
                  : "text-ink-muted hover:text-ink hover:bg-white/[0.03]"
              )}
            >
              {active && (
                <motion.span
                  layoutId="sidebar-active"
                  className="absolute inset-0 bg-brand/10 border border-brand/20 rounded-control"
                  transition={{ type: "spring", stiffness: 400, damping: 32 }}
                />
              )}
              <Icon size={17} strokeWidth={1.75} className="relative" />
              <span className="relative">{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="px-3 pt-4 border-t border-border">
        <p className="text-[10px] text-ink-faint font-mono">
          IRI is not a medical diagnosis
        </p>
      </div>
    </aside>
  );
}
