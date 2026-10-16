import { expect, test, type Page } from '@playwright/test';
import { AGENT, PROJECT_ACTIVE, installApiMocks, openSpa } from './fixtures';

type Source = { emit(type: string, event: unknown): void; close(): void };
async function controlledStream(page: Page) {
  await page.addInitScript(() => {
    class Source {
      closed = false;
      handlers = new Map<string, ((event: { data: string }) => void)[]>();
      constructor() { (window as unknown as { pendingSources: Source[] }).pendingSources.push(this); }
      addEventListener(type: string, handler: (event: { data: string }) => void) {
        this.handlers.set(type, [...(this.handlers.get(type) ?? []), handler]);
      }
      close() { this.closed = true; }
      emit(type: string, event: unknown) {
        if (!this.closed) for (const handler of this.handlers.get(type) ?? []) handler({ data: JSON.stringify(event) });
      }
    }
    (window as unknown as { pendingSources: Source[] }).pendingSources = [];
    window.EventSource = Source as unknown as typeof EventSource;
  });
}
async function selectProject(page: Page) {
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await expect(page.locator('.breadcrumb-agent-name')).toHaveText(AGENT.display_name);
}
async function pendingEvent(page: Page, type: string, seq: number) {
  await page.evaluate(({ type, seq, projectId }) => {
    (window as unknown as { pendingSources: Source[] }).pendingSources.at(-1)!.emit(type, {
      type, seq, project_id: projectId, data: {},
    });
  }, { type, seq, projectId: PROJECT_ACTIVE.id });
}
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: 'ignoreErrors' }); });

test('active project and attention share one pending read per fallback poll', async ({ page }) => {
  await page.clock.install();
  await installApiMocks(page, { projects: [PROJECT_ACTIVE], jobs: [] });
  await controlledStream(page);
  let approvals = 0;
  let interactions = 0;
  await page.route('**/projects/*/approvals', route => { approvals++; return route.fulfill({ json: [] }); });
  await page.route('**/projects/*/interactions', route => { interactions++; return route.fulfill({ json: [] }); });
  await selectProject(page);
  await expect.poll(() => approvals).toBeGreaterThan(0);
  expect(approvals).toBe(1);
  expect(interactions).toBe(1);
  await page.clock.runFor(5_100);
  await expect.poll(() => approvals).toBe(2);
  expect(interactions).toBe(2);
});

test('slow pending reads do not overlap or grow on subsequent polling ticks', async ({ page }) => {
  await page.clock.install();
  await installApiMocks(page, { projects: [PROJECT_ACTIVE], jobs: [] });
  await controlledStream(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let approvals = 0;
  let interactions = 0;
  await page.route('**/projects/*/approvals', async route => { approvals++; await held; await route.fulfill({ json: [] }); });
  await page.route('**/projects/*/interactions', async route => { interactions++; await held; await route.fulfill({ json: [] }); });
  await selectProject(page);
  await expect.poll(() => approvals).toBeGreaterThan(0);
  await page.clock.runFor(21_000);
  expect(approvals).toBe(1);
  expect(interactions).toBe(1);
  release();
});

test('SSE during pending HTTP drops the stale result and refreshes once afterward', async ({ page }) => {
  await installApiMocks(page, { projects: [PROJECT_ACTIVE], jobs: [] });
  await controlledStream(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let reads = 0;
  await page.route('**/projects/*/interactions', async route => {
    reads++;
    if (reads === 1) { await held; await route.fulfill({ json: [] }); }
    else await route.fulfill({ json: [{ interaction_id: 'new', session_id: AGENT.id, prompt: 'NEW QUESTION' }] });
  });
  await selectProject(page);
  await expect.poll(() => page.evaluate(() => (window as unknown as { pendingSources: Source[] }).pendingSources.length)).toBeGreaterThan(0);
  await pendingEvent(page, 'interaction.requested', 1);
  await pendingEvent(page, 'interaction.requested', 2);
  expect(reads).toBe(1);
  release();
  await expect(page.getByTestId('interaction-prompt-window')).toContainText('NEW QUESTION');
  expect(reads).toBe(2);
});


test('many projects use a bounded batch instead of starting every pending request together', async ({ page }) => {
  const projects = [PROJECT_ACTIVE, ...Array.from({ length: 7 }, (_, index) => ({
    ...PROJECT_ACTIVE, id: `project-${index}`, name: `Project ${index}`,
  }))];
  await installApiMocks(page, { projects, jobs: [] });
  await controlledStream(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let started = 0;
  let running = 0;
  let maximum = 0;
  await page.route('**/projects/*/approvals', async route => {
    started++; running++; maximum = Math.max(maximum, running);
    await held;
    await route.fulfill({ json: [] });
    running--;
  });
  await selectProject(page);
  await expect.poll(() => started).toBe(3);
  expect(maximum).toBe(3);
  release();
  await expect.poll(() => started).toBe(8);
  expect(maximum).toBeLessThanOrEqual(3);
});

test('a completed question in another project cannot return from an older fallback response', async ({ page }) => {
  await page.clock.install();
  const other = { ...PROJECT_ACTIVE, id: 'other-project', name: 'Other pending project' };
  await installApiMocks(page, { projects: [PROJECT_ACTIVE, other], jobs: [] });
  await controlledStream(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let reads = 0;
  let accepted = false;
  let started = false;
  await page.route(`**/projects/${other.id}/interactions`, async route => {
    reads++;
    const snapshot = accepted ? [] : [{ interaction_id: 'other-one', session_id: 'other-agent', prompt: 'OTHER QUESTION' }];
    if (reads === 2) { started = true; await held; }
    await route.fulfill({ json: snapshot });
  });
  await page.route(`**/projects/${other.id}/interactions/*/response`, route => {
    accepted = true;
    return route.fulfill({ json: { ok: true } });
  });
  await selectProject(page);
  const card = page.locator('.attention-card.interaction').filter({ hasText: 'OTHER QUESTION' });
  await expect(card).toBeVisible();
  await page.clock.runFor(5_100);
  await expect.poll(() => started).toBe(true);
  await card.getByRole('textbox').fill('resolved');
  await card.getByRole('textbox').press('Enter');
  await expect(card).toBeHidden();
  release();
  await expect.poll(() => reads).toBe(3);
  await expect(card).toBeHidden();
});

test('a late pending response belongs to its project after selection changes', async ({ page }) => {
  const other = { ...PROJECT_ACTIVE, id: 'other-project', name: 'Other selected project' };
  await installApiMocks(page, { projects: [PROJECT_ACTIVE, other], jobs: [] });
  await controlledStream(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let started = false;
  await page.route(`**/projects/${PROJECT_ACTIVE.id}/interactions`, async route => {
    started = true; await held;
    await route.fulfill({ json: [{ interaction_id: 'old', session_id: AGENT.id, prompt: 'OLD PROJECT QUESTION' }] });
  });
  await page.route(`**/projects/${other.id}/interactions`, route => route.fulfill({
    json: [{ interaction_id: 'current', session_id: AGENT.id, prompt: 'CURRENT PROJECT QUESTION' }],
  }));
  await selectProject(page);
  await expect.poll(() => started).toBe(true);
  await page.getByTitle(`选择项目: ${other.name}`, { exact: true }).click();
  const prompt = page.getByTestId('interaction-prompt-window');
  await expect(prompt).toContainText('CURRENT PROJECT QUESTION');
  const received = page.waitForResponse(response => response.url().endsWith(`/projects/${PROJECT_ACTIVE.id}/interactions`));
  release();
  await received;
  await expect(prompt).toContainText('CURRENT PROJECT QUESTION');
  await expect(prompt).not.toContainText('OLD PROJECT QUESTION');
});

test('archiving a project removes its shared pending state', async ({ page }) => {
  await installApiMocks(page, { projects: [PROJECT_ACTIVE], jobs: [], interactions: [
    { interaction_id: 'archived', session_id: AGENT.id, prompt: 'ARCHIVED QUESTION' },
  ] });
  await controlledStream(page);
  await selectProject(page);
  await expect(page.getByTestId('interaction-prompt-window')).toContainText('ARCHIVED QUESTION');
  page.once('dialog', dialog => dialog.accept());
  await page.getByTitle(`归档 "${PROJECT_ACTIVE.name}"`, { exact: true }).click();
  await expect(page.getByTestId('interaction-prompt-window')).toBeHidden();
  await expect(page.locator('.attention-card').filter({ hasText: 'ARCHIVED QUESTION' })).toHaveCount(0);
});
