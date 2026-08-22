import assert from 'node:assert/strict';
import { collectPending, diffNewItems, type ProjectPending } from './attention.ts';

function project(partial: Partial<ProjectPending> = {}): ProjectPending {
  return { name: 'proj', approvals: [], interactions: [], ...partial };
}

// NOTE: rows are declared as standalone consts — node --experimental-strip-types
// (amaro) misparses an object literal with a string value nested inside
// `new Map([[..., f({ a: [{ k: 'v' }] })]])`.

const approvalRow: Record<string, unknown> = {
  id: 'apv-1',
  session_id: 's1',
  agent_name: 'coordinator',
  tool_name: 'bash_command',
  risk_summary: 'rm -rf build/',
  created_at: '2026-08-22T10:00:00',
};
const interactionRow: Record<string, unknown> = {
  interaction_id: 'ixn-9',
  session_id: 's2',
  agent_id: 'researcher',
  prompt: 'Which solvent?',
  created_at: '2026-08-22T09:00:00',
};

const perProject = new Map<string, ProjectPending>();
perProject.set('p1', project({ name: 'Alpha', approvals: [approvalRow] }));
perProject.set('p2', project({ name: 'Beta', interactions: [interactionRow] }));

const items = collectPending(perProject);
assert.equal(items.length, 2);
// Sorted by created_at: the older interaction comes first.
assert.equal(items[0].key, 'p2:interaction:ixn-9');
assert.equal(items[0].body, 'Which solvent?');
assert.equal(items[1].key, 'p1:approval:apv-1');
assert.equal(items[1].body, 'bash_command — rm -rf build/');
assert.equal(items[1].projectName, 'Alpha');

// Rows without an id are dropped rather than keyed on "undefined".
const noIdMap = new Map<string, ProjectPending>();
const noIdRow: Record<string, unknown> = { session_id: 's' };
noIdMap.set('p3', project({ approvals: [noIdRow] }));
assert.equal(collectPending(noIdMap).length, 0);

// diffNewItems: only unseen keys surface, and it stays pure.
const seen = new Set<string>(['p2:interaction:ixn-9']);
const fresh = diffNewItems(items, seen);
assert.equal(fresh.length, 1);
assert.equal(fresh[0].key, 'p1:approval:apv-1');
assert.equal(seen.size, 1, 'diffNewItems must not mutate the seen set');

// After a decision the row leaves the next poll — and never re-alerts.
for (const item of items) seen.add(item.key);
const afterDecision = new Map<string, ProjectPending>();
afterDecision.set('p1', project({ name: 'Alpha' }));
afterDecision.set('p2', perProject.get('p2')!);
const remaining = collectPending(afterDecision);
assert.equal(remaining.length, 1);
assert.equal(diffNewItems(remaining, seen).length, 0);

console.log('attention tests passed');
