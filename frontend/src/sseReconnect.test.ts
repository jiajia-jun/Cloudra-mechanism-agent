import assert from 'node:assert/strict';
import { SSE_RECONNECT_DELAY_MS, planSseReconnect } from './sseReconnect.ts';

assert.deepEqual(
  planSseReconnect({ cursor: 42, stillWanted: true }),
  { action: 'reconnect', delayMs: SSE_RECONNECT_DELAY_MS, cursor: 42, nextState: 'offline' },
);

assert.deepEqual(
  planSseReconnect({ cursor: 0, stillWanted: true }),
  { action: 'reconnect', delayMs: 2000, cursor: 0, nextState: 'offline' },
);

assert.deepEqual(
  planSseReconnect({ cursor: 99, stillWanted: false }),
  { action: 'ignore' },
);

// Negative/NaN cursor clamps to 0 so reconnect never sends garbage.
{
  const plan = planSseReconnect({ cursor: -1, stillWanted: true });
  assert.equal(plan.action, 'reconnect');
  if (plan.action === 'reconnect') assert.equal(plan.cursor, 0);
}
{
  const plan = planSseReconnect({ cursor: Number.NaN, stillWanted: true });
  assert.equal(plan.action, 'reconnect');
  if (plan.action === 'reconnect') assert.equal(plan.cursor, 0);
}

console.log('sseReconnect.test.ts: ok');
