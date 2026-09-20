import { cn } from "@/lib/utils";

type BadgeTone = "brand" | "low" | "moderate" | "high" | "critical" | "neutral";

const TONE_CLASSES: Record<BadgeTone, string> = {
  brand: "text-brand border-brand/30 bg-brand/10",
  low: "text-risk-low border-risk-low/30 bg-risk-low/10",
  moderate: "text-risk-moderate border-risk-moderate/30 bg-risk-moderate/10",
  high: "text-risk-high border-risk-high/30 bg-risk-high/10",
  critical: "text-risk-critical border-risk-critical/30 bg-risk-critical/10",
  neutral: "text-ink-faint border-border bg-white/[0.02]",
};

export function Badge({
  children,
  tone = "neutral",
  className,
  dot,
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-1 rounded-control border text-[10px] font-mono uppercase tracking-wide",
        TONE_CLASSES[tone],
        className
      )}
    >
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function riskToneFromLevel(level: number): BadgeTone {
  if (level >= 3) return "critical";
  if (level === 2) return "high";
  if (level === 1) return "moderate";
  return "low";
}
