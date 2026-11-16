import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { parseSync, transformSync } from 'rolldown/utils';
import { mergeProjectSnapshot } from './projectState.ts';
import type { Project } from './types.ts';

// Exercise the real snapshot write. An earlier view can return after a local
// PATCH acknowledgement but before its SSE event has reached this browser.
const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8');
const nodes: any[] = [];
function visit(node: any) {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) { node.forEach(visit); return; }
  nodes.push(node); Object.values(node).forEach(visit);
}
visit(parseSync('App.tsx', source, { lang: 'tsx' }).program);
const declaration = nodes.find(node => node.type === 'VariableDeclarator' && node.id?.name === 'updateProjectView');
const callback = declaration.init.arguments[0];
const fresh = { id: 'p', updated_at: '2026-11-16T00:00:00.000002Z', settings: { orchestration_mode: 'dag_guided' } };
let projects = [fresh];
const apply = vm.runInNewContext(transformSync('snapshot.ts', `(${source.slice(callback.start, callback.end)});`, { lang: 'ts' }).code, {
  mergeProjectSnapshot, projectStateThroughRef: { current: new Map([['p', 100]]) },
  setProjects: (update: (p: typeof projects) => typeof projects) => { projects = update(projects); },
});
apply({ project: { ...fresh, updated_at: '2026-11-16T00:00:00.000001Z', settings: { orchestration_mode: 'standard' } }, cursor: 100 });
assert.equal(projects[0].settings.orchestration_mode, 'dag_guided', 'a stale view must not undo a local settings receipt');
for (const older of ['2026-11-16T00:00:00Z', '2026-11-16T00:00:00+00:00', '2026-11-16T00:00:00.000001Z']) {
  assert.equal(mergeProjectSnapshot(fresh as Project, { ...fresh, updated_at: older } as Project), fresh,
    'older HTTP receipts must not undo newer SSE state, even within the same millisecond');
}
console.log('project snapshot freshness passed');
