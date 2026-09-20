"use client";

import React from "react";
import { motion, type HTMLMotionProps } from "framer-motion";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "outline-brand";
type Size = "sm" | "md" | "lg" | "icon";

export interface ButtonProps extends HTMLMotionProps<"button"> {
  variant?: Variant;
  size?: Size;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-brand text-white hover:bg-brand-bright shadow-glow-brand border border-transparent",
  secondary:
    "bg-panel-raised text-ink border border-border hover:border-border-strong hover:bg-white/[0.04]",
  danger:
    "bg-risk-high/15 text-risk-high border border-risk-high/30 hover:bg-risk-high/25",
  ghost:
    "bg-transparent text-ink-muted border border-transparent hover:text-ink hover:bg-white/[0.04]",
  "outline-brand":
    "bg-transparent text-brand border border-brand/30 hover:bg-brand/10",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "px-3 py-1.5 text-xs gap-1.5",
  md: "px-4 py-2 text-sm gap-2",
  lg: "px-5 py-2.5 text-sm gap-2",
  icon: "w-9 h-9 p-0 justify-center",
};

/**
 * The app's single button primitive. Every page previously hand-wrote its
 * own `flex items-center gap-2 px-4 py-2 rounded-control ...` className —
 * this centralizes that so variant/size changes propagate everywhere at
 * once instead of needing a find-and-replace sweep.
 */
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "secondary", size = "md", ...props }, ref) => {
    return (
      <motion.button
        ref={ref}
        whileTap={{ scale: 0.96 }}
        className={cn(
          "press-scale inline-flex items-center rounded-control font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
          VARIANT_CLASSES[variant],
          SIZE_CLASSES[size],
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
