import assert from 'node:assert/strict';
import { dagStatusLabel } from './dagStatus.ts';

assert.equal(dagStatusLabel({}).label, 'legacy unknown');
assert.equal(dagStatusLabel({ reviewState: 'queued' }).label, 'review in progress');
assert.equal(
  dagStatusLabel({ deliveryDisposition: 'partial', approvalId: 'approval-1' }).label,
  'approved partial',
);
assert.equal(dagStatusLabel({ deliveryDisposition: 'complete', approvalId: 'approval-1' }).label, 'approved complete');
assert.equal(dagStatusLabel({ hasContradictions: true }).label, 'unresolved contradiction');
assert.equal(
  dagStatusLabel({ checks: { stationary_point: 'supports', identity: 'missing' } }).label,
  'checks pending',
);
console.log('dagStatus tests ok');
