export interface RuntimeSettings {
  model: string;
  base_url: string;
  api_key_set: boolean;
  temperature: number;
  max_tokens: number;
  context_window: number;
  timeout: number;
  yolo: boolean;
  visual_mode?: boolean;
  schedule_mode?: boolean;
  native_search: string;
  native_search_params: Record<string, unknown>;
  reasoning_effort?: string | null;
  orchestration_mode: 'standard' | 'dag_record' | 'dag_guided';
  invocation_protocol?: 'traditional' | 'javascript';
  unattended?: boolean;
  clean_context?: boolean;
}

export interface PermissionSet {
  read: boolean;
  write: boolean;
  manage: boolean;
  script: boolean;
  destructive: boolean;
}

export interface AgentCapabilities {
  permissions: PermissionSet;
  can_spawn: boolean;
  spawn_roles: string[] | null;
  tools: string[];
}

export interface CompletionSummary {
  run_id: string | null;
  run_outcome: 'succeeded' | 'failed' | 'cancelled' | null;
  completion_basis: string | null;
  verification_label: 'verified' | 'supervisor_reviewed' | 'partial' | 'scope_completed' | 'unverified';
}

export interface Agent {
  id: string;
  project_id: string;
  role_id: string;
  display_name: string;
  parent_session_id: string | null;
  state: string;
  settings: RuntimeSettings;
  settings_revision: number;
  capabilities: AgentCapabilities;
  current_run: { run_id: string; started_at: string; invocation_protocol?: string } | null;
  current_task?: string | null;
  // 运行期投影（服务端从收尾事件算出）：该 agent 最近一次已结束 run 的完成
  // 依据；正在跑/挂起或从未收尾时为 null。
  completion?: CompletionSummary | null;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  name: string;
  workspace_dir: string | null;
  archived: boolean;
  settings: {
    orchestration_mode: 'standard' | 'dag_record' | 'dag_guided';
    defaults: Partial<RuntimeSettings>;
  };
  created_at: string;
  updated_at: string;
}

export interface EventEnvelope {
  stream: 'agent' | 'project';
  event_id: string;
  project_id: string;
  session_id: string | null;
  run_id: string | null;
  seq: number;
  session_seq: number | null;
  type: string;
  data: Record<string, unknown>;
  created_at: string;
}

// AgentHub 论坛帖（hub.posted 事件的投影，见 cloudra/runtime_v2/hub_bridge.py）。
export interface HubPost {
  id: string;
  seq: number;
  created_at: string;
  topic: string;
  kind: string;
  author_agent: string;
  author_session: string | null;
  to_agent: string | null;
  parent_id: string | null;
  content: string;
}

export interface ProviderPreset {
  id: string;
  name: string;
  default_url: string;
  default_model: string;
  models: string[];
  context_window: number;
  supports_vision: boolean;
  native_search: string;
  key_hint?: string;
  match_hosts?: string[];
}

export interface RuntimeConfigSlot {
  provider?: string;
  model: string;
  url: string;
  key_set: boolean;
  context_window: number;
  timeout: number;
  supports_vision?: boolean;
  reasoning_effort?: string | null;
}

export interface RuntimeConfig {
  config_file: string;
  coordinator: RuntimeConfigSlot;
  follower: RuntimeConfigSlot;
  tool_document_loading: ToolDocumentLoadingConfig;
}

export interface SemanticConnection {
  endpoint: string;
  model: string;
  key_set: boolean;
  max_tools: number | null;
}

export interface ToolDocumentLoadingConfig {
  strategy: 'llm' | 'semantic';
  semantic_backend: 'jev' | 'reranker';
  jev: SemanticConnection & { min_probability: number | null };
  reranker: SemanticConnection & { min_score: number | null };
}

export interface CodexAuthStatus {
  authenticated: boolean;
  expires_at: number | null;
  account_id: string | null;
}

export interface CodexDeviceLogin {
  login_id: string;
  user_code: string;
  verification_uri: string;
  interval: number;
  expires_at: number;
}

export interface KgOverview {
  db_present: boolean;
  entities: number;
  relations: number;
  corroborated: number;
  type_dist: Record<string, number>;
  rel_dist: Record<string, number>;
}

export interface KgSearchRow {
  id: string;
  type: string;
  label: string;
  label_en: string | null;
  content: string;
  score: number;
  hop: number;
  fallback: string;
  source: string;
}

export interface KgNode {
  id: string;
  type: string;
  label: string;
  label_en: string | null;
  n_sources: number;
  degree: number;
  hop: number;
}

export interface KgEdge {
  src_id: string;
  dst_id: string;
  rel_type: string;
  corroborated: boolean;
  source: string;
  falsified: boolean;
}

export interface KgGraph {
  focus: KgNode | null;
  nodes: KgNode[];
  edges: KgEdge[];
  truncated: boolean;
}

export interface KgSearchResponse {
  query: string;
  fallback: string | null;
  results: KgSearchRow[];
}

export interface KgHealthChannel {
  ok: boolean;
  entities?: number;
  relations?: number;
  sources?: number;
  error?: string;
}

export interface KgHealth {
  graph: KgHealthChannel;
  content: KgHealthChannel;
}

export interface ComputeJob {
  id: number;
  conversation_id: string;
  session_id: string | null;
  state: string;
  path: string;
  start_timestamp: number | null;
  end_timestamp: number | null;
  jobtype: string;
  // Owning registered node (capacity is accounted per node); null only on legacy rows.
  node_id: string | null;
  scheduler: string;
  scheduler_state: string | null;
  last_error: string | null;
  priority: number;
  req_cpus: number;
  req_memory_mb: number | null;
  attempt_count: number;
}

export interface NodeResources {
  max_concurrent: number;
  cpus: number;
  memory_mb: number;
}

export interface ComputeNode {
  node_id: string;
  display_name: string;
  scheduler: string;
  // transport: 'local' runs on this host; 'ssh' stages jobs to a remote server
  // (remote = user@host of the SSH target, null for local nodes).
  connection: string;
  remote: string | null;
  state: string;
  // effective = registered scheduling quota; OS availability is observational only.
  // free = quota minus in-flight reservations.
  capacity: {
    registered: NodeResources;
    os_available: { memory_mb: number | null; cpus: number | null };
    effective: NodeResources;
  };
  in_flight: { slots: number; cpus: number; memory_mb: number };
  free: { slots: number; cpus: number; memory_mb: number };
}

export interface PendingReminder {
  schedule_id: number;
  session_id: string;
  project_id: string;
  message: string;
  wake_at: string;
  wake_ts: number;
  check_command: string | null;
  interval_seconds: number | null;
}

export interface FsBrowseEntry {
  name: string;
  path: string;
  is_dir: boolean;
  mtime?: number | null;
}

export interface FsBrowseShortcut {
  name: string;
  path: string;
}

export interface FsBrowseResponse {
  current: string;
  parent: string | null;
  home: string;
  cwd: string;
  shortcuts: FsBrowseShortcut[];
  entries: FsBrowseEntry[];
  writable: boolean;
}
