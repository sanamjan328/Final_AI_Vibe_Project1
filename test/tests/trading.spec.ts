import { test, expect } from '@playwright/test';

/**
 * Parse a dollar-formatted string like "$9,810.45" or "10000" into a number.
 */
function parseCash(text: string | null): number {
  if (!text) return NaN;
  const cleaned = text.replace(/[^0-9.\-]/g, '');
  return parseFloat(cleaned);
}

/**
 * Read the current AAPL quantity from the portfolio API. Returns 0 if no
 * position exists. The tests share a single SQLite DB across runs, so we
 * compute deltas against the pre-test state rather than absolute values.
 */
async function getAAPLQuantity(baseURL: string): Promise<number> {
  const res = await fetch(`${baseURL}/api/portfolio`);
  const body = await res.json();
  const row = (body.positions ?? []).find((p: { ticker: string }) => p.ticker === 'AAPL');
  return row ? Number(row.quantity) : 0;
}

test.describe('Trading', () => {
  test('buy then sell AAPL updates cash and positions', async ({ page, baseURL }) => {
    await page.goto('/');

    const cashEl = page.getByTestId('cash-balance');
    await expect(cashEl).toBeVisible();

    const initialCashText = await cashEl.textContent();
    const initialCash = parseCash(initialCashText);
    expect(initialCash).toBeGreaterThan(0);

    const startQty = await getAAPLQuantity(baseURL!);

    // Buy 1 AAPL through the trade bar.
    await page.getByTestId('trade-ticker').fill('AAPL');
    await page.getByTestId('trade-quantity').fill('1');
    await page.getByTestId('trade-buy').click();

    // Cash should decrease after the buy.
    await expect.poll(async () => {
      const t = await cashEl.textContent();
      return parseCash(t);
    }, {
      message: 'Expected cash balance to decrease after buying 1 AAPL',
      timeout: 10000,
    }).toBeLessThan(initialCash);

    // AAPL should appear in the positions table.
    const positionsTable = page.getByTestId('positions-table');
    await expect(positionsTable).toBeVisible();
    await expect(page.getByTestId('position-AAPL')).toBeVisible({
      timeout: 10000,
    });

    // Confirm via the API that quantity increased by exactly 1.
    await expect.poll(async () => getAAPLQuantity(baseURL!), {
      message: 'Expected AAPL quantity to increase by 1 after buy',
      timeout: 10000,
    }).toBe(startQty + 1);

    // Sell the 1 AAPL share we just bought.
    await page.getByTestId('trade-ticker').fill('AAPL');
    await page.getByTestId('trade-quantity').fill('1');
    await page.getByTestId('trade-sell').click();

    // Cash should rise back toward (not necessarily exactly) the pre-trade value.
    // Prices fluctuate, so we tolerate a small delta.
    await expect.poll(async () => {
      const t = await cashEl.textContent();
      return parseCash(t);
    }, {
      message: 'Expected cash balance to recover after selling AAPL',
      timeout: 10000,
    }).toBeGreaterThan(initialCash - initialCash * 0.05);

    // AAPL quantity should return to its pre-test baseline. If the baseline
    // was 0, the row should be absent or show quantity 0; otherwise it should
    // exactly match startQty.
    await expect.poll(async () => getAAPLQuantity(baseURL!), {
      message: 'Expected AAPL quantity to return to pre-test baseline after sell',
      timeout: 10000,
    }).toBe(startQty);
  });
});
