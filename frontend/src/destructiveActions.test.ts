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
assert.equal(
  cancelAllComputeConfirm(),
  '取消所有项目中尚未完成的计算？\n\n排队中的任务会立即取消；正在运行的任务会收到停止请求，确认进程退出后才显示“已取消”。',
);

assert.equal(
  formatCancelAllToast({
    ready_cancelled: 2,
    cancel_requested: 3,
  }),
  '已取消 2 个排队任务；已请求停止 3 个运行任务，等待确认退出。',
);
assert.equal(formatCancelAllToast({ ready_cancelled: 2, cancel_requested: 0 }), '已取消 2 个排队任务。');
assert.equal(formatCancelAllToast({ ready_cancelled: 0, cancel_requested: 0 }), '没有新的计算任务需要取消。');
assert.equal(
  cancelAllComputeConfirm('en'),
  'Cancel unfinished compute jobs in ALL projects?\n\nQueued jobs are cancelled immediately. Running jobs receive a stop request and are shown as cancelled only after their processes have exited.',
);
assert.equal(
  formatCancelAllToast({ ready_cancelled: 2, cancel_requested: 3 }, 'en'),
  'Cancelled 2 queued jobs; requested stopping 3 running jobs, awaiting confirmed exit.',
);
assert.equal(formatCancelAllToast({ ready_cancelled: 2, cancel_requested: 0 }, 'en'), 'Cancelled 2 queued jobs.');
assert.equal(formatCancelAllToast({ ready_cancelled: 0, cancel_requested: 0 }, 'en'), 'No new compute jobs need cancellation.');

console.log('destructiveActions.test.ts: ok');
