import { test, expect } from '@playwright/test';

test.describe('Portfolio visualizations', () => {
  test('heatmap and P&L chart populate after a trade', async ({ page }) => {
    await page.goto('/');

    // Buy a share so the portfolio has a position to visualize.
    await expect(page.getByTestId('cash-balance')).toBeVisible();
    await page.getByTestId('trade-ticker').fill('AAPL');
    await page.getByTestId('trade-quantity').fill('1');
    await page.getByTestId('trade-buy').click();

    // Heatmap cell for AAPL. Expected:
    //   data-testid="portfolio-heatmap"
    //   data-testid="heatmap-cell-AAPL" inside it
    const heatmap = page.getByTestId('portfolio-heatmap');
    await expect(heatmap).toBeVisible();
    await expect(page.getByTestId('heatmap-cell-AAPL')).toBeVisible({
      timeout: 10000,
    });

    // P&L chart should have at least one data point. Expected:
    //   data-testid="pnl-chart" container with at least one
    //   data-testid="pnl-point" element OR an SVG <path>/<circle> child.
    const pnlChart = page.getByTestId('pnl-chart');
    await expect(pnlChart).toBeVisible();

    await expect.poll(async () => {
      const points = pnlChart.locator('[data-testid="pnl-point"], svg path, svg circle, canvas');
      return await points.count();
    }, {
      message: 'Expected at least one rendered point in P&L chart',
      timeout: 15000,
    }).toBeGreaterThan(0);
  });
});
