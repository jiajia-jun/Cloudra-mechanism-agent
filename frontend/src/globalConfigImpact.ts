import type { Agent, Project, RuntimeConfigSlot } from './types';

export type ConfigSlot = 'coordinator' | 'follower';
export type MissingField = 'model' | 'base_url' | 'api_key';
export type ImpactDecision = 'use_new_global' | 'complete_old' | 'keep_as_is';

export interface ImpactedAgent {
  projectId: string;
  projectName: string;
  agent: Agent;
  missingFields: MissingField[];
  reason: 'model_without_endpoint' | 'old_endpoint_incomplete';
}

export function normalizedEndpoint(value: string): string {
  let url = value.trim();
  while (url.endsWith('/')) url = url.slice(0, -1);
  return url;
}

export function findImpactedAgents(params: {
  slot: ConfigSlot;
  oldSlot: Pick<RuntimeConfigSlot, 'url' | 'model' | 'key_set' | 'context_window' | 'timeout'>;
  newUrl: string;
  projects: Array<Pick<Project, 'id' | 'name'>>;
  agentsByProject: Record<string, Agent[]>;
}): ImpactedAgent[] {
  const { slot, oldSlot, newUrl, projects, agentsByProject } = params;
  const oldNorm = normalizedEndpoint(oldSlot.url);
  const newNorm = normalizedEndpoint(newUrl);
  if (!oldNorm || oldNorm === newNorm) {
    return [];
  }

  const impacted: ImpactedAgent[] = [];
  for (const project of projects) {
    const agents = agentsByProject[project.id] ?? [];
    for (const agent of agents) {
      const agentSlot: ConfigSlot = agent.role_id === 'coordinator' ? 'coordinator' : 'follower';
      if (agentSlot !== slot) continue;

      const hasModel = Boolean(agent.settings.model?.trim());
      const hasBaseUrl = Boolean(agent.settings.base_url?.trim());
      const hasApiKey = Boolean(agent.settings.api_key_set);

      if (hasModel && !hasBaseUrl) {
        const missingFields: MissingField[] = ['base_url'];
        if (oldSlot.key_set && !hasApiKey) missingFields.push('api_key');
        impacted.push({
          projectId: project.id,
          projectName: project.name,
          agent,
          missingFields,
          reason: 'model_without_endpoint',
        });
        continue;
      }

      if (hasBaseUrl && normalizedEndpoint(agent.settings.base_url) === oldNorm) {
        const missingFields: MissingField[] = [];
        if (!hasModel) missingFields.push('model');
        if (oldSlot.key_set && !hasApiKey) missingFields.push('api_key');
        if (missingFields.length > 0) {
          impacted.push({
            projectId: project.id,
            projectName: project.name,
            agent,
            missingFields,
            reason: 'old_endpoint_incomplete',
          });
        }
      }
    }
  }
  return impacted;
}

export function buildImpactResolutionPatch(params: {
  item: ImpactedAgent;
  decision: ImpactDecision;
  oldSlot: Pick<RuntimeConfigSlot, 'url' | 'model' | 'context_window' | 'timeout'>;
  manualApiKey?: string;
}): Record<string, unknown> | null {
  const { item, decision, oldSlot, manualApiKey } = params;
  if (decision === 'keep_as_is') return null;

  if (decision === 'use_new_global') {
    const patch: Record<string, unknown> = {};
    if (item.agent.settings.model) patch.model = '';
    if (item.agent.settings.base_url) patch.base_url = '';
    if (item.agent.settings.api_key_set) patch.api_key = '';
    if (item.agent.settings.context_window) patch.context_window = 0;
    return Object.keys(patch).length > 0 ? patch : null;
  }

  // complete_old: 补齐旧供应商缺失的 base_url / model / 手动填写的 api_key
  const patch: Record<string, unknown> = {};
  if (!item.agent.settings.base_url && oldSlot.url) {
    patch.base_url = oldSlot.url;
  }
  if (!item.agent.settings.model && oldSlot.model) {
    patch.model = oldSlot.model;
  }
  if (!item.agent.settings.context_window && oldSlot.context_window > 0) {
    patch.context_window = oldSlot.context_window;
  }
  if (!item.agent.settings.timeout && oldSlot.timeout > 0) {
    patch.timeout = oldSlot.timeout;
  }
  const trimmedKey = manualApiKey?.trim();
  if (trimmedKey) {
    patch.api_key = trimmedKey;
  }
  return Object.keys(patch).length > 0 ? patch : null;
}
