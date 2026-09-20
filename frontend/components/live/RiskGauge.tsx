"use client";

import clsx from "clsx";

interface RiskGaugeProps {
  /** 0–100 combined injury risk index */
  value: number;
  /** 0=low 1=moderate 2=high 3=critical, mirrors risk_level from the engine */
  riskLevel: number;
  /** MC-Dropout uncertainty interval, 0–100 scale, shown as a shaded arc band */
  uncertaintyLower?: number;
  uncertaintyUpper?: number;
  label?: string;
}

const RISK_COLORS = ["#16D97B", "#F5A524", "#EF4444", "#FF1F5C"];
const RISK_LABELS = ["LOW", "MODERATE", "HIGH", "CRITICAL"];

// 270° instrument arc, like a lab dial — from -135deg to +135deg
const START_ANGLE = -135;
const SWEEP = 270;

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const start = polar(cx, cy, r, startDeg);
  const end = polar(cx, cy, r, endDeg);
  const largeArc = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
}

export function RiskGauge({
  value,
  riskLevel,
  uncertaintyLower,
  uncertaintyUpper,
  label = "INJURY RISK INDEX",
}: RiskGaugeProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const color = RISK_COLORS[Math.min(riskLevel, 3)] ?? RISK_COLORS[0];
  const valueAngle = START_ANGLE + (clamped / 100) * SWEEP;

  const cx = 100;
  const cy = 100;
  const r = 78;

  const ticks = Array.from({ length: 11 }, (_, i) => i * 10);

  return (
    <div className="flex flex-col items-center">
      <svg width="200" height="180" viewBox="0 0 200 180" className="overflow-visible">
        {/* Track */}
        <path
          d={arcPath(cx, cy, r, START_ANGLE, START_ANGLE + SWEEP)}
          fill="none"
          stroke="rgba(232,236,239,0.08)"
          strokeWidth={10}
          strokeLinecap="round"
        />

        {/* Uncertainty band (MC-Dropout interval) */}
        {uncertaintyLower !== undefined && uncertaintyUpper !== undefined && (
          <path
            d={arcPath(
              cx,
              cy,
              r,
              START_ANGLE + (Math.max(0, uncertaintyLower) / 100) * SWEEP,
              START_ANGLE + (Math.min(100, uncertaintyUpper) / 100) * SWEEP
            )}
            fill="none"
            stroke="#22D3EE"
            strokeOpacity={0.35}
            strokeWidth={14}
            strokeLinecap="round"
          />
        )}

        {/* Value arc */}
        <path
          d={arcPath(cx, cy, r, START_ANGLE, valueAngle)}
          fill="none"
          stroke={color}
          strokeWidth={10}
          strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 6px ${color}80)` }}
        />

        {/* Tick marks */}
        {ticks.map((t) => {
          const angle = START_ANGLE + (t / 100) * SWEEP;
          const inner = polar(cx, cy, r - 14, angle);
          const outer = polar(cx, cy, r - 8, angle);
          return (
            <line
              key={t}
              x1={inner.x}
              y1={inner.y}
              x2={outer.x}
              y2={outer.y}
              stroke="rgba(232,236,239,0.25)"
              strokeWidth={1.5}
            />
          );
        })}

        {/* Needle tip */}
        <circle
          cx={polar(cx, cy, r, valueAngle).x}
          cy={polar(cx, cy, r, valueAngle).y}
          r={4}
          fill={color}
        />

        {/* Center readout */}
        <text
          x={cx}
          y={cy - 4}
          textAnchor="middle"
          className="font-mono tabular"
          fontSize="30"
          fill="#E8ECEF"
        >
          {clamped.toFixed(1)}
        </text>
        <text
          x={cx}
          y={cy + 16}
          textAnchor="middle"
          className="font-mono"
          fontSize="10"
          fill="#8791A0"
          letterSpacing="1"
        >
          %
        </text>
      </svg>

      <p className="text-[11px] font-mono tracking-[0.15em] text-ink-faint -mt-2">{label}</p>
      <p
        className={clsx("text-xs font-display tracking-wide mt-1")}
        style={{ color }}
      >
        {RISK_LABELS[Math.min(riskLevel, 3)] ?? "—"}
      </p>
    </div>
  );
}
