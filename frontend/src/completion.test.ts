import assert from 'node:assert/strict';
import { completionChipFor, stateBadgeText } from './completion.ts';

assert.equal(
  completionChipFor({ run_id: 'r1', run_outcome: 'succeeded', completion_basis: 'scope_completed', verification_label: 'scope_completed' })?.tone,
  'warn',
);

// 只有证据门禁确认过的结题才显示为已验证完成。
assert.equal(
  completionChipFor({ run_id: 'r1', run_outcome: 'succeeded', completion_basis: 'dag_verified', verification_label: 'verified' })
    ?.label,
  'verified complete',
);
assert.equal(
  completionChipFor({ run_id: 'r1', run_outcome: 'succeeded', completion_basis: 'supervisor_approved', verification_label: 'partial' })
    ?.label,
  'partial delivery',
);
assert.equal(
  completionChipFor({ run_id: 'r1', run_outcome: 'succeeded', completion_basis: 'supervisor_supported', verification_label: 'supervisor_reviewed' })
    ?.label,
  'Supervisor-reviewed delivery',
);
assert.equal(
  completionChipFor({ run_id: 'r1', run_outcome: 'succeeded', completion_basis: 'supervisor_supported', verification_label: 'supervisor_reviewed' })
    ?.detail,
  'The delivery passed its coverage gate using Supervisor judgment; this is not independent scientific verification.',
);
assert.equal(
  completionChipFor({ run_id: 'r1', run_outcome: 'succeeded', completion_basis: 'partial_recorded', verification_label: 'partial' })
    ?.tone,
  'warn',
);
// 普通（standard）自述结束：绝不显示成 verified complete。
const declared = completionChipFor({
  run_id: 'r1',
  run_outcome: 'succeeded',
  completion_basis: 'declared',
  verification_label: 'unverified',
});
assert.equal(declared?.label, 'not independently verified');
assert.notEqual(declared?.tone, 'ok');

// failed / cancelled 即使带 unverified 也不出芯片——那不是「自述结题」。
assert.equal(
  completionChipFor({
    run_id: 'r1',
    run_outcome: 'failed',
    completion_basis: null,
    verification_label: 'unverified',
  }),
  null,
);
assert.equal(
  completionChipFor({
    run_id: 'r1',
    run_outcome: 'cancelled',
    completion_basis: null,
    verification_label: 'unverified',
  }),
  null,
);

// 没有依据 / 未知标签：什么都不显示，不猜。
assert.equal(completionChipFor(null), null);
assert.equal(completionChipFor(undefined), null);
assert.equal(
  completionChipFor({ run_id: null, run_outcome: null, completion_basis: null, verification_label: 'bogus' as never }),
  null,
);

// 状态徽标：succeeded 只是「结束了」。
assert.equal(stateBadgeText('succeeded'), 'ended');
assert.equal(stateBadgeText('running'), 'running');
assert.equal(stateBadgeText('failed'), 'failed');

console.log('completion tests ok');
