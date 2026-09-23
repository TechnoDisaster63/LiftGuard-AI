"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Home" },
  { href: "/live", label: "Live" },
  { href: "/sessions", label: "Sessions" },
  { href: "/reports", label: "Reports" },
  { href: "/users", label: "Users" },
  { href: "/register", label: "Register" },
  { href: "/hardware", label: "Hardware" },
  { href: "/settings", label: "Settings" },
];

/** Polls /api/health so the chip reflects the backend now, not at page load. */
export function useBackendOnline() {
  const [online, setOnline] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    const check = () =>
      api
        .health()
        .then(() => alive && setOnline(true))
        .catch(() => alive && setOnline(false));
    check();
    const t = setInterval(check, 10000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  return online;
}

export function TopNav() {
  const pathname = usePathname() ?? "";
  const online = useBackendOnline();
  return (
    <header className="lg-nav flex items-center gap-7 px-10 pt-7 pb-3">
      <Link href="/dashboard" className="lg-word mr-3">
        LIFTGUARD
      </Link>
      <nav className="flex items-center gap-6">
        {NAV.map(({ href, label }) => {
          const on = pathname.startsWith(href);
          return (
            <Link key={href} href={href} className={`lg-navlink ${on ? "on" : ""}`} aria-current={on ? "page" : undefined}>
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="ml-auto flex items-center gap-2.5">
        <span className="lg-chip lg-m" title="Backend health, checked every 10 s">
          <span className="lg-dot" style={{ background: online === null ? "var(--lg-faint)" : online ? "var(--lg-mint)" : "var(--lg-amber)" }} />
          {online === null ? "Checking backend" : online ? "Backend online" : "Backend offline"}
        </span>
        <span className="lg-chip lg-m" title="Movement mode. Squat is the only mode today.">
          Mode · Squat
        </span>
      </div>
    </header>
  );
}
