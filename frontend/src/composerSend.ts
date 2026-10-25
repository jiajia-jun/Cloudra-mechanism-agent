/** The composer only answers questions belonging to the selected session. */

export type PendingInteraction = {
  interaction_id?: string | number;
  id?: string | number;
  session_id?: unknown;
};

export function composerInteractionFor<T extends PendingInteraction>(interactions: T[], agentId: string | null): T | undefined {
  return agentId ? interactions.find(interaction => interaction.session_id === agentId) : undefined;
}

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
  activeAgentId: string | null;
  interactions: PendingInteraction[];
}): ComposerSendTarget {
  const content = opts.draft.trim();
  if (!content) return { kind: 'noop', reason: 'empty' };
  if (!opts.hasProject) return { kind: 'noop', reason: 'no_project' };
  if (opts.sending) return { kind: 'noop', reason: 'busy' };
  if (content.startsWith('/')) {
    return { kind: 'slash', command: content };
  }
  const interaction = composerInteractionFor(opts.interactions, opts.activeAgentId);
  if (interaction) {
    const ixnId = interaction.interaction_id ?? interaction.id;
    if (ixnId !== undefined && ixnId !== null && String(ixnId) !== '') {
      return { kind: 'respond', interactionId: ixnId };
    }
  }
  if (!opts.activeAgentId) return { kind: 'spawn_coordinator' };
  return { kind: 'message' };
}
