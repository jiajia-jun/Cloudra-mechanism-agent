import { expect, test } from '@playwright/test';
import { AGENT, PROJECT_ACTIVE, installApiMocks, openSpa } from './fixtures';

test('new chat sends the first query in the chosen workspace without a central button', async ({ page }) => {
  await installApiMocks(page, { jobs: [] });
  const created = { ...PROJECT_ACTIVE, id: 'proj_chat', name: 'Explore substitution' };
  const agent = { ...AGENT, id: 'agent_chat', project_id: created.id };
  const creates: unknown[] = [];
  const spawns: unknown[] = [];
  await page.route('**/api/v2/projects', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    creates.push(route.request().postDataJSON());
    await route.fulfill({ json: { command_id: 'cmd_create', event_id: 'ev_create', accepted: true, data: created } });
  });
  await page.route('**/api/v2/projects/proj_chat/agents', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: [agent] });
    spawns.push(route.request().postDataJSON());
    await route.fulfill({ json: { command_id: 'cmd_spawn', event_id: 'ev_spawn', accepted: true, data: agent } });
  });
  await page.route('**/api/v2/projects/proj_chat/view', (route) => route.fulfill({ json: { agents: spawns.length ? [agent] : [], cursor: 0 } }));
  await page.route('**/api/v2/agents/agent_chat', (route) => route.fulfill({ json: agent }));
  await openSpa(page);
  await page.getByRole('button', { name: '新聊天', exact: true }).click();
  await expect(page.locator('.welcome-state button')).toHaveCount(0);
  await expect(page.locator('.agentbar select')).toHaveCount(0);
  await expect(page.getByTestId('composer-input')).toBeEnabled();
  await page.getByRole('button', { name: '选择项目', exact: true }).click();
  await page.getByRole('option', { name: 'live', exact: true }).click();
  await page.getByTestId('composer-input').fill('Explore substitution');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect.poll(() => spawns.length).toBe(1);
  expect(creates).toEqual([{ name: 'Explore substitution', workspace_dir: '/tmp/live' }]);
  expect(spawns[0]).toMatchObject({ role_id: 'coordinator', query: 'Explore substitution', language: 'zh' });
  await expect(page.getByTestId('composer-input')).toHaveValue('');
  await page.getByRole('button', { name: '新聊天', exact: true }).click();
  await expect(page.locator('.welcome-state')).toBeVisible();
  await expect(page.getByRole('button', { name: '选择项目', exact: true })).toContainText('live');
  expect(creates).toHaveLength(1);
});

test('appearance and wallpaper settings persist outside the chat toolbar', async ({ page }) => {
  await installApiMocks(page, { jobs: [] });
  await openSpa(page);
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('button', { name: '外观', exact: true }).click();
  await page.getByLabel('界面主题', { exact: true }).selectOption('emerald');
  await page.getByLabel('壁纸', { exact: true }).selectOption('none');
  await page.getByRole('button', { name: '返回聊天', exact: true }).click();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'emerald');
  await expect(page.locator('html')).toHaveAttribute('data-wallpaper', 'none');
  await expect(page.locator('.agentbar select')).toHaveCount(0);
  await expect(page.locator('.welcome-state button')).toHaveCount(0);
});

test('retrying a failed first spawn reuses the created chat', async ({ page }) => {
  await installApiMocks(page, { projects: [], jobs: [] });
  const created = { ...PROJECT_ACTIVE, id: 'proj_retry', name: 'Retry question' };
  const agent = { ...AGENT, id: 'agent_retry', project_id: created.id };
  let creates = 0;
  let spawns = 0;
  await page.route('**/api/v2/projects', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    creates += 1;
    await route.fulfill({ json: { command_id: 'cmd_create', event_id: 'ev_create', accepted: true, data: created } });
  });
  await page.route('**/api/v2/projects/proj_retry/agents', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: spawns > 1 ? [agent] : [] });
    spawns += 1;
    if (spawns === 1) return route.fulfill({ status: 503, json: { detail: 'Temporary failure' } });
    return route.fulfill({ json: { command_id: 'cmd_spawn', event_id: 'ev_spawn', accepted: true, data: agent } });
  });
  await page.route('**/api/v2/projects/proj_retry/view', (route) => route.fulfill({ json: { agents: spawns > 1 ? [agent] : [], cursor: 0 } }));
  await page.route('**/api/v2/agents/agent_retry', (route) => route.fulfill({ json: agent }));
  await openSpa(page);
  await page.getByTestId('composer-input').fill('Retry question');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeEnabled();
  await expect(page.getByTestId('composer-input')).toHaveValue('Retry question');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect.poll(() => spawns).toBe(2);
  expect(creates).toBe(1);
  await expect(page.getByTestId('composer-input')).toHaveValue('');
});

test('new project uses a compact form and retains its fields after a creation failure', async ({ page }) => {
  await installApiMocks(page, { jobs: [] });
  const attempts: unknown[] = [];
  const created = { ...PROJECT_ACTIVE, id: 'proj_form', name: 'Mechanism study', workspace_dir: '/tmp/study' };
  let browseCalls = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v2/fs/browse') browseCalls += 1;
  });
  await page.route('**/api/v2/projects', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    attempts.push(route.request().postDataJSON());
    if (attempts.length === 1) return route.fulfill({ status: 503, json: { detail: 'Temporary failure' } });
    return route.fulfill({ json: { command_id: 'cmd_create', event_id: 'ev_create', accepted: true, data: created } });
  });
  await openSpa(page);
  await page.getByRole('button', { name: '选择项目', exact: true }).click();
  await page.getByRole('button', { name: '新建项目', exact: true }).click();
  const modal = page.getByRole('dialog', { name: '新建项目', exact: true });
  await expect(modal.getByRole('textbox')).toHaveCount(2);
  await expect(modal.getByRole('button', { name: '创建', exact: true })).toBeDisabled();
  await modal.getByLabel('项目名称', { exact: true }).fill(' Mechanism study ');
  await modal.getByLabel('文件夹', { exact: true }).fill('/tmp/study');
  await modal.getByRole('button', { name: '创建', exact: true }).click();
  await expect(modal.getByRole('alert')).toBeVisible();
  await expect(modal.getByLabel('项目名称', { exact: true })).toHaveValue(' Mechanism study ');
  await modal.getByRole('button', { name: '创建', exact: true }).click();
  await expect(modal).toHaveCount(0);
  expect(attempts).toEqual([
    { name: 'Mechanism study', workspace_dir: '/tmp/study' },
    { name: 'Mechanism study', workspace_dir: '/tmp/study' },
  ]);
  expect(browseCalls).toBe(0);
  await expect(page.getByRole('button', { name: '选择项目', exact: true })).toContainText('study');
});

for (const theme of ['glass', 'emerald']) {
  test(`${theme} uses the shared composer geometry without an inner focus box`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem('cloudra.theme', value), theme);
    await installApiMocks(page, { projects: [], jobs: [] });
    await openSpa(page);
    await expect(page.getByRole('button', { name: '选择项目', exact: true })).toHaveText('选择项目');
    await expect(page.locator('.welcome-mark img')).toBeVisible();
    await expect(page.locator('.welcome-mark img')).toHaveCSS('object-fit', 'contain');
    const composer = page.locator('.composer');
    const border = await composer.evaluate((el) => getComputedStyle(el).borderColor);
    await page.getByTestId('composer-input').focus();
    const inputStyle = await page.getByTestId('composer-input').evaluate((el) => {
      const style = getComputedStyle(el);
      return { outline: style.outlineWidth, border: style.borderWidth, background: style.backgroundColor, shadow: style.boxShadow };
    });
    expect(inputStyle).toEqual({ outline: '0px', border: '0px', background: 'rgba(0, 0, 0, 0)', shadow: 'none' });
    await expect(composer).toHaveCSS('border-radius', '24px');
    await expect(composer).toHaveCSS('border-color', border);
    await expect(page.locator('.composer-project-context')).toHaveCSS('border-top-left-radius', '18px');
  });

  test(`${theme} keeps the 390px composer usable when the project sidebar opens and closes`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.addInitScript((value) => localStorage.setItem('cloudra.theme', value), theme);
    await installApiMocks(page, { projects: [], jobs: [] });
    await openSpa(page);
    const input = page.getByTestId('composer-input');
    await input.fill('Keep this narrow-screen draft');
    const initialBox = await input.boundingBox();
    expect(initialBox).not.toBeNull();
    expect(initialBox!.width).toBeGreaterThan(240);
    expect(initialBox!.x + initialBox!.width).toBeLessThanOrEqual(390);
    await page.getByRole('button', { name: '显示侧栏', exact: true }).click();
    await expect(page.getByRole('button', { name: '新聊天', exact: true })).toBeVisible();
    const expandedBox = await input.boundingBox();
    expect(expandedBox!.width).toBeGreaterThan(240);
    await page.getByRole('button', { name: '收起项目侧栏', exact: true }).click();
    await expect(page.getByRole('button', { name: '显示侧栏', exact: true })).toBeVisible();
    await expect(input).toHaveValue('Keep this narrow-screen draft');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
}

test('clock opens scheduled tasks while settings has a single navigation entry', async ({ page }) => {
  await installApiMocks(page, { jobs: [] });
  await page.route(`**/api/v2/projects/${PROJECT_ACTIVE.id}/reminders/pending`, (route) => route.fulfill({ json: [{
    schedule_id: 4, project_id: PROJECT_ACTIVE.id, session_id: AGENT.id,
    message: 'Check reaction results', wake_at: '2026-10-05T00:00:00Z', wake_ts: 1791158400,
    check_command: null, interval_seconds: null,
  }] }));
  await openSpa(page);
  await expect(page.getByRole('button', { name: '设置', exact: true })).toHaveCount(1);
  await expect(page.getByRole('button', { name: '全局设置', exact: true })).toHaveCount(0);
  await expect(page.getByTestId('cancel-all-compute-foot')).toBeHidden();
  await page.getByRole('button', { name: '定时任务', exact: true }).click();
  const panel = page.getByRole('dialog', { name: '定时任务', exact: true });
  await expect(panel.getByText('Check reaction results').first()).toBeVisible();
  await panel.getByRole('button', { name: '返回聊天', exact: true }).click();
  await expect(panel).toHaveCount(0);
  await expect(page.getByRole('button', { name: '新聊天', exact: true })).toBeVisible();
});
