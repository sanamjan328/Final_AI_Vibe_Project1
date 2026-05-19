"use client";

import type { Position } from "@/lib/types";

interface PortfolioHeatmapProps {
  positions: Position[];
  totalValue: number;
}

function pnlColor(pnlPct: number): string {
  const clamped = Math.max(-10, Math.min(10, pnlPct));
  const intensity = Math.abs(clamped) / 10;
  const alpha = 0.25 + intensity * 0.55;
  if (clamped >= 0) {
    return `rgba(38, 166, 65, ${alpha.toFixed(3)})`;
  }
  return `rgba(218, 54, 51, ${alpha.toFixed(3)})`;
}

interface Tile {
  ticker: string;
  weight: number;
  pnlPct: number;
  value: number;
}

// Simple squarified-ish layout — sort by weight desc, lay out as flexbox rows.
function buildRows(tiles: Tile[]): Tile[][] {
  if (tiles.length === 0) return [];
  const sorted = [...tiles].sort((a, b) => b.weight - a.weight);

  // Heuristic: rows of 2-3 tiles depending on count
  const perRow = Math.max(1, Math.min(3, Math.ceil(Math.sqrt(sorted.length))));
  const rows: Tile[][] = [];
  for (let i = 0; i < sorted.length; i += perRow) {
    rows.push(sorted.slice(i, i + perRow));
  }
  return rows;
}

export default function PortfolioHeatmap({
  positions,
  totalValue,
}: PortfolioHeatmapProps) {
  const tiles: Tile[] = positions
    .filter((p) => p.quantity > 0)
    .map((p) => {
      const value = p.quantity * p.current_price;
      return {
        ticker: p.ticker,
        value,
        weight: totalValue > 0 ? value / totalValue : 0,
        pnlPct: p.pnl_pct,
      };
    });

  const rows = buildRows(tiles);
  const totalRowWeight = rows.map((r) =>
    r.reduce((acc, t) => acc + t.weight, 0)
  );
  const sumWeight = totalRowWeight.reduce((a, b) => a + b, 0) || 1;

  return (
    <div
      data-testid="portfolio-heatmap"
      className="flex flex-col h-full bg-[color:var(--color-panel)] border border-[color:var(--color-border-soft)] rounded"
    >
      <div className="px-3 py-2 border-b border-[color:var(--color-border-soft)]">
        <h3 className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-muted)]">
          Heatmap
        </h3>
      </div>
      <div className="flex-1 flex flex-col gap-[2px] p-[2px] min-h-0">
        {tiles.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-xs text-[color:var(--color-text-muted)]">
            No positions yet
          </div>
        ) : (
          rows.map((row, i) => (
            <div
              key={i}
              className="flex gap-[2px] min-h-0"
              style={{
                flexBasis: `${(totalRowWeight[i] / sumWeight) * 100}%`,
              }}
            >
              {row.map((tile) => {
                const rowSum = totalRowWeight[i] || 1;
                const widthPct = (tile.weight / rowSum) * 100;
                return (
                  <div
                    key={tile.ticker}
                    data-testid={`heatmap-cell-${tile.ticker}`}
                    className="flex flex-col items-center justify-center rounded-sm overflow-hidden text-center"
                    style={{
                      flexBasis: `${widthPct}%`,
                      backgroundColor: pnlColor(tile.pnlPct),
                    }}
                    title={`${tile.ticker} · ${(tile.weight * 100).toFixed(1)}% · ${
                      tile.pnlPct >= 0 ? "+" : ""
                    }${tile.pnlPct.toFixed(2)}%`}
                  >
                    <span className="text-xs font-semibold text-white leading-tight">
                      {tile.ticker}
                    </span>
                    <span className="text-[10px] text-white/85 tabular">
                      {tile.pnlPct >= 0 ? "+" : ""}
                      {tile.pnlPct.toFixed(2)}%
                    </span>
                  </div>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
