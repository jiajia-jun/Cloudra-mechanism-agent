import type { EventEnvelope } from './types';
import type { StreamView } from './timeline';

const MAX_PAYLOAD_BYTES = 64 * 1024;
const WINDOW_BYTES = 4 * 1024 * 1024;
const eventSizes = new WeakMap<EventEnvelope, number>();

/** Conservative resident-size estimate without a duplicate JSON string. */
function valueBytes(value: unknown, stopAt = Infinity): number {
  const pending = [value];
  let bytes = 0;
  while (pending.length && bytes <= stopAt) {
    const item = pending.pop();
    if (typeof item === 'string') bytes += item.length * 2;
    else if (item && typeof item === 'object') {
      bytes += 32;
      for (const key in item) {
        bytes += key.length * 2 + 8;
        if (bytes > stopAt) break;
        pending.push((item as Record<string, unknown>)[key]);
      }
    } else bytes += 8;
  }
  return bytes;
}

function sizeOf(event: EventEnvelope): number {
  let size = eventSizes.get(event);
  if (size === undefined) {
    size = valueBytes(event);
    eventSizes.set(event, size);
  }
  return size;
}

function forDisplay(event: EventEnvelope, limit = MAX_PAYLOAD_BYTES): EventEnvelope {
  if (event.data._payload_omitted || valueBytes(event.data, limit) <= limit) return event;
  const note = 'Large payload omitted from this view. Open the audit log to load the full event.';
  return { ...event, data: { _payload_omitted: true, content: note, summary: note } };
}

function eventOrder(left: EventEnvelope, right: EventEnvelope): number {
  return left.seq - right.seq
    || (left.session_seq ?? 0) - (right.session_seq ?? 0)
    || left.event_id.localeCompare(right.event_id);
}

function chronological(events: EventEnvelope[]): EventEnvelope[] {
  for (let index = 1; index < events.length; index++) {
    if (eventOrder(events[index - 1], events[index]) > 0) return [...events].sort(eventOrder);
  }
  return events;
}

/** Keep the edge adjacent to the requested cursor so trimmed history can be
 * fetched on the next older/newer click without skipping evidence. */
export function boundEventPage(
  events: EventEnvelope[],
  count: number,
  edge: 'oldest' | 'newest' = 'newest',
  maxBytes = WINDOW_BYTES,
): EventEnvelope[] {
  const ordered = chronological(events);
  const candidates = edge === 'newest' ? ordered.slice(-count).reverse() : ordered.slice(0, count);
  const page: EventEnvelope[] = [];
  let bytes = 0;
  for (const candidate of candidates) {
    const event = forDisplay(candidate, Math.min(MAX_PAYLOAD_BYTES, maxBytes / 2));
    const size = sizeOf(event);
    if (bytes + size > maxBytes) break;
    page.push(event);
    bytes += size;
  }
  return edge === 'newest' ? page.reverse() : page;
}

/** Linear merge for ordered delivery, bounded sorting for reentrant batches.
 * Evicted history stays in the server, never a second cache. */
export function mergeAndTrimLiveEvents(
  prev: EventEnvelope[],
  batch: EventEnvelope[],
  windowSize: number,
): { live: EventEnvelope[]; dropped: boolean } {
  const seen = new Set(prev.map((e) => e.event_id));
  const added: EventEnvelope[] = [];
  for (const event of batch) {
    if (seen.has(event.event_id)) continue;
    seen.add(event.event_id);
    added.push(event);
  }
  if (added.length === 0) return { live: prev, dropped: false };
  const combined = [...prev, ...added];
  const live = boundEventPage(combined, windowSize);
  return { live, dropped: live.length < combined.length };
}

/** Bound pending frames too: browsers suspend animation callbacks in background tabs. */
export class LiveEventBuffer {
  private events: EventEnvelope[] = [];
  private eventIds = new Set<string>();
  private bytes = 0;
  private count: number;
  private maxBytes: number;

  constructor(count: number, maxBytes = WINDOW_BYTES) {
    this.count = count;
    this.maxBytes = maxBytes;
  }

  add(candidate: EventEnvelope): void {
    if (this.eventIds.has(candidate.event_id)) return;
    const event = forDisplay(candidate, Math.min(MAX_PAYLOAD_BYTES, this.maxBytes / 2));
    const last = this.events.at(-1);
    if (!last || eventOrder(last, event) <= 0) this.events.push(event);
    else {
      let before = 0;
      let after = this.events.length;
      while (before < after) {
        const middle = (before + after) >>> 1;
        if (eventOrder(this.events[middle], event) < 0) before = middle + 1;
        else after = middle;
      }
      this.events.splice(before, 0, event);
    }
    this.eventIds.add(event.event_id);
    this.bytes += sizeOf(event);
    while (this.events.length > this.count || this.bytes > this.maxBytes) {
      const removed = this.events.shift()!;
      this.bytes -= sizeOf(removed);
      this.eventIds.delete(removed.event_id);
    }
  }

  drain(): EventEnvelope[] {
    const events = this.events;
    this.clear();
    return events;
  }

  clear(): void {
    this.events = [];
    this.eventIds.clear();
    this.bytes = 0;
  }
}

export function eventMatchesQuery(event: EventEnvelope, query: string): boolean {
  if (event.type.toLowerCase().includes(query)) return true;
  const pending: unknown[] = [event.data];
  while (pending.length) {
    const value = pending.pop();
    if (typeof value === 'string' && value.toLowerCase().includes(query)) return true;
    if ((typeof value === 'number' || typeof value === 'boolean') && String(value).includes(query)) return true;
    if (value && typeof value === 'object') {
      for (const [key, child] of Object.entries(value)) {
        if (key.toLowerCase().includes(query)) return true;
        pending.push(child);
      }
    }
  }
  return false;
}

/** Transient narration has no reason to retain every previous streamed turn.
 * Complete persisted events remain independently retrievable from the server. */
export function boundStreamView(view: StreamView, alreadyOmitted = false): StreamView & { omitted: boolean } {
  const maxText = 65536;
  const maxFrozenBytes = 512 * 1024;
  let omitted = alreadyOmitted || view.streamText.length > maxText
    || (view.streamThinking?.length ?? 0) > maxText || view.frozen.length > 100;
  const frozen: StreamView['frozen'] = [];
  let bytes = 0;
  for (const message of view.frozen.slice(-100).reverse()) {
    const content = message.content.slice(-maxText);
    if (content.length !== message.content.length) omitted = true;
    if (bytes + content.length * 2 > maxFrozenBytes) {
      omitted = true;
      break;
    }
    frozen.push(content === message.content ? message : { ...message, content });
    bytes += content.length * 2;
  }
  return {
    ...view,
    streamText: view.streamText.slice(-maxText),
    streamThinking: view.streamThinking?.slice(-maxText),
    frozen: frozen.reverse(),
    omitted,
  };
}
