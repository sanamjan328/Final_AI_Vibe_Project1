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
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(__file__))

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from app.market.cache import PriceCache
from app.market.simulator import MarketSimulator, TICKER_PARAMS, TICK_INTERVAL

# ── Palette ──────────────────────────────────────────────────────────────────
YELLOW  = "#ecad0a"
BLUE    = "#209dd7"
PURPLE  = "#753991"
UP      = "bright_green"
UP_DIM  = "green"
DOWN    = "bright_red"
DOWN_DIM= "red"
FLAT    = "grey58"
DIM     = "grey42"
BORDER  = "grey23"
WHITE   = "bold white"

# ── Sparkline ─────────────────────────────────────────────────────────────────
_SPARK      = "▁▂▃▄▅▆▇█"
SPARK_WIDTH = 20
HISTORY_LEN = 200   # ticks kept per ticker

# Severity bar characters — used in the event log
_SEV_CHARS = "░▒▓█"


# ── State dataclass ───────────────────────────────────────────────────────────
@dataclass
class TickerState:
    flash_ttl:  int   = 0    # render-frames left for price-flash highlight
    shock_ttl:  int   = 0    # render-frames left for ⚡ badge
    streak:     int   = 0    # consecutive same-direction ticks (+ up / - down)
    last_dir:   str   = ""


@dataclass
class ShockEvent:
    ts:         datetime
    ticker:     str
    prev_price: float
    new_price:  float
    change_pct: float
    direction:  str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chg_color(direction: str) -> str:
    return UP if direction == "up" else (DOWN if direction == "down" else FLAT)


def _colored_sparkline(
    prices: list[float],
    session_open: float,
    width: int = SPARK_WIDTH,
) -> Text:
    """
    Build a per-character colored sparkline.

    Each character is colored:
      - bright_green  if that price is above the session open
      - bright_red    if below the session open
      - grey          if equal
    The final character is always bold+bright to mark the live tip.
    A trend arrow (↗ ↘ →) follows the bars.
    """
    if not prices:
        return Text("─" * width + " →", style=DIM)

    window  = list(prices)[-width:]
    lo, hi  = min(window), max(window)
    span    = hi - lo or 1e-9
    ref     = session_open or window[0]

    t = Text()
    for i, p in enumerate(window):
        idx    = int((p - lo) / span * (len(_SPARK) - 1))
        bar    = _SPARK[idx]
        is_tip = i == len(window) - 1
        if p > ref:
            style = f"bold {UP}" if is_tip else UP_DIM
        elif p < ref:
            style = f"bold {DOWN}" if is_tip else DOWN_DIM
        else:
            style = FLAT
        t.append(bar, style=style)

    # Pad to fixed width
    if len(window) < width:
        t.append("─" * (width - len(window)), style=DIM)

    # Trend arrow based on last 5 ticks
    tail = list(prices)[-5:]
    if len(tail) >= 2:
        delta = tail[-1] - tail[0]
        if delta > 0:
            t.append(" ↗", style=f"bold {UP}")
        elif delta < 0:
            t.append(" ↘", style=f"bold {DOWN}")
        else:
            t.append(" →", style=FLAT)
    else:
        t.append(" →", style=DIM)

    return t


def _arrow_cell(direction: str, streak: int) -> Text:
    """
    Large colored direction arrow.
    Double arrow (▲▲ / ▼▼) when streak ≥ 5 in the same direction.
    """
    strong = abs(streak) >= 5
    if direction == "up":
        glyph = "▲▲" if strong else " ▲"
        style = f"bold {UP}"
    elif direction == "down":
        glyph = "▼▼" if strong else " ▼"
        style = f"bold {DOWN}"
    else:
        glyph = " ◆"
        style = FLAT
    return Text(glyph, style=style, justify="center")


def _price_cell(price: float, direction: str, flashing: bool) -> Text:
    col = _chg_color(direction)
    txt = f"${price:>10,.2f}"
    if flashing:
        bg  = "on dark_green" if direction == "up" else "on dark_red"
        return Text(txt, style=f"bold {col} {bg}")
    return Text(txt, style=f"bold {col}")


def _fmt_change(change: float) -> str:
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:,.3f}"


def _fmt_pct(pct: float) -> str:
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _fmt_session(price: float, open_price: float) -> tuple[str, str]:
    if not open_price:
        return "  —  ", FLAT
    pct  = (price - open_price) / open_price * 100
    sign = "+" if pct >= 0 else ""
    col  = UP if pct > 0 else (DOWN if pct < 0 else FLAT)
    return f"{sign}{pct:.2f}%", col


def _severity_bar(abs_pct: float) -> Text:
    """
    Visual bar showing shock magnitude.
    0-1%  → 1 block, 1-2% → 2, 2-3% → 3, 3%+ → 4 blocks (max).
    """
    level = min(int(abs_pct), 4)
    bars  = _SEV_CHARS[level - 1] * level if level else "·"
    col   = [FLAT, UP_DIM, UP, f"bold {UP}", f"bold {YELLOW}"][level]
    return Text(bars.ljust(4), style=col)


def _elapsed_label(event_ts: datetime, now: datetime) -> str:
    secs = int((now - event_ts).total_seconds())
    if secs < 60:
        return f"{secs:>2}s ago"
    return f"{secs // 60}m{secs % 60:02d}s"


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
            (" Market Simulator", WHITE),
        ),
        Text(clock, style=f"bold {BLUE}", justify="center"),
        Text(f"Tick #{tick_count:,}   uptime {uptime}  ", style=DIM),
    )
    return Panel(grid, border_style=YELLOW, padding=(0, 0))


def _watchlist_panel(
    prices:       dict,
    history:      dict,
    session_open: dict,
    states:       dict,  # ticker → TickerState
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
    t.add_column("",        width=2,              no_wrap=True)          # arrow
    t.add_column("TICKER",  style=f"bold {BLUE}", width=7,  no_wrap=True)
    t.add_column("PRICE",   justify="right",      width=13, no_wrap=True)
    t.add_column("CHANGE",  justify="right",      width=10, no_wrap=True)
    t.add_column("CHG %",   justify="right",      width=9,  no_wrap=True)
    t.add_column("SESSION", justify="right",      width=9,  no_wrap=True)
    t.add_column("HI",      justify="right",      width=10, no_wrap=True)
    t.add_column("LO",      justify="right",      width=10, no_wrap=True)
    t.add_column(f"SPARKLINE  ({SPARK_WIDTH} ticks)",
                            justify="left",       min_width=SPARK_WIDTH + 4, no_wrap=True)

    for ticker in list(TICKER_PARAMS.keys()):
        if ticker not in prices:
            continue

        u    = prices[ticker]
        col  = _chg_color(u.direction)
        st   = states.get(ticker, TickerState())
        hist = list(history[ticker])
        hi   = max(hist) if hist else u.price
        lo   = min(hist) if hist else u.price
        sess_str, sess_col = _fmt_session(u.price, session_open.get(ticker, 0.0))
        shock_mark = " ⚡" if st.shock_ttl > 0 else ""

        t.add_row(
            _arrow_cell(u.direction, st.streak),
            ticker + shock_mark,
            _price_cell(u.price, u.direction, st.flash_ttl > 0),
            Text(_fmt_change(u.change), style=col),
            Text(_fmt_pct(u.change_pct), style=f"bold {col}"),
            Text(sess_str, style=sess_col),
            Text(f"${hi:,.2f}", style=f"dim {UP}"),
            Text(f"${lo:,.2f}", style=f"dim {DOWN}"),
            _colored_sparkline(hist, session_open.get(ticker, 0.0)),
        )

    return Panel(
        t,
        title=(
            f"[bold {YELLOW}]  Live Prices[/]  "
            f"[dim]GBM · Cholesky · {TICK_INTERVAL * 1000:.0f} ms ticks[/]"
        ),
        border_style=BORDER,
        padding=(0, 0),
    )


def _events_panel(events: deque) -> Panel:
    now = datetime.now(timezone.utc)

    body = Text()
    if not events:
        body.append("\n  Waiting for shock events…\n", style=DIM)
    else:
        for ev in events:
            col   = _chg_color(ev.direction)
            sign  = "+" if ev.change_pct > 0 else ""
            arrow = "▲" if ev.direction == "up" else "▼"
            age   = _elapsed_label(ev.ts, now)

            # Row 1: time + ticker + direction arrow + pct
            body.append(f"\n  {ev.ts.strftime('%H:%M:%S')} ", style=DIM)
            body.append(f"{arrow} {ev.ticker:<5}", style=f"bold {col}")
            body.append(f"  {sign}{ev.change_pct:.2f}%", style=f"bold {col}")
            body.append(f"  {age}", style=DIM)
            body.append("  ")
            body.append_text(_severity_bar(abs(ev.change_pct)))

            # Row 2: price transition
            body.append(f"\n      ${ev.prev_price:>9,.2f}", style=DIM)
            body.append("  →  ", style=FLAT)
            body.append(f"${ev.new_price:>9,.2f}", style=f"bold {col}")
            body.append("\n")

    count_label = f"  {len(events)} event{'s' if len(events) != 1 else ''}"
    return Panel(
        body,
        title=f"[bold {YELLOW}]  Shock Events[/][dim]{count_label}[/]",
        border_style=BORDER,
        padding=(0, 0),
    )


def _footer_panel(prices: dict, tick_count: int, elapsed_s: float) -> Panel:
    n_up   = sum(1 for u in prices.values() if u.direction == "up")
    n_down = sum(1 for u in prices.values() if u.direction == "down")
    n_flat = len(prices) - n_up - n_down
    total  = max(len(prices), 1)
    tps    = tick_count / max(elapsed_s, 1)

    # Visual breadth bar: green blocks for up, red for down, grey for flat
    bar_width = 20
    n_up_blocks   = round(n_up   / total * bar_width)
    n_down_blocks = round(n_down / total * bar_width)
    n_flat_blocks = bar_width - n_up_blocks - n_down_blocks

    breadth = Text()
    breadth.append("  breadth [", style=DIM)
    breadth.append("█" * n_up_blocks,   style=UP)
    breadth.append("█" * n_flat_blocks, style=FLAT)
    breadth.append("█" * n_down_blocks, style=DOWN)
    breadth.append("]", style=DIM)

    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(justify="left")
    grid.add_column(justify="left")
    grid.add_column(justify="left")
    grid.add_column(justify="left")
    grid.add_column(justify="right")
    grid.add_row(
        Text(f"  ▲ {n_up} up",    style=f"bold {UP}"),
        Text(f"▼ {n_down} down",  style=f"bold {DOWN}"),
        Text(f"◆ {n_flat} flat",  style=FLAT),
        breadth,
        Text(
            f"GBM + Cholesky  ·  {tps:.1f} ticks/s  ·  "
            f"[bold {YELLOW}]Ctrl+C[/] to exit  ",
            style=DIM,
        ),
    )
    return Panel(grid, border_style=BORDER, padding=(0, 0))


def _build_layout(
    tick_count:   int,
    start:        datetime,
    prices:       dict,
    history:      dict,
    session_open: dict,
    states:       dict,
    events:       deque,
) -> Layout:
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()

    layout = Layout()
    layout.split_column(
        Layout(name="header",  size=3),
        Layout(name="body"),
        Layout(name="footer",  size=3),
    )
    layout["body"].split_row(
        Layout(name="watchlist", ratio=5),
        Layout(name="events",    ratio=2),
    )

    layout["header"].update(_header_panel(tick_count, start))
    layout["watchlist"].update(_watchlist_panel(prices, history, session_open, states))
    layout["events"].update(_events_panel(events))
    layout["footer"].update(_footer_panel(prices, tick_count, elapsed))
    return layout


# ── Main ──────────────────────────────────────────────────────────────────────

async def run() -> None:
    console = Console()
    console.print(
        f"\n[bold {YELLOW}]FinAlly[/] Market Simulator  —  starting GBM engine…\n"
    )

    cache   = PriceCache()
    sim     = MarketSimulator(cache)
    tickers = list(TICKER_PARAMS.keys())

    history:      dict[str, deque]       = defaultdict(lambda: deque(maxlen=HISTORY_LEN))
    session_open: dict[str, float]       = {}
    states:       dict[str, TickerState] = defaultdict(TickerState)
    events:       deque[ShockEvent]      = deque(maxlen=8)
    tick_count    = 0
    start         = datetime.now(timezone.utc)

    queue = cache.subscribe()
    await sim.start(tickers)

    with Live(
        _build_layout(0, start, {}, history, session_open, states, events),
        console=console,
        screen=True,
        refresh_per_second=10,
    ) as live:
        try:
            while True:
                # ── Drain all updates queued since last render loop ──────────
                while True:
                    try:
                        u = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    tick_count += 1
                    history[u.ticker].append(u.price)

                    if u.ticker not in session_open:
                        session_open[u.ticker] = u.price

                    st = states[u.ticker]

                    # Flash highlight: show for 2 render frames (~200 ms)
                    st.flash_ttl = 2

                    # Streak tracking
                    if u.direction == st.last_dir:
                        st.streak = st.streak + 1 if u.direction == "up" else st.streak - 1
                    else:
                        st.streak = 1 if u.direction == "up" else -1
                    st.last_dir = u.direction

                    # Shock detection: GBM normal moves are ~0.01–0.02 % per tick.
                    # Any single-tick move beyond 0.5 % is a simulator shock event.
                    if abs(u.change_pct) >= 0.5:
                        st.shock_ttl = 20   # ~2 s at 10 fps
                        events.appendleft(
                            ShockEvent(
                                ts=datetime.now(timezone.utc),
                                ticker=u.ticker,
                                prev_price=u.prev_price,
                                new_price=u.price,
                                change_pct=u.change_pct,
                                direction=u.direction,
                            )
                        )

                # ── Age out per-ticker transient state ──────────────────────
                for st in states.values():
                    if st.flash_ttl > 0:
                        st.flash_ttl -= 1
                    if st.shock_ttl > 0:
                        st.shock_ttl -= 1

                # ── Re-render ───────────────────────────────────────────────
                live.update(
                    _build_layout(
                        tick_count, start,
                        cache.get_all(), history, session_open, states, events,
                    )
                )
                await asyncio.sleep(0.10)   # 10 render-loops / sec

        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await sim.stop()
            cache.unsubscribe(queue)

    elapsed_s = int((datetime.now(timezone.utc) - start).total_seconds())
    console.print(
        f"\n[bold {YELLOW}]FinAlly[/] stopped. "
        f"[{BLUE}]{tick_count:,}[/] ticks · "
        f"[{BLUE}]{elapsed_s}s[/] elapsed · "
        f"[{BLUE}]{len(events)}[/] shock events logged.\n"
    )


if __name__ == "__main__":
    asyncio.run(run())
