import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';
import { parseSync, transformSync } from 'rolldown/utils';
import { mergeAgentSnapshot } from './agentState.ts';
import { mergeProjectSnapshot } from './projectState.ts';

const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8');
const nodes: any[] = [];
function visit(node: any) {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) { node.forEach(visit); return; }
  nodes.push(node); Object.values(node).forEach(visit);
}
visit(parseSync('App.tsx', source, { lang: 'tsx' }).program);
const code = (node: any) => source.slice(node.start, node.end);
const action = (name: string) => {
  const node = nodes.find(node => node.type === 'FunctionDeclaration' && node.id?.name === name);
  return node ? code(node) : '';
};
function run(text: string, globals: Record<string, unknown>) {
  return vm.runInNewContext(transformSync('actions.ts', text, { lang: 'ts' }).code, { mergeAgentSnapshot, mergeProjectSnapshot, ...globals });
}

test('mode save retries failed members and reflects independently successful members', async () => {
  let project = { id: 'p', settings: { orchestration_mode: 'standard', defaults: {} } };
  const agent = (id: string) => ({ id, display_name: id, project_id: 'p', settings_revision: 1, settings: { orchestration_mode: 'standard' } });
  const server = [agent('a'), agent('b')];
  let cached = structuredClone(server);
  let fail = true;
  const writes: string[] = [];
  const api = {
    patchProject: async (_id: string, patch: object) => ({ data: { ...project, ...patch } }),
    listAgents: async () => structuredClone(server),
    patchSettings: async (id: string, patch: object) => {
      writes.push(id);
      if (id === 'b' && fail) { fail = false; throw new Error('temporary failure'); }
      const item = server.find(a => a.id === id)!;
      Object.assign(item.settings, patch); item.settings_revision++;
      return { data: structuredClone(item) };
    },
  };
  const save = () => run(`${action('updateAgentSettings')}\n${action('syncProjectAgentSettings')}\n${action('handleSaveProjectSettings')}\nhandleSaveProjectSettings;`, {
    activeProject: project, agents: cached, api, dedupeAgents: (a: unknown[]) => a,
    setProjects: (update: (p: typeof project[]) => typeof project[]) => { project = update([project])[0]; },
    setAgents: (update: (a: typeof cached) => typeof cached) => { cached = update(cached); },
    reportError() {}, pushToast() {},
  });
  await assert.rejects(save()({ orchestration_mode: 'dag_guided' }));
  assert.equal(project.settings.orchestration_mode, 'dag_guided');
  assert.equal(cached[0].settings.orchestration_mode, 'dag_guided', 'successful member must be reflected despite another failure');
  await save()({ orchestration_mode: 'dag_guided' });
  assert.deepEqual(writes, ['a', 'b', 'b']);
  assert.equal(cached[1].settings.orchestration_mode, 'dag_guided');
});

test('settings events update both scopes without regressing newer settings', () => {
  let projects = [{ id: 'p', name: 'old', settings: { orchestration_mode: 'standard', defaults: {} } }];
  let agents = [{ id: 'a', settings_revision: 1, settings: { orchestration_mode: 'standard', model: 'old' } }];
  const property = nodes.find(node => (node.type === 'Property' || node.type === 'ObjectProperty')
    && node.key?.name === 'onEvent' && code(node).includes("event.type === 'project.synced'"));
  const callback = run(`(${code(property.value)});`, {
    closed: false, cursor: 0, activeProjectId: 'p', activeAgentIdRef: { current: null },
    projectStateThroughRef: { current: new Map() }, agentStateThroughRef: { current: new Map() },
    setProjects: (update: (p: typeof projects) => typeof projects) => { projects = update(projects); },
    setAgents: (update: (a: typeof agents) => typeof agents) => { agents = update(agents); },
  });
  callback({ type: 'project.settings_changed', seq: 1, project_id: 'p', session_id: null, data: { changes: { orchestration_mode: 'dag_guided', defaults: {} } } });
  callback({ type: 'agent.settings_changed', seq: 2, project_id: 'p', session_id: 'a', data: { changes: { orchestration_mode: 'dag_guided', model: null }, settings_revision: 2 } });
  assert.equal(projects[0].settings.orchestration_mode, 'dag_guided');
  assert.equal(agents[0].settings.orchestration_mode, 'dag_guided');
  assert.equal(agents[0].settings.model, 'old', 'null has the same no-op meaning as RuntimeSettings.apply');
  callback({ type: 'agent.settings_changed', seq: 3, project_id: 'p', session_id: 'a', data: { changes: { orchestration_mode: 'standard' }, settings_revision: 1 } });
  assert.equal(agents[0].settings.orchestration_mode, 'dag_guided');
});

test('cleared Agent overrides do not display the project defaults as effective settings', () => {
  const globals = {
    activeAgent: { settings: { model: '', reasoning_effort: null } },
    activeProject: { settings: { defaults: { model: 'project-model', reasoning_effort: 'ultra' } } },
  };
  for (const [name, expected] of [['currentModel', ''], ['reasoningEffort', null]]) {
    const attr = nodes.find(node => node.type === 'JSXAttribute' && node.name?.name === name);
    assert.equal(run(`(${code(attr.value.expression)});`, globals), expected);
  }
});

test('project snapshots repair stale settings but cannot roll back a newer event', () => {
  const declaration = nodes.find(node => node.type === 'VariableDeclarator' && node.id?.name === 'updateProjectView');
  let projects = [{ id: 'p', settings: { orchestration_mode: 'standard' } }];
  const through = new Map([['p', 10]]);
  const apply = run(`(${code(declaration.init.arguments[0])});`, {
    projectStateThroughRef: { current: through },
    setProjects: (update: (p: typeof projects) => typeof projects) => { projects = update(projects); },
  });
  apply({ project: { id: 'p', settings: { orchestration_mode: 'dag_record' } }, cursor: 20 });
  assert.equal(projects[0].settings.orchestration_mode, 'dag_record');
  through.set('p', 30);
  apply({ project: { id: 'p', settings: { orchestration_mode: 'standard' } }, cursor: 25 });
  assert.equal(projects[0].settings.orchestration_mode, 'dag_record');
});
