import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, streamProject } from './api';
import Markdown from './Markdown';
import DagPanel from './DagPanel';
import type { Agent, EventEnvelope, Project } from './types';
import {
  applyStreamEvent,
  buildTimeline,
  type MessageItem,
  type StreamView,
  type ThinkingItem,
  type TimelineItem,
  type ToolItem,
} from './timeline';

/* ------------------------------------------------------------------ helpers */

type ToastKind = 'error' | 'ok' | 'info';
interface Toast { id: number; kind: ToastKind; text: string }

let toastSeq = 0;

function short(text: unknown, max = 80): string {
  const s = typeof text === 'string' ? text : JSON.stringify(text);
  if (!s) return '';
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function dedupeAgents(list: Agent[]): Agent[] {
  const seen = new Map<string, Agent>();
  for (const a of list) seen.set(a.id, a);
  return [...seen.values()];
}

/* ------------------------------------------------------------------ app */

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const [streamView, setStreamView] = useState<StreamView>({ streamText: '', frozen: [] });
  const [thinkingItems, setThinkingItems] = useState<ThinkingItem[]>([]);
  const [pendingMessages, setPendingMessages] = useState<MessageItem[]>([]);
  const [roles, setRoles] = useState<Array<{ role_id: string; display_name: string }>>([]);
  const [draft, setDraft] = useState('');
  const [newProject, setNewProject] = useState('');
  const [newProjectWs, setNewProjectWs] = useState('');
  const [sending, setSending] = useState(false);
  const [connState, setConnState] = useState<'connecting' | 'live' | 'offline'>('connecting');
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [approvals, setApprovals] = useState<Array<Record<string, unknown>>>([]);
  const [interactions, setInteractions] = useState<Array<Record<string, unknown>>>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventEnvelope | null>(null);
  const [expandedAgents, setExpandedAgents] = useState<Set<string>>(new Set());

  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;
  const activeAgent = agents.find((a) => a.id === activeAgentId) ?? null;

  // Sidebar grouping: projects bucketed by workspace_dir ('' = no workspace,
  // sorted last).
  const groupedProjects = useMemo(() => {
    const groups = new Map<string, Project[]>();
    for (const p of projects) {
      const key = p.workspace_dir ?? '';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(p);
    }
    return [...groups.entries()].sort(([a], [b]) =>
      a === '' ? 1 : b === '' ? -1 : a.localeCompare(b),
    );
  }, [projects]);

  // Refs so the long-lived SSE subscription always sees current values.
  const activeAgentIdRef = useRef(activeAgentId);
  activeAgentIdRef.current = activeAgentId;
  // Highest session_seq seen for the visible agent (chunks carry seq 0, so
  // thinking segments anchor to the last real event before them).
  const maxSeqRef = useRef(0);
  const thinkingIdRef = useRef(0);

  const pushToast = useCallback((kind: ToastKind, text: string) => {
    const id = ++toastSeq;
    setToasts((prev) => [...prev.slice(-4), { id, kind, text }]);
    window.setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000);
  }, []);
  const reportError = useCallback(
    (e: unknown) => pushToast('error', e instanceof Error ? e.message : String(e)),
    [pushToast],
  );

  /* ------------------------------------------------------- initial loading */

  useEffect(() => {
    api.listProjects().then(setProjects).catch(reportError);
    api.listRoles().then(setRoles).catch(reportError);
  }, [reportError]);

  /* ---------------------------------------------------- project switching */

  const selectAgent = useCallback(
    async (agentId: string) => {
      setActiveAgentId(agentId);
      setPendingMessages([]);
      setStreamView({ streamText: '', frozen: [] });
      setThinkingItems([]);
      maxSeqRef.current = 0;
      setSelectedEvent(null);
      try {
        const [agent, eventList] = await Promise.all([api.getAgent(agentId), api.events(agentId)]);
        setAgents((prev) =>
          dedupeAgents(
            prev.some((a) => a.id === agentId)
              ? prev.map((a) => (a.id === agentId ? agent : a))
              : [...prev, agent],
          ),
        );
        setEvents(eventList);
        // Anchors for future thinking segments must account for the fetched
        // history — otherwise the first chunks land at seq 0.5, above the
        // triggering user message, and no SSE echo ever re-bases them.
        maxSeqRef.current = eventList.reduce((m, e) => Math.max(m, e.session_seq ?? 0), 0);
      } catch (e) {
        reportError(e);
      }
    },
    [reportError],
  );

  useEffect(() => {
    if (!activeProjectId) return;
    setAgents([]);
    setActiveAgentId(null);
    setEvents([]);
    setStreamView({ streamText: '', frozen: [] });
    setThinkingItems([]);
    maxSeqRef.current = 0;
    setPendingMessages([]);
    setSelectedEvent(null);
    api
      .listAgents(activeProjectId)
      .then((list) => {
        const agents = dedupeAgents(list);
        setAgents(agents);
        if (agents[0]) void selectAgent(agents[0].id);
      })
      .catch(reportError);
  }, [activeProjectId, selectAgent, reportError]);

  /* ------------------------------------------------------------ SSE stream */

  useEffect(() => {
    if (!activeProjectId) return;
    setConnState('connecting');
    let cursor = 0;
    // History replays from cursor 0 on every (re)connect; side-effect toasts
    // must only fire for events after the replay boundary (project.synced).
    let replaying = true;
    const source = streamProject(activeProjectId, cursor, {
      onOpen: () => setConnState('live'),
      onError: () => setConnState('offline'),
      onEvent: (event) => {
        if (event.type === 'project.synced') {
          replaying = false;
          return;
        }
        cursor = Math.max(cursor, event.seq);
        const sessionId = event.session_id;
        // Agent list / chip state updates, regardless of selection.
        if (event.type === 'agent.spawned' && activeProjectId) {
          api
            .listAgents(activeProjectId)
            .then((list) => setAgents(dedupeAgents(list)))
            .catch(() => undefined);
          // Surface the new sub-agent: auto-expand its parent's chip.
          const parentId = event.data?.parent_session_id;
          if (typeof parentId === 'string' && parentId) {
            setExpandedAgents((prev) => new Set(prev).add(parentId));
          }
        }
        if (event.type === 'agent.state_changed' && sessionId) {
          const to = String(event.data.to ?? '');
          setAgents((prev) =>
            dedupeAgents(prev.map((a) => (a.id === sessionId ? { ...a, state: to } : a))),
          );
        }
        if (event.type === 'approval.requested' || event.type === 'tool.approval_requested') {
          if (!replaying) {
            pushToast('info', `Approval requested: ${short(event.data.tool_name ?? event.data.message ?? '', 60)}`);
          }
          if (activeProjectId) api.approvals(activeProjectId).then(setApprovals).catch(() => undefined);
        }
        if (event.type === 'approval.decided' && activeProjectId) {
          api.approvals(activeProjectId).then(setApprovals).catch(() => undefined);
        }
        if (event.type === 'interaction.requested' && activeProjectId) {
          api.interactions(activeProjectId).then(setInteractions).catch(() => undefined);
        }
        // Timeline events for the visible agent.
        if (sessionId && sessionId === activeAgentIdRef.current) {
          // Token-level streaming: llm.chunk never enters the event list.
          // Reasoning deltas accumulate into per-LLM-call thinking segments
          // interleaved between tool rows; content deltas feed the live bubble
          // which applyStreamEvent freezes into the timeline so a later tool
          // round cannot swallow it.
          if (event.type === 'llm.chunk') {
            const delta = String(event.data.delta ?? '');
            if (event.data.kind === 'reasoning') {
              setThinkingItems((prev) => {
                const last = prev[prev.length - 1];
                if (last?.live) {
                  return [...prev.slice(0, -1), { ...last, text: last.text + delta }];
                }
                return [
                  ...prev,
                  {
                    kind: 'thinking',
                    id: `th-${++thinkingIdRef.current}`,
                    seq: maxSeqRef.current + 0.5,
                    text: delta,
                    live: true,
                  },
                ];
              });
            } else {
              setStreamView((prev) => applyStreamEvent(prev, event));
            }
            return;
          }
          maxSeqRef.current = Math.max(maxSeqRef.current, event.session_seq ?? 0);
          if (event.type === 'agent.message_injected') {
            // The triggering user message belongs *before* this turn's
            // thinking, even when its echo arrives after the first chunks:
            // re-anchor the open segment just after it instead of closing.
            const anchor = (event.session_seq ?? 0) + 0.5;
            setThinkingItems((prev) => {
              const last = prev[prev.length - 1];
              return last?.live ? [...prev.slice(0, -1), { ...last, seq: anchor }] : prev;
            });
          } else if (event.type === 'agent.thinking') {
            // The persisted segment replaces its transient streamed copy —
            // without this the same reasoning would render twice.
            const persisted = String(event.data.content ?? '');
            setThinkingItems((prev) => {
              const last = prev[prev.length - 1];
              if (
                last &&
                (last.text === persisted ||
                  persisted.startsWith(last.text) ||
                  last.text.startsWith(persisted))
              ) {
                return prev.slice(0, -1);
              }
              return prev;
            });
          } else {
            // Any other real event ends the currently streaming segment.
            setThinkingItems((prev) => {
              const last = prev[prev.length - 1];
              return last?.live ? [...prev.slice(0, -1), { ...last, live: false }] : prev;
            });
          }
          setStreamView((prev) => applyStreamEvent(prev, event));
          setEvents((prev) => {
            if (prev.some((e) => e.event_id === event.event_id)) return prev;
            return [...prev, event].slice(-500);
          });
          if (event.type === 'agent.message_injected') {
            const content = String(event.data.content ?? '');
            setPendingMessages((prev) => {
              const idx = prev.findIndex((m) => m.content === content);
              return idx === -1 ? prev : prev.filter((_, i) => i !== idx);
            });
          }
          if (event.type === 'llm.failed' && !replaying) {
            pushToast('error', `LLM failed: ${short(event.data.error ?? event.data.message ?? '', 100)}`);
          }
        }
      },
    });
    return () => source.close();
  }, [activeProjectId, pushToast]);

  /* -------------------------------------------------- approvals polling */

  useEffect(() => {
    if (!activeProjectId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const [a, i] = await Promise.all([
          api.approvals(activeProjectId),
          api.interactions(activeProjectId),
        ]);
        if (cancelled) return;
        setApprovals(a);
        setInteractions(i);
      } catch {
        /* polling errors are transient */
      }
    };
    void poll();
    const timer = window.setInterval(poll, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeProjectId]);

  /* ------------------------------------------------------------- actions */

  async function createProjectAndSelect() {
    const name = newProject.trim();
    if (!name) return;
    try {
      const resp = await api.createProject(name, newProjectWs.trim() || undefined);
      const list = await api.listProjects();
      setProjects(list);
      setActiveProjectId(resp.data.id);
      setNewProject('');
      setNewProjectWs('');
      pushToast('ok', `Project "${name}" created`);
    } catch (e) {
      reportError(e);
    }
  }

  async function changeWorkspace(dir: string) {
    if (!activeProject) return;
    const value = dir.trim() || null;
    if (value === (activeProject.workspace_dir ?? null)) return;
    try {
      const resp = await api.patchProject(activeProject.id, { workspace_dir: value });
      setProjects((prev) => prev.map((p) => (p.id === activeProject.id ? resp.data : p)));
      pushToast('ok', value ? `Workspace → ${value}` : 'Workspace cleared');
    } catch (e) {
      reportError(e);
    }
  }

  async function sendMessage() {
    const content = draft.trim();
    if (!content || !activeProject || sending) return;
    setSending(true);
    try {
      if (!activeAgent) {
        const resp = await api.spawnAgent(activeProject.id, {
          role_id: 'coordinator',
          query: content,
          settings: { orchestration_mode: activeProject.settings.orchestration_mode },
        });
        setDraft('');
        await selectAgent(resp.data.id);
      } else {
        // Optimistic echo; reconciled when the SSE echo arrives.
        setPendingMessages((prev) => [
          ...prev,
          { kind: 'message', id: `pending-${Date.now()}`, seq: Number.MAX_SAFE_INTEGER, sender: 'user', senderLabel: 'user', content, pending: true },
        ]);
        setDraft('');
        await api.sendMessage(activeAgent.id, content);
      }
    } catch (e) {
      setPendingMessages((prev) => prev.filter((m) => m.content !== content));
      reportError(e);
    } finally {
      setSending(false);
    }
  }

  async function spawnRole(roleId: string) {
    if (!activeProject || !roleId) return;
    try {
      const resp = await api.spawnAgent(activeProject.id, {
        role_id: roleId,
        settings: { orchestration_mode: activeProject.settings.orchestration_mode },
      });
      await selectAgent(resp.data.id);
      pushToast('ok', `Spawned ${roleId}`);
    } catch (e) {
      reportError(e);
    }
  }

  async function changeOrchestrationMode(mode: string) {
    if (!activeProject) return;
    try {
      const resp = await api.patchProject(activeProject.id, {
        settings: {
          orchestration_mode: mode,
          // The wire shape of `defaults` carries explicit nulls for every
          // unset field; never echo those back into a patch.
          defaults: Object.fromEntries(
            Object.entries({ ...activeProject.settings.defaults, orchestration_mode: mode }).filter(
              ([, v]) => v !== null && v !== undefined,
            ),
          ),
        },
      });
      setProjects((prev) => prev.map((p) => (p.id === activeProject.id ? resp.data : p)));
      // Agents snapshot their settings at spawn time, so a mid-project mode
      // switch must also patch every existing agent for dag tools to see it.
      const targets = dedupeAgents(
        agents.filter((a) => a.project_id === activeProject.id && a.settings.orchestration_mode !== mode),
      );
      const updated = await Promise.all(
        targets.map((a) => api.patchSettings(a.id, { orchestration_mode: mode })),
      );
      if (updated.length > 0) {
        setAgents((prev) =>
          dedupeAgents(prev.map((a) => updated.find((u) => u.data.id === a.id)?.data ?? a)),
        );
      }
      pushToast('ok', `Orchestration mode → ${mode}`);
    } catch (e) {
      reportError(e);
    }
  }

  async function cancelAgent() {
    if (!activeAgent) return;
    try {
      const resp = await api.cancel(activeAgent.id);
      setAgents((prev) => dedupeAgents(prev.map((a) => (a.id === resp.data.id ? resp.data : a))));
      pushToast('ok', `Cancelled ${activeAgent.display_name}`);
    } catch (e) {
      reportError(e);
    }
  }

  async function toggleProjectYolo(checked: boolean) {
    if (!activeProject) return;
    try {
      // 项目级 YOLO：写进项目 defaults（新 spawn 的 agent 自动继承），并级联
      // PATCH 现存 agent（settings 是 spawn 时快照，patch_settings 原地生效）。
      // 注意 project settings 是整对象校验替换，orchestration_mode 必须带回。
      const resp = await api.patchProject(activeProject.id, {
        settings: {
          orchestration_mode: activeProject.settings.orchestration_mode,
          defaults: Object.fromEntries(
            Object.entries({ ...activeProject.settings.defaults, yolo: checked }).filter(
              ([, v]) => v !== null && v !== undefined,
            ),
          ),
        },
      });
      setProjects((prev) => prev.map((p) => (p.id === activeProject.id ? resp.data : p)));
      const targets = dedupeAgents(
        agents.filter((a) => a.project_id === activeProject.id && a.settings.yolo !== checked),
      );
      const updated = await Promise.all(targets.map((a) => api.patchSettings(a.id, { yolo: checked })));
      if (updated.length > 0) {
        setAgents((prev) =>
          dedupeAgents(prev.map((a) => updated.find((u) => u.data.id === a.id)?.data ?? a)),
        );
      }
      pushToast('ok', `YOLO ${checked ? 'on' : 'off'} (project-wide)`);
    } catch (e) {
      reportError(e);
    }
  }

  async function patchSettings(patch: Record<string, unknown>) {
    if (!activeAgent) return;
    try {
      // 单个 agent 的设置覆盖（项目级 YOLO 开关在 AgentBar）。
      const resp = await api.patchSettings(activeAgent.id, patch);
      setAgents((prev) => dedupeAgents(prev.map((a) => (a.id === activeAgent.id ? resp.data : a))));
      pushToast('ok', 'Settings saved');
    } catch (e) {
      reportError(e);
    }
  }

  /* ------------------------------------------------------------ rendering */

  const sessionEvents = useMemo(
    () => (activeAgentId ? events.filter((e) => e.session_id === activeAgentId) : []),
    [events, activeAgentId],
  );
  const timeline = useMemo(() => {
    // Pending (optimistic) user messages are by definition the newest — keep
    // them out of the seq sort so a thinking segment can never float above.
    const persisted = new Set(
      sessionEvents
        .filter((e) => e.type === 'agent.message_emitted')
        .map((e) => String(e.data.content ?? '')),
    );
    const frozen = streamView.frozen.filter((m) => !persisted.has(m.content));
    const merged: TimelineItem[] = [...buildTimeline(sessionEvents, []), ...thinkingItems, ...frozen];
    if (streamView.streamText) {
      merged.push({
        kind: 'message',
        id: 'stream-live',
        seq: maxSeqRef.current + 0.4,
        sender: 'assistant',
        senderLabel: activeAgent?.display_name ?? 'assistant',
        content: streamView.streamText,
        streaming: true,
      });
    }
    merged.sort((a, b) => a.seq - b.seq);
    return [...merged, ...pendingMessages];
  }, [sessionEvents, pendingMessages, thinkingItems, streamView, activeAgent?.display_name]);
  const runningTool = useMemo(
    () => timeline.find((item) => item.kind === 'tool' && item.running) as ToolItem | undefined,
    [timeline],
  );
  const liveThinking = thinkingItems.some((item) => item.live);

  // Agent tree: sub-agents fold under their parent's chip in the agent bar.
  const childrenOf = useMemo(() => {
    const ids = new Set(agents.map((a) => a.id));
    const m = new Map<string, Agent[]>();
    for (const a of agents) {
      if (a.parent_session_id && ids.has(a.parent_session_id)) {
        const list = m.get(a.parent_session_id) ?? [];
        list.push(a);
        m.set(a.parent_session_id, list);
      }
    }
    return m;
  }, [agents]);
  const rootAgents = useMemo(() => {
    const ids = new Set(agents.map((a) => a.id));
    return agents.filter((a) => !a.parent_session_id || !ids.has(a.parent_session_id));
  }, [agents]);

  const toggleAgentExpanded = useCallback((id: string) => {
    setExpandedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const renderAgentChip = (a: Agent, depth: number): React.ReactNode => {
    const children = childrenOf.get(a.id) ?? [];
    const childCount = children.length;
    const expanded = expandedAgents.has(a.id);
    return (
      <Fragment key={a.id}>
        <span className={`agent-chip-wrap${depth > 0 ? ' child' : ''}`}>
          <button
            className={`agent-chip ${a.id === activeAgentId ? 'active' : ''}`}
            onClick={() => selectAgent(a.id)}
          >
            <span className={`state-dot ${a.state}`} />
            {a.display_name}
          </button>
          {childCount > 0 && (
            <button
              className="chip-caret"
              title={expanded ? 'Collapse sub-agents' : `${childCount} sub-agent(s) — click to expand`}
              onClick={() => toggleAgentExpanded(a.id)}
            >
              {expanded ? '▾' : '▸'}{childCount}
            </button>
          )}
        </span>
        {expanded && children.map((c) => renderAgentChip(c, depth + 1))}
      </Fragment>
    );
  };

  const chatRef = useRef<HTMLDivElement | null>(null);
  const nearBottomRef = useRef(true);
  useEffect(() => {
    const el = chatRef.current;
    if (el && nearBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [timeline, streamView, activeAgent?.state]);

  const connLabel = !activeProject ? 'idle' : connState === 'live' ? 'live' : connState === 'connecting' ? 'connecting' : 'reconnecting…';

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-head">
          <span className="brand-dot" />
          <span className="brand">Cloudra</span>
        </div>
        <div className="sidebar-new">
          <input
            className="input"
            value={newProject}
            onChange={(e) => setNewProject(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && createProjectAndSelect()}
            placeholder="New project…"
          />
          <button className="btn primary sm" style={{ height: 30 }} onClick={createProjectAndSelect} disabled={!newProject.trim()}>
            +
          </button>
          <input
            className="input ws-path"
            value={newProjectWs}
            onChange={(e) => setNewProjectWs(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && createProjectAndSelect()}
            placeholder="workspace dir (optional)…"
            title="Workspace directory: agents read/write within it"
          />
        </div>
        <div className="project-list">
          {projects.length === 0 && <div className="empty-hint">No projects yet — create one above.</div>}
          {groupedProjects.map(([ws, list]) => (
            <div key={ws || '__none'} className="ws-group">
              <div className="ws-header" title={ws || undefined}>{ws || 'no workspace'}</div>
              {list.map((p) => (
                <div
                  key={p.id}
                  className={`project-item ${p.id === activeProjectId ? 'active' : ''}`}
                  onClick={() => setActiveProjectId(p.id)}
                >
                  <div className="project-name">{p.name}</div>
                  <div className="project-meta">{p.settings.orchestration_mode}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </aside>

      <main className="main">
        <div className="agentbar">
          <span className="agentbar-title">{activeProject?.name ?? 'Select a project'}</span>
          {activeProject && (
            <input
              key={`ws-${activeProject.id}`}
              className="input ws-input"
              defaultValue={activeProject.workspace_dir ?? ''}
              placeholder="workspace dir…"
              title="Workspace directory: this project's agents read/write within it. Edit and press Enter to change; clear to unset."
              onBlur={(e) => changeWorkspace(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
            />
          )}
          {rootAgents.map((a) => renderAgentChip(a, 0))}
          {activeProject && (
            <select
              className="select agentbar-select mode"
              title="orchestration mode (project default for new agents)"
              value={activeProject.settings.orchestration_mode}
              onChange={(e) => changeOrchestrationMode(e.target.value)}
            >
              <option value="standard">standard</option>
              <option value="dag_record">dag_record</option>
              <option value="dag_guided">dag_guided</option>
            </select>
          )}
          {activeProject && (
            <label
              className="agentbar-yolo"
              title="YOLO: auto-approve destructive ops via the guard LLM, project-wide. Stored as the project default for new agents and cascaded to all existing agents; per-agent override lives in the Inspector."
            >
              <input
                type="checkbox"
                checked={activeProject.settings.defaults?.yolo === true}
                onChange={(e) => toggleProjectYolo(e.target.checked)}
              />
              YOLO
            </label>
          )}
          {activeProject && (
            <select className="select agentbar-select" value="" onChange={(e) => spawnRole(e.target.value)}>
              <option value="">+ spawn…</option>
              {roles.map((r) => (
                <option key={r.role_id} value={r.role_id}>{r.display_name}</option>
              ))}
            </select>
          )}
          <span className="conn-status">
            {activeProject && <span className={`state-dot ${connState === 'live' ? 'running' : 'waiting_input'}`} />}
            {connLabel}
          </span>
        </div>

        <div
          className="chat-scroll"
          ref={chatRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          }}
        >
          <div className="chat-column">
            {!activeProject && (
              <div className="chat-empty">
                <div className="big">Welcome to Cloudra</div>
                Pick a project on the left, or create a new one.
              </div>
            )}
            {activeProject && timeline.length === 0 && activeAgent?.state !== 'running' && (
              <div className="chat-empty">
                <div className="big">{activeAgent ? `${activeAgent.display_name} is ready` : 'No activity yet'}</div>
                {activeAgent
                  ? 'Type a query below and press Send to start this agent.'
                  : 'Send a message below to start the coordinator.'}
              </div>
            )}
            {timeline.map((item) =>
              item.kind === 'message' ? (
                <div
                  key={item.id}
                  className={`msg ${item.sender}${item.streaming ? ' streaming' : ''}`}
                  style={item.pending ? { opacity: 0.55 } : undefined}
                >
                  <span className="msg-sender">{item.pending ? 'sending…' : item.senderLabel}</span>
                  {item.sender === 'user' ? (
                    <div className="msg-bubble">{item.content}</div>
                  ) : (
                    <div className="msg-body">
                      <Markdown text={item.content} />
                    </div>
                  )}
                </div>
              ) : item.kind === 'tool' ? (
                <ToolRowView key={item.id} item={item} />
              ) : item.kind === 'thinking' ? (
                <details key={item.id} className={`thinking${item.live ? ' live' : ''}`}>
                  <summary>
                    <span className="thinking-dot" />
                    thinking{item.live ? '…' : ''}
                  </summary>
                  <div className="thinking-body">{item.text}</div>
                </details>
              ) : (
                <div key={item.id} className="tool-row fail" style={{ cursor: 'default' }}>
                  <span className="tool-icon">!</span>
                  <span className="tool-summary">{item.text}</span>
                </div>
              ),
            )}
            {activeAgent?.state === 'running' && (runningTool || (!streamView.streamText && !liveThinking)) && (
              <div className="run-status">
                <span className="state-dot running" />
                <span className="shimmer">{runningTool ? `running ${runningTool.name}…` : 'thinking…'}</span>
              </div>
            )}
            {activeAgent?.state === 'waiting_approval' && (
              <div className="run-status">
                <span className="state-dot waiting_approval" />
                <span style={{ color: 'var(--yellow-soft)' }}>waiting for approval — see the approvals tab</span>
              </div>
            )}
            {activeAgent?.state === 'queued' && timeline.length > 0 && (
              <div className="run-status">
                <span className="state-dot queued" />
                <span>queued — enter a query below to start</span>
              </div>
            )}
          </div>
        </div>

        <div className="composer-wrap">
          {interactions.length > 0 && (
            <div className="ask-banner">
              <span className="state-dot waiting_input" />
              <span>
                Agent is asking: {short(interactions[0].prompt ?? interactions[0].message ?? '', 100)} — reply in the interactions tab
                {interactions.length > 1 ? ` (+${interactions.length - 1} more)` : ''}
              </span>
            </div>
          )}
          <div className="composer">
            <textarea
              rows={2}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void sendMessage();
                }
              }}
              placeholder={
                !activeProject
                  ? 'Select or create a project first…'
                  : activeAgent
                    ? activeAgent.state === 'failed' || activeAgent.state === 'cancelled'
                      ? `Message ${activeAgent.display_name} — this reopens it with a fresh run…`
                      : `Guide ${activeAgent.display_name}…`
                    : 'Describe the task for the coordinator…'
              }
              disabled={!activeProject}
            />
            <div className="composer-actions">
              <span className="composer-hint">Enter to send · Shift+Enter for newline</span>
              {activeAgent && activeAgent.state === 'running' && (
                <button className="btn ghost sm" onClick={() => cancelAgent()}>Cancel</button>
              )}
              <button className="btn primary sm" onClick={sendMessage} disabled={!draft.trim() || !activeProject || sending}>
                {sending ? 'Sending…' : 'Send'}
              </button>
            </div>
          </div>
        </div>
      </main>

      <Inspector
        activeAgent={activeAgent}
        activeProject={activeProject}
        events={sessionEvents}
        selectedEvent={selectedEvent}
        onSelectEvent={setSelectedEvent}
        onPatchSettings={patchSettings}
        approvals={approvals}
        interactions={interactions}
        onRefreshApprovals={() => activeProject && api.approvals(activeProject.id).then(setApprovals).catch(reportError)}
        onRefreshInteractions={() => activeProject && api.interactions(activeProject.id).then(setInteractions).catch(reportError)}
        onError={reportError}
        onToast={pushToast}
      />

      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`} onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ tool row */

function ToolRowView({ item }: { item: ToolItem }) {
  const [open, setOpen] = useState(false);
  const icon = item.running ? '▸' : item.ok ? '✓' : '✗';
  const cls = item.running ? 'running' : item.ok ? 'ok' : 'fail';
  return (
    <>
      <div className={`tool-row ${cls}`} onClick={() => setOpen((v) => !v)}>
        <span className="tool-icon">{icon}</span>
        <span className="tool-name">{item.name}</span>
        <span className="tool-sep">·</span>
        <span className="tool-summary">
          {item.running
            ? short(item.argsSummary, 120) || 'running…'
            : short(item.resultSummary, 200) || (item.ok ? 'done' : 'failed')}
        </span>
        {item.durationMs != null && <span className="tool-sep">{item.durationMs}ms</span>}
      </div>
      {open && (
        <div className="tool-detail">
          {item.argsSummary && <>IN{'\n'}{item.argsSummary}{'\n\n'}</>}
          {item.resultSummary && <>OUT{'\n'}{item.resultSummary}</>}
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ inspector */

type InspectorTab = 'events' | 'dag' | 'approvals' | 'interactions' | 'artifacts' | 'settings' | 'context' | 'skills';

interface GoalForm {
  objective: string;
  completion_criteria: string;
  current_focus: string;
}

interface ContextStats {
  session_id: string;
  messages: number;
  tokens: number;
  by_role: Record<string, { messages: number; tokens: number }>;
  last_prompt_tokens: number | null;
}

const EMPTY_GOAL: GoalForm = { objective: '', completion_criteria: '', current_focus: '' };

function Inspector({ activeAgent, activeProject, events, selectedEvent, onSelectEvent, onPatchSettings, approvals, interactions, onRefreshApprovals, onRefreshInteractions, onError, onToast }: {
  activeAgent: Agent | null;
  activeProject: Project | null;
  events: EventEnvelope[];
  selectedEvent: EventEnvelope | null;
  onSelectEvent: (e: EventEnvelope) => void;
  onPatchSettings: (patch: Record<string, unknown>) => void;
  approvals: Array<Record<string, unknown>>;
  interactions: Array<Record<string, unknown>>;
  onRefreshApprovals: () => void;
  onRefreshInteractions: () => void;
  onError: (e: unknown) => void;
  onToast: (kind: ToastKind, text: string) => void;
}) {
  const [tab, setTab] = useState<InspectorTab>('events');
  const [artifacts, setArtifacts] = useState<Array<Record<string, unknown>>>([]);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [goal, setGoal] = useState<GoalForm>(EMPTY_GOAL);
  const [goalLoaded, setGoalLoaded] = useState(false);
  const [stats, setStats] = useState<ContextStats | null>(null);
  const [keepRecent, setKeepRecent] = useState(20);
  const [skills, setSkills] = useState<Array<Record<string, unknown>>>([]);

  async function loadTab(next: InspectorTab) {
    setTab(next);
    try {
      if (next === 'artifacts' && activeProject) {
        setArtifacts(await api.artifacts(activeProject.id));
      } else if (next === 'context' && activeAgent) {
        const [goalResp, statsResp] = await Promise.all([api.getGoal(activeAgent.id), api.getContextStats(activeAgent.id)]);
        setGoal(goalResp.goal ?? EMPTY_GOAL);
        setGoalLoaded(true);
        setStats(statsResp);
      } else if (next === 'skills') {
        setSkills(await api.listSkills());
      }
    } catch (e) {
      onError(e);
    }
  }

  async function decide(approvalId: number | string, decision: 'approve' | 'deny') {
    if (!activeProject) return;
    setDeciding(`${approvalId}:${decision}`);
    try {
      await api.decideApproval(activeProject.id, approvalId, decision, decision === 'deny' ? 'denied by user' : '');
      onToast('ok', `${decision === 'approve' ? 'Approved' : 'Denied'}`);
      onRefreshApprovals();
    } catch (e) {
      onError(e);
    } finally {
      setDeciding(null);
    }
  }

  async function refreshStats() {
    if (!activeAgent) return;
    try {
      setStats(await api.getContextStats(activeAgent.id));
    } catch (e) {
      onError(e);
    }
  }

  const toolEvents = events.filter((e) => e.type.startsWith('tool.') || e.type.startsWith('llm.') || e.type.startsWith('run.'));

  return (
    <aside className="inspector">
      <div className="tabs">
        {(['events', 'dag', 'approvals', 'interactions', 'artifacts', 'settings', 'context', 'skills'] as const).map((t) => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => loadTab(t)}>
            {t}
            {t === 'approvals' && approvals.length > 0 && <span className="badge">{approvals.length}</span>}
            {t === 'interactions' && interactions.length > 0 && <span className="badge">{interactions.length}</span>}
          </button>
        ))}
      </div>
      <div className="inspector-body">
        {tab === 'events' && (
          <>
            {toolEvents.length === 0 && <div className="empty-hint">No tool/LLM events yet.</div>}
            {toolEvents.map((event) => (
              <button
                key={event.event_id}
                className={`event-row ${selectedEvent?.event_id === event.event_id ? 'selected' : ''}`}
                onClick={() => onSelectEvent(event)}
              >
                <span className="seq">#{event.session_seq ?? '?'}</span>
                {event.type}
              </button>
            ))}
          </>
        )}

        {tab === 'dag' && (
          activeProject ? (
            <DagPanel project={activeProject} onError={onError} onToast={onToast} />
          ) : (
            <div className="empty-hint">Select a project first.</div>
          )
        )}

        {tab === 'approvals' && (
          <>
            {approvals.length === 0 && <div className="empty-hint">No pending approvals.</div>}
            {approvals.map((approval) => {
              const id = approval.id as number;
              return (
                <div key={String(id)} className="card">
                  <div className="card-title">{String(approval.tool_name ?? approval.tool ?? 'tool')}</div>
                  <div className="card-meta">#{String(id)}</div>
                  <pre className="json-view">{JSON.stringify(approval, null, 2)}</pre>
                  <div className="card-actions">
                    <button className="btn green sm" disabled={deciding !== null} onClick={() => decide(id, 'approve')}>
                      {deciding === `${id}:approve` ? 'Approving…' : 'Approve'}
                    </button>
                    <button className="btn yellow sm" disabled={deciding !== null} onClick={() => decide(id, 'deny')}>
                      {deciding === `${id}:deny` ? 'Denying…' : 'Deny'}
                    </button>
                  </div>
                </div>
              );
            })}
          </>
        )}

        {tab === 'interactions' && (
          <>
            {interactions.length === 0 && <div className="empty-hint">No pending interactions.</div>}
            {interactions.map((item) => {
              const interactionId = item.interaction_id as number | string | undefined;
              return (
                <div key={String(interactionId ?? item.id ?? '')} className="card">
                  <div className="card-meta">{String(item.session_id ?? '')}</div>
                  <pre className="json-view">{JSON.stringify(item, null, 2)}</pre>
                  {activeProject && interactionId && (
                    <input
                      className="input"
                      placeholder="Type a response and press Enter…"
                      style={{ width: '100%', marginTop: 8 }}
                      onKeyDown={async (e) => {
                        if (e.key !== 'Enter') return;
                        const value = (e.target as HTMLInputElement).value;
                        if (!value.trim()) return;
                        try {
                          await api.respondInteraction(activeProject.id, interactionId, value);
                          onToast('ok', 'Response sent');
                          onRefreshInteractions();
                        } catch (err) {
                          onError(err);
                        }
                      }}
                    />
                  )}
                </div>
              );
            })}
          </>
        )}

        {tab === 'artifacts' && (
          <>
            {artifacts.length === 0 && <div className="empty-hint">No artifacts yet.</div>}
            {artifacts.map((artifact) => (
              <div key={String(artifact.artifact_id)} className="card">
                <div className="card-title">{String(artifact.name)}</div>
                <div className="card-meta">
                  {String(artifact.mime_type ?? '')} · {String(artifact.size ?? '')} bytes
                </div>
                {activeProject && (
                  <div className="card-actions">
                    <a
                      className="btn outline sm"
                      href={api.artifactDownloadUrl(activeProject.id, String(artifact.artifact_id))}
                      download={String(artifact.name)}
                    >
                      download
                    </a>
                  </div>
                )}
              </div>
            ))}
          </>
        )}

        {tab === 'context' &&
          (activeAgent ? (
            <>
              <div className="ctx-section">
                <div className="ctx-title">Goal anchor</div>
                {goalLoaded ? (
                  <>
                    <label className="field">
                      objective
                      <input
                        className="input"
                        value={goal.objective}
                        onChange={(e) => setGoal((g) => ({ ...g, objective: e.target.value }))}
                      />
                    </label>
                    <label className="field">
                      completion_criteria
                      <input
                        className="input"
                        value={goal.completion_criteria}
                        onChange={(e) => setGoal((g) => ({ ...g, completion_criteria: e.target.value }))}
                      />
                    </label>
                    <label className="field">
                      current_focus
                      <input
                        className="input"
                        value={goal.current_focus}
                        onChange={(e) => setGoal((g) => ({ ...g, current_focus: e.target.value }))}
                      />
                    </label>
                    <button
                      className="btn primary sm"
                      onClick={async () => {
                        try {
                          await api.setGoal(activeAgent.id, goal);
                          onToast('ok', 'Goal saved');
                        } catch (e) {
                          onError(e);
                        }
                      }}
                    >
                      Save
                    </button>
                  </>
                ) : (
                  <div className="empty-hint">Loading goal…</div>
                )}
              </div>

              <div className="ctx-section">
                <div className="ctx-title">
                  Context stats
                  <button className="btn ghost sm" style={{ marginLeft: 'auto' }} onClick={refreshStats}>
                    Refresh
                  </button>
                </div>
                {stats ? (
                  <>
                    <div className="ctx-row">
                      <span>messages</span>
                      <span>{stats.messages}</span>
                    </div>
                    <div className="ctx-row">
                      <span>tokens</span>
                      <span>{stats.tokens}</span>
                    </div>
                    <div className="ctx-row">
                      <span>last prompt tokens</span>
                      <span>{stats.last_prompt_tokens ?? '—'}</span>
                    </div>
                    <table className="ctx-table">
                      <thead>
                        <tr>
                          <th>role</th>
                          <th>messages</th>
                          <th>tokens</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(stats.by_role).map(([role, s]) => (
                          <tr key={role}>
                            <td>{role}</td>
                            <td>{s.messages}</td>
                            <td>{s.tokens}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="muted-note">
                      tokens estimated from persisted events; last_prompt_tokens is the exact value from the latest LLM call
                    </div>
                  </>
                ) : (
                  <div className="empty-hint">Loading stats…</div>
                )}
              </div>

              <div className="ctx-section">
                <div className="ctx-title">Compact context</div>
                <label className="field">
                  keep_recent
                  <input
                    className="input"
                    type="number"
                    min={1}
                    value={keepRecent}
                    onChange={(e) => setKeepRecent(Math.max(1, Number(e.target.value) || 1))}
                  />
                </label>
                <button
                  className="btn outline sm"
                  onClick={async () => {
                    try {
                      await api.compactAgent(activeAgent.id, keepRecent);
                      onToast('ok', 'Compaction queued — applies on the next turn');
                    } catch (e) {
                      onError(e);
                    }
                  }}
                >
                  Compact
                </button>
              </div>
            </>
          ) : (
            <div className="empty-hint">Select an agent…</div>
          ))}

        {tab === 'skills' && (
          <>
            {skills.length === 0 && <div className="empty-hint">No skills found.</div>}
            {skills.map((skill) => (
              <details key={String(skill.name)} className="skill-item">
                <summary>
                  <span className="skill-name">{String(skill.name ?? '(unnamed)')}</span>
                  {skill.description != null && <span className="skill-desc">{String(skill.description)}</span>}
                </summary>
                <div className="skill-body">{String(skill.content ?? '')}</div>
              </details>
            ))}
          </>
        )}

        {tab === 'settings' &&
          (activeAgent ? (
            <>
              <label className="field">
                model
                <input
                  className="input"
                  key={`model-${activeAgent.id}`}
                  defaultValue={activeAgent.settings.model}
                  onBlur={(e) => e.target.value !== activeAgent.settings.model && onPatchSettings({ model: e.target.value })}
                />
              </label>
              <label className="field">
                base_url
                <input
                  className="input"
                  key={`url-${activeAgent.id}`}
                  defaultValue={activeAgent.settings.base_url}
                  onBlur={(e) => e.target.value !== activeAgent.settings.base_url && onPatchSettings({ base_url: e.target.value })}
                />
              </label>
              <label className="field-row">
                <input type="checkbox" checked={activeAgent.settings.yolo} onChange={(e) => onPatchSettings({ yolo: e.target.checked })} />
                YOLO (this agent only; project-wide toggle is in the top bar)
              </label>
              <label className="field">
                temperature
                <input
                  className="input"
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  key={`temp-${activeAgent.id}`}
                  defaultValue={activeAgent.settings.temperature}
                  onBlur={(e) => Number(e.target.value) !== activeAgent.settings.temperature && onPatchSettings({ temperature: Number(e.target.value) })}
                />
              </label>
              <div className="muted-note">Changes apply to this session on the next LLM request.</div>
            </>
          ) : (
            <div className="empty-hint">Select an agent to edit settings.</div>
          ))}
      </div>
      {tab === 'events' && (
        <div className="event-detail">
          {selectedEvent ? (
            <pre className="json-view">{JSON.stringify(selectedEvent, null, 2)}</pre>
          ) : (
            <div className="empty-hint">Select an event to inspect.</div>
          )}
        </div>
      )}
    </aside>
  );
}
