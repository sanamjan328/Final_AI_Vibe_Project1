"use client";

import { useEffect, useRef } from "react";
import type { SparklinePoint } from "@/lib/types";

interface MainChartProps {
  ticker: string | null;
  points: SparklinePoint[];
  currentPrice: number | null;
  changePct: number | null;
}

export default function MainChart({
  ticker,
  points,
  currentPrice,
  changePct,
}: MainChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  // chart and series refs are loosely typed because lightweight-charts is dynamic-imported
  // and we only need a minimal subset of its API here.
  const chartRef = useRef<unknown>(null);
  const seriesRef = useRef<unknown>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    let cleanup = () => {};
    let cancelled = false;

    (async () => {
      const lib = await import("lightweight-charts");
      if (cancelled || !containerRef.current) return;

      const chart = lib.createChart(containerRef.current, {
        layout: {
          background: { color: "#0d1117" },
          textColor: "#8b949e",
          fontFamily:
            'ui-monospace, "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
        },
        grid: {
          vertLines: { color: "#21262d" },
          horzLines: { color: "#21262d" },
        },
        rightPriceScale: {
          borderColor: "#30363d",
        },
        timeScale: {
          borderColor: "#30363d",
          timeVisible: true,
          secondsVisible: true,
        },
        crosshair: {
          mode: 1,
        },
        autoSize: true,
      });

      const series = chart.addSeries(lib.LineSeries, {
        color: "#209dd7",
        lineWidth: 2,
        priceLineColor: "#ecad0a",
        priceLineWidth: 1,
      });

      chartRef.current = chart;
      seriesRef.current = series;

      const resize = () => {
        if (containerRef.current) {
          chart.applyOptions({
            width: containerRef.current.clientWidth,
            height: containerRef.current.clientHeight,
          });
        }
      };
      resize();
      const ro = new ResizeObserver(resize);
      ro.observe(containerRef.current);

      cleanup = () => {
        ro.disconnect();
        chart.remove();
        chartRef.current = null;
        seriesRef.current = null;
      };
    })();

    return () => {
      cancelled = true;
      cleanup();
    };
  }, []);

  useEffect(() => {
    const series = seriesRef.current as
      | { setData: (data: { time: number; value: number }[]) => void }
      | null;
    if (!series) return;
    // Deduplicate by timestamp (lightweight-charts requires strictly ascending unique times).
    const seen = new Set<number>();
    const data: { time: number; value: number }[] = [];
    for (const p of points) {
      const t = Math.floor(p.t / 1000);
      if (seen.has(t)) {
        data[data.length - 1] = { time: t, value: p.p };
      } else {
        seen.add(t);
        data.push({ time: t, value: p.p });
      }
    }
    series.setData(data);
  }, [points]);

  const isUp = (changePct ?? 0) >= 0;

  return (
    <div
      data-testid="main-chart"
      className="relative flex flex-col flex-1 min-h-0 bg-[color:var(--color-terminal)]"
    >
      <div className="flex items-center justify-between px-5 py-3 border-b border-[color:var(--color-border-soft)]">
        <div className="flex items-baseline gap-4">
          <h2 className="text-lg font-bold text-[color:var(--color-text-bright)]">
            {ticker || "—"}
          </h2>
          {ticker && (
            <>
              <span className="text-2xl font-semibold tabular text-[color:var(--color-text-bright)]">
                {currentPrice !== null && currentPrice !== undefined
                  ? `$${currentPrice.toFixed(2)}`
                  : "—"}
              </span>
              {changePct !== null && changePct !== undefined && (
                <span
                  className={`text-sm font-medium tabular ${
                    isUp
                      ? "text-[color:var(--color-up-green)]"
                      : "text-[color:var(--color-down-red)]"
                  }`}
                >
                  {isUp ? "+" : ""}
                  {changePct.toFixed(2)}%
                </span>
              )}
            </>
          )}
        </div>
        <span className="text-[10px] uppercase tracking-widest text-[color:var(--color-text-muted)]">
          Live · accumulating since page load
        </span>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0" />
      {!ticker && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none text-[color:var(--color-text-muted)] text-sm">
          Select a ticker from the watchlist
        </div>
      )}
    </div>
  );
}
