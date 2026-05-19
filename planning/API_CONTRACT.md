# FinAlly — Agent Coordination Contract

This document defines the integration points between all team members.
All agents MUST follow these interfaces exactly to ensure the system integrates correctly.

---

## Team Members & File Ownership

| Agent | Owns |
|---|---|
| database-engineer | `backend/app/db/` · `backend/tests/db/` |
| backend-api-engineer | `backend/app/api/` · `backend/app/main.py` · `backend/tests/api/` |
| llm-engineer | `backend/app/llm/` · `backend/tests/llm/` |
| frontend-engineer | `frontend/` (entire directory) |
| devops-engineer | `Dockerfile` · `docker-compose.yml` · `.env.example` · `scripts/` |
| integration-tester | `test/` (entire directory) |

Do NOT modify files owned by another agent unless you have coordinated first.

---

## Database Layer Interface (`backend/app/db/`)

The database engineer exports these functions from `backend/app/db/database.py`:

```python
async def get_db() -> aiosqlite.Connection:
    """Returns an open DB connection. Used as FastAPI dependency."""

async def init_db() -> None:
    """Called on app startup. Creates tables and seeds if needed."""
```

Database path: resolved from environment `DB_PATH` (default `db/finally.db` relative to project root).

### Tables (exact names — do not change)
- `users_profile` — `id`, `cash_balance`, `created_at`
- `watchlist` — `id`, `user_id`, `ticker`, `added_at` (UNIQUE: user_id+ticker)
- `positions` — `id`, `user_id`, `ticker`, `quantity`, `avg_cost`, `updated_at` (UNIQUE: user_id+ticker)
- `trades` — `id`, `user_id`, `ticker`, `side`, `quantity`, `price`, `executed_at`
- `portfolio_snapshots` — `id`, `user_id`, `total_value`, `recorded_at`
- `chat_messages` — `id`, `user_id`, `role`, `content`, `actions`, `created_at`

Default user_id for all operations: `"default"`
Default seed: user with cash_balance=10000.0, watchlist = [AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX]

---

## API Endpoints (Backend → Frontend contract)

Base URL: `http://localhost:8000`

### SSE Stream
```
GET /api/stream/prices
Content-Type: text/event-stream

Event format (JSON string in `data:` field):
{
  "ticker": "AAPL",
  "price": 191.23,
  "prev_price": 190.85,
  "change_pct": 0.20,
  "direction": "up",   // "up" | "down" | "flat"
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### Portfolio
```
GET /api/portfolio
Response: {
  "cash_balance": 9500.0,
  "total_value": 10234.50,
  "positions": [
    {
      "ticker": "AAPL",
      "quantity": 5.0,
      "avg_cost": 189.00,
      "current_price": 191.23,
      "unrealized_pnl": 11.15,
      "pnl_pct": 1.18
    }
  ]
}

POST /api/portfolio/trade
Body: { "ticker": "AAPL", "side": "buy", "quantity": 10 }
Response: {
  "success": true,
  "trade": { "ticker": "AAPL", "side": "buy", "quantity": 10, "price": 191.23, "executed_at": "..." },
  "cash_balance": 8108.50,
  "error": null   // or error string on failure
}

GET /api/portfolio/history
Response: [
  { "total_value": 10000.0, "recorded_at": "2024-01-01T12:00:00Z" }
]
```

### Watchlist
```
GET /api/watchlist
Response: [
  { "ticker": "AAPL", "price": 191.23, "prev_price": 190.85, "change_pct": 0.20, "direction": "up" }
]
// price/prev_price/change_pct/direction are null if not yet in price cache

POST /api/watchlist
Body: { "ticker": "PYPL" }
Response: { "ticker": "PYPL", "added": true }

DELETE /api/watchlist/{ticker}
Response: { "ticker": "AAPL", "removed": true }
```

### Chat
```
POST /api/chat
Body: { "message": "What should I buy?" }
Response: {
  "message": "Based on your portfolio...",
  "trades": [{ "ticker": "AAPL", "side": "buy", "quantity": 5 }],
  "watchlist_changes": [{ "ticker": "PYPL", "action": "add" }],
  "executed_trades": [...],    // trades that actually went through
  "failed_trades": [...],      // trades that failed + reason
  "executed_watchlist_changes": [...]
}
```

### System
```
GET /api/health
Response: { "status": "ok", "mode": "simulator" | "massive" }
```

---

## LLM Integration Interface (`backend/app/llm/`)

The LLM engineer exports from `backend/app/llm/chat.py`:

```python
async def process_chat_message(
    user_message: str,
    portfolio_context: dict,
    conversation_history: list[dict],
    mock: bool = False
) -> ChatResponse:
    ...

class ChatResponse(BaseModel):
    message: str
    trades: list[TradeAction] = []
    watchlist_changes: list[WatchlistAction] = []

class TradeAction(BaseModel):
    ticker: str
    side: str  # "buy" | "sell"
    quantity: float

class WatchlistAction(BaseModel):
    ticker: str
    action: str  # "add" | "remove"
```

Environment: reads `OPENROUTER_API_KEY` from `.env`.
Mock mode: when `LLM_MOCK=true` env var is set, return deterministic canned response.

---

## Market Data (already complete — do not modify)

The market module lives at `backend/app/market/`. It exports:
- `PriceCache` from `backend/app/market/cache.py`
- `MarketDataFactory` from `backend/app/market/factory.py` 
- `PriceUpdate` model from `backend/app/market/models.py`

The backend API engineer uses `MarketDataFactory` to start the background data source and reads from `PriceCache`.

---

## Frontend API Client

All fetch calls go to the same origin — no CORS config needed.
- SSE: `new EventSource('/api/stream/prices')`
- REST: `fetch('/api/portfolio')`, `fetch('/api/watchlist')`, etc.

---

## Environment Variables

```bash
OPENROUTER_API_KEY=...   # required for LLM
MASSIVE_API_KEY=          # optional; empty = use simulator
LLM_MOCK=false            # set to "true" for E2E tests
DB_PATH=db/finally.db    # optional override
```

---

## Dependency / Build Order

1. **database-engineer** and **frontend-engineer** and **devops-engineer** can start immediately (parallel)
2. **backend-api-engineer** can start after database-engineer publishes `backend/app/db/database.py`
3. **llm-engineer** can start after database-engineer publishes `backend/app/db/database.py`
4. **integration-tester** starts after all other agents have completed their core work and Dockerfile builds successfully
