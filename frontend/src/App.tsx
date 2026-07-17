import { memo, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Check, FolderOpen, KeyRound, Menu, Plus, ScrollText, Send, Settings, Sparkles, Square, Trash2, TriangleAlert, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { api, streamSession, tokenStore } from "./api";
import type { Approval, ConfigDisplay, Message, Session, SessionEvent, TranscriptItem } from "./types";

// sleeping 是旧版本 Session 的完成状态，保留兼容，避免为历史 Session 打开无尽 SSE。
const terminalStates = new Set(["completed", "sleeping", "failed", "cancelled", "killed", "interrupted"]);
const WORKING_DIRECTORY_KEY = "cloudra_working_directory";
const YOLO_KEY = "cloudra_yolo_auto_approve";
const isDesktop = "__TAURI_INTERNALS__" in window;

// 进入 transcript 面板的事件类型（其余事件只进生命周期时间线）
const transcriptEventTypes = new Set(["llm_chunk", "llm_stream_end", "tool_started", "tool_finished"]);

// Supervisor 审查事件（supervisor_review）在边栏的展示结构
type SupervisorReview = { verdict: string; reasoning: string; advice: string[]; agentName?: string; time?: string };

function parseSupervisorReview(event: SessionEvent): SupervisorReview {
  const data = event.data;
  return {
    verdict: String(data.verdict ?? "unknown"),
    reasoning: String(data.reasoning ?? ""),
    advice: Array.isArray(data.advice) ? data.advice.map((item) => String(item)) : [],
    agentName: data.agent_name ? String(data.agent_name) : undefined,
    time: event.created_at,
  };
}

// 展示用 result 兜底：历史会话的 result 可能是 stop 工具的原始返回
// （{"stopped": true, "message": "..."} 的 JSON 串），此时只展示 message 正文。
function displayResult(result: string): string {
  const trimmed = result.trim();
  if (!trimmed.startsWith("{")) return result;
  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>;
    if (parsed && typeof parsed.message === "string" && "stopped" in parsed) return parsed.message;
  } catch { /* 不是 JSON，原样展示 */ }
  return result;
}

// 把一条事件折叠进某个 session 的对话式 transcript（SSE 实时与 REST 回放共用）。
// 不可变更新：返回新数组，便于 memo 组件做浅比较。
function applyTranscriptEvent(items: TranscriptItem[], event: SessionEvent): TranscriptItem[] {
  const closeLast = (list: TranscriptItem[]): TranscriptItem[] => {
    const last = list[list.length - 1];
    if (last && last.kind !== "tool" && last.open) {
      return [...list.slice(0, -1), { ...last, open: false }];
    }
    return list;
  };

  const data = event.data;
  if (event.event_type === "llm_chunk") {
    const kind = data.stream === "reasoning" ? "reasoning" : "content";
    const last = items[items.length - 1];
    if (last && last.kind === kind && last.open) {
      return [...items.slice(0, -1), { ...last, text: last.text + (data.delta ?? "") }];
    }
    return [...closeLast(items), { kind, text: data.delta ?? "", open: true }];
  }
  if (event.event_type === "llm_stream_end") {
    return closeLast(items);
  }
  if (event.event_type === "tool_started") {
    return [
      ...closeLast(items),
      { kind: "tool", tool: String(data.tool ?? "unknown"), args: String(data.arguments ?? ""), state: "running" }
    ];
  }
  if (event.event_type === "tool_finished") {
    const result = String(data.result ?? "");
    for (let i = items.length - 1; i >= 0; i--) {
      const item = items[i];
      if (item.kind === "tool" && item.state === "running" && item.tool === String(data.tool ?? "")) {
        const next = [...items];
        next[i] = { ...item, state: "done" as const, result };
        return next;
      }
    }
    return [...items, { kind: "tool", tool: String(data.tool ?? "unknown"), args: "", state: "done", result }];
  }
  return items;
}

// 从全量事件（REST 回放）构建 transcript；回放结束强制闭合所有 open 气泡
function buildTranscript(events: SessionEvent[]): TranscriptItem[] {
  const items = events.reduce<TranscriptItem[]>((acc, event) => applyTranscriptEvent(acc, event), []);
  return items.map((item) => (item.kind !== "tool" && item.open ? { ...item, open: false } : item));
}

const stateLabels: Record<string, string> = {
  idle: "空闲", queued: "排队中", running: "运行中", thinking: "思考中",
  completed: "已完成", sleeping: "已完成", failed: "失败", cancelled: "已取消",
  killed: "已终止", interrupted: "已中断", cancel_requested: "正在取消"
};

function stateLabel(state?: string | null) {
  return stateLabels[state ?? "idle"] ?? state ?? "空闲";
}

const verdictLabels: Record<string, string> = {
  pass: "审查通过",
  redirect: "纠正方向",
  pause_and_reflect: "暂停反思"
};

function verdictLabel(verdict: string) {
  return verdictLabels[verdict] ?? verdict ?? "—";
}

function shortId(value: string) {
  return value.length > 22 ? `${value.slice(0, 12)}…${value.slice(-7)}` : value;
}

function time(value?: string | null) {
  if (!value) return "--:--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "--:--" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// 侧边栏会话列表的短日期：今天只显示时分，跨天显示月/日
function shortDateTime(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const sameDay = date.toDateString() === new Date().toDateString();
  return sameDay
    ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString([], { month: "2-digit", day: "2-digit" });
}

// REST 全量事件与 SSE 已送达事件按 id 归并（并集、升序），避免互相覆盖
function mergeEventsById(current: SessionEvent[], incoming: SessionEvent[]) {
  if (incoming.length === 0) return current;
  const byId = new Map<number, SessionEvent>();
  for (const event of current) byId.set(event.id, event);
  for (const event of incoming) byId.set(event.id, event);
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

function decodeUnicode(str: string) {
  return str.replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
}

function messageText(message: Message) {
  let text = "";
  if (typeof message.content === "string") text = message.content;
  else if (Array.isArray(message.content)) {
    text = message.content.map((part) => {
      if (typeof part === "object" && part && "text" in part) return String(part.text);
      return "";
    }).filter(Boolean).join("\n");
  } else {
    text = message.content ? JSON.stringify(message.content) : "";
  }
  return decodeUnicode(text);
}

function looksLikeMarkdown(text: string) {
  return /(^|\n)#{1,6}\s|(^|\n)[-*+]\s|(^|\n)\d+\.\s|(^|\n)>\s|(^|\n)```|`[^`\n]+`|!?\[[^\]]*\]\([^)]*\)|\*\*[^*]+\*\*|\*[^*]+\*/m.test(text);
}

function MarkdownString({ value }: { value: string }) {
  const [raw, setRaw] = useState(false);
  if (!looksLikeMarkdown(value)) {
    return <span className="json-string">"{value}"</span>;
  }
  return (
    <span className="json-string">
      <button type="button" className="json-md-toggle" onClick={() => setRaw(!raw)} title={raw ? "渲染 Markdown" : "显示原始文本"}>
        {raw ? "MD" : "TXT"}
      </button>
      {raw ? (
        `"${value}"`
      ) : (
        <span className="json-markdown">
          <ReactMarkdown>{value}</ReactMarkdown>
        </span>
      )}
    </span>
  );
}

function JsonNode({ value, depth = 0, defaultOpen = false }: { value: unknown; depth?: number; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  if (value !== null && typeof value === "object") {
    const isArray = Array.isArray(value);
    const count = isArray ? value.length : Object.keys(value as Record<string, unknown>).length;
    return (
      <div className="json-node" style={{ marginLeft: depth > 0 ? 12 : 0 }}>
        <button type="button" className="json-toggle" onClick={() => setOpen(!open)} aria-label={open ? "折叠" : "展开"}>
          {open ? "-" : "+"}
        </button>
        <span className="json-bracket">{isArray ? `[${count}]` : `{${count}}`}</span>
        {open && (
          <div className="json-children">
            {isArray
              ? (value as unknown[]).map((item, index) => (
                  <div key={index} className="json-row">
                    <JsonNode value={item} depth={depth + 1} defaultOpen={false} />
                  </div>
                ))
              : Object.entries(value as Record<string, unknown>).map(([key, val]) => (
                  <div key={key} className="json-row">
                    <span className="json-key">{key}:</span>
                    <JsonNode value={val} depth={depth + 1} defaultOpen={false} />
                  </div>
                ))}
          </div>
        )}
      </div>
    );
  }
  if (typeof value === "string") {
    return <MarkdownString value={value} />;
  }
  return (
    <span className={`json-${value === null ? "null" : typeof value}`}>
      {value === null ? "null" : String(value)}
    </span>
  );
}

function JsonView({ text }: { text: string }) {
  try {
    const data = JSON.parse(text);
    return (
      <div className="json-view">
        <JsonNode value={data} defaultOpen={true} />
      </div>
    );
  } catch {
    return <pre className="message-text">{text}</pre>;
  }
}

function eventLabel(event: SessionEvent) {
  const data = event.data;
  if (event.event_type === "phase") return data.phase === "thinking" ? "正在思考" : "正在执行";
  if (event.event_type === "tool_started") return `调用工具 · ${String(data.tool ?? "unknown")}`;
  if (event.event_type === "tool_finished") return `工具返回 · ${String(data.tool ?? "unknown")}`;
  if (event.event_type === "llm_chunk" || event.event_type === "llm_stream_end") return null; // 流式增量在流式面板展示
  if (event.event_type === "supervisor_review") return `Supervisor 审查 · ${verdictLabel(String(event.data.verdict ?? ""))}`;
  const labels: Record<string, string> = {
    queued: "已进入队列", running: "开始运行", completed: "运行完成",
    failed: "运行失败", cancelled: "已取消", interrupted: "运行中断",
    cancel_requested: "收到打断请求"
  };
  return labels[event.event_type] ?? event.event_type;
}

// 消息条目抽成 memo 组件：流式 state 高频更新时不再拖着整个消息列表的 ReactMarkdown 重渲染
const MessageItem = memo(function MessageItem({ message }: { message: Message }) {
  const text = messageText(message);
  return (
    <article className={`message ${message.role}`}>
      <div className="message-meta">{message.role === "user" ? "你" : message.role === "assistant" ? "Cloudra" : "工具"}</div>
      <div className="message-body">
        {message.role === "tool" ? (
          <JsonView text={text} />
        ) : (
          <div className="message-text">
            <ReactMarkdown>{text}</ReactMarkdown>
          </div>
        )}
      </div>
    </article>
  );
});

// 思考气泡：流入中默认展开，闭合后自动折叠；用户可手动切换
const ReasoningBubble = memo(function ReasoningBubble({ text, open }: { text: string; open: boolean }) {
  const [expanded, setExpanded] = useState(open);
  useEffect(() => { if (!open) setExpanded(false); }, [open]);
  return (
    <details className="bubble bubble-reasoning" open={expanded} onToggle={(e) => setExpanded(e.currentTarget.open)}>
      <summary>思考过程</summary>
      <div className="message-text"><ReactMarkdown>{text}</ReactMarkdown></div>
    </details>
  );
});

const ContentBubble = memo(function ContentBubble({ text }: { text: string }) {
  return <div className="bubble bubble-content message-text"><ReactMarkdown>{text}</ReactMarkdown></div>;
});

// 工具气泡：单行摘要，点击展开参数/结果
const ToolBubble = memo(function ToolBubble({ item }: { item: Extract<TranscriptItem, { kind: "tool" }> }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={`bubble-tool ${item.state}`}>
      <button type="button" className="bubble-tool-head" onClick={() => setExpanded(!expanded)}>
        <i className={item.state === "running" ? "pulse" : "pulse ended"} />
        <span className="bubble-tool-name">{item.tool}</span>
        <span className="bubble-tool-state">{item.state === "running" ? "执行中" : "完成"}</span>
      </button>
      {expanded && (
        <div className="bubble-tool-body">
          {item.args && <pre>{item.args}</pre>}
          {item.result && <pre>{item.result.length > 800 ? `${item.result.slice(0, 800)}…` : item.result}</pre>}
        </div>
      )}
    </div>
  );
});

// 一个 session 的对话式 transcript 面板：只有该 session 的 items 变化时才重渲染
const TranscriptPanel = memo(function TranscriptPanel({ name, active, items }: { name: string; active: boolean; items: TranscriptItem[] }) {
  return (
    <div className="transcript">
      <div className="transcript-head"><i className={active ? "pulse" : "pulse ended"} /><span>{name}</span></div>
      <div className="transcript-body">
        {items.map((item, index) => {
          if (item.kind === "reasoning") return <ReasoningBubble key={index} text={item.text} open={item.open} />;
          if (item.kind === "content") return <ContentBubble key={index} text={item.text} />;
          if (item.kind === "tool") return <ToolBubble key={index} item={item} />;
          return null;
        })}
      </div>
    </div>
  );
});

type ConfigRole = "coordinator" | "follower";
type ConfigFormState = Record<ConfigRole, { model: string; url: string; key: string; supports_vision: boolean }>;

const configRoleLabels: Record<ConfigRole, string> = { coordinator: "Coordinator · 协调者", follower: "Follower · 执行者" };

function configFormFrom(data: ConfigDisplay): ConfigFormState {
  return {
    coordinator: {
      model: data.llm.coordinator.model, url: data.llm.coordinator.url, key: "",
      supports_vision: data.llm.coordinator.supports_vision
    },
    follower: {
      model: data.llm.follower.model, url: data.llm.follower.url, key: "",
      supports_vision: data.llm.follower.supports_vision
    }
  };
}

// 设置弹窗：等价 `cloudra config show` + 逐项 `cloudra config set <key> <value>`
function SettingsModal({ onClose }: { onClose: () => void }) {
  const config = useQuery({ queryKey: ["config"], queryFn: api.getConfig });
  const baselineRef = useRef<ConfigDisplay | null>(null);
  const [form, setForm] = useState<ConfigFormState | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (config.data && !baselineRef.current) {
      baselineRef.current = config.data;
      setForm(configFormFrom(config.data));
    }
  }, [config.data]);

  // 只提交相对基线改动过的字段；key 留空表示不修改；supports_vision 按 "true"/"false" 提交
  const changes = useMemo(() => {
    const base = baselineRef.current;
    if (!base || !form) return [];
    const list: { key: string; value: string }[] = [];
    (["coordinator", "follower"] as const).forEach((role) => {
      if (form[role].model !== base.llm[role].model) list.push({ key: `${role}.model`, value: form[role].model });
      if (form[role].url !== base.llm[role].url) list.push({ key: `${role}.url`, value: form[role].url });
      if (form[role].key.trim()) list.push({ key: `${role}.key`, value: form[role].key.trim() });
      if (form[role].supports_vision !== base.llm[role].supports_vision) {
        list.push({ key: `${role}.supports_vision`, value: String(form[role].supports_vision) });
      }
    });
    return list;
  }, [form]);

  const save = useMutation({
    // 改动逐个提交，任一失败即中断并在弹窗内展示错误
    mutationFn: async (list: { key: string; value: string }[]) => {
      let latest: ConfigDisplay | null = null;
      for (const change of list) latest = await api.setConfigValue(change.key, change.value);
      return latest;
    },
    onSuccess: (latest) => {
      if (latest) {
        baselineRef.current = latest;
        setForm(configFormFrom(latest));
      }
      setError("");
      setSaved(true);
    },
    onError: (cause) => {
      setError(cause instanceof Error ? cause.message : String(cause));
      setSaved(false);
    }
  });

  const update = (role: ConfigRole, field: "model" | "url" | "key", value: string) => {
    setForm((current) => current ? { ...current, [role]: { ...current[role], [field]: value } } : current);
    setSaved(false);
  };
  const updateVision = (role: ConfigRole, checked: boolean) => {
    setForm((current) => current ? { ...current, [role]: { ...current[role], supports_vision: checked } } : current);
    setSaved(false);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}><div className="modal wide" onClick={(event) => event.stopPropagation()}>
      <div className="modal-head"><span><Settings size={15} /> 设置</span><button className="icon-button" onClick={onClose}><X size={16} /></button></div>
      <div className="modal-scroll">
        {config.isLoading && <p>正在读取配置…</p>}
        {config.isError && <p className="error">{String(config.error)}</p>}
        {config.data && form && (
          <>
            <div className="config-meta">
              <div><span>数据目录</span><code>{config.data.data_dir}</code></div>
              <div><span>配置文件</span><code>{config.data.config_file}</code></div>
            </div>
            {(["coordinator", "follower"] as const).map((role) => (
              <fieldset className="config-group" key={role}>
                <legend>{configRoleLabels[role]}</legend>
                <label>模型
                  <input value={form[role].model} onChange={(event) => update(role, "model", event.target.value)} />
                </label>
                <label>接口地址
                  <input value={form[role].url} onChange={(event) => update(role, "url", event.target.value)} />
                </label>
                <label>API Key <small>当前：{config.data.llm[role].key}</small>
                  <input type="password" value={form[role].key} placeholder="留空则不修改"
                    onChange={(event) => update(role, "key", event.target.value)} />
                </label>
                <label className="config-check">
                  <input type="checkbox" checked={form[role].supports_vision}
                    onChange={(event) => updateVision(role, event.target.checked)} />
                  支持视觉输入（supports_vision）
                </label>
              </fieldset>
            ))}
          </>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      {saved && !error && <p className="config-saved">已保存。</p>}
      <button className="block-button" disabled={save.isPending || changes.length === 0 || !form}
        onClick={() => { setError(""); save.mutate(changes); }}>
        {save.isPending ? "保存中…" : "保存"}
      </button>
    </div></div>
  );
}

// Skills 弹窗：等价 `cloudra skills`
function SkillsModal({ onClose }: { onClose: () => void }) {
  const skills = useQuery({ queryKey: ["skills"], queryFn: api.getSkills });
  return (
    <div className="modal-backdrop" onClick={onClose}><div className="modal wide" onClick={(event) => event.stopPropagation()}>
      <div className="modal-head"><span><Sparkles size={15} /> Skills</span><button className="icon-button" onClick={onClose}><X size={16} /></button></div>
      <div className="modal-scroll">
        {skills.isLoading && <p>正在加载…</p>}
        {skills.isError && <p className="error">{String(skills.error)}</p>}
        {skills.data && skills.data.length === 0 && <p>暂无可用 Skills。</p>}
        {skills.data?.map((skill) => (
          <div className="skill-item" key={skill.name}>
            <strong>{skill.name}</strong>
            <p>{skill.description}</p>
          </div>
        ))}
      </div>
    </div></div>
  );
}

// 日志查看器：等价 `cloudra logs <conv_id>`
function LogsModal({ conversationId, onClose }: { conversationId: string; onClose: () => void }) {
  const logs = useQuery({ queryKey: ["logs", conversationId], queryFn: () => api.getLogs(conversationId) });
  const [selected, setSelected] = useState<string | null>(null);
  const current = logs.data?.find((file) => file.name === selected) ?? logs.data?.[0] ?? null;

  return (
    <div className="modal-backdrop" onClick={onClose}><div className="modal wide" onClick={(event) => event.stopPropagation()}>
      <div className="modal-head"><span><ScrollText size={15} /> 运行日志</span><button className="icon-button" onClick={onClose}><X size={16} /></button></div>
      {logs.isLoading && <p>正在读取日志…</p>}
      {logs.isError && <p className="error">{String(logs.error)}</p>}
      {logs.data && logs.data.length === 0 && <p>暂无日志。</p>}
      {logs.data && logs.data.length > 0 && current && (
        <div className="logs-body">
          <div className="logs-tabs">
            {logs.data.map((file) => (
              <button key={file.name} className={file.name === current.name ? "selected" : ""}
                onClick={() => setSelected(file.name)}>{file.name}</button>
            ))}
          </div>
          <div className="logs-content">
            <div className="logs-meta">
              <span>{current.name}</span>
              <span>{(current.size / 1024).toFixed(1)} KB</span>
              {current.truncated && <span className="logs-truncated">已截断</span>}
            </div>
            <pre>{current.content}</pre>
          </div>
        </div>
      )}
    </div></div>
  );
}

const sessionStateFilters = [
  { value: "", label: "全部" },
  { value: "queued", label: "排队中" },
  { value: "running", label: "运行中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
  { value: "cancelled", label: "已取消" },
  { value: "interrupted", label: "已中断" }
];

// Sessions 监控弹窗：等价 `cloudra sessions [--state <state>]`
function SessionsModal({ onClose }: { onClose: () => void }) {
  const [stateFilter, setStateFilter] = useState("");
  const allSessions = useQuery({
    queryKey: ["all-sessions", stateFilter],
    queryFn: () => api.getAllSessions(stateFilter || undefined),
    // 有排队/运行/取消中的行时才 3s 轮询，否则静止
    refetchInterval: (query) =>
      query.state.data?.some((row) => row.state === "queued" || row.state === "running" || row.state === "cancel_requested")
        ? 3_000
        : false
  });

  return (
    <div className="modal-backdrop" onClick={onClose}><div className="modal wide" onClick={(event) => event.stopPropagation()}>
      <div className="modal-head"><span><Activity size={15} /> Sessions 监控</span><button className="icon-button" onClick={onClose}><X size={16} /></button></div>
      <div className="sessions-filter">
        <span>状态</span>
        <select value={stateFilter} onChange={(event) => setStateFilter(event.target.value)}>
          {sessionStateFilters.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </div>
      {allSessions.isLoading && <p>正在加载…</p>}
      {allSessions.isError && <p className="error">{String(allSessions.error)}</p>}
      {allSessions.data && allSessions.data.length === 0 && <p>暂无 Session 记录。</p>}
      {allSessions.data && allSessions.data.length > 0 && (
        <div className="sessions-table-wrap">
          <table className="sessions-table">
            <thead>
              <tr><th>会话 ID</th><th>Session ID</th><th>Agent</th><th>状态</th><th>结果摘要</th></tr>
            </thead>
            <tbody>
              {allSessions.data.map((row) => (
                <tr key={`${row.conversation_id}-${row.session_id}`}>
                  <td><code>{shortId(row.conversation_id)}</code></td>
                  <td><code>{shortId(row.session_id)}</code></td>
                  <td>{row.agent_type ?? "—"}</td>
                  <td>{stateLabel(row.state)}</td>
                  <td>{row.result ? (row.result.length > 80 ? `${row.result.slice(0, 80)}…` : row.result) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div></div>
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  // 每个 session 的对话式 transcript（coordinator + 子 Agent），由事件流经 reducer 构建
  const [transcripts, setTranscripts] = useState<Record<string, TranscriptItem[]>>({});
  // session_id -> 面板显示名（优先事件的 agent_name，回落 agent_type/sessionId）
  const [agentNames, setAgentNames] = useState<Record<string, string>>({});
  // session_id -> 最近一次 Supervisor 审查（边栏展示当前阶段意见）
  const [supervisorReviews, setSupervisorReviews] = useState<Record<string, SupervisorReview>>({});
  const [query, setQuery] = useState("");
  const [workingDirectory, setWorkingDirectory] = useState(() => localStorage.getItem(WORKING_DIRECTORY_KEY) ?? "");
  const [yolo, setYolo] = useState(() => localStorage.getItem(YOLO_KEY) === "1");
  const [token, setToken] = useState(tokenStore.get());
  const [tokenOpen, setTokenOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const streamRef = useRef<AbortController | null>(null);
  // 当前主 SSE 对应的 session_id，用于丢弃旧流的迟到事件
  const streamSessionIdRef = useRef<string | null>(null);
  const childStreamsRef = useRef<Map<string, AbortController>>(new Map());
  // transcript 事件的 ref 缓冲：约 120ms 批量 fold 进 transcripts state，避免每个事件触发整树渲染
  const transcriptBufferRef = useRef<Record<string, SessionEvent[]>>({});
  const flushTimerRef = useRef<number | null>(null);
  // 用户是否停留在底部附近（距底 <80px），决定内容更新时是否跟随滚动
  const followRef = useRef(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  const scheduleStreamFlush = () => {
    if (flushTimerRef.current !== null) return;
    flushTimerRef.current = window.setTimeout(() => {
      flushTimerRef.current = null;
      const pending = transcriptBufferRef.current;
      transcriptBufferRef.current = {};
      const entries = Object.entries(pending);
      if (!entries.length) return;
      setTranscripts((current) => {
        const next = { ...current };
        for (const [sessionId, pendingEvents] of entries) {
          next[sessionId] = pendingEvents.reduce(applyTranscriptEvent, next[sessionId] ?? []);
        }
        return next;
      });
    }, 120);
  };

  // 把一条 transcript 事件（llm_chunk/tool_*/llm_stream_end）排入缓冲，顺带记录 agent 显示名
  const bufferTranscriptEvent = (sessionId: string, event: SessionEvent) => {
    (transcriptBufferRef.current[sessionId] ??= []).push(event);
    if (event.data.agent_name) {
      const name = String(event.data.agent_name);
      setAgentNames((current) => (current[sessionId] ? current : { ...current, [sessionId]: name }));
    }
    scheduleStreamFlush();
  };

  // 清空所有 transcript 状态（切换/新建/删除会话时调用）
  const resetTranscripts = () => {
    transcriptBufferRef.current = {};
    setTranscripts({});
    setAgentNames({});
    setSupervisorReviews({});
  };

  // 记录一条 supervisor_review 事件（低频事件，直接 set，不走缓冲）
  const captureSupervisorReview = (sessionId: string, event: SessionEvent) => {
    setSupervisorReviews((current) => ({ ...current, [sessionId]: parseSupervisorReview(event) }));
  };

  // REST 回放：把全量事件中的 transcript 事件重建为气泡（同时回填显示名与 Supervisor 审查）
  const replayTranscript = (sessionId: string, list: SessionEvent[]) => {
    const relevant = list
      .filter((event) => transcriptEventTypes.has(event.event_type))
      .sort((a, b) => a.id - b.id);
    setTranscripts((current) => ({ ...current, [sessionId]: buildTranscript(relevant) }));
    const named = relevant.find((event) => event.data.agent_name);
    if (named?.data.agent_name) {
      const name = String(named.data.agent_name);
      setAgentNames((current) => (current[sessionId] ? current : { ...current, [sessionId]: name }));
    }
    const review = [...list].reverse().find((event) => event.event_type === "supervisor_review");
    if (review) captureSupervisorReview(sessionId, review);
  };

  const toggleYolo = (checked: boolean) => {
    setYolo(checked);
    if (checked) localStorage.setItem(YOLO_KEY, "1");
    else localStorage.removeItem(YOLO_KEY);
  };

  const health = useQuery({
    queryKey: ["health"], queryFn: api.health, retry: 5, retryDelay: 1_000, refetchInterval: 10_000
  });
  const conversations = useQuery({ queryKey: ["conversations", token], queryFn: api.conversations });
  const messages = useQuery({
    queryKey: ["messages", conversationId, token],
    queryFn: () => api.messages(conversationId!), enabled: Boolean(conversationId)
  });
  const sessions = useQuery({
    queryKey: ["sessions", conversationId, token],
    queryFn: () => api.sessions(conversationId!), enabled: Boolean(conversationId),
    // 仅在活跃 Session 未终态时轮询，用于发现协调者动态拉起的子 Agent session
    refetchInterval: activeSession && !terminalStates.has(activeSession.state) ? 3_000 : false
  });
  const approvals = useQuery({
    queryKey: ["approvals", token], queryFn: api.approvals,
    // 有运行中会话时才需要盯审批
    refetchInterval: activeSession && !terminalStates.has(activeSession.state) ? 3_000 : false
  });

  useEffect(() => {
    if (!conversationId && conversations.data?.length) setConversationId(conversations.data[0].id);
  }, [conversationId, conversations.data]);

  // 监听窗口滚动：仅当用户距底部 <80px 时跟随新内容滚动，上翻阅读不被打断
  useEffect(() => {
    const onScroll = () => {
      followRef.current = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 80;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (followRef.current) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events, messages.data, transcripts]);

  useEffect(() => () => {
    streamRef.current?.abort();
    if (flushTimerRef.current !== null) window.clearTimeout(flushTimerRef.current);
  }, []);

  useEffect(() => {
    if (!conversationId || !sessions.data?.length || activeSession) return;
    const latest = sessions.data[0];
    setActiveSession(latest);
    api.sessionEvents(conversationId, latest.session_id)
      .then((list) => {
        setEvents((current) => mergeEventsById(current, list));
        // 终态 session 没有 SSE，用 REST 全量回放重建 transcript；
        // 未终态的由 startStream 的 SSE 从头重建，避免双通道重复折叠
        if (terminalStates.has(latest.state)) replayTranscript(latest.session_id, list);
      })
      .catch(() => setEvents([]));
    if (!terminalStates.has(latest.state)) startStream(latest, conversationId);
  // startStream intentionally uses the current component state and is only invoked on a new selection.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, sessions.data, activeSession]);

  const createConversation = useMutation({
    mutationFn: api.createConversation,
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      setConversationId(conversation.id);
      setActiveSession(null);
      setEvents([]);
      resetTranscripts();
    }
  });

  const startStream = (session: Session, convId = conversationId!) => {
    streamRef.current?.abort();
    const controller = new AbortController();
    streamRef.current = controller;
    streamSessionIdRef.current = session.session_id;
    setActiveSession(session);
    setEvents([]);
    delete transcriptBufferRef.current[session.session_id];
    setTranscripts((current) => {
      const next = { ...current };
      delete next[session.session_id];
      return next;
    });
    void streamSession(convId, session.session_id, (event) => {
      if (streamSessionIdRef.current !== session.session_id) return; // 旧流的迟到事件直接丢弃
      if (event.event_type === "llm_chunk") {
        bufferTranscriptEvent(session.session_id, event);
        return;
      }
      if (transcriptEventTypes.has(event.event_type)) bufferTranscriptEvent(session.session_id, event);
      if (event.event_type === "supervisor_review") captureSupervisorReview(session.session_id, event);
      setEvents((current) => current.some((item) => item.id === event.id) ? current : [...current, event]);
      if (terminalStates.has(event.event_type)) {
        queryClient.invalidateQueries({ queryKey: ["messages", convId] });
        queryClient.invalidateQueries({ queryKey: ["sessions", convId] });
        api.session(convId, session.session_id).then(setActiveSession).catch(() => undefined);
      }
    }, controller.signal).catch((error) => {
      if (!controller.signal.aborted) {
        setEvents((current) => [...current, {
          id: -Date.now(), event_type: "failed", data: { error: String(error) }, created_at: new Date().toISOString()
        }]);
      }
    });
  };

  // 为活跃子 Agent session 各开一条 SSE，累积它们的 transcript 事件
  useEffect(() => {
    if (!conversationId || !activeSession || !sessions.data) return;
    const children = sessions.data.filter(
      (item) => item.parent_session_id === activeSession.session_id && !terminalStates.has(item.state)
    );
    for (const child of children) {
      if (childStreamsRef.current.has(child.session_id)) continue;
      const controller = new AbortController();
      childStreamsRef.current.set(child.session_id, controller);
      void streamSession(conversationId, child.session_id, (event) => {
        if (transcriptEventTypes.has(event.event_type)) bufferTranscriptEvent(child.session_id, event);
        if (event.event_type === "supervisor_review") captureSupervisorReview(child.session_id, event);
        if (terminalStates.has(event.event_type)) {
          childStreamsRef.current.delete(child.session_id);
          queryClient.invalidateQueries({ queryKey: ["sessions", conversationId] });
        }
      }, controller.signal).catch(() => {
        childStreamsRef.current.delete(child.session_id);
      });
    }
  }, [conversationId, activeSession, sessions.data, queryClient]);

  // 切换会话/会话结束时清理子流
  useEffect(() => {
    return () => {
      childStreamsRef.current.forEach((controller) => controller.abort());
      childStreamsRef.current.clear();
    };
  }, [conversationId, activeSession?.session_id]);

  const submit = useMutation({
    mutationFn: async () => {
      let convId = conversationId;
      if (!convId) convId = (await api.createConversation()).id;
      const directory = workingDirectory.trim();
      const session = await api.createSession(convId, query.trim(), directory, yolo);
      if (directory) localStorage.setItem(WORKING_DIRECTORY_KEY, directory);
      else localStorage.removeItem(WORKING_DIRECTORY_KEY);
      return { convId, session };
    },
    onSuccess: ({ convId, session }) => {
      setConversationId(convId);
      setQuery("");
      followRef.current = true;
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["messages", convId] });
      queryClient.invalidateQueries({ queryKey: ["sessions", convId] });
      startStream(session, convId);
    }
  });

  const cancel = useMutation({
    mutationFn: () => api.cancelSession(conversationId!, activeSession!.session_id),
    onSuccess: (session) => setActiveSession(session)
  });

  const decide = useMutation({
    mutationFn: ({ approval, decision }: { approval: Approval; decision: "approved" | "denied" }) =>
      api.decideApproval(approval, decision),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["approvals"] })
  });

  const deleteAll = useMutation({
    mutationFn: api.deleteAllConversations,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      setConversationId(null);
      setActiveSession(null);
      setEvents([]);
      resetTranscripts();
      setClearOpen(false);
    }
  });

  const visibleApprovals = useMemo(
    () => approvals.data?.filter((item) => !conversationId || item.conversation_id === conversationId) ?? [],
    [approvals.data, conversationId]
  );
  const isRunning = activeSession && !terminalStates.has(activeSession.state);

  // 当前可见 session（主 session + 其子 Agent）中最新的一条 Supervisor 审查，供右侧边栏展示
  const latestReview = useMemo(() => {
    if (!activeSession) return null;
    const ids = [
      activeSession.session_id,
      ...(sessions.data?.filter((item) => item.parent_session_id === activeSession.session_id).map((item) => item.session_id) ?? [])
    ];
    let latest: (SupervisorReview & { sessionId: string }) | null = null;
    for (const id of ids) {
      const review = supervisorReviews[id];
      if (review && (!latest || String(review.time ?? "") > String(latest.time ?? ""))) {
        latest = { ...review, sessionId: id };
      }
    }
    return latest;
  }, [activeSession, sessions.data, supervisorReviews]);

  const saveToken = () => {
    tokenStore.set(token.trim());
    setTokenOpen(false);
    queryClient.clear();
    conversations.refetch();
  };

  const chooseWorkingDirectory = async () => {
    if (!isDesktop || isRunning) return;
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({ directory: true, multiple: false, title: "选择 Cloudra 工作目录" });
    if (typeof selected === "string") setWorkingDirectory(selected);
  };

  return (
    <div className={`shell ${latestReview ? "with-supervisor" : ""}`}>
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="brand"><div className="brand-mark">C</div><div><strong>Cloudra</strong><small>科研协作工作台</small></div></div>
        <button className="block-button" onClick={() => createConversation.mutate()}><Plus size={15} /> 新对话</button>
        <div className="section-label">对话记录</div>
        <nav className="conversation-list">
          {conversations.isError && <div className="muted error">{String(conversations.error)}</div>}
          {conversations.data?.map((conversation) => (
            <button key={conversation.id} className={conversation.id === conversationId ? "selected" : ""}
              onClick={() => {
                streamRef.current?.abort();
                streamSessionIdRef.current = null;
                setConversationId(conversation.id);
                setActiveSession(null);
                setEvents([]);
                resetTranscripts();
                followRef.current = true;
                setSidebarOpen(false);
              }}>
              <span>{shortId(conversation.id)}</span>
              <small>{[stateLabel(conversation.state), shortDateTime(conversation.last_active)].filter(Boolean).join(" · ")}</small>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button className="text-button" onClick={() => setSettingsOpen(true)}><Settings size={14} /> 设置</button>
          <button className="text-button" onClick={() => setSkillsOpen(true)}><Sparkles size={14} /> Skills</button>
          <button className="text-button" onClick={() => setSessionsOpen(true)}><Activity size={14} /> Sessions 监控</button>
          <button className="text-button" onClick={() => setTokenOpen(true)}><KeyRound size={14} /> API 密钥</button>
          <button className="text-button danger" disabled={deleteAll.isPending}
            onClick={() => setClearOpen(true)}>
            <Trash2 size={14} /> 清空会话
          </button>
          <span className={`connection ${health.isSuccess ? "online" : "offline"}`}>
            <i /> {health.isSuccess ? `${isDesktop ? "桌面服务" : "本地服务"} · v${health.data.version}` : "正在连接本地服务"}
          </span>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(true)}><Menu size={17} /></button>
          <div><div className="eyebrow">当前对话</div><h1>{conversationId ? shortId(conversationId) : "未选择对话"}</h1></div>
          {sessions.data && sessions.data.length > 1 && <select className="session-select" value={activeSession?.session_id ?? ""}
            onChange={(event) => {
              const selected = sessions.data?.find((item) => item.session_id === event.target.value) ?? null;
              streamRef.current?.abort();
              streamSessionIdRef.current = null;
              setActiveSession(selected);
              setEvents([]);
              if (selected && conversationId) {
                api.sessionEvents(conversationId, selected.session_id)
                  .then((list) => {
                    setEvents((current) => mergeEventsById(current, list));
                    if (terminalStates.has(selected.state)) replayTranscript(selected.session_id, list);
                  })
                  .catch(() => setEvents([]));
                if (!terminalStates.has(selected.state)) startStream(selected, conversationId);
              }
            }}>
            {sessions.data.map((session) => <option value={session.session_id} key={session.session_id}>{shortId(session.session_id)} · {stateLabel(session.state)}</option>)}
          </select>}
          <button className="icon-button" disabled={!conversationId} onClick={() => setLogsOpen(true)} title="查看运行日志">
            <ScrollText size={16} />
          </button>
          <div className={`state-chip ${activeSession?.state ?? "idle"}`}><i />{stateLabel(activeSession?.state)}</div>
        </header>

        <section className="content">
          {!conversationId && !conversations.isLoading && (
            <div className="empty"><span>□</span><h2>开始一段研究对话</h2><p>输入问题后，系统会创建 Conversation 和第一个 Coordinator Session。</p></div>
          )}
          <div className="messages">
            {messages.data?.filter((message) => message.role !== "system" && messageText(message)).map((message, index) => (
              <MessageItem message={message} key={`${message.role}-${index}`} />
            ))}
          </div>

          {(activeSession || events.length > 0) && (
            <section className="runtime">
              <div className="runtime-head"><span>运行轨迹</span><code>{activeSession ? shortId(activeSession.session_id) : "--"}</code></div>
              <div className="event-list">
                {events.map((event) => {
                  const label = eventLabel(event);
                  if (label === null) return null;
                  return (
                    <div className={`event ${event.event_type}`} key={event.id}>
                      <time>{time(event.created_at)}</time><i /><span>{label}</span>
                    </div>
                  );
                })}
                {activeSession?.error && <div className="event failed"><time>ERR</time><i /><span>{activeSession.error}</span></div>}
              </div>
              {/* 对话式 transcript：activeSession 恒在最上，其后是它的子 Agent session */}
              {activeSession && (() => {
                const children = sessions.data?.filter(
                  (item) => item.parent_session_id === activeSession.session_id
                ) ?? [];
                return [activeSession, ...children].map((session) => {
                  const items = transcripts[session.session_id] ?? [];
                  const active = !terminalStates.has(session.state);
                  if (!active && items.length === 0) return null;
                  const name = agentNames[session.session_id] ?? session.agent_type ?? shortId(session.session_id);
                  return <TranscriptPanel key={session.session_id} name={name} active={active} items={items} />;
                });
              })()}
              {/* 最终总结只显示当前主 session（通常是 coordinator）的 result，固定在对话末尾 */}
              {activeSession && terminalStates.has(activeSession.state) && activeSession.result && (
                <div className="bubble bubble-result">
                  <div className="bubble-result-label">最终结果</div>
                  <div className="message-text"><ReactMarkdown>{displayResult(activeSession.result)}</ReactMarkdown></div>
                </div>
              )}
            </section>
          )}

          {visibleApprovals.map((approval) => (
            <section className="approval" key={`${approval.conversation_id}-${approval.id}`}>
              <div><div className="eyebrow">需要你的确认</div><pre>{approval.details}</pre></div>
              <div className="approval-actions">
                <button onClick={() => decide.mutate({ approval, decision: "denied" })}><X size={14} /> 拒绝</button>
                <button className="inverse" onClick={() => decide.mutate({ approval, decision: "approved" })}><Check size={14} /> 允许</button>
              </div>
            </section>
          ))}
          <div ref={bottomRef} />
        </section>

        <footer className="composer">
          <div className="directory-field">
            <FolderOpen size={15} />
            <span>工作目录</span>
            <input aria-label="工作目录" value={workingDirectory} onChange={(event) => setWorkingDirectory(event.target.value)}
              disabled={Boolean(isRunning)} placeholder="留空则使用服务启动目录" />
            {isDesktop && <button type="button" className="directory-picker" disabled={Boolean(isRunning)}
              onClick={chooseWorkingDirectory}>选择…</button>}
            <label className="yolo-check" title="危险操作由 LLM 自动审批（等价 CLI 的 --yolo）">
              <input type="checkbox" checked={yolo} disabled={Boolean(isRunning)}
                onChange={(event) => toggleYolo(event.target.checked)} />
              YOLO 自动审批
            </label>
          </div>
          <textarea value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入研究任务…"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (query.trim() && !submit.isPending && !isRunning) submit.mutate();
              }
            }} />
          {isRunning ? (
            <button
              className="send stop"
              disabled={cancel.isPending || activeSession?.state === "cancel_requested"}
              onClick={() => cancel.mutate()}
              title={activeSession?.state === "cancel_requested" ? "正在取消…" : "打断 Session"}
            >
              <Square size={16} />
            </button>
          ) : (
            <button className="send" disabled={!query.trim() || submit.isPending} onClick={() => submit.mutate()} title="提交"><Send size={16} /></button>
          )}
          {submit.isError && <div className="composer-error">{String(submit.error)}</div>}
          <div className="composer-note">Enter 发送 · Shift + Enter 换行</div>
        </footer>
      </main>

      {tokenOpen && <div className="modal-backdrop" onClick={() => setTokenOpen(false)}><div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head"><span>API 密钥</span><button className="icon-button" onClick={() => setTokenOpen(false)}><X size={16} /></button></div>
        <p>本机未设置密钥时可以留空。密钥只保存在当前设备。</p>
        <input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Bearer token" />
        <button className="block-button" onClick={saveToken}>保存并重新连接</button>
      </div></div>}

      {clearOpen && <div className="modal-backdrop" onClick={() => setClearOpen(false)}><div className="modal warning" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head"><span><TriangleAlert size={15} /> 清空所有会话</span><button className="icon-button" onClick={() => setClearOpen(false)}><X size={16} /></button></div>
        <p>此操作会<strong>永久删除</strong>所有 Conversation、Session、消息和审批记录，且无法撤销。</p>
        <p>当前会话数：<strong>{conversations.data?.length ?? 0}</strong></p>
        <div className="modal-actions">
          <button className="block-button" onClick={() => setClearOpen(false)}>取消</button>
          <button className="block-button warning" disabled={deleteAll.isPending} onClick={() => deleteAll.mutate()}>确认删除</button>
        </div>
      </div></div>}

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
      {skillsOpen && <SkillsModal onClose={() => setSkillsOpen(false)} />}
      {sessionsOpen && <SessionsModal onClose={() => setSessionsOpen(false)} />}
      {logsOpen && conversationId && <LogsModal conversationId={conversationId} onClose={() => setLogsOpen(false)} />}

      {latestReview && (
        <aside className="supervisor-side">
          <div className="section-label">Supervisor 意见</div>
          <div className={`supervisor-card ${latestReview.verdict}`}>
            <div className="supervisor-card-head">
              <span className="supervisor-verdict">{verdictLabel(latestReview.verdict)}</span>
              <small>{agentNames[latestReview.sessionId] ?? latestReview.agentName ?? shortId(latestReview.sessionId)}</small>
            </div>
            {latestReview.reasoning && <p>{latestReview.reasoning}</p>}
            {latestReview.advice.length > 0 && (
              <ul>{latestReview.advice.map((item, index) => <li key={index}>{item}</li>)}</ul>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
