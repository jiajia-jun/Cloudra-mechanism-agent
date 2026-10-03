import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api';
import type { Agent, ComputeJob, ComputeNode, PendingReminder, Project } from './types';
import { useI18n, type Translations } from './i18n';

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

export default function OpsPanel({ project, agents, onError }: {
  project: Project;
  agents: Agent[];
  onError: (e: unknown) => void;
}) {
  const { t } = useI18n();
  const [jobs, setJobs] = useState<ComputeJob[] | null>(null);
  const [nodes, setNodes] = useState<ComputeNode[] | null>(null);
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
    try {
      const data = await api.listComputeJobs(project.id);
      setJobs(data);
    } catch (e) {
      onError(e);
    }
  }, [project.id, onError]);

  const loadNodes = useCallback(async () => {
    try {
      const data = await api.computeNodes();
      setNodes(data);
    } catch (e) {
      onError(e);
    }
  }, [onError]);

  const loadReminders = useCallback(async () => {
    try {
      const data = await api.listPendingReminders(project.id);
      setReminders(data);
    } catch (e) {
      onError(e);
    }
  }, [project.id, onError]);

  useEffect(() => {
    void loadJobs();
    const timer = setInterval(() => {
      api.listComputeJobs(project.id).then(setJobs).catch(() => undefined);
    }, 4000);
    return () => clearInterval(timer);
  }, [loadJobs, project.id]);

  useEffect(() => {
    void loadNodes();
    const timer = setInterval(() => {
      api.computeNodes().then(setNodes).catch(() => undefined);
    }, 4000);
    return () => clearInterval(timer);
  }, [loadNodes]);

  useEffect(() => {
    void loadReminders();
    const timer = setInterval(() => {
      api.listPendingReminders(project.id).then(setReminders).catch(() => undefined);
    }, 8000);
    return () => clearInterval(timer);
  }, [loadReminders, project.id]);

  // Overall KPI compute metrics
  const kpis = useMemo(() => {
    const onlineNodes = (nodes ?? []).filter((n) => n.state === 'online').length;
    const totalNodes = nodes?.length ?? 0;
    const totalSlots = (nodes ?? []).reduce((acc, n) => acc + (n.capacity.effective.max_concurrent || 0), 0);
    const usedSlots = (nodes ?? []).reduce((acc, n) => acc + (n.in_flight.slots || 0), 0);
    const totalCpus = (nodes ?? []).reduce((acc, n) => acc + (n.capacity.effective.cpus || 0), 0);
    const usedCpus = (nodes ?? []).reduce((acc, n) => acc + (n.in_flight.cpus || 0), 0);
    const activeJobs = (jobs ?? []).length;
    const runningJobs = (jobs ?? []).filter((j) => j.state === 'running').length;
    const pendingReminders = (reminders ?? []).length;
    const slotUsagePercent = totalSlots > 0 ? Math.round((usedSlots / totalSlots) * 100) : 0;
    return {
      onlineNodes,
      totalNodes,
      totalSlots,
      usedSlots,
      totalCpus,
      usedCpus,
      activeJobs,
      runningJobs,
      pendingReminders,
      slotUsagePercent,
    };
  }, [nodes, jobs, reminders]);

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
              <span className="kpi-number green">{kpis.onlineNodes}</span>
              <span className="kpi-unit">/ {kpis.totalNodes}</span>
            </div>
            <span className="kpi-sub">
              {kpis.onlineNodes > 0 ? t.opsKpiNodesDesc : t.opsNodesNoneOnline}
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
              <span className="kpi-number amber">{kpis.usedSlots}</span>
              <span className="kpi-unit">/ {kpis.totalSlots}</span>
            </div>
            <span className="kpi-sub">
              {t.opsKpiSlotsDesc(Math.max(0, kpis.totalSlots - kpis.usedSlots), kpis.slotUsagePercent)}
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
              <span className="kpi-number cyan">{kpis.usedCpus}</span>
              <span className="kpi-unit">/ {kpis.totalCpus}</span>
            </div>
            <span className="kpi-sub">
              {t.opsKpiCpuDesc(Math.max(0, kpis.totalCpus - kpis.usedCpus))}
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
              onClick={() => loadNodes().catch(onError)}
            >
              <RefreshSvg />
              <span>{t.opsRefreshNodes}</span>
            </button>
          </div>
          <div className="ops-card-body">
            {nodes === null ? (
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
                          <span className={`status-pill ${n.state === 'online' ? 'online' : 'offline'}`}>
                            <span className="status-glow-dot" />
                            {n.state.toUpperCase()}
                          </span>
                        </div>
                      </div>

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
                <span className="empty-title">{t.opsQueueEmptyTitle}</span>
                <span className="empty-desc">{t.opsQueueEmptyDesc}</span>
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
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((j) => (
                      <tr key={j.id} title={j.last_error ?? j.path}>
                        <td className="ops-mono bold">#{j.id}</td>
                        <td>
                          <span className={`state-badge ${j.state}`}>
                            <span className="badge-dot" />
                            {j.state}
                          </span>
                        </td>
                        <td>
                          <span className="jobtype-pill">{j.jobtype}</span>
                        </td>
                        <td className="ops-mono">{j.node_id ?? '—'}</td>
                        <td className="ops-mono filename" title={j.path}>{basename(j.path)}</td>
                        <td>
                          <span className="owner-tag">{ownerLabel(j.session_id)}</span>
                        </td>
                        <td>
                          <span className="badge role-badge">{j.scheduler}</span>
                        </td>
                        <td className="ops-mono">{elapsed(j.start_timestamp)}</td>
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
