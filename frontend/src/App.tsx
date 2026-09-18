import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { api, EVENTS_WINDOW, HISTORY_PAGE_SIZE, streamProject } from './api';
import Markdown from './Markdown';
import DagPanel from './DagPanel';
import OpsPanel from './OpsPanel';
import type { Agent, ComputeJob, EventEnvelope, PendingReminder, Project } from './types';
import AuditLog from './AuditLog';
import GlobalConfig from './GlobalConfig';
import KnowledgePanel from './KnowledgePanel';
import BenchmarkPanel from './BenchmarkPanel';
import TelemetryPanel from './TelemetryPanel';
import AttentionDock, { type NotifPermission } from './AttentionDock';
import { collectPending, diffNewItems, type PendingAttention, type ProjectPending } from './attention';
import {
  applyStreamEvent,
  buildTimeline,
  type MessageItem,
  type StreamView,
  type ThinkingItem,
  type TimelineItem,
  type ToolItem,
} from './timeline';
import { ToolRow } from './ToolRow';
import { ProgramCard } from './ProgramCard';
import { PathPickerModal } from './PathPickerModal';

export type InspectorTab = 'overview' | 'ops' | 'dag' | 'approvals' | 'interactions' | 'artifacts' | 'settings' | 'events';

/* ------------------------------------------------------------------ helpers */

type ToastKind = 'error' | 'ok' | 'info';
interface Toast { id: number; kind: ToastKind; text: string }

let toastSeq = 0;

function elapsed(startTs: number | null): string {
  if (!startTs || startTs <= 0) return '—';
  const secs = Math.max(0, Math.floor(Date.now() / 1000 - startTs));
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m${secs % 60}s`;
  return `${Math.floor(secs / 3600)}h${Math.floor((secs % 3600) / 60)}m`;
}

function wakeCountdown(wakeTs: number): string {
  const secs = Math.floor(wakeTs - Date.now() / 1000);
  if (secs <= 0) return '已到期';
  if (secs < 60) return `${secs}s 后`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m 后`;
  return `${Math.floor(secs / 3600)}h 后`;
}

function short(text: unknown, max = 80): string {
  const s = typeof text === 'string' ? text : JSON.stringify(text);
  if (!s) return '';
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function fmtBytes(n: number): string {
  if (!Number.isFinite(n) || n < 0) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function dedupeAgents(list: Agent[]): Agent[] {
  const seen = new Map<string, Agent>();
  for (const a of list) seen.set(a.id, a);
  return [...seen.values()];
}

function stamp(iso: unknown): string {
  if (!iso || typeof iso !== 'string') return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function cleanPromptText(raw: unknown): string {
  if (!raw) return '';
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        return String(parsed.question ?? parsed.prompt ?? parsed.message ?? raw);
      }
    } catch {
      return raw;
    }
    return raw;
  }
  if (typeof raw === 'object' && raw !== null) {
    const obj = raw as Record<string, unknown>;
    return String(obj.question ?? obj.prompt ?? obj.message ?? JSON.stringify(raw));
  }
  return String(raw);
}

interface SlashCommandDef {
  command: string;
  args?: string;
  desc: string;
  insertText: string;
}

const SLASH_COMMANDS: SlashCommandDef[] = [
  {
    command: '/schedule',
    args: '[on|off]',
    desc: 'Toggle autonomous schedule mode & self-wake guard',
    insertText: '/schedule ',
  },
  {
    command: '/goal',
    args: '<objective>',
    desc: 'Set pinned task goal for active agent',
    insertText: '/goal ',
  },
  {
    command: '/yolo',
    args: '[on|off]',
    desc: 'Toggle background LLM auto-approval for actions',
    insertText: '/yolo ',
  },
  {
    command: '/visual',
    args: '[on|off]',
    desc: 'Toggle visual mode (vision tools + image input)',
    insertText: '/visual ',
  },
  {
    command: '/compact',
    desc: 'Compress conversation history and summarize past steps',
    insertText: '/compact',
  },
  {
    command: '/help',
    desc: 'Show help guide and list of available slash commands',
    insertText: '/help',
  },
];

function ThinkingBlock({ item }: { item: ThinkingItem }) {
  const [open, setOpen] = useState(Boolean(item.live));
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (item.live) setOpen(true);
  }, [item.live]);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(item.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className={`thinking-card ${item.live ? 'live' : ''} ${open ? 'open' : ''}`}>
      <div className="thinking-head" onClick={() => setOpen((prev) => !prev)}>
        <span className={`thinking-dot ${item.live ? 'live' : ''}`} />
        <span className="thinking-title">{item.live ? 'Thinking…' : 'Thought process'}</span>
        <span className="thinking-meta">{item.text.length} chars</span>
        <div className="thinking-actions">
          <button
            type="button"
            className="btn ghost sm thinking-copy"
            title="Copy reasoning text"
            onClick={handleCopy}
          >
            {copied ? 'Copied' : 'Copy'}
          </button>
          <span className="thinking-toggle">{open ? '▼' : '▶'}</span>
        </div>
      </div>
      {open && <div className="thinking-body">{item.text}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ app */

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  // Older history pages pulled in by the "Load earlier" bubble at the top of
  // the chat.  Kept separate from `events` so the live SSE window can keep
  // clipping itself to EVENTS_WINDOW without discarding user-loaded pages.
  const [olderEvents, setOlderEvents] = useState<EventEnvelope[]>([]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasOlder, setHasOlder] = useState(true);
  const [streamView, setStreamView] = useState<StreamView>({ streamText: '', frozen: [] });
  const [sidebarView, setSidebarView] = useState<'ops' | 'projects'>('ops');
  const [sidebarJobs, setSidebarJobs] = useState<ComputeJob[] | null>(null);
  const [sidebarReminders, setSidebarReminders] = useState<PendingReminder[] | null>(null);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('overview');
  // Resizing and collapsing state
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const saved = localStorage.getItem('cloudra:sidebar-width');
    const parsed = saved ? parseInt(saved, 10) : 260;
    return Number.isFinite(parsed) && parsed >= 180 && parsed <= 500 ? parsed : 260;
  });
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(() => {
    const saved = localStorage.getItem('cloudra:sidebar-open');
    return saved !== null ? saved === 'true' : true;
  });
  const [inspectorWidth, setInspectorWidth] = useState<number>(() => {
    const saved = localStorage.getItem('cloudra:inspector-width');
    const parsed = saved ? parseInt(saved, 10) : 380;
    return Number.isFinite(parsed) && parsed >= 280 && parsed <= 900 ? parsed : 380;
  });
  const [inspectorOpen, setInspectorOpen] = useState<boolean>(() => {
    const saved = localStorage.getItem('cloudra:inspector-open');
    return saved !== null ? saved === 'true' : true;
  });
  const [resizingSide, setResizingSide] = useState<'sidebar' | 'inspector' | null>(null);
  const [editingWs, setEditingWs] = useState(false);
  const [pendingMessages, setPendingMessages] = useState<MessageItem[]>([]);
  const [roles, setRoles] = useState<Array<{ role_id: string; display_name: string }>>([]);
  const [draft, setDraft] = useState('');
  const [slashSelected, setSlashSelected] = useState(0);
  const [slashDismissed, setSlashDismissed] = useState(false);
  const composerTextareaRef = useRef<HTMLTextAreaElement>(null);
  const [newProject, setNewProject] = useState('');
  const [newProjectWs, setNewProjectWs] = useState('');
  const [inlineCreate, setInlineCreate] = useState<{ ws: string; name: string } | null>(null);
  const [sending, setSending] = useState(false);
  const [connState, setConnState] = useState<'connecting' | 'live' | 'offline'>('connecting');
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [approvals, setApprovals] = useState<Array<Record<string, unknown>>>([]);
  const [interactions, setInteractions] = useState<Array<Record<string, unknown>>>([]);
  const [expandedAgents, setExpandedAgents] = useState<Set<string>>(new Set());
  const [globalOpen, setGlobalOpen] = useState(() => {
    return Boolean(
      new URLSearchParams(window.location.search).has('code') &&
        sessionStorage.getItem('openrouter_pkce_verifier')
    );
  });
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
  const [benchmarkOpen, setBenchmarkOpen] = useState(false);
  const [telemetryOpen, setTelemetryOpen] = useState(false);
  const [pendingImages, setPendingImages] = useState<Array<{ path: string; artifactId: string; name: string; size: number }>>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Cross-project pending approvals/ask_user (the AttentionDock + desktop
  // notifications).  Keyed by project id; polled for every non-archived
  // project since the SSE stream only covers the active one.
  const [attention, setAttention] = useState<Map<string, ProjectPending>>(new Map());
  const attentionSeenRef = useRef<Set<string>>(new Set());
  const attentionBaselineRef = useRef(false);
  const [notifPermission, setNotifPermission] = useState<NotifPermission>(
    typeof Notification === 'undefined' ? 'unsupported' : Notification.permission,
  );
  // Jump target set by the dock / a notification click when the owning
  // project is not active yet; consumed by the project-switch effect.
  const jumpTargetRef = useRef<{ projectId: string; sessionId: string } | null>(null);
  // path → artifact_id for images uploaded in this browser session, so the
  // message_injected echo (which carries paths only) can still render them.
  const uploadedArtifactsRef = useRef<Map<string, string>>(new Map());

  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;
  const activeAgent = agents.find((a) => a.id === activeAgentId) ?? null;
  // Visual mode gates the composer attach button; defaults to on.
  const visualOn = activeProject
    ? (activeAgent?.settings.visual_mode ?? activeProject.settings.defaults?.visual_mode ?? true) !== false
    : false;

  // Slash commands autocomplete calculation
  const isSlashPrompt = draft.startsWith('/') && !draft.includes('\n');
  const slashPrefix = isSlashPrompt ? draft.trim().toLowerCase() : '';
  const matchingSlash = useMemo(() => {
    if (!isSlashPrompt || slashDismissed) return [];
    return SLASH_COMMANDS.filter((cmd) => {
      if (slashPrefix === '/') return true;
      return cmd.command.toLowerCase().startsWith(slashPrefix);
    });
  }, [isSlashPrompt, slashPrefix, slashDismissed]);

  const selectSlashCommand = (cmd: SlashCommandDef) => {
    setDraft(cmd.insertText);
    setSlashDismissed(true);
    if (composerTextareaRef.current) {
      composerTextareaRef.current.focus();
    }
  };

  // Sidebar grouping: active projects bucketed by workspace_dir ('' = no
  // workspace, sorted last); archived ones live in a separate section below.
  const groupedProjects = useMemo(() => {
    const groups = new Map<string, Project[]>();
    for (const p of projects) {
      if (p.archived) continue;
      const key = p.workspace_dir ?? '';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(p);
    }
    return [...groups.entries()].sort(([a], [b]) =>
      a === '' ? 1 : b === '' ? -1 : a.localeCompare(b),
    );
  }, [projects]);

  const archivedProjects = useMemo(() => projects.filter((p) => p.archived), [projects]);

  const workspaceSuggestions = useMemo(
    () =>
      [...new Set(projects.map((p) => p.workspace_dir?.trim()).filter(Boolean) as string[])].sort(
        (a, b) => a.localeCompare(b),
      ),
    [projects],
  );

  const [pathPicker, setPathPicker] = useState<{
    isOpen: boolean;
    title?: string;
    initialPath?: string;
    onSelect: (path: string) => void;
  }>({
    isOpen: false,
    onSelect: () => {},
  });

  const openPathPicker = useCallback(
    (options: {
      title?: string;
      initialPath?: string;
      onSelect: (path: string) => void;
    }) => {
      setPathPicker({
        isOpen: true,
        title: options.title,
        initialPath: options.initialPath,
        onSelect: options.onSelect,
      });
    },
    [],
  );

  const extraPickerShortcuts = useMemo(
    () =>
      workspaceSuggestions.map((ws) => ({
        name: ws.split('/').filter(Boolean).pop() || ws,
        path: ws,
      })),
    [workspaceSuggestions],
  );

  // Refs so the long-lived SSE subscription always sees current values.
  const activeAgentIdRef = useRef(activeAgentId);
  activeAgentIdRef.current = activeAgentId;
  const maxSeqRef = useRef(0);

  // Sync panel widths and visibility to localStorage
  useEffect(() => {
    localStorage.setItem('cloudra:sidebar-width', String(sidebarWidth));
  }, [sidebarWidth]);
  useEffect(() => {
    localStorage.setItem('cloudra:sidebar-open', String(sidebarOpen));
  }, [sidebarOpen]);
  useEffect(() => {
    localStorage.setItem('cloudra:inspector-width', String(inspectorWidth));
  }, [inspectorWidth]);
  useEffect(() => {
    localStorage.setItem('cloudra:inspector-open', String(inspectorOpen));
  }, [inspectorOpen]);

  // Shortcut Cmd+B / Ctrl+B toggles sidebar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'b' || e.key === 'B')) {
        e.preventDefault();
        setSidebarOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Window drag listeners for sidebar / inspector resizers
  useEffect(() => {
    if (!resizingSide) return;
    const handleMouseMove = (e: MouseEvent) => {
      if (resizingSide === 'sidebar') {
        const next = Math.max(180, Math.min(500, e.clientX));
        setSidebarWidth(next);
      } else if (resizingSide === 'inspector') {
        const next = Math.max(280, Math.min(900, Math.min(window.innerWidth - 300, window.innerWidth - e.clientX)));
        setInspectorWidth(next);
      }
    };
    const handleMouseUp = () => {
      setResizingSide(null);
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [resizingSide]);

  // SSE events arrive in bursts (full history replay on connect, and one
  // llm.*/tool.* event per token/step during a run).  Feeding each event
  // straight into `setEvents` re-runs `buildTimeline` (a full sort +
  // stringification of the window) per event — thousands of times on open and
  // on every tool burst.  We coalesce into one state update per animation
  // frame so the transcript rebuilds once, not per event.
  const eventBufferRef = useRef<EventEnvelope[]>([]);
  const flushRafRef = useRef<number | null>(null);
  const flushBufferedEvents = useCallback(() => {
    flushRafRef.current = null;
    const batch = eventBufferRef.current;
    eventBufferRef.current = [];
    if (batch.length === 0) return;
    setEvents((prev) => {
      const seen = new Set(prev.map((e) => e.event_id));
      let next = prev;
      let changed = false;
      for (const event of batch) {
        if (seen.has(event.event_id)) continue;
        seen.add(event.event_id);
        next = [...next, event];
        changed = true;
      }
      return changed ? next.slice(-EVENTS_WINDOW) : prev;
    });
  }, []);
  const bufferEvent = useCallback(
    (event: EventEnvelope) => {
      eventBufferRef.current.push(event);
      if (flushRafRef.current == null) {
        flushRafRef.current = requestAnimationFrame(flushBufferedEvents);
      }
    },
    [flushBufferedEvents],
  );

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
    api.listProjects(true).then(setProjects).catch(reportError);
    api.listRoles().then(setRoles).catch(reportError);
  }, [reportError]);

  /* ---------------------------------------------------- benchmark drill-down */

  const openBenchmarkProject = useCallback(
    (projectId: string) => {
      setBenchmarkOpen(false);
      // 批次运行期间新项目可能尚未进入侧边栏缓存：先刷新再定位。
      api.listProjects(true)
        .then((list) => {
          setProjects(list);
          setActiveProjectId(projectId);
        })
        .catch(reportError);
    },
    [reportError],
  );

  /* ---------------------------------------------------- project switching */

  const selectProject = useCallback((projectId: string) => {
    setActiveProjectId(projectId);
    setSidebarView('ops');
  }, []);

  const loadSidebarOps = useCallback(async () => {
    if (!activeProjectId) {
      setSidebarJobs(null);
      setSidebarReminders(null);
      return;
    }
    try {
      const [jobs, reminders] = await Promise.all([
        api.listComputeJobs(activeProjectId, true),
        api.listPendingReminders(activeProjectId),
      ]);
      setSidebarJobs(jobs);
      setSidebarReminders(reminders);
    } catch {
      // ignore transient poll error
    }
  }, [activeProjectId]);

  useEffect(() => {
    if (!activeProjectId || !sidebarOpen || sidebarView !== 'ops') {
      return;
    }
    void loadSidebarOps();
    const timer = setInterval(() => {
      void loadSidebarOps();
    }, 4000);
    return () => clearInterval(timer);
  }, [activeProjectId, sidebarOpen, sidebarView, loadSidebarOps]);

  const selectAgent = useCallback(
    async (agentId: string) => {
      setActiveAgentId(agentId);
      setPendingMessages([]);
      setStreamView({ streamText: '', frozen: [] });
      setOlderEvents([]);
      setLoadingOlder(false);
      setHasOlder(true);
      maxSeqRef.current = 0;
      // Drop any buffered events from the previous agent: they must not leak
      // into the freshly loaded transcript.
      eventBufferRef.current = [];
      if (flushRafRef.current != null) {
        cancelAnimationFrame(flushRafRef.current);
        flushRafRef.current = null;
      }
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
        setHasOlder(eventList.length >= EVENTS_WINDOW);
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
    setOlderEvents([]);
    setLoadingOlder(false);
    setHasOlder(true);
    setStreamView({ streamText: '', frozen: [] });
    maxSeqRef.current = 0;
    setPendingMessages([]);
    setPendingImages([]);
    api
      .listAgents(activeProjectId)
      .then((list) => {
        const agents = dedupeAgents(list);
        setAgents(agents);
        // A jump from the attention dock / a desktop notification overrides
        // the default "select the first agent".
        const jump = jumpTargetRef.current;
        if (jump && jump.projectId === activeProjectId && agents.some((a) => a.id === jump.sessionId)) {
          jumpTargetRef.current = null;
          void selectAgent(jump.sessionId);
        } else if (agents[0]) {
          void selectAgent(agents[0].id);
        }
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
          // Reasoning and content deltas feed streamView via applyStreamEvent.
          if (event.type === 'llm.chunk') {
            setStreamView((prev) => applyStreamEvent(prev, event, maxSeqRef.current));
            return;
          }
          maxSeqRef.current = Math.max(maxSeqRef.current, event.session_seq ?? 0);
          setStreamView((prev) => applyStreamEvent(prev, event, maxSeqRef.current));
          bufferEvent(event);
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

  /* ------------------------------------- cross-project attention polling */

  const jumpTo = useCallback(
    (projectId: string, sessionId: string) => {
      if (projectId === activeProjectId) {
        if (sessionId) void selectAgent(sessionId);
        return;
      }
      jumpTargetRef.current = { projectId, sessionId };
      setActiveProjectId(projectId);
    },
    [activeProjectId, selectAgent],
  );
  // Notification onclick handlers fire outside React; route through a ref
  // so they always call the latest jumpTo.
  const jumpFnRef = useRef(jumpTo);
  jumpFnRef.current = jumpTo;

  const notifyAttention = useCallback((item: PendingAttention) => {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    const title =
      item.kind === 'approval'
        ? `Approval needed · ${item.projectName}`
        : `Agent question · ${item.projectName}`;
    // `tag` collapses repeat polls of the same request into one OS popup.
    const n = new Notification(title, { body: short(`${item.title}: ${item.body}`, 140), tag: item.key });
    n.onclick = () => {
      window.focus();
      jumpFnRef.current(item.projectId, item.sessionId);
      n.close();
    };
  }, []);

  // Poll approvals/ask_user for EVERY non-archived project: the SSE stream
  // and the Inspector only cover the active one, and a request that parks
  // an agent in another project must still reach the user.
  useEffect(() => {
    const targets = projects.filter((p) => !p.archived);
    if (targets.length === 0) {
      setAttention(new Map());
      return;
    }
    let cancelled = false;
    const poll = async () => {
      const results = await Promise.all(
        targets.map(async (p) => {
          try {
            const [approvals, interactions] = await Promise.all([
              api.approvals(p.id),
              api.interactions(p.id),
            ]);
            return [p.id, { name: p.name, approvals, interactions } satisfies ProjectPending] as const;
          } catch {
            return null; // one unreachable project must not sink the rest
          }
        }),
      );
      if (cancelled) return;
      const next = new Map<string, ProjectPending>();
      for (const r of results) if (r) next.set(r[0], r[1]);
      setAttention(next);
      // First poll only seeds the baseline — re-opening the app must not
      // re-alert for long-pending requests.
      const items = collectPending(next);
      if (!attentionBaselineRef.current) {
        attentionBaselineRef.current = true;
        attentionSeenRef.current = new Set(items.map((i) => i.key));
        return;
      }
      const fresh = diffNewItems(items, attentionSeenRef.current);
      attentionSeenRef.current = new Set(items.map((i) => i.key));
      for (const item of fresh) notifyAttention(item);
    };
    void poll();
    const timer = window.setInterval(poll, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [projects, notifyAttention]);

  const refreshProjectPending = useCallback(async (projectId: string) => {
    try {
      const [approvals, interactions] = await Promise.all([
        api.approvals(projectId),
        api.interactions(projectId),
      ]);
      setAttention((prev) => {
        const next = new Map(prev);
        next.set(projectId, { name: prev.get(projectId)?.name ?? '', approvals, interactions });
        return next;
      });
    } catch {
      /* the next poll reconciles */
    }
  }, []);

  const handleAttentionDecide = useCallback(
    async (item: PendingAttention, decision: 'approve' | 'deny') => {
      try {
        await api.decideApproval(item.projectId, item.id, decision, decision === 'deny' ? 'denied by user' : '');
        pushToast('ok', `${decision === 'approve' ? 'Approved' : 'Denied'} · ${item.projectName}`);
      } catch (e) {
        reportError(e);
      } finally {
        await refreshProjectPending(item.projectId);
      }
    },
    [pushToast, reportError, refreshProjectPending],
  );

  const handleAttentionRespond = useCallback(
    async (item: PendingAttention, response: string) => {
      try {
        await api.respondInteraction(item.projectId, item.id, response);
        pushToast('ok', `Response sent · ${item.projectName}`);
      } catch (e) {
        reportError(e);
      } finally {
        await refreshProjectPending(item.projectId);
      }
    },
    [pushToast, reportError, refreshProjectPending],
  );

  /* ------------------------------------------------------------- actions */

  async function createProject(name: string, workspaceDir?: string) {
    const resp = await api.createProject(name, workspaceDir);
    const list = await api.listProjects(true);
    setProjects(list);
    setActiveProjectId(resp.data.id);
    pushToast('ok', `Project "${name}" created`);
  }

  async function createProjectAndSelect() {
    const name = newProject.trim();
    if (!name) return;
    try {
      await createProject(name, newProjectWs.trim() || undefined);
      setNewProject('');
      setNewProjectWs('');
    } catch (e) {
      reportError(e);
    }
  }

  async function submitInlineCreate() {
    const name = inlineCreate?.name.trim();
    if (!name || !inlineCreate) return;
    try {
      await createProject(name, inlineCreate.ws || undefined);
      setInlineCreate(null);
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

  async function archiveProject(p: Project) {
    if (
      !window.confirm(
        `Archive project "${p.name}"?\n\nIt will move to the Archived section; you can restore it later.`,
      )
    ) {
      return;
    }
    try {
      await api.archiveProject(p.id);
      setProjects((prev) => prev.map((x) => (x.id === p.id ? { ...x, archived: true } : x)));
      if (activeProjectId === p.id) setActiveProjectId(null);
      pushToast('ok', `Project "${p.name}" archived`);
    } catch (e) {
      reportError(e);
    }
  }

  async function unarchiveProject(p: Project) {
    try {
      await api.unarchiveProject(p.id);
      setProjects((prev) => prev.map((x) => (x.id === p.id ? { ...x, archived: false } : x)));
      pushToast('ok', `Project "${p.name}" restored`);
    } catch (e) {
      reportError(e);
    }
  }

  async function deleteProject(p: Project) {
    if (
      !window.confirm(
        `Permanently delete project "${p.name}"?\n\nThis cannot be undone: the conversation history and artifacts are erased. The workspace directory is kept.`,
      )
    ) {
      return;
    }
    try {
      const resp = await api.deleteProject(p.id);
      if (!resp.accepted) {
        const err = (resp.data as { error?: { message?: string } } | null)?.error;
        pushToast('error', err?.message ?? 'Delete rejected');
        return;
      }
      setProjects((prev) => prev.filter((x) => x.id !== p.id));
      if (activeProjectId === p.id) setActiveProjectId(null);
      pushToast('ok', `Project "${p.name}" permanently deleted`);
    } catch (e) {
      reportError(e);
    }
  }

  async function cancelAllComputeJobs() {
    if (
      !window.confirm(
        'Cancel ALL unfinished compute jobs?\n\nQueued jobs are cancelled immediately; Slurm jobs are scancelled via their poll loop; local jobs are ledger-cancelled (processes are never killed).',
      )
    ) {
      return;
    }
    try {
      const counts = await api.cancelAllComputeJobs();
      void loadSidebarOps();
      pushToast(
        'ok',
        `Compute jobs cancelled: ${counts.ready_cancelled} queued, ${counts.slurm_cancel_requested} slurm (cancel requested), ${counts.local_cancelled} local`,
      );
    } catch (e) {
      reportError(e);
    }
  }

  async function sendMessage() {
    const content = draft.trim();
    if (!content || !activeProject || sending) return;
    const images = pendingImages.map((p) => p.path);
    const imageArtifactIds = pendingImages.map((p) => p.artifactId);
    setSending(true);
    try {
      if (content.startsWith('/')) {
        const lower = content.toLowerCase();
        if (lower.startsWith('/schedule')) {
          setDraft('');
          const arg = content.slice(9).trim().toLowerCase();
          const currentVal = activeAgent?.settings.schedule_mode ?? activeProject?.settings.defaults?.schedule_mode ?? false;
          const nextVal = arg === 'off' ? false : arg === 'on' ? true : !currentVal;
          await toggleProjectSchedule(nextVal);
          return;
        }
        if (lower.startsWith('/goal')) {
          setDraft('');
          const text = content.slice(5).trim();
          if (!text) {
            pushToast('info', 'Usage: /goal <task objective description>');
            return;
          }
          if (activeAgent) {
            await api.setGoal(activeAgent.id, { objective: text, completion_criteria: '', current_focus: '' });
            pushToast('ok', `Goal set: ${short(text, 50)}`);
          } else {
            pushToast('info', 'Select an agent first to set goal');
          }
          return;
        }
        if (lower.startsWith('/yolo')) {
          setDraft('');
          const arg = content.slice(5).trim().toLowerCase();
          const currentVal = activeAgent?.settings.yolo ?? activeProject?.settings.defaults?.yolo ?? false;
          const nextVal = arg === 'off' ? false : arg === 'on' ? true : !currentVal;
          await toggleProjectYolo(nextVal);
          return;
        }
        if (lower.startsWith('/visual')) {
          setDraft('');
          const arg = content.slice(7).trim().toLowerCase();
          const currentVal = activeAgent?.settings.visual_mode ?? activeProject?.settings.defaults?.visual_mode ?? true;
          const nextVal = arg === 'off' ? false : arg === 'on' ? true : !currentVal;
          await toggleProjectVisual(nextVal);
          return;
        }
        if (lower.startsWith('/compact')) {
          setDraft('');
          if (activeAgent) {
            await api.compactAgent(activeAgent.id);
            pushToast('ok', 'Context compaction requested');
          }
          return;
        }
        if (lower === '/help') {
          setDraft('');
          pushToast('info', 'Commands: /schedule [on|off], /goal <text>, /yolo [on|off], /visual [on|off], /compact');
          return;
        }
      }
      if (interactions.length > 0 && activeProject) {
        const first = interactions[0];
        const ixnId = (first.interaction_id ?? first.id) as string | number | undefined;
        if (ixnId) {
          setDraft('');
          await api.respondInteraction(activeProject.id, ixnId, content);
          pushToast('ok', 'Response sent to agent');
          api.interactions(activeProject.id).then(setInteractions).catch(reportError);
          return;
        }
      }
      setPendingImages([]);
      if (!activeAgent) {
        // With images attached the spawn `query` cannot carry them, so spawn
        // idle and deliver text + images as the first message instead.
        const resp = await api.spawnAgent(activeProject.id, {
          role_id: 'coordinator',
          query: images.length > 0 ? undefined : content,
          settings: {
            orchestration_mode: activeProject.settings.orchestration_mode,
            yolo: activeProject.settings.defaults?.yolo ?? false,
            visual_mode: activeProject.settings.defaults?.visual_mode ?? true,
            schedule_mode: activeProject.settings.defaults?.schedule_mode ?? false,
            invocation_protocol: activeProject.settings.defaults?.invocation_protocol ?? 'javascript',
          },
        });
        setDraft('');
        if (images.length > 0) {
          await api.sendMessage(resp.data.id, content, images, imageArtifactIds);
        }
        await selectAgent(resp.data.id);
      } else {
        // Optimistic echo; reconciled when the SSE echo arrives.
        setPendingMessages((prev) => [
          ...prev,
          {
            kind: 'message',
            id: `pending-${Date.now()}`,
            seq: Number.MAX_SAFE_INTEGER,
            sender: 'user',
            senderLabel: 'user',
            content,
            pending: true,
            imagePaths: images.length > 0 ? images : undefined,
            imageArtifactIds: imageArtifactIds.length > 0 ? imageArtifactIds : undefined,
          },
        ]);
        setDraft('');
        await api.sendMessage(activeAgent.id, content, images, imageArtifactIds);
      }
    } catch (e) {
      setPendingMessages((prev) => prev.filter((m) => m.content !== content));
      setPendingImages((prev) => (prev.length === 0 ? pendingImages : prev));
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
        settings: {
          orchestration_mode: activeProject.settings.orchestration_mode,
          yolo: activeProject.settings.defaults?.yolo ?? false,
          visual_mode: activeProject.settings.defaults?.visual_mode ?? true,
          schedule_mode: activeProject.settings.defaults?.schedule_mode ?? false,
          invocation_protocol: activeProject.settings.defaults?.invocation_protocol ?? 'javascript',
        },
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

  async function cancelAgent(targetId?: string, displayName?: string) {
    const id = targetId ?? activeAgent?.id;
    const name = displayName ?? (targetId ? (agents.find((a) => a.id === targetId)?.display_name ?? targetId) : activeAgent?.display_name);
    if (!id) return;
    try {
      const resp = await api.cancel(id);
      setAgents((prev) => dedupeAgents(prev.map((a) => (a.id === resp.data.id ? resp.data : a))));
      pushToast('ok', `Cancelled ${name ?? id}`);
    } catch (e) {
      reportError(e);
    }
  }

  async function toggleProjectSchedule(checked: boolean) {
    if (!activeProject) return;
    try {
      const resp = await api.patchProject(activeProject.id, {
        settings: {
          orchestration_mode: activeProject.settings.orchestration_mode,
          defaults: Object.fromEntries(
            Object.entries({ ...activeProject.settings.defaults, schedule_mode: checked }).filter(
              ([, v]) => v !== null && v !== undefined,
            ),
          ),
        },
      });
      setProjects((prev) => prev.map((p) => (p.id === activeProject.id ? resp.data : p)));
      const targets = dedupeAgents(
        agents.filter((a) => a.project_id === activeProject.id && a.settings.schedule_mode !== checked),
      );
      const updated = await Promise.all(targets.map((a) => api.patchSettings(a.id, { schedule_mode: checked })));
      if (updated.length > 0) {
        setAgents((prev) =>
          dedupeAgents(prev.map((a) => updated.find((u) => u.data.id === a.id)?.data ?? a)),
        );
      }
      pushToast('ok', `Schedule mode ${checked ? 'on' : 'off'} (project-wide)`);
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

  async function toggleProjectVisual(checked: boolean) {
    if (!activeProject) return;
    try {
      // 项目级 visual 模式：与 YOLO 同构——写项目 defaults（新 spawn 继承）并级联
      // PATCH 现存 agent（settings 是 spawn 时快照）。project settings 整对象
      // 校验替换，orchestration_mode 必须带回。
      const resp = await api.patchProject(activeProject.id, {
        settings: {
          orchestration_mode: activeProject.settings.orchestration_mode,
          defaults: Object.fromEntries(
            Object.entries({ ...activeProject.settings.defaults, visual_mode: checked }).filter(
              ([, v]) => v !== null && v !== undefined,
            ),
          ),
        },
      });
      setProjects((prev) => prev.map((p) => (p.id === activeProject.id ? resp.data : p)));
      const targets = dedupeAgents(
        agents.filter((a) => a.project_id === activeProject.id && (a.settings.visual_mode ?? true) !== checked),
      );
      const updated = await Promise.all(targets.map((a) => api.patchSettings(a.id, { visual_mode: checked })));
      if (updated.length > 0) {
        setAgents((prev) =>
          dedupeAgents(prev.map((a) => updated.find((u) => u.data.id === a.id)?.data ?? a)),
        );
      }
      pushToast('ok', `Visual mode ${checked ? 'on' : 'off'} (project-wide)`);
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

  async function onPickImages(files: FileList | null) {
    if (!files || files.length === 0 || !activeProject) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const resp = await api.uploadFile(activeProject.id, file);
        uploadedArtifactsRef.current.set(resp.path, resp.artifact_id);
        setPendingImages((prev) => [...prev, { path: resp.path, artifactId: resp.artifact_id, name: file.name, size: file.size }]);
      }
    } catch (e) {
      reportError(e);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  /** Resolve a message item's attachments to downloadable URLs (artifact id
   * from the payload, else the session upload map keyed by path). */
  function messageImageUrls(item: MessageItem): string[] {
    if (!activeProject) return [];
    const ids = item.imageArtifactIds ?? [];
    const paths = item.imagePaths ?? [];
    const urls: string[] = [];
    for (let i = 0; i < Math.max(ids.length, paths.length); i++) {
      const id = ids[i] ?? (paths[i] ? uploadedArtifactsRef.current.get(paths[i]) : undefined);
      if (id) urls.push(api.artifactDownloadUrl(activeProject.id, id));
    }
    return urls;
  }

  /* ------------------------------------------------------------ rendering */

  const sessionEvents = useMemo(
    () =>
      activeAgentId
        ? [...olderEvents, ...events].filter((e) => e.session_id === activeAgentId)
        : [],
    [olderEvents, events, activeAgentId],
  );
  // Persisted events → timeline items is the expensive step (full sort +
  // stringification of every tool args/result).  It must only re-run when the
  // event list actually changes — NOT on every streaming token — otherwise a
  // tool-heavy run re-builds the whole transcript per llm.chunk.
  const persistedTimeline = useMemo(() => buildTimeline(sessionEvents, []), [sessionEvents]);
  // Committed timeline: persisted items + frozen narration, sorted once.  The
  // live streaming bubble and the transient thinking segments stay out of this
  // memo so token deltas never re-trigger the O(n log n) sort.
  const committedTimeline = useMemo(() => {
    const persisted = new Set(
      persistedTimeline
        .filter((i): i is MessageItem => i.kind === 'message')
        .map((m) => m.content),
    );
    const frozen = streamView.frozen.filter((m) => !persisted.has(m.content));
    const merged: TimelineItem[] = [...persistedTimeline, ...frozen];
    merged.sort((a, b) => a.seq - b.seq);
    return merged;
  }, [persistedTimeline, streamView.frozen]);
  const timeline = useMemo(() => {
    // Live bubble before thinking/pending messages, transient streaming thinking,
    // and optimistic pending user messages.
    const items: TimelineItem[] = [...committedTimeline];
    if (streamView.streamText) {
      items.push({
        kind: 'message',
        id: 'stream-live',
        seq: maxSeqRef.current + 0.4,
        sender: 'assistant',
        senderLabel: activeAgent?.display_name ?? 'assistant',
        content: streamView.streamText,
        streaming: true,
      });
    }
    if (streamView.streamThinking) {
      const st = streamView.streamThinking;
      const alreadyPersisted = committedTimeline.some(
        (it) =>
          it.kind === 'thinking' &&
          (it.text === st ||
            it.text.startsWith(st) ||
            st.startsWith(it.text)),
      );
      if (!alreadyPersisted) {
        items.push({
          kind: 'thinking',
          id: 'stream-thinking',
          seq: streamView.streamThinkingSeq || maxSeqRef.current + 0.3,
          text: st,
          live: Boolean(streamView.streamThinkingLive),
        });
      }
    }
    items.push(...pendingMessages);
    items.sort((a, b) => a.seq - b.seq);
    return items;
  }, [
    committedTimeline,
    streamView.streamText,
    streamView.streamThinking,
    streamView.streamThinkingLive,
    streamView.streamThinkingSeq,
    pendingMessages,
    activeAgent?.display_name,
  ]);
  const runningTool = useMemo(
    () => {
      for (const item of timeline) {
        if (item.kind === 'tool' && item.running) return item as ToolItem;
        // Program children run nested: surface the active child in the
        // current-working indicator exactly like a top-level tool.
        if (item.kind === 'program') {
          const child = item.children.find((c) => c.running);
          if (child) return child;
        }
      }
      return undefined;
    },
    [timeline],
  );
  const liveThinking = Boolean(streamView.streamThinkingLive);

  const currentAgentActivity = useMemo<{
    type: 'generating' | 'running_tool' | 'waiting' | 'thinking' | 'running' | 'idle';
    label: string;
  }>(() => {
    if (streamView.streamText) {
      return { type: 'generating', label: 'Streaming response…' };
    }
    if (runningTool) {
      return {
        type: 'running_tool',
        label: `Running ${runningTool.name}${runningTool.argsSummary ? `: ${runningTool.argsSummary.slice(0, 50)}` : '…'}`,
      };
    }
    if (liveThinking) {
      return { type: 'thinking', label: 'Reasoning / Thinking…' };
    }
    if (activeAgent?.state === 'running') {
      return { type: 'running', label: 'Processing turn…' };
    }
    if (activeAgent?.state === 'waiting_approval') {
      return { type: 'waiting', label: 'Waiting for approval' };
    }
    if (activeAgent?.state === 'waiting_input') {
      return { type: 'waiting', label: 'Waiting for user input' };
    }
    return { type: 'idle', label: 'Ready' };
  }, [streamView.streamText, runningTool, liveThinking, activeAgent?.state]);

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

  // The dock covers only OTHER projects — the active one already surfaces
  // requests via the Inspector tabs and the composer ask-banner.
  const attentionItems = useMemo(() => {
    const others = new Map(attention);
    if (activeProjectId) others.delete(activeProjectId);
    return collectPending(others);
  }, [attention, activeProjectId]);

  const renderSidebarAgentItem = (a: Agent, depth: number): React.ReactNode => {
    const children = childrenOf.get(a.id) ?? [];
    const childCount = children.length;
    const expanded = expandedAgents.has(a.id);
    const isCoordinator = a.role_id === 'coordinator';
    const isActive = a.id === activeAgentId;
    const isRunning = a.state === 'running';
    const isWaiting = a.state === 'waiting_approval' || a.state === 'waiting_input';

    return (
      <Fragment key={a.id}>
        <div
          className={`sidebar-agent-row ${isActive ? 'active' : ''} ${isRunning ? 'is-running' : ''}`}
          style={{ paddingLeft: 8 + depth * 14 }}
          onClick={() => void selectAgent(a.id)}
          title={`Agent: ${a.display_name} (${a.role_id}) · state: ${a.state}`}
        >
          {childCount > 0 ? (
            <button
              type="button"
              className="sidebar-agent-caret"
              title={expanded ? 'Collapse sub-agents' : `Expand ${childCount} sub-agent(s)`}
              onClick={(e) => {
                e.stopPropagation();
                toggleAgentExpanded(a.id);
              }}
            >
              {expanded ? '▾' : '▸'}
            </button>
          ) : (
            <span className="sidebar-agent-spacer" />
          )}

          <span className={`state-dot ${a.state}`} />
          {isCoordinator ? (
            <span className="sidebar-agent-role coordinator" title="Coordinator">COORD</span>
          ) : (
            <span className="sidebar-agent-role" title={a.role_id}>{a.role_id}</span>
          )}
          <span className="sidebar-agent-name">{a.display_name}</span>

          {isWaiting && (
            <span className="sidebar-agent-badge waiting" title="Waiting for approval / input">!</span>
          )}

          {isRunning && (
            <button
              type="button"
              className="sidebar-agent-cancel"
              title={`Cancel ${a.display_name}`}
              onClick={(e) => {
                e.stopPropagation();
                void cancelAgent(a.id, a.display_name);
              }}
            >
              ✕
            </button>
          )}
        </div>
        {expanded && children.map((c) => renderSidebarAgentItem(c, depth + 1))}
      </Fragment>
    );
  };

  const chatRef = useRef<HTMLDivElement | null>(null);
  const nearBottomRef = useRef(true);
  useEffect(() => {
    const el = chatRef.current;
    if (el && nearBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [timeline, streamView, activeAgent?.state]);
  // Prepending an older page must not yank the viewport: capture the scroll
  // geometry before the fetch and re-anchor by the height delta after the new
  // page renders.  (The auto-scroll above is a no-op here — nearBottom is
  // false while the user is up at the top.)
  const scrollRestoreRef = useRef<{ height: number } | null>(null);
  useLayoutEffect(() => {
    const el = chatRef.current;
    const restore = scrollRestoreRef.current;
    if (el && restore) {
      scrollRestoreRef.current = null;
      el.scrollTop += el.scrollHeight - restore.height;
    }
  }, [olderEvents]);
  const loadOlder = useCallback(async () => {
    if (!activeAgentId || loadingOlder || !hasOlder) return;
    let oldest = Infinity;
    for (const e of olderEvents) {
      if (e.session_id === activeAgentId) oldest = Math.min(oldest, e.session_seq ?? Infinity);
    }
    for (const e of events) {
      if (e.session_id === activeAgentId) oldest = Math.min(oldest, e.session_seq ?? Infinity);
    }
    if (!Number.isFinite(oldest)) return;
    const el = chatRef.current;
    if (el) scrollRestoreRef.current = { height: el.scrollHeight };
    setLoadingOlder(true);
    try {
      const page = await api.eventsPage(activeAgentId, { before: oldest, limit: HISTORY_PAGE_SIZE });
      const known = new Set([...olderEvents, ...events].map((e) => e.event_id));
      const fresh = page.filter((e) => !known.has(e.event_id));
      setOlderEvents((prev) => [...fresh, ...prev]);
      if (page.length < HISTORY_PAGE_SIZE) setHasOlder(false);
    } catch (e) {
      reportError(e);
    } finally {
      setLoadingOlder(false);
    }
  }, [activeAgentId, loadingOlder, hasOlder, olderEvents, events, reportError]);

  const connLabel = !activeProject ? 'idle' : connState === 'live' ? 'live' : connState === 'connecting' ? 'connecting' : 'reconnecting…';
  const totalPending = approvals.length + interactions.length;

  return (
    <div className={`app ${resizingSide ? 'resizing' : ''}`}>
      <datalist id="workspace-dirs">
        {workspaceSuggestions.map((ws) => (
          <option key={ws} value={ws} />
        ))}
      </datalist>
      {sidebarOpen && (
        <aside className="sidebar" style={{ width: sidebarWidth }}>
          {activeProject && sidebarView === 'ops' ? (
            <>
              <div className="sidebar-ops-header">
                <div className="sidebar-nav-row">
                  <button
                    type="button"
                    className="sidebar-back-btn"
                    onClick={() => setSidebarView('projects')}
                    title="Switch project / view all projects"
                  >
                    ← All Projects
                  </button>
                  <button
                    type="button"
                    className="btn ghost sm project-archive"
                    title={`Archive "${activeProject.name}"`}
                    onClick={() => void archiveProject(activeProject)}
                  >
                    ⬇ Archive
                  </button>
                </div>
                <div className="sidebar-project-info">
                  <div className="sidebar-project-title" title={activeProject.name}>
                    {activeProject.name}
                  </div>
                  {editingWs ? (
                    <div className="ws-edit-row">
                      <input
                        key={`sidebar-ws-${activeProject.id}`}
                        className="input ws-input"
                        autoFocus
                        defaultValue={activeProject.workspace_dir ?? ''}
                        placeholder="workspace dir…"
                        title="Workspace directory: this project's agents read/write within it. Edit and press Enter to change; clear to unset."
                        list="workspace-dirs"
                        onBlur={(e) => {
                          setEditingWs(false);
                          changeWorkspace(e.target.value);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            setEditingWs(false);
                            changeWorkspace((e.target as HTMLInputElement).value);
                          } else if (e.key === 'Escape') {
                            setEditingWs(false);
                          }
                        }}
                      />
                      <button
                        type="button"
                        className="btn ghost sm ws-browse-btn"
                        title="Browse directory"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => {
                          setEditingWs(false);
                          openPathPicker({
                            title: `Select Workspace for ${activeProject.name}`,
                            initialPath: activeProject.workspace_dir ?? undefined,
                            onSelect: (p) => changeWorkspace(p),
                          });
                        }}
                      >
                        📁
                      </button>
                    </div>
                  ) : (
                    <div className="ws-pill-row">
                      <button
                        type="button"
                        className={`agentbar-ws-pill ${!activeProject.workspace_dir ? 'empty' : ''}`}
                        title={activeProject.workspace_dir ? `Workspace: ${activeProject.workspace_dir} (click to edit)` : 'Set workspace directory (click to edit)'}
                        onClick={() => setEditingWs(true)}
                      >
                        <span className="ws-pill-icon">WS:</span>
                        <span className="ws-pill-text">
                          {activeProject.workspace_dir
                            ? (activeProject.workspace_dir.split('/').filter(Boolean).pop() || activeProject.workspace_dir)
                            : 'bind workspace'}
                        </span>
                      </button>
                      <button
                        type="button"
                        className="btn ghost sm ws-pill-browse"
                        title="Browse and select workspace folder"
                        onClick={() =>
                          openPathPicker({
                            title: `Select Workspace for ${activeProject.name}`,
                            initialPath: activeProject.workspace_dir ?? undefined,
                            onSelect: (p) => changeWorkspace(p),
                          })
                        }
                      >
                        📁
                      </button>
                    </div>
                  )}
                </div>
              </div>

              <div className="sidebar-ops-content">
                {/* Agent Swarm Section */}
                <div className="sidebar-section">
                  <div className="sidebar-section-header">
                    <span className="sidebar-section-title">Agent Swarm ({agents.length})</span>
                    <div className="sidebar-spawn-wrap">
                      <select
                        className="select sidebar-spawn-select"
                        value=""
                        onChange={(e) => {
                          if (e.target.value) void spawnRole(e.target.value);
                        }}
                        title="Spawn specialized subagent"
                      >
                        <option value="">+ Spawn…</option>
                        {roles.map((r) => (
                          <option key={r.role_id} value={r.role_id}>{r.display_name}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {agents.length === 0 ? (
                    <div className="sidebar-empty-hint">No agents spawned yet.</div>
                  ) : (
                    <div className="sidebar-agent-tree">
                      {rootAgents.map((a) => renderSidebarAgentItem(a, 0))}
                    </div>
                  )}
                </div>

                {/* Ops Telemetry Section */}
                <div className="sidebar-section sidebar-ops-section">
                  <div className="sidebar-section-header">
                    <span className="sidebar-section-title">
                      Compute Queue {sidebarJobs && sidebarJobs.length > 0 ? `(${sidebarJobs.length})` : ''}
                    </span>
                    {sidebarJobs && sidebarJobs.length > 0 && (
                      <button
                        type="button"
                        className="btn ghost xs sidebar-cancel-all-btn"
                        title="Cancel all active compute jobs"
                        onClick={() => void cancelAllComputeJobs()}
                      >
                        Cancel All
                      </button>
                    )}
                  </div>
                  {sidebarJobs === null ? (
                    <div className="sidebar-ops-empty">Loading jobs…</div>
                  ) : sidebarJobs.length === 0 ? (
                    <div className="sidebar-ops-empty">No active compute jobs</div>
                  ) : (
                    <div className="sidebar-jobs-list">
                      {sidebarJobs.slice(0, 5).map((j) => (
                        <div
                          key={j.id}
                          className="sidebar-job-row"
                          title={`#${j.id} ${j.jobtype} @ ${j.node_id ?? 'unassigned'} - ${j.path}`}
                        >
                          <span className="sidebar-job-id">#{j.id}</span>
                          <span className="sidebar-job-type">{j.jobtype}</span>
                          <span className={`state-badge xs ${j.state}`}>{j.state}</span>
                          <span className="sidebar-job-time">{elapsed(j.start_timestamp)}</span>
                        </div>
                      ))}
                      {sidebarJobs.length > 5 && (
                        <div className="sidebar-ops-more">+{sidebarJobs.length - 5} more jobs</div>
                      )}
                    </div>
                  )}

                  {sidebarReminders && sidebarReminders.length > 0 && (
                    <>
                      <div className="sidebar-section-header" style={{ marginTop: 10 }}>
                        <span className="sidebar-section-title">
                          Reminders ({sidebarReminders.length})
                        </span>
                      </div>
                      <div className="sidebar-reminders-list">
                        {sidebarReminders.slice(0, 3).map((r) => (
                          <div key={r.schedule_id} className="sidebar-reminder-row" title={r.message}>
                            <span className="sidebar-reminder-time">{wakeCountdown(r.wake_ts)}</span>
                            <span className="sidebar-reminder-msg">{r.message}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}

                  <button
                    type="button"
                    className="sidebar-open-ops-btn"
                    onClick={() => {
                      setInspectorOpen(true);
                      setInspectorTab('ops');
                    }}
                  >
                    Open Ops in Inspector →
                  </button>
                </div>
              </div>

              <div className="sidebar-foot">
                <button
                  type="button"
                  className="sidebar-foot-item"
                  onClick={() => setSidebarView('projects')}
                  title="Switch to another project"
                >
                  <span className="sidebar-foot-label">Switch Project</span>
                </button>
                <button
                  type="button"
                  className={`sidebar-foot-item sidebar-global ${globalOpen ? 'active' : ''}`}
                  title="Global LLM config"
                  onClick={() => setGlobalOpen(true)}
                >
                  <span className="sidebar-foot-label">Global Settings</span>
                </button>
                <button
                  type="button"
                  className={`sidebar-foot-item sidebar-knowledge ${knowledgeOpen ? 'active' : ''}`}
                  title="chem-kb knowledge base"
                  onClick={() => setKnowledgeOpen(true)}
                >
                  <span className="sidebar-foot-label">Knowledge Base</span>
                </button>
                <button
                  type="button"
                  className={`sidebar-foot-item sidebar-benchmark ${benchmarkOpen ? 'active' : ''}`}
                  title="Benchmark cockpit"
                  onClick={() => setBenchmarkOpen(true)}
                >
                  <span className="sidebar-foot-label">Benchmark</span>
                </button>
                <button
                  type="button"
                  className={`sidebar-foot-item sidebar-telemetry ${telemetryOpen ? 'active' : ''}`}
                  title="LLM telemetry: token usage, prompt cache analysis, context export"
                  onClick={() => setTelemetryOpen(true)}
                >
                  <span className="sidebar-foot-label">Telemetry</span>
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="sidebar-head">
                <img className="brand-logo" src="/logo.png" alt="Cloudra" />
              </div>
              {activeProject && (
                <button
                  type="button"
                  className="sidebar-back-to-active"
                  onClick={() => setSidebarView('ops')}
                  title={`Return to active project: ${activeProject.name}`}
                >
                  <span>← Current:</span>
                  <strong style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{activeProject.name}</strong>
                </button>
              )}
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
                <div className="ws-input-wrap">
                  <input
                    className="input ws-path"
                    value={newProjectWs}
                    onChange={(e) => setNewProjectWs(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && createProjectAndSelect()}
                    placeholder="workspace dir (optional)…"
                    title="Workspace directory: agents read/write within it"
                    list="workspace-dirs"
                  />
                  <button
                    type="button"
                    className="btn ghost sm ws-browse-btn"
                    title="Browse and select workspace folder"
                    onClick={() =>
                      openPathPicker({
                        title: 'Select Workspace Directory',
                        initialPath: newProjectWs,
                        onSelect: (p) => setNewProjectWs(p),
                      })
                    }
                  >
                    📁
                  </button>
                </div>
              </div>
              <div className="project-list">
                {projects.length === 0 && <div className="empty-hint">No projects yet — create one above.</div>}
                {groupedProjects.map(([ws, list]) => (
                  <div key={ws || '__none'} className="ws-group">
                    <div className="ws-header-row">
                      <div className="ws-header" title={ws || undefined}>{ws || 'no workspace'}</div>
                      <button
                        type="button"
                        className="btn ghost sm ws-add"
                        title={ws ? `New project in ${ws}` : 'New project without workspace'}
                        onClick={() => setInlineCreate({ ws, name: '' })}
                      >
                        +
                      </button>
                    </div>
                    {inlineCreate?.ws === ws && (
                      <div className="ws-inline-create">
                        <input
                          className="input"
                          autoFocus
                          value={inlineCreate.name}
                          onChange={(e) => setInlineCreate({ ws, name: e.target.value })}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') void submitInlineCreate();
                            if (e.key === 'Escape') setInlineCreate(null);
                          }}
                          placeholder="Project name…"
                        />
                        <button
                          type="button"
                          className="btn primary sm"
                          disabled={!inlineCreate.name.trim()}
                          onClick={() => void submitInlineCreate()}
                        >
                          Create
                        </button>
                      </div>
                    )}
                    {list.map((p) => (
                      <div
                        key={p.id}
                        className={`project-item ${p.id === activeProjectId ? 'active' : ''}`}
                        onClick={() => selectProject(p.id)}
                      >
                        <div className="project-name">{p.name}</div>
                        <div className="project-meta">
                          {p.name.startsWith('benchmark:') ? '[Benchmark] ' : ''}
                          {p.settings.orchestration_mode}
                        </div>
                        <button
                          type="button"
                          className="btn ghost sm project-archive"
                          title={`Archive "${p.name}"`}
                          onClick={(e) => {
                            e.stopPropagation();
                            void archiveProject(p);
                          }}
                        >
                          ⬇
                        </button>
                      </div>
                    ))}
                  </div>
                ))}
                {archivedProjects.length > 0 && (
                  <details className="archived-group">
                    <summary>Archived ({archivedProjects.length})</summary>
                    {archivedProjects.map((p) => (
                      <div
                        key={p.id}
                        className={`project-item archived ${p.id === activeProjectId ? 'active' : ''}`}
                        onClick={() => selectProject(p.id)}
                      >
                        <div className="project-name">{p.name}</div>
                        <div className="project-meta">archived · {p.settings.orchestration_mode}</div>
                        <button
                          type="button"
                          className="btn ghost sm project-archive"
                          title={`Restore "${p.name}"`}
                          onClick={(e) => {
                            e.stopPropagation();
                            void unarchiveProject(p);
                          }}
                        >
                          ⬆
                        </button>
                        <button
                          type="button"
                          className="btn ghost sm project-archive"
                          title={`Delete "${p.name}" permanently (workspace directory is kept)`}
                          onClick={(e) => {
                            e.stopPropagation();
                            void deleteProject(p);
                          }}
                        >
                          🗑
                        </button>
                      </div>
                    ))}
                  </details>
                )}
              </div>
              <div className="sidebar-foot">
                <button
                  type="button"
                  className={`sidebar-foot-item sidebar-global ${globalOpen ? 'active' : ''}`}
                  title="Global LLM config: the fallback slots behind empty per-agent settings"
                  onClick={() => setGlobalOpen(true)}
                >
                  <span className="sidebar-foot-label">Global Settings</span>
                </button>
                <button
                  type="button"
                  className={`sidebar-foot-item sidebar-knowledge ${knowledgeOpen ? 'active' : ''}`}
                  title="chem-kb knowledge base: overview, entity search and ego graph"
                  onClick={() => setKnowledgeOpen(true)}
                >
                  <span className="sidebar-foot-label">Knowledge Base</span>
                </button>
                <button
                  type="button"
                  className={`sidebar-foot-item sidebar-benchmark ${benchmarkOpen ? 'active' : ''}`}
                  title="Benchmark cockpit: run task batches and drill into per-task scores"
                  onClick={() => setBenchmarkOpen(true)}
                >
                  <span className="sidebar-foot-label">Benchmark</span>
                </button>
                <button
                  type="button"
                  className={`sidebar-foot-item sidebar-telemetry ${telemetryOpen ? 'active' : ''}`}
                  title="LLM telemetry: token usage, prompt cache analysis, context export"
                  onClick={() => setTelemetryOpen(true)}
                >
                  <span className="sidebar-foot-label">Telemetry</span>
                </button>
                <button
                  type="button"
                  className="sidebar-foot-item sidebar-compute-cancel"
                  title="Cancel all unfinished compute jobs (ledger-level; never kills processes)"
                  onClick={() => void cancelAllComputeJobs()}
                >
                  <span className="sidebar-foot-label">Cancel All Compute Jobs</span>
                </button>
              </div>
            </>
          )}
        </aside>
      )}
      {sidebarOpen && (
        <div
          className={`resizer resizer-sidebar ${resizingSide === 'sidebar' ? 'active' : ''}`}
          onMouseDown={(e) => {
            e.preventDefault();
            setResizingSide('sidebar');
          }}
          title="Drag to resize sidebar"
        />
      )}

      <main className="main">
        <div className="agentbar">
          <div className="agentbar-left">
            <button
              type="button"
              className="btn ghost sm panel-toggle"
              title={sidebarOpen ? 'Hide sidebar (Cmd+B)' : 'Show sidebar (Cmd+B)'}
              onClick={() => setSidebarOpen((v) => !v)}
            >
              {sidebarOpen ? '◀' : '▶'}
            </button>
            <div className="header-breadcrumb">
              <span
                className="breadcrumb-project"
                title={activeProject?.name ? `Project: ${activeProject.name} (click to view in sidebar)` : 'Select a project'}
                onClick={() => {
                  if (!sidebarOpen) setSidebarOpen(true);
                  if (activeProject) setSidebarView('ops');
                }}
              >
                {activeProject?.name ?? 'Select a project'}
              </span>
              {activeAgent && (
                <>
                  <span className="breadcrumb-separator">/</span>
                  <span className="breadcrumb-agent" title={`Active Agent: ${activeAgent.display_name} (${activeAgent.role_id}) · state: ${activeAgent.state}`}>
                    <span className={`state-dot ${activeAgent.state}`} />
                    <span className="breadcrumb-agent-name">{activeAgent.display_name}</span>
                    <span className="badge role-badge">{activeAgent.role_id}</span>
                  </span>
                </>
              )}
            </div>
          </div>

          <div className="agentbar-group system-controls">
            {activeAgent && (
              <div
                className={`agentbar-activity-pill ${currentAgentActivity.type}`}
                title={`Active agent: ${activeAgent.display_name} · ${currentAgentActivity.label}`}
              >
                <span className={`state-dot ${currentAgentActivity.type === 'idle' ? 'idle' : currentAgentActivity.type === 'waiting' ? 'waiting_input' : 'running'}`} />
                <span className="activity-label">{currentAgentActivity.label}</span>
              </div>
            )}
            {activeProject && (
              <div className="agentbar-control-item" title="Orchestration mode: Controls DAG generation and supervision workflow">
                <span className="control-label">Mode</span>
                <select
                  className="select agentbar-select mode"
                  value={activeProject.settings.orchestration_mode}
                  onChange={(e) => changeOrchestrationMode(e.target.value)}
                >
                  <option value="standard">standard (Direct)</option>
                  <option value="dag_record">dag_record (Record)</option>
                  <option value="dag_guided">dag_guided (Supervised)</option>
                </select>
              </div>
            )}
            {activeProject && (
              <button
                type="button"
                className={`yolo-toggle-badge ${activeProject.settings.defaults?.yolo === true ? 'active' : 'guarded'}`}
                title="Safety Policy: YOLO mode auto-approves destructive shell & compute actions via guard model. Click to toggle project-wide."
                onClick={() => toggleProjectYolo(!(activeProject.settings.defaults?.yolo === true))}
              >
                <span className="yolo-tag">{activeProject.settings.defaults?.yolo === true ? 'YOLO' : 'SAFE'}</span>
              </button>
            )}
            <span className="conn-status" title={`SSE stream status: ${connLabel}`}>
              {activeProject && <span className={`state-dot ${connState === 'live' ? 'running' : 'waiting_input'}`} />}
              <span className="conn-label">{connLabel}</span>
            </span>
            <button
              type="button"
              className={`btn ghost sm panel-toggle inspector-toggle-btn ${inspectorOpen ? 'active' : ''} ${totalPending > 0 ? 'attention' : ''}`}
              title={inspectorOpen ? 'Hide inspector' : `Show inspector${totalPending > 0 ? ` (${totalPending} action required)` : ''}`}
              onClick={() => setInspectorOpen((v) => !v)}
            >
              <span>{inspectorOpen ? 'Inspector ▶' : '◀ Inspector'}</span>
              {totalPending > 0 && <span className="badge attention-badge">{totalPending}</span>}
            </button>
          </div>
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
            {activeAgent && hasOlder && timeline.length > 0 && (
              <button className="load-earlier" disabled={loadingOlder} onClick={() => void loadOlder()}>
                {loadingOlder ? 'loading…' : 'Load earlier'}
              </button>
            )}
            {activeAgent && !hasOlder && olderEvents.length > 0 && (
              <div className="history-end">beginning of history</div>
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
                    <div className="msg-bubble">
                      {item.content}
                      {messageImageUrls(item).length > 0 && (
                        <div className="msg-images">
                          {messageImageUrls(item).map((url) => (
                            <a key={url} href={url} target="_blank" rel="noreferrer">
                              <img src={url} alt="attachment" loading="lazy" />
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="msg-body">
                      {/* Streaming text renders as plain text to avoid a full
                          remark/KaTeX parse on every token; committed messages
                          get markdown. */}
                      {item.streaming ? item.content : <Markdown text={item.content} />}
                    </div>
                  )}
                </div>
              ) : item.kind === 'tool' ? (
                <ToolRow
                  key={item.id}
                  item={item}
                  imageUrl={
                    item.imageArtifactId && activeProject
                      ? api.artifactDownloadUrl(activeProject.id, item.imageArtifactId)
                      : null
                  }
                />
              ) : item.kind === 'program' ? (
                <ProgramCard
                  key={item.id}
                  item={item}
                  childImageUrl={(child) =>
                    child.imageArtifactId && activeProject
                      ? api.artifactDownloadUrl(activeProject.id, child.imageArtifactId)
                      : null
                  }
                />
              ) : item.kind === 'thinking' ? (
                <ThinkingBlock key={item.id} item={item} />
              ) : (
                <div
                  key={item.id}
                  className={`tool-row ${item.level === 'warn' ? 'fail' : 'info'}`}
                  style={{ cursor: 'default' }}
                >
                  <span className="tool-icon">{item.level === 'warn' ? '!' : 'ℹ'}</span>
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
          {matchingSlash.length > 0 && (
            <div className="slash-menu">
              <div className="slash-header">
                <span>Commands</span>
                <span className="slash-header-hint">Tab or Enter to select · Esc to dismiss</span>
              </div>
              <div className="slash-list">
                {matchingSlash.map((cmd, idx) => (
                  <div
                    key={cmd.command}
                    className={`slash-item ${idx === slashSelected ? 'selected' : ''}`}
                    onClick={() => selectSlashCommand(cmd)}
                    onMouseEnter={() => setSlashSelected(idx)}
                  >
                    <span className="slash-cmd">{cmd.command}</span>
                    {cmd.args && <span className="slash-args">{cmd.args}</span>}
                    <span className="slash-desc">{cmd.desc}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {interactions.length > 0 && (
            <div className="ask-banner">
              <span className="state-dot waiting_input" />
              <span>
                Agent is asking: {short(cleanPromptText(interactions[0].prompt ?? interactions[0].message), 100)} (type below to answer)
                {interactions.length > 1 ? ` (+${interactions.length - 1} more)` : ''}
              </span>
            </div>
          )}
          <div className="composer">
            {pendingImages.length > 0 && activeProject && (
              <div className="composer-attachments">
                {pendingImages.map((img) => (
                  <span
                    key={img.path}
                    className="composer-attachment"
                    title={`${img.name} · ${fmtBytes(img.size)}`}
                  >
                    <img src={api.artifactDownloadUrl(activeProject.id, img.artifactId)} alt={img.name} />
                    <span className="attachment-name">{img.name}</span>
                    <button
                      type="button"
                      className="attachment-remove"
                      title={`Remove ${img.name}`}
                      onClick={() => setPendingImages((prev) => prev.filter((p) => p.path !== img.path))}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <textarea
              ref={composerTextareaRef}
              rows={2}
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                setSlashDismissed(false);
                setSlashSelected(0);
              }}
              onKeyDown={(e) => {
                if (matchingSlash.length > 0) {
                  if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    setSlashSelected((prev) => (prev + 1) % matchingSlash.length);
                    return;
                  }
                  if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    setSlashSelected((prev) => (prev - 1 + matchingSlash.length) % matchingSlash.length);
                    return;
                  }
                  if (
                    e.key === 'Tab' ||
                    (e.key === 'Enter' && !e.shiftKey && slashPrefix !== matchingSlash[slashSelected]?.command.toLowerCase())
                  ) {
                    e.preventDefault();
                    const selected = matchingSlash[slashSelected] || matchingSlash[0];
                    if (selected) {
                      selectSlashCommand(selected);
                      return;
                    }
                  }
                  if (e.key === 'Escape') {
                    e.preventDefault();
                    setSlashDismissed(true);
                    return;
                  }
                }
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void sendMessage();
                }
              }}
              placeholder={
                !activeProject
                  ? 'Select or create a project first…'
                  : interactions.length > 0
                    ? `Reply to ${activeAgent?.display_name ?? 'agent'}: ${short(cleanPromptText(interactions[0].prompt ?? interactions[0].message), 60)}…`
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
              {visualOn && (
                <>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                    multiple
                    hidden
                    onChange={(e) => void onPickImages(e.target.files)}
                  />
                  <button
                    type="button"
                    className="btn ghost sm"
                    title="Attach images to the message (png/jpg/jpeg/webp, max 20 MB each)"
                    disabled={uploading}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {uploading ? 'Uploading…' : 'Attach Image'}
                  </button>
                </>
              )}
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

      {inspectorOpen && (
        <div
          className={`resizer resizer-inspector ${resizingSide === 'inspector' ? 'active' : ''}`}
          onMouseDown={(e) => {
            e.preventDefault();
            setResizingSide('inspector');
          }}
          title="Drag to resize inspector"
        />
      )}

      {inspectorOpen && (
        <Inspector
          width={inspectorWidth}
          activeAgent={activeAgent}
          activeProject={activeProject}
          agents={agents}
          liveEvents={sessionEvents}
          onPatchSettings={patchSettings}
          approvals={approvals}
          interactions={interactions}
          onRefreshApprovals={() => activeProject && api.approvals(activeProject.id).then(setApprovals).catch(reportError)}
          onRefreshInteractions={() => activeProject && api.interactions(activeProject.id).then(setInteractions).catch(reportError)}
          onError={reportError}
          onToast={pushToast}
          onClose={() => setInspectorOpen(false)}
          currentAgentActivity={currentAgentActivity}
          onToggleYolo={(yolo) => toggleProjectYolo(yolo)}
          onChangeMode={(mode) => changeOrchestrationMode(mode)}
          onChangeWorkspace={(ws) => changeWorkspace(ws)}
          onOpenPathPicker={openPathPicker}
          tab={inspectorTab}
          onSelectTab={setInspectorTab}
        />
      )}

      <div className="floating-stack">
        <div className="toasts">
          {toasts.map((t) => (
            <div key={t.id} className={`toast ${t.kind}`} onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}>
              {t.text}
            </div>
          ))}
        </div>
        <AttentionDock
          items={attentionItems}
          notifPermission={notifPermission}
          onEnableNotifications={() => {
            if (typeof Notification === 'undefined') return;
            Notification.requestPermission()
              .then((p) => setNotifPermission(p))
              .catch(() => undefined);
          }}
          onJump={(item) => jumpTo(item.projectId, item.sessionId)}
          onDecide={handleAttentionDecide}
          onRespond={handleAttentionRespond}
        />
      </div>
        {globalOpen && <GlobalConfig onClose={() => setGlobalOpen(false)} onToast={pushToast} />}
        {knowledgeOpen && <KnowledgePanel onClose={() => setKnowledgeOpen(false)} onToast={pushToast} />}
        {benchmarkOpen && (
          <BenchmarkPanel
            onClose={() => setBenchmarkOpen(false)}
            onOpenProject={openBenchmarkProject}
            onToast={pushToast}
          />
        )}
        {telemetryOpen && (
          <TelemetryPanel onClose={() => setTelemetryOpen(false)} onToast={pushToast} />
        )}
        <PathPickerModal
          isOpen={pathPicker.isOpen}
          title={pathPicker.title}
          initialPath={pathPicker.initialPath}
          extraShortcuts={extraPickerShortcuts}
          onSelect={pathPicker.onSelect}
          onClose={() => setPathPicker((prev) => ({ ...prev, isOpen: false }))}
        />
    </div>
  );
}

/* ------------------------------------------------------------------ inspector */

const TAB_CONFIG: Record<InspectorTab, { label: string; title: string }> = {
  overview: { label: 'Status', title: 'Project status, active agent & quick controls' },
  ops: { label: 'Ops', title: 'Agent tree, compute queue & pending reminders' },
  dag: { label: 'DAG', title: 'Mechanism DAG graph and verification status' },
  approvals: { label: 'Approvals', title: 'Pending sensitive tool approvals' },
  interactions: { label: 'Prompts', title: 'Agent questions and input requests' },
  artifacts: { label: 'Artifacts', title: 'Generated files, figures and outputs' },
  settings: { label: 'Settings', title: 'Agent LLM overrides, context memory & skills' },
  events: { label: 'Events', title: 'Live execution audit log & tool calls' },
};

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

function InteractionCard({
  item,
  projectId,
  onRefresh,
  onError,
  onToast,
}: {
  item: Record<string, unknown>;
  projectId: string | null;
  onRefresh: () => void;
  onError: (e: unknown) => void;
  onToast: (kind: ToastKind, text: string) => void;
}) {
  const [response, setResponse] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const interactionId = (item.interaction_id ?? item.id) as string | number | undefined;
  const agentId = String(item.agent_id ?? item.session_id ?? 'agent');
  const prompt = cleanPromptText(item.prompt ?? item.message);
  const createdAt = String(item.created_at ?? '');

  const handleSend = async () => {
    if (!projectId || !interactionId) return;
    const trimmed = response.trim();
    if (!trimmed || submitting) return;
    try {
      setSubmitting(true);
      await api.respondInteraction(projectId, interactionId, trimmed);
      onToast('ok', 'Response sent to agent');
      setResponse('');
      onRefresh();
    } catch (err) {
      onError(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="card interaction-card">
      <div className="card-header-row">
        <span className="badge role-badge">{agentId}</span>
        <span className="interaction-title">Needs your input</span>
        {createdAt && (
          <span className="card-meta" style={{ marginLeft: 'auto', marginBottom: 0 }}>
            {stamp(createdAt)}
          </span>
        )}
      </div>
      <div className="interaction-prompt">
        {prompt ? <Markdown text={prompt} /> : <span className="muted-note">(Empty prompt)</span>}
      </div>
      {projectId && interactionId && (
        <div className="interaction-input-box">
          <textarea
            className="input interaction-textarea"
            rows={2}
            placeholder="Type your response here (Enter to send, Shift+Enter for new line)…"
            value={response}
            disabled={submitting}
            onChange={(e) => setResponse(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void handleSend();
              }
            }}
          />
          <div className="interaction-actions">
            <button
              type="button"
              className="btn green sm"
              disabled={submitting || !response.trim()}
              onClick={handleSend}
            >
              {submitting ? 'Sending…' : 'Send response ↵'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Inspector({
  activeAgent,
  activeProject,
  agents,
  liveEvents,
  onPatchSettings,
  approvals,
  interactions,
  onRefreshApprovals,
  onRefreshInteractions,
  onError,
  onToast,
  width,
  onClose,
  currentAgentActivity,
  onToggleYolo,
  onChangeMode,
  onChangeWorkspace,
  onOpenPathPicker,
  tab: controlledTab,
  onSelectTab,
}: {
  activeAgent: Agent | null;
  activeProject: Project | null;
  agents: Agent[];
  liveEvents: EventEnvelope[];
  onPatchSettings: (patch: Record<string, unknown>) => void;
  approvals: Array<Record<string, unknown>>;
  interactions: Array<Record<string, unknown>>;
  onRefreshApprovals: () => void;
  onRefreshInteractions: () => void;
  onError: (e: unknown) => void;
  onToast: (kind: ToastKind, text: string) => void;
  width?: number;
  onClose?: () => void;
  currentAgentActivity?: { type: string; label: string };
  onToggleYolo?: (yolo: boolean) => void;
  onChangeMode?: (mode: string) => void;
  onChangeWorkspace?: (ws: string) => void;
  onOpenPathPicker?: (options: {
    title?: string;
    initialPath?: string;
    onSelect: (path: string) => void;
  }) => void;
  tab?: InspectorTab;
  onSelectTab?: (tab: InspectorTab) => void;
}) {
  const [internalTab, setInternalTab] = useState<InspectorTab>('overview');
  const tab = controlledTab ?? internalTab;
  const setTab = onSelectTab ?? setInternalTab;
  const [settingsSubTab, setSettingsSubTab] = useState<'model' | 'context' | 'skills'>('model');
  const [artifacts, setArtifacts] = useState<Array<Record<string, unknown>>>([]);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [goal, setGoal] = useState<GoalForm>(EMPTY_GOAL);
  const [goalLoaded, setGoalLoaded] = useState(false);
  const [stats, setStats] = useState<ContextStats | null>(null);
  const [skills, setSkills] = useState<Array<Record<string, unknown>>>([]);
  const [dagSummary, setDagSummary] = useState<{
    mode: string;
    nodeCount: number;
    edgeCount: number;
    draftAccepted: boolean;
    hasDraft: boolean;
  } | null>(null);

  const loadDagSummary = useCallback(async () => {
    if (!activeProject) {
      setDagSummary(null);
      return;
    }
    try {
      const [deliv, draft] = await Promise.allSettled([
        api.dagDelivery(activeProject.id),
        api.dagDraft(activeProject.id),
      ]);
      const graph = deliv.status === 'fulfilled' ? deliv.value.graph : null;
      const nodes = graph && Array.isArray((graph as any).nodes) ? (graph as any).nodes.length : 0;
      const edges = graph && Array.isArray((graph as any).edges) ? (graph as any).edges.length : 0;
      const isAccepted = draft.status === 'fulfilled' ? Boolean(draft.value?.mechanism_accepted) : false;
      const hasDraft = draft.status === 'fulfilled' ? Boolean(draft.value?.draft) : false;
      setDagSummary({
        mode: activeProject.settings.orchestration_mode ?? 'standard',
        nodeCount: nodes,
        edgeCount: edges,
        draftAccepted: isAccepted,
        hasDraft,
      });
    } catch {
      // ignore
    }
  }, [activeProject]);

  useEffect(() => {
    if (tab === 'overview') {
      void loadDagSummary();
      if (activeAgent) {
        api.getContextStats(activeAgent.id).then(setStats).catch(() => {});
      }
    }
  }, [tab, activeProject?.id, activeAgent?.id, loadDagSummary]);

  async function loadTab(next: InspectorTab) {
    setTab(next);
    try {
      if (next === 'overview') {
        void loadDagSummary();
        if (activeAgent) {
          api.getContextStats(activeAgent.id).then(setStats).catch(() => {});
        }
      } else if (next === 'artifacts' && activeProject) {
        setArtifacts(await api.artifacts(activeProject.id));
      } else if (next === 'settings') {
        if (activeAgent) {
          const [goalResp, statsResp] = await Promise.all([
            api.getGoal(activeAgent.id),
            api.getContextStats(activeAgent.id),
          ]);
          setGoal(goalResp.goal ?? EMPTY_GOAL);
          setGoalLoaded(true);
          setStats(statsResp);
        }
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

  return (
    <aside className="inspector" style={width ? { width } : undefined}>
      <div className="inspector-header">
        <div className="inspector-title-wrap">
          <span className="inspector-title">Inspector</span>
          {activeAgent ? (
            <span className="inspector-target-badge" title={`Inspecting agent ${activeAgent.display_name} (${activeAgent.role_id})`}>
              <span className={`state-dot ${activeAgent.state}`} />
              <span className="badge-name">{activeAgent.display_name}</span>
            </span>
          ) : activeProject ? (
            <span className="inspector-target-badge" title={`Inspecting project ${activeProject.name}`}>
              <span className="badge-name">{activeProject.name}</span>
            </span>
          ) : null}
        </div>
        {onClose && (
          <button
            type="button"
            className="inspector-close-btn"
            title="Close inspector"
            onClick={onClose}
          >
            ✕
          </button>
        )}
      </div>
      <div className="tabs">
        {(['overview', 'ops', 'dag', 'approvals', 'interactions', 'artifacts', 'settings', 'events'] as const).map((t) => {
          const cfg = TAB_CONFIG[t];
          const hasBadge = (t === 'approvals' && approvals.length > 0) || (t === 'interactions' && interactions.length > 0);
          const badgeCount = t === 'approvals' ? approvals.length : interactions.length;
          return (
            <button
              key={t}
              className={`tab ${tab === t ? 'active' : ''} ${hasBadge ? 'has-badge' : ''}`}
              title={cfg.title}
              onClick={() => loadTab(t)}
            >
              <span className="tab-label">{cfg.label}</span>
              {hasBadge && <span className="badge">{badgeCount}</span>}
            </button>
          );
        })}
      </div>
      <div className="inspector-body">
        {tab === 'overview' && (
          <div className="overview-dashboard">
            {/* 1. Active Agent Status */}
            <div className="card overview-card">
              <div className="card-header-row">
                <span className="card-section-label">Active Agent</span>
                {activeAgent && (
                  <span className={`state-badge ${activeAgent.state}`} style={{ marginLeft: 'auto' }}>
                    {activeAgent.state}
                  </span>
                )}
              </div>
              {activeAgent ? (
                <div className="overview-agent-body">
                  <div className="overview-agent-title-row">
                    <span className="overview-agent-name">{activeAgent.display_name}</span>
                    <span className="badge role-badge">{activeAgent.role_id}</span>
                    {activeAgent.settings.model && (
                      <span className="badge model-badge">{activeAgent.settings.model}</span>
                    )}
                  </div>
                  <div className="overview-activity-desc">
                    <span className="activity-label-bold">Status:</span>{' '}
                    <span className="activity-text">{currentAgentActivity?.label ?? activeAgent.state}</span>
                  </div>
                  {stats && (
                    <div className="overview-metrics-strip">
                      <div className="overview-metric">
                        <span className="metric-val">{stats.messages}</span>
                        <span className="metric-lbl">Messages</span>
                      </div>
                      <div className="overview-metric">
                        <span className="metric-val">{stats.tokens.toLocaleString()}</span>
                        <span className="metric-lbl">Est. Tokens</span>
                      </div>
                      {stats.last_prompt_tokens != null && (
                        <div className="overview-metric">
                          <span className="metric-val">{stats.last_prompt_tokens.toLocaleString()}</span>
                          <span className="metric-lbl">Last Prompt</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="empty-hint">No active agent selected</div>
              )}
            </div>

            {/* 2. Pending Actions (Approvals & Prompts) */}
            {(approvals.length > 0 || interactions.length > 0) && (
              <div className="overview-attention-section">
                <div className="overview-section-title">
                  <span>Action Required ({approvals.length + interactions.length})</span>
                </div>
                {approvals.map((approval) => {
                  const id = approval.id as number | string;
                  const tool = String(approval.tool_name ?? approval.tool ?? 'tool');
                  const details = String(approval.details ?? '');
                  const risk = String(approval.risk_summary ?? '');
                  return (
                    <div key={`overview-app-${id}`} className="card approval-card">
                      <div className="card-header-row">
                        <span className="badge tool-badge">{tool}</span>
                        <span className="card-meta" style={{ marginLeft: 'auto', marginBottom: 0 }}>#{String(id)}</span>
                      </div>
                      {risk && <div className="approval-risk-banner">[Risk] {risk}</div>}
                      {details && <div className="approval-details-text">{details}</div>}
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
                {interactions.map((item) => (
                  <InteractionCard
                    key={`overview-prompt-${String(item.interaction_id ?? item.id ?? '')}`}
                    item={item}
                    projectId={activeProject?.id ?? null}
                    onRefresh={onRefreshInteractions}
                    onError={onError}
                    onToast={onToast}
                  />
                ))}
              </div>
            )}

            {/* 3. Mechanism & DAG Summary */}
            {activeProject && (
              <div className="card overview-card">
                <div className="card-header-row">
                  <span className="card-section-label">Mechanism DAG</span>
                  <span className="badge mode-badge" style={{ marginLeft: 'auto' }}>
                    {activeProject.settings.orchestration_mode}
                  </span>
                </div>
                <div className="overview-dag-body">
                  {dagSummary ? (
                    <div className="overview-dag-stats">
                      <div className="overview-dag-status-pill">
                        <span className="dag-status-label">Status:</span>
                        <span className={`dag-status-val ${dagSummary.draftAccepted ? 'ok' : dagSummary.hasDraft ? 'pending' : 'neutral'}`}>
                          {dagSummary.draftAccepted ? 'Mechanism Accepted' : dagSummary.hasDraft ? 'Draft Proposed (Pending Review)' : 'No Draft Yet'}
                        </span>
                      </div>
                      <div className="overview-metrics-strip">
                        <div className="overview-metric">
                          <span className="metric-val">{dagSummary.nodeCount}</span>
                          <span className="metric-lbl">Species Nodes</span>
                        </div>
                        <div className="overview-metric">
                          <span className="metric-val">{dagSummary.edgeCount}</span>
                          <span className="metric-lbl">Elementary Steps</span>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="empty-hint">Loading DAG summary…</div>
                  )}
                  <div className="card-actions" style={{ marginTop: '0.6rem' }}>
                    <button
                      type="button"
                      className="btn outline sm"
                      onClick={() => loadTab('dag')}
                    >
                      Open Interactive DAG →
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* 4. Quick Project Controls */}
            {activeProject && (
              <div className="card overview-card">
                <div className="card-header-row">
                  <span className="card-section-label">Quick Controls</span>
                </div>
                <div className="overview-controls-grid">
                  <div className="overview-control-row">
                    <span className="control-name">Safety Policy</span>
                    <button
                      type="button"
                      className={`btn sm ${activeProject.settings.defaults?.yolo === true ? 'yellow' : 'outline'}`}
                      onClick={() => onToggleYolo?.(!(activeProject.settings.defaults?.yolo === true))}
                    >
                      {activeProject.settings.defaults?.yolo === true ? 'YOLO: ON (Auto-approve)' : 'Guarded (Require Approval)'}
                    </button>
                  </div>
                  <div className="overview-control-row">
                    <span className="control-name">Orchestration Mode</span>
                    <select
                      className="select sm"
                      value={activeProject.settings.orchestration_mode}
                      onChange={(e) => onChangeMode?.(e.target.value)}
                    >
                      <option value="standard">standard (Direct)</option>
                      <option value="dag_record">dag_record (Record)</option>
                      <option value="dag_guided">dag_guided (Supervised)</option>
                    </select>
                  </div>
                  <div className="overview-control-row">
                    <span className="control-name">Workspace</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flexWrap: 'wrap' }}>
                      <span className="mono-path" title={activeProject.workspace_dir ?? undefined}>
                        {activeProject.workspace_dir || '(none)'}
                      </span>
                      {onOpenPathPicker && (
                        <button
                          type="button"
                          className="btn ghost sm"
                          style={{ height: 22, padding: '0 6px', fontSize: 11 }}
                          title="Browse and set workspace directory"
                          onClick={() =>
                            onOpenPathPicker({
                              title: `Change Workspace for ${activeProject.name}`,
                              initialPath: activeProject.workspace_dir ?? undefined,
                              onSelect: (p) => onChangeWorkspace?.(p),
                            })
                          }
                        >
                          📁 Change
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {tab === 'dag' && (
          activeProject ? (
            <DagPanel project={activeProject} onError={onError} onToast={onToast} />
          ) : (
            <div className="inspector-empty-guide">
              <span className="badge sm">DAG</span>
              <div className="empty-title">No Project Selected</div>
              <div className="empty-desc">Select a project on the left to view and edit its mechanism DAG graph.</div>
            </div>
          )
        )}

        {tab === 'ops' && (
          activeProject ? (
            <OpsPanel project={activeProject} agents={agents} onError={onError} />
          ) : (
            <div className="inspector-empty-guide">
              <span className="badge sm">Ops</span>
              <div className="empty-title">No Project Selected</div>
              <div className="empty-desc">Select a project on the left to view its agent tree, compute queue and pending reminders.</div>
            </div>
          )
        )}

        {tab === 'approvals' && (
          <>
            {approvals.length === 0 && (
              <div className="inspector-empty-guide">
                <span className="badge sm">Approvals</span>
                <div className="empty-title">No Pending Approvals</div>
                <div className="empty-desc">
                  When an agent requests potentially destructive operations (e.g. bash commands or file writes), approval requests will appear here for review.
                </div>
              </div>
            )}
            {approvals.map((approval) => {
              const id = approval.id as number | string;
              const tool = String(approval.tool_name ?? approval.tool ?? 'tool');
              const agentName = String(approval.agent_name ?? '');
              const details = String(approval.details ?? '');
              const risk = String(approval.risk_summary ?? '');
              const diff = String(approval.candidate_diff ?? '');
              const createdAt = String(approval.created_at ?? '');
              return (
                <div key={String(id)} className="card approval-card">
                  <div className="card-header-row">
                    <span className="badge tool-badge">{tool}</span>
                    {agentName && <span className="badge role-badge">{agentName}</span>}
                    <span className="card-meta" style={{ marginLeft: 'auto', marginBottom: 0 }}>
                      #{String(id)}{createdAt ? ` · ${stamp(createdAt)}` : ''}
                    </span>
                  </div>
                  {risk && <div className="approval-risk-banner">[Risk] {risk}</div>}
                  {details && <div className="approval-details-text">{details}</div>}
                  {diff && (
                    <div className="approval-diff-wrap">
                      <div className="approval-diff-title">Proposed Changes</div>
                      <pre className="approval-diff-content">{diff}</pre>
                    </div>
                  )}
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
            {interactions.length === 0 && (
              <div className="inspector-empty-guide">
                <span className="badge sm">Prompts</span>
                <div className="empty-title">No Pending Prompts</div>
                <div className="empty-desc">
                  When an agent requires clarification, parameter inputs, or guidance, interactive prompt cards will appear here.
                </div>
              </div>
            )}
            {interactions.map((item) => (
              <InteractionCard
                key={String(item.interaction_id ?? item.id ?? '')}
                item={item}
                projectId={activeProject?.id ?? null}
                onRefresh={onRefreshInteractions}
                onError={onError}
                onToast={onToast}
              />
            ))}
          </>
        )}

        {tab === 'artifacts' && (
          <>
            {artifacts.length === 0 && (
              <div className="inspector-empty-guide">
                <span className="badge sm">Artifacts</span>
                <div className="empty-title">No Artifacts Yet</div>
                <div className="empty-desc">
                  Files, molecular structures, and figures generated in this project will appear here for preview and download.
                </div>
              </div>
            )}
            {artifacts.map((artifact) => (
              <div key={String(artifact.artifact_id)} className="card">
                <div className="card-title">{String(artifact.name)}</div>
                <div className="card-meta">
                  {String(artifact.mime_type ?? '')} · {String(artifact.size ?? '')} bytes
                </div>
                {activeProject && String(artifact.mime_type ?? '').startsWith('image/') && (
                  <a
                    className="artifact-thumb"
                    href={api.artifactDownloadUrl(activeProject.id, String(artifact.artifact_id))}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <img
                      src={api.artifactDownloadUrl(activeProject.id, String(artifact.artifact_id))}
                      alt={String(artifact.name)}
                      loading="lazy"
                    />
                  </a>
                )}
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

        {tab === 'settings' && (
          <div className="settings-panel">
            <div className="settings-subtabs">
              <button
                type="button"
                className={`tab sm ${settingsSubTab === 'model' ? 'active' : ''}`}
                onClick={() => setSettingsSubTab('model')}
              >
                Model & LLM
              </button>
              <button
                type="button"
                className={`tab sm ${settingsSubTab === 'context' ? 'active' : ''}`}
                onClick={() => setSettingsSubTab('context')}
              >
                Memory & Context
              </button>
              <button
                type="button"
                className={`tab sm ${settingsSubTab === 'skills' ? 'active' : ''}`}
                onClick={() => setSettingsSubTab('skills')}
              >
                Skills ({skills.length})
              </button>
            </div>

            {settingsSubTab === 'model' && (
              activeAgent ? (
                <>
                  <div className="settings-hierarchy-card">
                    <div className="hierarchy-title">Agent Level Override</div>
                    <div className="hierarchy-desc">
                      Settings applied to <b>{activeAgent.display_name}</b> alone. Values left empty inherit from the global config (<b>{activeAgent.role_id === 'coordinator' ? 'Coordinator' : 'Follower'}</b> slot).
                    </div>
                  </div>
                  <label className="field">
                    model
                    <input
                      className="input"
                      key={`model-${activeAgent.id}`}
                      list="agent-model-suggestions"
                      defaultValue={activeAgent.settings.model}
                      onBlur={(e) => e.target.value !== activeAgent.settings.model && onPatchSettings({ model: e.target.value })}
                    />
                    <datalist id="agent-model-suggestions">
                      <option value="anthropic/claude-sonnet-5" />
                      <option value="deepseek-v4-pro" />
                      <option value="openai/gpt-6-astra" />
                      <option value="google/gemini-3.8-flash" />
                      <option value="qwen/qwen3.8-max-0902" />
                      <option value="kimi-for-coding" />
                      <option value="kimi-k3" />
                      <option value="glm-5.3" />
                      <option value="minimax-m3" />
                      <option value="deepseek-ai/DeepSeek-V4-Pro" />
                    </datalist>
                    <span className="field-hint">
                      empty → global config ({activeAgent.role_id === 'coordinator' ? 'coordinator' : 'follower'} slot)
                    </span>
                  </label>
                  <label className="field">
                    base_url
                    <input
                      className="input"
                      key={`url-${activeAgent.id}`}
                      list="agent-url-suggestions"
                      defaultValue={activeAgent.settings.base_url}
                      onBlur={(e) => e.target.value !== activeAgent.settings.base_url && onPatchSettings({ base_url: e.target.value })}
                    />
                    <datalist id="agent-url-suggestions">
                      <option value="https://openrouter.ai/api/v1" label="OpenRouter" />
                      <option value="https://opencode.ai/zen/go/v1" label="OpenCode Go" />
                      <option value="https://api.kimi.com/coding/v1" label="Kimi Coding Plan (Kimi Code)" />
                      <option value="https://api.moonshot.cn/v1" label="Moonshot (Kimi 开放平台)" />
                      <option value="https://api.deepseek.com" label="DeepSeek" />
                      <option value="https://api.openai.com/v1" label="OpenAI" />
                      <option value="https://generativelanguage.googleapis.com/v1beta/openai/" label="Google Gemini" />
                      <option value="https://dashscope.aliyuncs.com/compatible-mode/v1" label="通义千问 (DashScope)" />
                      <option value="https://api.siliconflow.cn/v1" label="硅基流动 (SiliconFlow)" />
                      <option value="https://api.minimaxi.com/v1" label="MiniMax" />
                      <option value="http://localhost:11434/v1" label="Ollama (Local)" />
                    </datalist>
                    <span className="field-hint">
                      empty → global config ({activeAgent.role_id === 'coordinator' ? 'coordinator' : 'follower'} slot)
                    </span>
                  </label>
                  <div className="field">
                    api key
                    <div className="api-key-row">
                      <span className={`api-key-state ${activeAgent.settings.api_key_set ? 'ok' : ''}`}>
                        {activeAgent.settings.api_key_set ? 'overriding' : 'not set'}
                      </span>
                      {activeAgent.settings.api_key_set && (
                        <button className="btn ghost sm" onClick={() => onPatchSettings({ api_key: '' })}>
                          clear override
                        </button>
                      )}
                    </div>
                    <input
                      className="input"
                      type="password"
                      autoComplete="off"
                      key={`key-${activeAgent.id}`}
                      placeholder={
                        activeAgent.settings.api_key_set
                          ? 'type a new key to replace the override…'
                          : 'type to override the global key for this agent…'
                      }
                      onBlur={(e) => {
                        const value = e.target.value;
                        e.target.value = '';
                        if (value) onPatchSettings({ api_key: value });
                      }}
                    />
                    <span className="field-hint">
                      write-only: the stored key is never shown. Leave the box empty to keep the
                      current setting; use “clear override” to fall back to the global key.
                    </span>
                  </div>
                  <label className="field-row">
                    <input type="checkbox" checked={activeAgent.settings.yolo} onChange={(e) => onPatchSettings({ yolo: e.target.checked })} />
                    YOLO (this agent only; project-wide toggle is in the top bar)
                  </label>
                  <label className="field-row" title="Vision tools + image input for this agent">
                    <input
                      type="checkbox"
                      checked={activeAgent.settings.visual_mode !== false}
                      onChange={(e) => onPatchSettings({ visual_mode: e.target.checked })}
                    />
                    Visual (this agent only; project-wide toggle via /visual)
                  </label>
                  <label className="field-row" title="Enforce autonomous wake-up timers before stopping">
                    <input
                      type="checkbox"
                      checked={Boolean(activeAgent.settings.schedule_mode)}
                      onChange={(e) => onPatchSettings({ schedule_mode: e.target.checked })}
                    />
                    Schedule mode (autonomous self-wake guard)
                  </label>
                  <label className="field" title="Tool invocation protocol for this agent's NEXT run (frozen once a run starts)">
                    invocation protocol
                    <select
                      className="input"
                      value={activeAgent.settings.invocation_protocol ?? 'javascript'}
                      onChange={(e) => onPatchSettings({ invocation_protocol: e.target.value })}
                    >
                      <option value="traditional">traditional (direct tool calls)</option>
                      <option value="javascript">javascript (js_exec programs)</option>
                    </select>
                    <span className="field-hint">
                      applies to the next run; the active run keeps its frozen protocol
                      {activeAgent.current_run?.invocation_protocol &&
                      activeAgent.current_run.invocation_protocol !==
                        (activeAgent.settings.invocation_protocol ?? 'javascript')
                        ? ` — active run: ${activeAgent.current_run.invocation_protocol}`
                        : ''}
                    </span>
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
                    <span className="field-hint">sampling temperature, 0–2</span>
                  </label>
                  <label className="field" title="Reasoning effort passed as the OpenAI-compatible reasoning_effort parameter">
                    reasoning effort
                    <select
                      className="input"
                      value={activeAgent.settings.reasoning_effort ?? ''}
                      onChange={(e) => onPatchSettings({ reasoning_effort: e.target.value || null })}
                    >
                      <option value="">default (not sent)</option>
                      <option value="minimal">minimal</option>
                      <option value="low">low</option>
                      <option value="medium">medium</option>
                      <option value="high">high</option>
                    </select>
                    <span className="field-hint">
                      thinking strength; empty falls back to the global config slot
                    </span>
                  </label>
                  <div className="muted-note">Changes apply to this session on the next LLM request.</div>
                </>
              ) : (
                <div className="inspector-empty-guide">
                  <span className="badge sm">Settings</span>
                  <div className="empty-title">Select an Agent</div>
                  <div className="empty-desc">Pick an agent from the top bar to inspect or override its model and LLM credentials.</div>
                </div>
              )
            )}

            {settingsSubTab === 'context' && (
              activeAgent ? (
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
                        <div className="stats-metric-grid">
                          <div className="stat-metric-card">
                            <span className="stat-metric-val">{stats.messages}</span>
                            <span className="stat-metric-lbl">Messages</span>
                          </div>
                          <div className="stat-metric-card">
                            <span className="stat-metric-val">{stats.tokens.toLocaleString()}</span>
                            <span className="stat-metric-lbl">Est. Tokens</span>
                          </div>
                          <div className="stat-metric-card">
                            <span className="stat-metric-val">{stats.last_prompt_tokens != null ? stats.last_prompt_tokens.toLocaleString() : '—'}</span>
                            <span className="stat-metric-lbl">Last Prompt</span>
                          </div>
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
                    <div className="empty-hint">
                      Replaces the whole conversation history with one structured
                      summary (applies on the next turn).
                    </div>
                    <button
                      className="btn outline sm"
                      onClick={async () => {
                        try {
                          await api.compactAgent(activeAgent.id);
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
                <div className="inspector-empty-guide">
                  <span className="badge sm">Context</span>
                  <div className="empty-title">Select an Agent</div>
                  <div className="empty-desc">Pick an agent from the top bar to inspect its goal anchor, token stats, and context memory.</div>
                </div>
              )
            )}

            {settingsSubTab === 'skills' && (
              <>
                {skills.length === 0 && (
                  <div className="inspector-empty-guide">
                    <span className="badge sm">Skills</span>
                    <div className="empty-title">No Skills Found</div>
                    <div className="empty-desc">No specialized skills are registered for the current agent or environment.</div>
                  </div>
                )}
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
          </div>
        )}

        {tab === 'events' && (
          <AuditLog
            agentId={activeAgent?.id ?? null}
            projectId={activeProject?.id ?? null}
            liveEvents={liveEvents}
            onError={onError}
          />
        )}
      </div>
    </aside>
  );
}
