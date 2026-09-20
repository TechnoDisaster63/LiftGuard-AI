import Link from "next/link";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: React.ReactNode;
  message: string;
  actionLabel?: string;
  actionHref?: string;
  className?: string;
}

export function EmptyState({ icon, message, actionLabel, actionHref, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center text-center py-10 px-6", className)}>
      {icon && <div className="text-ink-faint mb-3">{icon}</div>}
      <p className="text-sm text-ink-muted">{message}</p>
      {actionLabel && actionHref && (
        <Link href={actionHref} className="text-sm text-brand hover:underline mt-2">
          {actionLabel} →
        </Link>
      )}
    </div>
  );
}
