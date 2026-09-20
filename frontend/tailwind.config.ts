import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        void: "#050608",
        panel: "#10131A",
        "panel-raised": "#151922",
        border: {
          DEFAULT: "rgba(237, 239, 243, 0.09)",
          strong: "rgba(237, 239, 243, 0.18)",
        },
        ink: {
          DEFAULT: "#EDEFF3",
          muted: "#8B93A3",
          faint: "#4A5262",
        },
        // Brand: the app's own interactive/identity color -- deliberately
        // NOT reused for risk semantics anymore (it was accidentally the
        // same hex as "safe risk" before, which muddied the meaning of
        // both). Violet reads as "LiftGuard AI is doing something", not
        // "you are safe".
        brand: {
          DEFAULT: "#7C5CFF",
          dim: "#4C3BA0",
          bright: "#9B82FF",
          glow: "rgba(124, 92, 255, 0.4)",
        },
        // Risk: purely data-driven, independent palette from brand.
        risk: {
          low: "#16D97B",
          moderate: "#F5A524",
          high: "#EF4444",
          critical: "#FF1F5C",
        },
        uncertainty: "#22D3EE",
      },
      fontFamily: {
        display: ["var(--font-space-grotesk)", "sans-serif"],
        body: ["var(--font-inter)", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
      },
      boxShadow: {
        glass: "0 8px 32px rgba(0, 0, 0, 0.5)",
        "glow-brand": "0 0 28px rgba(124, 92, 255, 0.35)",
        "glow-risk": "0 0 28px rgba(239, 68, 68, 0.35)",
        sharp: "4px 4px 0 0 rgba(124, 92, 255, 0.15)",
      },
      backdropBlur: {
        glass: "20px",
      },
      borderRadius: {
        panel: "6px",
        control: "4px",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { transform: "scale(0.95)", opacity: "0.6" },
          "70%": { transform: "scale(1.15)", opacity: "0" },
          "100%": { transform: "scale(0.95)", opacity: "0" },
        },
        "fade-slide-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-glow": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
        "gradient-shift": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-400px 0" },
          "100%": { backgroundPosition: "400px 0" },
        },
        "toast-in": {
          "0%": { opacity: "0", transform: "translateX(16px) scale(0.96)" },
          "100%": { opacity: "1", transform: "translateX(0) scale(1)" },
        },
        "border-sweep": {
          "0%": { backgroundPosition: "0% 0%" },
          "100%": { backgroundPosition: "200% 0%" },
        },
      },
      animation: {
        "pulse-ring": "pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-slide-up": "fade-slide-up 0.4s ease-out",
        "pulse-ring-slow": "pulse-glow 1.6s ease-in-out infinite",
        "gradient-shift": "gradient-shift 8s ease infinite",
        shimmer: "shimmer 1.6s linear infinite",
        "toast-in": "toast-in 0.25s cubic-bezier(0.16, 1, 0.3, 1)",
        "border-sweep": "border-sweep 3s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
