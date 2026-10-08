import assert from 'node:assert/strict';
import * as windows from './eventWindow.ts';
import { applyStreamEvent, type StreamView } from './timeline.ts';
const { mergeAndTrimLiveEvents } = windows;
import type { EventEnvelope } from './types.ts';

function ev(id: string, seq: number): EventEnvelope {
  return {
    event_id: id,
    type: 'agent.message_emitted',
    stream: 'agent',
    project_id: 'p',
    session_id: 's',
    seq,
    session_seq: seq,
    created_at: '2026-01-01T00:00:00Z',
    data: {},
  } as EventEnvelope;
}

const first = mergeAndTrimLiveEvents([], [ev('a', 1), ev('b', 2)], 2);
assert.deepEqual(first.live.map((e) => e.event_id), ['a', 'b']);
assert.equal(first.dropped, false);

const overflow = mergeAndTrimLiveEvents(first.live, [ev('c', 3)], 2);
assert.deepEqual(overflow.live.map((e) => e.event_id), ['b', 'c']);
assert.equal(overflow.dropped, true);
assert.equal('spilled' in overflow, false, 'evicted live history must not be handed to an unbounded cache');

const dup = mergeAndTrimLiveEvents(overflow.live, [ev('c', 3)], 2);
assert.equal(dup.live, overflow.live);
assert.equal(dup.dropped, false);

// A hidden tab can receive many complete event bursts before its next frame.
const buffer = new windows.LiveEventBuffer(500);
for (let seq = 1; seq <= 20000; seq++) buffer.add(ev(`buffer-${seq}`, seq));
const buffered = buffer.drain();
assert.equal(buffered.length, 500);
assert.equal(buffered[0].session_seq, 19501);
assert.equal(buffered.at(-1)?.session_seq, 20000);
assert.equal(buffer.drain().length, 0);

const huge = { ...ev('huge', 10), data: { content: 'x'.repeat(10 * 1024 * 1024) } };
const compacted = windows.boundEventPage([huge], 500);
assert.equal(compacted.length, 1);
assert.equal(compacted[0].event_id, huge.event_id);
assert.equal(compacted[0].data._payload_omitted, true);
assert.equal(Object.values(compacted[0].data).includes(huge.data.content), false);
assert.ok(String(compacted[0].data.content).includes('full event'));

// A bounded historical page must keep the adjacent edge: backwards pages keep
// their newest entries, forwards pages keep their oldest, so evicted events
// remain reachable on the very next cursor query.
const history = Array.from({ length: 1000 }, (_, i) => ev(`history-${i + 1}`, i + 1));
const backwards = windows.boundEventPage(history, 200, 'newest');
const forwards = windows.boundEventPage(history, 200, 'oldest');
assert.equal(backwards[0].session_seq, 801);
assert.equal(backwards.at(-1)?.session_seq, 1000);
assert.equal(forwards[0].session_seq, 1);
assert.equal(forwards.at(-1)?.session_seq, 200);

// Payload accounting traverses values directly; it must not retain serialized
// copies of a complete context or tool-result JSON string.
const stringify = JSON.stringify;
JSON.stringify = () => { throw new Error('payload accounting must not serialize'); };
try {
  const payloads = Array.from({ length: 500 }, (_, i) => ({
    ...ev(`payload-${i}`, i + 1), data: { result: 'y'.repeat(60 * 1024) },
  }));
  const bounded = windows.boundEventPage(payloads, 500);
  assert.equal(bounded.length, 500);
  assert.ok(bounded.every((event) => event.data._payload_omitted === true));
} finally {
  JSON.stringify = stringify;
}

const byteBuffer = new windows.LiveEventBuffer(500, 1024);
for (let seq = 1; seq <= 500; seq++) byteBuffer.add({ ...ev(`bytes-${seq}`, seq), data: { content: 'z'.repeat(100) } });
assert.ok(byteBuffer.drain().length < 10, 'buffer must enforce a byte budget as well as a count');

let readFields = 0;
const broadPayload: Record<string, unknown> = {};
for (let index = 0; index < 10000; index++) {
  Object.defineProperty(broadPayload, `field-${index}`, {
    enumerable: true, get: () => { readFields++; return 'field value'; },
  });
}
windows.boundEventPage([{ ...ev('broad', 1), data: broadPayload }], 500);
assert.ok(readFields < 10000, 'size accounting must stop before reading a whole oversized object');
assert.equal(windows.eventMatchesQuery({ ...ev('search', 1), data: { result: { count: 314 } } }, '314'), true);

const reentrant = mergeAndTrimLiveEvents([ev('r1', 1)], [ev('r3', 3), ev('r2', 2)], 2);
assert.deepEqual(reentrant.live.map((event) => event.session_seq), [2, 3]);
const lateHistory = mergeAndTrimLiveEvents([ev('h10', 10), ev('h11', 11)], [ev('h2', 2)], 2);
assert.deepEqual(lateHistory.live.map((event) => event.session_seq), [10, 11]);
const reentrantBuffer = new windows.LiveEventBuffer(2);
reentrantBuffer.add(ev('q3', 3));
reentrantBuffer.add(ev('q1', 1));
reentrantBuffer.add(ev('q2', 2));
assert.deepEqual(reentrantBuffer.drain().map((event) => event.session_seq), [2, 3]);

let stream: StreamView & { omitted?: boolean } = { streamText: '', frozen: [] };
for (let turn = 1; turn <= 1000; turn++) {
  stream = windows.boundStreamView(applyStreamEvent(stream, {
    type: 'llm.chunk', data: { kind: 'content', delta: `transient-${turn} ` + 't'.repeat(10000) },
  }), Boolean(stream.omitted));
  stream = windows.boundStreamView(applyStreamEvent(stream, {
    type: 'llm.request_started', session_seq: turn, data: {},
  }), Boolean(stream.omitted));
}
assert.ok(stream.frozen.length <= 100);
assert.ok(stream.frozen.reduce((bytes, message) => bytes + message.content.length * 2, 0) <= 512 * 1024);
assert.ok(stream.frozen.at(-1)?.content.startsWith('transient-1000'));
assert.equal(stream.omitted, true);
stream = windows.boundStreamView({ ...stream, streamText: 'x'.repeat(10 * 1024 * 1024) + 'LATEST_CONTENT' });
assert.ok(stream.streamText.length <= 65536);
assert.ok(stream.streamText.endsWith('LATEST_CONTENT'));
assert.equal(stream.omitted, true);
const independent = windows.boundStreamView({ streamText: 'new agent', frozen: [] });
assert.equal(independent.omitted, false, 'switching agents must not carry the old omission flag');
