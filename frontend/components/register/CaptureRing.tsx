"use client";

interface CaptureRingProps {
  progress: number; // 0–1
  sampleCount: number;
  size?: number;
}

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  if (endDeg - startDeg >= 359.999) endDeg = startDeg + 359.999; // avoid degenerate full-circle arc
  const start = polar(cx, cy, r, startDeg);
  const end = polar(cx, cy, r, endDeg);
  const largeArc = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
}

export function CaptureRing({ progress, sampleCount, size = 320 }: CaptureRingProps) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 6;
  const clamped = Math.max(0, Math.min(1, progress));

  return (
    <svg width={size} height={size} className="absolute inset-0 pointer-events-none">
      <path
        d={arcPath(cx, cy, r, 0, 360)}
        fill="none"
        stroke="rgba(232,236,239,0.1)"
        strokeWidth={4}
      />
      <path
        d={arcPath(cx, cy, r, 0, clamped * 360)}
        fill="none"
        stroke="#7C5CFF"
        strokeWidth={4}
        strokeLinecap="round"
        style={{ filter: "drop-shadow(0 0 8px rgba(124,92,255,0.6))" }}
      />
      <text
        x={cx}
        y={cy + 8}
        textAnchor="middle"
        className="font-mono tabular"
        fontSize="34"
        fill="#E8ECEF"
      >
        {sampleCount}
      </text>
      <text
        x={cx}
        y={cy + 32}
        textAnchor="middle"
        className="font-mono"
        fontSize="11"
        fill="#8791A0"
        letterSpacing="1"
      >
        SAMPLES
      </text>
    </svg>
  );
}
