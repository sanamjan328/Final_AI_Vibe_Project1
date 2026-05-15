# Market Data Backend — Code Review

**Reviewer:** Claude Sonnet 4.6  
**Date:** 2026-05-15  
**Scope:** `backend/app/market/` (all 6 modules) + `backend/tests/market/` (all 5 test files)  
**Python version:** 3.13.7  

---

## Test Results

```
74 tests collected
73 passed, 1 failed
Runtime: 13.02s
```

**Failing test:** `tests/market/test_massive_client.py::test_stop_cancels_task`

---

## Overall Assessment

The market data backend is well-implemented and largely production-quality. The architecture cleanly separates the six concerns (models, cache, interface, simulator, Massive client, factory) with no leakage between layers. The GBM math is correct, the cache fan-out design is sound, and the test suite is thorough. The single test failure is a test bug caused by a Python 3.13 asyncio behavior change — it is not a defect in production code. Three minor production code issues and four test coverage gaps are documented below.

---

## 1. Failing Test — Root Cause and Fix

### `test_stop_cancels_task` — Python 3.13 asyncio task scheduling change

**Location:** `backend/tests/market/test_massive_client.py:224`

**What the test does:** Creates an asyncio task (`fake_loop`) that records a `cancelled = True` flag in its `except CancelledError` block, immediately assigns it to `client._task`, then calls `client.stop()` and asserts the flag is `True`.

**Why it fails in Python 3.13:** In Python 3.13, cancelling a task before the event loop has had a chance to schedule it (i.e., before any `await` point after `create_task`) discards the task without running any of its coroutine body. The `except CancelledError` handler in `fake_loop` therefore never executes and `cancelled` stays `False`.

This is **not a bug in `MassiveClient.stop()`**. The `stop()` implementation correctly calls `task.cancel()` and awaits the result. The test setup is the problem.

**Fix** — yield to the event loop after `create_task` so the task reaches its first `await` before being cancelled:

```python
@pytest.mark.asyncio
async def test_stop_cancels_task():
    client, _ = _make_client()
    cancelled = False

    async def fake_loop():
        nonlocal cancelled
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            cancelled = True
            raise

    client._task = asyncio.create_task(fake_loop())
    await asyncio.sleep(0)   # <-- one line added; yields so fake_loop starts
    await client.stop()
    assert cancelled
```

---

## 2. Production Code Issues

### 2a. Overly broad exception clause in `get_daily_bars`

**File:** `backend/app/market/massive_client.py:124`

```python
except (httpx.HTTPError, Exception) as e:
```

`httpx.HTTPError` is a subclass of `Exception`, making the first branch unreachable and the clause equivalent to a bare `except Exception`. The intent (catch anything and return `[]`) is correct but the code should say what it means:

```python
except Exception as e:
```

Or more precisely, if you want to distinguish HTTP errors from network errors, split them as done in `_fetch_snapshots`.

### 2b. Shock events can fire during the post-shock reversion window

**File:** `backend/app/market/simulator.py:165`

The shock check is evaluated before the revert check:

```python
# Shock event: override GBM with a sudden ±5% jump
if np.random.random() < P_EVENT:        # checked first
    ...
    new_states[ticker] = _TickerState(..., revert=EVENT_REVERT_TICKS)
    continue

# Normal GBM step
effective_drift = 0.0 if state.revert > 0 else state.drift   # checked second
```

This allows a second shock to trigger while the ticker is already in its post-shock reversion window, resetting `revert` back to `EVENT_REVERT_TICKS`. The `MARKET_SIMULATOR.md` design doc shows the inverse ordering — revert-check first, shock only in an `elif`. The behavior is not broken, but it deviates from the spec and means consecutive back-to-back shocks are slightly more common than intended. Consider aligning code or spec.

### 2c. Cache is empty for up to 500ms after simulator startup

**File:** `backend/app/market/simulator.py:142`

```python
async def _tick_loop(self) -> None:
    while True:
        await asyncio.sleep(TICK_INTERVAL)   # sleeps FIRST
        updates = self._compute_tick()
```

Because the loop sleeps before computing the first tick, `cache.get_all()` returns `{}` for up to 500ms after `start()` is called. The SSE endpoint sends an immediate snapshot to every connecting client — a browser opening in that window sees an empty watchlist until the first tick fires.

The same issue exists in `MassiveClient._poll_loop`, where `asyncio.sleep(self._poll_interval)` is at the end of the loop but the first HTTP fetch happens only if `self._tickers` is non-empty; that case is fine since the sleep is after the fetch. However, the simulator truly defers its first price computation.

Fix for the simulator — compute the first tick immediately, then enter the timed loop:

```python
async def _tick_loop(self) -> None:
    updates = self._compute_tick()       # prime the cache immediately
    if updates:
        await self._cache.update(updates)
    while True:
        await asyncio.sleep(TICK_INTERVAL)
        updates = self._compute_tick()
        if updates:
            await self._cache.update(updates)
```

Low-priority for a demo but the right fix for production.

---

## 3. Design Doc vs. Implementation Divergences

All three divergences are in the docs — the code is correct in each case.

| File | Doc error | Actual implementation (correct) |
|------|-----------|----------------------------------|
| `MARKET_INTERFACE.md` | `_subscribers.discard(queue)` — `discard` is a set method; `_subscribers` is a `list` | `list.remove(queue)` wrapped in `try/except ValueError` |
| `MARKET_INTERFACE.md` | `MassiveClient.start()` sets `self._tickers = set(tickers)` without `.upper()` normalization | `{t.upper() for t in tickers}` — correctly normalizes |
| `MARKET_SIMULATOR.md` | Shows revert check before shock check (`if revert > 0 ... elif P_EVENT`) | Shock is checked first (`if P_EVENT ... continue; effective_drift = ... if revert`) — see §2b |
| `MARKET_INTERFACE.md` | Fan-out uses `await queue.put(u)` (blocking) | `queue.put_nowait(u)` with `QueueFull` swallow (non-blocking, correct) |

---

## 4. Module-by-Module Analysis

### `models.py`

Clean, minimal dataclasses with no dependencies. The `direction` property is a pure computed property — correct design choice. `DailyBar.vwap` optional field with `None` default is handled correctly (not a mutable default). No issues.

### `cache.py`

The lock design is correct: the asyncio lock is held only for the dict write, then released before the fan-out loop. In single-threaded asyncio this is safe — no other coroutine can run between lock release and subscriber iteration. The CPython GIL comment is accurate for read-path atomicity.

`put_nowait` with silent `QueueFull` drop is the right pattern for SSE: a lagging client misses some ticks but does not block the update path. `maxsize=1000` is a reasonable buffer (~8 minutes of history at 500ms ticks).

`get_all()` returning a shallow copy (`dict(self._prices)`) is correct — callers can iterate without racing against future updates.

### `interface.py`

The ABC correctly declares all five methods. Return types are accurately annotated. No issues.

### `simulator.py`

The GBM implementation is mathematically correct:
- The Itô correction `(μ - σ²/2)·Δt` is applied, eliminating Jensen's inequality upward bias.
- Per-tick parameters are correctly derived: `drift = (annual_drift - 0.5 * vol²) * (dt / seconds_per_year)`, `vol_per_tick = annual_vol * sqrt(dt / seconds_per_year)`.
- Cholesky decomposition on a symmetric positive-definite matrix correctly produces correlated normals.
- `max(price, 0.01)` floor prevents negative prices under extreme shocks.

One subtle inconsistency in the shock path: `change_pct` is stored as `round(shock_pct * 100, 4)`, but `change` is computed as `new_price - state.price`. If `new_price` is clamped to 0.01 (i.e., `state.price * (1 + shock_pct) < 0.01`), these two fields become inconsistent — `change` reflects the floor but `change_pct` reflects the raw shock. This edge case requires a price below ~$0.011 and is effectively unreachable given the seed prices and tick timescales, but it is worth noting.

`_rebuild_cholesky` is called on every `add_ticker`/`remove_ticker`. For 10–20 tickers this is fast (microseconds); at larger scales it would be worth batching or deferring.

### `massive_client.py`

The `httpx.AsyncClient` is created once and kept alive for the loop's lifetime — this is efficient (avoids per-poll TCP handshake). The `timeout=10.0` is reasonable; it is less than the minimum `poll_interval` of 15s, so a timeout cannot cause poll intervals to stack.

Error handling in `_fetch_snapshots`:
- **403**: clears `_tickers` to prevent continued hammering with a bad key. Good.
- **429**: backs off with a 60s sleep inside `_fetch_snapshots`, then the calling loop also sleeps `poll_interval` seconds before the next fetch. Total backoff = 60 + poll_interval ≈ 75s on free tier, which is safe.
- **Non-OK `status` field**: checked after `raise_for_status()` succeeds, so this catches Massive API-level errors (e.g., `"status": "ERROR"` with HTTP 200). Good defensive check.

The `_parse_snapshots` field precedence (`lastTrade.p` → `day.c`) matches the Massive API documentation in `MASSIVE_API.md`. The `todaysChange`/`todaysChangePerc` fields are used when present, with a computed fallback when absent — aligning `prev_price` semantics between the simulator (previous tick) and Massive (previous close).

### `factory.py`

The `.strip()` on the API key handles accidental whitespace in `.env` files. Lazy imports of concrete classes inside the `if` branch mean neither implementation is loaded unless selected — beneficial for import-time performance and avoids pulling in `numpy` or `httpx` unnecessarily in tests that only need the other path. No issues.

---

## 5. Test Coverage Assessment

### Well-covered

| Area | Tests |
|------|-------|
| `PriceCache` | All public methods, fan-out to multiple subscribers, full-queue drop behavior, idempotent unsubscribe, overwrite semantics (12 tests) |
| `MarketSimulator` | GBM parameters, Cholesky reconstruction for known/unknown tickers, add/remove at runtime, case normalization, revert decrement, empty ticker list, stop idempotency, cache persistence after removal (22 tests) |
| `MassiveClient._parse_snapshots` | `lastTrade.p` preference, `day.c` fallback, missing change fields computed from diff, nanosecond timestamp parsing, `updated=0` fallback to now, malformed entry skipping, empty list, rounding (8 tests) |
| `MassiveClient` lifecycle | start/stop, ticker normalization, idempotent remove, 403/network error handling, non-OK status (9 tests) |
| `Factory` | All 4 key-selection paths, default poll interval, custom poll interval, interface conformance, api_key passed through (8 tests) |
| `Models` | All three directions, field assertions, optional vwap (7 tests) |

### Coverage gaps

| Missing scenario | Risk | Notes |
|-----------------|------|-------|
| `_fetch_snapshots` with HTTP 429 | Medium | The 429 path calls `asyncio.sleep(60)` inside `_fetch_snapshots`. There is no test confirming this sleep fires and that the method returns `[]`. |
| `_poll_loop` end-to-end integration | Low | All `start()` tests mock `_poll_loop`. There is no test that the loop actually calls `_fetch_snapshots`, receives updates, and writes them to the cache. |
| Shock fires during reversion window | Low | Behavioral edge case (§2b) has no targeted test. |
| `change_pct` consistency in shock path | Very low | When `new_price` hits the 0.01 floor, `change_pct` and `change` fields become inconsistent. Practically unreachable but untested. |
| `get_daily_bars` HTTP 4xx/5xx errors | Low | `test_get_daily_bars_returns_empty_on_error` tests `httpx.RequestError` (network error) but not `httpx.HTTPStatusError` (e.g., a 404 or 503 from the bars endpoint). |

---

## 6. Architecture and Design Quality

**Strengths:**

- **Clean abstraction boundary.** `MarketDataSource` ABC enforces the contract. `__init__.py` exports only the interface and factory — callers cannot accidentally import a concrete class.
- **Correct lock scope.** `PriceCache` holds the asyncio lock for the minimum time (dict write only) and releases it before fan-out. No risk of deadlock.
- **Slow-client protection.** `put_nowait` + `QueueFull` swallow prevents a lagging SSE client from applying back-pressure to the market data pipeline.
- **Graceful key-failure handling.** The 403 path in `MassiveClient` clears the ticker set, halting all further polls with a bad key rather than burning API quota.
- **GBM math is correct.** Itô correction, Cholesky-correlated draws, price floor — all implemented as specified.
- **Factory lazy imports.** Neither numpy (simulator) nor httpx (MassiveClient) is imported in tests that only need the other implementation.
- **Good test isolation.** Long poll intervals (`poll_interval=999.0`) in `_make_client()` prevent background polling from contaminating unit tests.

**No significant design concerns.** The subsystem is production-quality within its stated scope.

---

## 7. Summary Table

| Category | Status |
|---------|--------|
| Tests passing | 73 / 74 |
| Failing test | 1 — test bug (Python 3.13 task scheduling), not a production defect |
| Production bugs | 0 critical |
| Minor production issues | 3 (overly broad except, shock-during-revert ordering, empty cache on startup) |
| Doc/code divergences | 4 — all in docs; implementation is correct in each case |
| Test coverage gaps | 5 minor scenarios identified |
| Architecture | Clean, spec-compliant, extensible |

---

## 8. Recommended Actions

Priority order:

1. **Fix `test_stop_cancels_task`** — add `await asyncio.sleep(0)` after `asyncio.create_task(fake_loop())`. One-line change, unblocks clean CI.

2. **Narrow the exception clause in `get_daily_bars`** — change `except (httpx.HTTPError, Exception)` to `except Exception` (or split into specific types). Makes intent explicit.

3. **Decide on shock-during-reversion behavior** — either update the simulator to check `revert > 0` before rolling for a shock (matching `MARKET_SIMULATOR.md`), or update the doc to reflect the current implementation. Pick one.

4. **Add a test for the HTTP 429 path** — `_fetch_snapshots` with a 429 response should confirm `asyncio.sleep(60)` is called and the method returns `[]`.

5. **Consider priming the cache immediately on simulator startup** (§2c) — low-priority, but eliminates the empty-watchlist flash on first page load.
