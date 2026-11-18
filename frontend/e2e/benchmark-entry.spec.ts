import { expect, test } from '@playwright/test';
import { PROJECT_ACTIVE, installApiMocks, openSpa } from './fixtures';

for (const labels of [
  { language: 'Chinese', more: '更多', benchmark: 'Benchmark 评测', settings: '全局设置', console: '控制台', ops: '计算调度', cancel: '取消所有项目的计算' },
  { language: 'English', more: 'More', benchmark: 'Benchmark', settings: 'Global Settings', console: 'Console', ops: 'Compute Ops', cancel: 'Cancel compute across all projects' },
]) {
  test(`${labels.language}: More opens Benchmark and preserves cancellation consent`, async ({ page }) => {
    const mocks = await installApiMocks(page, { jobs: [] });
    await page.route('**/api/v2/benchmark/*', async (route) => {
      const path = new URL(route.request().url()).pathname;
      const responses: Record<string, unknown> = {
        '/api/v2/benchmark/status': {
          batch_id: null,
          status: 'idle',
          started_at: null,
          finished_at: null,
          config: {},
          tasks: [],
        },
        '/api/v2/benchmark/catalog': { tiers: [] },
        '/api/v2/benchmark/runs': { batches: [] },
      };
      if (!(path in responses)) return route.fallback();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(responses[path]),
      });
    });

    await openSpa(page);
    const sidebar = page.locator('aside.left-sidebar');
    await sidebar.getByText(PROJECT_ACTIVE.name, { exact: true }).click();
    await expect(page.getByTestId('composer-input')).toBeEnabled();
    if (labels.language === 'English') {
      await page.getByRole('button', { name: 'EN', exact: true }).click();
    }
    const more = sidebar.locator('summary').filter({ hasText: labels.more });
    const benchmark = sidebar.getByRole('button', { name: labels.benchmark, exact: true });
    const cancel = page.getByRole('button', { name: labels.cancel, exact: true });

    await expect(more).toBeVisible({ timeout: 1500 });
    await expect(sidebar.getByRole('button', { name: labels.settings, exact: true })).toBeVisible();
    await expect(benchmark).toBeHidden();
    await expect(cancel).toBeHidden();
    await more.click();
    await expect(benchmark).toBeVisible();
    await expect(cancel).toHaveCount(0);
    expect(mocks.cancelAllHits).toHaveLength(0);

    await benchmark.click();
    const panel = page.locator('.bm-modal');
    await expect(panel.getByText('Benchmark cockpit', { exact: true })).toBeVisible();
    await expect(cancel).toBeHidden();
    expect(mocks.cancelAllHits).toHaveLength(0);
    await panel.getByRole('button', { name: '✕', exact: true }).click();
    await expect(panel).toBeHidden();
    await expect(more).toBeVisible();
    await expect(benchmark).toBeHidden();

    await page.locator('.view-mode-btn').filter({hasText:labels.console}).click();
    await page.getByRole('button',{name:labels.ops}).click();
    await expect(cancel).toBeVisible();
    const pendingDialog = page.waitForEvent('dialog');
    const click = cancel.click();
    const dialog = await pendingDialog;
    expect(dialog.type()).toBe('confirm');
    expect(mocks.cancelAllHits).toHaveLength(0);
    await dialog.dismiss();
    await click;
    expect(mocks.cancelAllHits).toHaveLength(0);
  });
}
