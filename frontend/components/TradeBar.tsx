"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { fmtCurrency } from "@/lib/format";

interface TradeBarProps {
  selectedTicker: string | null;
  currentPrice: number | null;
  onTradeComplete: () => void;
}

type Feedback = { kind: "success" | "error"; text: string } | null;

export default function TradeBar({
  selectedTicker,
  currentPrice,
  onTradeComplete,
}: TradeBarProps) {
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  const effectiveTicker = (ticker || selectedTicker || "").toUpperCase();
  const qty = Number(quantity);
  const estimate =
    currentPrice && qty > 0 ? currentPrice * qty : null;

  const submit = async (side: "buy" | "sell") => {
    const t = effectiveTicker.trim();
    if (!t || !qty || qty <= 0) {
      setFeedback({ kind: "error", text: "Enter a ticker and positive quantity." });
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      const res = await api.trade({ ticker: t, side, quantity: qty });
      if (res.success && res.trade) {
        setFeedback({
          kind: "success",
          text: `${side.toUpperCase()} ${qty} ${t} @ ${fmtCurrency(res.trade.price)}`,
        });
        setQuantity("");
        onTradeComplete();
      } else {
        setFeedback({ kind: "error", text: res.error || "Trade failed" });
      }
    } catch (e) {
      setFeedback({
        kind: "error",
        text: e instanceof Error ? e.message : "Trade failed",
      });
    } finally {
      setBusy(false);
      setTimeout(() => setFeedback(null), 4000);
    }
  };

  return (
    <div
      data-testid="trade-bar"
      className="flex items-center gap-3 px-4 py-3 bg-[color:var(--color-panel)] border border-[color:var(--color-border-soft)] rounded"
    >
      <div className="flex flex-col">
        <label className="text-[10px] uppercase tracking-widest text-[color:var(--color-text-muted)]">
          Ticker
        </label>
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder={selectedTicker || "AAPL"}
          data-testid="trade-ticker"
          className="w-24 px-2 py-1.5 text-sm font-semibold uppercase bg-[color:var(--color-terminal)] border border-[color:var(--color-border-soft)] rounded text-[color:var(--color-text-bright)] focus:outline-none focus:border-[color:var(--color-accent-blue)]"
        />
      </div>

      <div className="flex flex-col">
        <label className="text-[10px] uppercase tracking-widest text-[color:var(--color-text-muted)]">
          Quantity
        </label>
        <input
          type="number"
          min="0"
          step="any"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          placeholder="0"
          data-testid="trade-quantity"
          className="w-28 px-2 py-1.5 text-sm tabular bg-[color:var(--color-terminal)] border border-[color:var(--color-border-soft)] rounded text-[color:var(--color-text-bright)] focus:outline-none focus:border-[color:var(--color-accent-blue)]"
        />
      </div>

      <div className="flex flex-col">
        <span className="text-[10px] uppercase tracking-widest text-[color:var(--color-text-muted)]">
          Estimated
        </span>
        <span className="text-sm tabular text-[color:var(--color-text-bright)] min-w-[88px]">
          {estimate ? fmtCurrency(estimate) : "—"}
        </span>
      </div>

      <div className="flex gap-2 ml-auto">
        <button
          type="button"
          onClick={() => submit("buy")}
          disabled={busy}
          data-testid="trade-buy"
          className="px-4 py-2 text-sm font-semibold rounded bg-[color:var(--color-accent-blue)] text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          BUY
        </button>
        <button
          type="button"
          onClick={() => submit("sell")}
          disabled={busy}
          data-testid="trade-sell"
          className="px-4 py-2 text-sm font-semibold rounded bg-[color:var(--color-down-red)] text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          SELL
        </button>
      </div>

      {feedback && (
        <div
          data-testid="trade-feedback"
          className={`text-xs px-3 py-1.5 rounded ${
            feedback.kind === "success"
              ? "bg-[color:var(--color-up-green)]/15 text-[color:var(--color-up-green)]"
              : "bg-[color:var(--color-down-red)]/15 text-[color:var(--color-down-red)]"
          }`}
        >
          {feedback.text}
        </div>
      )}
    </div>
  );
}
