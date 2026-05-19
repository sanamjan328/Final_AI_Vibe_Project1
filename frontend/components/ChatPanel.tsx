"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmtCurrency } from "@/lib/format";
import type { ChatMessageView } from "@/lib/types";

interface ChatPanelProps {
  onActionsExecuted: () => void;
}

function newId() {
  return Math.random().toString(36).slice(2, 10);
}

export default function ChatPanel({ onActionsExecuted }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessageView[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi — I'm FinAlly. Ask me about your portfolio, market action, or tell me to buy/sell shares.",
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;

    const userMsg: ChatMessageView = {
      id: newId(),
      role: "user",
      content: text,
    };
    const placeholderId = newId();
    const placeholder: ChatMessageView = {
      id: placeholderId,
      role: "assistant",
      content: "",
      pending: true,
    };

    setMessages((m) => [...m, userMsg, placeholder]);
    setInput("");
    setBusy(true);

    try {
      const res = await api.chat(text);
      setMessages((m) =>
        m.map((msg) =>
          msg.id === placeholderId
            ? {
                ...msg,
                content: res.message,
                pending: false,
                executed_trades: res.executed_trades,
                failed_trades: res.failed_trades,
                executed_watchlist_changes: res.executed_watchlist_changes,
              }
            : msg
        )
      );
      if (
        res.executed_trades?.length ||
        res.executed_watchlist_changes?.length
      ) {
        onActionsExecuted();
      }
    } catch (e) {
      setMessages((m) =>
        m.map((msg) =>
          msg.id === placeholderId
            ? {
                ...msg,
                content: "",
                pending: false,
                error: e instanceof Error ? e.message : "Chat failed",
              }
            : msg
        )
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside
      data-testid="chat-panel"
      className="flex flex-col h-full bg-[color:var(--color-panel)] border-l border-[color:var(--color-border-soft)]"
    >
      <div className="px-4 py-3 border-b border-[color:var(--color-border-soft)]">
        <h2 className="text-xs uppercase tracking-[0.2em] text-[color:var(--color-text-muted)]">
          AI Copilot
        </h2>
        <p className="text-[10px] text-[color:var(--color-text-muted)] mt-0.5">
          Ask for analysis · executes trades on your behalf
        </p>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-3 space-y-3"
        data-testid="chat-messages"
      >
        {messages.map((msg) => (
          <div
            key={msg.id}
            data-testid="chat-message"
            data-role={msg.role}
            className={`flex flex-col ${
              msg.role === "user" ? "items-end" : "items-start"
            }`}
          >
            <div
              className={`max-w-[88%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap break-words ${
                msg.role === "user"
                  ? "bg-[color:var(--color-accent-purple)] text-white"
                  : "bg-[color:var(--color-card)] text-[color:var(--color-text-bright)] border border-[color:var(--color-border-soft)]"
              }`}
            >
              {msg.pending ? (
                <span className="inline-flex items-center gap-1.5 text-[color:var(--color-text-muted)]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--color-accent-yellow)] animate-pulse" />
                  Thinking…
                </span>
              ) : msg.error ? (
                <span className="text-[color:var(--color-down-red)]">
                  {msg.error}
                </span>
              ) : (
                msg.content
              )}
            </div>

            {msg.executed_trades && msg.executed_trades.length > 0 && (
              <div className="mt-1.5 flex flex-col gap-1 max-w-[88%]">
                {msg.executed_trades.map((t, i) => (
                  <div
                    key={`et-${i}`}
                    className="text-[11px] px-2 py-1 rounded border border-[color:var(--color-up-green)]/40 bg-[color:var(--color-up-green)]/10 text-[color:var(--color-up-green)]"
                  >
                    {t.side === "buy" ? "↑ Bought" : "↓ Sold"}{" "}
                    {t.quantity} {t.ticker} @ {fmtCurrency(t.price)}
                  </div>
                ))}
              </div>
            )}

            {msg.failed_trades && msg.failed_trades.length > 0 && (
              <div className="mt-1.5 flex flex-col gap-1 max-w-[88%]">
                {msg.failed_trades.map((t, i) => (
                  <div
                    key={`ft-${i}`}
                    className="text-[11px] px-2 py-1 rounded border border-[color:var(--color-down-red)]/40 bg-[color:var(--color-down-red)]/10 text-[color:var(--color-down-red)]"
                  >
                    ✕ Failed {t.side} {t.quantity} {t.ticker} — {t.reason}
                  </div>
                ))}
              </div>
            )}

            {msg.executed_watchlist_changes &&
              msg.executed_watchlist_changes.length > 0 && (
                <div className="mt-1.5 flex flex-col gap-1 max-w-[88%]">
                  {msg.executed_watchlist_changes.map((c, i) => (
                    <div
                      key={`wl-${i}`}
                      className="text-[11px] px-2 py-1 rounded border border-[color:var(--color-accent-blue)]/40 bg-[color:var(--color-accent-blue)]/10 text-[color:var(--color-accent-blue)]"
                    >
                      Watchlist · {c.action === "add" ? "added" : "removed"}{" "}
                      {c.ticker}
                    </div>
                  ))}
                </div>
              )}
          </div>
        ))}
      </div>

      <div className="border-t border-[color:var(--color-border-soft)] p-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask FinAlly anything…"
            disabled={busy}
            data-testid="chat-input"
            className="flex-1 px-3 py-2 text-sm bg-[color:var(--color-terminal)] border border-[color:var(--color-border-soft)] rounded text-[color:var(--color-text-bright)] placeholder:text-[color:var(--color-text-muted)] focus:outline-none focus:border-[color:var(--color-accent-purple)] disabled:opacity-60"
          />
          <button
            type="button"
            onClick={send}
            disabled={busy || !input.trim()}
            data-testid="chat-send"
            className="px-4 py-2 text-sm font-semibold rounded bg-[color:var(--color-accent-purple)] text-white hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
      </div>
    </aside>
  );
}
