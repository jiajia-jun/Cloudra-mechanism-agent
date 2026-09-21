import assert from 'node:assert/strict';
import { resolveComposerSendTarget } from './composerSend.ts';

assert.deepEqual(
  resolveComposerSendTarget({
    draft: '  ',
    sending: false,
    hasProject: true,
    hasAgent: true,
    interactions: [],
  }),
  { kind: 'noop', reason: 'empty' },
);

assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'hi',
    sending: false,
    hasProject: false,
    hasAgent: false,
    interactions: [],
  }),
  { kind: 'noop', reason: 'no_project' },
);

assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'hi',
    sending: true,
    hasProject: true,
    hasAgent: true,
    interactions: [],
  }),
  { kind: 'noop', reason: 'busy' },
);

assert.deepEqual(
  resolveComposerSendTarget({
    draft: '/compact',
    sending: false,
    hasProject: true,
    hasAgent: true,
    interactions: [{ id: 1 }],
  }),
  { kind: 'slash', command: '/compact' },
);

// Pending ask_user hijacks Send even when an agent is selected.
assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'ethanol',
    sending: false,
    hasProject: true,
    hasAgent: true,
    interactions: [{ interaction_id: 'ixn_1', id: 99 }],
  }),
  { kind: 'respond', interactionId: 'ixn_1' },
);

// Prefer interaction_id; fall back to id (AttentionDock vs Inspector shapes).
assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'yes',
    sending: false,
    hasProject: true,
    hasAgent: true,
    interactions: [{ id: 42 }],
  }),
  { kind: 'respond', interactionId: 42 },
);

assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'start',
    sending: false,
    hasProject: true,
    hasAgent: false,
    interactions: [],
  }),
  { kind: 'spawn_coordinator' },
);

assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'continue',
    sending: false,
    hasProject: true,
    hasAgent: true,
    interactions: [],
  }),
  { kind: 'message' },
);

console.log('composerSend.test.ts: ok');
