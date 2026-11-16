import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { parseSync, transformSync } from 'rolldown/utils';

const source = readFileSync(new URL('./ProjectSettingsModal.tsx', import.meta.url), 'utf8');
const ast = parseSync('ProjectSettingsModal.tsx', source, { lang: 'tsx' }).program;
const declarations = ast.body.map((node: any) => node.declaration ?? node)
  .filter((node: any) => node.type !== 'ImportDeclaration');
const code = transformSync('settings.tsx', declarations.map((node: any) => source.slice(node.start, node.end)).join('\n')
  + '\n({ AgentStrip, ProjectSettingsModal });', { lang: 'tsx' }).code;

type Element = { type: unknown; props: Record<string, any> };
function componentHarness(name: 'AgentStrip' | 'ProjectSettingsModal') {
  const state: unknown[] = [];
  let cursor = 0;
  const jsx = (type: unknown, props: Record<string, any>) => ({ type, props });
  const components = vm.runInNewContext(code, {
    require: () => ({ jsx, jsxs: jsx }),
    setTimeout() {},
    useState(initial: unknown) {
      const index = cursor++;
      if (!(index in state)) state[index] = typeof initial === 'function' ? initial() : initial;
      return [state[index], (next: unknown) => {
        state[index] = typeof next === 'function' ? next(state[index]) : next;
      }];
    },
  });
  return (props: Record<string, unknown>) => {
    cursor = 0;
    const tree = components[name](props);
    const elements: Element[] = [];
    function visit(node: any) {
      if (Array.isArray(node)) { node.forEach(visit); return; }
      if (!node || typeof node !== 'object') return;
      elements.push(node);
      visit(node.props?.children);
    }
    visit(tree);
    return {
      find: (predicate: (element: Element) => boolean) => {
        const element = elements.find(predicate);
        assert.ok(element, 'expected form control exists');
        return element.props;
      },
      fields: elements.filter(element => element.type === 'input' || element.type === 'select'),
    };
  };
}
const agent = (settings: object = {}) => ({ id: 'a', role_id: 'coordinator', display_name: 'A', state: 'idle',
  settings_revision: 1, settings: { model: 'old-model', orchestration_mode: 'standard', invocation_protocol: 'javascript',
    temperature: 1, reasoning_effort: 'ultra', context_window: 20000, max_tokens: 4000, timeout: 120,
    yolo: false, visual_mode: true, unattended: false, clean_context: false, ...settings } });
const project = (settings: object = {}) => ({ id: 'p', name: 'Project', workspace_dir: '/tmp/project',
  settings: { orchestration_mode: 'standard', defaults: { model: 'old-model', reasoning_effort: 'ultra' }, ...settings } });
const agentProps = (current: ReturnType<typeof agent>, onSave: (...args: any[]) => unknown) => ({
  agent: current, projectDefaultModel: 'unsaved-project-model', isExpanded: true, onToggleExpand() {}, onSave,
});
const projectProps = (current: ReturnType<typeof project>, onSaveProjectSettings: (patch: any) => unknown) => ({
  project: current, agents: [], activeAgentId: null, onClose() {}, onSaveProjectSettings,
  onSaveAgentSettings() {}, onToast() {},
});
const modelField = (form: ReturnType<ReturnType<typeof componentHarness>>) => form.fields.find(field =>
  field.type === 'input' && field.props.type === 'text')!.props;
const saveAgent = (form: ReturnType<ReturnType<typeof componentHarness>>) => form.find(element =>
  element.type === 'button' && element.props.children === '保存此智能体配置');
const saveProject = (form: ReturnType<ReturnType<typeof componentHarness>>) => form.find(element =>
  element.type === 'button' && element.props.children === '保存全局基准');

// A live DAG settings update must update untouched fields and must not be undone by editing only the model.
test('untouched mode follows live settings and model-only save stays sparse', async () => {
  const render = componentHarness('AgentStrip'); const patches: object[] = [];
  const save = async (_id: string, patch: object) => patches.push(patch);
  let form = render(agentProps(agent(), save));
  modelField(form).onChange({ target: { value: 'new-model' } });
  form = render(agentProps(agent({ orchestration_mode: 'dag_guided' }), save));
  assert.equal(form.fields.find(field => field.type === 'select')!.props.value, 'dag_guided');
  await saveAgent(form).onClick();
  assert.deepEqual(structuredClone(patches), [{ model: 'new-model' }]);
});

// Clearing overrides uses the server's supported empty-string values, not ignored null patches.
test('clearing Agent overrides submits supported reset values', async () => {
  const render = componentHarness('AgentStrip'); const patches: object[] = [];
  const props = agentProps(agent(), async (_id: string, patch: object) => patches.push(patch));
  let form = render(props);
  modelField(form).onChange({ target: { value: '' } });
  form.find(element => element.type === 'select' && element.props.title === '思考强度').onChange({ target: { value: '' } });
  form = render(props);
  await saveAgent(form).onClick();
  assert.deepEqual(structuredClone(patches), [{ model: '', reasoning_effort: '' }]);
});

// An accepted save clears only submitted edits: typing while it is pending remains an unsaved draft.
test('save preserves later typing and clears only submitted edits', async () => {
  const render = componentHarness('AgentStrip'); let resolve!: () => void;
  const pending = new Promise<void>(done => { resolve = done; });
  const patches: object[] = [];
  const save = async (_id: string, patch: object) => { patches.push(patch); await pending; };
  let form = render(agentProps(agent(), save));
  modelField(form).onChange({ target: { value: 'sent-model' } });
  form = render(agentProps(agent(), save));
  const saving = saveAgent(form).onClick();
  form = render(agentProps(agent(), save));
  modelField(form).onChange({ target: { value: 'next-model' } });
  resolve(); await saving;
  form = render(agentProps(agent({ model: 'sent-model' }), save));
  assert.equal(modelField(form).value, 'next-model');
  await saveAgent(form).onClick();
  assert.deepEqual(structuredClone(patches), [{ model: 'sent-model' }, { model: 'next-model' }]);
  form = render(agentProps(agent({ model: 'latest-server-model' }), save));
  assert.equal(modelField(form).value, 'latest-server-model');
});

// Project defaults can be cleared, and an unrelated incoming mode change is never replaced by an old draft.
test('project clears overrides without reverting live mode', async () => {
  const render = componentHarness('ProjectSettingsModal'); const patches: object[] = [];
  const save = async (patch: object) => patches.push(patch);
  let form = render(projectProps(project(), save));
  form.find(element => element.type === 'input' && element.props.placeholder === '例如: anthropic/claude-3-5-sonnet').onChange({ target: { value: '' } });
  form.fields.filter(field => field.type === 'select')[2].props.onChange({ target: { value: '' } });
  form = render(projectProps(project({ orchestration_mode: 'dag_guided' }), save));
  assert.equal(form.fields.find(field => field.type === 'select')!.props.value, 'dag_guided');
  await saveProject(form).onClick();
  assert.deepEqual(structuredClone(patches), [{ defaults: { model: '', reasoning_effort: '' } }]);
});

// Editing project defaults must not synchronize or overwrite independent Agent modes.
test('project model-only save does not submit orchestration mode', async () => {
  const render = componentHarness('ProjectSettingsModal'); const patches: object[] = [];
  const props = projectProps(project(), async (patch: object) => patches.push(patch));
  let form = render(props);
  form.find(element => element.type === 'input' && element.props.placeholder === '例如: anthropic/claude-3-5-sonnet').onChange({ target: { value: 'new-model' } });
  form = render(props);
  await saveProject(form).onClick();
  assert.deepEqual(structuredClone(patches), [{ defaults: { model: 'new-model' } }]);
});

// A failed mode cascade retains the explicit mode edit so the next save can retry it.
test('failed mode save retains the target mode for retry', async () => {
  const render = componentHarness('ProjectSettingsModal'); const patches: object[] = [];
  const save = async (patch: object) => {
    patches.push(patch);
    if (patches.length === 1) throw new Error('agent update failed');
  };
  let form = render(projectProps(project(), save));
  form.fields.find(field => field.type === 'select')!.props.onChange({ target: { value: 'dag_guided' } });
  form = render(projectProps(project(), save));
  await saveProject(form).onClick();
  // The project write succeeded before the Agent update failed.
  form = render(projectProps(project({ orchestration_mode: 'dag_guided' }), save));
  await saveProject(form).onClick();
  assert.deepEqual(structuredClone(patches), [
    { orchestration_mode: 'dag_guided' },
    { orchestration_mode: 'dag_guided' },
  ]);
});

// Empty Agent model inherits the global role slot, independent of an unsaved project default.
test('empty Agent model is independent of project draft', async () => {
  const render = componentHarness('AgentStrip');
  const form = render(agentProps(agent({ model: '' }), async () => {}));
  assert.ok(!String(form.find(element => element.props.title === '当前模型').children).includes('unsaved-project-model'));
});
