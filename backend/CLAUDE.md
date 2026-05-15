# Backend — FinAlly AI Trading Workstation

FastAPI (Python 3.12+) backend managed with `uv`. Single port (8000), SQLite database, SSE streaming, LLM integration. See `../planning/PLAN.md` for the full project spec.

---

## Quick start

```bash
cd backend
uv run pytest          # run all tests
uv run uvicorn app.main:app --reload --port 8000  # dev server (main.py not yet built)
```

---

## Directory layout

```
backend/
├── app/
│   ├── __init__.py
│   └── market/              # Market data subsystem (fully implemented)
│       ├── __init__.py      # Public exports: PriceCache, PriceUpdate, DailyBar, create_market_data_source
│       ├── models.py        # PriceUpdate, DailyBar dataclasses
│       ├── cache.py         # PriceCache — shared in-memory store + SSE fan-out
│       ├── interface.py     # MarketDataSource ABC
│       ├── simulator.py     # MarketSimulator — correlated GBM, no external deps
│       ├── massive_client.py# MassiveClient — polls Massive (formerly Polygon.io) REST API
│       └── factory.py       # create_market_data_source() — reads env, returns correct impl
├── tests/
│   └── market/              # 76 tests, all passing
├── conftest.py              # Adds backend/ to sys.path for test imports
├── pyproject.toml           # uv project config, pytest config
└── uv.lock                  # Locked dependency graph
```

---

## Environment variables

| Variable | Required | Default | Effect |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes (for chat) | — | LLM calls via LiteLLM → OpenRouter |
| `MASSIVE_API_KEY` | No | — | If set and non-empty: use Massive REST API for market data |
| `MASSIVE_POLL_INTERVAL` | No | `15.0` | Seconds between Massive API polls (free tier safe at 15s) |
| `LLM_MOCK` | No | `false` | Set `true` to return deterministic mock LLM responses (E2E tests) |

Read from `.env` at project root (one level up from `backend/`). The `.env.example` at root documents all variables.

---

## Market data subsystem (`app/market/`)

The only fully implemented subsystem. Everything below is production-quality and covered by tests.

### Architecture

```
create_market_data_source()   ← reads env, constructs one of:
    MarketSimulator               ← no external deps, GBM-based
    MassiveClient                 ← polls Massive REST API
        ↓ both write to
    PriceCache                    ← shared in-memory dict
        ↓ SSE endpoint reads from
    asyncio.Queue (per client)    ← fan-out, one queue per connected browser tab
```

### Key invariant: `positions ∪ watchlist`

The market data source must track **every ticker that has an open position OR appears on the watchlist**. Portfolio P&L requires live prices for held tickers even after the user removes them from the watchlist.

- **Startup** (`main.py` lifespan): seed `source.start()` with `positions ∪ watchlist`, not watchlist alone.
- **Watchlist DELETE route**: only call `source.remove_ticker(ticker)` if the user holds no position in that ticker.
- **Trade execution (buy)**: call `source.add_ticker(ticker)` when a new position is opened.

### `MarketDataSource` interface (`interface.py`)

All code outside `app/market/` must import only through `app.market` (the `__init__.py` exports). Never import a concrete class directly.

```python
from app.market import PriceCache, PriceUpdate, DailyBar, create_market_data_source
```

Methods:

| Method | Sync/Async | Notes |
|---|---|---|
| `start(tickers)` | `async` | Called once at app startup. Tickers = `positions ∪ watchlist`. |
| `stop()` | `async` | Cancels background task. Safe to call if never started. |
| `add_ticker(ticker)` | sync | Normalises to uppercase. Idempotent. Takes effect on next poll/tick. |
| `remove_ticker(ticker)` | sync | Normalises to uppercase. Safe if ticker not tracked. Cache entry stays until overwritten. |
| `get_daily_bars(ticker, from_date, to_date)` | `async` | Returns `[]` for the simulator (no historical data). |

### `PriceCache` (`cache.py`)

Single shared mutable state. Created once in the FastAPI lifespan and stored as `app.state.cache`.

- **Reads** (`get`, `get_all`, `get_tickers`): synchronous dict lookup — no lock needed (CPython GIL).
- **Writes** (`update`): holds the asyncio lock for the dict update, then releases before fan-out.
- **Fan-out** (`subscribe` / `unsubscribe`): each SSE client gets its own `asyncio.Queue(maxsize=1000)`. Updates are `put_nowait` — a full queue drops the update rather than blocking the write path.

### `MarketSimulator` (`simulator.py`)

- Geometric Brownian Motion with Itô correction: `log_return = (μ - σ²/2)·Δt + σ·√Δt·z`
- 10×10 correlation matrix for the default tickers; unknown tickers use default cross-asset correlation of 0.3
- Tick interval: 500ms
- Shock events: ~0.2% chance per ticker per tick of a sudden ±5% move, followed by a 5-second drift-suppression reversion window. Shocks cannot fire while a ticker is already in its reversion window.
- **Cache primed on startup**: `_tick_loop` computes the first tick immediately before entering the sleep loop, so SSE clients connecting at boot see prices at once.
- `get_daily_bars` always returns `[]` — simulator has no historical data.

Seed prices and per-ticker GBM parameters are defined in `TICKER_PARAMS` at the top of `simulator.py`.

### `MassiveClient` (`massive_client.py`)

- Polls `GET /v2/snapshot/locale/us/markets/stocks/tickers` with all tracked tickers in one request.
- Price field preference: `lastTrade.p` (Developer/Advanced plans only) → falls back to `day.c`.
- Error handling:
  - **403**: clears `_tickers` to stop hammering with a bad key.
  - **429**: backs off 60 seconds, then continues. Does **not** clear tickers (transient, not an auth failure).
  - **Other HTTP errors**: backs off 5 seconds.
  - **Network errors**: backs off 5 seconds.
- `httpx.AsyncClient` is kept alive for the poll loop's lifetime (avoids per-poll TCP handshake).
- `get_daily_bars` uses `GET /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}`.

### Factory (`factory.py`)

```python
source = create_market_data_source(cache)
```

Reads `MASSIVE_API_KEY` from env (`.strip()` handles accidental whitespace). Uses lazy imports — neither `numpy` (simulator) nor `httpx` (MassiveClient) is loaded unless that implementation is selected.

---

## FastAPI integration (planned — `app/main.py`)

Not yet implemented. When built, follow this pattern from `../planning/MARKET_INTERFACE.md`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .market import PriceCache, create_market_data_source
from .database import get_default_watchlist, get_open_positions

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = PriceCache()
    source = create_market_data_source(cache)
    watchlist = await get_default_watchlist() or DEFAULT_TICKERS
    positions = list(await get_open_positions())   # {ticker: qty} → keys
    tickers = list(dict.fromkeys(watchlist + positions))  # union, deduped
    await source.start(tickers)
    app.state.cache = cache
    app.state.market = source
    yield
    await source.stop()

app = FastAPI(lifespan=lifespan)
```

SSE endpoint, watchlist routes, portfolio routes, and chat route designs are in `../planning/PLAN.md` and `../planning/archive/MARKET_INTERFACE.md`.

---

## LLM integration (planned)

Use the `cerebras` skill (LiteLLM → OpenRouter → `openrouter/openai/gpt-oss-120b` with Cerebras inference). Use structured outputs. See `../planning/PLAN.md §9` for the full prompt design and response schema.

---

## Testing

```bash
uv run pytest              # all tests
uv run pytest tests/market/ -v   # market subsystem only
uv run pytest -k cache     # filter by name
```

Tests live in `tests/market/`, mirroring `app/market/`. All async tests use `pytest-asyncio` (`asyncio_mode = "auto"` in `pyproject.toml`).

**Coverage (76 tests, all passing):**

| Module | Tests |
|---|---|
| `cache.py` | 12 — all public methods, fan-out, full-queue drop, idempotent unsubscribe |
| `simulator.py` | 22 — GBM params, Cholesky rebuild, add/remove at runtime, shock/revert, stop idempotency |
| `massive_client.py` | 21 — parse (8), lifecycle (7), error paths including 403 + 429 (4), daily bars (2) |
| `factory.py` | 8 — all key-selection paths, poll interval, interface conformance |
| `models.py` | 7 — direction property, field assertions, optional vwap |
| `models.py` | 6 — direction property, all three directions, field assertions |

**Conventions:**
- Long poll intervals (`poll_interval=999.0`) in `_make_client()` prevent background polling from firing during unit tests.
- Use `patch("asyncio.sleep", new_callable=AsyncMock)` when testing backoff paths.
- After `asyncio.create_task(coro)`, add `await asyncio.sleep(0)` before cancelling so the coroutine reaches its first `await` (required in Python 3.13+).

---

## Dependencies

Runtime: `fastapi`, `uvicorn[standard]`, `httpx`, `numpy`, `pydantic`, `litellm`, `python-dotenv`, `aiosqlite`

Dev/test: `pytest`, `pytest-asyncio`, `pytest-mock`, `respx`

Managed with `uv`. To add a dependency: `uv add <package>`. To install all: `uv sync`.
