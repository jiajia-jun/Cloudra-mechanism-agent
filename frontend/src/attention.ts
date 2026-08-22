/**
 * attention — cross-project pending approval / ask_user aggregation.
 *
 * The per-project Inspector and ask-banner only cover the ACTIVE project.
 * These pure helpers flatten every polled project's pending rows into one
 * uniform list (for the floating AttentionDock) and diff consecutive polls
 * so desktop notifications fire only for genuinely new requests.
 */

export interface ProjectPending {
  name: string;
  approvals: Array<Record<string, unknown>>;
  interactions: Array<Record<string, unknown>>;
}

export interface PendingAttention {
  /** Stable identity across polls: `${projectId}:${kind}:${id}`. */
  key: string;
  projectId: string;
  projectName: string;
  kind: 'approval' | 'interaction';
  id: string;
  sessionId: string;
  /** agent name / tool name for approvals, agent name for interactions. */
  title: string;
  /** risk_summary for approvals, the ask_user prompt for interactions. */
  body: string;
  createdAt: string;
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : v == null ? '' : String(v);
}

export function collectPending(perProject: Map<string, ProjectPending>): PendingAttention[] {
  const out: PendingAttention[] = [];
  for (const [projectId, pending] of perProject) {
    for (const row of pending.approvals) {
      const id = str(row.id ?? row.approval_id);
      if (!id) continue;
      out.push({
        key: `${projectId}:approval:${id}`,
        projectId,
        projectName: pending.name,
        kind: 'approval',
        id,
        sessionId: str(row.session_id),
        title: str(row.agent_name),
        body: str(row.tool_name) + (row.risk_summary ? ` — ${str(row.risk_summary)}` : ''),
        createdAt: str(row.created_at),
      });
    }
    for (const row of pending.interactions) {
      const id = str(row.interaction_id ?? row.id);
      if (!id) continue;
      out.push({
        key: `${projectId}:interaction:${id}`,
        projectId,
        projectName: pending.name,
        kind: 'interaction',
        id,
        sessionId: str(row.session_id),
        title: str(row.agent_id),
        body: str(row.prompt ?? row.message),
        createdAt: str(row.created_at),
      });
    }
  }
  // ISO timestamps sort lexically; oldest request first.
  out.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  return out;
}

/**
 * Items whose key is not in `seen`.  Pure: the caller owns the seen set
 * (first poll seeds it silently so reloading the page does not re-alert
 * for long-pending requests).
 */
export function diffNewItems(items: PendingAttention[], seen: ReadonlySet<string>): PendingAttention[] {
  return items.filter((item) => !seen.has(item.key));
}
