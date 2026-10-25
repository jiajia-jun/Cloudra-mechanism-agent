import assert from 'node:assert/strict';
import { composerInteractionFor, resolveComposerSendTarget } from './composerSend.ts';

assert.deepEqual(
  resolveComposerSendTarget({
    draft: '  ',
    sending: false,
    hasProject: true,
    activeAgentId: 'B',
    interactions: [],
  }),
  { kind: 'noop', reason: 'empty' },
);

assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'hi',
    sending: false,
    hasProject: false,
    activeAgentId: null,
    interactions: [],
  }),
  { kind: 'create_project' },
);

assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'new chat', sending: true, hasProject: false, activeAgentId: null, interactions: [],
  }),
  { kind: 'noop', reason: 'busy' },
);

assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'hi',
    sending: true,
    hasProject: true,
    activeAgentId: 'B',
    interactions: [],
  }),
  { kind: 'noop', reason: 'busy' },
);

assert.deepEqual(
  resolveComposerSendTarget({
    draft: '/compact',
    sending: false,
    hasProject: true,
    activeAgentId: 'B',
    interactions: [{ id: 1 }],
  }),
  { kind: 'slash', command: '/compact' },
);

// A pending question from A must not hijack a message addressed to B.
assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'continue B', sending: false, hasProject: true, activeAgentId: 'B',
    interactions: [{ interaction_id: 'ask-A', session_id: 'A' }],
  }),
  { kind: 'message' },
);
// Reply to B's question even when A's question is first in the project inbox.
const pending = [{ interaction_id: 'ask-A', session_id: 'A', prompt: 'Question A' },
  { interaction_id: 'ask-B', session_id: 'B', prompt: 'Question B' }];
assert.equal(composerInteractionFor(pending, 'B')?.prompt, 'Question B');
assert.equal(composerInteractionFor(pending, null), undefined);
assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'answer B', sending: false, hasProject: true, activeAgentId: 'B',
    interactions: pending,
  }),
  { kind: 'respond', interactionId: 'ask-B' },
);
assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'new task', sending: false, hasProject: true, activeAgentId: null,
    interactions: pending,
  }),
  { kind: 'spawn_coordinator' },
);

// Pending ask_user for the selected agent receives its reply.
assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'ethanol',
    sending: false,
    hasProject: true,
    activeAgentId: 'B',
    interactions: [{ interaction_id: 'ixn_1', id: 99, session_id: 'B' }],
  }),
  { kind: 'respond', interactionId: 'ixn_1' },
);

// Prefer interaction_id; fall back to id (AttentionDock vs Inspector shapes).
assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'yes',
    sending: false,
    hasProject: true,
    activeAgentId: 'B',
    interactions: [{ id: 42, session_id: 'B' }],
  }),
  { kind: 'respond', interactionId: 42 },
);

assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'start',
    sending: false,
    hasProject: true,
    activeAgentId: null,
    interactions: [],
  }),
  { kind: 'spawn_coordinator' },
);

assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'continue',
    sending: false,
    hasProject: true,
    activeAgentId: 'B',
    interactions: [],
  }),
  { kind: 'message' },
);

console.log('composerSend.test.ts: ok');
