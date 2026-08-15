import type { Agent, EventEnvelope, Project, TranscriptMessage } from './types';

const runtimeUrl = (window as any).cloudraRuntime?.runtimeBaseUrl ?? (import.meta.env.VITE_RUNTIME_URL ?? 'http://127.0.0.1:8000');

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${runtimeUrl}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!resp.ok) {
    let code = 'http_error';
    let message = resp.statusText;
    try {
      const body = await resp.json();
      code = body.detail?.code ?? code;
      message = body.detail?.message ?? body.detail ?? message;
    } catch {
      /* keep defaults */
    }
    throw new ApiError(code, String(message));
  }
  return (await resp.json()) as T;
}

interface CommandResponse<T> {
  command_id: string;
  accepted: boolean;
  event_id: string;
  data: T;
}

export const api = {
  listProjects: () => request<Project[]>('/api/v2/projects'),
  createProject: (name: string, workspace_dir?: string) =>
    request<CommandResponse<Project>>('/api/v2/projects', {
      method: 'POST',
      body: JSON.stringify({ name, workspace_dir }),
    }),
  listAgents: (projectId: string) => request<Agent[]>(`/api/v2/projects/${projectId}/agents`),
  spawnAgent: (
    projectId: string,
    body: { role_id: string; query?: string; parent_session_id?: string | null },
  ) =>
    request<CommandResponse<Agent>>(`/api/v2/projects/${projectId}/agents`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getAgent: (agentId: string) => request<Agent>(`/api/v2/agents/${agentId}`),
  transcript: (agentId: string) =>
    request<{ messages: TranscriptMessage[] }>(`/api/v2/agents/${agentId}/transcript`),
  events: (agentId: string, after = 0, types?: string) =>
    request<EventEnvelope[]>(
      `/api/v2/agents/${agentId}/events?after=${after}${types ? `&types=${types}` : ''}`,
    ),
  sendMessage: (agentId: string, content: string) =>
    request<CommandResponse<Agent>>(`/api/v2/agents/${agentId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
  cancel: (agentId: string, message?: string) =>
    request<CommandResponse<Agent>>(`/api/v2/agents/${agentId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  restart: (agentId: string, message?: string) =>
    request<CommandResponse<Agent>>(`/api/v2/agents/${agentId}/restart`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  patchSettings: (agentId: string, patch: Record<string, unknown>) =>
    request<CommandResponse<Agent>>(`/api/v2/agents/${agentId}/settings`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  listRoles: () => request<Array<{ role_id: string; display_name: string }>>('/api/v2/roles'),
  approvals: (projectId: string) => request<Array<Record<string, unknown>>>(`/api/v2/projects/${projectId}/approvals`),
  decideApproval: (projectId: string, approvalId: number | string, decision: 'approve' | 'deny', reason = '') =>
    request<{ accepted: boolean }>(`/api/v2/projects/${projectId}/approvals/${approvalId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, reason }),
    }),
  interactions: (projectId: string) => request<Array<Record<string, unknown>>>(`/api/v2/projects/${projectId}/interactions`),
  respondInteraction: (projectId: string, interactionId: number | string, response: string) =>
    request<Record<string, unknown>>(`/api/v2/projects/${projectId}/interactions/${interactionId}/response`, {
      method: 'POST',
      body: JSON.stringify({ response }),
    }),
  artifacts: (projectId: string) => request<Array<Record<string, unknown>>>(`/api/v2/projects/${projectId}/artifacts`),
  dagDelivery: (projectId: string) => request<Record<string, unknown>>(`/api/v2/projects/${projectId}/dag/delivery`),
  dagReport: (projectId: string) => request<Record<string, unknown>>(`/api/v2/projects/${projectId}/dag/report`),
  dagMutations: (projectId: string, operations: unknown[], baseRevisions: Record<string, number>, rationale: string) =>
    request<Record<string, unknown>>(`/api/v2/projects/${projectId}/dag/mutations`, {
      method: 'POST',
      body: JSON.stringify({ operations, base_revisions: baseRevisions, rationale }),
    }),
};

export function streamProject(projectId: string, cursor: number, onEvent: (e: EventEnvelope) => void) {
  const source = new EventSource(`${runtimeUrl}/api/v2/projects/${projectId}/stream?cursor=${cursor}`);
  source.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as EventEnvelope);
    } catch {
      /* ignore malformed */
    }
  };
  return source;
}
