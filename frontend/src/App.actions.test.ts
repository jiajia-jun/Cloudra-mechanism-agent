import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import { parseSync, transformSync } from 'rolldown/utils';
import { resolveComposerSendTarget } from './composerSend.ts';
import * as composerSend from './composerSend.ts';
import { mergeProjectSnapshot } from './projectState.ts';

const appSource = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8');
const appTree = parseSync('App.tsx', appSource, { lang: 'tsx' }).program;
const nodes: any[] = [];
function visit(node: any) {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) { node.forEach(visit); return; }
  nodes.push(node);
  Object.values(node).forEach(visit);
}
visit(appTree);
function action(name: string) {
  const node = nodes.find(node => node.type === 'FunctionDeclaration' && node.id?.name === name)!;
  return appSource.slice(node.start, node.end);
}
const picker = nodes.find(node => node.type === 'ArrowFunctionExpression'
  && node.body?.operator === 'void' && node.body.argument?.type === 'CallExpression'
  && node.body.argument.callee.name === 'changeWorkspace')!;
const pickerCallback = appSource.slice(picker.start, picker.end);
function actions(globals: Record<string, unknown>) {
  const code = `${action('changeWorkspace')}\n${action('createProject')}\n${action('sendMessage')}\n${action('spawnRole')}\n${action('onPickImages')}\n({ changeWorkspace, createProject, sendMessage, spawnRole, onPickImages, picked: ${pickerCallback} });`;
  return vm.runInNewContext(transformSync('actions.ts', code, { lang: 'ts' }).code, {
    resolveComposerSendTarget,
    mergeProjectSnapshot,
    activeProjectIdRef: { current: (globals.activeProject as { id?: string } | null)?.id },
    agentSelectionVersionRef: { current: 0 },
    setAgents() {},
    ...globals,
  });
}

// Exercise the actual sidebar callback while a different project is selected.
{
  const clicked = { id: 'P', workspace_dir: '/old-P' };
  const active = { id: 'Q', workspace_dir: '/old-Q' };
  let projects = [clicked, active];
  const patches: unknown[] = [];
  const calls = actions({
    p: clicked, activeProject: active,
    api: { patchProject: async (id: string, patch: object) => {
      patches.push({ id, patch });
      return { data: { ...clicked, ...patch } };
    } },
    setProjects: (update: (prev: object[]) => typeof projects) => { projects = update(projects); },
    pushToast() {}, reportError(error: unknown) { throw error; },
  });
  calls.picked('/new-P');
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(structuredClone(patches), [{ id: 'P', patch: { workspace_dir: '/new-P' } }]);
  assert.equal(projects.find(project => project.id === 'P')?.workspace_dir, '/new-P');
  assert.equal(projects.find(project => project.id === 'Q')?.workspace_dir, '/old-Q');
}

// A successful creation is authoritative even if a subsequent list read fails.
{
  const created = { id: 'created', name: 'new project' };
  let projects: object[] = [];
  let selected: string | undefined;
  const notices: string[] = [];
  const calls = actions({
    p: {}, activeProject: null,
    api: { createProject: async () => ({ data: created }), listProjects: async () => { throw new Error('offline'); } },
    setProjects: (update: (prev: object[]) => object[]) => { projects = update(projects); },
    setActiveProjectId: (id: string) => { selected = id; },
    pushToast: (_kind: string, text: string) => notices.push(text),
  });
  await calls.createProject('new project');
  assert.equal(selected, 'created');
  assert.deepEqual(structuredClone(projects), [created]);
  assert.equal(notices.length, 1);
}

// SSE may populate the same project while the creation response is pending.
{
  const existing = { id: 'existing', name: 'another project' };
  const created = { id: 'created', name: 'new project' };
  let projects: object[] = [existing];
  const calls = actions({
    p: {}, activeProject: null,
    api: { createProject: async () => ({ data: created }) },
    setProjects: (update: (prev: object[]) => object[]) => { projects = update(projects); },
    setActiveProjectId() {}, pushToast() {},
  });
  const pending = calls.createProject('new project');
  projects = [existing, { ...created, name: 'SSE snapshot' }];
  await pending;
  assert.deepEqual(structuredClone(projects), [existing, created]);
}

// Unknown slash input still starts a coordinator when no agent is selected.
{
  let draft = '/unknown hello';
  let selected: string | undefined;
  let pending: object[] = [];
  const requests: { projectId: string; body: Record<string, unknown> }[] = [];
  const errors: string[] = [];
  const calls = actions({
    p: {}, activeProject: { id: 'P', settings: { orchestration_mode: 'standard' } },
    activeAgent: null, draft, sending: false, interactions: [],
    pendingMessageSeqRef: { current: 0 }, pendingImages: [], lang: 'en',
    api: { spawnAgent: async (projectId: string, body: Record<string, unknown>) => {
      requests.push({ projectId, body });
      return { data: { id: 'created-agent' } };
    } },
    setSending() {}, setPendingImages() {},
    setPendingMessages: (update: (prev: object[]) => object[]) => { pending = update(pending); },
    setDraft: (value: string | ((current: string) => string)) => { draft = typeof value === 'function' ? value(draft) : value; },
    selectAgent: async (id: string) => { selected = id; },
    reportError: (error: Error) => errors.push(error.message),
  });
  await calls.sendMessage();
  assert.deepEqual(errors, []);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].projectId, 'P');
  assert.equal(requests[0].body.role_id, 'coordinator');
  assert.equal(requests[0].body.query, '/unknown hello');
  assert.equal(selected, 'created-agent');
  assert.equal(draft, '');
  assert.deepEqual(pending, []);
}

// 在已有研究项目中启动主控时，沿用该项目选择的模型并保留等待期间的新草稿。
{
  let draft = 'Explore substitution';
  const project = { id: 'study', settings: {
    orchestration_mode: 'dag_guided', defaults: { model: 'chosen-model', reasoning_effort: 'ultra' },
  } };
  const spawns: Record<string, unknown>[] = [];
  const errors: string[] = [];
  const calls = actions({
    activeProject: project, activeAgent: null, interactions: [], draft, sending: false,
    pendingImages: [], pendingMessageSeqRef: { current: 0 }, lang: 'zh',
    api: { spawnAgent: async (projectId: string, body: Record<string, unknown>) => {
      spawns.push({ projectId, ...body });
      draft = 'Next question';
      return { data: { id: 'new-agent' } };
    } },
    setSending() {}, setPendingImages() {}, setPendingMessages() {}, selectAgent() {},
    setDraft: (value: string | ((current: string) => string)) => { draft = typeof value === 'function' ? value(draft) : value; },
    reportError: (error: Error) => errors.push(error.message),
  });
  await calls.sendMessage();
  assert.deepEqual(errors, []);
  assert.deepEqual(structuredClone(spawns), [{
    projectId: 'study', role_id: 'coordinator', query: 'Explore substitution', language: 'zh',
    settings: { model: 'chosen-model', reasoning_effort: 'ultra', orchestration_mode: 'dag_guided' },
  }]);
  assert.equal(draft, 'Next question');
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function composerState(activeAgent: { id: string } | null = null) {
  const state = { draft: 'Original question', images: [] as Array<{ path: string; artifactId: string }>,
    messages: [] as object[], agents: [] as Array<{ id: string }>, selected: activeAgent?.id ?? null, errors: [] as string[] };
  const projectRef = { current: 'P' };
  const selectionRef = { current: 1 };
  const globals = {
    activeProject: { id: 'P', settings: { orchestration_mode: 'standard', defaults: {} } }, activeAgent,
    activeProjectIdRef: projectRef, agentSelectionVersionRef: selectionRef,
    draft: state.draft, sending: false, interactions: [], pendingImages: state.images,
    pendingMessageSeqRef: { current: 0 }, lang: 'en',
    setDraft: (update: string | ((prev: string) => string)) => { state.draft = typeof update === 'function' ? update(state.draft) : update; },
    setPendingImages: (update: typeof state.images | ((prev: typeof state.images) => typeof state.images)) => { state.images = typeof update === 'function' ? update(state.images) : update; },
    setPendingMessages: (update: (prev: object[]) => object[]) => { state.messages = update(state.messages); },
    setAgents: (update: (prev: typeof state.agents) => typeof state.agents) => { state.agents = update(state.agents); },
    setSending() {}, setUploading() {}, pushToast() {},
    selectAgent: async (id: string) => { state.selected = id; selectionRef.current++; },
    reportError: (error: Error) => state.errors.push(error.message),
    uploadedArtifactsRef: { current: new Map() }, fileInputRef: { current: null },
  };
  return { state, projectRef, selectionRef, globals };
}

for (const entry of ['sendMessage', 'spawnRole'] as const) {
  for (const switchTo of ['project', 'agent'] as const) {
    await test(`${entry} does not select its created agent after switching ${switchTo}`, async () => {
      const { state, projectRef, selectionRef, globals } = composerState();
      const response = deferred<{ data: { id: string } }>();
      const calls = actions({ ...globals, api: { spawnAgent: () => response.promise } });
      const pending = entry === 'sendMessage' ? calls.sendMessage() : calls.spawnRole('small_mol');
      if (switchTo === 'project') projectRef.current = 'Q';
      selectionRef.current++;
      state.selected = 'new-selection';
      state.draft = 'Original question';
      response.resolve({ data: { id: 'old-created-agent' } });
      await pending;
      assert.deepEqual(state.errors, []);
      assert.equal(state.selected, 'new-selection');
      assert.equal(state.draft, 'Original question', 'a late send must not clear another selection’s draft');
    });
  }
}

await test('a late upload never adds the previous project’s attachments to the current composer', async () => {
  const { state, projectRef, selectionRef, globals } = composerState();
  const response = deferred<{ path: string; artifact_id: string }>();
  const calls = actions({ ...globals, api: { uploadFile: () => response.promise } });
  const pending = calls.onPickImages([{ name: 'original.png', size: 32 }]);
  projectRef.current = 'Q';
  selectionRef.current++;
  state.images = [{ path: '/Q/new.png', artifactId: 'new-image' }];
  response.resolve({ path: '/P/original.png', artifact_id: 'old-image' });
  await pending;
  assert.deepEqual(state.images, [{ path: '/Q/new.png', artifactId: 'new-image' }]);
});

for (const whileWaiting of ['unchanged', 'new-draft', 'other-project'] as const) {
  await test(`a failed send preserves text and attachments (${whileWaiting})`, async () => {
    const { state, projectRef, selectionRef, globals } = composerState({ id: 'agent-P' });
    state.images.push({ path: '/P/original.png', artifactId: 'old-image' });
    const response = deferred<never>();
    const calls = actions({ ...globals, api: { sendMessage: () => response.promise } });
    const pending = calls.sendMessage();
    if (whileWaiting === 'new-draft') state.draft = 'Next question';
    if (whileWaiting === 'other-project') {
      projectRef.current = 'Q'; selectionRef.current++; state.draft = 'Question for Q'; state.images = [];
    }
    response.reject(new Error('offline'));
    await pending;
    assert.deepEqual(state.errors, ['offline']);
    assert.equal(state.draft, whileWaiting === 'new-draft' ? 'Next question' : whileWaiting === 'other-project' ? 'Question for Q' : 'Original question');
    assert.deepEqual(state.images, whileWaiting === 'other-project' ? [] : [{ path: '/P/original.png', artifactId: 'old-image' }]);
    assert.equal(state.messages.length, 0);
  });
}

await test('retrying the first image message reuses the agent already created before delivery failed', async () => {
  const { state, globals } = composerState();
  state.images.push({ path: '/P/original.png', artifactId: 'image-P' });
  let spawns = 0;
  const recipients: string[] = [];
  const api = {
    spawnAgent: async () => ({ data: { id: `created-${++spawns}`, project_id: 'P' } }),
    sendMessage: async (id: string) => {
      recipients.push(id);
      if (recipients.length === 1) throw new Error('first delivery failed');
      return { event_id: 'delivered-message' };
    },
    eventDetail: async () => ({ session_seq: 1 }),
  };
  await actions({ ...globals, api }).sendMessage();
  assert.equal(state.draft, 'Original question');
  assert.equal(state.images.length, 1);
  await actions({ ...globals, api, activeAgent: state.agents.find(agent => agent.id === state.selected) ?? null,
    draft: state.draft, pendingImages: state.images, setEvents() {}, maxSeqRef: { current: 0 },
  }).sendMessage();
  assert.equal(spawns, 1, 'retry must use the accepted creation instead of spawning a second coordinator');
  assert.deepEqual(recipients, ['created-1', 'created-1']);
  assert.equal(state.selected, 'created-1');
  assert.equal(state.draft, '');
  assert.equal(state.images.length, 0);
  assert.deepEqual(state.errors, ['first delivery failed']);
});

await test('changing agent while the accepted spawn selection loads does not clear the new composer', async () => {
  const { state, selectionRef, globals } = composerState();
  state.images.push({ path: '/P/original.png', artifactId: 'image-P' });
  const selecting = deferred<void>();
  const selected = deferred<void>();
  const calls = actions({ ...globals,
    api: { spawnAgent: async () => ({ data: { id: 'created-agent', project_id: 'P' } }), sendMessage: async () => ({ event_id: 'message' }) },
    selectAgent: (id: string) => {
      state.selected = id; selectionRef.current++; selected.resolve(); return selecting.promise;
    },
  });
  const sending = calls.sendMessage();
  await selected.promise;
  selectionRef.current++;
  state.selected = 'other-agent';
  state.draft = 'Original question';
  state.images = [{ path: '/P/next.png', artifactId: 'next-image' }];
  selecting.resolve();
  await sending;
  assert.equal(state.selected, 'other-agent');
  assert.equal(state.draft, 'Original question');
  assert.deepEqual(state.images, [{ path: '/P/next.png', artifactId: 'next-image' }]);
});

await test('same-role siblings do not share pending interaction or approval UI state', () => {
  const activeAgent = { id: 'B', role_id: 'small_mol', display_name: 'Worker B' };
  const appPredicate = nodes.find(node => node.type === 'VariableDeclarator' && node.id?.name === 'hasActiveAgentDecision').init;
  const promptSource = readFileSync(new URL('./InteractionPrompt.tsx', import.meta.url), 'utf8');
  const promptTree = parseSync('InteractionPrompt.tsx', promptSource, { lang: 'tsx' }).program;
  const promptNodes: any[] = [];
  function collect(node: any) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { node.forEach(collect); return; }
    promptNodes.push(node); Object.values(node).forEach(collect);
  }
  collect(promptTree);
  const currentPredicate = promptNodes.find(node => node.type === 'VariableDeclarator' && node.id?.name === 'isCurrentAgent').init;
  for (const kind of ['interaction', 'approval'] as const) {
    for (const [sessionId, belongs] of [['A', false], ['B', true], [undefined, false]] as const) {
      const item = { session_id: sessionId, agent_id: 'small_mol', agent_name: 'small_mol', id: 'pending' };
      const hidden = vm.runInNewContext(transformSync('predicate.ts', appSource.slice(appPredicate.start, appPredicate.end), { lang: 'ts' }).code,
        { ...composerSend, activeAgent, interactions: kind === 'interaction' ? [item] : [], approvals: kind === 'approval' ? [item] : [] });
      const claimsCurrent = vm.runInNewContext(transformSync('predicate.ts', promptSource.slice(currentPredicate.start, currentPredicate.end), { lang: 'ts' }).code,
        { ...composerSend, activeAgent, sessionId, rawAgentId: 'small_mol', currentItem: { kind, data: item } });
      assert.equal(hidden, belongs, `${kind} for ${sessionId} must gate only its owning session’s composer`);
      assert.equal(claimsCurrent, belongs, `${kind} for ${sessionId} must use the same instance identity in its banner`);
    }
  }
});

console.log('App.actions.test.ts: ok');
