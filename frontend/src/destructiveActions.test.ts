import assert from 'node:assert/strict';
import {
  archiveProjectConfirm,
  cancelAllComputeConfirm,
  formatCancelAllToast,
  hardDeleteProjectConfirm,
} from './destructiveActions.ts';

assert.match(archiveProjectConfirm('Demo'), /Archive project "Demo"/);
assert.match(hardDeleteProjectConfirm('Demo'), /Permanently delete project "Demo"/);
assert.match(hardDeleteProjectConfirm('x'), /cannot be undone/);
assert.match(cancelAllComputeConfirm(), /never killed/);
assert.match(cancelAllComputeConfirm(), /scancelled/);

assert.equal(
  formatCancelAllToast({
    ready_cancelled: 2,
    slurm_cancel_requested: 1,
    local_cancelled: 3,
  }),
  'Compute jobs cancelled: 2 queued, 1 slurm (cancel requested), 3 local',
);

console.log('destructiveActions.test.ts: ok');
