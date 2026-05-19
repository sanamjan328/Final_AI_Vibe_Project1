import { test, expect } from '@playwright/test';

/**
 * Requires the backend to be running with LLM_MOCK=true. The mock LLM
 * is expected to return the canned reply documented in the team-lead
 * brief: "I've analyzed your portfolio. You have a well-diversified
 * position. Consider adding some NVDA exposure for AI sector growth."
 * (See planning/PLAN.md §9 — LLM Mock Mode.)
 */
test.describe('Chat (LLM mock)', () => {
  test('assistant responds to a user message', async ({ page }) => {
    await page.goto('/');

    // Chat panel and input. Expected:
    //   data-testid="chat-panel"
    //   data-testid="chat-input"
    //   data-testid="chat-send"
    //   each message: data-testid="chat-message" with data-role="user"|"assistant"
    const chatPanel = page.getByTestId('chat-panel');
    await expect(chatPanel).toBeVisible();

    const input = page.getByTestId('chat-input');
    await input.fill('What should I buy?');
    await page.getByTestId('chat-send').click();

    // The user message should appear first.
    await expect(
      page.getByTestId('chat-message').filter({ hasText: 'What should I buy?' })
    ).toBeVisible({ timeout: 5000 });

    // Then an assistant message with non-empty content should appear.
    const assistantMessages = page
      .getByTestId('chat-message')
      .and(page.locator('[data-role="assistant"]'));

    await expect.poll(async () => {
      const count = await assistantMessages.count();
      if (count === 0) return '';
      return (await assistantMessages.last().textContent()) ?? '';
    }, {
      message: 'Expected a non-empty assistant response (LLM_MOCK=true)',
      timeout: 20000,
    }).not.toBe('');

    // In LLM_MOCK=true mode the response is deterministic.
    await expect(assistantMessages.last()).toContainText('NVDA', {
      timeout: 5000,
    });
  });
});
