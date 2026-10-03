import { expect, test } from '@playwright/test';
import {
  AGENT,
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
    await page.getByTestId('cancel-all-compute-foot').click();
    await expect.poll(() => mocks.cancelAllHits.length).toBe(0);
  });

  test('Cancel All: accept confirm posts and toasts counts', async ({ page }) => {
    const mocks = await installApiMocks(page, { jobs: [] });
    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toContain('never killed');
      await dialog.accept();
    });
    await openSpa(page);
    await page.getByTestId('cancel-all-compute-foot').click();
    await expect.poll(() => mocks.cancelAllHits.length).toBe(1);
    await expect(
      page.getByText(
        formatCancelAllToast({
          ready_cancelled: 1,
          slurm_cancel_requested: 0,
          local_cancelled: 1,
        }),
      ),
    ).toBeVisible();
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
    await page.goto('/#token=sekrit-e2e');
    await page.getByPlaceholder('新建项目名…').waitFor({ state: 'visible' });
    await expect.poll(() => new URL(page.url()).hash).toBe('');
    const stored = await page.evaluate(() => sessionStorage.getItem('cloudra.api_token'));
    expect(stored).toBe('sekrit-e2e');
  });
});


test('language switch preserves the new project entry and persists English', async ({ page }) => {
  await installApiMocks(page, { jobs: [] });
  await openSpa(page);
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await page.getByPlaceholder('新建项目名…').fill('reaction draft');
  await page.getByRole('button', { name: 'EN', exact: true }).click();
  await expect(page.getByPlaceholder('New project name…')).toHaveValue('reaction draft');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await page.reload();
  await expect(page.getByPlaceholder('New project name…')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await page.getByText('Archived Projects (1)', { exact: true }).click();
  await expect(page.getByTestId(`hard-delete-${PROJECT_ARCHIVED.id}`)).toBeVisible();
  await page.getByRole('button', { name: '中', exact: true }).click();
  await expect(page.getByPlaceholder('新建项目名…')).toBeVisible();
});
