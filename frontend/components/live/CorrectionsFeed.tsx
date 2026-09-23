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

const FLAG_TEXT: Record<string, string> = {
  LIMITED_DEPTH: "Last rep: limited depth",
  EXCESSIVE_TRUNK_LEAN: "Last rep: trunk lean",
  LOW_RANGE_OF_MOTION: "Last rep: low range of motion",
  KNEES_CAVING: "Last rep: knees caving in",
  HEELS_LIFTING: "Last rep: heels lifting",
  DEPTH_INCONSISTENT: "Last rep: shallower than usual",
  FAST_DESCENT: "Last rep: fast descent",
  SHALLOW_PUSHUP: "Last rep: shallow push-up",
  HIPS_SAGGING: "Last rep: hips sagging",
  HIPS_PIKING: "Last rep: hips piking",
};

// Live cues and the last counted rep's form-risk flags are shown together so
// the panel never says "no corrections" while the rep card shows a flag.
export function CorrectionsFeed({
  corrections,
  repFlags = [],
}: {
  corrections: Correction[];
  repFlags?: string[];
}) {
  const flagItems: Correction[] = (repFlags ?? []).map((flag) => ({
    id: `rep_${flag}`,
    priority: 2,
    command: FLAG_TEXT[flag] ?? flag,
    display: FLAG_TEXT[flag] ?? flag,
    body_part: "FORM-RISK FLAG",
  }));
  corrections = [...(corrections ?? []), ...flagItems];
  if (!corrections.length) {
    return (
      <Card className="p-4">
        <CardEyebrow className="mb-2">Form Corrections</CardEyebrow>
        <p className="text-sm text-ink-muted flex items-center gap-1.5">
          <CheckCircle2 size={14} /> No live cues right now
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
