"use client";

import { useEffect, useRef, useState } from "react";
import type { ConnectionStatus, PriceUpdate, SparklinePoint } from "@/lib/types";

const MAX_SPARKLINE_POINTS = 120;

export interface PriceStreamState {
  prices: Record<string, PriceUpdate>;
  sparklines: Record<string, SparklinePoint[]>;
  status: ConnectionStatus;
  lastTick: number;
}

export function usePriceStream(): PriceStreamState {
  const [prices, setPrices] = useState<Record<string, PriceUpdate>>({});
  const [sparklines, setSparklines] = useState<Record<string, SparklinePoint[]>>({});
  const [status, setStatus] = useState<ConnectionStatus>("reconnecting");
  const [lastTick, setLastTick] = useState<number>(0);

  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    let cancelled = false;

    const connect = () => {
      try {
        const es = new EventSource("/api/stream/prices");
        esRef.current = es;
        setStatus("reconnecting");

        es.onopen = () => {
          if (cancelled) return;
          setStatus("connected");
        };

        es.onmessage = (ev) => {
          if (cancelled || !ev.data) return;
          try {
            const update = JSON.parse(ev.data) as PriceUpdate;
            if (!update?.ticker || typeof update.price !== "number") return;

            setPrices((prev) => ({ ...prev, [update.ticker]: update }));

            setSparklines((prev) => {
              const existing = prev[update.ticker] || [];
              const next = [
                ...existing,
                { t: Date.now(), p: update.price },
              ];
              if (next.length > MAX_SPARKLINE_POINTS) {
                next.splice(0, next.length - MAX_SPARKLINE_POINTS);
              }
              return { ...prev, [update.ticker]: next };
            });

            setLastTick(Date.now());
          } catch {
            // ignore malformed messages
          }
        };

        es.onerror = () => {
          if (cancelled) return;
          // EventSource has built-in retry. While the browser is reconnecting,
          // readyState === CONNECTING; only mark fully disconnected if the
          // connection is closed and won't retry.
          if (es.readyState === EventSource.CLOSED) {
            setStatus("disconnected");
          } else {
            setStatus("reconnecting");
          }
        };
      } catch {
        if (!cancelled) setStatus("disconnected");
      }
    };

    connect();

    return () => {
      cancelled = true;
      esRef.current?.close();
      esRef.current = null;
    };
  }, []);

  return { prices, sparklines, status, lastTick };
}
