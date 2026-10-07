import { expect, test } from '@playwright/test';
import { installApiMocks, openSpa } from './fixtures';

async function mockCodex(page: import('@playwright/test').Page) {
  await installApiMocks(page);
  const slot = {
    provider: 'openai-codex', model: 'gpt-6-sol',
    url: 'https://chatgpt.com/backend-api/codex', key_set: false,
    context_window: 200000, timeout: 300, supports_vision: true,
  };
  let authenticated = false;
  let polls = 0;
  const saved: Array<Record<string, unknown>> = [];
  await page.route('**/api/v2/runtime/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let result: unknown;
    if (path.endsWith('/providers')) {
      result = [{
        id: 'openai-codex', name: 'OpenAI Codex (ChatGPT OAuth)',
        default_url: slot.url, default_model: slot.model,
        models: [slot.model], context_window: 200000,
        supports_vision: true, native_search: 'off',
      }, { id: 'custom', name: 'Custom', models: [] }];
    } else if (path.endsWith('/config')) {
      if (request.method() === 'PATCH') saved.push(request.postDataJSON());
      result = { config_file: '/tmp/config.yaml', coordinator: slot, follower: slot };
    } else if (path.endsWith('/codex/status')) {
      result = { authenticated, account_id: authenticated ? 'account-test' : null, expires_at: null };
    } else if (path.endsWith('/codex/device-login')) {
      result = {
        login_id: 'flow-test', user_code: 'ABCD-EFGH',
        verification_uri: 'https://auth.openai.com/codex/device',
        interval: 1, expires_at: Date.now() / 1000 + 600,
      };
    } else if (path.endsWith('/codex/device-poll')) {
      expect(request.postDataJSON()).toEqual({ login_id: 'flow-test' });
      authenticated = ++polls >= 2;
      result = { status: authenticated ? 'authorized' : 'pending' };
    } else if (path.endsWith('/codex/auth') && request.method() === 'DELETE') {
      authenticated = false;
      result = { status: 'logged_out' };
    } else {
      return route.fallback();
    }
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(result) });
  });
  await openSpa(page);
  await page.getByRole('button', { name: '全局设置', exact: true }).click();
  return { saved, polls: () => polls };
}

test('Codex login uses device code and keeps model configuration explicit', async ({ page }, testInfo) => {
  const state = await mockCodex(page);
  const panel = page.getByRole('region', { name: 'Codex OAuth' });
  await expect(panel.getByText('未登录', { exact: true })).toBeVisible();
  await expect(page.locator('.modal input[type="password"]')).toHaveCount(0);
  await panel.getByRole('button', { name: '登录 ChatGPT / Codex', exact: true }).click();
  await expect(panel.getByText('ABCD-EFGH', { exact: true })).toBeVisible();
  await expect(panel.getByRole('link', { name: '打开授权页面' }))
    .toHaveAttribute('href', 'https://auth.openai.com/codex/device');
  await testInfo.attach('Codex device login', { body: await page.screenshot(), contentType: 'image/png' });
  await expect(panel.getByText('已登录', { exact: true })).toBeVisible();
  expect(state.saved).toHaveLength(0);
  await page.locator('.modal').getByRole('button', { name: 'Save', exact: true }).first().click();
  expect(state.saved).toHaveLength(1);
  expect(state.saved[0]).toMatchObject({ slot: 'coordinator', changes: { provider: 'openai-codex', key: '' } });
  await panel.getByRole('button', { name: '退出 Codex 登录' }).click();
  await expect(panel.getByText('未登录', { exact: true })).toBeVisible();
});

test('closing settings stops device-code polling', async ({ page }) => {
  const state = await mockCodex(page);
  const panel = page.getByRole('region', { name: 'Codex OAuth' });
  await panel.getByRole('button', { name: '登录 ChatGPT / Codex', exact: true }).click();
  await expect(panel.getByText('ABCD-EFGH', { exact: true })).toBeVisible();
  await page.locator('.modal').getByRole('button', { name: 'close', exact: true }).click();
  const countAtClose = state.polls();
  await page.waitForTimeout(1200);
  expect(state.polls()).toBe(countAtClose);
});
