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

export function cancelAllComputeConfirm(): string {
  return (
    'Cancel ALL unfinished compute jobs?\n\nQueued jobs are cancelled immediately; Slurm jobs are scancelled via their poll loop; local jobs are ledger-cancelled (processes are never killed).'
  );
}

/** Format cancel-all API counts the way the sidebar toast does. */
export function formatCancelAllToast(counts: {
  ready_cancelled: number;
  slurm_cancel_requested: number;
  local_cancelled: number;
}): string {
  return (
    `Compute jobs cancelled: ${counts.ready_cancelled} queued, ` +
    `${counts.slurm_cancel_requested} slurm (cancel requested), ` +
    `${counts.local_cancelled} local`
  );
}
