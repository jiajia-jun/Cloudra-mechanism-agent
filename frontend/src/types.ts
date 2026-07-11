export type Conversation = {
  id: string;
  state: string;
  create_time?: string;
  last_active?: string;
};

export type Session = {
  session_id: string;
  agent_id: string | null;
  agent_type: string | null;
  parent_session_id: string | null;
  query: string | null;
  state: string;
  result: string | null;
  error: string | null;
  pid: number | null;
  worker_id: string | null;
  created_at: string | null;
  started_at: string | null;
  heartbeat_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
};

export type SessionEvent = {
  id: number;
  event_type: string;
  data: Record<string, unknown>;
  created_at: string;
};

export type Message = {
  role: string;
  content: unknown;
};

export type Approval = {
  id: number;
  conversation_id: string;
  session_id: string;
  agent_name: string | null;
  details: string;
};
