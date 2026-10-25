import { expect, test } from '@playwright/test';
import { AGENT, PROJECT_ACTIVE, RUNTIME_CONFIG, installApiMocks, openModelSettings, openSpa } from './fixtures';

test('folder picker localizes failures, retries and selection', async ({ page }) => {
  await installApiMocks(page, { projects: [], jobs: [] });
  let attempts = 0;
  await page.route('**/api/v2/fs/browse*', async (route) => {
    attempts += 1;
    if (attempts === 1) return route.fulfill({ status: 401, json: { detail: 'invalid token' } });
    return route.fulfill({ json: { current: '/work', parent: '/', home: '/home', cwd: '/work', writable: true, shortcuts: [], entries: [{ name: 'reactions', path: '/work/reactions', is_dir: true }] } });
  });
  await openSpa(page);
  await page.getByRole('button', { name: '选择项目', exact: true }).click();
  await page.getByRole('button', { name: '新建项目', exact: true }).click();
  await page.getByRole('dialog', { name: '新建项目', exact: true }).getByRole('button', { name: '选择', exact: true }).click();
  const picker = page.getByRole('dialog', { name: '选择文件夹', exact: true });
  await expect(picker.getByRole('alert')).toContainText('登录状态已失效');
  await expect(picker.getByText('此文件夹中没有子文件夹', { exact: true })).toHaveCount(0);
  await expect(picker.getByRole('button', { name: '选择', exact: true })).toBeDisabled();
  await expect(picker.getByText('GUI Picker', { exact: true })).toHaveCount(0);
  await picker.getByRole('button', { name: '重试', exact: true }).click();
  await picker.getByRole('button', { name: 'reactions', exact: true }).click();
  await picker.getByRole('button', { name: '选择', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '新建项目', exact: true }).getByLabel('文件夹', { exact: true })).toHaveValue('/work/reactions');
  await page.getByRole('dialog', { name: '新建项目', exact: true }).getByRole('button', { name: '取消', exact: true }).click();
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await page.getByLabel('语言', { exact: true }).selectOption('en');
  await page.getByRole('button', { name: 'Back to chat', exact: true }).click();
  await page.getByRole('button', { name: 'Choose project', exact: true }).click();
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await page.getByRole('dialog', { name: 'New project', exact: true }).getByRole('button', { name: 'Choose', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Choose folder', exact: true }).getByRole('button', { name: 'Select', exact: true })).toBeEnabled();
  await expect(page.getByLabel('Folder path', { exact: true })).toBeVisible();
});

test('composer model menu searches models and saves reasoning without settings navigation', async ({ page }) => {
  await installApiMocks(page, { projects: [], jobs: [] });
  const slot = { provider: 'example', model: 'model-a', url: 'https://example.test/v1', key_set: true, context_window: 1000, timeout: 60, reasoning_effort: 'medium' };
  const config = { ...RUNTIME_CONFIG, coordinator: { ...slot }, follower: { ...slot } };
  const patches: Array<{ slot: string; changes: Record<string, unknown> }> = [];
  await page.route('**/api/v2/runtime/config', async (route) => {
    if (route.request().method() === 'PATCH') {
      const patch = route.request().postDataJSON(); patches.push(patch);
      Object.assign(config.coordinator, patch.changes);
    }
    return route.fulfill({ json: config });
  });
  await page.route('**/api/v2/runtime/providers', (route) => route.fulfill({ json: [{ id: 'example', name: 'Example', default_model: 'model-a', default_url: slot.url, models: ['model-a', 'model-b'], context_window: 1000, supports_vision: true, native_search: '' }] }));
  await openSpa(page);
  await page.getByRole('button', { name: '选择模型', exact: true }).click();
  const menu = page.getByRole('dialog', { name: '模型选择', exact: true });
  await expect(menu.getByRole('heading', { name: 'Example', exact: true })).toBeVisible();
  await expect(menu.getByRole('button', { name: 'model-a', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await menu.getByRole('button', { name: '高', exact: true }).click();
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0]).toEqual({ slot: 'coordinator', changes: { model: 'model-a', reasoning_effort: 'high' } });
  await menu.getByLabel('搜索模型', { exact: true }).fill('model-b');
  await expect(menu.getByRole('button', { name: 'model-a', exact: true })).toHaveCount(0);
  await menu.getByRole('button', { name: 'model-b', exact: true }).click();
  await expect(page.getByRole('button', { name: '选择模型', exact: true })).toContainText('model-b');
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await expect(page.getByRole('navigation', { name: '设置分类', exact: true }).getByRole('button', { name: '模型', exact: true })).toHaveCount(0);
});

for (const scope of ['agent', 'project'] as const) {
  test(`composer model choice updates the selected ${scope} without changing global defaults`, async ({ page }) => {
    await installApiMocks(page, { jobs: [], agents: scope === 'agent' ? [AGENT] : [] });
    const localPatches: Array<Record<string, unknown>> = [];
    const globalPatches: unknown[] = [];
    await page.route('**/api/v2/runtime/providers', (route) => route.fulfill({ json: [{
      id: 'custom', name: 'Custom', default_model: 'test-model', default_url: 'https://llm.example/v1',
      models: ['test-model', 'chosen-model'], context_window: 200000,
      supports_vision: true, native_search: 'off',
    }] }));
    await page.route('**/api/v2/runtime/config', (route) => {
      if (route.request().method() === 'PATCH') globalPatches.push(route.request().postDataJSON());
      return route.fulfill({ json: RUNTIME_CONFIG });
    });
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
    await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
    if (scope === 'agent') await expect(page.locator('.breadcrumb-agent-name')).toHaveText(AGENT.display_name);
    await expect(page.getByTestId('composer-input')).toBeEnabled();
    await page.getByRole('button', { name: '选择模型', exact: true }).click();
    await page.getByRole('button', { name: 'chosen-model', exact: true }).click();
    await expect(page.getByRole('button', { name: '选择模型', exact: true })).toContainText('chosen-model');
    expect(localPatches).toHaveLength(1);
    expect(localPatches[0]).toMatchObject(scope === 'agent'
      ? { model: 'chosen-model' }
      : { settings: { orchestration_mode: 'standard', defaults: { model: 'chosen-model' } } });
    expect(globalPatches).toEqual([]);
  });
}

test('existing agent can clear an ultra reasoning override back to default', async ({ page }) => {
  const agent = { ...AGENT, settings: { ...AGENT.settings, model: 'test-model', reasoning_effort: 'ultra' } };
  await installApiMocks(page, { jobs: [], agents: [agent] });
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

test('composer shows global model settings before opening its menu and after editing them', async ({ page }) => {
  await installApiMocks(page, { projects: [], jobs: [] });
  const config = { ...RUNTIME_CONFIG, coordinator: { ...RUNTIME_CONFIG.coordinator, model: 'initial-global-model', reasoning_effort: 'high' } };
  await page.route('**/api/v2/runtime/config', (route) => {
    if (route.request().method() === 'PATCH') Object.assign(config.coordinator, route.request().postDataJSON().changes);
    return route.fulfill({ json: config });
  });
  await openSpa(page);
  const trigger = page.getByRole('button', { name: '选择模型', exact: true });
  await expect(trigger).toContainText('initial-global-model');
  await expect(trigger.locator('.model-trigger-effort')).toHaveText('高');
  await openModelSettings(page);
  const coordinator = page.locator('.modal-section').filter({ hasText: '主控模型' });
  await coordinator.getByLabel('模型名称', { exact: false }).fill('edited-global-model');
  await coordinator.getByRole('button', { name: '保存', exact: true }).click();
  await expect(coordinator.getByRole('button', { name: '保存', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '返回聊天', exact: true }).click();
  await expect(trigger).toContainText('edited-global-model');
  await expect(trigger.locator('.model-trigger-effort')).toHaveText('高');
});

test('new folder action closes its menu and focuses the folder name', async ({ page }) => {
  await installApiMocks(page, { projects: [], jobs: [] });
  await page.route('**/api/v2/fs/browse*', (route) => route.fulfill({ json: {
    current: '/tmp', parent: '/', home: '/tmp', cwd: '/tmp', writable: true,
    entries: [], shortcuts: [{ name: 'Home', path: '/tmp' }],
  } }));
  await openSpa(page);
  await page.getByRole('button', { name: '选择项目', exact: true }).click();
  await page.getByRole('button', { name: '新建项目', exact: true }).click();
  await page.getByRole('dialog', { name: '新建项目', exact: true }).getByRole('button', { name: '选择', exact: true }).click();
  const picker = page.getByRole('dialog', { name: '选择文件夹', exact: true });
  await expect(picker.getByRole('button', { name: '选择', exact: true })).toBeEnabled();
  await picker.getByLabel('更多操作', { exact: true }).click();
  await picker.getByRole('button', { name: '新建文件夹', exact: true }).click();
  await expect(picker.getByRole('button', { name: '新建文件夹', exact: true })).toBeHidden();
  await expect(picker.getByLabel('文件夹名称', { exact: true })).toBeFocused();
});
