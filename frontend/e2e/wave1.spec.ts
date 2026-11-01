import { expect, test } from '@playwright/test';
import {
  AGENT,
  JOB,
  PROJECT_ACTIVE,
  PROJECT_ARCHIVED,
  installApiMocks,
  openSpa,
} from './fixtures';
import {
  cancelAllComputeConfirm,
  formatCancelAllToast,
  hardDeleteProjectConfirm,
} from '../src/destructiveActions';

test.describe('destructive confirms', () => {
  test('Cancel All: dismiss confirm does not hit API', async ({ page }) => {
    const mocks = await installApiMocks(page, { jobs: [] });
    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toBe(cancelAllComputeConfirm());
      await dialog.dismiss();
    });
    await openSpa(page);
    await page.locator('aside.left-sidebar summary').filter({ hasText: '更多' }).click();
    await page.getByTestId('cancel-all-compute-foot').click();
    await expect.poll(() => mocks.cancelAllHits.length).toBe(0);
  });

  test('Cancel All: accept confirm posts and toasts counts', async ({ page }) => {
    const mocks = await installApiMocks(page, { jobs: [] });
    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toBe(cancelAllComputeConfirm());
      await dialog.accept();
    });
    await openSpa(page);
    await page.locator('aside.left-sidebar summary').filter({ hasText: '更多' }).click();
    await page.getByTestId('cancel-all-compute-foot').click();
    await expect.poll(() => mocks.cancelAllHits.length).toBe(1);
    await expect(
      page.getByText(
        formatCancelAllToast({
          ready_cancelled: 1,
          cancel_requested: 1,
        }),
      ),
    ).toBeVisible();
  });

  test('Cancel All: disables duplicate requests and refreshes cancellation-in-progress', async ({ page }) => {
    await installApiMocks(page, { jobs: [JOB] });
    let cancelHits = 0;
    let stopping = false;
    let releaseCancel: (() => void) | undefined;
    const cancelResponse = new Promise<void>((resolve) => { releaseCancel = resolve; });
    await page.route('**/api/v2/compute/cancel-all', async (route) => {
      cancelHits += 1;
      await cancelResponse;
      stopping = true;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ ready_cancelled: 0, cancel_requested: 1 }),
      });
    });
    await page.route('**/api/v2/projects/*/compute/jobs?*', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([{ ...JOB, state: stopping ? 'cancel_requested' : 'running' }]),
      });
    });
    await openSpa(page);
    await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
    await page.locator('.view-mode-btn').filter({ hasText: '控制台' }).click();
    await page.getByRole('button', { name: '计算调度', exact: false }).click();
    const jobRow = page.locator('.ops-table tbody tr').filter({ hasText: '#7' });
    await expect(jobRow.getByText('running', { exact: true })).toBeVisible();
    page.once('dialog', async (dialog) => { await dialog.accept(); });
    const more = page.locator('aside.left-sidebar summary').filter({ hasText: '更多' });
    await more.click();
    const button = page.getByTestId('cancel-all-compute-foot');
    await button.click();
    await expect(button).toBeDisabled();
    await expect(button).toHaveText('请求中…');
    await expect.poll(() => cancelHits).toBe(1);
    await button.evaluate((element: HTMLButtonElement) => { element.click(); });
    expect(cancelHits).toBe(1);
    releaseCancel?.();
    await expect(button).toBeEnabled();
    await expect(page.getByText('已取消 0 个排队任务；已请求停止 1 个运行任务，等待确认退出。')).toBeVisible();
    await expect(jobRow.getByText('取消中', { exact: true })).toBeVisible();
    await expect(jobRow.getByText('已取消', { exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: '项目总览', exact: true }).click();
    await expect(page.locator('.portal-nav-card').filter({ hasText: '量子化学计算资源调度' })).toContainText('1 个任务取消中');
  });

  test('Cancel All: failed request restores the button without claiming cancellation', async ({ page }) => {
    await installApiMocks(page, { jobs: [JOB] });
    let stopping = false;
    await page.route('**/api/v2/projects/*/compute/jobs?*', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([{ ...JOB, state: stopping ? 'cancel_requested' : 'running' }]),
      });
    });
    await page.route('**/api/v2/compute/cancel-all', async (route) => {
      // A lost/error response does not prove that the server made no change.
      stopping = true;
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '暂时无法取消计算' }),
      });
    });
    page.once('dialog', async (dialog) => { await dialog.accept(); });
    await openSpa(page);
    await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
    await page.locator('.view-mode-btn').filter({ hasText: '控制台' }).click();
    await page.getByRole('button', { name: '计算调度', exact: false }).click();
    const jobRow = page.locator('.ops-table tbody tr').filter({ hasText: '#7' });
    await expect(jobRow.getByText('running', { exact: true })).toBeVisible();
    await page.locator('aside.left-sidebar summary').filter({ hasText: '更多' }).click();
    const button = page.getByTestId('cancel-all-compute-foot');
    await button.click();
    await expect(page.getByText('暂时无法取消计算')).toBeVisible();
    await expect(button).toBeEnabled();
    await expect(button).toHaveText('取消全部计算');
    await expect(page.locator('.toast.ok')).toHaveCount(0);
    await expect(jobRow.getByText('取消中', { exact: true })).toBeVisible({ timeout: 1500 });
  });

  for (const surface of ['queue', 'summary']) test(`Cancel All: stale ${surface} response cannot overwrite stopping state`, async ({ page }) => {
    await installApiMocks(page, { jobs: [JOB] });
    let stopping = false;
    let delayNext = surface === 'summary';
    let heldRequest = false;
    let releaseOld: (() => void) | undefined;
    const oldResponse = new Promise<void>((resolve) => { releaseOld = resolve; });
    await page.route('**/api/v2/projects/*/compute/jobs?*', async (route) => {
      const row = { ...JOB, state: stopping ? 'cancel_requested' : 'running' };
      if (delayNext) {
        delayNext = false;
        heldRequest = true;
        await oldResponse;
      }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify([row]) });
    });
    await page.route('**/api/v2/compute/cancel-all', async (route) => {
      stopping = true;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ ready_cancelled: 0, cancel_requested: 1 }),
      });
    });
    await openSpa(page);
    await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
    await page.locator('.view-mode-btn').filter({ hasText: '控制台' }).click();
    await page.getByRole('button', { name: '计算调度', exact: false }).click();
    const jobRow = page.locator('.ops-table tbody tr').filter({ hasText: '#7' });
    await expect(jobRow.getByText('running', { exact: true })).toBeVisible();
    if (surface === 'queue') {
      delayNext = true;
      await page.getByRole('button', { name: '刷新队列', exact: true }).click();
    }
    await expect.poll(() => heldRequest).toBe(true);
    page.once('dialog', async (dialog) => { await dialog.accept(); });
    await page.locator('aside.left-sidebar summary').filter({ hasText: '更多' }).click();
    await page.getByTestId('cancel-all-compute-foot').click();
    await expect(jobRow.getByText('取消中', { exact: true })).toBeVisible();
    const summaryCard = page.locator('.portal-nav-card').filter({ hasText: '量子化学计算资源调度' });
    if (surface === 'summary') {
      await page.getByRole('button', { name: '项目总览', exact: true }).click();
      await expect(summaryCard).toContainText('1 个任务取消中');
    }
    const oldDelivered = page.waitForResponse((response) => response.url().includes('/compute/jobs') && response.request().method() === 'GET');
    releaseOld?.();
    await oldDelivered;
    // Two frames allow React to apply a stale result if the guard is absent.
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    if (surface === 'queue') {
      await expect(jobRow.getByText('取消中', { exact: true })).toBeVisible({ timeout: 500 });
    } else {
      await expect(summaryCard).toContainText('1 个任务取消中', { timeout: 500 });
    }
  });

  test('Hard delete: dismiss confirm does not DELETE', async ({ page }) => {
    const mocks = await installApiMocks(page, { jobs: [] });
    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toBe(hardDeleteProjectConfirm(PROJECT_ARCHIVED.name));
      await dialog.dismiss();
    });
    await openSpa(page);
    await page.getByText('已归档项目 (1)').click();
    await page.getByTestId(`hard-delete-${PROJECT_ARCHIVED.id}`).click();
    await expect.poll(() => mocks.deleteHits.length).toBe(0);
  });

  test('Hard delete: accept confirm DELETEs with hard=true', async ({ page }) => {
    const mocks = await installApiMocks(page, { jobs: [] });
    page.once('dialog', async (dialog) => {
      await dialog.accept();
    });
    await openSpa(page);
    await page.getByText('已归档项目 (1)').click();
    await page.getByTestId(`hard-delete-${PROJECT_ARCHIVED.id}`).click();
    await expect.poll(() => mocks.deleteHits.length).toBe(1);
    expect(mocks.deleteHits[0]).toContain(`projects/${PROJECT_ARCHIVED.id}`);
    expect(mocks.deleteHits[0]).toContain('hard=true');
  });
});

test.describe('composer hijack', () => {
  for (const entry of ['decision window', 'collapsed composer']) test(`pending interaction routes ${entry} to respond, not messages`, async ({ page }) => {
    const interaction = {
      interaction_id: 'ixn_1',
      id: 'ixn_1',
      session_id: AGENT.id,
      prompt: 'which solvent?',
    };
    const mocks = await installApiMocks(page, {
      interactions: [interaction],
      jobs: [],
    });
    const messagePosts: string[] = [];
    await page.route('**/api/v2/agents/*/messages', async (route) => {
      messagePosts.push(route.request().url());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          command_id: 'c',
          accepted: true,
          event_id: 'e',
          data: AGENT,
        }),
      });
    });

    await openSpa(page);
    // AttentionDock also shows the project name when interactions are pending —
    // click the sidebar row, not getByText(name).
    await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
    const prompt = page.getByTestId('interaction-prompt-window');
    await expect(prompt.getByText(AGENT.display_name, { exact: true })).toBeVisible();
    await expect(page.getByTestId('interaction-prompt-window').getByText('which solvent?', { exact: true })).toBeVisible({ timeout: 10_000 });
    if (entry === 'collapsed composer') {
      await prompt.getByRole('button', { name: '收起 ↓' }).click();
      await expect(page.getByTestId('interaction-collapsed-bar')).toBeVisible();
    }
    const box = entry === 'decision window' ? prompt.getByRole('textbox') : page.getByTestId('composer-input');
    await expect(box).toBeEnabled();
    await box.fill('ethanol');
    await page.getByRole('button', { name: entry === 'decision window' ? '提交回答 ↵' : 'Send', exact: true }).click();
    await expect.poll(() => mocks.respondHits.length).toBe(1);
    expect(mocks.respondHits[0]).toMatchObject({
      payload: { response: 'ethanol' },
    });
    expect(String((mocks.respondHits[0] as { path: string }).path)).toContain('ixn_1');
    expect(messagePosts).toEqual([]);
  });
});

test.describe('token bootstrap', () => {
  test('#token= is scrubbed from the address bar', async ({ page }) => {
    await installApiMocks(page, { jobs: [] });
    await openSpa(page, '#token=sekrit-e2e');
    await expect.poll(() => new URL(page.url()).hash).toBe('');
    const stored = await page.evaluate(() => sessionStorage.getItem('cloudra.api_token'));
    expect(stored).toBe('sekrit-e2e');
  });
});


test('language switch preserves the new project entry and persists English', async ({ page }) => {
  await installApiMocks(page, { jobs: [] });
  await openSpa(page);
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await page.getByRole('button', { name: '新建项目', exact: true }).click();
  await page.getByPlaceholder('新建项目名…').fill('reaction draft');
  await page.getByRole('button', { name: 'EN', exact: true }).click();
  await expect(page.getByPlaceholder('New project name…')).toHaveValue('reaction draft');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await page.reload();
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await expect(page.getByPlaceholder('New project name…')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await page.getByText('Archived Projects (1)', { exact: true }).click();
  await expect(page.getByTestId(`hard-delete-${PROJECT_ARCHIVED.id}`)).toBeVisible();
  await page.getByRole('button', { name: '中', exact: true }).click();
  await expect(page.getByPlaceholder('新建项目名…')).toBeVisible();
});
