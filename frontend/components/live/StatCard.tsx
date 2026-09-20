import { Card, CardEyebrow } from "@/components/ui/card";

interface StatCardProps {
  label: string;
  value: string | number;
  unit?: string;
  accent?: "clinical" | "amber" | "red" | "neutral";
  icon?: React.ReactNode;
}

const ACCENT_TEXT: Record<string, string> = {
  clinical: "text-brand",
  amber: "text-risk-moderate",
  red: "text-risk-high",
  neutral: "text-ink",
};

export function StatCard({ label, value, unit, accent = "neutral", icon }: StatCardProps) {
  return (
    <Card className="p-4 flex flex-col gap-2 animate-fade-slide-up" accent={false}>
      <div className="flex items-center justify-between">
        <CardEyebrow>{label}</CardEyebrow>
        {icon && <span className="text-ink-faint">{icon}</span>}
      </div>
      <p className={`font-display text-2xl tabular ${ACCENT_TEXT[accent]}`}>
        {value}
        {unit && <span className="text-sm text-ink-faint ml-1 font-body">{unit}</span>}
      </p>
    </Card>
  );
}
