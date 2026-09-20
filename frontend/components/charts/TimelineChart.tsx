"use client";

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

interface TimelineChartProps {
  data: number[];
  color?: string;
  unit?: string;
  height?: number;
}

export function TimelineChart({ data, color = "#7C5CFF", unit = "", height = 220 }: TimelineChartProps) {
  const points = data.map((v, i) => ({ i, v }));

  if (points.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm text-ink-faint font-mono"
        style={{ height }}
      >
        No data yet — run a live session first
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={points} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid stroke="rgba(232,236,239,0.06)" vertical={false} />
        <XAxis
          dataKey="i"
          tick={{ fill: "#4A5262", fontSize: 11, fontFamily: "var(--font-jetbrains-mono)" }}
          axisLine={{ stroke: "rgba(232,236,239,0.08)" }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: "#4A5262", fontSize: 11, fontFamily: "var(--font-jetbrains-mono)" }}
          axisLine={false}
          tickLine={false}
          width={36}
        />
        <Tooltip
          contentStyle={{
            background: "rgba(18,24,33,0.95)",
            border: "1px solid rgba(232,236,239,0.1)",
            borderRadius: 10,
            fontSize: 12,
            fontFamily: "var(--font-jetbrains-mono)",
          }}
          labelStyle={{ color: "#8791A0" }}
          formatter={(value: number) => [`${value.toFixed(2)}${unit}`, ""]}
        />
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
