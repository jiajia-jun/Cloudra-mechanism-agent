import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { api, EVENTS_WINDOW, HISTORY_PAGE_SIZE, streamProject } from './api';
import Markdown from './Markdown';
import DagPanel from './DagPanel';
import OpsPanel from './OpsPanel';
import type { Agent, CompletionSummary, ComputeJob, EventEnvelope, Project } from './types';
import GlobalConfig from './GlobalConfig';
import ProjectSettingsModal from './ProjectSettingsModal';
import KnowledgePanel from './KnowledgePanel';
import BenchmarkPanel from './BenchmarkPanel';
import TelemetryPanel from './TelemetryPanel';
import HubPanel from './HubPanel';
import { ConsoleIndexPage, type ConsoleTab } from './ConsoleIndexPage';
import { ArtifactsPanel } from './ArtifactsPanel';
import AuditLog from './AuditLog';
import AttentionDock, { type NotifPermission } from './AttentionDock';
import InteractionPrompt from './InteractionPrompt';
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
import { boundEventPage, boundStreamView, LiveEventBuffer, mergeAndTrimLiveEvents } from './eventWindow';
import { resolveComposerSendTarget } from './composerSend';
import { planSseReconnect } from './sseReconnect';
import {
  archiveProjectConfirm,
  cancelAllComputeConfirm,
  formatCancelAllToast,
  hardDeleteProjectConfirm,
} from './destructiveActions';
import { ToolRow } from './ToolRow';
import { ProgramCard } from './ProgramCard';
import { PathPickerModal } from './PathPickerModal';
import { completionChipFor } from './completion';
import { useI18n } from './i18n';

/* ------------------------------------------------------------------ helpers */

type ToastKind = 'error' | 'ok' | 'info';
interface Toast { id: number; kind: ToastKind; text: string }

let toastSeq = 0;

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
    command: '/protocol',
    args: '[traditional|javascript]',
    desc: 'Set project-wide tool invocation protocol (next run)',
    insertText: '/protocol ',
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

/** 笔记行图标：info 提示 / warn 警告 / error 失败。 */
function noteIcon(level: 'warn' | 'info' | 'error'): string {
  if (level === 'info') return 'ℹ';
  return level === 'error' ? '✕' : '!';
}

/** 完成依据标签：只渲染服务端给出的验证等级，不本地推导、不猜未知值。 */
function CompletionChip({ completion }: { completion?: CompletionSummary | null }) {
  const chip = completionChipFor(completion);
  if (!chip || chip.tone === 'neutral') return null;
  return (
    <span className={`completion-badge ${chip.tone}`} title={chip.detail}>
      {chip.label}
    </span>
  );
}

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
  const { lang, setLang, t } = useI18n();
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);
  const [projectStream, setProjectStream] = useState<{ projectId: string; cursor: number } | null>(null);
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  // One historical page, isolated from the live tail while browsing.
  const [olderEvents, setOlderEvents] = useState<EventEnvelope[]>([]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasOlder, setHasOlder] = useState(true);
  const [streamView, setStreamView] = useState<StreamView & { omitted?: boolean }>({ streamText: '', frozen: [] });
  const [sidebarJobs, setSidebarJobs] = useState<ComputeJob[] | null>(null);
  const [computeRefreshVersion, setComputeRefreshVersion] = useState(0);
  const [cancellingCompute, setCancellingCompute] = useState(false);
  const cancellingComputeRef = useRef(false);
  const sidebarJobsRequestRef = useRef(0);
  const [viewMode, setViewMode] = useState<'dialogue' | 'console'>('dialogue');
  const [consoleTab, setConsoleTab] = useState<ConsoleTab>('overview');
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(() => {
    const saved = localStorage.getItem('cloudra:sidebar-open') ?? localStorage.getItem('cloudra:right-sidebar-open');
    return saved !== null ? saved === 'true' : true;
  });

  useEffect(() => {
    localStorage.setItem('cloudra:sidebar-open', String(sidebarOpen));
  }, [sidebarOpen]);

  const [pendingMessages, setPendingMessages] = useState<MessageItem[]>([]);
  const pendingMessageSeqRef = useRef(0);
  const [roles, setRoles] = useState<Array<{ role_id: string; display_name: string }>>([]);
  const [draft, setDraft] = useState('');
  const [slashSelected, setSlashSelected] = useState(0);
  const [slashDismissed, setSlashDismissed] = useState(false);
  const composerTextareaRef = useRef<HTMLTextAreaElement>(null);
  const [newProject, setNewProject] = useState('');
  const [sending, setSending] = useState(false);
  const [connState, setConnState] = useState<'connecting' | 'live' | 'offline'>('connecting');
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [interactionCollapsed, setInteractionCollapsed] = useState(false);
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
  const [hubOpen, setHubOpen] = useState(false);
  const [projectSettingsOpen, setProjectSettingsOpen] = useState(false);
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

  const approvals = attention.get(activeProjectId ?? '')?.approvals ?? [];
  const interactions = attention.get(activeProjectId ?? '')?.interactions ?? [];
  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;
  const activeAgent = agents.find((a) => a.id === activeAgentId) ?? null;
  // Visual mode gates the composer attach button; defaults to on.
  const visualOn = activeProject
    ? (activeAgent?.settings.visual_mode ?? activeProject.settings.defaults?.visual_mode ?? true) !== false
    : false;

  const hasActiveAgentDecision = Boolean(
    interactions.find(
      (ixn) =>
        (activeAgent?.id && String(ixn.session_id) === String(activeAgent.id)) ||
        (activeAgent?.role_id && String(ixn.agent_id) === String(activeAgent.role_id))
    ) ||
    approvals.find(
      (appr) =>
        (activeAgent?.id && String(appr.session_id) === String(activeAgent.id)) ||
        (activeAgent?.role_id && (String(appr.agent_name) === String(activeAgent.role_id) || String(appr.agent_name) === String(activeAgent.display_name)))
    ) ||
    ((interactions.length > 0 || approvals.length > 0) && !activeAgent)
  );

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
      const key = (p.workspace_dir ?? '').trim();
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(p);
    }
    return [...groups.entries()].sort(([a], [b]) =>
      a === '' ? 1 : b === '' ? -1 : a.localeCompare(b),
    );
  }, [projects]);

  const archivedProjects = useMemo(() => projects.filter((p) => p.archived), [projects]);

  const [collapsedWorkspaces, setCollapsedWorkspaces] = useState<Set<string>>(new Set());
  const toggleWorkspace = (ws: string) => {
    setCollapsedWorkspaces((prev) => {
      const next = new Set(prev);
      if (next.has(ws)) next.delete(ws);
      else next.add(ws);
      return next;
    });
  };

  const [inlineCreate, setInlineCreate] = useState<{ ws: string; name: string } | null>(null);
  const [newProjectWs, setNewProjectWs] = useState('');


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
  const activeProjectIdRef = useRef(activeProjectId);
  activeProjectIdRef.current = activeProjectId;
  const decisionSendingRef = useRef(false);
  const pendingRevisionRef = useRef(0);
  const activeAgentIdRef = useRef(activeAgentId);
  const agentSelectionVersionRef = useRef(0);
  const maxSeqRef = useRef(0);

  const projectsRef = useRef(projects);
  projectsRef.current = projects;
  const pendingLoadsRef = useRef(new Map<string, Promise<ProjectPending | undefined>>());
  const pendingDirtyRef = useRef(new Set<string>());

  const refreshProjectPending = useCallback((projectId: string, changed = false): Promise<ProjectPending | undefined> => {
    if (!projectsRef.current.some((project) => project.id === projectId && !project.archived)) return Promise.resolve(undefined);
    const existing = pendingLoadsRef.current.get(projectId);
    if (existing) {
      if (changed) pendingDirtyRef.current.add(projectId);
      return existing;
    }
    const promise: Promise<ProjectPending | undefined> = Promise.resolve().then(async () => {
      let latest: ProjectPending | undefined;
      do {
        pendingDirtyRef.current.delete(projectId);
        try {
          const [approvals, interactions] = await Promise.all([
            api.approvals(projectId), api.interactions(projectId),
          ]);
          const project = projectsRef.current.find((item) => item.id === projectId && !item.archived);
          if (!project || pendingLoadsRef.current.get(projectId) !== promise) return;
          // A committed change arrived while HTTP was running. Do not publish
          // its older snapshot; callers share the follow-up request as well.
          if (pendingDirtyRef.current.has(projectId)) continue;
          const pending = { name: project.name, approvals, interactions };
          latest = pending;
          setAttention((prev) => new Map(prev).set(projectId, pending));
        } catch {
          // Keep the last visible pending state; the next fallback retries.
        }
      } while (pendingDirtyRef.current.has(projectId) && projectsRef.current.some((item) => item.id === projectId && !item.archived));
      return latest;
    }).finally(() => {
      if (pendingLoadsRef.current.get(projectId) === promise) {
        pendingLoadsRef.current.delete(projectId);
        pendingDirtyRef.current.delete(projectId);
      }
    });
    pendingLoadsRef.current.set(projectId, promise);
    return promise;
  }, []);

  const removePendingItem = useCallback((projectId: string, kind: 'approvals' | 'interactions', id: string | number) => {
    if (pendingLoadsRef.current.has(projectId)) pendingDirtyRef.current.add(projectId);
    setAttention((prev) => {
      const pending = prev.get(projectId);
      if (!pending) return prev;
      const rows = pending[kind].filter((item) => String(item.interaction_id ?? item.approval_id ?? item.id) !== String(id));
      return new Map(prev).set(projectId, { ...pending, [kind]: rows });
    });
  }, []);

  useEffect(() => {
    const ids = new Set(projects.filter((project) => !project.archived).map((project) => project.id));
    setAttention((prev) => {
      if ([...prev.keys()].every((id) => ids.has(id))) return prev;
      return new Map([...prev].filter(([id]) => ids.has(id)));
    });
    for (const id of pendingLoadsRef.current.keys()) {
      if (!ids.has(id)) {
        pendingLoadsRef.current.delete(id);
        pendingDirtyRef.current.delete(id);
      }
    }
  }, [projects]);

  // Shortcut Cmd+B / Ctrl+B toggles project sidebar
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

  // SSE events arrive in bursts (full history replay on connect, and one
  // llm.*/tool.* event per token/step during a run).  Feeding each event
  // straight into `setEvents` re-runs `buildTimeline` (a full sort +
  // stringification of the window) per event — thousands of times on open and
  // on every tool burst.  We coalesce into one state update per animation
  // frame so the transcript rebuilds once, not per event.
  const eventBufferRef = useRef(new LiveEventBuffer(EVENTS_WINDOW));
  const flushRafRef = useRef<number | null>(null);
  const flushBufferedEvents = useCallback(() => {
    flushRafRef.current = null;
    const batch = eventBufferRef.current.drain();
    if (batch.length === 0) return;
    setEvents((prev) => mergeAndTrimLiveEvents(prev, batch, EVENTS_WINDOW).live);
  }, []);
  const bufferEvent = useCallback(
    (event: EventEnvelope) => {
      eventBufferRef.current.add(event);
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
  }, []);

  const loadSidebarOps = useCallback(async () => {
    const requestVersion = ++sidebarJobsRequestRef.current;
    if (!activeProjectId) {
      setSidebarJobs(null);
      return;
    }
    try {
      const jobs = await api.listComputeJobs(activeProjectId, true);
      if (requestVersion === sidebarJobsRequestRef.current && activeProjectIdRef.current === activeProjectId) {
        setSidebarJobs(jobs);
      }
    } catch {
      // ignore transient poll error
    }
  }, [activeProjectId]);

  useEffect(() => {
    if (!activeProjectId) return;
    void loadSidebarOps();
    const timer = setInterval(() => {
      void loadSidebarOps();
    }, 4000);
    return () => clearInterval(timer);
  }, [activeProjectId, loadSidebarOps]);

  const selectAgent = useCallback(
    async (agentId: string) => {
      const version = ++agentSelectionVersionRef.current;
      activeAgentIdRef.current = agentId;
      setActiveAgentId(agentId);
      setEvents([]);
      setPendingMessages([]);
      setStreamView({ streamText: '', frozen: [] });
      setOlderEvents([]);
      setLoadingOlder(false);
      setHasOlder(true);
      maxSeqRef.current = 0;
      // Drop any buffered events from the previous agent: they must not leak
      // into the freshly loaded transcript.
      eventBufferRef.current.clear();
      if (flushRafRef.current != null) {
        cancelAnimationFrame(flushRafRef.current);
        flushRafRef.current = null;
      }
      try {
        const detailsThrough = maxSeqRef.current;
        const [agent, eventList] = await Promise.all([api.getAgent(agentId), api.events(agentId)]);
        if (version !== agentSelectionVersionRef.current) return;
        const completionCurrent = maxSeqRef.current === detailsThrough;
        setAgents((prev) => prev.some((current) => current.id === agentId) ? prev.map((current) => current.id === agentId ? {
          ...agent,
          state: current.state,
          current_run: current.current_run,
          current_task: current.current_task,
          completion: current.current_run ? null : completionCurrent ? agent.completion : current.completion,
        } : current) : [...prev, agent]);
        const page = boundEventPage(eventList, EVENTS_WINDOW);
        setEvents((prev) => mergeAndTrimLiveEvents(prev, page, EVENTS_WINDOW).live);
        setHasOlder(eventList.length >= EVENTS_WINDOW || page.length < eventList.length);
        // Anchors for future thinking segments must account for the fetched
        // history — otherwise the first chunks land at seq 0.5, above the
        // triggering user message, and no SSE echo ever re-bases them.
        maxSeqRef.current = eventList.reduce((m, e) => Math.max(m, e.session_seq ?? 0), maxSeqRef.current);
      } catch (e) {
        if (version === agentSelectionVersionRef.current) reportError(e);
      }
    },
    [reportError],
  );

  useEffect(() => {
    let cancelled = false;
    ++agentSelectionVersionRef.current;
    ++pendingRevisionRef.current;
    setAgents([]);
    setProjectStream(null);
    activeAgentIdRef.current = null;
    setActiveAgentId(null);
    setEvents([]);
    setOlderEvents([]);
    setLoadingOlder(false);
    setHasOlder(true);
    setStreamView({ streamText: '', frozen: [] });
    maxSeqRef.current = 0;
    setPendingMessages([]);
    setPendingImages([]);
    setSidebarJobs(null);
    if (!activeProjectId) return;
    api
      .projectView(activeProjectId)
      .then((view) => {
        if (cancelled) return;
        const agents = dedupeAgents(view.agents);
        setAgents(agents);
        setProjectStream({ projectId: activeProjectId, cursor: view.cursor });
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
      .catch((error) => { if (!cancelled) reportError(error); });
    return () => {
      cancelled = true;
      ++agentSelectionVersionRef.current;
      eventBufferRef.current.clear();
      if (flushRafRef.current != null) {
        cancelAnimationFrame(flushRafRef.current);
        flushRafRef.current = null;
      }
    };
  }, [activeProjectId, selectAgent, reportError]);

  /* ------------------------------------------------------------ SSE stream */

  useEffect(() => {
    if (!activeProjectId || projectStream?.projectId !== activeProjectId) return;
    setConnState('connecting');
    let cursor = projectStream.cursor;
    let replaying = true;
    let synced = false;
    let source: ReturnType<typeof streamProject> | null = null;
    let closed = false;
    let reconnectTimer: number | null = null;

    const connect = () => {
      if (closed) return;
      replaying = true;
      source = streamProject(activeProjectId, cursor, {
        onOpen: () => setConnState('live'),
        onError: () => {
          const plan = planSseReconnect({ cursor, stillWanted: !closed });
          if (plan.action === 'ignore') return;
          setConnState(plan.nextState);
          if (source) {
            source.close();
            source = null;
          }
          if (reconnectTimer === null) {
            reconnectTimer = window.setTimeout(() => {
              reconnectTimer = null;
              connect();
            }, plan.delayMs);
          }
        },
        onEvent: (event) => {
          if (closed) return;
          if (event.type === 'project.synced') {
            cursor = Math.max(cursor, Number(event.data.replayed_through ?? 0));
            replaying = false;
            if (synced) {
              const agentId = activeAgentIdRef.current;
              const version = agentSelectionVersionRef.current;
              if (agentId) void api.events(agentId).then((page) => {
                if (closed || version !== agentSelectionVersionRef.current) return;
                setEvents((prev) => mergeAndTrimLiveEvents(prev, page, EVENTS_WINDOW).live);
                maxSeqRef.current = page.reduce((max, item) => Math.max(max, item.session_seq ?? 0), maxSeqRef.current);
              }).catch(() => undefined);
            }
            synced = true;
            return;
          }
          if (event.type === 'project.deleted') {
            const pid = event.project_id;
            setProjects((prev) => prev.filter((p) => p.id !== pid));
            if (activeProjectId === pid) {
              activeAgentIdRef.current = null;
              setActiveAgentId(null);
              setAgents([]);
              setActiveProjectId(null);
            }
            return;
          }
          cursor = Math.max(cursor, event.seq);
        const sessionId = event.session_id;
        // Agent list / chip state updates, regardless of selection.
        if (event.type === 'agent.spawned' && activeProjectId) {
          const spawned = { ...event.data, completion: null } as unknown as Agent;
          setAgents((prev) => prev.some((agent) => agent.id === spawned.id) ? prev : [...prev, spawned]);
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
        if (event.type === 'agent.task_updated' && sessionId) {
          const task = event.data?.current_task != null ? String(event.data.current_task) : null;
          setAgents((prev) =>
            dedupeAgents(prev.map((a) => (a.id === sessionId ? { ...a, current_task: task } : a))),
          );
        }
        if (event.type === 'run.started' && sessionId) {
          const runId = String(event.data.run_id ?? event.run_id ?? '');
          const protocol = event.data.invocation_protocol;
          setAgents((prev) =>
            dedupeAgents(
              prev.map((a) =>
                a.id === sessionId
                  ? {
                      ...a,
                      completion: null,
                      current_run: {
                        run_id: runId,
                        started_at: String(event.data.started_at ?? event.created_at ?? ''),
                        invocation_protocol:
                          typeof protocol === 'string'
                            ? protocol
                            : a.current_run?.invocation_protocol,
                      },
                    }
                  : a,
              ),
            ),
          );
        }
        if ((event.type === 'run.finished' || event.type === 'agent.cancelled') && sessionId) {
          setAgents((prev) =>
            dedupeAgents(prev.map((a) => (a.id === sessionId ? { ...a, current_run: null } : a))),
          );
          // 完成依据（已验证完成 / 部分交付 / 未独立验证）由服务端从收尾事件
          // 投影，本地无从重建：收尾后拉一次当前 agent 把它补齐（只补正在看的
          // 那个，其他 agent 在切换时补齐；不能覆盖 SSE 已推进的状态）。
          if (sessionId === activeAgentIdRef.current) {
            const version = agentSelectionVersionRef.current;
            const through = event.session_seq ?? maxSeqRef.current;
            void api.getAgent(sessionId).then((fresh) => {
              if (closed || version !== agentSelectionVersionRef.current || maxSeqRef.current !== through) return;
              setAgents((prev) => prev.map((agent) => agent.id === sessionId
                ? { ...agent, completion: agent.current_run ? null : fresh.completion } : agent));
            }).catch(() => undefined);
          }
        }
        if (event.type === 'approval.requested' || event.type === 'tool.approval_requested') {
          if (!replaying) {
            pushToast('info', `Approval requested: ${short(event.data.tool_name ?? event.data.message ?? '', 60)}`);
          }
          if (activeProjectId) void refreshProjectPending(activeProjectId, true);
        }
        if (event.type === 'approval.decided' && activeProjectId) {
          void refreshProjectPending(activeProjectId, true);
        }
        // Compact feedback: the button only queues the request — the actual
        // run happens at the next turn boundary and can take minutes on
        // thinking models. Surface started/finished so the button is not a
        // black box (refusals include the reason + error label).
        if (
          (event.type === 'compaction.started' || event.type === 'compaction.finished') &&
          sessionId &&
          sessionId === activeAgentIdRef.current &&
          !replaying
        ) {
          if (event.type === 'compaction.started') {
            pushToast('info', `Compacting context… (${event.data?.history_messages ?? '?'} messages)`);
          } else if (event.data?.compacted) {
            pushToast('ok', `Compacted: ${event.data?.before_messages ?? '?'} → ${event.data?.after_messages ?? '?'} messages`);
          } else {
            const reason = String(event.data?.reason ?? 'refused');
            const err = String(event.data?.error ?? '').slice(0, 80);
            pushToast('error', `Compaction refused: ${reason}${err ? ` (${err})` : ''}`);
          }
        }
        if (
          (event.type === 'interaction.requested' ||
            event.type === 'interaction.responded' ||
            event.type === 'interaction.expired') &&
          activeProjectId
        ) {
          void refreshProjectPending(activeProjectId, true);
        }
        // Timeline events for the visible agent.
        if (sessionId && sessionId === activeAgentIdRef.current) {
          // Token-level streaming: llm.chunk never enters the event list.
          // Reasoning and content deltas feed streamView via applyStreamEvent.
          if (event.type === 'llm.chunk') {
            setStreamView((prev) => boundStreamView(
              applyStreamEvent(prev, event, maxSeqRef.current), Boolean(prev.omitted),
            ));
            return;
          }
          maxSeqRef.current = Math.max(maxSeqRef.current, event.session_seq ?? 0);
          setStreamView((prev) => boundStreamView(
            applyStreamEvent(prev, event, maxSeqRef.current), Boolean(prev.omitted),
          ));
          bufferEvent(event);
          if (event.type === 'llm.failed' && !replaying) {
            pushToast('error', `LLM failed: ${short(event.data.error ?? event.data.message ?? '', 100)}`);
          }
        }
      },
    });
  };

  connect();
  return () => {
    closed = true;
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
    }
    source?.close();
  };
}, [activeProjectId, projectStream, pushToast, refreshProjectPending]);

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

  // One fallback supplies both the active Inspector and cross-project attention.
  // Three project workers bound fan-out; slow rounds never overlap themselves.
  useEffect(() => {
    const targets = projects.filter((p) => !p.archived);
    if (targets.length === 0) return;
    let cancelled = false;
    let running = false;
    const poll = async () => {
      if (running) return;
      running = true;
      try {
        const next = new Map<string, ProjectPending>();
        let index = 0;
        const worker = async () => {
          while (!cancelled && index < targets.length) {
            const project = targets[index++];
            const pending = await refreshProjectPending(project.id);
            if (pending) next.set(project.id, pending);
          }
        };
        await Promise.all(Array.from({ length: Math.min(3, targets.length) }, worker));
        if (cancelled) return;
        const items = collectPending(next);
        if (!attentionBaselineRef.current) {
          attentionBaselineRef.current = true;
          attentionSeenRef.current = new Set(items.map((item) => item.key));
          return;
        }
        const fresh = diffNewItems(items, attentionSeenRef.current);
        attentionSeenRef.current = new Set(items.map((item) => item.key));
        for (const item of fresh) notifyAttention(item);
      } finally {
        running = false;
      }
    };
    void poll();
    const timer = window.setInterval(poll, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [projects, notifyAttention, refreshProjectPending]);

  const handleAttentionDecide = useCallback(
    async (item: PendingAttention, decision: 'approve' | 'deny') => {
      try {
        await api.decideApproval(item.projectId, item.id, decision, decision === 'deny' ? 'denied by user' : '');
        removePendingItem(item.projectId, 'approvals', item.id);
        pushToast('ok', `${decision === 'approve' ? 'Approved' : 'Denied'} · ${item.projectName}`);
      } catch (e) {
        reportError(e);
      } finally {
        await refreshProjectPending(item.projectId, true);
      }
    },
    [pushToast, reportError, refreshProjectPending, removePendingItem],
  );

  const handleAttentionRespond = useCallback(
    async (item: PendingAttention, response: string) => {
      try {
        await api.respondInteraction(item.projectId, item.id, response);
        removePendingItem(item.projectId, 'interactions', item.id);
        pushToast('ok', `Response sent · ${item.projectName}`);
      } catch (e) {
        reportError(e);
      } finally {
        await refreshProjectPending(item.projectId, true);
      }
    },
    [pushToast, reportError, refreshProjectPending, removePendingItem],
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
    if (!inlineCreate || !inlineCreate.name.trim()) return;
    try {
      await createProject(inlineCreate.name.trim(), inlineCreate.ws.trim() || undefined);
      setInlineCreate(null);
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
    if (!window.confirm(archiveProjectConfirm(p.name))) {
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



  const handleRespondInteraction = async (interactionId: string | number, answer: string): Promise<boolean> => {
    if (!activeProject || decisionSendingRef.current) return false;
    const projectId = activeProject.id;
    decisionSendingRef.current = true;
    setSending(true);
    try {
      await api.respondInteraction(projectId, interactionId, answer);
    } catch (err: unknown) {
      reportError(err);
      return false;
    } finally {
      decisionSendingRef.current = false;
      setSending(false);
    }
    const revision = ++pendingRevisionRef.current;
    pushToast('ok', t.interactionSentToast || 'Response sent to agent');
    removePendingItem(projectId, 'interactions', interactionId);
    void refreshProjectPending(projectId, true);
    const selection = agentSelectionVersionRef.current;
    const through = maxSeqRef.current;
    // The mutation succeeded. A failed refresh must not suggest resubmission.
    void api.listAgents(projectId).then((sessions) => {
      if (activeProjectIdRef.current !== projectId || pendingRevisionRef.current !== revision
          || agentSelectionVersionRef.current !== selection || maxSeqRef.current !== through) return;
      setAgents(dedupeAgents(sessions));
    }).catch(() => undefined);
    return true;
  };

  const handleDecideApproval = async (
    approvalId: string | number,
    decision: 'approve' | 'deny',
    reason = ''
  ): Promise<boolean> => {
    if (!activeProject || decisionSendingRef.current) return false;
    const projectId = activeProject.id;
    decisionSendingRef.current = true;
    setSending(true);
    try {
      await api.decideApproval(projectId, approvalId, decision, reason || (decision === 'deny' ? 'denied by user' : ''));
    } catch (err: unknown) {
      reportError(err);
      return false;
    } finally {
      decisionSendingRef.current = false;
      setSending(false);
    }
    const revision = ++pendingRevisionRef.current;
    pushToast('ok', decision === 'approve' ? t.approvalApprovedToast : t.approvalDeniedToast);
    removePendingItem(projectId, 'approvals', approvalId);
    void refreshProjectPending(projectId, true);
    const selection = agentSelectionVersionRef.current;
    const through = maxSeqRef.current;
    void api.listAgents(projectId).then((sessions) => {
      if (activeProjectIdRef.current !== projectId || pendingRevisionRef.current !== revision
          || agentSelectionVersionRef.current !== selection || maxSeqRef.current !== through) return;
      setAgents(dedupeAgents(sessions));
    }).catch(() => undefined);
    return true;
  };

  async function deleteProject(p: Project) {
    if (!window.confirm(hardDeleteProjectConfirm(p.name))) {
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
    if (cancellingComputeRef.current || !window.confirm(cancelAllComputeConfirm(lang))) {
      return;
    }
    cancellingComputeRef.current = true;
    setCancellingCompute(true);
    try {
      const counts = await api.cancelAllComputeJobs();
      pushToast('ok', formatCancelAllToast(counts, lang));
    } catch (e) {
      reportError(e);
    } finally {
      setComputeRefreshVersion((version) => version + 1);
      await loadSidebarOps();
      cancellingComputeRef.current = false;
      setCancellingCompute(false);
    }
  }

  async function sendMessage() {
    const target = resolveComposerSendTarget({
      draft,
      sending,
      hasProject: Boolean(activeProject),
      hasAgent: Boolean(activeAgent),
      interactions,
    });
    if (target.kind === 'noop' || !activeProject) return;
    const content = draft.trim();
    const pendingId = `pending-${++pendingMessageSeqRef.current}`;
    const images = pendingImages.map((p) => p.path);
    const imageArtifactIds = pendingImages.map((p) => p.artifactId);
    setSending(true);
    try {
      if (target.kind === 'slash') {
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
        if (lower.startsWith('/protocol')) {
          setDraft('');
          const arg = content.slice(9).trim().toLowerCase();
          const current =
            activeAgent?.settings.invocation_protocol ??
            activeProject?.settings.defaults?.invocation_protocol ??
            'javascript';
          let next: 'traditional' | 'javascript';
          if (arg === 'traditional' || arg === 'trad') {
            next = 'traditional';
          } else if (arg === 'javascript' || arg === 'js') {
            next = 'javascript';
          } else if (!arg) {
            next = current === 'traditional' ? 'javascript' : 'traditional';
          } else {
            pushToast('info', 'Usage: /protocol [traditional|javascript]');
            return;
          }
          await changeProjectInvocationProtocol(next);
          return;
        }
        if (lower.startsWith('/compact')) {
          setDraft('');
          if (activeAgent) {
            await api.compactAgent(activeAgent.id);
            const st = String(activeAgent.state ?? '');
            if (st === 'running' || st === 'queued' || st === 'waiting_approval' || st === 'waiting_input') {
              pushToast('ok', 'Compaction queued — the running agent executes it at its next turn boundary');
            } else {
              pushToast('error', `Agent is ${st || 'not running'} — compaction queued but it will NOT run until the agent runs again`);
            }
          }
          return;
        }
        if (lower === '/help') {
          setDraft('');
          pushToast(
            'info',
            'Commands: /schedule [on|off], /goal <text>, /yolo [on|off], /visual [on|off], /protocol [traditional|javascript], /compact',
          );
          return;
        }
        // Unknown slash: fall through to message/spawn so the agent can see it.
      }
      if (target.kind === 'respond') {
        if (await handleRespondInteraction(target.interactionId, content)) {
          if (activeProjectIdRef.current === activeProject.id) setDraft((current) => current === draft ? '' : current);
        }
        return;
      }
      setPendingImages([]);
      if (target.kind === 'spawn_coordinator') {
        // With images attached the spawn `query` cannot carry them, so spawn
        // idle and deliver text + images as the first message instead.
        const resp = await api.spawnAgent(activeProject.id, {
          role_id: 'coordinator',
          query: images.length > 0 ? undefined : content,
          language: lang,
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
          await api.sendMessage(resp.data.id, content, images, imageArtifactIds, lang);
        }
        await selectAgent(resp.data.id);
      } else {
        // The command receipt confirms this exact local send; SSE may arrive independently.
        setPendingMessages((prev) => [
          ...prev,
          {
            kind: 'message',
            id: pendingId,
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
        const agentId = activeAgent!.id;
        const version = agentSelectionVersionRef.current;
        const receipt = await api.sendMessage(agentId, content, images, imageArtifactIds, lang);
        setPendingMessages((prev) => prev.filter((message) => message.id !== pendingId));
        void api.eventDetail(agentId, receipt.event_id).then((message) => {
          if (version !== agentSelectionVersionRef.current) return;
          setEvents((prev) => mergeAndTrimLiveEvents(prev, [message], EVENTS_WINDOW).live);
          maxSeqRef.current = Math.max(maxSeqRef.current, message.session_seq ?? 0);
        }).catch(reportError);
      }
    } catch (e) {
      setPendingMessages((prev) => prev.filter((message) => message.id !== pendingId));
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

  async function handleSaveProjectSettings(patch: {
    orchestration_mode?: 'standard' | 'dag_record' | 'dag_guided';
    defaults?: Record<string, unknown>;
    name?: string;
  }) {
    if (!activeProject) return;
    try {
      const mode = patch.orchestration_mode || activeProject.settings.orchestration_mode;
      const currentDefaults = activeProject.settings.defaults || {};
      const newDefaults = Object.fromEntries(
        Object.entries({
          ...currentDefaults,
          ...(patch.defaults || {}),
          orchestration_mode: mode,
        }).filter(([, v]) => v !== null && v !== undefined && v !== ''),
      );

      const payload: Record<string, unknown> = {
        settings: {
          orchestration_mode: mode,
          defaults: newDefaults,
        },
      };
      if (patch.name && patch.name !== activeProject.name) {
        payload.name = patch.name;
      }

      const resp = await api.patchProject(activeProject.id, payload);
      setProjects((prev) => prev.map((p) => (p.id === activeProject.id ? resp.data : p)));

      // If orchestration_mode changed, cascade to existing agents in project
      if (patch.orchestration_mode && patch.orchestration_mode !== activeProject.settings.orchestration_mode) {
        const targets = dedupeAgents(
          agents.filter((a) => a.project_id === activeProject.id && a.settings.orchestration_mode !== patch.orchestration_mode),
        );
        if (targets.length > 0) {
          const updated = await Promise.all(
            targets.map((a) => api.patchSettings(a.id, { orchestration_mode: patch.orchestration_mode })),
          );
          setAgents((prev) =>
            dedupeAgents(prev.map((a) => updated.find((u) => u.data.id === a.id)?.data ?? a)),
          );
        }
      }

      pushToast('ok', '项目全局设置已更新');
    } catch (e) {
      reportError(e);
      throw e;
    }
  }

  async function handleSaveAgentSettings(agentId: string, patch: Record<string, unknown>) {
    try {
      const resp = await api.patchSettings(agentId, patch);
      setAgents((prev) => dedupeAgents(prev.map((a) => (a.id === agentId ? resp.data : a))));
      pushToast('ok', `Agent 设置已更新: ${resp.data.display_name}`);
    } catch (e) {
      reportError(e);
      throw e;
    }
  }

  async function cancelAgent(targetId?: string, displayName?: string) {
    const id = targetId ?? activeAgent?.id;
    const name = displayName ?? (targetId ? (agents.find((a) => a.id === targetId)?.display_name ?? targetId) : activeAgent?.display_name);
    if (!id) return;
    try {
      await api.cancel(id);
      if (activeProjectId) {
        const list = await api.listAgents(activeProjectId);
        setAgents(dedupeAgents(list));
      }
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

  async function changeProjectInvocationProtocol(protocol: string) {
    if (!activeProject) return;
    // 与 YOLO 同构：写项目 defaults（新 spawn 继承）+ 级联 PATCH 现存 agent。
    // 协议在 run.started 时冻结；当前 run 不受影响，下次 run 起用新值。
    try {
      const resp = await api.patchProject(activeProject.id, {
        settings: {
          orchestration_mode: activeProject.settings.orchestration_mode,
          defaults: Object.fromEntries(
            Object.entries({
              ...activeProject.settings.defaults,
              invocation_protocol: protocol,
            }).filter(([, v]) => v !== null && v !== undefined),
          ),
        },
      });
      setProjects((prev) => prev.map((p) => (p.id === activeProject.id ? resp.data : p)));
      const targets = dedupeAgents(
        agents.filter(
          (a) =>
            a.project_id === activeProject.id &&
            (a.settings.invocation_protocol ?? 'javascript') !== protocol,
        ),
      );
      const updated = await Promise.all(
        targets.map((a) => api.patchSettings(a.id, { invocation_protocol: protocol })),
      );
      if (updated.length > 0) {
        setAgents((prev) =>
          dedupeAgents(prev.map((a) => updated.find((u) => u.data.id === a.id)?.data ?? a)),
        );
      }
      pushToast('ok', `Invocation protocol → ${protocol} (project-wide; next run)`);
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
        ? (olderEvents.length ? olderEvents : events).filter((e) => e.session_id === activeAgentId)
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
    if (olderEvents.length) return persistedTimeline;
    const persisted = new Set(
      persistedTimeline
        .filter((i): i is MessageItem => i.kind === 'message')
        .map((m) => m.content),
    );
    const frozen = streamView.frozen.filter((m) => !persisted.has(m.content));
    const merged: TimelineItem[] = [...persistedTimeline, ...frozen];
    merged.sort((a, b) => a.seq - b.seq);
    return merged;
  }, [persistedTimeline, streamView.frozen, olderEvents.length]);
  const timeline = useMemo(() => {
    if (olderEvents.length) return committedTimeline;
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
    olderEvents.length,
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
          data-testid={`agent-row-${a.id}`}
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
  const scrollRestoreRef = useRef<'older' | 'newer' | null>(null);
  useLayoutEffect(() => {
    const el = chatRef.current;
    const restore = scrollRestoreRef.current;
    if (el && restore) {
      scrollRestoreRef.current = null;
      el.scrollTop = restore === 'older' ? el.scrollHeight : 0;
    }
  }, [olderEvents]);
  const canLoadOlder = olderEvents.length
    ? hasOlder
    : hasOlder || (sessionEvents[0]?.session_seq ?? 0) > 1;
  const loadOlder = useCallback(async () => {
    if (!activeAgentId || loadingOlder || !canLoadOlder) return;
    const oldest = Math.min(...sessionEvents.map((event) => event.session_seq ?? Infinity));
    if (!Number.isFinite(oldest)) return;
    nearBottomRef.current = false;
    const version = agentSelectionVersionRef.current;
    setLoadingOlder(true);
    try {
      const page = await api.eventsPage(activeAgentId, { before: oldest, limit: HISTORY_PAGE_SIZE });
      if (version !== agentSelectionVersionRef.current) return;
      const bounded = boundEventPage(page, HISTORY_PAGE_SIZE);
      if (bounded.length) {
        scrollRestoreRef.current = 'older';
        setOlderEvents(bounded);
      }
      setHasOlder(page.length >= HISTORY_PAGE_SIZE || bounded.length < page.length);
    } catch (e) {
      reportError(e);
    } finally {
      if (version === agentSelectionVersionRef.current) setLoadingOlder(false);
    }
  }, [activeAgentId, loadingOlder, canLoadOlder, sessionEvents, reportError]);

  const loadLatest = useCallback(async () => {
    if (!activeAgentId || loadingOlder) return;
    const version = agentSelectionVersionRef.current;
    setLoadingOlder(true);
    try {
      const page = await api.eventsPage(activeAgentId, { limit: EVENTS_WINDOW });
      if (version !== agentSelectionVersionRef.current) return;
      const newest = page.at(-1)?.session_seq ?? 0;
      const bounded = boundEventPage(page, EVENTS_WINDOW);
      setEvents((prev) => mergeAndTrimLiveEvents(
        bounded, prev.filter((event) => (event.session_seq ?? 0) > newest), EVENTS_WINDOW,
      ).live);
      nearBottomRef.current = true;
      setOlderEvents([]);
      setHasOlder(page.length >= EVENTS_WINDOW || bounded.length < page.length);
    } catch (e) {
      reportError(e);
    } finally {
      if (version === agentSelectionVersionRef.current) setLoadingOlder(false);
    }
  }, [activeAgentId, loadingOlder, reportError]);

  const loadNewer = useCallback(async () => {
    if (!activeAgentId || loadingOlder || !olderEvents.length) return;
    const newest = olderEvents.at(-1)?.session_seq;
    if (newest == null) return;
    const version = agentSelectionVersionRef.current;
    setLoadingOlder(true);
    try {
      const page = await api.eventsPage(activeAgentId, { after: newest, tail: false, limit: HISTORY_PAGE_SIZE });
      if (version !== agentSelectionVersionRef.current) return;
      if (page.length) {
        scrollRestoreRef.current = 'newer';
        setOlderEvents(boundEventPage(page, HISTORY_PAGE_SIZE, 'oldest'));
        setHasOlder(true);
      } else {
        await loadLatest();
      }
    } catch (e) {
      reportError(e);
    } finally {
      if (version === agentSelectionVersionRef.current) setLoadingOlder(false);
    }
  }, [activeAgentId, loadingOlder, olderEvents, loadLatest, reportError]);

  const connLabel = !activeProject ? 'idle' : connState === 'live' ? 'live' : connState === 'connecting' ? 'connecting' : 'reconnecting…';
  const totalPending = approvals.length + interactions.length;

  return (
    <div className="app">
      <datalist id="workspace-dirs">
        {workspaceSuggestions.map((ws) => (
          <option key={ws} value={ws} />
        ))}
      </datalist>
      <aside className={`left-sidebar ${!sidebarOpen ? 'collapsed' : ''}`}>
        <div className="left-sidebar-head">
          <div className="left-sidebar-title">
            <span>{t.sidebarProjectsTitle}</span>
          </div>
          <button
            type="button"
            className="btn ghost sm"
            style={{ padding: '0 6px', height: 22 }}
            onClick={() => setSidebarOpen(false)}
            title="收起项目侧栏"
          >
            ◀
          </button>
        </div>

        <div className="left-sidebar-content">
          {/* New Project Creator Bar */}
          <div className="new-project-bar">
            <div className="new-project-row">
              <input
                className="input"
                value={newProject}
                onChange={(e) => setNewProject(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && createProjectAndSelect()}
                placeholder={t.sidebarNewProjectPlaceholder}
                style={{ height: 28, fontSize: 12, flex: 1 }}
              />
              <button
                type="button"
                className="btn primary sm"
                style={{ height: 28, padding: '0 10px' }}
                onClick={createProjectAndSelect}
                disabled={!newProject.trim()}
                title="新建项目"
              >
                +
              </button>
            </div>
            <div className="new-project-ws-row">
              <input
                className="input ws-path"
                value={newProjectWs}
                onChange={(e) => setNewProjectWs(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && createProjectAndSelect()}
                placeholder={t.sidebarNewProjectWsPlaceholder}
                title="项目工作区路径：机理计算文件与日志落盘目录"
                list="workspace-dirs"
              />
              <button
                type="button"
                className="btn ghost sm ws-browse-btn"
                title="浏览选择工作区文件夹"
                onClick={() =>
                  openPathPicker({
                    title: '选择项目工作区文件夹',
                    initialPath: newProjectWs,
                    onSelect: (p) => setNewProjectWs(p),
                  })
                }
              >
                {t.sidebarBrowseWs}
              </button>
            </div>
          </div>

          {/* Workspace Groups (按项目地址分类会话) */}
          <div className="workspace-groups-list">
            {projects.length === 0 && (
              <div className="chat-empty" style={{ padding: '20px 0' }}>
                {t.sidebarNoProjectsHint}
              </div>
            )}

            {groupedProjects.map(([ws, list]) => {
              const isCollapsed = collapsedWorkspaces.has(ws);
              const folderName = ws
                ? ws.split('/').filter(Boolean).pop() || ws
                : '未指定地址 (临时)';
              const hasActiveProject = list.some((p) => p.id === activeProjectId);

              return (
                <div key={ws || '__none'} className={`ws-group ${hasActiveProject ? 'has-active' : ''}`}>
                  <div
                    className="ws-group-header"
                    onClick={() => toggleWorkspace(ws)}
                    title={ws || '未绑定工作区目录（内存/临时工作区）'}
                  >
                    <span className="ws-folder-toggle">{isCollapsed ? '▶' : '▼'}</span>
                    <div className="ws-folder-info">
                      <span className="ws-folder-name">{folderName}</span>
                      {ws && <span className="ws-folder-path">{ws}</span>}
                    </div>
                    <span className="badge sm ws-count">{list.length}</span>
                    <button
                      type="button"
                      className="btn ghost sm ws-add-btn"
                      title={ws ? `在 ${folderName} 下新建项目` : '新建未绑定项目'}
                      onClick={(e) => {
                        e.stopPropagation();
                        setInlineCreate({ ws, name: '' });
                        setCollapsedWorkspaces((prev) => {
                          const next = new Set(prev);
                          next.delete(ws);
                          return next;
                        });
                      }}
                    >
                      +
                    </button>
                  </div>

                  {!isCollapsed && (
                    <div className="ws-group-body">
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
                            placeholder="输入项目名…"
                            style={{ height: 26, fontSize: 11.5 }}
                          />
                          <button
                            type="button"
                            className="btn primary sm"
                            style={{ height: 26, padding: '0 8px', fontSize: 11 }}
                            disabled={!inlineCreate.name.trim()}
                            onClick={() => void submitInlineCreate()}
                          >
                            创建
                          </button>
                          <button
                            type="button"
                            className="btn ghost sm"
                            style={{ height: 26, padding: '0 6px', fontSize: 11 }}
                            onClick={() => setInlineCreate(null)}
                          >
                            ✕
                          </button>
                        </div>
                      )}

                      {list.map((p) => {
                        const isActive = p.id === activeProjectId;
                        return (
                          <div
                            key={p.id}
                            className={`project-node ${isActive ? 'active' : ''}`}
                          >
                            <div
                              className="project-node-header"
                              onClick={() => selectProject(p.id)}
                              title={`选择项目: ${p.name}`}
                            >
                              <div className="project-node-title">
                                {isActive && <span className="active-dot" />}
                                <span className="project-title-text">{p.name}</span>
                                {p.name.startsWith('benchmark:') && (
                                  <span className="badge sm bm-tag">BM</span>
                                )}
                              </div>
                              <div className="project-node-actions">
                                <button
                                  type="button"
                                  className="btn ghost sm mini-icon-btn"
                                  title={`${t.sidebarRename} "${p.name}"`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    openPathPicker({
                                      title: `${t.sidebarRename} ${p.name}`,
                                      initialPath: p.workspace_dir ?? undefined,
                                      onSelect: (newDir) => void changeWorkspace(newDir),
                                    });
                                  }}
                                >
                                  {t.sidebarRename}
                                </button>
                                <button
                                  type="button"
                                  className="btn ghost sm mini-icon-btn"
                                  title={`归档 "${p.name}"`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    void archiveProject(p);
                                  }}
                                >
                                  {t.sidebarArchive}
                                </button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}

            {archivedProjects.length > 0 && (
              <details className="archived-group" style={{ marginTop: 12 }}>
                <summary className="archived-summary">
                  {t.sidebarArchivedCount(archivedProjects.length)}
                </summary>
                <div className="archived-list">
                  {archivedProjects.map((p) => (
                    <div
                      key={p.id}
                      className="archived-item"
                      onClick={() => selectProject(p.id)}
                    >
                      <span className="archived-name">{p.name}</span>
                      <button
                        type="button"
                        className="btn ghost sm"
                        style={{ height: 20, fontSize: 11, padding: '0 6px' }}
                        title={`${t.sidebarRestore} "${p.name}"`}
                        onClick={(e) => {
                          e.stopPropagation();
                          void unarchiveProject(p);
                        }}
                      >
                        {t.sidebarRestore}
                      </button>
                      <button
                        type="button"
                        className="btn ghost sm"
                        data-testid={`hard-delete-${p.id}`}
                        title={lang === 'zh' ? '永久删除（保留工作区目录）' : 'Permanently delete (keep workspace)'}
                        onClick={(e) => { e.stopPropagation(); void deleteProject(p); }}
                      >
                        {lang === 'zh' ? '永久删除' : 'Delete'}
                      </button>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        </div>

        {/* Sidebar actions */}
        <div className="left-sidebar-foot">
          <button
            type="button"
            className="btn outline sm settings-btn"
            onClick={() => setGlobalOpen(true)}
            title={t.sidebarGlobalSettingsTip}
          >
            <span>{t.sidebarGlobalSettings}</span>
          </button>
          <details className="sidebar-more">
            <summary>{t.sidebarMore}</summary>
            <div className="sidebar-more-actions">
              <button
                type="button"
                className="btn ghost sm"
                onClick={(event) => {
                  event.currentTarget.closest('details')?.removeAttribute('open');
                  setBenchmarkOpen(true);
                }}
              >
                {t.sidebarBenchmark}
              </button>
              <button
                type="button"
                className="btn ghost sm"
                data-testid="cancel-all-compute-foot"
                disabled={cancellingCompute}
                onClick={() => { void cancelAllComputeJobs(); }}
              >
                {cancellingCompute
                  ? (lang === 'zh' ? '请求中…' : 'Requesting…')
                  : (lang === 'zh' ? '取消全部计算' : 'Cancel All Compute')}
              </button>
            </div>
          </details>
        </div>
      </aside>

      <main className="main">
        <div className="agentbar">
          <div className="agentbar-left">
            <button
              type="button"
              className={`btn ghost sm sidebar-toggle-btn ${sidebarOpen ? 'active' : ''}`}
              onClick={() => setSidebarOpen((v) => !v)}
              title={sidebarOpen ? '◀' : '▶'}
              style={{ height: 26, padding: '0 8px', fontSize: 11.5 }}
            >
              {sidebarOpen ? '◀' : `▶ ${t.sidebarProjectsTitle}`}
            </button>
            <div
              className="brand-logo-wrap"
              title="Cloudra — Computational Chemistry Agent Workbench"
              onClick={() => {
                setSidebarOpen(true);
              }}
            >
              <img src="/logo.png" alt="Cloudra" className="brand-logo-icon" />
              <span className="brand-logo-text">Cloudra</span>
            </div>
            <div className="agentbar-divider" />
            <div className="header-breadcrumb">
              <span
                className="breadcrumb-project"
                title={activeProject?.name ? `${t.projectSettings}: ${activeProject.name}` : t.breadcrumbSelectProject}
                onClick={() => {
                  setSidebarOpen(true);
                }}
              >
                {activeProject?.name ?? t.breadcrumbSelectProject}
              </span>
              {activeAgent && (
                <>
                  <span className="breadcrumb-separator">/</span>
                  {agents.length > 1 ? (
                    <div className="breadcrumb-agent-wrap">
                      <span className={`state-dot ${activeAgent.state}`} />
                      <select
                        className="breadcrumb-agent-select"
                        value={activeAgent.id}
                        onChange={(e) => {
                          const val = e.target.value;
                          if (val.startsWith('spawn:')) {
                            void spawnRole(val.slice(6));
                          } else {
                            void selectAgent(val);
                          }
                        }}
                      >
                        <optgroup label={t.breadcrumbActiveAgents}>
                          {agents.map((a) => (
                            <option key={a.id} value={a.id}>
                              {a.display_name} ({a.role_id})
                            </option>
                          ))}
                        </optgroup>
                        {roles.length > 0 && (
                          <optgroup label={t.breadcrumbSpawnAgent}>
                            {roles.map((r) => (
                              <option key={r.role_id} value={`spawn:${r.role_id}`}>
                                + {r.display_name} ({r.role_id})
                              </option>
                            ))}
                          </optgroup>
                        )}
                      </select>
                      {activeAgent.current_task && (
                        <span className="breadcrumb-current-task" title={activeAgent.current_task}>
                          <span className="task-banner-pulse" />
                          <span className="breadcrumb-task-text">{activeAgent.current_task}</span>
                        </span>
                      )}
                      <CompletionChip completion={activeAgent.completion} />
                    </div>
                  ) : (
                    <span className="breadcrumb-agent" title={`Active Agent: ${activeAgent.display_name} (${activeAgent.role_id}) · state: ${activeAgent.state}`}>
                      <span className={`state-dot ${activeAgent.state}`} />
                      <span className="breadcrumb-agent-name">{activeAgent.display_name}</span>
                      <span className="badge role-badge">{activeAgent.role_id}</span>
                      {activeAgent.current_task && (
                        <span className="breadcrumb-current-task" title={activeAgent.current_task}>
                          <span className="task-banner-pulse" />
                          <span className="breadcrumb-task-text">{activeAgent.current_task}</span>
                        </span>
                      )}
                      <CompletionChip completion={activeAgent.completion} />
                    </span>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Central View Mode Switcher */}
          <div className="view-mode-switcher">
            <button
              type="button"
              className={`view-mode-btn ${viewMode === 'dialogue' ? 'active' : ''}`}
              onClick={() => setViewMode('dialogue')}
              title={lang === 'zh' ? '切换至对话流模式 (全屏推演与交互)' : 'Switch to Dialogue Mode'}
            >
              <span>{t.dialogue}</span>
            </button>
            <button
              type="button"
              className={`view-mode-btn ${viewMode === 'console' ? 'active' : ''}`}
              onClick={() => setViewMode('console')}
              title={lang === 'zh' ? '切换至控制台模式 (机理图与计算队列)' : 'Switch to Console Mode'}
            >
              <span>{t.console}</span>
              {sidebarJobs && sidebarJobs.length > 0 && (
                <span className="mode-badge">{sidebarJobs.length}</span>
              )}
            </button>
          </div>

          <div className="agentbar-group system-controls">
            <button
              type="button"
              className="btn outline sm project-settings-btn"
              onClick={() => setProjectSettingsOpen(true)}
              title={activeProject ? `${t.projectSettings}: ${activeProject.name}` : t.selectProjectHint}
              disabled={!activeProject}
            >
              <span>{t.projectSettings}</span>
            </button>
            <div className="lang-switcher-pill" title={t.langToggle}>
              <button
                type="button"
                className={`lang-pill-btn ${lang === 'zh' ? 'active' : ''}`}
                onClick={() => setLang('zh')}
              >
                中
              </button>
              <button
                type="button"
                className={`lang-pill-btn ${lang === 'en' ? 'active' : ''}`}
                onClick={() => setLang('en')}
              >
                EN
              </button>
            </div>
            <span className="conn-status" title={`SSE stream status: ${connLabel}`}>
              {activeProject && <span className={`state-dot ${connState === 'live' ? 'running' : 'waiting_input'}`} />}
              <span className="conn-label">{connState === 'live' ? t.live : connLabel}</span>
            </span>
            {totalPending > 0 && (
              <span className="badge attention-badge" title={`${totalPending} 项决策等待审核`}>
                {totalPending} 待审核
              </span>
            )}
          </div>
        </div>

        {viewMode === 'dialogue' ? (
          <>
            {activeAgent && (
              <div className={`live-agent-pulse ${currentAgentActivity.type}`}>
                <span className="pulse-indicator">
                  <span className="pulse-dot" />
                </span>
                <span className="pulse-agent">{activeAgent.display_name}</span>
                <span className="pulse-divider">·</span>
                <span className="pulse-status">{currentAgentActivity.label}</span>
                {sidebarJobs && sidebarJobs.length > 0 && (
                  <span
                    className="pulse-compute-tag"
                    onClick={() => {
                      setViewMode('console');
                      setConsoleTab('compute');
                    }}
                    title="切换至控制台查看计算队列"
                  >
                    {lang === 'zh'
                      ? `${sidebarJobs.length} 个计算任务未完成 →`
                      : `${sidebarJobs.length} unfinished compute jobs →`}
                  </span>
                )}
              </div>
            )}
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
                <div className="big">{t.emptyHeroTitle}</div>
                {t.selectProjectHint}
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
            {activeAgent && canLoadOlder && sessionEvents.length > 0 && (
              <button className="load-earlier" disabled={loadingOlder} onClick={() => void loadOlder()}>
                {loadingOlder ? 'loading…' : 'Load earlier'}
              </button>
            )}
            {activeAgent && !hasOlder && olderEvents.length > 0 && (
              <div className="history-end">beginning of history</div>
            )}
            {olderEvents.length > 0 && (
              <div className="audit-pager">
                <span>Browsing history · {olderEvents.length} events shown</span>
                <button className="btn ghost sm" disabled={loadingOlder} onClick={() => void loadNewer()}>Newer</button>
                <button className="btn ghost sm" disabled={loadingOlder} onClick={() => void loadLatest()}>Latest</button>
              </div>
            )}
            {sessionEvents.some((event) => event.data._payload_omitted) && (
              <button className="load-earlier" onClick={() => { setViewMode('console'); setConsoleTab('audit'); }}>
                Large event contents are available in the audit log
              </button>
            )}
            {streamView.omitted && !olderEvents.length && (
              <div className="history-end">
                Earlier transient text is omitted from this view. Full persisted events are available in the audit log.
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
                  className={`tool-row ${item.level === 'info' ? 'info' : 'fail'}`}
                  style={{ cursor: 'default' }}
                >
                  <span className="tool-icon">{noteIcon(item.level)}</span>
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
                <span style={{ color: 'var(--yellow-soft)' }}>{t.approvalTimelineWaiting}</span>
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
          {(interactions.length > 0 || approvals.length > 0) && (
            <InteractionPrompt
              key={activeProjectId}
              interactions={interactions}
              approvals={approvals}
              activeAgent={activeAgent}
              agents={agents}
              onRespond={handleRespondInteraction}
              onDecide={handleDecideApproval}
              onSelectAgent={(agentId: string) => void selectAgent(agentId)}
              onToggleYolo={(yoloVal: boolean) => toggleProjectYolo(yoloVal)}
              isYolo={activeProject?.settings.defaults?.yolo === true}
              sending={sending}
              t={t}
              isCollapsed={interactionCollapsed}
              onToggleCollapse={(c: boolean) => setInteractionCollapsed(c)}
            />
          )}
          {(!hasActiveAgentDecision || interactionCollapsed) && (
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
              data-testid="composer-input"
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
              {activeProject && (
                <button
                  type="button"
                  className={`yolo-toggle-badge ${activeProject.settings.defaults?.yolo === true ? 'active' : 'guarded'}`}
                  title={
                    activeProject.settings.defaults?.yolo === true
                      ? '安全策略：当前处于 YOLO 模式（敏感破坏性操作自动放行）'
                      : '安全策略：当前处于 SAFE 模式（敏感操作与计算需人工审批）'
                  }
                  onClick={() => toggleProjectYolo(!(activeProject.settings.defaults?.yolo === true))}
                >
                  <span className="yolo-tag">{activeProject.settings.defaults?.yolo === true ? 'YOLO' : 'SAFE'}</span>
                </button>
              )}
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
          )}
        </div>
      </>
    ) : (
      <div className="console-view-wrapper">
        {/* Console Sub-navigation Bar */}
        <div className="console-subnav-bar">
          <div className="console-subnav-pills">
            <button
              type="button"
              className={`console-subnav-btn ${consoleTab === 'overview' ? 'active' : ''}`}
              onClick={() => setConsoleTab('overview')}
            >
              <span>{t.tabOverview}</span>
            </button>
            <button
              type="button"
              className={`console-subnav-btn ${consoleTab === 'dag' ? 'active' : ''}`}
              onClick={() => setConsoleTab('dag')}
            >
              <span>{t.tabDag}</span>
              {(activeProject?.settings.orchestration_mode === 'dag_guided' ||
                activeProject?.settings.defaults?.orchestration_mode === 'dag_guided') && (
                <span className="subnav-dot-active" />
              )}
            </button>
            <button
              type="button"
              className={`console-subnav-btn ${consoleTab === 'compute' ? 'active' : ''}`}
              onClick={() => setConsoleTab('compute')}
            >
              <span>{t.tabCompute}</span>
              {sidebarJobs && sidebarJobs.length > 0 && (
                <span className="badge sm">{sidebarJobs.length}</span>
              )}
            </button>
            <button
              type="button"
              className={`console-subnav-btn ${consoleTab === 'artifacts' ? 'active' : ''}`}
              onClick={() => setConsoleTab('artifacts')}
            >
              <span>{t.tabArtifacts}</span>
            </button>
            <button
              type="button"
              className={`console-subnav-btn ${consoleTab === 'audit' ? 'active' : ''}`}
              onClick={() => setConsoleTab('audit')}
            >
              <span>{t.tabAudit}</span>
            </button>
            <button
              type="button"
              className={`console-subnav-btn ${consoleTab === 'telemetry' ? 'active' : ''}`}
              onClick={() => setConsoleTab('telemetry')}
            >
              <span>{t.tabTelemetry}</span>
            </button>
            <button
              type="button"
              className={`console-subnav-btn ${consoleTab === 'hub' ? 'active' : ''}`}
              onClick={() => setConsoleTab('hub')}
            >
              <span>{t.tabHub}</span>
            </button>
          </div>

          {consoleTab !== 'overview' && (
            <button
              type="button"
              className="btn ghost sm console-back-overview-btn"
              onClick={() => setConsoleTab('overview')}
            >
              {t.backToOverview}
            </button>
          )}
        </div>

        {/* Console Active Tab Viewport */}
        <div className="console-tab-viewport">
          {!activeProject ? (
            <div className="chat-empty">{t.selectProjectHint}</div>
          ) : consoleTab === 'overview' ? (
            <ConsoleIndexPage
              project={activeProject}
              agents={agents}
              activeAgent={activeAgent}
              sidebarJobs={sidebarJobs}
              onNavigate={(tab) => setConsoleTab(tab)}
              onOpenProjectSettings={() => setProjectSettingsOpen(true)}
              onSelectAgent={(agentId) => selectAgent(agentId)}
              onOpenDialogue={(agentId) => {
                selectAgent(agentId);
                setViewMode('dialogue');
              }}
              onError={reportError}
              onToast={(text, kind) => pushToast(kind === 'warn' ? 'info' : (kind ?? 'info'), text)}
            />
          ) : consoleTab === 'dag' ? (
            <DagPanel
              project={activeProject}
              onError={reportError}
              onToast={pushToast}
            />
          ) : consoleTab === 'compute' ? (
            <div className="console-compute-container">
              <OpsPanel project={activeProject} agents={agents} onError={reportError} refreshVersion={computeRefreshVersion} />
            </div>
          ) : consoleTab === 'artifacts' ? (
            <ArtifactsPanel project={activeProject} onError={reportError} />
          ) : consoleTab === 'audit' ? (
            <div className="console-audit-container">
              <AuditLog
                agentId={activeAgentId}
                projectId={activeProjectId}
                liveEvents={events}
                onError={reportError}
              />
            </div>
          ) : consoleTab === 'telemetry' ? (
            <div className="console-telemetry-embedded">
              <TelemetryPanel onClose={() => setConsoleTab('overview')} onToast={pushToast} />
            </div>
          ) : consoleTab === 'hub' ? (
            <div className="console-hub-container">
              <HubPanel
                projects={projects}
                initialProjectId={activeProjectId}
                embedded
                onToast={pushToast}
              />
            </div>
          ) : null}
        </div>
      </div>
    )}
  </main>

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
        {projectSettingsOpen && activeProject && (
          <ProjectSettingsModal
            project={activeProject}
            agents={agents.filter((a) => a.project_id === activeProject.id)}
            activeAgentId={activeAgentId}
            roles={roles}
            onClose={() => setProjectSettingsOpen(false)}
            onSaveProjectSettings={handleSaveProjectSettings}
            onSaveAgentSettings={handleSaveAgentSettings}
            onToast={pushToast}
          />
        )}
        {globalOpen && (
          <GlobalConfig
            onClose={() => setGlobalOpen(false)}
            onToast={pushToast}
          />
        )}
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
        {hubOpen && (
          <HubPanel
            projects={projects}
            initialProjectId={activeProjectId}
            onClose={() => setHubOpen(false)}
            onToast={pushToast}
          />
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
