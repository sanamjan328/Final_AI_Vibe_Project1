"use client";

import type { SparklinePoint } from "@/lib/types";

interface SparklineProps {
  points: SparklinePoint[];
  width?: number;
  height?: number;
  positive?: boolean;
}

export default function Sparkline({
  points,
  width = 80,
  height = 24,
  positive,
}: SparklineProps) {
  if (!points || points.length < 2) {
    return (
      <svg width={width} height={height} className="opacity-30">
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="currentColor"
          strokeWidth={1}
          strokeDasharray="2,2"
        />
      </svg>
    );
  }

  const ys = points.map((p) => p.p);
  const min = Math.min(...ys);
  const max = Math.max(...ys);
  const range = max - min || 1;

  const stepX = width / (points.length - 1);
  const path = points
    .map((p, i) => {
      const x = i * stepX;
      const y = height - ((p.p - min) / range) * (height - 4) - 2;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const isUp =
    positive ?? points[points.length - 1].p >= points[0].p;
  const stroke = isUp ? "#26a641" : "#da3633";

  return (
    <svg width={width} height={height} className="block">
      <path
        d={path}
        fill="none"
        stroke={stroke}
        strokeWidth={1.25}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
