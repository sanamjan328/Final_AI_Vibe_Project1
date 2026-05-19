# FinAlly — End-to-End Tests

Playwright tests that verify the FinAlly app works end-to-end against a real
running container. Tests assume the LLM is in mock mode (`LLM_MOCK=true`) so
chat scenarios are deterministic.

## Running locally

Start the backend (or full container) on port 8000, then:

```bash
cd test
npm install
npx playwright install chromium
BASE_URL=http://localhost:8000 npx playwright test
```

To run a single spec:

```bash
BASE_URL=http://localhost:8000 npx playwright test tests/fresh-start.spec.ts
```

To watch the browser as tests run:

```bash
BASE_URL=http://localhost:8000 npm run test:headed
```

## Running via Docker Compose

This spins up the app container and a Playwright container together; no local
Node install required.

```bash
cd test
docker compose -f docker-compose.test.yml up --build --exit-code-from playwright
```

## Test layout

- `tests/fresh-start.spec.ts` — default watchlist, cash balance, live prices
- `tests/watchlist.spec.ts` — add and remove a ticker
- `tests/trading.spec.ts` — buy + sell flow updates cash and positions
- `tests/portfolio.spec.ts` — heatmap and P&L chart render after a trade
- `tests/chat.spec.ts` — mock-LLM chat returns a response

## Selectors

Tests prefer `data-testid` attributes where the frontend exposes them, and fall
back to accessible roles / text content. If a test fails because a selector
does not exist, coordinate with the frontend engineer to add the missing
`data-testid` rather than relying on brittle CSS selectors.
