import assert from 'node:assert/strict';
import { mergeAndTrimLiveEvents } from './eventWindow.ts';
import type { EventEnvelope } from './types.ts';

function ev(id: string, seq: number): EventEnvelope {
  return {
    event_id: id,
    type: 'agent.message_emitted',
    stream: 'agent',
    project_id: 'p',
    session_id: 's',
    session_seq: seq,
    created_at: '2026-01-01T00:00:00Z',
    data: {},
  } as EventEnvelope;
}

const first = mergeAndTrimLiveEvents([], [ev('a', 1), ev('b', 2)], 2);
assert.deepEqual(first.live.map((e) => e.event_id), ['a', 'b']);
assert.deepEqual(first.spilled, []);

const overflow = mergeAndTrimLiveEvents(first.live, [ev('c', 3)], 2);
assert.deepEqual(overflow.live.map((e) => e.event_id), ['b', 'c']);
assert.deepEqual(overflow.spilled.map((e) => e.event_id), ['a']);

const dup = mergeAndTrimLiveEvents(overflow.live, [ev('c', 3)], 2);
assert.equal(dup.live, overflow.live);
assert.deepEqual(dup.spilled, []);
