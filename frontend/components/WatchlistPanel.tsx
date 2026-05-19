"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import type { PriceUpdate, SparklinePoint, WatchlistRow } from "@/lib/types";
import PriceCell from "./PriceCell";
import Sparkline from "./Sparkline";

interface WatchlistPanelProps {
  rows: WatchlistRow[];
  prices: Record<string, PriceUpdate>;
  sparklines: Record<string, SparklinePoint[]>;
  selected: string | null;
  onSelect: (ticker: string) => void;
  onChange: () => void;
}

export default function WatchlistPanel({
  rows,
  prices,
  sparklines,
  selected,
  onSelect,
  onChange,
}: WatchlistPanelProps) {
  const [newTicker, setNewTicker] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAdd = async () => {
    const t = newTicker.trim().toUpperCase();
    if (!t) return;
    setAdding(true);
    setError(null);
    try {
      await api.addWatchlist(t);
      setNewTicker("");
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add ticker");
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (ticker: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.removeWatchlist(ticker);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove");
    }
  };

  return (
    <aside
      data-testid="watchlist"
      className="flex flex-col w-full h-full bg-[color:var(--color-panel)] border-r border-[color:var(--color-border-soft)]"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-[color:var(--color-border-soft)]">
        <h2 className="text-xs uppercase tracking-[0.2em] text-[color:var(--color-text-muted)]">
          Watchlist
        </h2>
        <span className="text-[10px] text-[color:var(--color-text-muted)]">
          {rows.length} symbols
        </span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {rows.length === 0 && (
          <div className="px-4 py-8 text-center text-sm text-[color:var(--color-text-muted)]">
            No tickers yet. Add one below.
          </div>
        )}
        {rows.map((row) => {
          const live = prices[row.ticker];
          const price = live?.price ?? row.price;
          const changePct = live?.change_pct ?? row.change_pct;
          const direction = live?.direction ?? row.direction;
          const isSelected = row.ticker === selected;
          const pts = sparklines[row.ticker] || [];

          return (
            <div
              key={row.ticker}
              data-testid={`watchlist-ticker-${row.ticker}`}
              onClick={() => onSelect(row.ticker)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSelect(row.ticker);
              }}
              role="button"
              tabIndex={0}
              className={`w-full flex items-center justify-between px-4 py-2.5 border-l-2 row-hover text-left transition-colors cursor-pointer ${
                isSelected
                  ? "border-[color:var(--color-accent-yellow)] bg-[color:var(--color-card)]"
                  : "border-transparent"
              }`}
            >
              <div className="flex flex-col min-w-0">
                <span className="font-semibold text-sm text-[color:var(--color-text-bright)]">
                  {row.ticker}
                </span>
                <span
                  className={`text-[11px] tabular ${
                    changePct === null || changePct === undefined
                      ? "text-[color:var(--color-text-muted)]"
                      : changePct >= 0
                      ? "text-[color:var(--color-up-green)]"
                      : "text-[color:var(--color-down-red)]"
                  }`}
                >
                  {fmtPct(changePct)}
                </span>
              </div>

              <div className="flex items-center gap-3">
                <Sparkline
                  points={pts}
                  positive={(changePct ?? 0) >= 0}
                />
                <span data-testid={`price-${row.ticker}`}>
                  <PriceCell
                    price={price}
                    direction={direction}
                    className="text-sm font-medium"
                  />
                </span>
                <button
                  type="button"
                  onClick={(e) => handleRemove(row.ticker, e)}
                  data-testid={`watchlist-remove-${row.ticker}`}
                  aria-label={`Remove ${row.ticker}`}
                  className="text-[color:var(--color-text-muted)] hover:text-[color:var(--color-down-red)] text-base leading-none px-1 cursor-pointer bg-transparent border-0"
                >
                  ×
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="border-t border-[color:var(--color-border-soft)] p-3 space-y-2">
        <div className="flex gap-2">
          <input
            type="text"
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAdd();
            }}
            placeholder="Add ticker (e.g. PYPL)"
            data-testid="watchlist-add-input"
            className="flex-1 px-2 py-1.5 text-sm bg-[color:var(--color-terminal)] border border-[color:var(--color-border-soft)] rounded text-[color:var(--color-text-bright)] placeholder:text-[color:var(--color-text-muted)] focus:outline-none focus:border-[color:var(--color-accent-blue)]"
          />
          <button
            type="button"
            onClick={handleAdd}
            disabled={adding || !newTicker.trim()}
            data-testid="watchlist-add-submit"
            className="px-3 py-1.5 text-xs font-semibold bg-[color:var(--color-accent-blue)] text-white rounded hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            ADD
          </button>
        </div>
        {error && (
          <p className="text-xs text-[color:var(--color-down-red)]">{error}</p>
        )}
      </div>
    </aside>
  );
}
