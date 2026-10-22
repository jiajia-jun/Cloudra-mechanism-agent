import { expect, test, type Page } from '@playwright/test';
import { AGENT, PROJECT_ACTIVE, installApiMocks, openSpa } from './fixtures';

function event(seq: number, content = `memory-message-${seq}`) {
  return {
    event_id: `memory-event-${seq}`, type: 'agent.message_emitted', stream: 'agent',
    project_id: PROJECT_ACTIVE.id, session_id: AGENT.id, seq, session_seq: seq,
    created_at: '2026-10-09T00:00:00Z', data: { content },
  };
}

async function history(page: Page, events: ReturnType<typeof event>[]) {
  await installApiMocks(page, { jobs: [] });
  const requests: string[] = [];
  await page.route('**/api/v2/agents/*/events**', async (route) => {
    const url = new URL(route.request().url());
    requests.push(url.pathname + url.search);
    if (url.pathname.includes('/events/')) {
      const entry = events.find((event) => event.event_id === url.pathname.split('/').at(-1));
      return route.fulfill({ json: entry });
    }
    const after = Number(url.searchParams.get('after') ?? 0);
    const before = Number(url.searchParams.get('before') ?? Infinity);
    const limit = Number(url.searchParams.get('limit') ?? 500);
    const matched = events.filter((event) => event.session_seq > after && event.session_seq < before);
    const selected = url.searchParams.get('tail') === 'false' ? matched.slice(0, limit) : matched.slice(-limit);
    await route.fulfill({ json: selected });
  });
  return requests;
}

async function controlledStreams(page: Page) {
  await page.addInitScript(() => {
    class Source {
      handlers = new Map<string, ((event: { data: string }) => void)[]>();
      closed = false;
      constructor() {
        (window as unknown as { memorySources: Source[] }).memorySources.push(this);
      }
      addEventListener(type: string, handler: (event: { data: string }) => void) {
        this.handlers.set(type, [...(this.handlers.get(type) ?? []), handler]);
      }
      close() { this.closed = true; }
      emit(type: string, envelope: unknown) {
        if (this.closed) return;
        for (const handler of this.handlers.get(type) ?? []) handler({ data: JSON.stringify(envelope) });
      }
    }
    (window as unknown as { memorySources: Source[] }).memorySources = [];
    window.EventSource = Source as unknown as typeof EventSource;
  });
}

test('chat replaces bounded history pages and can return through newer pages to latest', async ({ page }, testInfo) => {
  const requests = await history(page, Array.from({ length: 1500 }, (_, index) => event(index + 1)));
  await openSpa(page);
  await page.getByText(PROJECT_ACTIVE.name, { exact: true }).click();
  await expect(page.locator('.msg-body').filter({ hasText: 'memory-message-1500' })).toBeVisible();
  await page.getByRole('button', { name: 'Load earlier', exact: true }).click();
  await expect(page.locator('.msg-body').filter({ hasText: 'memory-message-1000' })).toBeVisible();
  await expect(page.locator('.msg')).toHaveCount(500);
  await expect(page.locator('.msg-body').filter({ hasText: 'memory-message-1500' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Load earlier', exact: true }).click();
  await expect(page.locator('.msg-body').filter({ hasText: 'memory-message-500' })).toBeVisible();
  await expect(page.locator('.msg')).toHaveCount(500);
  await page.getByRole('button', { name: 'Newer', exact: true }).click();
  await expect(page.locator('.msg-body').filter({ hasText: 'memory-message-1000' })).toBeVisible();
  await expect(page.locator('.msg')).toHaveCount(500);
  await page.getByRole('button', { name: 'Latest', exact: true }).click();
  await expect(page.locator('.msg-body').filter({ hasText: 'memory-message-1500' })).toBeVisible();
  await expect(page.locator('.msg')).toHaveCount(500);
  expect(requests.some((url) => url.includes('after=500') && url.includes('tail=false'))).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('cloudra-memory-chat.png') });
});

test('audit navigation replaces pages and loads oversized payload only on request', async ({ page }, testInfo) => {
  const events = Array.from({ length: 650 }, (_, index) => event(index + 1));
  events[649] = event(650, 'FULL-EVIDENCE-MARKER ' + 'x'.repeat(100000));
  const requests = await history(page, events);
  await openSpa(page);
  await page.getByText(PROJECT_ACTIVE.name, { exact: true }).click();
  await page.getByRole('button', { name: 'Large event contents are available in the audit log' }).click();
  await page.getByRole('button', { name: 'System events' }).click();
  await expect(page.locator('.audit-card')).toHaveCount(200);
  const card = page.locator('.audit-card').filter({ hasText: '#650' });
  await card.locator('summary').click();
  await expect(card.getByRole('button', { name: 'Load full event payload' })).toBeVisible();
  expect(requests.some((url) => url.endsWith('/events/memory-event-650'))).toBe(false);
  await card.getByRole('button', { name: 'Load full event payload' }).click();
  await expect(card.locator('.af-text').filter({ hasText: 'FULL-EVIDENCE-MARKER' })).toHaveCount(1);
  await card.locator('summary').click();
  await expect(card.locator('.af-text').filter({ hasText: 'FULL-EVIDENCE-MARKER' })).toHaveCount(0);
  await page.getByRole('button', { name: 'older ›' }).click();
  await expect(page.locator('.audit-page-info')).toContainText('#251–450');
  await expect(page.locator('.audit-card')).toHaveCount(200);
  await page.getByRole('button', { name: '‹ newer' }).click();
  await expect(page.locator('.audit-page-info')).toContainText('#451–650');
  await expect(page.locator('.audit-card')).toHaveCount(200);
  await page.getByRole('button', { name: 'latest', exact: true }).click();
  await expect(page.locator('.audit-page-info')).toContainText('latest');
  await page.screenshot({ path: testInfo.outputPath('cloudra-memory-audit.png') });
});

test('forum live posts preserve the browsed page and offer bounded refresh instead of append', async ({ page }) => {
  await controlledStreams(page);
  await installApiMocks(page, { jobs: [] });
  let posts = Array.from({ length: 500 }, (_, index) => ({
    id: `hub-${index + 1}`, seq: index + 1, topic: 'memory-topic', kind: 'finding',
    author_agent: 'user', author_session: null, to_agent: null, parent_id: null,
    created_at: '2026-10-09T00:00:00Z', content: `initial-post-${index + 1}`,
  }));
  await page.route('**/api/v2/projects/*/hub/posts', (route) => route.fulfill({ json: { posts } }));
  await openSpa(page);
  await page.getByText(PROJECT_ACTIVE.name, { exact: true }).click();
  await page.getByRole('button', { name: '控制台', exact: true }).click();
  await page.getByRole('button', { name: '协同论坛', exact: true }).click();
  await page.locator('.hub-topic-name').filter({ hasText: 'memory-topic' }).click();
  await expect(page.locator('.hub-post')).toHaveCount(500);
  await page.evaluate(({ projectId }) => {
    const sources = (window as unknown as { memorySources: { emit(type: string, envelope: unknown): void }[] }).memorySources;
    for (let seq = 501; seq <= 5500; seq++) {
      for (const source of sources) source.emit('hub.posted', {
        event_id: `hub-${seq}`, type: 'hub.posted', project_id: projectId, seq,
        created_at: '2026-10-09T00:00:00Z', data: { topic: 'new-topic', content: 'new post' },
      });
    }
  }, { projectId: PROJECT_ACTIVE.id });
  await expect(page.getByRole('button', { name: '5000 new posts · refresh latest' })).toBeVisible();
  await expect(page.locator('.hub-post')).toHaveCount(500);
  await expect(page.getByText('initial-post-1', { exact: true })).toBeVisible();
  posts = posts.map((post, index) => ({ ...post, id: `hub-${index + 5001}`, seq: index + 5001,
    topic: 'new-topic', content: `latest-post-${index + 5001}` }));
  await page.getByRole('button', { name: '5000 new posts · refresh latest' }).click();
  await page.locator('.hub-topic-name').filter({ hasText: 'new-topic' }).click();
  await expect(page.locator('.hub-post')).toHaveCount(500);
  await expect(page.locator('.hub-post-content').filter({ hasText: 'latest-post-5500' })).toBeVisible();
  await expect(page.getByText('initial-post-1', { exact: true })).toHaveCount(0);
});

test('transient narration stays bounded and explicitly marks omission', async ({ page }) => {
  await controlledStreams(page);
  await history(page, []);
  await openSpa(page);
  await page.getByText(PROJECT_ACTIVE.name, { exact: true }).click();
  await expect(page.getByText('Main Coordinator', { exact: true }).first()).toBeVisible();
  await page.evaluate(({ projectId, agentId }) => {
    const sources = (window as unknown as { memorySources: { emit(type: string, envelope: unknown): void }[] }).memorySources;
    for (let seq = 1; seq <= 300; seq++) {
      for (const source of sources) {
        const base = { event_id: `transient-${seq}`, project_id: projectId, session_id: agentId, seq,
          session_seq: seq, created_at: '2026-10-09T00:00:00Z' };
        source.emit('llm.chunk', { ...base, seq: 0, type: 'llm.chunk', data: { kind: 'content', delta: `narration-${seq} ` + 'n'.repeat(10000) } });
        source.emit('llm.request_started', { ...base, type: 'llm.request_started', data: {} });
      }
    }
  }, { projectId: PROJECT_ACTIVE.id, agentId: AGENT.id });
  await expect(page.getByText('Earlier transient text is omitted from this view. Full persisted events are available in the audit log.')).toBeVisible();
  expect(await page.locator('.msg').count()).toBeLessThanOrEqual(100);
  await expect(page.locator('.msg-body').filter({ hasText: 'narration-300 ' })).toBeVisible();
});

test('chat can retrieve every byte-trimmed event from a short page in both directions', async ({ page }) => {
  await history(page, Array.from({ length: 150 }, (_, index) => event(
    index + 1, `byte-message-${index + 1} ` + 'b'.repeat(30000),
  )));
  await openSpa(page);
  await page.getByText(PROJECT_ACTIVE.name, { exact: true }).click();
  await expect(page.locator('.msg-body').filter({ hasText: 'byte-message-150 ' })).toBeVisible();
  const shown = () => page.locator('.msg-body').evaluateAll((elements) => elements.map(
    (element) => Number(element.textContent!.split(' ')[0].slice('byte-message-'.length)),
  ));
  expect((await shown()).length).toBeLessThan(150);
  const seen = new Set<number>();
  for (let pageIndex = 0; pageIndex < 5; pageIndex++) {
    const current = await shown();
    current.forEach((seq) => seen.add(seq));
    if (current[0] === 1) break;
    const older = page.getByRole('button', { name: 'Load earlier', exact: true });
    await expect(older).toBeEnabled();
    await older.click();
    await expect.poll(async () => (await shown())[0]).toBeLessThan(current[0]);
  }
  expect([...seen].sort((left, right) => left - right)).toEqual(Array.from({ length: 150 }, (_, index) => index + 1));
  const forward = new Set<number>();
  for (let pageIndex = 0; pageIndex < 5; pageIndex++) {
    const current = await shown();
    current.forEach((seq) => forward.add(seq));
    if (current.at(-1) === 150) break;
    const newer = page.getByRole('button', { name: 'Newer', exact: true });
    await expect(newer).toBeEnabled();
    await newer.click();
    await expect.poll(async () => (await shown()).at(-1)!).toBeGreaterThan(current.at(-1)!);
  }
  expect([...forward].sort((left, right) => left - right)).toEqual(Array.from({ length: 150 }, (_, index) => index + 1));
  await page.getByRole('button', { name: 'Latest', exact: true }).click();
  await expect(page.locator('.msg-body').filter({ hasText: 'byte-message-150 ' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Load earlier', exact: true })).toBeEnabled();
});

test('audit can retrieve every byte-trimmed event from a short page in both directions', async ({ page }) => {
  await history(page, Array.from({ length: 150 }, (_, index) => event(
    index + 1, `byte-message-${index + 1} ` + 'b'.repeat(30000),
  )));
  await openSpa(page);
  await page.getByText(PROJECT_ACTIVE.name, { exact: true }).click();
  await page.getByRole('button', { name: '控制台', exact: true }).click();
  await page.getByRole('button', { name: '审计日志', exact: true }).click();
  await page.getByRole('button', { name: 'System events' }).click();
  await expect(page.locator('.audit-page-info')).toContainText('–150');
  const shown = () => page.locator('.audit-card .ac-seq').evaluateAll((elements) => elements.map(
    (element) => Number(element.textContent!.slice(1)),
  ));
  expect((await shown()).length).toBeLessThan(150);
  const seen = new Set<number>();
  for (let pageIndex = 0; pageIndex < 5; pageIndex++) {
    const current = await shown();
    current.forEach((seq) => seen.add(seq));
    if (current[0] === 1) break;
    const older = page.getByRole('button', { name: 'older ›', exact: true });
    await expect(older).toBeEnabled();
    await older.click();
    await expect.poll(async () => (await shown())[0]).toBeLessThan(current[0]);
  }
  expect([...seen].sort((left, right) => left - right)).toEqual(Array.from({ length: 150 }, (_, index) => index + 1));
  const forward = new Set<number>();
  for (let pageIndex = 0; pageIndex < 5; pageIndex++) {
    const current = await shown();
    current.forEach((seq) => forward.add(seq));
    if (current.at(-1) === 150) break;
    const newer = page.getByRole('button', { name: '‹ newer', exact: true });
    await expect(newer).toBeEnabled();
    await newer.click();
    await expect.poll(async () => (await shown()).at(-1)!).toBeGreaterThan(current.at(-1)!);
  }
  expect([...forward].sort((left, right) => left - right)).toEqual(Array.from({ length: 150 }, (_, index) => index + 1));
  await page.getByRole('button', { name: 'latest', exact: true }).click();
  await expect(page.locator('.audit-page-info')).toContainText('latest');
  await expect(page.getByRole('button', { name: 'older ›', exact: true })).toBeEnabled();
});
