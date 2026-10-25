import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { parseSync, transformSync } from 'rolldown/utils';
import { resolveComposerSendTarget } from './composerSend.ts';

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
  const code = `${action('changeWorkspace')}\n${action('createProject')}\n${action('sendMessage')}\n({ changeWorkspace, createProject, sendMessage, picked: ${pickerCallback} });`;
  return vm.runInNewContext(transformSync('actions.ts', code, { lang: 'ts' }).code, { resolveComposerSendTarget, ...globals });
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

console.log('App.actions.test.ts: ok');
