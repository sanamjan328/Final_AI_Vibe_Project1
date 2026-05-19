"use client";

import { fmtCurrency } from "@/lib/format";
import type { ConnectionStatus } from "@/lib/types";

interface HeaderProps {
  totalValue: number | null;
  cashBalance: number | null;
  status: ConnectionStatus;
}

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connected: "Live",
  reconnecting: "Reconnecting",
  disconnected: "Offline",
};

const STATUS_COLOR: Record<ConnectionStatus, string> = {
  connected: "bg-[color:var(--color-up-green)]",
  reconnecting: "bg-[color:var(--color-accent-yellow)]",
  disconnected: "bg-[color:var(--color-down-red)]",
};

export default function Header({ totalValue, cashBalance, status }: HeaderProps) {
  return (
    <header className="flex items-center justify-between gap-6 px-5 py-3 bg-[color:var(--color-panel)] border-b border-[color:var(--color-border-soft)]">
      <div className="flex items-baseline gap-3">
        <h1 className="text-xl font-bold tracking-wide text-[color:var(--color-accent-yellow)]">
          FinAlly
        </h1>
        <span className="text-xs uppercase tracking-[0.25em] text-[color:var(--color-text-muted)]">
          AI Trading Workstation
        </span>
      </div>

      <div className="flex items-center gap-8">
        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase tracking-widest text-[color:var(--color-text-muted)]">
            Portfolio Value
          </span>
          <span className="text-xl font-semibold tabular text-[color:var(--color-text-bright)]">
            {fmtCurrency(totalValue)}
          </span>
        </div>

        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase tracking-widest text-[color:var(--color-text-muted)]">
            Cash
          </span>
          <span
            data-testid="cash-balance"
            className="text-lg font-medium tabular text-[color:var(--color-accent-blue)]"
          >
            {fmtCurrency(cashBalance)}
          </span>
        </div>

        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-[color:var(--color-card)] border border-[color:var(--color-border-soft)]"
          data-testid="connection-status"
          data-status={status}
        >
          <span
            className={`inline-block h-2 w-2 rounded-full ${STATUS_COLOR[status]} ${
              status === "connected" ? "status-pulse" : ""
            }`}
          />
          <span className="text-xs text-[color:var(--color-text-muted)]">
            {STATUS_LABEL[status]}
          </span>
        </div>
      </div>
    </header>
  );
}
