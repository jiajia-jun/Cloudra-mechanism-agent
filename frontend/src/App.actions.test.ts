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
    setAgents() {}, recipientReady: true, uploading: false, adoptFirstAgent() {},
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
      response.resolve({ data: { id: 'old-created-agent' } });
      await pending;
      assert.deepEqual(state.errors, []);
      assert.equal(state.selected, 'new-selection');
      assert.equal(state.draft, entry === 'sendMessage' ? '' : 'Original question',
        'only the accepted send consumes its original recipient’s draft');
    });
  }
}

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

const draftHookSource = readFileSync(new URL('./useComposerDraft.ts', import.meta.url), 'utf8')
  .replace("import { useState } from 'react';", '').replace('export function', 'function');

function draftStore() {
  let all: Record<string, unknown> = {};
  return vm.runInNewContext(transformSync('draft.ts', draftHookSource+'\nuseComposerDraft;', { lang: 'ts' }).code, {
    useState: () => [all, (update: (old: object) => typeof all) => { all = update(all); }],
  }) as (project: string, agent: string | null, question?: string) => ReturnType<typeof import('./useComposerDraft')['useComposerDraft']>;
}

test('draft text and in-flight uploads stay with their project, agent and question', async () => {
  const render = draftStore();
  const { globals } = composerState({ id: 'A' });
  const upload = deferred<{ path: string; artifact_id: string }>();
  render('P','A').setDraft('For A');
  const pick = actions({ ...globals, ...render('P','A'), api: { uploadFile: () => upload.promise } });
  const pending = pick.onPickImages([{ name: 'a.png', size: 5 }]);
  assert.equal(render('P','A').uploading, true);
  const deliveries: object[] = [];
  await actions({ ...globals, ...render('P','A'), api: { sendMessage: () => { deliveries.push({}); } } }).sendMessage();
  assert.equal(deliveries.length, 0);
  render('P','B').setDraft('For B');
  upload.resolve({path:'P/a.png', artifact_id:'a'});
  await pending;
  assert.equal(render('P','A').uploading, false);
  assert.equal(render('P','A').pendingImages[0]?.artifactId, 'a');
  assert.equal(render('P','A').draft, 'For A');
  assert.equal(render('P','B').draft, 'For B');
  assert.equal(render('P','B').pendingImages.length, 0);
  assert.equal(render('Q','A').draft, '');
  assert.equal(render('P','A','question').draft, '');
});

test('adopting the first coordinator preserves unsent text and attachments for retry', () => {
  const render = draftStore();
  render('P',null).setDraft('First image');
  render('P',null).setPendingImages(() => [{ path:'a.png', artifactId:'a', name:'a.png', size:5 }]);
  render('P',null).adoptFirstAgent('new');
  assert.equal(render('P','new').draft,'First image');
  assert.equal(render('P','new').pendingImages[0]?.artifactId, 'a');
  assert.equal(render('P',null).draft,'');
  assert.equal(render('Q','new').pendingImages.length,0);
});

test('project loading and an unresolved selection cannot start a coordinator', async () => {
  const ready = nodes.find(node => node.type === 'VariableDeclarator' && node.id?.name === 'recipientReady').init;
  const code = transformSync('ready.ts', '('+appSource.slice(ready.start,ready.end)+')', {lang:'ts'}).code;
  for (const state of [
    { projectStream:null, activeAgentId:null, agents:[] },
    { projectStream:{projectId:'previous'}, activeAgentId:'A', activeAgent:{project_id:'previous'}, agents:[{id:'A'}] },
    { projectStream:{projectId:'P'}, activeAgentId:null, agents:[{id:'A'}] },
  ]) {
    const recipientReady = vm.runInNewContext(code, { activeProjectId:'P', activeProject:{id:'P'}, activeAgent:null, ...state });
    assert.equal(recipientReady, false);
    const {globals}=composerState();
    let spawns=0;
    await actions({...globals, recipientReady, api:{spawnAgent(){++spawns;}}}).sendMessage();
    assert.equal(spawns,0);
  }
});

test('input method candidate selection cannot submit chat or an answer', () => {
  const helpers = readFileSync(new URL('./LongTextControls.tsx', import.meta.url), 'utf8');
  const helper = parseSync('LongTextControls.tsx',helpers,{lang:'tsx'}).program.body.find((n:any)=>n.declaration?.id?.name==='composingText') as any;
  const composingText=vm.runInNewContext(transformSync('composing.ts','('+helpers.slice(helper.declaration.start,helper.declaration.end)+')',{lang:'ts'}).code);
  for(const [filename,id] of [['App.tsx','chat-message-input'],['InteractionPrompt.tsx','interaction-answer-input']]) {
    const source=readFileSync(new URL('./'+filename, import.meta.url),'utf8');
    const found:any[]=[];
    function visit(node:any){
      if(!node || typeof node!=='object')return;
      if(node.type==='JSXOpeningElement')found.push(node);
      Object.values(node).forEach(visit);
    }
    visit(parseSync(filename,source,{lang:'tsx'}).program);
    const box=found.find(node=>node.attributes.some((a:any)=>a.name?.name==='id' && a.value?.value===id));
    const fn=box.attributes.find((a:any)=>a.name?.name==='onKeyDown').value.expression;
    let sends=0;
    const callback=vm.runInNewContext(transformSync('key.ts','('+source.slice(fn.start,fn.end)+')',{lang:'ts'}).code,
      { composingText,longText:false,matchingSlash:[],sendMessage:()=>{sends++;},handleSendAnswer:()=>{sends++;} });
    const enter={key:'Enter',shiftKey:false,preventDefault(){}};
    for (const nativeEvent of [{isComposing:true,keyCode:13},{isComposing:false,keyCode:229}]) callback({...enter,nativeEvent});
    assert.equal(sends,0);
    callback({...enter,nativeEvent:{isComposing:false,keyCode:13}});
    assert.equal(sends,1);
  }
});
