import assert from 'node:assert/strict';
import {
  applyStreamEvent,
  buildTimeline,
  formatToolArgs,
  type MessageItem,
  type NoteItem,
  type ProgramItem,
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

/* ------------------------------------------------------- stream thinking */

const thinkChunk1 = applyStreamEvent(view(), {
  type: 'llm.chunk',
  session_seq: 1,
  data: { kind: 'reasoning', delta: 'Let me think about ' },
});
assert.equal(thinkChunk1.streamThinking, 'Let me think about ');
assert.equal(thinkChunk1.streamThinkingLive, true);

const thinkChunk2 = applyStreamEvent(thinkChunk1, {
  type: 'llm.chunk',
  session_seq: 1,
  data: { kind: 'reasoning', delta: 'reaction mechanism.' },
});
assert.equal(thinkChunk2.streamThinking, 'Let me think about reaction mechanism.');
assert.equal(thinkChunk2.streamThinkingLive, true);

// Other events (e.g. state_changed) do not interrupt streaming thinking
const stateEv = applyStreamEvent(thinkChunk2, {
  type: 'agent.state_changed',
  session_seq: 2,
  data: { to: 'running' },
});
assert.equal(stateEv.streamThinking, 'Let me think about reaction mechanism.');
assert.equal(stateEv.streamThinkingLive, true);

// When content arrives, thinking live flag transitions to false
const contentChunk = applyStreamEvent(thinkChunk2, {
  type: 'llm.chunk',
  session_seq: 3,
  data: { kind: 'content', delta: 'Here is the answer.' },
});
assert.equal(contentChunk.streamThinking, 'Let me think about reaction mechanism.');
assert.equal(contentChunk.streamThinkingLive, false);
assert.equal(contentChunk.streamText, 'Here is the answer.');

// Authoritative agent.thinking clears transient streamThinking
const afterThinkingPersist = applyStreamEvent(contentChunk, {
  type: 'agent.thinking',
  session_seq: 4,
  data: { content: 'Let me think about reaction mechanism.' },
});
assert.equal(afterThinkingPersist.streamThinking, '');
assert.equal(afterThinkingPersist.streamThinkingLive, false);

console.log('timeline.stream-thinking ok');

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

// Stop-triggered compaction names the user/schedule boundary.
const afterStop = buildTimeline(
  [
    {
      ...ev('compaction.finished', 7.5, {
        compacted: true,
        before_messages: 20,
        after_messages: 4,
        trigger: 'stop',
      }),
      run_id: 'r2b',
    },
  ],
  [],
);
assert.match((afterStop[0] as NoteItem).text, /last user\/schedule message/);

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

/* ----------------------------------------------------- tool arg summaries */

assert.equal(
  formatToolArgs('read', { path: 'src/foo.py' }),
  'src/foo.py',
  'live read tool summarizes path',
);
assert.equal(
  formatToolArgs('text_reader', { filepath: 'legacy/bar.py' }),
  'legacy/bar.py',
  'historical text_reader events still summarize filepath',
);

console.log('timeline.tool-args ok');

/* ------------------------------------------------------ program projection */

// One ProgramItem groups its child ToolItems by execution_id; requested
// creates a queued row, started updates it, the raw-result event adds no
// row, finished settles it, and duplicate program.finished events are no-ops.
{
  const submitted = ev('program.submitted', 1, {
    execution_id: 'exec1', outer_tool_call_id: 'wire1', code: 'text(1);', source_hash: 'h',
  });
  const requestedA = ev('tool.requested', 2, {
    tool_call_id: 'a', tool_name: 'echo', arguments_summary: { value: 3 }, execution_id: 'exec1',
  });
  const startedA = ev('tool.started', 3, {
    tool_call_id: 'a', tool_name: 'echo', arguments_summary: { value: 3 }, execution_id: 'exec1',
  });
  const requestedB = ev('tool.requested', 4, {
    tool_call_id: 'b', tool_name: 'echo', arguments_summary: { value: 4 }, execution_id: 'exec1',
  });
  const finishedA = ev('tool.finished', 5, {
    tool_call_id: 'a', tool_name: 'echo', execution_id: 'exec1', status: 'completed',
    effect_state: 'completed', is_success: true, result_summary: 'ok', duration_ms: 2,
    raw_result_event_id: 'raw-a', error: null,
  });
  const startedB = ev('tool.started', 6, {
    tool_call_id: 'b', tool_name: 'echo', arguments_summary: { value: 4 }, execution_id: 'exec1',
  });
  const finishedB = ev('tool.finished', 7, {
    tool_call_id: 'b', tool_name: 'echo', execution_id: 'exec1', status: 'failed',
    effect_state: 'completed', is_success: false, result_summary: 'nope', duration_ms: 1,
    raw_result_event_id: 'raw-b', error: null,
  });
  const programFinished = ev('program.finished', 8, {
    execution_id: 'exec1', outer_tool_call_id: 'wire1', status: 'completed',
    duration_ms: 9, error: null, calls: [],
  });
  const items = buildTimeline(
    [submitted, requestedA, startedA, requestedB, finishedA, startedB, finishedB, programFinished, programFinished],
    [],
  );
  const program = items.find((item) => item.kind === 'program') as ProgramItem | undefined;
  assert.equal(program?.kind, 'program');
  if (program?.kind === 'program') {
    assert.equal(program.children.length, 2);
    assert.deepEqual(program.children.map((child) => child.callId), ['a', 'b']);
    assert.equal(program.status, 'completed');
    assert.equal(program.source, 'text(1);');
    assert.deepEqual(program.children.map((child) => child.status), ['completed', 'failed']);
    assert.equal(program.children[0].effectState, 'completed');
  }
  assert.equal(items.filter((item) => item.kind === 'tool').length, 0);
  console.log('timeline.program-basic ok');
}

// Queued/running/waiting/blocked child states and program outputs.
{
  const items = buildTimeline(
    [
      ev('program.submitted', 1, { execution_id: 'e1', outer_tool_call_id: 'w', code: 'x', source_hash: 'h' }),
      ev('tool.requested', 2, { tool_call_id: 'q', tool_name: 'echo', arguments_summary: {}, execution_id: 'e1' }),
      ev('tool.requested', 3, { tool_call_id: 'r', tool_name: 'echo', arguments_summary: {}, execution_id: 'e1' }),
      ev('tool.started', 4, { tool_call_id: 'r', tool_name: 'echo', arguments_summary: {}, execution_id: 'e1' }),
      ev('tool.requested', 5, { tool_call_id: 'w1', tool_name: 'submit_compute_job', arguments_summary: {}, execution_id: 'e1' }),
      ev('tool.finished', 6, {
        tool_call_id: 'w1', tool_name: 'submit_compute_job', execution_id: 'e1',
        status: 'waiting', effect_state: 'not_started', is_success: false,
        result_summary: 'needs approval', duration_ms: 0, raw_result_event_id: null,
        error: { code: 'policy_wait', message: 'needs approval' },
      }),
      ev('tool.requested', 7, { tool_call_id: 'blk', tool_name: 'bash', arguments_summary: {}, execution_id: 'e1' }),
      ev('tool.finished', 8, {
        tool_call_id: 'blk', tool_name: 'bash', execution_id: 'e1',
        status: 'blocked', effect_state: 'not_started', is_success: false,
        result_summary: 'denied', duration_ms: 0, raw_result_event_id: null,
        error: { code: 'policy_blocked', message: 'denied' },
      }),
      ev('program.output', 9, { execution_id: 'e1', output_index: 0, value: { n: 1 } }),
    ],
    [],
  );
  const program = items.find((item) => item.kind === 'program') as ProgramItem;
  assert.deepEqual(program.children.map((child) => child.status), ['queued', 'running', 'waiting', 'blocked']);
  assert.deepEqual(program.outputs, [{ n: 1 }]);
  console.log('timeline.program-states ok');
}

// Orphan rows (raw result without a requested, children whose program events
// were paginated away) get a source-unavailable shell — never dropped.
{
  const items = buildTimeline(
    [
      ev('tool.finished', 3, {
        tool_call_id: 'orphan', tool_name: 'echo', execution_id: 'gone',
        status: 'completed', effect_state: 'completed', is_success: true,
        result_summary: 'ok', duration_ms: 1, raw_result_event_id: 'raw', error: null,
      }),
    ],
    [],
  );
  const program = items.find((item) => item.kind === 'program') as ProgramItem;
  assert.equal(program.executionId, 'gone');
  assert.equal(program.source, null);
  assert.equal(program.status, 'unknown');
  assert.equal(program.children.length, 1);
  assert.equal(program.children[0].status, 'completed');
  assert.equal(items.filter((item) => item.kind === 'tool').length, 0);
  console.log('timeline.program-orphan ok');
}

// Two interleaved executions stay grouped per execution_id; duplicate SSE
// deliveries (same event_id) do not double rows.
{
  const requestedA1 = ev('tool.requested', 2, { tool_call_id: 'a1', tool_name: 'echo', arguments_summary: {}, execution_id: 'eA' });
  const events = [
    ev('program.submitted', 1, { execution_id: 'eA', outer_tool_call_id: 'wA', code: 'a', source_hash: 'hA' }),
    requestedA1,
    requestedA1, // duplicate SSE frame
    ev('program.submitted', 3, { execution_id: 'eB', outer_tool_call_id: 'wB', code: 'b', source_hash: 'hB' }),
    ev('tool.requested', 4, { tool_call_id: 'b1', tool_name: 'echo', arguments_summary: {}, execution_id: 'eB' }),
    ev('tool.finished', 5, {
      tool_call_id: 'a1', tool_name: 'echo', execution_id: 'eA', status: 'completed',
      effect_state: 'completed', is_success: true, result_summary: 'ok', duration_ms: 1,
      raw_result_event_id: null, error: null,
    }),
    ev('program.finished', 6, { execution_id: 'eA', outer_tool_call_id: 'wA', status: 'completed', duration_ms: 5, error: null, calls: [] }),
  ];
  const items = buildTimeline(events, []);
  const programs = items.filter((item) => item.kind === 'program') as ProgramItem[];
  assert.equal(programs.length, 2);
  const [a, b] = programs;
  assert.equal(a.executionId, 'eA');
  assert.deepEqual(a.children.map((c) => c.callId), ['a1']);
  assert.equal(a.status, 'completed');
  assert.equal(b.executionId, 'eB');
  assert.deepEqual(b.children.map((c) => c.callId), ['b1']);
  assert.equal(b.children[0].status, 'queued');
  console.log('timeline.program-interleaved ok');
}

// Run termination interrupts still-open programs and their child rows.
{
  const items = buildTimeline(
    [
      ev('program.submitted', 1, { execution_id: 'e1', outer_tool_call_id: 'w', code: 'x', source_hash: 'h' }),
      ev('tool.requested', 2, { tool_call_id: 'a', tool_name: 'echo', arguments_summary: {}, execution_id: 'e1' }),
      ev('tool.started', 3, { tool_call_id: 'a', tool_name: 'echo', arguments_summary: {}, execution_id: 'e1' }),
      ev('run.finished', 4, { outcome: 'failed' }),
    ],
    [],
  );
  const program = items.find((item) => item.kind === 'program') as ProgramItem;
  assert.equal(program.status, 'interrupted');
  assert.equal(program.children[0].status, 'interrupted');
  assert.equal(program.children[0].ok, false);
  console.log('timeline.program-interrupted ok');
}
