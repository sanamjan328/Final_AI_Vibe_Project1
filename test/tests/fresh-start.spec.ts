import { test, expect } from '@playwright/test';

test.describe('Fresh start', () => {
  test('default watchlist, $10,000 balance, prices streaming', async ({ page }) => {
    await page.goto('/');

    // Wait for the watchlist to populate. The watchlist container is expected
    // to expose `data-testid="watchlist"`; individual rows expose
    // `data-testid="watchlist-row"` (or `watchlist-ticker-<SYMBOL>`).
    const watchlist = page.getByTestId('watchlist');
    await expect(watchlist).toBeVisible();

    const rows = page.getByTestId(/^watchlist-(row|ticker-)/);
    await expect.poll(async () => rows.count(), {
      message: 'Expected at least 10 watchlist rows from seed data',
      timeout: 15000,
    }).toBeGreaterThanOrEqual(10);

    // Cash balance shows $10,000 on a fresh seed.
    const cash = page.getByTestId('cash-balance');
    await expect(cash).toContainText(/\$\s?10[,.]?000/);

    // Connection status dot should be green (connected). Element is expected
    // to have data-testid="connection-status" and either a class or
    // data-status attribute indicating "connected".
    const status = page.getByTestId('connection-status');
    await expect(status).toHaveAttribute('data-status', 'connected', {
      timeout: 10000,
    });

    // Prices are streaming. Capture one price, wait a few seconds, expect
    // any ticker price text to have changed.
    const firstPrice = page.getByTestId(/^price-/).first();
    await expect(firstPrice).toBeVisible();

    const initialPrices = await page
      .getByTestId(/^price-/)
      .allTextContents();

    await expect.poll(async () => {
      const current = await page.getByTestId(/^price-/).allTextContents();
      return current.some((p, i) => p !== initialPrices[i]);
    }, {
      message: 'Expected at least one price to change within 8s (SSE updates)',
      timeout: 8000,
    }).toBe(true);
  });
});
