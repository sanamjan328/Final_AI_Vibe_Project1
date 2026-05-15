# Massive API (formerly Polygon.io) — Reference Documentation

## Overview

Massive (rebranded from Polygon.io on October 30, 2025) provides REST and WebSocket APIs for
real-time and historical US stock market data. Existing Polygon.io API keys and integrations
continue to work without changes.

- **Docs:** https://massive.com/docs
- **Base URL:** `https://api.massive.com` (legacy `https://api.polygon.io` also works)
- **Python client:** `pip install -U massive`

---

## Authentication

Pass the API key as a query parameter (`apiKey`) or as a Bearer token header. The query
parameter form is simpler and works identically:

```python
# Query parameter (recommended for simplicity)
params = {"apiKey": "YOUR_API_KEY"}
requests.get(url, params=params)

# Bearer header (also accepted)
headers = {"Authorization": "Bearer YOUR_API_KEY"}
requests.get(url, headers=headers)
```

The official `massive` Python client handles auth automatically:

```python
from massive import RESTClient
client = RESTClient(api_key="YOUR_API_KEY")
# or set env var MASSIVE_API_KEY and call RESTClient() with no args
```

---

## Rate Limits & Tiers

| Plan | Price | Rate Limit | Data Freshness | WebSocket |
|---|---|---|---|---|
| **Free** | $0 | **5 req/min** | 15-min delayed | No |
| **Starter** | ~$29/mo | Unlimited | 15-min delayed | No |
| **Developer** | ~$79/mo | Unlimited | **Real-time** | No |
| **Advanced** | ~$199/mo | Unlimited | Real-time | **Yes** |
| **Business** | Custom | Unlimited | Real-time + FMV | Yes |

**FinAlly poll budget (free tier):** One bulk snapshot call per 15 s covers all 10 default
tickers comfortably within the 5 req/min limit (4 req/min used, 1 in reserve).

---

## Key Endpoints for FinAlly

### 1. Bulk Snapshot — Multiple Tickers (primary polling endpoint)

The main endpoint used by the FinAlly polling loop. One call covers the entire watchlist.

```
GET /v2/snapshot/locale/us/markets/stocks/tickers
```

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `tickers` | string | Comma-separated ticker list. Omit to return all ~10 000 tickers. |
| `include_otc` | boolean | Include OTC securities (default: false). |

**Request example:**

```python
import requests

BASE = "https://api.massive.com"
API_KEY = "YOUR_API_KEY"

def get_bulk_snapshot(api_key: str, tickers: list[str]) -> dict[str, dict]:
    """Returns a dict keyed by ticker symbol."""
    resp = requests.get(
        f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers",
        params={"apiKey": api_key, "tickers": ",".join(tickers)},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return {item["ticker"]: item for item in data.get("tickers", [])}

snapshots = get_bulk_snapshot(API_KEY, ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"])

for symbol, item in snapshots.items():
    # lastTrade.p is only populated on Developer/Advanced plans; fall back to day.c
    last_trade = item.get("lastTrade") or {}
    price      = last_trade.get("p") or item["day"]["c"]
    change_pct = item["todaysChangePerc"]     # % change from previous close
    prev_close = item["prevDay"]["c"]         # previous session close
    print(f"{symbol}: ${price:.2f}  ({change_pct:+.2f}%)")
```

**Response shape:**

```json
{
  "status": "OK",
  "count": 2,
  "tickers": [
    {
      "ticker": "AAPL",
      "todaysChange": 1.23,
      "todaysChangePerc": 0.65,
      "updated": 1605195918306274000,
      "day": {
        "o": 189.30, "h": 191.05, "l": 188.82, "c": 190.54,
        "v": 52341000, "vw": 190.12
      },
      "prevDay": {
        "o": 188.10, "h": 189.90, "l": 187.35, "c": 189.31,
        "v": 48200000, "vw": 188.75
      },
      "min": {
        "o": 190.48, "h": 190.60, "l": 190.40, "c": 190.54,
        "v": 145200, "vw": 190.51, "t": 1605195840000
      },
      "lastTrade": { "p": 190.54, "s": 100, "t": 1605195918306274000 },
      "lastQuote": { "P": 190.55, "p": 190.54, "t": 1605195918507251700 }
    }
  ]
}
```

**Field reference:**

| Field | Description |
|---|---|
| `lastTrade.p` | Most recent trade price — Developer/Advanced plans only; absent on Free/Starter. Fall back to `day.c` |
| `todaysChangePerc` | % change from previous session close — use as "daily change %" |
| `todaysChange` | Dollar change from previous session close |
| `day.c` | Current session's latest bar close (fallback if `lastTrade` absent) |
| `day.o / h / l` | Session open / high / low |
| `day.v` | Session volume |
| `prevDay.c` | Previous session close |
| `min.c` | Most recent minute bar close |
| `updated` | Nanosecond Unix timestamp of last update |

> **Note on "daily change %":** `todaysChangePerc` is intraday change from the *previous session
> close*. This is the correct field to surface as "daily change %" in the watchlist panel. It
> resolves the open question in PLAN.md §13 — no daily-open concept needed.

---

### 2. Single Ticker Snapshot

```
GET /v2/snapshot/locale/us/markets/stocks/tickers/{ticker}
```

Same response schema as above but for one ticker. Useful for on-demand lookups outside the
main polling loop (e.g., validating a newly added watchlist ticker).

```python
resp = requests.get(
    f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers/AAPL",
    params={"apiKey": API_KEY},
    timeout=10,
)
item = resp.json()["ticker"]
# lastTrade.p requires Developer/Advanced plan; fall back to day.c on free/Starter
last_trade = item.get("lastTrade") or {}
price      = last_trade.get("p") or item["day"]["c"]
change_pct = item["todaysChangePerc"]
```

---

### 3. Unified Snapshot v3 (up to 250 tickers per page)

The newer v3 endpoint supports pagination and a slightly different field naming convention.
Useful if the watchlist grows beyond what a single v2 call can handle.

```
GET /v3/snapshot?ticker.any_of=AAPL,TSLA,GOOGL&limit=250
```

```python
resp = requests.get(
    f"{BASE}/v3/snapshot",
    params={"apiKey": API_KEY, "ticker.any_of": "AAPL,TSLA,GOOGL", "limit": 250},
    timeout=10,
)
for item in resp.json().get("results", []):
    price = item["last_trade"]["price"]
    change_pct = item["session"]["change_percent"]
```

---

### 4. Historical Aggregates (OHLCV Bars)

Retrieves OHLCV bars over a date range. Use to seed chart history.

```
GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
```

**Path parameters:**

| Parameter | Description |
|---|---|
| `ticker` | Ticker symbol |
| `multiplier` | Integer time unit (e.g., `1`) |
| `timespan` | `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year` |
| `from` / `to` | `YYYY-MM-DD` or Unix millisecond timestamp |

**Query parameters:** `adjusted` (default: true), `sort` (`asc`/`desc`), `limit` (max 50 000)

```python
from datetime import date, timedelta

def get_daily_bars(api_key: str, ticker: str, days: int = 30) -> list[dict]:
    to_date   = date.today().isoformat()
    from_date = (date.today() - timedelta(days=days)).isoformat()
    resp = requests.get(
        f"{BASE}/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}",
        params={"apiKey": api_key, "adjusted": "true", "sort": "asc", "limit": 5000},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])

bars = get_daily_bars(API_KEY, "AAPL", days=30)
# Each bar: {"o": .., "h": .., "l": .., "c": .., "v": .., "vw": .., "t": <unix ms>}
```

---

### 5. Previous Day Bar

```
GET /v2/aggs/ticker/{ticker}/prev
```

Returns the most recent completed session's OHLCV. Useful as a fallback before the snapshot's
`prevDay` populates (e.g., early pre-market).

```python
resp = requests.get(
    f"{BASE}/v2/aggs/ticker/AAPL/prev",
    params={"apiKey": API_KEY},
    timeout=10,
)
prev = resp.json()["results"][0]
prev_close = prev["c"]
```

---

### 6. Daily Ticker Summary (with pre/after-hours)

```
GET /v1/open-close/{ticker}/{date}
```

Returns OHLCV for a specific historical date including pre-market and after-hours prices.

```python
resp = requests.get(
    f"{BASE}/v1/open-close/AAPL/2024-01-15",
    params={"apiKey": API_KEY, "adjusted": "true"},
    timeout=10,
)
day = resp.json()
# day["open"], day["high"], day["low"], day["close"], day["afterHours"], day["preMarket"]
```

---

## Async Raw HTTP (httpx — for use in FastAPI background tasks)

```python
import httpx

BASE = "https://api.massive.com"

async def fetch_bulk_snapshot(api_key: str, tickers: list[str]) -> dict[str, dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers",
            params={"apiKey": api_key, "tickers": ",".join(tickers)},
        )
        resp.raise_for_status()
        data = resp.json()
    return {item["ticker"]: item for item in data.get("tickers", [])}

async def fetch_daily_bars(
    api_key: str, ticker: str, from_date: str, to_date: str
) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{BASE}/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}",
            params={"apiKey": api_key, "adjusted": "true", "sort": "asc", "limit": 5000},
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
```

---

## Official Python Client (`massive`)

The official client wraps all endpoints and handles pagination automatically.

```python
from massive import RESTClient

client = RESTClient(api_key="YOUR_API_KEY")

# Bulk snapshot
snapshot = client.get_snapshot_all(
    market_type="stocks",
    tickers=["AAPL", "MSFT", "GOOGL", "NVDA"],
)
for item in snapshot:
    print(f"{item.ticker}: ${item.day.c:.2f}  ({item.todays_change_perc:+.2f}%)")

# Historical daily bars (auto-paginated)
for bar in client.list_aggs("AAPL", 1, "day", "2024-01-01", "2024-12-31", limit=50000):
    print(bar.timestamp, bar.close)

# Previous close
result = client.get_previous_close_agg("AAPL")
prev_close = result[0].close
```

---

## WebSocket Streaming (Advanced/Business plans only)

Real-time trade events pushed server → client. Not available on Free or Starter.

```python
from massive import WebSocketClient

def on_message(msgs):
    for m in msgs:
        if m.event_type == "T":  # trade
            print(f"{m.symbol}: ${m.price}  size={m.size}")

ws = WebSocketClient(
    api_key="YOUR_API_KEY",
    subscriptions=["T.AAPL", "T.MSFT", "T.GOOGL"],  # or "T.*" for all trades
)
ws.run(handle_msg=on_message)
```

Subscription prefixes: `T.*` = all trades, `Q.*` = all quotes, `A.*` = per-second aggregates,
`AM.*` = per-minute aggregates. For FinAlly, REST polling is the default; WebSocket is a
stretch-goal upgrade for paid plans.

---

## Error Handling

| HTTP Status | Meaning | Action |
|---|---|---|
| 200 | OK | Parse and cache |
| 403 | Bad/missing API key | Log error, halt polling |
| 429 | Rate limit exceeded | Exponential back-off; double poll interval |
| 500 / 503 | Server error | Retry after 5 s |

```python
import asyncio
import httpx

async def safe_poll(api_key: str, tickers: list[str]) -> dict[str, dict] | None:
    try:
        return await fetch_bulk_snapshot(api_key, tickers)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 403:
            raise  # unrecoverable — bad key
        await asyncio.sleep(60 if status == 429 else 5)
    except httpx.RequestError:
        await asyncio.sleep(5)
    return None
```

---

## Polling Strategy for FinAlly

| Plan | Poll Interval | Notes |
|---|---|---|
| Free (5 req/min) | **15 s** | 1 bulk call covers all 10 default tickers |
| Starter+ (unlimited, delayed) | 5–10 s | More responsive UI, same data freshness |
| Developer+ (unlimited, real-time) | 2–5 s | Near-real-time pricing |

Implementation: one `asyncio` background task that loops forever, polls the bulk snapshot
endpoint for `positions ∪ watchlist` tickers (not just watchlist — portfolio P&L needs prices
for held tickers even if removed from the watchlist), writes results to a shared in-memory
price cache, then sleeps for the configured interval.
