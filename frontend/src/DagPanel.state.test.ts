import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import { parseSync, transformSync } from 'rolldown/utils';

const source = readFileSync(new URL('./DagPanel.tsx', import.meta.url), 'utf8');
const tree = parseSync('DagPanel.tsx', source, { lang: 'tsx' }).program;
const nodes: any[] = [];
function visit(node: any) {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) { node.forEach(visit); return; }
  nodes.push(node);
  Object.values(node).forEach(visit);
}
visit(tree);
function evaluate(node: any, globals: Record<string, unknown>) {
  assert.ok(node, 'the actual component callback must exist');
  return vm.runInNewContext(transformSync('callback.ts', `(${source.slice(node.start, node.end)})`, { lang: 'ts' }).code, globals);
}
const applyNode = nodes.find(node => node.type === 'FunctionDeclaration' && node.id?.name === 'applyOps');
const loadNode = nodes.find(node => node.type === 'VariableDeclarator' && node.id?.name === 'load')!.init.arguments[0];

test('saving a displayed DAG keeps its revision and reports a concurrent edit instead of overwriting it', async () => {
  let submitted: any;
  const errors: Error[] = [];
  let refreshed = 0;
  const apply = evaluate(applyNode, {
    project: { id: 'p' }, data: { delivery: { revision: 1 }, projection: { revisions: { delivery: 2 } } },
    api: {
      dagProjection: async () => ({ revisions: { delivery: 2 } }),
      dagMutations: async (_id: string, operations: unknown[], base: object) => {
        submitted = { operations, base };
        return (base as { delivery: number }).delivery === 2 ? { accepted: true } : { accepted: false, rejection_code: 'stale_revision' };
      },
    },
    setBusy() {}, onToast() {}, onError: (error: Error) => errors.push(error),
    onChanged: () => { refreshed++; }, load: async () => {},
  });
  await apply([{ op: 'update_node', graph: 'delivery', node_id: 'a', changes: { label: 'renamed', smiles: 'C' } }], '', 'saved');
  assert.equal(submitted.base.delivery, 1, 'the displayed graph, not a newly fetched projection, owns the edit');
  assert.equal(errors.length, 1);
  assert.match(errors[0].message, /stale_revision/);
  assert.equal(refreshed, 0);
});

test('successful graph mutations notify the owner of the products and object menus', async () => {
  let refreshed = 0;
  const apply = evaluate(applyNode, {
    project: { id: 'p' }, data: { delivery: { revision: 1 } },
    api: { dagProjection: async () => ({ revisions: { delivery: 1 } }), dagMutations: async () => ({ accepted: true }) },
    setBusy() {}, onToast() {}, onError: (error: Error) => { throw error; },
    onChanged: () => { refreshed++; }, load: async () => {},
  });
  await apply([{ op: 'add_node', graph: 'delivery', node: { node_id: 'new', label: 'New' } }], '', 'saved');
  assert.equal(refreshed, 1, 'the parent cache must be invalidated after the server accepts the mutation');
});

test('a late DAG response cannot replace a newer complete load', async () => {
  let release!: (value: object) => void;
  const first = new Promise(resolve => { release = resolve; });
  let reads = 0;
  const committed: any[] = [];
  const load = evaluate(loadNode, {
    project: { id: 'p', settings: { orchestration_mode: 'dag_guided' } },
    loadVersion: { current: 0 },
    api: {
      dagDelivery: () => ++reads === 1 ? first : Promise.resolve({ mode: 'dag_guided', graph: { revision: 2 } }),
      dagReport: async () => null, dagHistory: async () => [], dagProjection: async () => null,
      dagReviews: async () => null, dagDraft: async () => null,
    },
    setData: (data: unknown) => committed.push(data),
  });
  const pending = load();
  await load();
  release({ mode: 'dag_guided', graph: { revision: 1 } });
  await pending;
  assert.equal(committed.length, 1);
  assert.equal(committed[0].delivery.revision, 2);
});

test('file evidence opens by its canonical reference and does not become a pathname', () => {
  const click = nodes.find(node => node.type === 'ArrowFunctionExpression'
    && node.body?.type === 'CallExpression' && node.body.callee.name === 'onOpenMolecule'
    && source.slice(node.start, node.end).includes('activeStage.ref.ref_type'));
  const ref = { ref_type: 'file', ref_id: 'ev_registered', content_hash: 'sha256:snapshot' };
  let opened: unknown;
  evaluate(click, { activeStage: { ref }, onOpenMolecule: (value: unknown) => { opened = value; } })();
  assert.deepEqual(structuredClone(opened), { file_evidence: ref });
});

test('switching the same project from guided to record invalidates its DAG load callback', () => {
  const hook = nodes.find(node => node.type === 'VariableDeclarator' && node.id?.name === 'load')!.init;
  let cached: { dependencies: unknown[]; callback: unknown } | undefined;
  const useCallback = (callback: unknown, dependencies: unknown[]) => {
    if (!cached || dependencies.some((value, index) => !Object.is(value, cached!.dependencies[index]))) {
      cached = { dependencies, callback };
    }
    return cached.callback;
  };
  const first = evaluate(hook, { useCallback, project: { id: 'same', settings: { orchestration_mode: 'dag_guided' } } });
  const changed = evaluate(hook, { useCallback, project: { id: 'same', settings: { orchestration_mode: 'dag_record' } } });
  assert.notEqual(changed, first, 'the mode change must start a fresh read even when the project ID stays the same');
});

test('unmounting cancels a pending DAG commit through the actual effect cleanup', async () => {
  const effect = nodes.find(node => node.type === 'CallExpression' && node.callee.name === 'useEffect'
    && node.arguments[1]?.elements?.some((item: any) => item.name === 'load'))!;
  const loadVersion = { current: 0 };
  let release!: (value: object) => void;
  const deferred = new Promise(resolve => { release = resolve; });
  const committed: unknown[] = [];
  const load = evaluate(loadNode, {
    project: { id: 'p' }, loadVersion,
    api: {
      dagDelivery: () => deferred,
      dagReport: async () => null, dagHistory: async () => [], dagProjection: async () => null,
      dagReviews: async () => null, dagDraft: async () => null,
    },
    setData: (data: unknown) => committed.push(data),
  });
  let pending: Promise<void> | undefined;
  const cleanup = evaluate(effect.arguments[0], {
    load: () => (pending = load()), loadVersion, onError: (error: Error) => { throw error; },
  })();
  cleanup();
  release({ mode: 'dag_guided', graph: { revision: 1 } });
  await pending;
  assert.equal(committed.length, 0);
});

test('the ResearchPanel graph callback invalidates the actual products effect', () => {
  const research = readFileSync(new URL('./ResearchPanel.tsx', import.meta.url), 'utf8');
  const found: any[] = [];
  function collect(node: any) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { node.forEach(collect); return; }
    found.push(node); Object.values(node).forEach(collect);
  }
  collect(parseSync('ResearchPanel.tsx', research, { lang: 'tsx' }).program);
  const child = found.find(node => node.type === 'JSXOpeningElement' && node.name.name === 'DagPanel');
  const callbackName = child.attributes.find((attribute: any) => attribute.name?.name === 'onChanged')?.value.expression.name;
  const callback = found.find(node => node.type === 'VariableDeclarator' && node.id?.name === callbackName)?.init;
  assert.ok(callback, 'the child mutation callback must be connected to the parent');
  const effect = found.find(node => node.type === 'CallExpression' && node.callee.name === 'useEffect'
    && research.slice(node.start, node.end).includes('workbenchApi.products'));
  let refresh = 0;
  const dependencies = () => vm.runInNewContext(research.slice(effect.arguments[1].start, effect.arguments[1].end), {
    project: { id: 'p' }, refresh, refreshVersion: 0,
  });
  const before = dependencies();
  const changed = vm.runInNewContext(transformSync('callback.ts', `(${research.slice(callback.start, callback.end)})`, { lang: 'ts' }).code, {
    useCallback: (fn: unknown) => fn,
    setRefresh: (update: (value: number) => number) => { refresh = update(refresh); },
  });
  changed();
  assert.notDeepEqual(structuredClone(dependencies()), structuredClone(before));
});
