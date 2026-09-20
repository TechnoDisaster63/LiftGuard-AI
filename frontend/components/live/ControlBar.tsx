"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Mic, MicOff, Zap, ZapOff, FlipHorizontal2, RotateCcw, Download,
  Crosshair, Cpu, Save, Gauge, Wifi, Video, ChevronDown,
} from "lucide-react";
import clsx from "clsx";

interface ControlBarProps {
  voiceEnabled: boolean;
  arduinoConnected: boolean;
  mirrorMode: boolean;
  calibrationMode: boolean;
  usingTemporal: boolean;
  processEveryN: number;
  onAction: (action: string) => void;
}

function DeckButton({
  active,
  onClick,
  icon,
  label,
  variant = "default",
}: {
  active?: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  variant?: "default" | "danger";
}) {
  return (
    <motion.button
      onClick={onClick}
      whileTap={{ scale: 0.94 }}
      whileHover={{ y: -1 }}
      className={clsx(
        "press-scale flex flex-col items-center justify-center gap-1.5 px-3 py-2.5 rounded-control border min-w-[74px]",
        active
          ? variant === "danger"
            ? "border-risk-high/40 bg-risk-high/10 text-risk-high"
            : "border-brand/40 bg-brand/10 text-brand shadow-glow-brand"
          : "border-border text-ink-muted hover:text-ink hover:border-border-strong"
      )}
    >
      {icon}
      <span className="text-[10px] font-mono tracking-wide">{label}</span>
    </motion.button>
  );
}

export function ControlBar({
  voiceEnabled,
  arduinoConnected,
  mirrorMode,
  calibrationMode,
  usingTemporal,
  processEveryN,
  onAction,
}: ControlBarProps) {
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraSource, setCameraSource] = useState<string>("cam0");

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel accent-bar rounded-panel p-4 pl-5"
    >
      <div className="flex items-center justify-between mb-3">
        <p className="text-[11px] font-mono uppercase tracking-wider text-ink-faint">
          Control Deck
        </p>
        <p className="text-[10px] font-mono text-ink-faint">
          every {processEveryN} frame{processEveryN > 1 ? "s" : ""}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <DeckButton
          active={voiceEnabled}
          onClick={() => onAction("toggle_voice")}
          icon={voiceEnabled ? <Mic size={16} /> : <MicOff size={16} />}
          label="VOICE"
        />
        <DeckButton
          active={arduinoConnected}
          onClick={() => onAction("toggle_arduino")}
          icon={arduinoConnected ? <Zap size={16} /> : <ZapOff size={16} />}
          label="LASER"
        />
        <DeckButton
          active={mirrorMode}
          onClick={() => onAction("toggle_mirror")}
          icon={<FlipHorizontal2 size={16} />}
          label="MIRROR"
        />
        <DeckButton
          active={usingTemporal}
          onClick={() => onAction("toggle_temporal")}
          icon={<Cpu size={16} />}
          label={usingTemporal ? "TCN" : "FRAME"}
        />
        <DeckButton
          active={calibrationMode}
          onClick={() => onAction(calibrationMode ? "complete_calibration" : "start_calibration")}
          icon={<Crosshair size={16} />}
          label={calibrationMode ? "FINISH CAL" : "CALIBRATE"}
        />

        <div className="w-px self-stretch bg-border mx-1" />

        <DeckButton
          onClick={() => onAction("speed_down")}
          icon={<Gauge size={16} />}
          label="SLOWER"
        />
        <DeckButton
          onClick={() => onAction("speed_up")}
          icon={<Gauge size={16} className="-scale-x-100" />}
          label="FASTER"
        />
        <DeckButton
          onClick={() => onAction("reset_reps")}
          icon={<RotateCcw size={16} />}
          label="RESET"
        />
        <DeckButton
          onClick={() => onAction("save_model")}
          icon={<Save size={16} />}
          label="SAVE"
        />
        <DeckButton
          onClick={() => onAction("export_data")}
          icon={<Download size={16} />}
          label="EXPORT"
        />

        {/* Camera source — its own small dropdown since it has multiple targets */}
        <div className="relative">
          <motion.button
            whileTap={{ scale: 0.94 }}
            whileHover={{ y: -1 }}
            onClick={() => setCameraOpen((o) => !o)}
            className={clsx(
              "press-scale flex flex-col items-center justify-center gap-1.5 px-3 py-2.5 rounded-control border min-w-[74px]",
              cameraOpen || cameraSource !== "cam0"
                ? "border-brand/40 bg-brand/10 text-brand shadow-glow-brand"
                : "border-border text-ink-muted hover:text-ink hover:border-border-strong"
            )}
          >
            <div className="flex items-center gap-1 relative">
              {cameraSource === "ip" ? <Wifi size={16} /> : <Video size={16} />}
              <span
                className={clsx(
                  "absolute -top-0.5 -right-1.5 w-1.5 h-1.5 rounded-full",
                  cameraOpen || cameraSource !== "cam0" ? "bg-brand animate-pulse-ring-slow" : "bg-ink-faint"
                )}
              />
              <ChevronDown size={11} className={clsx("transition-transform", cameraOpen && "rotate-180")} />
            </div>
            <span className="text-[10px] font-mono tracking-wide">
              {cameraSource === "ip" ? "IP CAM" : `CAM ${cameraSource.replace("cam", "")}`}
            </span>
          </motion.button>

          {cameraOpen && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="absolute bottom-full mb-2 left-0 glass-panel-raised rounded-control p-1.5 flex flex-col gap-1 w-36 z-10"
            >
              {[0, 1, 2].map((id) => (
                <button
                  key={id}
                  onClick={() => { setCameraSource(`cam${id}`); onAction(`switch_camera:${id}`); setCameraOpen(false); }}
                  className={clsx(
                    "flex items-center gap-2 px-2.5 py-1.5 rounded-control text-xs text-left transition-colors",
                    cameraSource === `cam${id}`
                      ? "text-brand bg-brand/10"
                      : "text-ink-muted hover:text-ink hover:bg-white/[0.04]"
                  )}
                >
                  <Video size={13} /> Camera {id}
                </button>
              ))}
              <button
                onClick={() => { setCameraSource("ip"); onAction("connect_ip_camera"); setCameraOpen(false); }}
                className={clsx(
                  "flex items-center gap-2 px-2.5 py-1.5 rounded-control text-xs text-left border-t border-border pt-2 transition-colors",
                  cameraSource === "ip"
                    ? "text-brand bg-brand/10"
                    : "text-ink-muted hover:text-ink hover:bg-white/[0.04]"
                )}
              >
                <Wifi size={13} /> IP Camera
              </button>
            </motion.div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
