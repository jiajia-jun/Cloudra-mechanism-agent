import type { EventEnvelope } from './types';

/** Merge a live SSE batch into the in-memory window and return events that
 *  fell off the front so the transcript can keep them in the older page. */
export function mergeAndTrimLiveEvents(
  prev: EventEnvelope[],
  batch: EventEnvelope[],
  windowSize: number,
): { live: EventEnvelope[]; spilled: EventEnvelope[] } {
  const seen = new Set(prev.map((e) => e.event_id));
  let next = prev;
  for (const event of batch) {
    if (seen.has(event.event_id)) continue;
    seen.add(event.event_id);
    next = [...next, event];
  }
  if (next === prev) return { live: prev, spilled: [] };
  if (next.length <= windowSize) return { live: next, spilled: [] };
  return {
    live: next.slice(-windowSize),
    spilled: next.slice(0, next.length - windowSize),
  };
}
