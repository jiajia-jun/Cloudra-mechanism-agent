import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { parseSync, transformSync } from 'rolldown/utils';

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
  const code = `${action('changeWorkspace')}\n${action('createProject')}\n({ changeWorkspace, createProject, picked: ${pickerCallback} });`;
  return vm.runInNewContext(transformSync('actions.ts', code, { lang: 'ts' }).code, globals);
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

console.log('App.actions.test.ts: ok');
