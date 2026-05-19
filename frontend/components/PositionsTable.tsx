"use client";

import { fmtCurrency, fmtPct, fmtQty } from "@/lib/format";
import type { Position, PriceUpdate } from "@/lib/types";
import PriceCell from "./PriceCell";

interface PositionsTableProps {
  positions: Position[];
  prices: Record<string, PriceUpdate>;
  onSelect?: (ticker: string) => void;
}

export default function PositionsTable({
  positions,
  prices,
  onSelect,
}: PositionsTableProps) {
  return (
    <div
      data-testid="positions-table"
      className="flex flex-col h-full bg-[color:var(--color-panel)] border border-[color:var(--color-border-soft)] rounded overflow-hidden"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-[color:var(--color-border-soft)]">
        <h3 className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-muted)]">
          Positions
        </h3>
        <span className="text-[10px] text-[color:var(--color-text-muted)]">
          {positions.length} open
        </span>
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[color:var(--color-panel)]">
            <tr className="text-left text-[10px] uppercase tracking-wider text-[color:var(--color-text-muted)]">
              <th className="px-3 py-2 font-medium">Ticker</th>
              <th className="px-3 py-2 font-medium text-right">Qty</th>
              <th className="px-3 py-2 font-medium text-right">Avg Cost</th>
              <th className="px-3 py-2 font-medium text-right">Price</th>
              <th className="px-3 py-2 font-medium text-right">P&L</th>
              <th className="px-3 py-2 font-medium text-right">P&L %</th>
            </tr>
          </thead>
          <tbody>
            {positions.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="px-3 py-6 text-center text-[color:var(--color-text-muted)]"
                >
                  No open positions. Use the trade bar or chat to buy.
                </td>
              </tr>
            )}
            {positions.map((p) => {
              const live = prices[p.ticker]?.price ?? p.current_price;
              const livePnl = (live - p.avg_cost) * p.quantity;
              const livePnlPct =
                p.avg_cost > 0
                  ? ((live - p.avg_cost) / p.avg_cost) * 100
                  : 0;
              const pnlClass =
                livePnl >= 0
                  ? "text-[color:var(--color-up-green)]"
                  : "text-[color:var(--color-down-red)]";
              return (
                <tr
                  key={p.ticker}
                  data-testid={`position-${p.ticker}`}
                  onClick={() => onSelect?.(p.ticker)}
                  className="row-hover border-t border-[color:var(--color-border-soft)] cursor-pointer"
                >
                  <td className="px-3 py-2 font-semibold text-[color:var(--color-text-bright)]">
                    {p.ticker}
                  </td>
                  <td className="px-3 py-2 text-right tabular">
                    {fmtQty(p.quantity)}
                  </td>
                  <td className="px-3 py-2 text-right tabular">
                    {fmtCurrency(p.avg_cost)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <PriceCell price={live} />
                  </td>
                  <td className={`px-3 py-2 text-right tabular ${pnlClass}`}>
                    {livePnl >= 0 ? "+" : ""}
                    {fmtCurrency(livePnl)}
                  </td>
                  <td className={`px-3 py-2 text-right tabular ${pnlClass}`}>
                    {fmtPct(livePnlPct)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
