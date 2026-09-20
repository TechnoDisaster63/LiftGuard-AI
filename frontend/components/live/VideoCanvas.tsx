"use client";

import { Loader2, WifiOff } from "lucide-react";
import clsx from "clsx";
import { VideoHUD } from "./VideoHUD";
import { SparklesCore } from "@/components/ui/sparkles";
import type { TelemetryPayload } from "@/lib/ws";

interface VideoCanvasProps {
  frameUrl: string | null;
  connectionState: "idle" | "connecting" | "open" | "closed" | "error";
  telemetry: TelemetryPayload | null;
}

export function VideoCanvas({ frameUrl, connectionState, telemetry }: VideoCanvasProps) {
  const highRisk = telemetry?.risk_level === 3;

  return (
    <div
      className={clsx(
        "relative w-full aspect-video rounded-panel overflow-hidden glass-panel-raised scan-surface transition-shadow duration-300",
        highRisk && "animate-pulse-ring-slow"
      )}
      style={
        highRisk
          ? { boxShadow: "0 0 0 2px #EF4444, 0 0 32px 4px rgba(239,68,68,0.45)" }
          : undefined
      }
    >
      {frameUrl ? (
        // The backend draws ONLY the pose skeleton + correction highlights
        // here (see liftguard_engine.py's _draw_web_frame) — genuinely
        // pixel-tied CV output. Everything else that used to be baked into
        // the frame as OpenCV text/panels is now the VideoHUD overlay below,
        // driven by the same telemetry data as real HTML/CSS.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={frameUrl}
          alt="Live pose analysis feed"
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="relative w-full h-full flex flex-col items-center justify-center gap-3 text-ink-faint">
          {connectionState === "idle" && (
            <div className="absolute inset-0">
              <SparklesCore
                background="transparent"
                minSize={0.3}
                maxSize={0.9}
                particleDensity={35}
                particleColor="#7C5CFF"
                speed={1}
                className="w-full h-full"
              />
            </div>
          )}
          <div className="relative flex flex-col items-center gap-3">
            {connectionState === "connecting" ? (
              <>
                <Loader2 className="animate-spin" size={28} strokeWidth={1.5} />
                <p className="text-sm font-mono">Connecting to camera…</p>
              </>
            ) : connectionState === "error" || connectionState === "closed" ? (
              <>
                <WifiOff size={28} strokeWidth={1.5} />
                <p className="text-sm font-mono">No live session</p>
              </>
            ) : (
              <p className="text-sm font-mono">Start a session to begin</p>
            )}
          </div>
        </div>
      )}

      {frameUrl && <VideoHUD telemetry={telemetry} />}

      {highRisk && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none">
          <span className="px-3 py-1.5 rounded-control bg-risk-high/15 border border-risk-high/50 text-risk-high text-xs font-display tracking-wider animate-pulse-ring">
            HIGH RISK
          </span>
        </div>
      )}

      {telemetry?.feedback_message && frameUrl && (
        <div className="absolute bottom-20 left-4 right-4 glass-panel rounded-control px-4 py-2">
          <p className="text-sm text-ink font-body">{telemetry.feedback_message}</p>
        </div>
      )}

      {/* Connection indicator — small and out of the way of the identity/badge chips */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5">
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            connectionState === "open" ? "bg-brand animate-pulse-ring" : "bg-ink-faint"
          }`}
        />
        <span className="text-[10px] font-mono uppercase tracking-wider text-ink-faint">
          {connectionState === "open" ? "Live" : connectionState}
        </span>
      </div>
    </div>
  );
}
