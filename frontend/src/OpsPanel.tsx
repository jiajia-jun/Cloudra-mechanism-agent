import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api';
import type { Agent, ComputeJob, ComputeNode, PendingReminder, Project } from './types';
import { useI18n, type Translations } from './i18n';

function basename(path: string): string {
  const parts = path.split('/');
  return parts[parts.length - 1] || path;
}

function elapsed(job: ComputeJob): string {
  const startTs = job.start_timestamp;
  const active = job.state === 'running' || job.state === 'cancel_requested';
  const endTs = active ? Date.now() / 1000 : job.end_timestamp;
  if (!startTs || startTs <= 0 || !endTs || endTs < startTs) return '—';
  const secs = Math.max(0, Math.floor(endTs - startTs));
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m${secs % 60}s`;
  return `${Math.floor(secs / 3600)}h${Math.floor((secs % 3600) / 60)}m`;
}

function gib(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)}G`;
  return `${Math.round(mb)}M`;
}

function wakeCountdown(wakeTs: number, t: Translations): string {
  const secs = Math.floor(wakeTs - Date.now() / 1000);
  if (secs <= 0) return t.opsCountdownDue;
  if (secs < 60) return t.opsCountdownSecs(secs);
  if (secs < 3600) return t.opsCountdownMins(Math.floor(secs / 60));
  return t.opsCountdownHours(Math.floor(secs / 3600));
}

/* Vector SVG Icons (No Emojis) */
function ServerSvg({ className = '' }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
      <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
      <line x1="6" y1="6" x2="6.01" y2="6" />
      <line x1="6" y1="18" x2="6.01" y2="18" />
    </svg>
  );
}

function CpuSvg({ className = '' }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <rect x="9" y="9" width="6" height="6" />
      <path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3" />
    </svg>
  );
}

function SlotsSvg({ className = '' }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  );
}

function LightningSvg({ className = '' }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

function ClockSvg({ className = '' }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function RefreshSvg({ className = '' }: { className?: string }) {
  return (
    <svg className={className} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  );
}

function NodeEnvironmentCheck({ node }: { node: ComputeNode }) {
  const { lang } = useI18n();
  const zh = lang === 'zh';
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; detail: string; time: string } | null>(null);
  async function check() {
    setChecking(true);
    try {
      const response = await api.checkNodeEnvironment(node.node_id);
      setResult({ ...response, time: new Date().toLocaleTimeString() });
    } catch (error) {
      setResult({ ok: false, detail: error instanceof Error ? error.message : String(error), time: new Date().toLocaleTimeString() });
    } finally {
      setChecking(false);
    }
  }
  const scope = [node.connection === 'ssh' ? 'SSH / rsync' : '', node.scheduler === 'slurm' ? 'Slurm CLI' : 'bash'].filter(Boolean).join(' · ');
  return <div className="node-environment-check">
    <button type="button" className="btn outline sm" disabled={checking} onClick={() => void check()}>
      {checking ? (zh ? '检查中…' : 'Checking…') : (zh ? '检查执行环境' : 'Check environment')}
    </button>
    <span className="dim" role="status">
      {result
        ? [result.time, scope, result.ok ? (zh ? '检查通过' : 'Check passed') : result.detail].join(' · ')
        : [scope, zh ? '尚未检查' : 'Unchecked'].join(' · ')}
    </span>
  </div>;
}

export default function OpsPanel({ project, agents, activeJobs, onCancel, cancelling, onError, onOpenResult, refreshVersion }: {
  project: Project;
  agents: Agent[];
  activeJobs: ComputeJob[] | null;
  cancelling: boolean;
  onCancel: (job?: ComputeJob) => void;
  onOpenResult: (jobId: number) => void;
  onError: (e: unknown) => void;
  refreshVersion: number;
}) {
  const { t, lang } = useI18n();
  const [jobs, setJobs] = useState<ComputeJob[] | null>(null);
  const [activeOnly, setActiveOnly] = useState(true);
  const jobsRequestRef = useRef(0);
  const [nodes, setNodes] = useState<ComputeNode[] | null>(null);
  const [nodesError, setNodesError] = useState('');
  const nodesRequestRef = useRef(0);
  const [reminders, setReminders] = useState<PendingReminder[] | null>(null);
  const remindersRequestRef = useRef(0);

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

  const loadJobs = useCallback(async (quiet = false) => {
    const requestVersion = ++jobsRequestRef.current;
    try {
      const data = await api.listComputeJobs(project.id, activeOnly);
      if (requestVersion === jobsRequestRef.current) setJobs(data);
    } catch (e) {
      if (!quiet && requestVersion === jobsRequestRef.current) onError(e);
    }
  }, [project.id, activeOnly, onError]);

  const loadNodes = useCallback(async () => {
    const revision = ++nodesRequestRef.current;
    try {
      const data = await api.computeNodes();
      if (revision !== nodesRequestRef.current) return;
      setNodes(data);
      setNodesError('');
    } catch (error) {
      if (revision !== nodesRequestRef.current) return;
      setNodes(null);
      setNodesError(error instanceof Error ? error.message : String(error));
    }
  }, []);

  const loadReminders = useCallback(async () => {
    const requestVersion = ++remindersRequestRef.current;
    try {
      const data = await api.listPendingReminders(project.id);
      if (requestVersion === remindersRequestRef.current) setReminders(data);
    } catch (e) {
      if (requestVersion === remindersRequestRef.current) throw e;
    }
  }, [project.id]);

  useEffect(() => {
    void loadJobs();
    const timer = setInterval(() => { void loadJobs(true); }, 4000);
    return () => {
      ++jobsRequestRef.current;
      clearInterval(timer);
    };
  }, [loadJobs, project.id, refreshVersion]);

  useEffect(() => {
    void loadNodes();
    const timer = setInterval(() => { void loadNodes(); }, 4000);
    return () => {
      ++nodesRequestRef.current;
      clearInterval(timer);
    };
  }, [loadNodes, refreshVersion]);

  useEffect(() => {
    setReminders(null);
    void loadReminders().catch(onError);
    const timer = setInterval(() => {
      void loadReminders().catch(() => undefined);
    }, 8000);
    return () => {
      ++remindersRequestRef.current;
      clearInterval(timer);
    };
  }, [loadReminders, onError]);

  // Overall KPI compute metrics
  const kpis = useMemo(() => {
    const totalNodes = nodes?.length ?? 0;
    const totalSlots = (nodes ?? []).reduce((acc, n) => acc + (n.capacity.effective.max_concurrent || 0), 0);
    const usedSlots = (nodes ?? []).reduce((acc, n) => acc + (n.in_flight.slots || 0), 0);
    const totalCpus = (nodes ?? []).reduce((acc, n) => acc + (n.capacity.effective.cpus || 0), 0);
    const usedCpus = (nodes ?? []).reduce((acc, n) => acc + (n.in_flight.cpus || 0), 0);
    const currentJobs = (activeOnly ? jobs : activeJobs) ?? [];
    const runningJobs = currentJobs.filter((j) => j.state === 'running').length;
    const pendingReminders = (reminders ?? []).length;
    const slotUsagePercent = totalSlots > 0 ? Math.round((usedSlots / totalSlots) * 100) : 0;
    return {
      totalNodes,
      totalSlots,
      usedSlots,
      totalCpus,
      usedCpus,
      activeJobs: currentJobs.length,
      runningJobs,
      pendingReminders,
      slotUsagePercent,
    };
  }, [nodes, jobs, activeJobs, activeOnly, reminders]);

  return (
    <div className="ops-dashboard-root">
      {/* 1. Top Level Compute KPI Strip (Vector SVGs) */}
      <div className="ops-kpi-strip">
        <div className="ops-kpi-card">
          <div className="kpi-icon-wrap emerald">
            <ServerSvg />
          </div>
          <div className="kpi-content">
            <span className="kpi-label">{t.opsKpiNodes}</span>
            <div className="kpi-val-row">
              <span className="kpi-number">{nodes ? kpis.totalNodes : '—'}</span>
            </div>
            <span className="kpi-sub">
              {nodesError ? (lang === 'zh' ? '读取失败' : 'Read failed') : t.opsKpiNodesDesc}
            </span>
          </div>
        </div>

        <div className="ops-kpi-card">
          <div className="kpi-icon-wrap amber">
            <SlotsSvg />
          </div>
          <div className="kpi-content">
            <span className="kpi-label">{t.opsKpiSlots}</span>
            <div className="kpi-val-row">
              <span className="kpi-number amber">{nodes ? kpis.usedSlots : '—'}</span>
              <span className="kpi-unit">/ {nodes ? kpis.totalSlots : '—'}</span>
            </div>
            <span className="kpi-sub">
              {nodes ? t.opsKpiSlotsDesc(Math.max(0, kpis.totalSlots - kpis.usedSlots), kpis.slotUsagePercent) : '—'}
            </span>
          </div>
        </div>

        <div className="ops-kpi-card">
          <div className="kpi-icon-wrap cyan">
            <CpuSvg />
          </div>
          <div className="kpi-content">
            <span className="kpi-label">{t.opsKpiCpu}</span>
            <div className="kpi-val-row">
              <span className="kpi-number cyan">{nodes ? kpis.usedCpus : '—'}</span>
              <span className="kpi-unit">/ {nodes ? kpis.totalCpus : '—'}</span>
            </div>
            <span className="kpi-sub">
              {nodes ? t.opsKpiCpuDesc(Math.max(0, kpis.totalCpus - kpis.usedCpus)) : '—'}
            </span>
          </div>
        </div>

        <div className="ops-kpi-card">
          <div className="kpi-icon-wrap purple">
            <LightningSvg />
          </div>
          <div className="kpi-content">
            <span className="kpi-label">{t.opsKpiTasks}</span>
            <div className="kpi-val-row">
              <span className="kpi-number purple">{kpis.activeJobs}</span>
              <span className="kpi-unit">{t.opsKpiTasksActive(kpis.activeJobs)}</span>
            </div>
            <span className="kpi-sub">
              {t.opsKpiTasksReminders(kpis.pendingReminders)}
            </span>
          </div>
        </div>
      </div>

      {/* 2. Main Compute Infrastructure Stack */}
      <div className="ops-compute-stack">
        {/* Card 1: Node Capacity Pools */}
        <div className="ops-card">
          <div className="ops-card-header">
            <div className="card-header-left">
              <span className="header-svg-wrap icon-emerald">
                <ServerSvg />
              </span>
              <span className="header-title">{t.opsPoolTitle}</span>
              <span className="badge sm">{nodes ? t.opsPoolNodesCount(nodes.length) : '…'}</span>
            </div>
            <button
              type="button"
              className="btn ghost sm refresh-btn"
              onClick={() => void loadNodes()}
            >
              <RefreshSvg />
              <span>{t.opsRefreshNodes}</span>
            </button>
          </div>
          <div className="ops-card-body">
            {nodesError ? (
              <p role="alert">{lang === 'zh' ? '无法读取计算节点配置' : 'Unable to read compute node configuration'} · {nodesError}</p>
            ) : nodes === null ? (
              <div className="ops-empty-hint">{t.opsLoadingNodes}</div>
            ) : nodes.length === 0 ? (
              <div className="ops-empty-state small">
                <span className="empty-svg-wrap">
                  <ServerSvg />
                </span>
                <span className="empty-title">{t.opsNodesNoneRegistered}</span>
              </div>
            ) : (
              <div className="node-capacity-grid">
                {nodes.map((n) => {
                  const cap = n.capacity.effective;
                  const used = n.in_flight;
                  const free = n.free;
                  const slotPercent = cap.max_concurrent > 0 ? Math.min(100, Math.round((used.slots / cap.max_concurrent) * 100)) : 0;
                  const cpuPercent = cap.cpus > 0 ? Math.min(100, Math.round((used.cpus / cap.cpus) * 100)) : 0;
                  const memPercent = cap.memory_mb > 0 ? Math.min(100, Math.round((used.memory_mb / cap.memory_mb) * 100)) : 0;
                  return (
                    <div className="node-item-card" key={n.node_id}>
                      <div className="node-item-header">
                        <div className="node-item-left">
                          <span className="node-type-svg">
                            <ServerSvg />
                          </span>
                          <span className="node-name">{n.display_name}</span>
                          <span className="badge role-badge">{n.scheduler}</span>
                          {n.connection === 'ssh' && (
                            <span className="badge role-badge ssh" title={n.remote ?? undefined}>
                              SSH {n.remote ? `· ${n.remote}` : ''}
                            </span>
                          )}
                        </div>
                        <div className="node-item-right">
                          <span className="badge role-badge">
                            {lang === 'zh'
                              ? (n.state === 'online' ? '登记为在线' : n.state === 'offline' ? '登记为离线' : `登记状态 · ${n.state}`)
                              : `Registered as ${n.state}`}
                          </span>
                        </div>
                      </div>

                      <NodeEnvironmentCheck key={JSON.stringify([n.node_id, n.connection, n.remote, n.scheduler])} node={n} />
                      {/* Three Gauges / Resource Bars */}
                      <div className="node-metrics-stack">
                        {/* 1. Concurrent Slots */}
                        <div className="node-metric-block">
                          <div className="metric-header-row">
                            <span className="metric-name">{t.opsMetricSlots}</span>
                            <span className="metric-values">
                              <strong>{used.slots}</strong> / {cap.max_concurrent} {t.opsSlotsFree(free.slots)}
                            </span>
                          </div>
                          <div className="metric-progress-track">
                            <div
                              className={`metric-progress-fill ${slotPercent >= 90 ? 'danger' : slotPercent >= 70 ? 'warning' : 'normal'}`}
                              style={{ width: `${slotPercent}%` }}
                            />
                          </div>
                        </div>

                        {/* 2. CPU Cores */}
                        <div className="node-metric-block">
                          <div className="metric-header-row">
                            <span className="metric-name">{t.opsMetricCpus}</span>
                            <span className="metric-values">
                              <strong>{used.cpus}</strong> / {cap.cpus} {t.opsCpusFree(free.cpus)}
                            </span>
                          </div>
                          <div className="metric-progress-track">
                            <div
                              className={`metric-progress-fill cyan ${cpuPercent >= 90 ? 'danger' : cpuPercent >= 70 ? 'warning' : 'normal'}`}
                              style={{ width: `${cpuPercent}%` }}
                            />
                          </div>
                        </div>

                        {/* 3. Memory */}
                        <div className="node-metric-block">
                          <div className="metric-header-row">
                            <span className="metric-name">{t.opsMetricMem}</span>
                            <span className="metric-values">
                              <strong>{gib(used.memory_mb)}</strong> / {gib(cap.memory_mb)} {t.opsMemFree(gib(free.memory_mb))}
                            </span>
                          </div>
                          <div className="metric-progress-track">
                            <div
                              className={`metric-progress-fill purple ${memPercent >= 90 ? 'danger' : memPercent >= 70 ? 'warning' : 'normal'}`}
                              style={{ width: `${memPercent}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Card 2: Quantum Chemistry Job Queue */}
        <div className="ops-card">
          <div className="ops-card-header">
            <div className="card-header-left">
              <span className="header-svg-wrap icon-amber">
                <LightningSvg />
              </span>
              <span className="header-title">{t.opsQueueTitle}</span>
              <span className="badge sm">{jobs ? t.opsQueueCount(jobs.length) : '…'}</span>
            </div>
            <div className="btn-group" role="group" aria-label={lang === 'zh' ? '作业范围' : 'Job range'}>
              {([true, false] as const).map(active => <button key={String(active)} type="button"
                className={`btn outline sm ${activeOnly === active ? 'active' : ''}`} aria-pressed={activeOnly === active}
                onClick={() => { if (active !== activeOnly) { ++jobsRequestRef.current; setJobs(null); setActiveOnly(active); } }}>
                {active ? (lang === 'zh' ? '活动作业' : 'Active jobs') : (lang === 'zh' ? '最近 100 条' : 'Latest 100')}
              </button>)}
            </div>
            <button type="button" className="btn ghost sm" data-testid="cancel-all-compute" disabled={cancelling} onClick={()=>onCancel()}>
              {cancelling ? (lang === 'zh' ? '请求中…' : 'Requesting…') : (lang === 'zh' ? '取消所有项目的计算' : 'Cancel compute across all projects')}
            </button>
            <button
              type="button"
              className="btn ghost sm refresh-btn"
              onClick={() => loadJobs().catch(onError)}
            >
              <RefreshSvg />
              <span>{t.opsRefreshQueue}</span>
            </button>
          </div>
          <div className="ops-card-body table-body">
            {jobs === null ? (
              <div className="ops-empty-hint">{t.opsLoadingJobs}</div>
            ) : jobs.length === 0 ? (
              <div className="ops-empty-state">
                <span className="empty-svg-wrap large amber">
                  <LightningSvg />
                </span>
                <span className="empty-title">{activeOnly ? t.opsQueueEmptyTitle : (lang === 'zh' ? '此项目暂无计算作业记录' : 'No recorded jobs for this project')}</span>
                {activeOnly && <span className="empty-desc">{t.opsQueueEmptyDesc}</span>}
              </div>
            ) : (
              <div className="ops-table-wrap">
                <table className="ops-table">
                  <thead>
                    <tr>
                      <th>{t.opsTableJobId}</th>
                      <th>{t.opsTableState}</th>
                      <th>{t.opsTableType}</th>
                      <th>{t.opsTableNode}</th>
                      <th>{t.opsTableFile}</th>
                      <th>{t.opsTableOwner}</th>
                      <th>{t.opsTableScheduler}</th>
                      <th>{t.opsTableElapsed}</th>
                      <th>{lang === 'zh' ? '操作' : 'Actions'}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((j) => (
                      <tr key={j.id} title={j.last_error ?? j.path}>
                        <td className="ops-mono bold">#{j.id}</td>
                        <td>
                          <span className={`state-badge ${j.state}`}>
                            <span className="badge-dot" />
                            {j.state === 'cancel_requested' ? (lang === 'zh' ? '取消中' : 'Stopping') : j.state}
                          </span>
                        </td>
                        <td>
                          <span className="jobtype-pill">{j.jobtype}</span>
                        </td>
                        <td className="ops-mono">{j.node_id ?? '—'}</td>
                        <td className="ops-mono filename" title={j.path}>{basename(j.path)}{j.last_error && j.state === 'failed' && <div>{j.last_error}</div>}</td>
                        <td>
                          <span className="owner-tag">{ownerLabel(j.session_id)}</span>
                        </td>
                        <td>
                          <span className="badge role-badge">{j.scheduler}</span>
                        </td>
                        <td className="ops-mono">{elapsed(j)}</td>
                        <td>{(j.state === 'ready' || j.state === 'running') && <button type="button" className="btn outline sm" disabled={cancelling}
                          aria-label={lang === 'zh' ? `取消作业 #${j.id}` : `Cancel job #${j.id}`} onClick={()=>onCancel(j)}>
                          {lang === 'zh' ? '取消' : 'Cancel'}
                        </button>}{['done','failed','cancelled'].includes(j.state) && <button className="btn outline sm" type="button"
                          aria-label={lang === 'zh' ? `查看作业 #${j.id} 的结果` : `View results for job #${j.id}`}
                          onClick={()=>onOpenResult(j.id)}>{lang === 'zh' ? '查看结果' : 'View results'}</button>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Card 3: Pending Reminders & Scheduled Heartbeats */}
        <div className="ops-card">
          <div className="ops-card-header">
            <div className="card-header-left">
              <span className="header-svg-wrap icon-purple">
                <ClockSvg />
              </span>
              <span className="header-title">{t.opsRemindersTitle}</span>
              <span className="badge sm">{reminders ? t.opsRemindersCount(reminders.length) : '…'}</span>
            </div>
            <button
              type="button"
              className="btn ghost sm refresh-btn"
              onClick={() => loadReminders().catch(onError)}
            >
              <RefreshSvg />
              <span>{t.opsRefreshReminders}</span>
            </button>
          </div>
          <div className="ops-card-body table-body">
            {reminders === null ? (
              <div className="ops-empty-hint">{t.opsLoadingReminders}</div>
            ) : reminders.length === 0 ? (
              <div className="ops-empty-state small">
                <span className="empty-svg-wrap purple">
                  <ClockSvg />
                </span>
                <span className="empty-title">{t.opsRemindersEmptyTitle}</span>
                <span className="empty-desc">{t.opsRemindersEmptyDesc}</span>
              </div>
            ) : (
              <div className="ops-table-wrap">
                <table className="ops-table">
                  <thead>
                    <tr>
                      <th>{t.opsTableScheduleId}</th>
                      <th>{t.opsTableOwner}</th>
                      <th>{t.opsTableCountdown}</th>
                      <th>{t.opsTableMessage}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reminders.map((r) => (
                      <tr key={r.schedule_id}>
                        <td className="ops-mono bold">{r.schedule_id}</td>
                        <td>
                          <span className="owner-tag">{ownerLabel(r.session_id)}</span>
                        </td>
                        <td>
                          <span className="countdown-pill" title={r.wake_at}>
                            <ClockSvg />
                            <span>{wakeCountdown(r.wake_ts, t)}</span>
                          </span>
                        </td>
                        <td className="ops-reminder-msg" title={r.message}>
                          {r.message}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
