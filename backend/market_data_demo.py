#!/usr/bin/env python3
"""
FinAlly — Market Data Simulator  ·  Rich Terminal Demo

Live Bloomberg-style dashboard driven by the GBM simulator.

Run:
    cd backend
    uv run python market_data_demo.py
"""

import asyncio
import sys
import os
from collections import defaultdict, deque
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.market.cache import PriceCache
from app.market.simulator import MarketSimulator, TICKER_PARAMS, TICK_INTERVAL

# ── Palette (matches FinAlly brand) ─────────────────────────────────────────
YELLOW      = "#ecad0a"
BLUE        = "#209dd7"
PURPLE      = "#753991"
UP          = "bright_green"
DOWN        = "bright_red"
FLAT        = "grey58"
DIM         = "grey42"
BORDER      = "grey23"

# ── Sparkline ────────────────────────────────────────────────────────────────
_SPARK = "▁▂▃▄▅▆▇█"
SPARK_WIDTH = 18
HISTORY_LEN = 120   # ticks kept per ticker (~60 s of history)


def _sparkline(prices: list[float], width: int = SPARK_WIDTH) -> tuple[str, str]:
    """Return (chars, color) where color reflects net direction."""
    if len(prices) < 2:
        return "─" * width, FLAT
    lo, hi = min(prices), max(prices)
    span = hi - lo or 1e-9
    chars = "".join(
        _SPARK[int((p - lo) / span * (len(_SPARK) - 1))]
        for p in prices[-width:]
    )
    color = UP if prices[-1] >= prices[0] else DOWN
    return chars.ljust(width), color


def _chg_color(direction: str) -> str:
    return {
        "up":   UP,
        "down": DOWN,
    }.get(direction, FLAT)


def _fmt_price(price: float) -> str:
    return f"${price:>10,.2f}"


def _fmt_change(change: float) -> str:
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:,.2f}"


def _fmt_pct(pct: float, direction: str) -> str:
    arrow = {"up": "▲", "down": "▼"}.get(direction, "─")
    sign  = "+" if pct >= 0 else ""
    return f"{arrow} {sign}{pct:.2f}%"


def _fmt_session(price: float, open_price: float) -> tuple[str, str]:
    if not open_price:
        return "  —  ", FLAT
    pct  = (price - open_price) / open_price * 100
    sign = "+" if pct >= 0 else ""
    col  = UP if pct > 0 else (DOWN if pct < 0 else FLAT)
    return f"{sign}{pct:.2f}%", col


# ── Panel builders ────────────────────────────────────────────────────────────

def _header_panel(tick_count: int, start: datetime) -> Panel:
    now     = datetime.now(timezone.utc)
    elapsed = int((now - start).total_seconds())
    uptime  = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
    clock   = now.strftime("%H:%M:%S UTC")

    grid = Table.grid(expand=True)
    grid.add_column(justify="left",  ratio=3)
    grid.add_column(justify="center",ratio=2)
    grid.add_column(justify="right", ratio=3)
    grid.add_row(
        Text.assemble(
            ("  FinAlly", f"bold {YELLOW}"),
            (" Market Simulator", "bold white"),
        ),
        Text(clock, style=f"bold {BLUE}", justify="center"),
        Text(f"Tick #{tick_count:,}   uptime {uptime}  ", style=DIM),
    )
    return Panel(grid, border_style=YELLOW, padding=(0, 0))


def _watchlist_panel(
    prices:       dict,
    history:      dict,
    session_open: dict,
    shocks:       set,
) -> Panel:
    t = Table(
        box=box.SIMPLE_HEAD,
        header_style=f"bold {YELLOW}",
        border_style=BORDER,
        show_footer=False,
        pad_edge=True,
        expand=True,
        padding=(0, 1),
    )
    t.add_column("TICKER",  style=f"bold {BLUE}", width=8,          no_wrap=True)
    t.add_column("PRICE",   justify="right",      width=12,         no_wrap=True)
    t.add_column("CHANGE",  justify="right",      width=10,         no_wrap=True)
    t.add_column("CHG %",   justify="right",      width=12,         no_wrap=True)
    t.add_column("SESSION", justify="right",      width=10,         no_wrap=True)
    t.add_column("HI",      justify="right",      width=10,         no_wrap=True)
    t.add_column("LO",      justify="right",      width=10,         no_wrap=True)
    t.add_column("SPARKLINE " + f"({SPARK_WIDTH}t)", justify="left", min_width=SPARK_WIDTH + 2, no_wrap=True)

    for ticker in list(TICKER_PARAMS.keys()):  # fixed display order
        if ticker not in prices:
            continue
        u     = prices[ticker]
        col   = _chg_color(u.direction)
        hist  = list(history[ticker])
        hi    = max(hist) if hist else u.price
        lo    = min(hist) if hist else u.price
        spark, spark_col = _sparkline(hist)
        sess_str, sess_col = _fmt_session(u.price, session_open.get(ticker, 0.0))
        shock_mark = " ⚡" if ticker in shocks else ""

        t.add_row(
            ticker + shock_mark,
            Text(_fmt_price(u.price),         style=f"bold {col}"),
            Text(_fmt_change(u.change),        style=col),
            Text(_fmt_pct(u.change_pct, u.direction), style=f"bold {col}"),
            Text(sess_str,                     style=sess_col),
            Text(f"${hi:,.2f}",               style=f"dim {UP}"),
            Text(f"${lo:,.2f}",               style=f"dim {DOWN}"),
            Text(spark,                        style=spark_col),
        )

    return Panel(
        t,
        title=f"[bold {YELLOW}]  Live Prices[/]  [dim]GBM · Cholesky · {TICK_INTERVAL * 1000:.0f} ms ticks[/]",
        border_style=BORDER,
        padding=(0, 0),
    )


def _events_panel(events: deque) -> Panel:
    body = Text()
    if not events:
        body.append("  Waiting for shock events…\n", style=DIM)
    for ts, line in events:
        body.append(f"  {ts}  ", style=DIM)
        body.append_text(line)
        body.append("\n")
    return Panel(
        body,
        title=f"[bold {YELLOW}]  Shock Events[/]",
        border_style=BORDER,
        padding=(0, 0),
    )


def _stats_panel(prices: dict, tick_count: int, elapsed_s: float) -> Panel:
    n_up   = sum(1 for u in prices.values() if u.direction == "up")
    n_down = sum(1 for u in prices.values() if u.direction == "down")
    n_flat = len(prices) - n_up - n_down
    tps    = tick_count / max(elapsed_s, 1)

    grid = Table.grid(expand=True, padding=(0, 3))
    grid.add_column(justify="left")
    grid.add_column(justify="left")
    grid.add_column(justify="left")
    grid.add_column(justify="right")
    grid.add_row(
        Text(f"▲ {n_up} up",    style=UP),
        Text(f"▼ {n_down} down",style=DOWN),
        Text(f"─ {n_flat} flat",style=FLAT),
        Text(
            f"GBM + Cholesky correlated noise  ·  {tps:.1f} ticks/s  ·  "
            f"[bold {YELLOW}]Ctrl+C[/] to exit  ",
            style=DIM,
        ),
    )
    return Panel(grid, border_style=BORDER, padding=(0, 1))


def _build_layout(
    tick_count:   int,
    start:        datetime,
    prices:       dict,
    history:      dict,
    session_open: dict,
    shocks:       set,
    events:       deque,
) -> Layout:
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()

    layout = Layout()
    layout.split_column(
        Layout(name="header",    size=3),
        Layout(name="body"),
        Layout(name="footer",    size=3),
    )
    layout["body"].split_row(
        Layout(name="watchlist", ratio=5),
        Layout(name="events",    ratio=2),
    )

    layout["header"].update(_header_panel(tick_count, start))
    layout["watchlist"].update(_watchlist_panel(prices, history, session_open, shocks))
    layout["events"].update(_events_panel(events))
    layout["footer"].update(_stats_panel(prices, tick_count, elapsed))
    return layout


# ── Main coroutine ────────────────────────────────────────────────────────────

async def run() -> None:
    console = Console()

    # Print a brief startup banner before entering full-screen mode
    console.print(
        f"\n[bold {YELLOW}]FinAlly[/] Market Simulator  —  starting GBM engine…\n",
    )

    cache   = PriceCache()
    sim     = MarketSimulator(cache)
    tickers = list(TICKER_PARAMS.keys())

    history:      dict[str, deque] = defaultdict(lambda: deque(maxlen=HISTORY_LEN))
    session_open: dict[str, float] = {}
    shocks:       set[str]         = set()
    shock_ttl:    dict[str, int]   = {}   # ticker → render-frames remaining
    events:       deque            = deque(maxlen=10)
    tick_count    = 0
    start         = datetime.now(timezone.utc)

    queue = cache.subscribe()
    await sim.start(tickers)

    initial = _build_layout(0, start, {}, history, session_open, shocks, events)

    with Live(initial, console=console, screen=True, refresh_per_second=8) as live:
        try:
            while True:
                # Drain every update the simulator has pushed since last loop
                while True:
                    try:
                        u = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    tick_count += 1
                    history[u.ticker].append(u.price)

                    if u.ticker not in session_open:
                        session_open[u.ticker] = u.price

                    # Shock detection: GBM per-tick moves are ~0.01–0.02 %.
                    # Any move beyond 0.5 % in a single tick is a shock event.
                    if abs(u.change_pct) >= 0.5:
                        shocks.add(u.ticker)
                        shock_ttl[u.ticker] = 16   # keep badge for ~2 s
                        ts  = datetime.now(timezone.utc).strftime("%H:%M:%S")
                        col = UP if u.change_pct > 0 else DOWN
                        sign = "+" if u.change_pct > 0 else ""
                        line = Text()
                        line.append(f"⚡ {u.ticker:<5}", style=f"bold {col}")
                        line.append(f"  {sign}{u.change_pct:.2f}%", style=f"bold {col}")
                        line.append(
                            f"  ${u.prev_price:,.2f} → ${u.price:,.2f}",
                            style=col,
                        )
                        events.appendleft((ts, line))

                # Age out shock badges
                expired = [t for t, ttl in shock_ttl.items() if ttl <= 0]
                for t in expired:
                    shocks.discard(t)
                    del shock_ttl[t]
                shock_ttl = {t: ttl - 1 for t, ttl in shock_ttl.items()}

                live.update(
                    _build_layout(
                        tick_count, start,
                        cache.get_all(), history, session_open, shocks, events,
                    )
                )
                await asyncio.sleep(0.10)   # ~10 render-loops / sec

        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await sim.stop()
            cache.unsubscribe(queue)

    console.print(
        f"\n[bold {YELLOW}]FinAlly[/] stopped.  "
        f"[{BLUE}]{tick_count:,}[/] ticks processed in "
        f"[{BLUE}]{(datetime.now(timezone.utc) - start).seconds}s[/].\n"
    )


if __name__ == "__main__":
    asyncio.run(run())
