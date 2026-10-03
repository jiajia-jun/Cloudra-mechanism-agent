import { expect, test, type Page } from '@playwright/test';
import { AGENT, PROJECT_ACTIVE, installApiMocks, openSpa } from './fixtures';

const question = (id: string) => ({ interaction_id: id, session_id: AGENT.id, prompt: `Question ${id}` });
async function selectLive(page: Page) {
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await expect(page.getByTestId('interaction-prompt-window')).toBeVisible();
}
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: 'ignoreErrors' }); });

for (const collapsed of [false, true]) {
  test(`failed response preserves ${collapsed ? 'composer' : 'card'} draft`, async ({ page }) => {
    await installApiMocks(page, { interactions: [question('one')], jobs: [] });
    await page.route('**/interactions/*/response', route => route.fulfill({ status: 503, json: { detail: 'temporarily unavailable' } }));
    await selectLive(page);
    const card = page.getByTestId('interaction-prompt-window');
    if (collapsed) await card.getByRole('button', { name: '收起 ↓' }).click();
    const box = collapsed ? page.getByTestId('composer-input') : card.getByRole('textbox');
    await box.fill('preserve my response');
    await box.press('Enter');
    await expect(page.getByText('temporarily unavailable', { exact: false }).first()).toBeVisible();
    await expect(box).toHaveValue('preserve my response');
  });
}

test('changing pending question clears previous answer draft', async ({ page }) => {
  await installApiMocks(page, { interactions: [question('one'), question('two')], jobs: [] });
  await selectLive(page);
  const card = page.getByTestId('interaction-prompt-window');
  await card.getByRole('textbox').fill('only for question one');
  await card.getByTitle('Next', { exact: true }).click();
  await expect(card).toContainText('Question two');
  await expect(card.getByRole('textbox')).toHaveValue('');
});

test('accepted response is removed even if refresh fails', async ({ page }) => {
  await installApiMocks(page, { interactions: [question('one')], jobs: [] });
  let accepted = false;
  let posts = 0;
  await page.route('**/projects/*/interactions', route => route.fulfill(accepted
    ? { status: 503, json: { detail: 'refresh unavailable' } }
    : { json: [question('one')] }));
  await page.route('**/interactions/*/response', route => { accepted = true; posts++; return route.fulfill({ json: { ok: true } }); });
  await selectLive(page);
  await page.getByTestId('interaction-prompt-window').getByRole('textbox').fill('accepted response');
  await page.getByTestId('interaction-prompt-window').getByRole('textbox').press('Enter');
  await expect(page.getByTestId('interaction-prompt-window')).toBeHidden();
  await expect(page.getByText('refresh unavailable', { exact: false })).toHaveCount(0);
  expect(posts).toBe(1);
});

test('late agent details cannot replace the newer selected agent transcript', async ({ page }) => {
  const second = { ...AGENT, id: 'agent_second', display_name: 'Second Coordinator' };
  await installApiMocks(page, { agents: [AGENT, second], jobs: [] });
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let started = false;
  await page.route(`**/agents/${AGENT.id}/events**`, async route => {
    started = true; await held;
    await route.fulfill({ json: [{ event_id: 'old', seq: 1, session_seq: 1, type: 'agent.message_injected', session_id: AGENT.id, data: { content: 'STALE TRANSCRIPT', role: 'user' } }] });
  });
  await page.route(`**/agents/${second.id}`, route => route.fulfill({ json: second }));
  await page.route(`**/agents/${second.id}/events**`, route => route.fulfill({ json: [{ event_id: 'new', seq: 2, session_seq: 2, type: 'agent.message_injected', session_id: second.id, data: { content: 'CURRENT TRANSCRIPT', role: 'user' } }] }));
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await expect.poll(() => started).toBe(true);
  await page.locator('.breadcrumb-agent-select').selectOption(second.id);
  await expect(page.getByTestId('composer-input')).toBeVisible();
  await expect(page.getByText('CURRENT TRANSCRIPT', { exact: true })).toBeVisible();
  const response = page.waitForResponse(r => r.url().includes(`/agents/${AGENT.id}/events`));
  release();
  await response;
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.getByText('CURRENT TRANSCRIPT', { exact: true })).toBeVisible();
});

test('late project agent list cannot replace the selected project', async ({ page }) => {
  const other = { ...PROJECT_ACTIVE, id: 'proj_other', name: 'Other project' };
  const otherAgent = { ...AGENT, id: 'agent_other', project_id: other.id, display_name: 'Other coordinator' };
  await installApiMocks(page, { projects: [PROJECT_ACTIVE, other], jobs: [] });
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let started = false;
  await page.route(`**/projects/${PROJECT_ACTIVE.id}/agents`, async route => { started = true; await held; await route.fulfill({ json: [AGENT] }); });
  await page.route(`**/projects/${other.id}/agents`, route => route.fulfill({ json: [otherAgent] }));
  await page.route(`**/agents/${otherAgent.id}`, route => route.fulfill({ json: otherAgent }));
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await expect.poll(() => started).toBe(true);
  await page.getByTitle(`选择项目: ${other.name}`, { exact: true }).click();
  await expect(page.locator('.breadcrumb-agent-name')).toHaveText(otherAgent.display_name);
  const response = page.waitForResponse(r => r.url().endsWith(`/projects/${PROJECT_ACTIVE.id}/agents`));
  release();
  await response;
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.locator('.breadcrumb-agent-name')).toHaveText(otherAgent.display_name);
});

test('repeated submit while a response is pending sends once', async ({ page }) => {
  await installApiMocks(page, { interactions: [question('one')], jobs: [] });
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let posts = 0;
  await page.route('**/interactions/*/response', async route => { posts++; await held; await route.fulfill({ status: 503, json: { detail: 'retry later' } }); });
  await selectLive(page);
  const box = page.getByTestId('interaction-prompt-window').getByRole('textbox');
  await box.fill('one response');
  await box.press('Enter');
  await expect.poll(() => posts).toBe(1);
  await expect(box).toBeDisabled();
  await box.dispatchEvent('keydown', { key: 'Enter' });
  release();
  await expect(box).toBeEnabled();
  await expect(box).toHaveValue('one response');
  expect(posts).toBe(1);
});

test('successful response preserves newer composer draft', async ({ page }) => {
  await installApiMocks(page, { interactions: [question('one')], jobs: [] });
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let posted = false;
  await page.route('**/interactions/*/response', async route => { posted = true; await held; await route.fulfill({ json: { ok: true } }); });
  await selectLive(page);
  await page.getByTestId('interaction-prompt-window').getByRole('button', { name: '收起 ↓' }).click();
  const box = page.getByTestId('composer-input');
  await box.fill('old response');
  await box.press('Enter');
  await expect.poll(() => posted).toBe(true);
  await box.fill('new draft');
  const response = page.waitForResponse(r => r.url().endsWith('/response'));
  release();
  await response;
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeEnabled();
  await expect(box).toHaveValue('new draft');
});

test('late refresh cannot restore a subsequently completed question', async ({ page }) => {
  await installApiMocks(page, { interactions: [question('one'), question('two')], jobs: [] });
  let count = 0;
  let refreshStarted = false;
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/projects/*/interactions', async route => {
    const snapshot = count;
    if (snapshot === 1) { refreshStarted = true; await held; }
    await route.fulfill({ json: snapshot === 0 ? [question('one'), question('two')] : snapshot === 1 ? [question('two')] : [] });
  });
  await page.route('**/interactions/*/response', route => { count++; return route.fulfill({ json: { ok: true } }); });
  await selectLive(page);
  const card = page.getByTestId('interaction-prompt-window');
  await card.getByRole('textbox').fill('first answer');
  await card.getByRole('textbox').press('Enter');
  await expect.poll(() => refreshStarted).toBe(true);
  await expect(card).toContainText('Question two');
  await card.getByRole('textbox').fill('second answer');
  await card.getByRole('textbox').press('Enter');
  await expect(card).toBeHidden();
  const response = page.waitForResponse(r => r.url().endsWith('/interactions'));
  release();
  await response;
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(card).toBeHidden();
  expect(count).toBe(2);
});
