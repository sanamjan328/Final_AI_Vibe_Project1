"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmtCurrency } from "@/lib/format";
import type { PortfolioSnapshot } from "@/lib/types";

export default function PnLChart() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<unknown>(null);
  const seriesRef = useRef<unknown>(null);
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);

  useEffect(() => {
    if (!containerRef.current) return;
    let cleanup = () => {};
    let cancelled = false;

    (async () => {
      const lib = await import("lightweight-charts");
      if (cancelled || !containerRef.current) return;

      const chart = lib.createChart(containerRef.current, {
        layout: {
          background: { color: "#161b22" },
          textColor: "#8b949e",
          fontFamily:
            'ui-monospace, "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
          fontSize: 10,
        },
        grid: {
          vertLines: { color: "#21262d" },
          horzLines: { color: "#21262d" },
        },
        rightPriceScale: { borderColor: "#30363d" },
        timeScale: {
          borderColor: "#30363d",
          timeVisible: true,
          secondsVisible: false,
        },
        autoSize: true,
      });

      const series = chart.addSeries(lib.AreaSeries, {
        topColor: "rgba(32, 157, 215, 0.4)",
        bottomColor: "rgba(32, 157, 215, 0.0)",
        lineColor: "#209dd7",
        lineWidth: 2,
      });

      chartRef.current = chart;
      seriesRef.current = series;

      const ro = new ResizeObserver(() => {
        if (containerRef.current) {
          chart.applyOptions({
            width: containerRef.current.clientWidth,
            height: containerRef.current.clientHeight,
          });
        }
      });
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
    const load = async () => {
      try {
        const data = await api.getPortfolioHistory();
        setSnapshots(data);
      } catch {
        // ignore — backend may not be ready yet
      }
    };
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const series = seriesRef.current as
      | { setData: (data: { time: number; value: number }[]) => void }
      | null;
    if (!series) return;
    const seen = new Set<number>();
    const data: { time: number; value: number }[] = [];
    for (const s of snapshots) {
      const t = Math.floor(new Date(s.recorded_at).getTime() / 1000);
      if (Number.isNaN(t)) continue;
      if (seen.has(t)) {
        data[data.length - 1] = { time: t, value: s.total_value };
      } else {
        seen.add(t);
        data.push({ time: t, value: s.total_value });
      }
    }
    series.setData(data);
  }, [snapshots]);

  const latest = snapshots.length ? snapshots[snapshots.length - 1].total_value : null;
  const first = snapshots.length ? snapshots[0].total_value : null;
  const delta =
    latest !== null && first !== null ? latest - first : null;

  return (
    <div
      data-testid="pnl-chart"
      className="flex flex-col h-full bg-[color:var(--color-panel)] border border-[color:var(--color-border-soft)] rounded"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-[color:var(--color-border-soft)]">
        <h3 className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-muted)]">
          Portfolio Value
        </h3>
        <span
          className={`text-xs tabular ${
            delta === null
              ? "text-[color:var(--color-text-muted)]"
              : delta >= 0
              ? "text-[color:var(--color-up-green)]"
              : "text-[color:var(--color-down-red)]"
          }`}
        >
          {delta === null ? "—" : `${delta >= 0 ? "+" : ""}${fmtCurrency(delta)}`}
        </span>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0" />
    </div>
  );
}
