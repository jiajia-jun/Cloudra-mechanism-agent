import assert from 'node:assert/strict';
import { mergeAgentSnapshot, mergeProjectAgentSnapshot } from './agentState.ts';
import type { Agent } from './types.ts';

const stopped = { id: 'a', state: 'cancelled', current_run: null, current_task: 'stopped',
  completion: null, display_name: 'latest name' } as Agent;
const running = { ...stopped, state: 'running', current_run: { run_id: 'new-run', started_at: '' },
  current_task: 'new task', display_name: 'cached name' };

assert.deepEqual(mergeAgentSnapshot(running, stopped, false), stopped,
  'a fresh read must correct the cached running state');
const advanced = mergeAgentSnapshot(running, stopped, true);
assert.equal(advanced.state, 'running');
assert.equal(advanced.current_run?.run_id, 'new-run');
assert.equal(advanced.current_task, 'new task');
assert.equal(advanced.display_name, 'latest name');

const worker = { ...running, id: 'worker' };
const spawned = { ...running, id: 'spawned-after-snapshot' };
const merged = mergeProjectAgentSnapshot([running, worker, spawned], [stopped, { ...stopped, id: 'worker' }],
  20, new Map([['a', 10], ['worker', 21], [spawned.id, 22]]));
assert.equal(merged.find(a => a.id === 'a')?.state, 'cancelled');
assert.equal(merged.find(a => a.id === 'worker')?.state, 'running', 'newer background-agent SSE must win');
assert.ok(merged.some(a => a.id === spawned.id), 'a late snapshot must retain a newly spawned agent');
console.log('agentState snapshots ok');
