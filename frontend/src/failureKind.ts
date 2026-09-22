/**
 * run 失败分类的展示口径（评审 5.10）：`run.finished.failure_kind` 枚举 →
 * 「发生了什么 + 下一步该做什么」。
 *
 * 只按枚举分流——不解析 `error` 文本、不做字符串匹配。原始 error 仍留在审计
 * 日志/事件里供人阅读；分类缺失或未知时返回 null（不猜）。
 */

export interface FailureNote {
  level: 'warn' | 'error';
  text: string;
}

const NOTES: Record<string, FailureNote> = {
  provider_permanent: {
    level: 'error',
    text:
      "Run failed: the provider permanently rejected this request. Check the agent's model, " +
      'base_url and API key — retrying the same request will not help.',
  },
  provider_transient_exhausted: {
    level: 'error',
    text:
      'Run failed: the provider kept failing until the retry budget ran out. Check provider ' +
      'status and rate limits, then send a message to resume.',
  },
  event_persistence: {
    level: 'error',
    text:
      'Run failed: a durable event write failed, so the event stream and the world may have ' +
      'diverged. Check the data directory (disk space/permissions) before resuming — the ' +
      'turn is deliberately not replayed.',
  },
  pipeline_internal: {
    level: 'error',
    text:
      'Run failed: internal harness error — not a provider or science failure. The raw error ' +
      'is in the audit log; send a message to resume, and report it if it repeats.',
  },
  completion_no_progress: {
    level: 'warn',
    text:
      'Run ended as failed: the completion gate rejected repeated exits without new progress. ' +
      'Resolve the open gaps it listed (or declare a partial delivery), then send a new message.',
  },
  runtime_interrupted: {
    level: 'warn',
    text:
      'Run interrupted by a process restart. Nothing was replayed; send a message to resume ' +
      'with fresh instructions.',
  },
};

export function failureNote(data: Record<string, unknown> | null | undefined): FailureNote | null {
  if (!data || data.outcome !== 'failed') return null;
  const kind = data.failure_kind;
  if (typeof kind !== 'string') return null;
  return NOTES[kind] ?? null;
}
