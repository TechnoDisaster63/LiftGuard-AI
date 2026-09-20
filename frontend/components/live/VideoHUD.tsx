"use client";

import { Mic, MicOff, Zap, ZapOff, Video, Activity } from "lucide-react";
import type { TelemetryPayload } from "@/lib/ws";

const ID_STATE_STYLE: Record<string, { color: string; label: string }> = {
  identified: { color: "#7C5CFF", label: "IDENTIFIED" },
  confirming: { color: "#F5A524", label: "CONFIRMING…" },
  scanning: { color: "#F5A524", label: "SCANNING…" },
  guest: { color: "#4A5262", label: "GUEST" },
  not_started: { color: "#4A5262", label: "AWAITING ID" },
};

function initialsOf(name: string) {
  return name
    .split(" ")
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

function spineColor(deg: number) {
  if (deg < 25) return "#16D97B";
  if (deg < 35) return "#F5A524";
  if (deg < 50) return "#F5A524";
  return "#EF4444";
}

/** Small glass pill used for the status-badge row (was cv2 rectangles + text) */
function Badge({ label, color, icon }: { label: string; color: string; icon?: React.ReactNode }) {
  return (
    <div
      className="flex items-center gap-1 px-2 py-1 rounded-control text-[10px] font-mono tracking-wide"
      style={{
        color,
        background: "rgba(10,14,19,0.55)",
        border: `1px solid ${color}40`,
      }}
    >
      {icon}
      {label}
    </div>
  );
}

export function VideoHUD({ telemetry }: { telemetry: TelemetryPayload | null }) {
  if (!telemetry) return null;

  const idState = ID_STATE_STYLE[telemetry.id_state] ?? ID_STATE_STYLE.not_started;
  const name = telemetry.user?.display_name;

  return (
    <>
      {/* Top-left: identity chip (was _draw_user_panel) */}
      <div className="absolute top-4 left-4 flex items-center gap-2.5 glass-panel rounded-panel pl-2 pr-3 py-2">
        <div
          className="w-8 h-8 rounded-full grid place-items-center text-[11px] font-display shrink-0"
          style={{ background: idState.color, color: "#050608" }}
        >
          {name ? initialsOf(name) : "G"}
        </div>
        <div>
          <p className="text-xs text-ink leading-tight">{name ?? "Guest Mode"}</p>
          <p className="text-[10px] font-mono leading-tight" style={{ color: idState.color }}>
            {idState.label}
          </p>
        </div>
      </div>

      {/* Top-right: status badges (was _draw_status_badges) */}
      <div className="absolute top-4 right-4 flex items-center gap-1.5">
        <Badge
          label={typeof telemetry.camera_id === "string" ? "IP" : `CAM ${telemetry.camera_id}`}
          color="#8791A0"
          icon={<Video size={11} />}
        />
        <Badge
          label={telemetry.voice_enabled ? (telemetry.voice_speaking ? "TALKING" : "VOICE") : "MUTED"}
          color={telemetry.voice_enabled ? "#7C5CFF" : "#4A5262"}
          icon={telemetry.voice_enabled ? <Mic size={11} /> : <MicOff size={11} />}
        />
        <Badge
          label={
            telemetry.arduino_connected
              ? telemetry.arduino_calibrated
                ? "LASER AUTO"
                : "LASER"
              : "NO LASER"
          }
          color={telemetry.arduino_connected ? "#7C5CFF" : "#4A5262"}
          icon={telemetry.arduino_connected ? <Zap size={11} /> : <ZapOff size={11} />}
        />
        {telemetry.fps !== null && (
          <Badge label={`${telemetry.fps.toFixed(0)} FPS`} color="#8791A0" icon={<Activity size={11} />} />
        )}
      </div>

      {/* Bottom-left: biomechanics readout (bottom of the old risk panel) */}
      {(telemetry.spine_flexion !== null || telemetry.hip_hinge_angle !== null) && (
        <div className="absolute bottom-4 left-4 glass-panel rounded-panel px-3 py-2 flex gap-4">
          {telemetry.spine_flexion !== null && (
            <div>
              <p className="text-[9px] font-mono text-ink-faint uppercase tracking-wider">Spine</p>
              <p
                className="text-sm font-mono tabular"
                style={{ color: spineColor(telemetry.spine_flexion) }}
              >
                {telemetry.spine_flexion.toFixed(1)}°
              </p>
            </div>
          )}
          {telemetry.hip_hinge_angle !== null && (
            <div>
              <p className="text-[9px] font-mono text-ink-faint uppercase tracking-wider">Hip</p>
              <p className="text-sm font-mono tabular text-ink-muted">
                {telemetry.hip_hinge_angle.toFixed(1)}°
              </p>
            </div>
          )}
          {telemetry.stability_index !== null && (
            <div>
              <p className="text-[9px] font-mono text-ink-faint uppercase tracking-wider">Stability</p>
              <p className="text-sm font-mono tabular text-ink-muted">
                {telemetry.stability_index.toFixed(2)}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Bottom-right: reps + phase (was part of _draw_exercise_panel) */}
      {telemetry.exercise_status?.exercise ? (
        <div className="absolute bottom-4 right-4 glass-panel rounded-panel px-3 py-2 flex items-center gap-3">
          <div className="text-right">
            <p className="text-[9px] font-mono text-ink-faint uppercase tracking-wider">
              {String(telemetry.exercise_status.exercise)}
            </p>
            <p className="text-lg font-display tabular text-brand leading-none mt-0.5">
              {String(telemetry.exercise_status.rep_count ?? 0)} reps
            </p>
          </div>
          {telemetry.exercise_status.phase_display ? (
            <span className="text-xl">{String(telemetry.exercise_status.phase_display)}</span>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
