import assert from 'node:assert/strict';
import {
  applyStreamEvent,
  buildTimeline,
  type MessageItem,
  type NoteItem,
  type StreamView,
  type ToolItem,
} from './timeline.ts';
import type { EventEnvelope } from './types.ts';

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

/* ------------------------------------------------------- image attachments */

function ev(type: string, sessionSeq: number, data: Record<string, unknown>): EventEnvelope {
  return {
    stream: 'agent',
    event_id: `e-${sessionSeq}-${type}`,
    project_id: 'p1',
    session_id: 's1',
    run_id: null,
    seq: sessionSeq,
    session_seq: sessionSeq,
    type,
    data,
    created_at: '2026-01-01T00:00:00Z',
  };
}

// agent.message_injected carries image paths for the user bubble.
const withImages = buildTimeline(
  [ev('agent.message_injected', 1, { sender: 'user', content: 'look at this', images: ['/ws/uploads/a.png'] })],
  [],
);
const userMsg = withImages[0] as MessageItem;
assert.equal(userMsg.kind, 'message');
assert.deepEqual(userMsg.imagePaths, ['/ws/uploads/a.png']);

// tool.finished with artifact_id + image_path attaches the image to the tool
// item — both for the paired (started→finished) and standalone shapes.
const paired = buildTimeline(
  [
    ev('tool.started', 2, { tool_name: 'molecule_drawer', tool_call_id: 'c1' }),
    ev('tool.finished', 3, {
      tool_name: 'molecule_drawer',
      tool_call_id: 'c1',
      is_success: true,
      artifact_id: 'art-1',
      image_path: '/ws/mol.png',
    }),
  ],
  [],
);
const pairedTool = paired[0] as ToolItem;
assert.equal(pairedTool.kind, 'tool');
assert.equal(pairedTool.imageArtifactId, 'art-1');
assert.equal(pairedTool.imagePath, '/ws/mol.png');

const standalone = buildTimeline(
  [
    ev('tool.finished', 4, {
      tool_name: 'molecule_drawer',
      is_success: true,
      result: { artifact_id: 'art-2', image_path: '/ws/mol2.png' },
    }),
  ],
  [],
);
const soloTool = standalone[0] as ToolItem;
assert.equal(soloTool.imageArtifactId, 'art-2', 'artifact ref nested in result payload is found');
assert.equal(soloTool.imagePath, '/ws/mol2.png');

console.log('timeline.images ok');

/* ----------------------------------------------------- compaction notes */

// compaction.started shows a live hint; compaction.finished rewrites the same
// row in place (paired by run_id), so the timeline holds a single note.
const compItems = buildTimeline(
  [
    { ...ev('compaction.started', 5, {}), run_id: 'r1' },
    {
      ...ev('compaction.finished', 6, {
        compacted: true,
        before_messages: 42,
        after_messages: 7,
        trigger: 'manual',
      }),
      run_id: 'r1',
    },
  ],
  [],
);
assert.equal(compItems.length, 1);
const compNote = compItems[0] as NoteItem;
assert.equal(compNote.kind, 'note');
assert.equal(compNote.level, 'info');
assert.equal(compNote.text, 'Context compacted (42 → 7 messages)');

// An overflow-triggered compaction says why it happened.
const overflow = buildTimeline(
  [
    {
      ...ev('compaction.finished', 7, {
        compacted: true,
        before_messages: 50,
        after_messages: 11,
        trigger: 'context_overflow',
      }),
      run_id: 'r2',
    },
  ],
  [],
);
assert.match((overflow[0] as NoteItem).text, /context window overflow/);

// A failed compaction warns instead of passing silently.
const failedComp = buildTimeline(
  [{ ...ev('compaction.finished', 8, { compacted: false, error: 'provider down' }), run_id: 'r3' }],
  [],
);
assert.equal((failedComp[0] as NoteItem).level, 'warn');
assert.match((failedComp[0] as NoteItem).text, /provider down/);

// A crash between started and finished settles the live hint.
const interrupted = buildTimeline(
  [
    { ...ev('compaction.started', 9, {}), run_id: 'r4' },
    { ...ev('run.finished', 10, { outcome: 'failed' }), run_id: 'r4' },
  ],
  [],
);
assert.equal((interrupted[0] as NoteItem).text, 'Context compaction interrupted');

console.log('timeline.compaction ok');
