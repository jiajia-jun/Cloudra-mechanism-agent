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
  data: Record<string, unknown> & {
    // llm_chunk 事件字段：token 级流式增量
    stream?: "content" | "reasoning";
    delta?: string;
    agent_id?: string;
    agent_name?: string;
  };
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

// GET /api/config 的脱敏配置展示（key 已被后端脱敏为 "***" 或 "(not set)"）
export type ConfigDisplay = {
  data_dir: string;
  config_file: string;
  llm: {
    coordinator: { model: string; url: string; key: string; supports_vision: boolean };
    follower: { model: string; url: string; key: string; supports_vision: boolean };
  };
};

// GET /api/conversations/{cid}/logs 的单个日志文件
export type LogFile = {
  name: string;
  size: number;
  content: string;
  truncated: boolean;
};

// GET /api/sessions 的跨会话 Session 行
export type SessionRow = Session & { conversation_id: string };

// GET /api/skills 的技能摘要
export type SkillInfo = {
  name: string;
  description: string;
};

// 运行区对话式 transcript 的气泡项：由 llm_chunk/tool_started/tool_finished/llm_stream_end 事件经 reducer 构建
export type TranscriptItem =
  | { kind: "reasoning" | "content"; text: string; open: boolean }
  | { kind: "tool"; tool: string; args: string; state: "running" | "done"; result?: string };
