export interface RuntimeSettings {
  model: string;
  base_url: string;
  api_key_set: boolean;
  temperature: number;
  max_tokens: number;
  context_window: number;
  timeout: number;
  yolo: boolean;
  native_search: string;
  native_search_params: Record<string, unknown>;
  orchestration_mode: 'standard' | 'dag_record' | 'dag_guided';
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
  current_run: { run_id: string; started_at: string; current_tool: string | null } | null;
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

export interface TranscriptMessage {
  message_id: string | null;
  sender: string | null;
  content: string;
  event_id: string;
  created_at: string;
}

export interface RuntimeConfigSlot {
  model: string;
  url: string;
  key_set: boolean;
  context_window: number;
  timeout: number;
}

export interface RuntimeConfig {
  config_file: string;
  coordinator: RuntimeConfigSlot;
  follower: RuntimeConfigSlot;
}
