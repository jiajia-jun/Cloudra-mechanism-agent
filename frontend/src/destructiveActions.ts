/** Copy + confirm gates for irreversible SPA actions.

Keeps destructive wording in one place so UI tests can assert the confirm
prompt without mounting React.
*/

export function archiveProjectConfirm(name: string): string {
  return `Archive project "${name}"?\n\nIt will move to the Archived section; you can restore it later.`;
}

export function hardDeleteProjectConfirm(name: string): string {
  return `Permanently delete project "${name}"?\n\nThis cannot be undone: the conversation history and artifacts are erased. The workspace directory is kept.`;
}

export function cancelAllComputeConfirm(lang: 'zh' | 'en' = 'zh'): string {
  return lang === 'zh'
    ? '取消所有项目中尚未完成的计算？\n\n排队中的任务会立即取消；正在运行的任务会收到停止请求，确认进程退出后才显示“已取消”。'
    : 'Cancel unfinished compute jobs in ALL projects?\n\nQueued jobs are cancelled immediately. Running jobs receive a stop request and are shown as cancelled only after their processes have exited.';
}

/** Format cancel-all API counts the way the sidebar toast does. */
export function formatCancelAllToast(counts: {
  ready_cancelled: number;
  cancel_requested: number;
}, lang: 'zh' | 'en' = 'zh'): string {
  if (counts.cancel_requested > 0) {
    return lang === 'zh'
      ? `已取消 ${counts.ready_cancelled} 个排队任务；已请求停止 ${counts.cancel_requested} 个运行任务，等待确认退出。`
      : `Cancelled ${counts.ready_cancelled} queued jobs; requested stopping ${counts.cancel_requested} running jobs, awaiting confirmed exit.`;
  }
  if (counts.ready_cancelled > 0) {
    return lang === 'zh'
      ? `已取消 ${counts.ready_cancelled} 个排队任务。`
      : `Cancelled ${counts.ready_cancelled} queued jobs.`;
  }
  return lang === 'zh' ? '没有新的计算任务需要取消。' : 'No new compute jobs need cancellation.';
}
