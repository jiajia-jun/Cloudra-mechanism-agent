import { expect, test, type Page } from '@playwright/test';
import { AGENT, PROJECT_ACTIVE, installApiMocks, openSpa } from './fixtures';

const WORKER = { ...AGENT, id: 'agent_worker', display_name: 'Worker', role_id: 'small_mol' };
function event(seq: number, content: string, agentId = AGENT.id, type = 'agent.message_emitted') {
  return { event_id: `event-${seq}`, type, stream: 'agent', project_id: PROJECT_ACTIVE.id,
    session_id: agentId, seq, session_seq: seq, created_at: '2026-10-17T00:00:00Z',
    data: { content, sender: type === 'agent.message_injected' ? 'user' : 'agent' } };
}

type Source = { url: string; closed: boolean; emit(type: string, data: unknown): void; fail(): void };
async function setup(page: Page, agents = [AGENT]) {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));
  await installApiMocks(page, { agents, jobs: [] });
  await page.route('**/api/v2/projects/*/view', (route) => route.fulfill({ json: { agents, cursor: 100 } }));
  await page.route('**/api/v2/projects/*/hub/posts', (route) => route.fulfill({ json: { posts: [] } }));
  await page.addInitScript(() => {
    class ControlledSource {
      url: string;
      closed = false;
      onopen?: () => void;
      onerror?: () => void;
      handlers = new Map<string, ((message: { data: string }) => void)[]>();
      constructor(url: string) {
        this.url = url;
        (window as unknown as { sources: ControlledSource[] }).sources.push(this);
      }
      addEventListener(type: string, handler: (message: { data: string }) => void) {
        this.handlers.set(type, [...(this.handlers.get(type) ?? []), handler]);
      }
      close() { this.closed = true; }
      fail() { this.onerror?.(); }
      emit(type: string, envelope: unknown) {
        if (this.closed) return;
        this.onopen?.();
        for (const handler of this.handlers.get(type) ?? []) handler({ data: JSON.stringify(envelope) });
      }
    }
    (window as unknown as { sources: ControlledSource[] }).sources = [];
    window.EventSource = ControlledSource as unknown as typeof EventSource;
  });
  return requests;
}
async function emit(page: Page, entry: { type: string; [key: string]: unknown }) {
  await page.evaluate((entry) => {
    (window as unknown as { sources: Source[] }).sources.at(-1)!.emit(entry.type, entry);
  }, entry);
}
async function synced(page: Page, through = 100) {
  await expect.poll(() => page.evaluate(() => (window as unknown as { sources: Source[] }).sources.length)).toBeGreaterThan(0);
  await page.evaluate((through) => {
    (window as unknown as { sources: Source[] }).sources.at(-1)!.emit('project.synced', {
      type: 'project.synced', seq: 0, data: { replayed_through: through },
    });
  }, through);
}
async function openProject(page: Page) {
  await openSpa(page);
  await page.getByText(PROJECT_ACTIVE.name, { exact: true }).click();
}
const bubble = (page: Page, text: string) => page.locator('.msg-body, .msg-bubble').filter({ hasText: text });

test('tail loading merges a concurrent live message instead of overwriting it', async ({ page }) => {
  await setup(page);
  let release: (() => void) | undefined;
  await page.route('**/api/v2/agents/*/events?**', async (route) => {
    await new Promise<void>((resolve) => { release = resolve; });
    await route.fulfill({ json: [event(90, 'tail before stream')] });
  });
  await openProject(page);
  await expect.poll(() => Boolean(release)).toBe(true);
  await synced(page);
  await emit(page, event(101, 'live during tail'));
  await emit(page, { ...event(102, ''), type: 'agent.state_changed', data: { to: 'running' } });
  await expect(bubble(page, 'live during tail')).toHaveCount(1);
  release!();
  await expect(bubble(page, 'tail before stream')).toHaveCount(1);
  await expect(bubble(page, 'live during tail')).toHaveCount(1);
  await expect(page.locator('.breadcrumb-agent .state-dot.running')).toHaveCount(1);
});

test('switching agents ignores a stale tail while retaining the selected live message', async ({ page }) => {
  await setup(page, [AGENT, WORKER]);
  let release: (() => void) | undefined;
  await page.route('**/api/v2/agents/*/events?**', async (route) => {
    const isWorker = route.request().url().includes(WORKER.id);
    if (!isWorker) await new Promise<void>((resolve) => { release = resolve; });
    await route.fulfill({ json: [event(isWorker ? 110 : 90, isWorker ? 'worker tail' : 'stale coordinator', isWorker ? WORKER.id : AGENT.id)] });
  });
  await openProject(page);
  await expect.poll(() => Boolean(release)).toBe(true);
  await synced(page);
  await page.locator('select').filter({ has: page.locator(`option[value="${WORKER.id}"]`) }).selectOption(WORKER.id);
  await expect(bubble(page, 'worker tail')).toHaveCount(1);
  await emit(page, event(111, 'worker live', WORKER.id));
  release!();
  await expect(bubble(page, 'worker live')).toHaveCount(1);
  await expect(bubble(page, 'stale coordinator')).toHaveCount(0);
});

test('reconnect resumes after the synced watermark and refreshes the bounded tail', async ({ page }) => {
  await setup(page);
  let entries = [event(90, 'initial tail')];
  let reads = 0;
  await page.route('**/api/v2/agents/*/events?**', (route) => { reads++; return route.fulfill({ json: entries }); });
  await openProject(page);
  await expect(bubble(page, 'initial tail')).toHaveCount(1);
  await synced(page, 140);
  const beforeReconnect = reads;
  entries = [...entries, event(141, 'message during disconnect')];
  await page.evaluate(() => (window as unknown as { sources: Source[] }).sources.at(-1)!.fail());
  await expect.poll(() => page.evaluate(() => (window as unknown as { sources: Source[] }).sources.length)).toBe(2);
  const url = await page.evaluate(() => (window as unknown as { sources: Source[] }).sources.at(-1)!.url);
  expect(new URL(url, 'http://127.0.0.1:5173').searchParams.get('cursor')).toBe('140');
  await synced(page, 141);
  await expect.poll(() => reads).toBeGreaterThan(beforeReconnect);
  await expect(bubble(page, 'message during disconnect')).toHaveCount(1);
  await emit(page, event(141, 'message during disconnect'));
  await expect(bubble(page, 'message during disconnect')).toHaveCount(1);
});

test('HTTP receipt confirms the exact sent message without an SSE echo', async ({ page }) => {
  await setup(page);
  const sent = event(101, 'accepted without stream', AGENT.id, 'agent.message_injected');
  await page.route('**/api/v2/agents/*/events/event-101', (route) => route.fulfill({ json: sent }));
  await page.route('**/api/v2/agents/*/messages', (route) => route.fulfill({ json: {
    accepted: true, command_id: 'message-command', event_id: sent.event_id, data: AGENT,
  } }));
  await openProject(page);
  await synced(page);
  await page.getByTestId('composer-input').fill(sent.data.content);
  await page.getByTestId('composer-input').press('Enter');
  await expect(page.locator('.msg-sender').filter({ hasText: 'sending…' })).toHaveCount(0);
  await expect(bubble(page, sent.data.content)).toHaveCount(1);
  await emit(page, sent);
  await expect(bubble(page, sent.data.content)).toHaveCount(1);
});

test('old identical replay cannot acknowledge a new send and an SSE-first receipt stays unique', async ({ page }) => {
  await setup(page);
  let release: (() => void) | undefined;
  const sent = event(102, 'same text', AGENT.id, 'agent.message_injected');
  await page.route('**/api/v2/agents/*/events/event-102', (route) => route.fulfill({ json: sent }));
  await page.route('**/api/v2/agents/*/messages', async (route) => {
    await new Promise<void>((resolve) => { release = resolve; });
    await route.fulfill({ json: { accepted: true, command_id: 'same-command', event_id: sent.event_id, data: AGENT } });
  });
  await openProject(page);
  await synced(page);
  await page.getByTestId('composer-input').fill('same text');
  await page.getByTestId('composer-input').press('Enter');
  await expect.poll(() => Boolean(release)).toBe(true);
  await emit(page, event(90, 'same text', AGENT.id, 'agent.message_injected'));
  await expect(page.locator('.msg-sender').filter({ hasText: 'sending…' })).toHaveCount(1);
  await emit(page, sent);
  release!();
  await expect(page.locator('.msg-sender').filter({ hasText: 'sending…' })).toHaveCount(0);
  await expect(bubble(page, 'same text')).toHaveCount(2);
});

test('an empty forum starts after the project view cursor', async ({ page }) => {
  await setup(page);
  await openProject(page);
  await synced(page);
  await page.getByRole('button', { name: '控制台', exact: true }).click();
  await page.getByRole('button', { name: '协同论坛', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { sources: Source[] }).sources.length)).toBe(2);
  const urls = await page.evaluate(() => (window as unknown as { sources: Source[] }).sources.map((source) => source.url));
  expect(urls.map((url) => new URL(url, 'http://127.0.0.1:5173').searchParams.get('cursor'))).toEqual(['100', '100']);
});

test('startup uses one project snapshot and only a bounded tail before incremental streaming', async ({ page }) => {
  const requests = await setup(page);
  await openProject(page);
  await synced(page);
  const urls = requests.map((url) => new URL(url));
  expect(urls.filter((url) => url.pathname.endsWith('/view'))).toHaveLength(1);
  expect(urls.filter((url) => url.pathname.endsWith('/agents'))).toHaveLength(0);
  const eventPages = urls.filter((url) => url.pathname.endsWith('/events'));
  expect(eventPages).toHaveLength(1);
  expect(eventPages[0].searchParams.get('tail')).toBe('true');
  expect(eventPages[0].searchParams.get('limit')).toBe('500');
  const stream = await page.evaluate(() => (window as unknown as { sources: Source[] }).sources[0].url);
  expect(new URL(stream, 'http://127.0.0.1:5173').searchParams.get('cursor')).toBe('100');
});

test('a failed identical send removes only its own pending bubble', async ({ page }) => {
  await setup(page);
  const previous = event(101, 'identical request', AGENT.id, 'agent.message_injected');
  let sends = 0;
  let reject: (() => void) | undefined;
  await page.route('**/api/v2/agents/*/events/event-101', (route) => route.fulfill({ json: previous }));
  await page.route('**/api/v2/agents/*/messages', async (route) => {
    if (++sends === 1) return route.fulfill({ json: {
      accepted: true, command_id: 'previous-command', event_id: previous.event_id, data: AGENT,
    } });
    await new Promise<void>((resolve) => { reject = resolve; });
    await route.fulfill({ status: 503, json: { detail: 'Message unavailable' } });
  });
  await openProject(page);
  await synced(page);
  const composer = page.getByTestId('composer-input');
  await composer.fill('identical request');
  await composer.press('Enter');
  await expect(bubble(page, 'identical request')).toHaveCount(1);
  await composer.fill('identical request');
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeEnabled();
  await composer.press('Enter');
  await expect.poll(() => Boolean(reject)).toBe(true);
  await expect(bubble(page, 'identical request')).toHaveCount(2);
  reject!();
  await expect(page.locator('.msg-sender').filter({ hasText: 'sending…' })).toHaveCount(0);
  await expect(bubble(page, 'identical request')).toHaveCount(1);
});

test('replayed transitions after the frozen project view update the visible agent', async ({ page }) => {
  await setup(page);
  await openProject(page);
  await expect.poll(() => page.evaluate(() => (window as unknown as { sources: Source[] }).sources.length)).toBe(1);
  await emit(page, { ...event(101, ''), type: 'agent.task_updated',
    data: { ...event(101, '').data, current_task: 'replayed current task' } });
  await emit(page, { ...event(102, ''), type: 'agent.state_changed',
    data: { ...event(102, '').data, to: 'running' } });
  await synced(page, 102);
  await expect(page.getByText('replayed current task', { exact: true })).toBeVisible();
  await expect(page.locator('.breadcrumb-agent .state-dot.running')).toHaveCount(1);
});

test('forum reconnect carries persisted events and synced watermarks without refreshing its page', async ({ page }) => {
  await setup(page);
  await openProject(page);
  await synced(page);
  await page.getByRole('button', { name: '控制台', exact: true }).click();
  await page.getByRole('button', { name: '协同论坛', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { sources: Source[] }).sources.length)).toBe(2);
  await emit(page, event(190, 'unrelated agent event'));
  await page.evaluate(() => (window as unknown as { sources: Source[] }).sources.at(-1)!.fail());
  await expect.poll(() => page.evaluate(() => (window as unknown as { sources: Source[] }).sources.length)).toBe(3);
  let url = await page.evaluate(() => (window as unknown as { sources: Source[] }).sources.at(-1)!.url);
  expect(new URL(url, 'http://127.0.0.1:5173').searchParams.get('cursor')).toBe('190');
  await synced(page, 220);
  await page.evaluate(() => (window as unknown as { sources: Source[] }).sources.at(-1)!.fail());
  await expect.poll(() => page.evaluate(() => (window as unknown as { sources: Source[] }).sources.length)).toBe(4);
  url = await page.evaluate(() => (window as unknown as { sources: Source[] }).sources.at(-1)!.url);
  expect(new URL(url, 'http://127.0.0.1:5173').searchParams.get('cursor')).toBe('220');
  await expect(page.getByRole('button', { name: /new posts/ })).toHaveCount(0);
});

test('a spawned agent receives subsequent task and run transitions before sync completes', async ({ page }) => {
  const requests = await setup(page);
  await page.route(`**/api/v2/agents/${WORKER.id}`, (route) => route.fulfill({ json: WORKER }));
  await openProject(page);
  await expect.poll(() => page.evaluate(() => (window as unknown as { sources: Source[] }).sources.length)).toBe(1);
  await page.evaluate(({ worker, projectId }) => {
    const source = (window as unknown as { sources: Source[] }).sources[0];
    const base = { project_id: projectId, session_id: worker.id, created_at: '2026-10-17T00:00:00Z' };
    for (const entry of [
      { ...base, event_id: 'spawn-worker', seq: 101, type: 'agent.spawned', data: worker },
      { ...base, event_id: 'worker-task', seq: 102, type: 'agent.task_updated', data: { current_task: 'new worker task' } },
      { ...base, event_id: 'worker-state', seq: 103, type: 'agent.state_changed', data: { to: 'running' } },
      { ...base, event_id: 'worker-run', seq: 104, type: 'run.started', data: { run_id: 'new-worker-run' } },
    ]) source.emit(entry.type, entry);
  }, { worker: WORKER, projectId: PROJECT_ACTIVE.id });
  await synced(page, 104);
  await expect(page.locator(`.breadcrumb-agent-select option[value="${WORKER.id}"]`)).toHaveCount(1);
  await page.locator('.breadcrumb-agent-select').selectOption(WORKER.id);
  await expect(page.getByText('new worker task', { exact: true })).toBeVisible();
  await expect(page.locator('.breadcrumb-agent-wrap .state-dot.running')).toHaveCount(1);
  expect(requests.filter((url) => new URL(url).pathname.endsWith('/agents'))).toHaveLength(0);
});

for (const origin of ['initial details', 'finished run'] as const) {
  test(`late ${origin} cannot restore completion A over newer completion B`, async ({ page }) => {
    await setup(page);
    let release: (() => void) | undefined;
    let reads = 0;
    const summary = (runId: string, label: string) => ({ run_id: runId, run_outcome: 'succeeded',
      completion_basis: label, verification_label: label });
    await page.route(`**/api/v2/agents/${AGENT.id}`, async (route) => {
      const held = ++reads === (origin === 'initial details' ? 1 : 2);
      if (held) await new Promise<void>((resolve) => { release = resolve; });
      return route.fulfill({ json: { ...AGENT, current_run: null,
        completion: held ? summary('run-a', 'verified') : summary('run-b', 'partial') } });
    });
    await openProject(page);
    await synced(page);
    if (origin === 'finished run') await emit(page, {
      ...event(101, ''), type: 'run.finished', run_id: 'run-a', data: { run_id: 'run-a' },
    });
    await expect.poll(() => Boolean(release)).toBe(true);
    await emit(page, { ...event(102, ''), type: 'run.started', run_id: 'run-b', data: { run_id: 'run-b' } });
    await emit(page, { ...event(103, ''), type: 'run.finished', run_id: 'run-b', data: { run_id: 'run-b' } });
    await expect(page.locator('.completion-badge')).toHaveText('partial delivery');
    const response = page.waitForResponse((response) => response.url().endsWith(`/agents/${AGENT.id}`));
    release!();
    await response;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.locator('.completion-badge')).toHaveText('partial delivery');
  });
}

test('a slow failing detail read does not keep an accepted send in flight', async ({ page }) => {
  await setup(page);
  let release: (() => void) | undefined;
  await page.route('**/api/v2/agents/*/messages', (route) => route.fulfill({ json: {
    accepted: true, command_id: 'accepted-command', event_id: 'event-101', data: AGENT,
  } }));
  await page.route('**/api/v2/agents/*/events/event-101', async (route) => {
    await new Promise<void>((resolve) => { release = resolve; });
    await route.fulfill({ status: 503, json: { detail: 'Event details temporarily unavailable' } });
  });
  await openProject(page);
  await synced(page);
  const composer = page.getByTestId('composer-input');
  await composer.fill('accepted request');
  await composer.press('Enter');
  await expect.poll(() => Boolean(release)).toBe(true);
  await composer.fill('next request');
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeEnabled();
  release!();
  await expect(page.locator('.msg-sender').filter({ hasText: 'sending…' })).toHaveCount(0);
  await expect(composer).toHaveValue('next request');
});

test('a successful spawn selects its fetched agent even when the stream echo is delayed', async ({ page }) => {
  await setup(page, []);
  await page.route('**/api/v2/projects/*/agents', (route) => route.fulfill({ json: {
    accepted: true, command_id: 'spawn-command', event_id: 'spawn-event', data: AGENT,
  } }));
  await openProject(page);
  await synced(page);
  await page.getByTestId('composer-input').fill('start the project');
  await page.getByTestId('composer-input').press('Enter');
  await expect(page.locator('.breadcrumb-agent-name')).toHaveText(AGENT.display_name);
});
