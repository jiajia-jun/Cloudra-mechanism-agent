import type { EventEnvelope } from './types';
import { failureNote } from './failureKind.ts';

export interface ToolItem {
  kind: 'tool';
  id: string;
  seq: number;
  name: string;
  argsSummary: string;
  running: boolean;
  ok: boolean | null;
  resultSummary: string;
  durationMs: number | null;
  /** Set when the tool produced an image artifact (artifact_id + image_path in
   * the tool.finished payload); the render layer turns it into a download URL. */
  imageArtifactId?: string;
  imagePath?: string;
  /** Wire/host call identity (tool_call_id); present on requested-started rows. */
  callId?: string;
  /** Set when this call ran inside a JavaScript program. */
  executionId?: string | null;
  /** queued | running | waiting | completed | failed | blocked | cancelled | interrupted */
  status?: string;
  /** not_started | completed | unknown — how far the external effect got. */
  effectState?: string;
}

export interface ProgramItem {
  kind: 'program';
  id: string;
  seq: number;
  executionId: string;
  outerCallId: string | null;
  /** Original source from program.submitted; null when the event was
   * paginated away (explicit source-unavailable shell, never fake code). */
  source: string | null;
  sourceHash: string | null;
  /** running | completed | failed | cancelled | interrupted | unknown
   * (unknown: no program.* event survived, inferred from orphan children). */
  status: string;
  children: ToolItem[];
  outputs: unknown[];
  error: Record<string, unknown> | null;
}

export interface MessageItem {
  kind: 'message';
  id: string;
  seq: number;
  sender: 'user' | 'assistant';
  senderLabel: string;
  content: string;
  pending?: boolean;
  streaming?: boolean;
  /** A transient partial is not a committed conversation message. */
  incomplete?: boolean;
  responseId?: string;
  /** Image attachments on user messages: workspace paths (from the event
   * payload) plus artifact ids when known (optimistic echo / future payloads). */
  imagePaths?: string[];
  imageArtifactIds?: string[];
}
export interface NoteItem {
  kind: 'note';
  id: string;
  seq: number;
  level: 'warn' | 'info' | 'error';
  text: string;
}
export interface ThinkingItem {
  kind: 'thinking';
  id: string;
  seq: number;
  text: string;
  live: boolean;
}
export type TimelineItem = ToolItem | ProgramItem | MessageItem | NoteItem | ThinkingItem;

export interface StreamView {
  streamText: string;
  frozen: MessageItem[];
  responseId?: string;
  streamClosed?: boolean;
  streamThinking?: string;
  streamThinkingLive?: boolean;
  streamThinkingSeq?: number;
}

const MESSAGE_TYPES = new Set(['agent.message_injected', 'agent.message_emitted']);

export function fullText(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function short(text: unknown, max = 80): string {
  const s = typeof text === 'string' ? text : JSON.stringify(text);
  if (!s) return '';
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function freezeStream(view: StreamView, seq: number): StreamView {
  const text = view.streamText;
  if (!text) return { ...view, streamText: '' };
  if (view.frozen.some((m) => view.responseId ? m.responseId === view.responseId : m.content === text)) {
    return { ...view, streamText: '' };
  }
  return {
    ...view,
    streamText: '',
    frozen: [
      ...view.frozen,
      {
        kind: 'message',
        id: `stream-${seq}`,
        seq: seq + 0.4,
        sender: 'assistant',
        senderLabel: 'assistant (incomplete output, not saved)',
        content: text,
        incomplete: true,
        responseId: view.responseId,
      },
    ],
  };
}

/** Live streamText and streamThinking vs events that would otherwise wipe it. */
export function applyStreamEvent(
  view: StreamView,
  event: { type: string; event_id?: string; session_seq?: number | null; data: Record<string, unknown> },
  fallbackSeq = 0,
): StreamView {
  if (event.type === 'llm.chunk') {
    const responseId = typeof event.data.response_id === 'string' ? event.data.response_id : undefined;
    if (view.streamClosed || (responseId && view.responseId && responseId !== view.responseId)) return view;
    view = { ...view, responseId: responseId ?? view.responseId };
    const delta = String(event.data.delta ?? '');
    if (!delta) return view;
    if (event.data.kind === 'reasoning') {
      const currentThinking = view.streamThinking ?? '';
      const baseSeq = (event.session_seq ?? 0) || fallbackSeq;
      const seq = view.streamThinkingSeq || (baseSeq + 0.3);
      return {
        ...view,
        streamThinking: currentThinking + delta,
        streamThinkingLive: true,
        streamThinkingSeq: seq,
      };
    }
    // Content chunks: reasoning has ended
    return {
      ...view,
      streamText: view.streamText + delta,
      streamThinkingLive: false,
    };
  }
  if (event.type === 'agent.thinking') {
    // Authoritative persisted thinking event arrived. Clear live transient streamThinking.
    return {
      ...view,
      streamThinking: '',
      streamThinkingLive: false,
      streamThinkingSeq: 0,
    };
  }
  if (event.type === 'agent.message_injected') {
    if (view.streamThinking) {
      return {
        ...view,
        streamThinkingSeq: (event.session_seq ?? 0) + 0.3,
      };
    }
    return view;
  }
  if (event.type === 'run.started' || event.type === 'run.retry') {
    // 新 run / 新尝试不能沿用上一次未持久化的思考，否则新分片会拼进旧文本。
    return {
      ...freezeStream(view, event.session_seq ?? 0),
      responseId: undefined,
      streamClosed: true,
      streamThinking: '',
      streamThinkingLive: false,
      streamThinkingSeq: 0,
    };
  }
  if (event.type === 'llm.request_started') {
    return {
      ...freezeStream(view, event.session_seq ?? 0),
      responseId: event.event_id,
      streamClosed: false,
      streamThinkingLive: false,
    };
  }
  if (
    event.type === 'run.finished' ||
    event.type === 'agent.cancelled' ||
    event.type === 'llm.failed'
  ) {
    // A provider interruption leaves an explicitly incomplete local fragment,
    // never a fabricated committed assistant message.
    return {
      ...freezeStream(view, event.session_seq ?? 0),
      streamClosed: true,
      streamThinkingLive: false,
    };
  }
  if (event.type === 'agent.message_emitted') {
    const content = String(event.data.content ?? '');
    const responseId = typeof event.data.response_id === 'string' ? event.data.response_id : undefined;
    const current = responseId ? responseId === view.responseId : content === view.streamText;
    return {
      ...view,
      streamText: current ? '' : view.streamText,
      frozen: view.frozen.filter((m) => responseId ? m.responseId !== responseId : m.content !== content),
      streamClosed: current ? true : view.streamClosed,
      streamThinkingLive: current ? false : view.streamThinkingLive,
    };
  }
  return view;
}

export function formatToolArgs(toolName: string, value: unknown): string {
  if (value == null) return '';
  let obj = value;
  if (typeof value === 'string') {
    try {
      obj = JSON.parse(value);
    } catch {
      return value;
    }
  }
  if (typeof obj === 'object' && obj !== null) {
    const data = obj as Record<string, unknown>;
    if (toolName === 'ask_user') {
      const q = String(data.question ?? data.prompt ?? '');
      if (data.default_answer) {
        return `${q} (default: ${String(data.default_answer)})`;
      }
      return q || fullText(value);
    }
    if (toolName === 'bashtools' || toolName === 'bash') {
      return String(data.command ?? data.cmd ?? fullText(value));
    }
    if (
      toolName === 'text_writer' || toolName === 'edit_file' || toolName === 'text_reader' ||
      toolName === 'write' || toolName === 'edit' || toolName === 'read'
    ) {
      return String(data.filepath ?? data.path ?? fullText(value));
    }
    if (toolName === 'submit_compute_job') {
      const parts = [data.job_type, data.input_file || data.name].filter(Boolean);
      return parts.length > 0 ? parts.join(' · ') : fullText(value);
    }
  }
  return fullText(value);
}

export function formatToolResult(toolName: string, value: unknown): string {
  if (value == null) return '';
  let obj = value;
  if (typeof value === 'string') {
    try {
      obj = JSON.parse(value);
    } catch {
      return value;
    }
  }
  if (typeof obj === 'object' && obj !== null) {
    const data = obj as Record<string, unknown>;
    if (toolName === 'ask_user') {
      if (data.rejected) {
        return `Rejected${data.reason ? `: ${String(data.reason)}` : ''}`;
      }
      if (data.answer != null && data.answer !== '') {
        return `Answer: ${String(data.answer)}`;
      }
      if (data.message) return String(data.message);
    }
    if (data.result != null && typeof data.result === 'string') {
      return data.result;
    }
    if (data.message != null && typeof data.message === 'string') {
      return data.message;
    }
  }
  return fullText(value);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

/** Pull an image artifact reference out of a tool.finished payload: either
 * top-level (`artifact_id`/`image_path`) or nested in the raw `result`
 * (object or JSON string). */
function extractToolImage(data: Record<string, unknown>): { artifactId?: string; imagePath?: string } {
  let artifactId = typeof data.artifact_id === 'string' && data.artifact_id ? data.artifact_id : undefined;
  let imagePath = typeof data.image_path === 'string' && data.image_path ? data.image_path : undefined;
  let result: unknown = data.result;
  if (typeof result === 'string') {
    try {
      result = JSON.parse(result);
    } catch {
      result = undefined;
    }
  }
  if (result && typeof result === 'object') {
    const r = result as Record<string, unknown>;
    if (!artifactId && typeof r.artifact_id === 'string' && r.artifact_id) artifactId = r.artifact_id;
    if (!imagePath && typeof r.image_path === 'string' && r.image_path) imagePath = r.image_path;
  }
  return { artifactId, imagePath };
}

export function buildTimeline(events: EventEnvelope[], pendingUserMessages: MessageItem[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  const openTools = new Map<string, ToolItem>();
  // JavaScript program projection: children are ToolItems grouped under one
  // ProgramItem by execution_id; requested creates a queued row, started
  // updates it, the raw-result event never adds a row, finished settles it.
  const programs = new Map<string, ProgramItem>();
  const programChildren = new Map<string, ToolItem>(); // tool_call_id -> child row
  const orphanChildren = new Map<string, ToolItem[]>(); // execution_id -> rows awaiting a program event
  const seenEventIds = new Set<string>();
  // compaction.started shows a live note that compaction.finished rewrites in
  // place (keyed by run); a crash in between is settled by run termination.
  const openCompactions = new Map<string, NoteItem>();
  const sorted = [...events].sort((a, b) => (a.session_seq ?? a.seq) - (b.session_seq ?? b.seq));

  const ensureProgram = (executionId: string, id: string, seq: number): ProgramItem => {
    let program = programs.get(executionId);
    if (program) return program;
    program = {
      kind: 'program',
      id,
      seq,
      executionId,
      outerCallId: null,
      source: null,
      sourceHash: null,
      status: 'running',
      children: [],
      outputs: [],
      error: null,
    };
    programs.set(executionId, program);
    items.push(program);
    const orphans = orphanChildren.get(executionId) ?? [];
    for (const orphan of orphans) program.children.push(orphan);
    orphanChildren.delete(executionId);
    return program;
  };

  const attachChild = (executionId: string, child: ToolItem) => {
    const program = programs.get(executionId);
    if (program) {
      program.children.push(child);
      return;
    }
    const bucket = orphanChildren.get(executionId) ?? [];
    bucket.push(child);
    orphanChildren.set(executionId, bucket);
  };

  const settleRow = (
    row: ToolItem,
    data: Record<string, unknown>,
    name: string,
  ) => {
    const status = typeof data.status === 'string' ? data.status : '';
    row.running = false;
    row.ok = status ? status === 'completed' : Boolean(data.is_success);
    row.status = status || (data.is_success ? 'completed' : 'failed');
    row.effectState = typeof data.effect_state === 'string' ? data.effect_state : undefined;
    row.resultSummary = formatToolResult(name, data.result_summary);
    row.durationMs = typeof data.duration_ms === 'number' ? data.duration_ms : null;
    const image = extractToolImage(data);
    row.imageArtifactId = image.artifactId;
    row.imagePath = image.imagePath;
  };

  for (const event of sorted) {
    if (seenEventIds.has(event.event_id)) continue; // duplicate SSE/replay rows
    seenEventIds.add(event.event_id);
    const seq = event.session_seq ?? event.seq;
    if (MESSAGE_TYPES.has(event.type)) {
      const sender = String(event.data.sender ?? 'agent');
      if (event.type === 'agent.message_injected' &&
          ['system', 'completion_gate', 'background_quiescence'].includes(sender)) {
        items.push({ kind: 'note', id: event.event_id, seq, level: 'info',
          text: `${sender}: ${fullText(event.data.content)}` });
        continue;
      }
      const imagePaths = stringList(event.data.images);
      const imageArtifactIds = stringList(event.data.image_artifact_ids);
      items.push({
        kind: 'message',
        id: event.event_id,
        seq,
        sender: event.type === 'agent.message_injected' && (sender === 'user' || sender === 'system') ? 'user' : 'assistant',
        senderLabel: sender,
        content: String(event.data.content ?? ''),
        responseId: typeof event.data.response_id === 'string' ? event.data.response_id : undefined,
        imagePaths: imagePaths.length > 0 ? imagePaths : undefined,
        imageArtifactIds: imageArtifactIds.length > 0 ? imageArtifactIds : undefined,
      });
    } else if (event.type === 'agent.thinking') {
      items.push({
        kind: 'thinking',
        id: event.event_id,
        seq,
        text: String(event.data.content ?? ''),
        live: false,
      });
    } else if (event.type === 'tool.requested') {
      const toolName = String(event.data.tool_name ?? 'tool');
      const callId = String(event.data.tool_call_id ?? event.event_id);
      const executionId = event.data.execution_id ? String(event.data.execution_id) : null;
      const item: ToolItem = {
        kind: 'tool',
        id: event.event_id,
        seq,
        name: toolName,
        argsSummary: formatToolArgs(toolName, event.data.arguments_summary),
        running: false,
        ok: null,
        resultSummary: '',
        durationMs: null,
        callId,
        executionId,
        status: 'queued',
      };
      if (executionId) {
        programChildren.set(callId, item);
        attachChild(executionId, item);
      } else {
        openTools.set(callId, item);
        items.push(item);
      }
    } else if (event.type === 'tool.started') {
      const toolName = String(event.data.tool_name ?? 'tool');
      const callId = String(event.data.tool_call_id ?? event.event_id);
      const executionId = event.data.execution_id ? String(event.data.execution_id) : null;
      const open = executionId ? programChildren.get(callId) : openTools.get(callId);
      if (open) {
        open.running = true;
        open.status = 'running';
        if (!open.argsSummary) {
          open.argsSummary = formatToolArgs(toolName, event.data.arguments_summary);
        }
        continue;
      }
      const item: ToolItem = {
        kind: 'tool',
        id: event.event_id,
        seq,
        name: toolName,
        argsSummary: formatToolArgs(toolName, event.data.arguments_summary),
        running: true,
        ok: null,
        resultSummary: '',
        durationMs: null,
        callId,
        executionId,
        status: 'running',
      };
      if (executionId) {
        programChildren.set(callId, item);
        attachChild(executionId, item);
      } else {
        openTools.set(callId, item);
        items.push(item);
      }
    } else if (event.type === 'tool.finished') {
      const callId = String(event.data.tool_call_id ?? '');
      const toolName = String(event.data.tool_name ?? 'tool');
      const executionId = event.data.execution_id ? String(event.data.execution_id) : null;
      const open = executionId ? programChildren.get(callId) : openTools.get(callId);
      if (open) {
        settleRow(open, event.data, open.name);
        if (executionId) programChildren.delete(callId);
        else openTools.delete(callId);
      } else {
        const row: ToolItem = {
          kind: 'tool',
          id: event.event_id,
          seq,
          name: toolName,
          argsSummary: '',
          running: false,
          ok: null,
          resultSummary: '',
          durationMs: null,
          callId,
          executionId,
        };
        settleRow(row, event.data, toolName);
        if (executionId) attachChild(executionId, row);
        else items.push(row);
      }
    } else if (event.type === 'program.submitted') {
      const executionId = String(event.data.execution_id ?? '');
      if (!executionId) continue;
      const program = ensureProgram(executionId, event.event_id, seq);
      program.source = typeof event.data.code === 'string' ? event.data.code : null;
      program.sourceHash = event.data.source_hash ? String(event.data.source_hash) : null;
      program.outerCallId = event.data.outer_tool_call_id
        ? String(event.data.outer_tool_call_id)
        : null;
    } else if (event.type === 'program.started') {
      const executionId = String(event.data.execution_id ?? '');
      if (!executionId) continue;
      const program = ensureProgram(executionId, event.event_id, seq);
      if (!program.outerCallId && event.data.outer_tool_call_id) {
        program.outerCallId = String(event.data.outer_tool_call_id);
      }
    } else if (event.type === 'program.output') {
      const executionId = String(event.data.execution_id ?? '');
      if (!executionId) continue;
      const program = ensureProgram(executionId, event.event_id, seq);
      program.outputs.push(event.data.value);
    } else if (event.type === 'program.finished') {
      const executionId = String(event.data.execution_id ?? '');
      if (!executionId) continue;
      const program = ensureProgram(executionId, event.event_id, seq);
      program.status = String(event.data.status ?? 'unknown');
      program.error =
        event.data.error && typeof event.data.error === 'object'
          ? (event.data.error as Record<string, unknown>)
          : null;
    } else if (event.type === 'compaction.started') {
      const item: NoteItem = {
        kind: 'note',
        id: event.event_id,
        seq,
        level: 'info',
        text: 'Compacting context…',
      };
      openCompactions.set(String(event.run_id ?? event.event_id), item);
      items.push(item);
    } else if (event.type === 'compaction.finished') {
      const key = String(event.run_id ?? '');
      const open = openCompactions.get(key);
      const d = event.data;
      let level: NoteItem['level'] = 'info';
      let text: string;
      if (d.error) {
        level = 'warn';
        text = `Context compaction failed: ${short(d.error, 160)}`;
      } else if (d.compacted) {
        const why =
          d.trigger === 'context_overflow'
            ? ' — context window overflow'
            : d.trigger === 'stop'
              ? ' — after last user/schedule message'
              : '';
        text = `Context compacted (${String(d.before_messages)} → ${String(d.after_messages)} messages${why})`;
      } else if (d.reason === 'nothing_to_compact') {
        text = 'Context already short — nothing to compact';
      } else {
        // 拒替换的其它原因（结构校验失败 / 摘要不缩短 / 合并容量不足 / 候选
        // 期间投影已变）各有诊断价值，不再一律说成"上下文本来就短"。
        const reason = typeof d.reason === 'string' && d.reason ? d.reason : '';
        text = reason
          ? `Context left unchanged — compaction refused (${reason})`
          : 'Context left unchanged — compaction refused';
      }
      if (open) {
        open.text = text;
        open.level = level;
        openCompactions.delete(key);
      } else {
        items.push({ kind: 'note', id: event.event_id, seq, level, text });
      }
    } else if (
      event.type === 'run.finished' ||
      event.type === 'agent.cancelled' ||
      event.type === 'run.started' ||
      event.type === 'run.retry'
    ) {
      for (const open of openTools.values()) {
        if (!open.running) continue;
        open.running = false;
        open.ok = false;
        open.status = 'interrupted';
        open.resultSummary = 'interrupted';
      }
      openTools.clear();
      for (const child of programChildren.values()) {
        if (child.running || child.status === 'queued') {
          child.running = false;
          child.ok = false;
          child.status = 'interrupted';
          child.resultSummary = 'interrupted';
        }
      }
      programChildren.clear();
      for (const program of programs.values()) {
        if (program.status === 'running') program.status = 'interrupted';
      }
      for (const pending of openCompactions.values()) {
        pending.text = 'Context compaction interrupted';
      }
      openCompactions.clear();
      // 失败的 run 按结构化 failure_kind 给出下一步（只认枚举，不解析 error 文本）。
      if (event.type === 'run.finished') {
        const failure = failureNote(event.data);
        if (failure) {
          items.push({
            kind: 'note',
            id: event.event_id,
            seq,
            level: failure.level,
            text: failure.text,
          });
        }
      }
    } else if (event.type === 'agent.completion_gate') {
      const action = String(event.data.action ?? 'unknown');
      const reason = fullText(event.data.reason);
      items.push({
        kind: 'note', id: event.event_id, seq,
        level: action === 'continue_work' ? 'warn' : 'info',
        text: `Completion gate (${action}): ${reason}`,
      });
    } else if (event.type === 'agent.warning' || event.type === 'llm.failed' || event.type === 'tool.blocked') {
      items.push({
        kind: 'note',
        id: event.event_id,
        seq,
        level: 'warn',
        text: fullText(event.data.message ?? event.data.error ?? event.type),
      });
    }
  }
  // Orphan children whose program events were paginated away still get an
  // explicit source-unavailable shell — never dropped, never fake code.
  for (const [executionId, children] of orphanChildren) {
    if (children.length === 0) continue;
    const unfinished = children.some((child) => child.running || child.status === 'queued');
    items.push({
      kind: 'program',
      id: `program-shell-${executionId}`,
      seq: children[0].seq - 0.1,
      executionId,
      outerCallId: null,
      source: null,
      sourceHash: null,
      status: unfinished ? 'running' : 'unknown',
      children,
      outputs: [],
      error: null,
    });
  }
  items.sort((a, b) => a.seq - b.seq);
  return [...items, ...pendingUserMessages];
}
