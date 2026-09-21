import type {
  Agent,
  ComputeJob,
  ComputeNode,
  EventEnvelope,
  FsBrowseResponse,
  KgGraph,
  KgHealth,
  KgOverview,
  KgSearchResponse,
  PendingReminder,
  Project,
  ProviderPreset,
  RuntimeConfig,
} from './types';
import { trustedRuntimeBase } from './runtimeUrl';

// Resolution order: trusted ?runtime= (loopback / same-origin only) ->
// Vite env -> same origin (production serves the SPA and API on one port).
const runtimeUrl: string = trustedRuntimeBase(
  new URLSearchParams(window.location.search).get('runtime'),
  window.location.origin,
  import.meta.env.VITE_RUNTIME_URL ?? '',
);

// ---- bearer token ----
// The launcher hands the token over via the URL fragment (#token=...): a
// fragment is never sent to the server.  We move it into sessionStorage and
// scrub the address bar so it does not leak via screenshots/history.
const TOKEN_STORAGE_KEY = 'cloudra.api_token';

function bootstrapToken(): string {
  const match = window.location.hash.match(/^#token=(.+)$/);
  if (match) {
    const token = decodeURIComponent(match[1]);
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
    history.replaceState(null, '', window.location.pathname + window.location.search);
    return token;
  }
  return sessionStorage.getItem(TOKEN_STORAGE_KEY) ?? '';
}

const apiToken: string = bootstrapToken();

function authHeaders(): Record<string, string> {
  return apiToken ? { Authorization: `Bearer ${apiToken}` } : {};
}

// URL-bearing surfaces that cannot carry headers (EventSource, <img src>,
// download <a href>) authenticate via the ?token= query fallback instead.
function withToken(url: string): string {
  if (!apiToken) return url;
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(apiToken)}`;
}

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${runtimeUrl}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers as Record<string, string> | undefined),
      ...authHeaders(),
    },
  });
  if (!resp.ok) {
    let code = resp.status === 401 ? 'unauthorized' : 'http_error';
    let message = resp.status === 401 ? '需要 API token（用启动时打印的 #token= URL 打开）' : resp.statusText;
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

function assertAccepted<T>(resp: CommandResponse<T>, fallback: string): CommandResponse<T> {
  if (resp.accepted === false) {
    const err = (resp.data as { error?: { message?: string } } | null)?.error;
    throw new ApiError('rejected', err?.message ?? fallback);
  }
  return resp;
}

// Bounded timeline window, shared by the history fetch and the live SSE
// handler (which slices the in-memory list to the same size).  The endpoint
// returns the LAST `limit` events per page; a single windowed fetch drowns
// sparse message/thinking events in tool.*/llm.* noise, so we always load the
// most recent window via `tail=true` — consistent with what the SSE stream
// keeps, and O(1) instead of paging the entire session.
export const EVENTS_WINDOW = 500;
// One backwards page of older history loaded per "load earlier" click in the
// chat transcript; same size as the live window so one click visibly doubles
// the transcript.
export const HISTORY_PAGE_SIZE = 500;

export const api = {
  listProjects: (includeArchived = false) =>
    request<Project[]>(`/api/v2/projects${includeArchived ? '?include_archived=true' : ''}`),
  createProject: (name: string, workspace_dir?: string) =>
    request<CommandResponse<Project>>('/api/v2/projects', {
      method: 'POST',
      body: JSON.stringify({ name, workspace_dir }),
    }),
  patchProject: (projectId: string, patch: Record<string, unknown>) =>
    request<CommandResponse<Project>>(`/api/v2/projects/${projectId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  archiveProject: (projectId: string) =>
    request<CommandResponse<Project>>(`/api/v2/projects/${projectId}`, { method: 'DELETE' }),
  unarchiveProject: (projectId: string) =>
    request<CommandResponse<Project>>(`/api/v2/projects/${projectId}`, {
      method: 'PATCH',
      body: JSON.stringify({ archived: false }),
    }),
  // Hard delete (archived projects only): tombstone event + on-disk support data
  // cleanup.  The workspace directory and compute.db history are always kept.
  deleteProject: (projectId: string) =>
    request<CommandResponse<{ deleted: string }>>(`/api/v2/projects/${projectId}?hard=true`, {
      method: 'DELETE',
    }),
  // Ledger-level cancel of every unfinished compute job; never kills processes.
  cancelAllComputeJobs: () =>
    request<{ ready_cancelled: number; slurm_cancel_requested: number; local_cancelled: number }>(
      '/api/v2/compute/cancel-all',
      { method: 'POST' },
    ),
  browseFs: (path?: string, showHidden = false) => {
    const params = new URLSearchParams();
    if (path) params.set('path', path);
    if (showHidden) params.set('show_hidden', 'true');
    const query = params.toString();
    return request<FsBrowseResponse>(`/api/v2/fs/browse${query ? `?${query}` : ''}`);
  },
  mkdirFs: (path: string) =>
    request<{ success: boolean; path: string }>('/api/v2/fs/mkdir', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  systemPickerFs: () =>
    request<{ supported: boolean; path: string | null; canceled?: boolean }>(
      '/api/v2/fs/system-picker',
      { method: 'POST' },
    ),
  listAgents: (projectId: string) => request<Agent[]>(`/api/v2/projects/${projectId}/agents`),
  // Read-only ops queries: project compute queue (active states by default)
  // and pending reminders. Rows carry session_id = owning agent.
  listComputeJobs: (projectId: string, activeOnly = true) =>
    request<ComputeJob[]>(
      `/api/v2/projects/${projectId}/compute/jobs?active_only=${activeOnly}`,
    ),
  // Registered-node capacity views (global ledger, not project-scoped): one
  // entry per node with its own quota, in-flight usage and free headroom.
  computeNodes: () => request<ComputeNode[]>('/api/v2/compute/nodes'),
  listPendingReminders: (projectId: string) =>
    request<PendingReminder[]>(`/api/v2/projects/${projectId}/reminders/pending`),
  spawnAgent: async (
    projectId: string,
    body: { role_id: string; query?: string; parent_session_id?: string | null; settings?: Record<string, unknown> },
  ) =>
    assertAccepted(
      await request<CommandResponse<Agent>>(`/api/v2/projects/${projectId}/agents`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
      'Spawn rejected',
    ),
  getAgent: (agentId: string) => request<Agent>(`/api/v2/agents/${agentId}`),
  events: (agentId: string, limit = EVENTS_WINDOW, types?: string) =>
    request<EventEnvelope[]>(
      `/api/v2/agents/${agentId}/events?after=0&limit=${limit}&tail=true${types ? `&types=${types}` : ''}`,
    ),
  /** One lazy page of the audit trail.  Omit `before` for the newest page;
   * with `before` set, returns the page of `limit` events ending at that
   * session_seq cursor (backwards paging). */
  eventsPage: (
    agentId: string,
    opts: { before?: number; limit?: number } = {},
  ) => {
    const { before, limit = 200 } = opts;
    const q = `after=0&limit=${limit}&tail=true${before != null ? `&before=${before}` : ''}`;
    return request<EventEnvelope[]>(`/api/v2/agents/${agentId}/events?${q}`);
  },
  sendMessage: async (agentId: string, content: string, images?: string[], imageArtifactIds?: (string | null)[]) =>
    assertAccepted(
      await request<CommandResponse<Agent>>(`/api/v2/agents/${agentId}/messages`, {
        method: 'POST',
        body: JSON.stringify(
          images && images.length > 0
            ? { content, images, image_artifact_ids: imageArtifactIds ?? [] }
            : { content },
        ),
      }),
      'Message rejected',
    ),
  uploadFile: (projectId: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    // headers:{} replaces the JSON content-type so fetch sets the multipart boundary.
    return request<{ path: string; artifact_id: string }>(`/api/v2/projects/${projectId}/uploads`, {
      method: 'POST',
      body: form,
      headers: {},
    });
  },
  cancel: async (agentId: string, message?: string) =>
    assertAccepted(
      await request<CommandResponse<Agent>>(`/api/v2/agents/${agentId}/cancel`, {
        method: 'POST',
        body: JSON.stringify({ message }),
      }),
      'Cancel rejected',
    ),
  patchSettings: (agentId: string, patch: Record<string, unknown>) =>
    request<CommandResponse<Agent>>(`/api/v2/agents/${agentId}/settings`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  listRoles: () => request<Array<{ role_id: string; display_name: string }>>('/api/v2/roles'),
  providers: () => request<ProviderPreset[]>('/api/v2/runtime/providers'),
  getOpenRouterPkce: (callbackUrl?: string) =>
    request<{ auth_url: string; code_verifier: string; code_challenge: string }>(
      `/api/v2/runtime/providers/openrouter/pkce${callbackUrl ? `?callback_url=${encodeURIComponent(callbackUrl)}` : ''}`
    ),
  exchangeOpenRouterCode: (code: string, code_verifier: string, slot?: 'coordinator' | 'follower') =>
    request<{ key: string; saved: boolean }>('/api/v2/runtime/providers/openrouter/code-exchange', {
      method: 'POST',
      body: JSON.stringify({ code, code_verifier, slot }),
    }),
  runtimeConfig: () => request<RuntimeConfig>('/api/v2/runtime/config'),
  patchRuntimeConfig: (slot: 'coordinator' | 'follower', changes: Record<string, unknown>) =>
    request<RuntimeConfig>('/api/v2/runtime/config', {
      method: 'PATCH',
      body: JSON.stringify({ slot, changes }),
    }),
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
  artifactDownloadUrl: (projectId: string, artifactId: string) =>
    withToken(`${runtimeUrl}/api/v2/artifacts/${artifactId}/download?project_id=${encodeURIComponent(projectId)}`),
  // Full human-readable Markdown dump of the project's event stream.
  projectTranscriptUrl: (projectId: string) =>
    withToken(`${runtimeUrl}/api/v2/projects/${projectId}/transcript`),
  // 2D molecular structure diagram rendered from SMILES.
  chemRenderSmilesUrl: (smiles: string, width = 200, height = 140, theme = 'dark') =>
    withToken(`${runtimeUrl}/api/v2/chem/render-smiles?smiles=${encodeURIComponent(smiles)}&width=${width}&height=${height}&theme=${theme}&v=w4`),
  dagDelivery: (projectId: string) =>
    request<{ mode: string; graph: Record<string, unknown> | null }>(`/api/v2/projects/${projectId}/dag/delivery`),
  dagReviews: (projectId: string) =>
    request<{ pending: Array<Record<string, unknown>>; recent: Array<Record<string, unknown>> } | null>(
      `/api/v2/projects/${projectId}/dag/reviews`,
    ),
  dagDraft: (projectId: string) =>
    request<{ mechanism_accepted: boolean; draft: Record<string, unknown> | null } | null>(
      `/api/v2/projects/${projectId}/dag/draft`,
    ),
  dagReport: (projectId: string) => request<Record<string, unknown> | null>(`/api/v2/projects/${projectId}/dag/report`),
  dagHistory: (projectId: string) => request<Array<Record<string, unknown>>>(`/api/v2/projects/${projectId}/dag/history`),
  dagProjection: (projectId: string) => request<Record<string, unknown> | null>(`/api/v2/projects/${projectId}/dag/projection`),
  dagReplan: (projectId: string, note: string) =>
    request<Record<string, unknown>>(`/api/v2/projects/${projectId}/dag/replan`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),
  dagMutations: (projectId: string, operations: unknown[], baseRevisions: Record<string, number>, rationale: string) =>
    request<Record<string, unknown>>(`/api/v2/projects/${projectId}/dag/mutations`, {
      method: 'POST',
      body: JSON.stringify({ operations, base_revisions: baseRevisions, rationale }),
    }),
  getGoal: (agentId: string) =>
    request<{ goal: { objective: string; completion_criteria: string; current_focus: string } | null }>(
      `/api/v2/agents/${agentId}/goal`,
    ),
  setGoal: (agentId: string, goal: { objective: string; completion_criteria: string; current_focus: string }) =>
    request<{ goal: { objective: string; completion_criteria: string; current_focus: string } }>(
      `/api/v2/agents/${agentId}/goal`,
      { method: 'POST', body: JSON.stringify(goal) },
    ),
  getContextStats: (agentId: string) =>
    request<{
      session_id: string;
      messages: number;
      tokens: number;
      by_role: Record<string, { messages: number; tokens: number }>;
      last_prompt_tokens: number | null;
    }>(`/api/v2/agents/${agentId}/context`),
  compactAgent: (agentId: string) =>
    request<CommandResponse<Agent>>(`/api/v2/agents/${agentId}/compact`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  listSkills: () => request<Array<Record<string, unknown>>>('/api/v2/skills'),
  knowledgeOverview: () => request<KgOverview>('/api/v2/knowledge/overview'),
  knowledgeHealth: () => request<KgHealth>('/api/v2/knowledge/health'),
  knowledgeSearch: (q: string, limit = 10) =>
    request<KgSearchResponse>(
      `/api/v2/knowledge/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),
  knowledgeGraph: (focus: string, hops: 1 | 2) =>
    request<KgGraph>(
      `/api/v2/knowledge/graph?focus=${encodeURIComponent(focus)}&hops=${hops}`,
    ),
  benchmarkStatus: () => request<BenchmarkStatus>('/api/v2/benchmark/status'),
  benchmarkCatalog: () => request<BenchmarkCatalog>('/api/v2/benchmark/catalog'),
  benchmarkStart: (body: { tiers?: string[]; tasks_dirs?: string[]; only?: string; concurrency?: number; timeout?: number }) =>
    request<BenchmarkStatus>('/api/v2/benchmark/start', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  benchmarkStop: () =>
    request<BenchmarkStatus>('/api/v2/benchmark/stop', {
      method: 'POST',
      body: '{}',
    }),
  benchmarkRuns: () => request<BenchmarkHistory>('/api/v2/benchmark/runs'),
  benchmarkStreamUrl: () => withToken(`${runtimeUrl}/api/v2/benchmark/stream`),
  // ---- LLM telemetry (read-only; routers/telemetry.py) ----
  telemetryTokens: (since?: string, until?: string) => {
    const params = new URLSearchParams();
    if (since) params.set('since', since);
    if (until) params.set('until', until);
    const query = params.toString();
    return request<TelemetryTokensResponse>(`/api/v2/telemetry/tokens${query ? `?${query}` : ''}`);
  },
  telemetryCache: (since?: string, until?: string, topN = 20) => {
    const params = new URLSearchParams();
    if (since) params.set('since', since);
    if (until) params.set('until', until);
    params.set('top_n', String(topN));
    return request<TelemetryCacheResponse>(`/api/v2/telemetry/cache?${params.toString()}`);
  },
  // Downloads cannot carry headers -> ?token= query fallback, like artifacts.
  telemetrySessionExportUrl: (sessionId: string) =>
    withToken(`${runtimeUrl}/api/v2/telemetry/export/session/${encodeURIComponent(sessionId)}`),
  telemetryProjectExportUrl: (projectId: string) =>
    withToken(`${runtimeUrl}/api/v2/telemetry/export/project/${encodeURIComponent(projectId)}`),
};

// ---- telemetry ----

export interface TelemetryTotals {
  requests: number;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  total_tokens: number;
  hit_rate: number;
  first_request_at: string | null;
  last_request_at: string | null;
}

export interface TelemetryAgentRow extends TelemetryTotals {
  session_id: string;
  project_id: string | null;
}

export interface TelemetryProjectRow extends TelemetryTotals {
  project_id: string;
  sessions: number;
}

export interface TelemetryTokensResponse {
  since: string | null;
  until: string | null;
  totals: TelemetryTotals & { sessions: number; projects: number };
  agents: TelemetryAgentRow[];
  projects: TelemetryProjectRow[];
}

export interface TelemetryCacheResponse {
  since: string | null;
  until: string | null;
  overall: TelemetryTotals;
  by_day: Array<TelemetryTotals & { day: string }>;
  by_request_bucket: Array<TelemetryTotals & { bucket: string; sessions: number }>;
  by_model: Array<TelemetryTotals & { model: string }>;
  miss_distribution: { count: number; median: number; p90: number; p99: number; max: number };
  top_misses: Array<{
    created_at: string | null;
    session_id: string | null;
    project_id: string | null;
    model: string;
    prompt_tokens: number;
    cached_tokens: number;
    missed_tokens: number;
  }>;
}

// ---- benchmark (GH #32) ----

export interface BenchmarkTaskRow {
  task_id: string;
  tier: string;
  family: string;
  name: string;
  status: 'queued' | 'running' | 'scored' | 'cancelled' | 'error' | string;
  project_id: string;
  agent_id: string;
  started_at: number | null;
  finished_at: number | null;
  error: string;
  final_score: number | null;
  graph_score: number | null;
  integrity_passed: boolean | null;
  selfconsistency_passed: boolean | null;
  accuracy_score: number | null;
  outcome: string | null;
  notes: string[];
}

export interface BenchmarkRefusalStats {
  tp: number;
  fp: number;
  fn: number;
  tn: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
}

export interface BenchmarkCatalogTier {
  tier: string;
  path: string;
  task_count: number;
  task_ids: string[];
}

export interface BenchmarkCatalog {
  tiers: BenchmarkCatalogTier[];
}

export interface BenchmarkStatus {
  batch_id: string | null;
  status: 'idle' | 'running' | 'stopping' | 'stopped' | 'done' | 'error' | string;
  started_at: number | null;
  finished_at: number | null;
  config: Record<string, unknown>;
  tasks: BenchmarkTaskRow[];
  refusal: BenchmarkRefusalStats | Record<string, never>;
}

export interface BenchmarkRunRow {
  task_id: string;
  sandbox: string;
  integrity_passed: boolean;
  graph_score: number;
  selfconsistency_passed: boolean;
  accuracy_score: number;
  final_score: number;
  outcome: string;
  notes: string[];
  ts: number;
}

export interface BenchmarkHistory {
  batches: Array<{
    batch_id: string;
    status: string;
    config: Record<string, unknown>;
    started_at: number;
    finished_at: number | null;
    runs: BenchmarkRunRow[];
  }>;
}

// Must stay in sync with cloudra/runtime_v2/events.py EVENT_TYPES: the server
// sends every event with an `event: <type>` line, and EventSource.onmessage
// only fires for unnamed events — listeners must be registered per type.
const KNOWN_EVENT_TYPES = [
  'project.created', 'project.updated', 'project.settings_changed',
  'project.deleted',
  'role.updated',
  'agent.spawn_requested', 'agent.spawned', 'agent.spawn_rejected',
  'agent.settings_changed', 'agent.message_injected', 'agent.message_emitted',
  'agent.cancel_requested', 'agent.cancelled',
  'agent.restart_requested', 'agent.restarted', 'agent.context_reset',
  'approval.requested', 'approval.decided', 'approval.expired',
  'interaction.requested', 'interaction.responded', 'interaction.expired',
  'command.rejected',
  'agent.state_changed', 'run.started', 'run.retry', 'run.finished',
  'agent.completion_gate',
  'llm.request_started', 'llm.chunk', 'llm.completed', 'llm.failed',
  'agent.thinking',
  'tool.requested', 'tool.started', 'tool.result_recorded', 'tool.blocked',
  'tool.finished', 'tool.approval_requested',
  'program.submitted', 'program.started', 'program.output', 'program.finished',
  'dag.gate_blocked',
  'hub.posted', 'hub.notification_consumed',
  'compaction.requested', 'compaction.started', 'compaction.finished',
  'reminder.scheduled', 'reminder.cancelled', 'reminder.fired',
  'email.received',
  'loop.detected',
  'agent.warning', 'project.synced',
  'context.pin_set', 'context.pin_cleared', 'context.injected',
  'context.prefix_installed', 'context.appended', 'context.compacted',
];

export interface StreamHandlers {
  onEvent: (e: EventEnvelope) => void;
  onOpen?: () => void;
  onError?: () => void;
}

export function streamProject(projectId: string, cursor: number, handlers: StreamHandlers) {
  const source = new EventSource(withToken(`${runtimeUrl}/api/v2/projects/${projectId}/stream?cursor=${cursor}`));
  const deliver = (msg: MessageEvent) => {
    try {
      handlers.onEvent(JSON.parse(msg.data) as EventEnvelope);
    } catch {
      /* ignore malformed */
    }
  };
  for (const type of KNOWN_EVENT_TYPES) source.addEventListener(type, deliver);
  source.onopen = () => handlers.onOpen?.();
  source.onerror = () => handlers.onError?.();
  return source;
}
