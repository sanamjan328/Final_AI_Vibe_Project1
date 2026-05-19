import { test, expect } from '@playwright/test';

test.describe('Watchlist', () => {
  test('add and remove a ticker', async ({ page }) => {
    await page.goto('/');

    // Wait for the watchlist to render first.
    await expect(page.getByTestId('watchlist')).toBeVisible();

    // Add PYPL via the add input. Expected: an input with
    // data-testid="watchlist-add-input" and a button with
    // data-testid="watchlist-add-submit".
    const addInput = page.getByTestId('watchlist-add-input');
    await addInput.fill('PYPL');
    await page.getByTestId('watchlist-add-submit').click();

    // PYPL should appear in the watchlist.
    const pyplRow = page.getByTestId('watchlist-ticker-PYPL');
    await expect(pyplRow).toBeVisible({ timeout: 10000 });

    // Remove PYPL. Expected: a remove button scoped to the row with
    // data-testid="watchlist-remove-PYPL" (or similar within the row).
    await page.getByTestId('watchlist-remove-PYPL').click();

    await expect(pyplRow).toHaveCount(0, { timeout: 10000 });
  });
});
