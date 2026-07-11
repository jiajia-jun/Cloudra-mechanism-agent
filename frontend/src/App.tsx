import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound, Menu, Plus, Send, Square, Trash2, TriangleAlert, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { api, streamSession, tokenStore } from "./api";
import type { Approval, Message, Session, SessionEvent } from "./types";

// sleeping 是旧版本 Session 的完成状态，保留兼容，避免为历史 Session 打开无尽 SSE。
const terminalStates = new Set(["completed", "sleeping", "failed", "cancelled", "killed", "interrupted"]);

function shortId(value: string) {
  return value.length > 22 ? `${value.slice(0, 12)}…${value.slice(-7)}` : value;
}

function time(value?: string | null) {
  if (!value) return "--:--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "--:--" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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
  const labels: Record<string, string> = {
    queued: "已进入队列", running: "开始运行", completed: "运行完成",
    failed: "运行失败", cancelled: "已取消", interrupted: "运行中断"
  };
  return labels[event.event_type] ?? event.event_type;
}

export default function App() {
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [query, setQuery] = useState("");
  const [token, setToken] = useState(tokenStore.get());
  const [tokenOpen, setTokenOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const streamRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const conversations = useQuery({ queryKey: ["conversations", token], queryFn: api.conversations });
  const messages = useQuery({
    queryKey: ["messages", conversationId, token],
    queryFn: () => api.messages(conversationId!), enabled: Boolean(conversationId)
  });
  const sessions = useQuery({
    queryKey: ["sessions", conversationId, token],
    queryFn: () => api.sessions(conversationId!), enabled: Boolean(conversationId)
  });
  const approvals = useQuery({
    queryKey: ["approvals", token], queryFn: api.approvals, refetchInterval: 3_000
  });

  useEffect(() => {
    if (!conversationId && conversations.data?.length) setConversationId(conversations.data[0].id);
  }, [conversationId, conversations.data]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events, messages.data]);
  useEffect(() => () => streamRef.current?.abort(), []);
  useEffect(() => {
    if (!conversationId || !sessions.data?.length || activeSession) return;
    const latest = sessions.data[0];
    setActiveSession(latest);
    api.sessionEvents(conversationId, latest.session_id).then(setEvents).catch(() => setEvents([]));
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
    }
  });

  const startStream = (session: Session, convId = conversationId!) => {
    streamRef.current?.abort();
    const controller = new AbortController();
    streamRef.current = controller;
    setActiveSession(session);
    setEvents([]);
    void streamSession(convId, session.session_id, (event) => {
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

  const submit = useMutation({
    mutationFn: async () => {
      let convId = conversationId;
      if (!convId) convId = (await api.createConversation()).id;
      const session = await api.createSession(convId, query.trim());
      return { convId, session };
    },
    onSuccess: ({ convId, session }) => {
      setConversationId(convId);
      setQuery("");
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
      setClearOpen(false);
    }
  });

  const visibleApprovals = useMemo(
    () => approvals.data?.filter((item) => !conversationId || item.conversation_id === conversationId) ?? [],
    [approvals.data, conversationId]
  );
  const isRunning = activeSession && !terminalStates.has(activeSession.state);

  const saveToken = () => {
    tokenStore.set(token.trim());
    setTokenOpen(false);
    queryClient.clear();
    conversations.refetch();
  };

  return (
    <div className="shell">
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="brand"><div><strong>CLOUDRA</strong><small>RESEARCH CONSOLE</small></div></div>
        <button className="block-button" onClick={() => createConversation.mutate()}><Plus size={15} /> 新对话</button>
        <div className="section-label">CONVERSATIONS</div>
        <nav className="conversation-list">
          {conversations.isError && <div className="muted error">{String(conversations.error)}</div>}
          {conversations.data?.map((conversation) => (
            <button key={conversation.id} className={conversation.id === conversationId ? "selected" : ""}
              onClick={() => { setConversationId(conversation.id); setActiveSession(null); setEvents([]); setSidebarOpen(false); }}>
              <span>{shortId(conversation.id)}</span><small>{conversation.state}</small>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button className="text-button" onClick={() => setTokenOpen(true)}><KeyRound size={14} /> API TOKEN</button>
          <button className="text-button danger" disabled={deleteAll.isPending}
            onClick={() => setClearOpen(true)}>
            <Trash2 size={14} /> 清空会话
          </button>
          <span className="connection"><i /> LOCAL / 8000</span>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(true)}><Menu size={17} /></button>
          <div><div className="eyebrow">CURRENT CONVERSATION</div><h1>{conversationId ? shortId(conversationId) : "未选择对话"}</h1></div>
          {sessions.data && sessions.data.length > 1 && <select className="session-select" value={activeSession?.session_id ?? ""}
            onChange={(event) => {
              const selected = sessions.data?.find((item) => item.session_id === event.target.value) ?? null;
              streamRef.current?.abort(); setActiveSession(selected); setEvents([]);
              if (selected && conversationId) {
                api.sessionEvents(conversationId, selected.session_id).then(setEvents);
                if (!terminalStates.has(selected.state)) startStream(selected, conversationId);
              }
            }}>
            {sessions.data.map((session) => <option value={session.session_id} key={session.session_id}>{shortId(session.session_id)} · {session.state}</option>)}
          </select>}
          <div className={`state-chip ${activeSession?.state ?? "idle"}`}><i />{activeSession?.state ?? "idle"}</div>
        </header>

        <section className="content">
          {!conversationId && !conversations.isLoading && (
            <div className="empty"><span>□</span><h2>开始一段研究对话</h2><p>输入问题后，系统会创建 Conversation 和第一个 Coordinator Session。</p></div>
          )}
          <div className="messages">
            {messages.data?.filter((message) => message.role !== "system" && messageText(message)).map((message, index) => (
              <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <div className="message-meta">{message.role === "user" ? "YOU" : message.role.toUpperCase()}</div>
                <div className="message-body">
                  {message.role === "tool" ? (
                    <JsonView text={messageText(message)} />
                  ) : (
                    <div className="message-text">
                      <ReactMarkdown>{messageText(message)}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>

          {(activeSession || events.length > 0) && (
            <section className="runtime">
              <div className="runtime-head"><span>SESSION TRACE</span><code>{activeSession ? shortId(activeSession.session_id) : "--"}</code></div>
              <div className="event-list">
                {events.map((event) => (
                  <div className={`event ${event.event_type}`} key={event.id}>
                    <time>{time(event.created_at)}</time><i /><span>{eventLabel(event)}</span>
                  </div>
                ))}
                {activeSession?.error && <div className="event failed"><time>ERR</time><i /><span>{activeSession.error}</span></div>}
              </div>
            </section>
          )}

          {visibleApprovals.map((approval) => (
            <section className="approval" key={`${approval.conversation_id}-${approval.id}`}>
              <div><div className="eyebrow">APPROVAL REQUIRED</div><pre>{approval.details}</pre></div>
              <div className="approval-actions">
                <button onClick={() => decide.mutate({ approval, decision: "denied" })}><X size={14} /> 拒绝</button>
                <button className="inverse" onClick={() => decide.mutate({ approval, decision: "approved" })}><Check size={14} /> 允许</button>
              </div>
            </section>
          ))}
          <div ref={bottomRef} />
        </section>

        <footer className="composer">
          <textarea value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入研究任务…"
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); if (query.trim()) submit.mutate(); } }} />
          {isRunning ? (
            <button className="send stop" onClick={() => cancel.mutate()} title="取消 Session"><Square size={16} /></button>
          ) : (
            <button className="send" disabled={!query.trim() || submit.isPending} onClick={() => submit.mutate()} title="提交"><Send size={16} /></button>
          )}
          <div className="composer-note">ENTER 发送 · SHIFT+ENTER 换行</div>
        </footer>
      </main>

      {tokenOpen && <div className="modal-backdrop" onClick={() => setTokenOpen(false)}><div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head"><span>API TOKEN</span><button className="icon-button" onClick={() => setTokenOpen(false)}><X size={16} /></button></div>
        <p>本机未设置 Token 时留空。Token 只保存在当前浏览器的 localStorage。</p>
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
    </div>
  );
}
