"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { usePriceStream } from "@/hooks/usePriceStream";
import type { Portfolio, WatchlistRow } from "@/lib/types";

import Header from "@/components/Header";
import WatchlistPanel from "@/components/WatchlistPanel";
import MainChart from "@/components/MainChart";
import PortfolioHeatmap from "@/components/PortfolioHeatmap";
import PnLChart from "@/components/PnLChart";
import PositionsTable from "@/components/PositionsTable";
import TradeBar from "@/components/TradeBar";
import ChatPanel from "@/components/ChatPanel";

const DEFAULT_TICKER = "AAPL";

export default function Page() {
  const { prices, sparklines, status } = usePriceStream();

  const [watchlist, setWatchlist] = useState<WatchlistRow[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const refreshWatchlist = useCallback(async () => {
    try {
      const data = await api.getWatchlist();
      setWatchlist(data);
      setSelected((s) => {
        if (s && data.some((r) => r.ticker === s)) return s;
        if (data.length > 0) {
          const fallback = data.find((r) => r.ticker === DEFAULT_TICKER);
          return fallback ? fallback.ticker : data[0].ticker;
        }
        return null;
      });
    } catch {
      // backend not ready
    }
  }, []);

  const refreshPortfolio = useCallback(async () => {
    try {
      const data = await api.getPortfolio();
      setPortfolio(data);
    } catch {
      // backend not ready
    }
  }, []);

  useEffect(() => {
    refreshWatchlist();
    refreshPortfolio();
    const id = setInterval(refreshPortfolio, 10_000);
    return () => clearInterval(id);
  }, [refreshWatchlist, refreshPortfolio]);

  const selectedPrice = useMemo(() => {
    if (!selected) return null;
    return prices[selected]?.price ?? null;
  }, [prices, selected]);

  const selectedChangePct = useMemo(() => {
    if (!selected) return null;
    return prices[selected]?.change_pct ?? null;
  }, [prices, selected]);

  const totalValue = useMemo(() => {
    if (!portfolio) return null;
    const cash = portfolio.cash_balance;
    const positionsValue = portfolio.positions.reduce((acc, p) => {
      const livePrice = prices[p.ticker]?.price ?? p.current_price;
      return acc + p.quantity * livePrice;
    }, 0);
    return cash + positionsValue;
  }, [portfolio, prices]);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header
        totalValue={totalValue}
        cashBalance={portfolio?.cash_balance ?? null}
        status={status}
      />

      <div className="flex flex-1 min-h-0">
        {/* Left: Watchlist */}
        <div className="w-[280px] shrink-0 h-full">
          <WatchlistPanel
            rows={watchlist}
            prices={prices}
            sparklines={sparklines}
            selected={selected}
            onSelect={setSelected}
            onChange={refreshWatchlist}
          />
        </div>

        {/* Center: chart, trade bar, positions */}
        <main className="flex flex-col flex-1 min-w-0 min-h-0">
          <div className="relative flex flex-col flex-1 min-h-0 border-b border-[color:var(--color-border-soft)]">
            <MainChart
              ticker={selected}
              points={selected ? sparklines[selected] || [] : []}
              currentPrice={selectedPrice}
              changePct={selectedChangePct}
            />
          </div>

          <div className="p-3 space-y-3 shrink-0">
            <TradeBar
              selectedTicker={selected}
              currentPrice={selectedPrice}
              onTradeComplete={() => {
                refreshPortfolio();
              }}
            />
          </div>

          <div className="flex gap-3 px-3 pb-3 min-h-[260px] max-h-[320px]">
            <div className="flex-[2] min-w-0">
              <PositionsTable
                positions={portfolio?.positions ?? []}
                prices={prices}
                onSelect={setSelected}
              />
            </div>
            <div className="flex-1 min-w-[200px]">
              <PortfolioHeatmap
                positions={portfolio?.positions ?? []}
                totalValue={totalValue ?? 0}
              />
            </div>
            <div className="flex-1 min-w-[220px]">
              <PnLChart />
            </div>
          </div>
        </main>

        {/* Right: Chat */}
        <div className="w-[340px] shrink-0 h-full">
          <ChatPanel onActionsExecuted={() => {
            refreshPortfolio();
            refreshWatchlist();
          }} />
        </div>
      </div>
    </div>
  );
}
