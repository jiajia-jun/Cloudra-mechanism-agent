import { Fragment, memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, EVENTS_WINDOW, streamProject } from './api';
import Markdown from './Markdown';
import DagPanel from './DagPanel';
import type { Agent, EventEnvelope, Project } from './types';
import AuditLog from './AuditLog';
import GlobalConfig from './GlobalConfig';
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
  const [globalOpen, setGlobalOpen] = useState(false);
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

  // Refs so the long-lived SSE subscription always sees current values.
  const activeAgentIdRef = useRef(activeAgentId);
  activeAgentIdRef.current = activeAgentId;
  // Highest session_seq seen for the visible agent (chunks carry seq 0, so
  // thinking segments anchor to the last real event before them).
  const maxSeqRef = useRef(0);
  const thinkingIdRef = useRef(0);

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

  /* ---------------------------------------------------- project switching */

  const selectAgent = useCallback(
    async (agentId: string) => {
      setActiveAgentId(agentId);
      setPendingMessages([]);
      setStreamView({ streamText: '', frozen: [] });
      setThinkingItems([]);
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
            await api.compactAgent(activeAgent.id, 6);
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
    () => (activeAgentId ? events.filter((e) => e.session_id === activeAgentId) : []),
    [events, activeAgentId],
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
    // Live bubble before the thinking block (seq 0.4 < 0.5), then any
    // transient thinking segments, then optimistic pending user messages.
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
    items.push(...thinkingItems);
    return [...items, ...pendingMessages];
  }, [committedTimeline, thinkingItems, streamView.streamText, pendingMessages, activeAgent?.display_name]);
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

  // The dock covers only OTHER projects — the active one already surfaces
  // requests via the Inspector tabs and the composer ask-banner.
  const attentionItems = useMemo(() => {
    const others = new Map(attention);
    if (activeProjectId) others.delete(activeProjectId);
    return collectPending(others);
  }, [attention, activeProjectId]);

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
      <datalist id="workspace-dirs">
        {workspaceSuggestions.map((ws) => (
          <option key={ws} value={ws} />
        ))}
      </datalist>
      <aside className="sidebar">
        <div className="sidebar-head">
          <img className="brand-logo" src="/logo.png" alt="Cloudra" />
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
            list="workspace-dirs"
          />
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
                  onClick={() => setActiveProjectId(p.id)}
                >
                  <div className="project-name">{p.name}</div>
                  <div className="project-meta">{p.settings.orchestration_mode}</div>
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
                  onClick={() => setActiveProjectId(p.id)}
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
                </div>
              ))}
            </details>
          )}
        </div>
        <div className="sidebar-foot">
          <button
            type="button"
            className="btn outline sm sidebar-global"
            title="Global LLM config: the fallback slots behind empty per-agent settings"
            onClick={() => setGlobalOpen(true)}
          >
            ⚙ Global settings
          </button>
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
              list="workspace-dirs"
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
                    {uploading ? 'Uploading…' : '📎 Image'}
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

      <Inspector
        activeAgent={activeAgent}
        activeProject={activeProject}
        liveEvents={sessionEvents}
        onPatchSettings={patchSettings}
        approvals={approvals}
        interactions={interactions}
        onRefreshApprovals={() => activeProject && api.approvals(activeProject.id).then(setApprovals).catch(reportError)}
        onRefreshInteractions={() => activeProject && api.interactions(activeProject.id).then(setInteractions).catch(reportError)}
        onError={reportError}
        onToast={pushToast}
      />

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
    </div>
  );
}

/* ------------------------------------------------------------------ tool row */

function ToolRowView({ item, imageUrl }: { item: ToolItem; imageUrl?: string | null }) {
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
      {imageUrl && !item.running && (
        <a className="tool-image" href={imageUrl} target="_blank" rel="noreferrer" title={item.imagePath ?? 'image output'}>
          <img src={imageUrl} alt={`${item.name} output`} loading="lazy" />
        </a>
      )}
      {open && (
        <div className="tool-detail">
          {item.argsSummary && (
            <div className="tool-detail-section">
              <span className="tool-detail-label">Arguments</span>
              <pre className="tool-detail-pre">{item.argsSummary}</pre>
            </div>
          )}
          {item.resultSummary && (
            <div className="tool-detail-section">
              <span className="tool-detail-label">Output</span>
              <pre className="tool-detail-pre">{item.resultSummary}</pre>
            </div>
          )}
        </div>
      )}
    </>
  );
}

// Memoized so a tool row re-renders only when its own item reference changes
// (i.e. the persisted timeline rebuilt), not on every streaming token.
const ToolRow = memo(ToolRowView);

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

function Inspector({ activeAgent, activeProject, liveEvents, onPatchSettings, approvals, interactions, onRefreshApprovals, onRefreshInteractions, onError, onToast }: {
  activeAgent: Agent | null;
  activeProject: Project | null;
  liveEvents: EventEnvelope[];
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
          <AuditLog
            agentId={activeAgent?.id ?? null}
            projectId={activeProject?.id ?? null}
            liveEvents={liveEvents}
            onError={onError}
          />
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
                  {risk && <div className="approval-risk-banner">⚠️ {risk}</div>}
                  {details && <div className="approval-details-text">{details}</div>}
                  {diff && (
                    <div className="approval-diff-wrap">
                      <div className="approval-diff-title">Proposed Changes</div>
                      <pre className="approval-diff-content">{diff}</pre>
                    </div>
                  )}
                  <div className="card-actions">
                    <button className="btn green sm" disabled={deciding !== null} onClick={() => decide(id, 'approve')}>
                      {deciding === `${id}:approve` ? 'Approving…' : '✓ Approve'}
                    </button>
                    <button className="btn yellow sm" disabled={deciding !== null} onClick={() => decide(id, 'deny')}>
                      {deciding === `${id}:deny` ? 'Denying…' : '✕ Deny'}
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
            {artifacts.length === 0 && <div className="empty-hint">No artifacts yet.</div>}
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
              <div className="settings-note">
                <div className="settings-note-title">Agent override — this session only</div>
                <ul>
                  <li>
                    Edits the effective settings of <b>{activeAgent.display_name}</b> alone: a
                    field-level override layered on top of project defaults and role defaults.
                  </li>
                  <li>
                    Other agents — including sub-agents spawned later — are <b>not</b> affected
                    and do not inherit these overrides.
                  </li>
                  <li>
                    Empty model / base_url / api key fall back to the global config (
                    <b>{activeAgent.role_id === 'coordinator' ? 'coordinator' : 'follower'}</b>{' '}
                    slot for this role).
                  </li>
                  <li>
                    Effective on the next LLM request. The api key can be overridden per agent
                    (write-only: the stored value is never shown).
                  </li>
                </ul>
              </div>
              <label className="field">
                model
                <input
                  className="input"
                  key={`model-${activeAgent.id}`}
                  defaultValue={activeAgent.settings.model}
                  onBlur={(e) => e.target.value !== activeAgent.settings.model && onPatchSettings({ model: e.target.value })}
                />
                <span className="field-hint">
                  empty → global config ({activeAgent.role_id === 'coordinator' ? 'coordinator' : 'follower'} slot)
                </span>
              </label>
              <label className="field">
                base_url
                <input
                  className="input"
                  key={`url-${activeAgent.id}`}
                  defaultValue={activeAgent.settings.base_url}
                  onBlur={(e) => e.target.value !== activeAgent.settings.base_url && onPatchSettings({ base_url: e.target.value })}
                />
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
              <div className="muted-note">Changes apply to this session on the next LLM request.</div>
            </>
          ) : (
            <div className="empty-hint">Select an agent to edit settings.</div>
          ))}
      </div>
    </aside>
  );
}
