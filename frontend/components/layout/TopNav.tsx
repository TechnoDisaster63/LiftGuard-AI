"use client";

import Link from "next/link";
import { Bell, Settings, User } from "lucide-react";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";

const TITLES: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/live": "Live Analysis",
  "/analytics": "Analytics",
  "/reports": "Reports",
  "/users": "Users",
  "/register": "Register User",
  "/sessions": "Sessions",
  "/hardware": "Hardware",
  "/settings": "Settings",
};

export function TopNav() {
  const pathname = usePathname();
  const title =
    Object.entries(TITLES).find(([p]) => pathname?.startsWith(p))?.[1] ?? "LiftGuard AI";

  return (
    <header className="h-16 shrink-0 flex items-center justify-between px-6 border-b border-border glass-panel">
      <h1 className="font-display text-lg text-ink tracking-tight">{title}</h1>

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" aria-label="Notifications">
          <Bell size={17} strokeWidth={1.75} />
        </Button>
        <Link href="/settings">
          <Button variant="ghost" size="icon" aria-label="Settings">
            <Settings size={17} strokeWidth={1.75} />
          </Button>
        </Link>
        <div className="ml-2 flex items-center gap-2 pl-3 border-l border-border">
          <div className="w-8 h-8 rounded-full bg-panel-raised border border-border grid place-items-center">
            <User size={15} strokeWidth={1.75} className="text-ink-muted" />
          </div>
          <span className="text-sm text-ink-muted hidden sm:inline">Guest</span>
        </div>
      </div>
    </header>
  );
}
