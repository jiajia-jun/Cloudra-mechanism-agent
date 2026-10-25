import { expect, test, type Page } from '@playwright/test';
import type { RuntimeConfig } from '../src/types';
import { AGENT, PROJECT_ACTIVE, installApiMocks, openSpa } from './fixtures';

async function mockModelConfig(page: Page) {
  const slot = {
    provider: 'custom', model: 'test-model', url: 'https://llm.example/v1',
    key_set: true, context_window: 200000, timeout: 300,
    supports_vision: true, reasoning_effort: 'high',
  };
  const config: RuntimeConfig = {
    config_file: '/tmp/config.yaml', coordinator: { ...slot }, follower: { ...slot },
    search_provider: 'deepseek', deepseek_api_key_set: false,
    tool_document_loading: {
      strategy: 'llm', semantic_backend: 'jev',
      jev: { endpoint: '', model: '', key_set: false, min_probability: null, max_tools: null },
      reranker: { endpoint: '', model: '', key_set: false, min_score: null, max_tools: null },
    },
  };
  const globalPatches: unknown[] = [];
  await page.route('**/api/v2/runtime/config', (route) => {
    if (route.request().method() === 'PATCH') {
      const patch = route.request().postDataJSON();
      globalPatches.push(patch);
      Object.assign(config[patch.slot as 'coordinator' | 'follower'], patch.changes);
    }
    return route.fulfill({ json: config });
  });
  await page.route('**/api/v2/runtime/providers', (route) => route.fulfill({ json: [{
    id: 'custom', name: 'Custom', default_model: 'test-model', default_url: slot.url,
    models: ['test-model', 'chosen-model'], context_window: 200000,
    supports_vision: true, native_search: 'off',
  }] }));
  return { config, globalPatches };
}

for (const scope of ['agent', 'project'] as const) {
  test(`model choice stays within the selected ${scope} and keeps global defaults`, async ({ page }) => {
    await installApiMocks(page, { jobs: [], agents: scope === 'agent' ? [AGENT] : [] });
    const { globalPatches } = await mockModelConfig(page);
    const localPatches: Array<Record<string, unknown>> = [];
    const path = scope === 'agent'
      ? `**/api/v2/agents/${AGENT.id}/settings`
      : `**/api/v2/projects/${PROJECT_ACTIVE.id}`;
    await page.route(path, (route) => {
      const patch = route.request().postDataJSON();
      localPatches.push(patch);
      const data = scope === 'agent'
        ? { ...AGENT, settings: { ...AGENT.settings, ...patch } }
        : { ...PROJECT_ACTIVE, settings: patch.settings };
      return route.fulfill({ json: { command_id: 'cmd_settings', event_id: 'ev_settings', accepted: true, data } });
    });
    await openSpa(page);
    await expect(page.getByRole('button', { name: '选择模型', exact: true })).toHaveCount(0);
    await expect(page.getByTestId('composer-input')).toBeDisabled();
    await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
    if (scope === 'agent') await expect(page.locator('.breadcrumb-agent-name')).toHaveText(AGENT.display_name);
    const trigger = page.getByRole('button', { name: '选择模型', exact: true });
    await expect(trigger).toContainText('test-model');
    await trigger.click();
    const menu = page.getByRole('dialog', { name: '模型选择', exact: true });
    await menu.getByLabel('搜索模型', { exact: true }).fill('chosen');
    await expect(menu.getByRole('button', { name: 'test-model', exact: true })).toHaveCount(0);
    await menu.getByRole('button', { name: 'chosen-model', exact: true }).click();
    await expect(trigger).toContainText('chosen-model');
    expect(localPatches).toHaveLength(1);
    expect(localPatches[0]).toMatchObject(scope === 'agent'
      ? { model: 'chosen-model' }
      : { settings: { orchestration_mode: 'standard', defaults: { model: 'chosen-model' } } });
    expect(globalPatches).toEqual([]);
  });
}

test('an existing agent clears ultra reasoning back to default and Escape closes the menu', async ({ page }) => {
  const agent = { ...AGENT, settings: { ...AGENT.settings, model: 'test-model', reasoning_effort: 'ultra' } };
  await installApiMocks(page, { jobs: [], agents: [agent] });
  await mockModelConfig(page);
  const patches: Array<Record<string, unknown>> = [];
  await page.route(`**/api/v2/agents/${agent.id}/settings`, (route) => {
    const patch = route.request().postDataJSON();
    patches.push(patch);
    Object.assign(agent.settings, patch);
    return route.fulfill({ json: { command_id: 'cmd_settings', event_id: 'ev_settings', accepted: true, data: agent } });
  });
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await expect(page.locator('.breadcrumb-agent-name')).toHaveText(agent.display_name);
  await page.getByRole('button', { name: '选择模型', exact: true }).click();
  const menu = page.getByRole('dialog', { name: '模型选择', exact: true });
  await menu.getByRole('button', { name: '默认', exact: true }).click();
  await expect(menu.getByRole('button', { name: '默认', exact: true })).toHaveAttribute('aria-pressed', 'true');
  expect(patches).toEqual([{ model: 'test-model', reasoning_effort: '' }]);
  await page.keyboard.press('Escape');
  await expect(menu).toBeHidden();
  await page.getByRole('button', { name: '选择模型', exact: true }).click();
  await expect(menu.getByRole('button', { name: '默认', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('model control shows saved defaults and refreshes after editing the original global configuration', async ({ page }) => {
  await installApiMocks(page, { agents: [], jobs: [] });
  await mockModelConfig(page);
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  const trigger = page.getByRole('button', { name: '选择模型', exact: true });
  await expect(trigger).toContainText('test-model');
  await expect(trigger.locator('.model-trigger-effort')).toHaveText('高');
  await trigger.click();
  await page.getByRole('button', { name: '编辑模型…', exact: true }).click();
  const coordinator = page.locator('.modal-section').filter({ hasText: 'Coordinator slot' });
  await coordinator.getByLabel('model (模型名称)', { exact: false }).fill('edited-global-model');
  await coordinator.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(coordinator.getByRole('button', { name: 'Save', exact: true })).toBeEnabled();
  await page.locator('.modal').getByRole('button', { name: 'close', exact: true }).click();
  await expect(trigger).toContainText('edited-global-model');
  await expect(trigger.locator('.model-trigger-effort')).toHaveText('高');
});
