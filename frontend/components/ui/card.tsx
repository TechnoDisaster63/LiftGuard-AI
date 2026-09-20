import React from "react";
import { cn } from "@/lib/utils";

/**
 * Systematizes the `glass-panel accent-bar rounded-panel p-*` pattern that
 * was hand-typed on nearly every page. Same visual language, one place to
 * change it.
 */
export const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { accent?: boolean; raised?: boolean }
>(({ className, accent = true, raised = false, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      raised ? "glass-panel-raised" : "glass-panel",
      accent && "accent-bar",
      "rounded-panel p-5",
      className
    )}
    {...props}
  />
));
Card.displayName = "Card";

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center justify-between mb-3", className)} {...props} />
  )
);
CardHeader.displayName = "CardHeader";

export const CardTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("font-display text-lg text-ink", className)} {...props} />
  )
);
CardTitle.displayName = "CardTitle";

export const CardEyebrow = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p
      ref={ref}
      className={cn("text-[11px] font-mono uppercase tracking-wider text-ink-faint", className)}
      {...props}
    />
  )
);
CardEyebrow.displayName = "CardEyebrow";

export const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn(className)} {...props} />
);
CardContent.displayName = "CardContent";
