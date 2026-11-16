import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { parseSync, transformSync } from 'rolldown/utils';

// Execute the real component callbacks, as App.actions.test.ts does. Only HTTP
// responses and React setters are controlled so request ordering is repeatable.
function component(file: string) {
  const source = readFileSync(new URL(file, import.meta.url), 'utf8');
  const nodes: any[] = [];
  function visit(node: any) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { node.forEach(visit); return; }
    nodes.push(node);
    Object.values(node).forEach(visit);
  }
  visit(parseSync(file, source, { lang: 'tsx' }).program);
  const text = (node: any): string => source.slice(node.start, node.end);
  return {
    variable(name: string) {
      return nodes.find(node => node.type === 'VariableDeclarator' && node.id?.name === name)?.init;
    },
    effect(fragment: string) {
      return nodes.find(node => node.type === 'CallExpression' && node.callee?.name === 'useEffect'
        && text(node.arguments[0]).includes(fragment));
    },
    event(name: string, fragment: string) {
      return nodes.find(node => node.type === 'JSXAttribute' && node.name?.name === name
        && node.value?.expression && text(node.value.expression).includes(fragment)).value.expression;
    },
    evaluate(node: any, globals: Record<string, unknown>): any {
      return vm.runInNewContext(transformSync('callback.ts', `(${text(node)})`, { lang: 'ts' }).code, globals);
    },
    callback(name: string, globals: Record<string, unknown>): any {
      const node = this.variable(name);
      return this.evaluate(node.type === 'CallExpression' ? node.arguments[0] : node, globals);
    },
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
const flush = () => new Promise(resolve => setImmediate(resolve));
const emptyGoal = { objective: '', completion_criteria: '', current_focus: '' };
const goalA = { objective: 'A objective', completion_criteria: 'A criteria', current_focus: 'A focus' };
const goalB = { objective: 'B objective', completion_criteria: 'B criteria', current_focus: 'B focus' };
const overview = component('./ConsoleIndexPage.tsx');
const hub = component('./HubPanel.tsx');
const ops = component('./OpsPanel.tsx');
const failures: string[] = [];
async function check(name: string, test: () => Promise<void> | void) {
  try { await test(); console.log(`ok: ${name}`); }
  catch (error) { failures.push(name); console.error(`FAIL: ${name}`, error); }
}

function goalState() {
  const state = { goal: null as object | null, draft: { ...emptyGoal }, editing: false, saving: false };
  const globals: Record<string, any> = {
    goalRequestRef: { current: 0 },
    goalEditRef: { current: 0 },
    setGoal(value: object | null) { state.goal = value; },
    setGoalDraft(value: typeof emptyGoal) { state.draft = value; },
    setEditingGoal(value: boolean) { state.editing = value; },
    setSavingGoal(value: boolean) { state.saving = value; },
    onToast() {}, onError(error: unknown) { throw error; }, t: { goalSavedToast: 'saved' },
  };
  if (overview.variable('changeGoalDraft')) globals.changeGoalDraft = overview.callback('changeGoalDraft', globals);
  return { state, globals };
}

await check('late A goal cannot replace B or become B saved objective', async () => {
  const { state, globals } = goalState();
  const a = deferred<{ goal: typeof goalA }>();
  const b = deferred<{ goal: typeof goalB }>();
  const writes: Array<{ id: string; goal: typeof goalA }> = [];
  const api = {
    getGoal: (id: string) => (id === 'A' ? a : b).promise,
    setGoal: async (id: string, goal: typeof goalA) => { writes.push({ id, goal }); return { goal }; },
  };
  const effect = overview.effect('api.getGoal');
  const cleanup = overview.evaluate(effect.arguments[0], { ...globals, api, activeAgent: { id: 'A' } })();
  cleanup?.();
  overview.evaluate(effect.arguments[0], { ...globals, api, activeAgent: { id: 'B' } })();
  b.resolve({ goal: goalB }); await flush();
  a.resolve({ goal: goalA }); await flush();
  assert.deepEqual(structuredClone(state.goal), goalB);
  await overview.callback('handleSaveGoal', { ...globals, api, activeAgent: { id: 'B' }, goalDraft: state.draft })();
  assert.deepEqual(structuredClone(writes), [{ id: 'B', goal: goalB }]);
});

await check('switching to an agent with no goal discards the previous goal editor', async () => {
  const { state, globals } = goalState();
  state.goal = goalA; state.draft = goalA; state.editing = true; state.saving = true;
  overview.evaluate(overview.effect('api.getGoal').arguments[0], {
    ...globals, activeAgent: { id: 'B' }, api: { getGoal: async () => ({ goal: null }) },
  })();
  await flush();
  assert.equal(state.goal, null);
  assert.deepEqual(structuredClone(state.draft), emptyGoal);
  assert.equal(state.editing, false);
  assert.equal(state.saving, false);
});

await check('late A goal save cannot close or overwrite the B editor', async () => {
  const { state, globals } = goalState();
  const saved = deferred<{ goal: typeof goalA }>();
  const api = { getGoal: async (id: string) => ({ goal: id === 'A' ? goalA : goalB }), setGoal: () => saved.promise };
  const effect = overview.effect('api.getGoal');
  const cleanup = overview.evaluate(effect.arguments[0], { ...globals, api, activeAgent: { id: 'A' } })();
  await flush();
  const pending = overview.callback('handleSaveGoal', { ...globals, api, activeAgent: { id: 'A' }, goalDraft: goalA })();
  cleanup?.();
  overview.evaluate(effect.arguments[0], { ...globals, api, activeAgent: { id: 'B' } })();
  await flush();
  state.editing = true; state.draft = { ...goalB, objective: 'B edited' }; state.saving = true;
  saved.resolve({ goal: goalA }); await pending;
  assert.deepEqual(structuredClone(state.goal), goalB);
  assert.equal(state.draft.objective, 'B edited');
  assert.equal(state.editing, true);
  assert.equal(state.saving, true);
});

await check('the initial goal read does not overwrite a draft already being edited', async () => {
  const { state, globals } = goalState();
  const read = deferred<{ goal: typeof goalA }>();
  overview.evaluate(overview.effect('api.getGoal').arguments[0], {
    ...globals, activeAgent: { id: 'A' }, api: { getGoal: () => read.promise },
  })();
  overview.evaluate(overview.event('onClick', 'setEditingGoal(true)'), { ...globals, goal: null })();
  overview.evaluate(overview.event('onChange', 'objective:'), { ...globals, goalDraft: state.draft })({ target: { value: 'new draft' } });
  read.resolve({ goal: goalA }); await flush();
  assert.deepEqual(structuredClone(state.goal), goalA);
  assert.equal(state.draft.objective, 'new draft');
  assert.equal(state.editing, true);
});

for (const field of ['objective', 'completion_criteria', 'current_focus'] as const) {
  await check(`saving a goal preserves new ${field} edits while waiting`, async () => {
    const { state, globals } = goalState();
    state.goal = goalA; state.draft = goalA; state.editing = true;
    const saved = deferred<{ goal: typeof goalA }>();
    const pending = overview.callback('handleSaveGoal', {
      ...globals, activeAgent: { id: 'A' }, goalDraft: state.draft, api: { setGoal: () => saved.promise },
    })();
    overview.evaluate(overview.event('onChange', `${field}:`), { ...globals, goalDraft: state.draft })({ target: { value: 'unsaved revision' } });
    saved.resolve({ goal: goalA }); await pending;
    assert.deepEqual(structuredClone(state.goal), goalA);
    assert.equal(state.draft[field], 'unsaved revision');
    assert.equal(state.editing, true);
    assert.equal(state.saving, false);
  });
}

await check('a saved goal closes the editor when the submitted draft is unchanged', async () => {
  const { state, globals } = goalState();
  state.editing = true;
  await overview.callback('handleSaveGoal', {
    ...globals, activeAgent: { id: 'A' }, goalDraft: goalA, api: { setGoal: async () => ({ goal: goalA }) },
  })();
  assert.deepEqual(structuredClone(state.goal), goalA);
  assert.equal(state.editing, false);
  assert.equal(state.saving, false);
});

await check('DAG activation uses the project mode even when cached summaries disagree', () => {
  for (const [mode, summary, mirror, want] of [
    ['standard', 'dag_guided', 'dag_guided', false],
    ['dag_record', 'standard', 'standard', true],
    ['dag_guided', 'standard', 'standard', true],
  ] as const) {
    const actual = overview.evaluate(overview.variable('dagModeActive'), {
      project: { settings: { orchestration_mode: mode, defaults: { orchestration_mode: mirror } } },
      dagSummary: { mode: summary, nodeCount: 1, edgeCount: 0, accepted: true },
    });
    assert.equal(actual, want, mode);
  }
});

await check('DAG summary reloads on mode changes and ignores old responses', async () => {
  const a = deferred<object>(); const b = deferred<object>();
  let summary: any = null; let reads = 0;
  const globals = { setDagSummary(value: unknown) { summary = value; }, api: { dagDelivery: () => (++reads === 1 ? a : b).promise } };
  const effect = overview.effect('api.dagDelivery');
  const first = { ...globals, project: { id: 'P', settings: { orchestration_mode: 'dag_guided' } } };
  const second = { ...globals, project: { id: 'P', settings: { orchestration_mode: 'dag_record' } } };
  const cleanup = overview.evaluate(effect.arguments[0], first)();
  const before = overview.evaluate(effect.arguments[1], first);
  const after = overview.evaluate(effect.arguments[1], second);
  if (before.some((value: unknown, index: number) => value !== after[index])) {
    cleanup?.(); overview.evaluate(effect.arguments[0], second)();
  }
  b.resolve({ mode: 'dag_record', graph: { nodes: [{}, {}], edges: [{}] } }); await flush();
  a.resolve({ mode: 'dag_guided', graph: { nodes: [{}], edges: [] } }); await flush();
  assert.equal(reads, 2);
  assert.equal(summary.nodeCount, 2);
  assert.equal(summary.edgeCount, 1);
});

await check('late A forum submission keeps B posts and the new B draft', async () => {
  const submitted = deferred<object>();
  const state = { posts: [] as any[], loadedPid: '', content: 'A draft', sending: false, topic: '' };
  const globals: Record<string, any> = {
    loadVersionRef: { current: 0 }, projectScopeRef: { current: 0 }, latestPostSeqRef: { current: 0 }, cursorRef: { current: 0 },
    setLoading() {}, setPosts(value: any[]) { state.posts = value; }, setAgents() {}, setPendingPosts() {},
    setLoadedPid(value: string) { state.loadedPid = value; }, setSelectedTopic(value: string) { state.topic = value; },
    setReplyTo() {}, setTopic() {}, setToAgent() {}, setSending(value: boolean) { state.sending = value; },
    setContent(value: string | ((current: string) => string)) { state.content = typeof value === 'function' ? value(state.content) : value; },
    onToast() {}, t: { hubPostedToast: () => '' },
    api: { projectView: async (pid: string) => ({ project: { id: pid }, agents: [{ id: pid }], cursor: 0 }),
      hubPosts: async (pid: string) => ({ posts: [{ id: pid, seq: 1, topic: pid, content: pid }] }), hubPost: () => submitted.promise },
  };
  globals.load = hub.callback('load', globals);
  const effect = hub.effect('setLoadedPid(null)');
  const cleanup = hub.evaluate(effect.arguments[0], { ...globals, projectId: 'A' })();
  await flush();
  const pending = hub.callback('submit', { ...globals, projectId: 'A', sending: false, topic: 'A', content: 'A draft', kind: 'question', toAgent: '', replyTo: null })();
  cleanup?.();
  hub.evaluate(effect.arguments[0], { ...globals, projectId: 'B' })();
  await flush();
  state.content = 'new B draft'; state.sending = true;
  submitted.resolve({ post: { topic: 'A' }, notified_count: 0 }); await pending;
  assert.equal(state.loadedPid, 'B');
  assert.equal(state.posts[0].topic, 'B');
  assert.equal(state.content, 'new B draft');
  assert.equal(state.sending, true);
});

for (const edited of [false, true]) {
  await check(`a forum submission ${edited ? 'preserves newly edited' : 'clears only submitted'} draft fields`, async () => {
    const submitted = deferred<object>();
    const firstReply = { id: 'first-post' };
    const nextReply = { id: 'next-post' };
    const state = { content: 'submitted content', toAgent: 'first-agent', replyTo: firstReply as object | null };
    function update<T>(current: T, next: T | ((value: T) => T)): T {
      return typeof next === 'function' ? (next as (value: T) => T)(current) : next;
    }
    const globals = {
      projectScopeRef: { current: 1 }, projectId: 'A', sending: false, topic: 'topic', kind: 'question',
      content: state.content, toAgent: state.toAgent, replyTo: firstReply,
      api: { hubPost: () => submitted.promise }, load: async () => {}, setSelectedTopic() {}, setSending() {},
      setContent(next: string | ((value: string) => string)) { state.content = update(state.content, next); },
      setToAgent(next: string | ((value: string) => string)) { state.toAgent = update(state.toAgent, next); },
      setReplyTo(next: object | null | ((value: object | null) => object | null)) { state.replyTo = update(state.replyTo, next); },
      onToast() {}, t: { hubPostedToast: () => '' },
    };
    const pending = hub.callback('submit', globals)();
    if (edited) { state.content = 'new draft'; state.toAgent = 'next-agent'; state.replyTo = nextReply; }
    submitted.resolve({ post: { topic: 'topic' }, notified_count: 0 }); await pending;
    assert.equal(state.content, edited ? 'new draft' : '');
    assert.equal(state.toAgent, edited ? 'next-agent' : '');
    assert.deepEqual(state.replyTo, edited ? nextReply : null);
  });
}

await check('reminder polling and manual refresh share stale-response protection', async () => {
  const a = deferred<object[]>(); const b = deferred<object[]>(); const manual = deferred<object[]>();
  let reminders: any[] | null = null; let bReads = 0;
  const timers: Array<() => void> = [];
  const shared = {
    remindersRequestRef: { current: 0 }, setReminders(value: any[] | null) { reminders = value; },
    onError(error: unknown) { throw error; }, setInterval(callback: () => void) { timers.push(callback); return timers.length; }, clearInterval() {},
    api: { listPendingReminders: (id: string) => id === 'A' ? a.promise : ++bReads === 1 ? b.promise : manual.promise },
  };
  const forProject = (id: string) => {
    const globals = { ...shared, project: { id } };
    return { ...globals, loadReminders: ops.callback('loadReminders', globals) };
  };
  const effect = ops.effect('void loadReminders()');
  const cleanup = ops.evaluate(effect.arguments[0], forProject('A'))();
  cleanup?.();
  const current = forProject('B');
  ops.evaluate(effect.arguments[0], current)();
  const newest = current.loadReminders();
  manual.resolve([{ project_id: 'B', message: 'new B reminder' }]); await newest;
  b.resolve([{ project_id: 'B', message: 'old B reminder' }]); await flush();
  a.resolve([{ project_id: 'A', message: 'A reminder' }]); await flush();
  assert.deepEqual(structuredClone(reminders), [{ project_id: 'B', message: 'new B reminder' }]);
  timers.at(-1)!(); await flush();
  assert.equal(bReads, 3);
});

assert.deepEqual(failures, [], `panel state regressions failed: ${failures.join(', ')}`);
console.log('panelState tests ok');
