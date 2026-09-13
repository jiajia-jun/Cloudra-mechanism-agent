import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api';
import type { Agent, ComputeJob, PendingReminder, Project } from './types';

/* Ops 面板：一屏看清项目在跑什么——agent 树（完整层级）、计算队列、
   残留 reminder。行里的 session_id 全部解析回归属 agent 名。 */

function basename(path: string): string {
  const parts = path.split('/');
  return parts[parts.length - 1] || path;
}

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
  if (secs < 3600) return `${Math.floor(secs / 60)} 分钟后`;
  return `${Math.floor(secs / 3600)} 小时后`;
}

export default function OpsPanel({ project, agents, onError }: {
  project: Project;
  agents: Agent[];
  onError: (e: unknown) => void;
}) {
  const [jobs, setJobs] = useState<ComputeJob[] | null>(null);
  const [reminders, setReminders] = useState<PendingReminder[] | null>(null);

  const agentName = useMemo(() => {
    const m = new Map<string, string>();
    for (const a of agents) m.set(a.id, a.display_name);
    return m;
  }, [agents]);

  const ownerLabel = useCallback(
    (sessionId: string | null): string => {
      if (!sessionId) return '—';
      return agentName.get(sessionId) ?? `${sessionId.slice(0, 12)}…`;
    },
    [agentName],
  );

  const loadJobs = useCallback(async () => {
    setJobs(await api.listComputeJobs(project.id));
  }, [project.id]);

  const loadReminders = useCallback(async () => {
    setReminders(await api.listPendingReminders(project.id));
  }, [project.id]);

  useEffect(() => {
    setJobs(null);
    loadJobs().catch(onError);
    const timer = setInterval(() => loadJobs().catch(() => undefined), 4000);
    return () => clearInterval(timer);
  }, [loadJobs, onError]);

  useEffect(() => {
    setReminders(null);
    loadReminders().catch(onError);
    const timer = setInterval(() => loadReminders().catch(() => undefined), 8000);
    return () => clearInterval(timer);
  }, [loadReminders, onError]);

  const childrenOf = useMemo(() => {
    const m = new Map<string, Agent[]>();
    for (const a of agents) {
      if (!a.parent_session_id) continue;
      const list = m.get(a.parent_session_id) ?? [];
      list.push(a);
      m.set(a.parent_session_id, list);
    }
    return m;
  }, [agents]);

  const rootAgents = useMemo(() => {
    const ids = new Set(agents.map((a) => a.id));
    return agents.filter((a) => !a.parent_session_id || !ids.has(a.parent_session_id));
  }, [agents]);

  const renderAgent = (a: Agent, depth: number): React.ReactNode => (
    <Fragment key={a.id}>
      <div className="ops-agent-row" style={{ paddingLeft: 8 + depth * 18 }}>
        <span className={`state-dot ${a.state}`} />
        <span className="ops-agent-name">{a.display_name}</span>
        <span className="badge role-badge">{a.role_id}</span>
        <span className={`state-badge ${a.state}`}>{a.state}</span>
        {a.current_run && (
          <span className="ops-dim" title={a.current_run.run_id}>
            run {a.current_run.run_id.slice(0, 8)}…
          </span>
        )}
      </div>
      {(childrenOf.get(a.id) ?? []).map((c) => renderAgent(c, depth + 1))}
    </Fragment>
  );

  return (
    <div className="ops-panel">
      <div className="card">
        <div className="card-header-row">
          <span className="card-section-label">Agent 树（{agents.length}）</span>
        </div>
        {agents.length === 0 ? (
          <div className="ops-empty">项目内还没有 agent。</div>
        ) : (
          <div className="ops-agent-tree">{rootAgents.map((a) => renderAgent(a, 0))}</div>
        )}
      </div>

      <div className="card">
        <div className="card-header-row">
          <span className="card-section-label">
            计算队列{jobs ? `（${jobs.length} 个活跃）` : ''}
          </span>
          <button className="btn ghost sm" onClick={() => loadJobs().catch(onError)}>
            刷新
          </button>
        </div>
        {jobs === null ? (
          <div className="ops-empty">加载中…</div>
        ) : jobs.length === 0 ? (
          <div className="ops-empty">没有排队或运行中的计算任务。</div>
        ) : (
          <table className="ops-table">
            <thead>
              <tr>
                <th>Job</th>
                <th>状态</th>
                <th>类型</th>
                <th>输入</th>
                <th>归属 Agent</th>
                <th>调度</th>
                <th>已运行</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} title={j.last_error ?? j.path}>
                  <td>#{j.id}</td>
                  <td>
                    <span className={`state-badge ${j.state}`}>{j.state}</span>
                  </td>
                  <td>{j.jobtype}</td>
                  <td className="ops-mono">{basename(j.path)}</td>
                  <td>{ownerLabel(j.session_id)}</td>
                  <td>{j.scheduler}</td>
                  <td>{elapsed(j.start_timestamp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-header-row">
          <span className="card-section-label">
            残留 Reminder{reminders ? `（${reminders.length}）` : ''}
          </span>
          <button className="btn ghost sm" onClick={() => loadReminders().catch(onError)}>
            刷新
          </button>
        </div>
        {reminders === null ? (
          <div className="ops-empty">加载中…</div>
        ) : reminders.length === 0 ? (
          <div className="ops-empty">没有待触发的 reminder。</div>
        ) : (
          <table className="ops-table">
            <thead>
              <tr>
                <th>#</th>
                <th>归属 Agent</th>
                <th>触发</th>
                <th>内容</th>
              </tr>
            </thead>
            <tbody>
              {reminders.map((r) => (
                <tr key={r.schedule_id}>
                  <td>{r.schedule_id}</td>
                  <td>{ownerLabel(r.session_id)}</td>
                  <td title={r.wake_at}>{wakeCountdown(r.wake_ts)}</td>
                  <td className="ops-reminder-msg" title={r.message}>
                    {r.message.length > 120 ? `${r.message.slice(0, 120)}…` : r.message}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
