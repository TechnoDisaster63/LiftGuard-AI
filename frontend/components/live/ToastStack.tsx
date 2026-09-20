"use client";

import { CheckCircle2, AlertCircle } from "lucide-react";
import type { ToastMessage } from "@/lib/ws";

export function ToastStack({ toasts }: { toasts: ToastMessage[] }) {
  if (!toasts.length) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 w-80">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`animate-toast-in flex items-start gap-2.5 px-4 py-3 rounded-control border shadow-glass ${
            t.tone === "error"
              ? "bg-risk-high/10 border-risk-high/40 text-risk-high"
              : "bg-panel-raised border-brand/30 text-ink"
          }`}
        >
          {t.tone === "error" ? (
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
          ) : (
            <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-brand" />
          )}
          <p className="text-sm leading-snug">{t.text}</p>
        </div>
      ))}
    </div>
  );
}
