import assert from 'node:assert/strict';
import { applyStreamEvent, type StreamView } from './timeline.ts';

function view(partial: Partial<StreamView> = {}): StreamView {
  return { streamText: '', frozen: [], ...partial };
}

// Streaming narration must survive the next tool round: llm.request_started
// used to wipe streamText, and the bubble lived only at the bottom of the
// chat — so the moment tools landed, the content vanished.

const streamed = applyStreamEvent(view(), {
  type: 'llm.chunk',
  session_seq: 0,
  data: { kind: 'content', delta: 'Let me check the file.' },
});
assert.equal(streamed.streamText, 'Let me check the file.');

const afterRequest = applyStreamEvent(streamed, {
  type: 'llm.request_started',
  session_seq: 10,
  data: {},
});
assert.equal(afterRequest.streamText, '', 'live bubble yields to a frozen timeline row');
assert.equal(afterRequest.frozen.length, 1);
assert.equal(afterRequest.frozen[0].content, 'Let me check the file.');
assert.ok(afterRequest.frozen[0].seq > 10 && afterRequest.frozen[0].seq < 11);

const afterTools = applyStreamEvent(afterRequest, {
  type: 'tool.started',
  session_seq: 13,
  data: { tool_name: 'text_reader' },
});
assert.equal(afterTools.frozen[0].content, 'Let me check the file.', 'tools must not swallow frozen content');

const afterPersist = applyStreamEvent(afterTools, {
  type: 'agent.message_emitted',
  session_seq: 12,
  data: { content: 'Let me check the file.' },
});
assert.equal(afterPersist.frozen.length, 0, 'persisted event replaces the freeze so the row is not duplicated');
assert.equal(afterPersist.streamText, '');

console.log('timeline.stream-commit ok');
