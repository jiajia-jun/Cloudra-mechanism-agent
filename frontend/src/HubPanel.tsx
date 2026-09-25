/**
 * HubPanel — AgentHub 论坛：项目内 agent 帖子的完整可视化 + 用户发帖。
 *
 * 布局仿网页论坛：左侧话题列表（按最新活动排序），右侧帖子流；进入一个
 * 话题后按 parent_id 缩进成线程，每帖可回复。底部是发帖框（可新开话题、
 * 选 kind、@ 具体 agent）。数据来自 routers/hub.py：初始 GET 投影，之后
 * 用项目 SSE 流增量追加 hub.posted（按 id 去重）。
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, streamProject } from './api';
import type { Agent, HubPost, Project } from './types';

interface HubPanelProps {
  projects: Project[];
  initialProjectId: string | null;
  onClose: () => void;
  onToast: (kind: 'ok' | 'error' | 'info', text: string) => void;
}

const KIND_LABELS: Record<string, string> = {
  finding: '发现',
  question: '提问',
  answer: '回答',
  broadcast: '广播',
  message: '定向',
};

function fmtTs(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function postFromEvent(e: { event_id: string; seq: number; created_at: string; data: Record<string, unknown> }): HubPost {
  return {
    id: e.event_id,
    seq: e.seq,
    created_at: e.created_at,
    topic: String(e.data.topic ?? ''),
    kind: String(e.data.kind ?? 'finding'),
    author_agent: String(e.data.author_agent ?? ''),
    author_session: (e.data.author_session as string | null) ?? null,
    to_agent: (e.data.to_agent as string | null) ?? null,
    parent_id: (e.data.parent_id as string | null) ?? null,
    content: String(e.data.content ?? ''),
  };
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
  const isUser = post.author_agent === 'user';
  return (
    <div className={`hub-post ${depth > 0 ? `hub-depth-${Math.min(depth, 4)}` : ''}`}>
      <div className="hub-post-head">
        <span className={`hub-author ${isUser ? 'user' : ''}`}>{isUser ? '👤 用户' : post.author_agent}</span>
        <span className={`hub-kind hub-kind-${post.kind}`}>{KIND_LABELS[post.kind] ?? post.kind}</span>
        {post.to_agent && <span className="hub-to">→ @{post.to_agent}</span>}
        <span className="hub-time">{fmtTs(post.created_at)}</span>
        <button type="button" className="btn ghost sm hub-reply-btn" onClick={() => onReply(post)}>
          回复
        </button>
      </div>
      <div className="hub-post-content">{post.content}</div>
    </div>
  );
}

export default function HubPanel({ projects, initialProjectId, onClose, onToast }: HubPanelProps) {
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

  const load = useCallback(
    async (pid: string) => {
      setLoading(true);
      try {
        const [res, agentRows] = await Promise.all([api.hubPosts(pid), api.listAgents(pid)]);
        setPosts(res.posts);
        setAgents(agentRows);
        setLoadedPid(pid);
      } catch (e) {
        onToast('error', e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [onToast],
  );

  useEffect(() => {
    setPosts([]);
    setAgents([]);
    setLoadedPid(null);
    setSelectedTopic(null);
    setReplyTo(null);
    if (projectId) void load(projectId);
  }, [projectId, load]);

  // Live tail: open the project SSE stream once the initial projection is in,
  // starting after the loaded high-watermark; append new hub.posted by id.
  const maxSeqRef = useRef(0);
  maxSeqRef.current = posts.reduce((m, p) => Math.max(m, p.seq), 0);
  useEffect(() => {
    if (!projectId || loadedPid !== projectId) return;
    const source = streamProject(projectId, maxSeqRef.current, {
      onEvent: (e) => {
        if (e.type !== 'hub.posted') return;
        const post = postFromEvent(e);
        setPosts((prev) => (prev.some((p) => p.id === post.id) ? prev : [...prev, post]));
      },
    });
    return () => source.close();
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

  const renderThread = (post: HubPost, depth: number): ReactNode => (
    <div key={post.id}>
      <PostCard post={post} depth={depth} onReply={startReply} />
      {(childrenOf.get(post.id) ?? []).map((child) => renderThread(child, depth + 1))}
    </div>
  );

  const startReply = (post: HubPost) => {
    setReplyTo(post);
    setSelectedTopic(post.topic);
    setTopic(post.topic);
  };

  const selectTopic = (t: string | null) => {
    setSelectedTopic(t);
    setReplyTo(null);
    if (t) setTopic(t);
  };

  const submit = async () => {
    if (!projectId || sending) return;
    if (!topic.trim() || !content.trim()) {
      onToast('error', '话题和内容都不能为空');
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
      setPosts((prev) => (prev.some((p) => p.id === res.post.id) ? prev : [...prev, res.post]));
      setSelectedTopic(res.post.topic);
      setContent('');
      setToAgent('');
      setReplyTo(null);
      onToast('ok', res.notified_count > 0 ? `已发布，通知了 ${res.notified_count} 个会话` : '已发布');
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

  return (
    <div className="modal-backdrop">
      <div className="modal hub-modal">
        <div className="hub-head">
          <div className="hub-head-left">
            <span className="hub-title">AgentHub 论坛</span>
            <select
              className="select hub-project-select"
              value={projectId ?? ''}
              onChange={(e) => setProjectId(e.target.value || null)}
              title="选择项目（论坛按项目隔离）"
            >
              {!projectId && <option value="">选择项目…</option>}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <span className="hub-count">{posts.length} 帖</span>
          </div>
          <div className="hub-head-right">
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => projectId && void load(projectId)}
              disabled={!projectId || loading}
              title="重新加载"
            >
              ↻ 刷新
            </button>
            <button className="btn ghost sm" type="button" onClick={onClose} title="关闭 (Esc)">
              ✕
            </button>
          </div>
        </div>

        {!projectId ? (
          <div className="hub-empty">先创建一个项目，AgentHub 论坛是按项目隔离的。</div>
        ) : (
          <div className="hub-body">
            <div className="hub-topics">
              <button
                type="button"
                className={`hub-topic-row ${selectedTopic === null ? 'active' : ''}`}
                onClick={() => selectTopic(null)}
              >
                <span className="hub-topic-name">📋 最新动态</span>
                <span className="hub-topic-count">{posts.length}</span>
              </button>
              {topics.map((t) => (
                <button
                  key={t.topic}
                  type="button"
                  className={`hub-topic-row ${selectedTopic === t.topic ? 'active' : ''}`}
                  onClick={() => selectTopic(t.topic)}
                  title={t.topic}
                >
                  <span className="hub-topic-name"># {t.topic}</span>
                  <span className="hub-topic-preview">{t.preview}</span>
                  <span className="hub-topic-meta">
                    <span className="hub-topic-count">{t.count} 帖</span>
                    <span>{fmtTs(t.latestAt)}</span>
                  </span>
                </button>
              ))}
              {topics.length === 0 && !loading && <div className="hub-topics-empty">还没有话题</div>}
            </div>

            <div className="hub-main">
              <div className="hub-posts">
                {loading && posts.length === 0 && <div className="hub-empty">加载中…</div>}
                {!loading && posts.length === 0 && (
                  <div className="hub-empty">论坛还没有帖子 — 用下面的发帖框发第一帖，agent 也能看到。</div>
                )}
                {selectedTopic === null
                  ? latestPosts.map((p) => (
                      <div key={p.id}>
                        <div className="hub-latest-topic" onClick={() => selectTopic(p.topic)}>
                          # {p.topic}
                        </div>
                        <PostCard post={p} depth={0} onReply={startReply} />
                      </div>
                    ))
                  : roots.map((p) => renderThread(p, 0))}
              </div>

              <div className="hub-composer">
                {replyTo && (
                  <div className="hub-reply-chip">
                    回复 {replyTo.author_agent === 'user' ? '用户' : replyTo.author_agent} 的帖子
                    <button type="button" className="hub-reply-cancel" onClick={() => setReplyTo(null)} title="取消回复">
                      ✕
                    </button>
                  </div>
                )}
                <div className="hub-composer-row">
                  <input
                    className="input hub-topic-input"
                    list="hub-topic-options"
                    placeholder="话题（可新开）"
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                  />
                  <datalist id="hub-topic-options">
                    {topics.map((t) => (
                      <option key={t.topic} value={t.topic} />
                    ))}
                  </datalist>
                  <select className="select hub-kind-select" value={kind} onChange={(e) => setKind(e.target.value)} title="帖子类型">
                    {Object.entries(KIND_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <input
                    className="input hub-to-input"
                    list="hub-agent-options"
                    placeholder="@ 通知谁（可选）"
                    value={toAgent}
                    onChange={(e) => setToAgent(e.target.value)}
                    title="role 名（如 small_mol）或会话 ID；留空不通知任何人，广播类型通知全部会话"
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
                    placeholder={replyTo ? '写下你的回复…' : '写下帖子内容…（帖子对项目内所有 agent 公开）'}
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
                    {sending ? '发布中…' : replyTo ? '回复' : '发布'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
