import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardEyebrow } from "@/components/ui/card";

interface Correction {
  id: string;
  priority: number;
  command: string;
  display: string;
  body_part: string;
}

const PRIORITY_COLOR: Record<number, string> = {
  1: "text-risk-high border-risk-high/30 bg-risk-high/5",
  2: "text-risk-moderate border-risk-moderate/30 bg-risk-moderate/5",
  3: "text-brand border-brand/30 bg-brand/5",
};

export function CorrectionsFeed({ corrections }: { corrections: Correction[] }) {
  if (!corrections?.length) {
    return (
      <Card className="p-4">
        <CardEyebrow className="mb-2">Form Corrections</CardEyebrow>
        <p className="text-sm text-risk-low flex items-center gap-1.5">
          <CheckCircle2 size={14} /> Good form — no corrections needed
        </p>
      </Card>
    );
  }

  return (
    <Card className="p-4">
      <CardEyebrow className="mb-3">Form Corrections</CardEyebrow>
      <ul className="space-y-2">
        <AnimatePresence initial={false}>
          {corrections.map((c) => (
            <motion.li
              key={c.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              className={`flex items-start gap-2 rounded-control border px-3 py-2 text-sm ${
                PRIORITY_COLOR[c.priority] ?? PRIORITY_COLOR[3]
              }`}
            >
              <AlertTriangle size={15} strokeWidth={1.75} className="mt-0.5 shrink-0" />
              <div>
                <p>{c.display}</p>
                <p className="text-[11px] font-mono text-ink-faint mt-0.5">{c.body_part}</p>
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </Card>
  );
}
