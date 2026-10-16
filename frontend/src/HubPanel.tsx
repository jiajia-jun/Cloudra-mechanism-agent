/**
 * HubPanel — AgentHub 论坛：项目内 agent 帖子的完整可视化 + 用户发帖。
 * 支持作为控制台嵌入式 Tab 面板，也支持作为弹窗运行。
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, streamProject } from './api';
import { planSseReconnect } from './sseReconnect';
import type { Agent, HubPost, Project } from './types';
import { useI18n } from './i18n';

export interface HubPanelProps {
  projects: Project[];
  initialProjectId: string | null;
  onClose?: () => void;
  onToast: (kind: 'ok' | 'error' | 'info', text: string) => void;
  embedded?: boolean;
}

function RefreshSvg() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
    </svg>
  );
}

function CloseSvg() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function ForumSvg() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}

function ReplySvg() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 17 4 12 9 7" />
      <path d="M20 18v-2a4 4 0 0 0-4-4H4" />
    </svg>
  );
}

function SendSvg() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function HashSvg() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="4" y1="9" x2="20" y2="9" />
      <line x1="4" y1="15" x2="20" y2="15" />
      <line x1="10" y1="3" x2="8" y2="21" />
      <line x1="16" y1="3" x2="14" y2="21" />
    </svg>
  );
}

function fmtTs(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function PostCard({
  post,
  depth,
  onReply,
}: {
  post: HubPost;
  depth: number;
  onReply: (post: HubPost) => void;
}) {
  const { t } = useI18n();
  const kindLabels: Record<string, string> = {
    finding: t.hubKindFinding,
    question: t.hubKindQuestion,
    answer: t.hubKindAnswer,
    broadcast: t.hubKindBroadcast,
    message: t.hubKindMessage,
  };
  const isUser = post.author_agent === 'user';
  const roleLower = post.author_agent.toLowerCase();
  const authorBadgeClass = isUser
    ? 'author-user'
    : roleLower.includes('coordinator')
    ? 'author-coordinator'
    : roleLower.includes('supervisor')
    ? 'author-supervisor'
    : roleLower.includes('calc') || roleLower.includes('compute') || roleLower.includes('small_mol')
    ? 'author-compute'
    : 'author-agent';

  return (
    <div className={`hub-post ${depth > 0 ? `hub-depth-${Math.min(depth, 4)}` : ''}`}>
      <div className="hub-post-head">
        <span className={`hub-author ${authorBadgeClass}`}>
          {isUser ? t.hubUser : post.author_agent}
        </span>
        <span className={`hub-kind hub-kind-${post.kind}`}>
          {kindLabels[post.kind] ?? post.kind}
        </span>
        {post.to_agent && (
          <span className="hub-to" title={`@${post.to_agent}`}>
            → @{post.to_agent}
          </span>
        )}
        <span className="hub-time">{fmtTs(post.created_at)}</span>
        <button
          type="button"
          className="btn ghost sm hub-reply-btn"
          onClick={() => onReply(post)}
          title={t.hubReplyAction}
        >
          <ReplySvg />
          <span>{t.hubReplyAction}</span>
        </button>
      </div>
      <div className="hub-post-content">{post.content}</div>
    </div>
  );
}

export default function HubPanel({
  projects,
  initialProjectId,
  onClose,
  onToast,
  embedded = false,
}: HubPanelProps) {
  const { t } = useI18n();
  const [projectId, setProjectId] = useState<string | null>(initialProjectId ?? projects[0]?.id ?? null);
  const [posts, setPosts] = useState<HubPost[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadedPid, setLoadedPid] = useState<string | null>(null);
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [replyTo, setReplyTo] = useState<HubPost | null>(null);
  const [topic, setTopic] = useState('');
  const [kind, setKind] = useState('question');
  const [toAgent, setToAgent] = useState('');
  const [content, setContent] = useState('');
  const [sending, setSending] = useState(false);
  const [pendingPosts, setPendingPosts] = useState(0);
  const cursorRef = useRef(0);
  const latestPostSeqRef = useRef(0);
  const loadVersionRef = useRef(0);

  // Sync if initialProjectId changes
  useEffect(() => {
    if (initialProjectId && initialProjectId !== projectId) {
      setProjectId(initialProjectId);
    }
  }, [initialProjectId]);

  const load = useCallback(
    async (pid: string) => {
      const version = ++loadVersionRef.current;
      setLoading(true);
      try {
        const view = await api.projectView(pid);
        if (version !== loadVersionRef.current) return;
        const res = await api.hubPosts(pid);
        if (version !== loadVersionRef.current) return;
        setPosts(res.posts);
        const fetchedThrough = res.posts.reduce((max, post) => Math.max(max, post.seq), 0);
        setPendingPosts(latestPostSeqRef.current > fetchedThrough ? 1 : 0);
        latestPostSeqRef.current = Math.max(latestPostSeqRef.current, fetchedThrough);
        cursorRef.current = Math.max(cursorRef.current, view.cursor, fetchedThrough);
        setAgents(view.agents);
        setLoadedPid(pid);
      } catch (e) {
        onToast('error', e instanceof Error ? e.message : String(e));
      } finally {
        if (version === loadVersionRef.current) setLoading(false);
      }
    },
    [onToast],
  );

  useEffect(() => {
    ++loadVersionRef.current;
    setPosts([]);
    setAgents([]);
    setLoadedPid(null);
    setSelectedTopic(null);
    setReplyTo(null);
    cursorRef.current = 0;
    latestPostSeqRef.current = 0;
    setPendingPosts(0);
    if (projectId) void load(projectId);
    return () => { ++loadVersionRef.current; };
  }, [projectId, load]);

  // Keep the browsed forum page stable. New posts are a refresh indicator,
  // rather than an ever-growing second event history.
  useEffect(() => {
    if (!projectId || loadedPid !== projectId) return;
    let source: ReturnType<typeof streamProject> | null = null;
    let closed = false;
    let reconnectTimer: number | null = null;
    const connect = () => {
      if (closed) return;
      source = streamProject(projectId, cursorRef.current, {
        onEvent: (event) => {
          if (closed) return;
          if (event.type === 'project.synced') {
            cursorRef.current = Math.max(cursorRef.current, Number(event.data.replayed_through ?? 0));
            return;
          }
          if (event.seq <= cursorRef.current) return;
          cursorRef.current = event.seq;
          if (event.type !== 'hub.posted' || event.seq <= latestPostSeqRef.current) return;
          latestPostSeqRef.current = event.seq;
          setPendingPosts((count) => Math.min(count + 1, 10000));
        },
        onError: () => {
          const plan = planSseReconnect({ cursor: cursorRef.current, stillWanted: !closed });
          if (plan.action === 'ignore') return;
          source?.close();
          source = null;
          if (reconnectTimer === null) reconnectTimer = window.setTimeout(() => {
            reconnectTimer = null;
            connect();
          }, plan.delayMs);
        },
      });
    };
    connect();
    return () => {
      closed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      source?.close();
    };
  }, [projectId, loadedPid]);

  const topics = useMemo(() => {
    const map = new Map<string, { topic: string; count: number; latestSeq: number; latestAt: string; preview: string }>();
    for (const p of posts) {
      const entry = map.get(p.topic) ?? { topic: p.topic, count: 0, latestSeq: -1, latestAt: '', preview: '' };
      entry.count += 1;
      if (p.seq > entry.latestSeq) {
        entry.latestSeq = p.seq;
        entry.latestAt = p.created_at;
        entry.preview = p.content.slice(0, 60);
      }
      map.set(p.topic, entry);
    }
    return [...map.values()].sort((a, b) => b.latestSeq - a.latestSeq);
  }, [posts]);

  // Topic view: threads via parent_id. Latest view: flat, newest first.
  const { roots, childrenOf } = useMemo(() => {
    const inScope = selectedTopic ? posts.filter((p) => p.topic === selectedTopic) : [];
    const byId = new Set(inScope.map((p) => p.id));
    const childrenOf = new Map<string, HubPost[]>();
    const roots: HubPost[] = [];
    for (const p of inScope) {
      if (p.parent_id && byId.has(p.parent_id)) {
        const list = childrenOf.get(p.parent_id) ?? [];
        list.push(p);
        childrenOf.set(p.parent_id, list);
      } else {
        roots.push(p);
      }
    }
    const bySeq = (a: HubPost, b: HubPost) => a.seq - b.seq;
    roots.sort(bySeq);
    for (const list of childrenOf.values()) list.sort(bySeq);
    return { roots, childrenOf };
  }, [posts, selectedTopic]);

  const latestPosts = useMemo(
    () => (selectedTopic ? [] : [...posts].sort((a, b) => b.seq - a.seq).slice(0, 200)),
    [posts, selectedTopic],
  );

  const startReply = (post: HubPost) => {
    setReplyTo(post);
    setSelectedTopic(post.topic);
    setTopic(post.topic);
  };

  const renderThread = (post: HubPost, depth: number): ReactNode => (
    <div key={post.id}>
      <PostCard post={post} depth={depth} onReply={startReply} />
      {(childrenOf.get(post.id) ?? []).map((child) => renderThread(child, depth + 1))}
    </div>
  );

  const selectTopic = (tName: string | null) => {
    setSelectedTopic(tName);
    setReplyTo(null);
    if (tName) setTopic(tName);
  };

  const submit = async () => {
    if (!projectId || sending) return;
    if (!topic.trim() || !content.trim()) {
      onToast('error', t.hubPostEmpty);
      return;
    }
    setSending(true);
    try {
      const res = await api.hubPost(projectId, {
        topic: topic.trim(),
        content: content.trim(),
        kind,
        ...(toAgent.trim() ? { to_agent: toAgent.trim() } : {}),
        ...(replyTo ? { parent_id: replyTo.id } : {}),
      });
      await load(projectId);
      setSelectedTopic(res.post.topic);
      setContent('');
      setToAgent('');
      setReplyTo(null);
      onToast('ok', t.hubPostedToast(res.notified_count));
    } catch (e) {
      onToast('error', e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };

  const roleOptions = useMemo(() => {
    const roles = new Set<string>();
    for (const a of agents) roles.add(a.role_id);
    return [...roles].sort();
  }, [agents]);

  const kindOptions: Record<string, string> = {
    finding: t.hubKindFinding,
    question: t.hubKindQuestion,
    answer: t.hubKindAnswer,
    broadcast: t.hubKindBroadcast,
    message: t.hubKindMessage,
  };

  const panelBody = (
    <div className={`hub-panel-root ${embedded ? 'embedded' : 'modal hub-modal'}`}>
      <div className="hub-head">
        <div className="hub-head-left">
          <span className="hub-header-icon-wrap icon-indigo">
            <ForumSvg />
          </span>
          <div className="hub-header-titles">
            <div className="hub-title-row">
              <span className="hub-title">{t.hubTitle}</span>
              <span className="badge sm neutral">{t.hubPostsCount(posts.length)}</span>
            </div>
            <div className="hub-subtitle">
              {t.hubSubtitle}
            </div>
          </div>
        </div>
        <div className="hub-head-right">
          <select
            className="select sm hub-project-select"
            value={projectId ?? ''}
            onChange={(e) => setProjectId(e.target.value || null)}
            title={t.hubProjectSelectHint}
          >
            {!projectId && <option value="">{t.hubChooseProject}</option>}
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn ghost sm hub-refresh-btn"
            onClick={() => projectId && void load(projectId)}
            disabled={!projectId || loading}
            title={t.hubRefresh}
          >
            <RefreshSvg />
            <span>{t.hubRefresh}</span>
          </button>
          {!embedded && onClose && (
            <button className="btn ghost sm" type="button" onClick={onClose} title="关闭 (Esc)">
              <CloseSvg />
            </button>
          )}
        </div>
      </div>

      {!projectId ? (
        <div className="hub-empty">{t.hubProjectEmptyHint}</div>
      ) : (
        <div className="hub-body">
          <div className="hub-topics">
            <button
              type="button"
              className={`hub-topic-row ${selectedTopic === null ? 'active' : ''}`}
              onClick={() => selectTopic(null)}
            >
              <div className="hub-topic-row-main">
                <span className="hub-topic-name">{t.hubLatestTopicTitle}</span>
                <span className="badge sm neutral">{posts.length}</span>
              </div>
              <span className="hub-topic-preview">{t.hubLatestTopicDesc}</span>
            </button>
            <div className="hub-topics-divider">
              <span>{t.hubTopicsCategoryTitle(topics.length)}</span>
            </div>
            {topics.map((tItem) => (
              <button
                key={tItem.topic}
                type="button"
                className={`hub-topic-row ${selectedTopic === tItem.topic ? 'active' : ''}`}
                onClick={() => selectTopic(tItem.topic)}
                title={tItem.topic}
              >
                <div className="hub-topic-row-main">
                  <span className="hub-topic-name">
                    <HashSvg />
                    <span>{tItem.topic}</span>
                  </span>
                  <span className="badge sm neutral">{tItem.count}</span>
                </div>
                <span className="hub-topic-preview">{tItem.preview}</span>
                <div className="hub-topic-meta">
                  <span>{fmtTs(tItem.latestAt)}</span>
                </div>
              </button>
            ))}
            {topics.length === 0 && !loading && (
              <div className="hub-topics-empty">{t.hubTopicsEmpty}</div>
            )}
          </div>

          <div className="hub-main">
            {pendingPosts > 0 && (
              <button className="btn outline sm" disabled={loading} onClick={() => projectId && void load(projectId)}>
                {pendingPosts >= 10000 ? '10,000+' : pendingPosts} new posts · refresh latest
              </button>
            )}
            <div className="hub-posts">
              {loading && posts.length === 0 && <div className="hub-empty">{t.hubLoadingPosts}</div>}
              {!loading && posts.length === 0 && (
                <div className="hub-empty-state">
                  <span className="empty-svg-wrap icon-indigo">
                    <ForumSvg />
                  </span>
                  <span className="empty-title">{t.hubEmptyTitle}</span>
                  <span className="empty-desc">{t.hubEmptyDesc}</span>
                </div>
              )}
              {selectedTopic === null
                ? latestPosts.map((p) => (
                    <div key={p.id}>
                      <div className="hub-latest-topic" onClick={() => selectTopic(p.topic)}>
                        <HashSvg />
                        <span>{p.topic}</span>
                      </div>
                      <PostCard post={p} depth={0} onReply={startReply} />
                    </div>
                  ))
                : roots.map((p) => renderThread(p, 0))}
            </div>

            <div className="hub-composer">
              {replyTo && (
                <div className="hub-reply-chip">
                  <ReplySvg />
                  <span>
                    {t.hubReplyToAuthor(replyTo.author_agent === 'user' ? t.hubUser : replyTo.author_agent)}
                  </span>
                  <button
                    type="button"
                    className="hub-reply-cancel"
                    onClick={() => setReplyTo(null)}
                    title={t.hubCancelReply}
                  >
                    <CloseSvg />
                  </button>
                </div>
              )}
              <div className="hub-composer-row">
                <input
                  className="input sm hub-topic-input"
                  list="hub-topic-options"
                  placeholder={t.hubTopicPlaceholder}
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                />
                <datalist id="hub-topic-options">
                  {topics.map((item) => (
                    <option key={item.topic} value={item.topic} />
                  ))}
                </datalist>
                <select
                  className="select sm hub-kind-select"
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                >
                  {Object.entries(kindOptions).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <input
                  className="input sm hub-to-input"
                  list="hub-agent-options"
                  placeholder={t.hubToAgentPlaceholder}
                  value={toAgent}
                  onChange={(e) => setToAgent(e.target.value)}
                  title={t.hubTypePlaceholder}
                />
                <datalist id="hub-agent-options">
                  {roleOptions.map((r) => (
                    <option key={r} value={r} />
                  ))}
                </datalist>
              </div>
              <div className="hub-composer-row">
                <textarea
                  className="textarea hub-content-input"
                  placeholder={replyTo ? t.hubReplyContentPlaceholder : t.hubContentPlaceholder}
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  rows={2}
                />
                <button
                  type="button"
                  className="btn primary sm hub-send"
                  onClick={() => void submit()}
                  disabled={sending || !topic.trim() || !content.trim()}
                >
                  <SendSvg />
                  <span>{sending ? t.hubPublishingBtn : replyTo ? t.hubReplyAction : t.hubPublishBtn}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  if (embedded) {
    return panelBody;
  }

  return (
    <div className="modal-backdrop">
      {panelBody}
    </div>
  );
}
