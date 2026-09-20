"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ShieldCheck, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

export function UncertaintyButton({ sessionId }: { sessionId: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  const openPanel = async () => {
    setOpen(true);
    setLoading(true);
    try {
      const res = await api.analytics.uncertainty(sessionId);
      setData(res);
    } catch {
      setData({});
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <motion.button
        whileTap={{ scale: 0.95 }}
        onClick={openPanel}
        className="press-scale flex items-center gap-2 px-3 py-2 rounded-control border border-uncertainty/30 text-uncertainty text-xs font-mono hover:bg-uncertainty/10 transition-colors"
      >
        <ShieldCheck size={14} /> UNCERTAINTY
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-void/70 flex items-center justify-center p-6"
            onClick={() => setOpen(false)}
          >
            <motion.div
              initial={{ opacity: 0, y: 12, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.97 }}
              onClick={(e) => e.stopPropagation()}
              className="glass-panel-raised accent-bar rounded-panel p-6 max-w-md w-full max-h-[70vh] overflow-y-auto"
            >
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <ShieldCheck size={18} className="text-uncertainty" />
                  <p className="font-display text-lg">Uncertainty Summary</p>
                </div>
                <button
                  onClick={() => setOpen(false)}
                  className="w-7 h-7 grid place-items-center rounded-control text-ink-faint hover:text-ink hover:bg-white/[0.04]"
                >
                  <X size={15} />
                </button>
              </div>

              {loading ? (
                <div className="flex items-center gap-2 text-sm text-ink-faint font-mono py-6 justify-center">
                  <Loader2 size={16} className="animate-spin" /> Loading…
                </div>
              ) : !data || Object.keys(data).length === 0 ? (
                <p className="text-sm text-ink-muted">
                  No uncertainty data yet — this fills in once the temporal (TCN) model has
                  processed enough frames with Monte Carlo Dropout active.
                </p>
              ) : (
                <dl className="space-y-2.5">
                  {Object.entries(data).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-4 text-sm">
                      <dt className="text-ink-faint font-mono shrink-0">{k}</dt>
                      <dd className="text-ink tabular text-right">
                        {typeof v === "number" ? v.toFixed(3) : String(v)}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
