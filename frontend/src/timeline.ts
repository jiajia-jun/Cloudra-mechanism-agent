import type { EventEnvelope } from './types';

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
  /** Image attachments on user messages: workspace paths (from the event
   * payload) plus artifact ids when known (optimistic echo / future payloads). */
  imagePaths?: string[];
  imageArtifactIds?: string[];
}
export interface NoteItem {
  kind: 'note';
  id: string;
  seq: number;
  level: 'warn' | 'info';
  text: string;
}
export interface ThinkingItem {
  kind: 'thinking';
  id: string;
  seq: number;
  text: string;
  live: boolean;
}
export type TimelineItem = ToolItem | MessageItem | NoteItem | ThinkingItem;

export interface StreamView {
  streamText: string;
  frozen: MessageItem[];
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
  if (view.frozen.some((m) => m.content === text)) {
    return { ...view, streamText: '' };
  }
  return {
    streamText: '',
    frozen: [
      ...view.frozen,
      {
        kind: 'message',
        id: `stream-${seq}`,
        seq: seq + 0.4,
        sender: 'assistant',
        senderLabel: 'assistant',
        content: text,
      },
    ],
  };
}

/** Live streamText vs events that would otherwise wipe it. */
export function applyStreamEvent(
  view: StreamView,
  event: { type: string; session_seq?: number | null; data: Record<string, unknown> },
): StreamView {
  if (event.type === 'llm.chunk') {
    const delta = String(event.data.delta ?? '');
    if (!delta || event.data.kind === 'reasoning') return view;
    return { ...view, streamText: view.streamText + delta };
  }
  if (
    event.type === 'llm.request_started' ||
    event.type === 'run.finished' ||
    event.type === 'llm.failed'
  ) {
    return freezeStream(view, event.session_seq ?? 0);
  }
  if (event.type === 'agent.message_emitted') {
    const content = String(event.data.content ?? '');
    return {
      streamText: '',
      frozen: view.frozen.filter((m) => m.content !== content),
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
  // compaction.started shows a live note that compaction.finished rewrites in
  // place (keyed by run); a crash in between is settled by run termination.
  const openCompactions = new Map<string, NoteItem>();
  const sorted = [...events].sort((a, b) => (a.session_seq ?? a.seq) - (b.session_seq ?? b.seq));
  for (const event of sorted) {
    const seq = event.session_seq ?? event.seq;
    if (MESSAGE_TYPES.has(event.type)) {
      const sender = String(event.data.sender ?? 'agent');
      const imagePaths = stringList(event.data.images);
      const imageArtifactIds = stringList(event.data.image_artifact_ids);
      items.push({
        kind: 'message',
        id: event.event_id,
        seq,
        sender: event.type === 'agent.message_injected' && (sender === 'user' || sender === 'system') ? 'user' : 'assistant',
        senderLabel: sender,
        content: String(event.data.content ?? ''),
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
    } else if (event.type === 'tool.started') {
      const toolName = String(event.data.tool_name ?? 'tool');
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
      };
      openTools.set(String(event.data.tool_call_id ?? event.event_id), item);
      items.push(item);
    } else if (event.type === 'tool.finished') {
      const callId = String(event.data.tool_call_id ?? '');
      const toolName = String(event.data.tool_name ?? 'tool');
      const open = openTools.get(callId);
      const ok = Boolean(event.data.is_success);
      const image = extractToolImage(event.data);
      if (open) {
        open.running = false;
        open.ok = ok;
        open.resultSummary = formatToolResult(open.name, event.data.result_summary);
        open.durationMs = typeof event.data.duration_ms === 'number' ? event.data.duration_ms : null;
        open.imageArtifactId = image.artifactId;
        open.imagePath = image.imagePath;
        openTools.delete(callId);
      } else {
        items.push({
          kind: 'tool',
          id: event.event_id,
          seq,
          name: toolName,
          argsSummary: '',
          running: false,
          ok,
          resultSummary: formatToolResult(toolName, event.data.result_summary),
          durationMs: typeof event.data.duration_ms === 'number' ? event.data.duration_ms : null,
          imageArtifactId: image.artifactId,
          imagePath: image.imagePath,
        });
      }
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
      } else {
        text = 'Context already short — nothing to compact';
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
        open.resultSummary = 'interrupted';
      }
      openTools.clear();
      for (const pending of openCompactions.values()) {
        pending.text = 'Context compaction interrupted';
      }
      openCompactions.clear();
    } else if (event.type === 'agent.warning' || event.type === 'llm.failed' || event.type === 'tool.blocked') {
      items.push({
        kind: 'note',
        id: event.event_id,
        seq,
        level: 'warn',
        text: short(event.data.message ?? event.data.error ?? event.type, 200),
      });
    }
  }
  return [...items, ...pendingUserMessages];
}
