/** Composer send routing: pending ask_user hijacks Send away from messages. */

export type PendingInteraction = {
  interaction_id?: string | number;
  id?: string | number;
};

export type ComposerSendTarget =
  | { kind: 'slash'; command: string }
  | { kind: 'respond'; interactionId: string | number }
  | { kind: 'spawn_coordinator' }
  | { kind: 'message' }
  | { kind: 'noop'; reason: 'empty' | 'busy' | 'no_project' };

/**
 * Decide where a composer Send goes. Mirrors App.tsx sendMessage branching
 * (slash commands are detected here but handled by the caller).
 */
export function resolveComposerSendTarget(opts: {
  draft: string;
  sending: boolean;
  hasProject: boolean;
  hasAgent: boolean;
  interactions: PendingInteraction[];
}): ComposerSendTarget {
  const content = opts.draft.trim();
  if (!content) return { kind: 'noop', reason: 'empty' };
  if (!opts.hasProject) return { kind: 'noop', reason: 'no_project' };
  if (opts.sending) return { kind: 'noop', reason: 'busy' };
  if (content.startsWith('/')) {
    return { kind: 'slash', command: content };
  }
  if (opts.interactions.length > 0) {
    const first = opts.interactions[0];
    const ixnId = first.interaction_id ?? first.id;
    if (ixnId !== undefined && ixnId !== null && String(ixnId) !== '') {
      return { kind: 'respond', interactionId: ixnId };
    }
  }
  if (!opts.hasAgent) return { kind: 'spawn_coordinator' };
  return { kind: 'message' };
}
