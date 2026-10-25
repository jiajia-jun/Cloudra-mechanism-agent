import { expect, test } from '@playwright/test';
import { installApiMocks, openModelSettings, openSpa } from './fixtures';

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
  let searchProvider = 'deepseek';
  let searchKeySet = false;
  const searchSaved: Array<Record<string, unknown>> = [];
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
    } else if (path.endsWith('/config') || path.endsWith('/config/search')) {
      if (request.method() === 'PATCH') saved.push(request.postDataJSON());
      if (path.endsWith('/config/search')) {
        const changes = request.postDataJSON();
        searchSaved.push(changes);
        if ('search_provider' in changes) searchProvider = changes.search_provider;
        if ('deepseek_api_key' in changes) searchKeySet = Boolean(changes.deepseek_api_key);
      }
      result = { config_file: '/tmp/config.yaml', coordinator: slot, follower: slot,
        search_provider: searchProvider, deepseek_api_key_set: searchKeySet,
        tool_document_loading: { strategy: 'llm', semantic_backend: 'jev',
          jev: { endpoint: '', model: '', key_set: false, min_probability: null, max_tools: null },
          reranker: { endpoint: '', model: '', key_set: false, min_score: null, max_tools: null } } };
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
  await openModelSettings(page);
  return { saved, searchSaved, polls: () => polls };
}

test('Codex login uses device code and keeps model configuration explicit', async ({ page }, testInfo) => {
  const state = await mockCodex(page);
  const panel = page.getByRole('region', { name: 'Codex OAuth' });
  await expect(panel.getByText('未登录', { exact: true })).toBeVisible();
  await expect(page.getByLabel('api key', { exact: true })).toHaveCount(0);
  await panel.getByRole('button', { name: '登录 ChatGPT / Codex', exact: true }).click();
  await expect(panel.getByText('ABCD-EFGH', { exact: true })).toBeVisible();
  await expect(panel.getByRole('link', { name: '打开授权页面' }))
    .toHaveAttribute('href', 'https://auth.openai.com/codex/device');
  await testInfo.attach('Codex device login', { body: await page.screenshot(), contentType: 'image/png' });
  await expect(panel.getByText('已登录', { exact: true })).toBeVisible();
  expect(state.saved).toHaveLength(0);
  await page.locator('.modal').getByRole('button', { name: '保存', exact: true }).first().click();
  expect(state.saved).toHaveLength(1);
  expect(state.saved[0]).toMatchObject({ slot: 'coordinator', changes: { provider: 'openai-codex', key: '' } });
  await panel.getByRole('button', { name: '退出 Codex 登录' }).click();
  await expect(panel.getByText('未登录', { exact: true })).toBeVisible();
});

test('Search/Fetch settings preserve a saved key when changing provider', async ({ page }) => {
  const state = await mockCodex(page);
  const panel = page.getByRole('region', { name: '网页搜索与读取' });
  const keyInput = panel.getByLabel('DeepSeek API 凭据');
  await expect(panel.getByLabel('搜索服务')).toHaveValue('deepseek');
  await keyInput.fill('shared-search-fetch-key');
  await expect(keyInput).toHaveAttribute('type', 'password');
  await panel.getByRole('button', { name: '保存搜索设置', exact: true }).click();
  await expect(keyInput).toHaveValue('');
  await expect(keyInput).toHaveAttribute('placeholder', '已设置；留空保留原凭据');
  expect(state.searchSaved[0]).toEqual({
    search_provider: 'deepseek', deepseek_api_key: 'shared-search-fetch-key',
  });

  await panel.getByLabel('搜索服务').selectOption('auto');
  await panel.getByRole('button', { name: '保存搜索设置', exact: true }).click();
  await expect.poll(() => state.searchSaved.length).toBe(2);
  expect(state.searchSaved[1]).toEqual({ search_provider: 'auto' });
  await panel.getByRole('button', { name: '清除 DeepSeek 凭据', exact: true }).click();
  await expect.poll(() => state.searchSaved.length).toBe(3);
  expect(state.searchSaved[2]).toEqual({ deepseek_api_key: '' });
});

test('closing settings stops device-code polling', async ({ page }) => {
  const state = await mockCodex(page);
  const panel = page.getByRole('region', { name: 'Codex OAuth' });
  await panel.getByRole('button', { name: '登录 ChatGPT / Codex', exact: true }).click();
  await expect(panel.getByText('ABCD-EFGH', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '返回聊天', exact: true }).click();
  const countAtClose = state.polls();
  await page.waitForTimeout(1200);
  expect(state.polls()).toBe(countAtClose);
});
