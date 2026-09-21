/** SSE reconnect decision for the project stream.

Extracted so the backoff + cursor carry can be unit-tested without a browser.
App.tsx still owns EventSource lifecycle; this only answers "what next?".
*/

export type ConnState = 'idle' | 'connecting' | 'live' | 'offline';

export type SseReconnectPlan =
  | { action: 'ignore' }
  | { action: 'reconnect'; delayMs: number; cursor: number; nextState: 'offline' };

export const SSE_RECONNECT_DELAY_MS = 2000;

/** After EventSource.onerror: close is caller's job; we return when to reopen. */
export function planSseReconnect(opts: {
  /** Last applied event.seq (0 = never received). */
  cursor: number;
  /** True while this stream's effect is still mounted. */
  stillWanted: boolean;
}): SseReconnectPlan {
  if (!opts.stillWanted) return { action: 'ignore' };
  return {
    action: 'reconnect',
    delayMs: SSE_RECONNECT_DELAY_MS,
    cursor: Number.isFinite(opts.cursor) ? Math.max(0, opts.cursor) : 0,
    nextState: 'offline',
  };
}
