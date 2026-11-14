import { useState, useEffect, useMemo } from 'react';
import { api } from './api';
import type { Project, Agent, ComputeJob } from './types';
import { useI18n, type Translations } from './i18n';

export type ConsoleTab = 'overview' | 'research' | 'compute' | 'audit' | 'telemetry' | 'hub';

function NetworkSvg() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="3" width="6" height="4" rx="1" />
      <rect x="2" y="17" width="6" height="4" rx="1" />
      <rect x="16" y="17" width="6" height="4" rx="1" />
      <path d="M12 7v4" />
      <path d="M5 14h14" />
      <path d="M5 14v3" />
      <path d="M12 11v6" />
      <path d="M19 14v3" />
    </svg>
  );
}

function CompassSvg() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
    </svg>
  );
}

function ShieldCheckSvg() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <polyline points="9 12 11 14 15 10" />
    </svg>
  );
}

function AtomSvg() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="2" />
      <ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(30 12 12)" />
      <ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(-30 12 12)" />
    </svg>
  );
}

function BotSvg() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="8" width="16" height="12" rx="2" />
      <line x1="12" y1="4" x2="12" y2="8" />
      <circle cx="9" cy="13" r="1.2" fill="currentColor" />
      <circle cx="15" cy="13" r="1.2" fill="currentColor" />
      <line x1="9" y1="16" x2="15" y2="16" />
    </svg>
  );
}

function ChatBubbleSvg() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function getRoleMeta(roleId: string, t: Translations) {
  const lower = roleId.toLowerCase();
  if (lower.includes('coordinator') || lower.includes('lead')) {
    return {
      title: t.roleCoordinatorTitle,
      desc: t.roleCoordinatorDesc,
      icon: <CompassSvg />,
      colorClass: 'role-coordinator',
    };
  }
  if (lower.includes('supervisor') || lower.includes('guard') || lower.includes('review')) {
    return {
      title: t.roleSupervisorTitle,
      desc: t.roleSupervisorDesc,
      icon: <ShieldCheckSvg />,
      colorClass: 'role-supervisor',
    };
  }
  if (
    lower.includes('compute') ||
    lower.includes('calc') ||
    lower.includes('qc') ||
    lower.includes('orca') ||
    lower.includes('gaussian') ||
    lower.includes('crest') ||
    lower.includes('xtb')
  ) {
    return {
      title: t.roleComputeTitle,
      desc: t.roleComputeDesc,
      icon: <AtomSvg />,
      colorClass: 'role-compute',
    };
  }
  return {
    title: t.roleWorkerTitle(roleId),
    desc: t.roleWorkerDesc,
    icon: <BotSvg />,
    colorClass: 'role-worker',
  };
}

function getStateMeta(state: string, t: Translations) {
  switch (state) {
    case 'running':
      return { label: t.stateRunning, dotClass: 'running' };
    case 'waiting_for_input':
    case 'waiting_for_dependents':
    case 'waiting_for_message':
      return { label: t.stateWaiting, dotClass: 'waiting' };
    case 'idle':
      return { label: t.stateIdle, dotClass: 'idle' };
    case 'errored':
      return { label: t.stateErrored, dotClass: 'errored' };
    case 'finished':
      return { label: t.stateFinished, dotClass: 'finished' };
    default:
      return { label: state, dotClass: 'neutral' };
  }
}

export interface ConsoleIndexPageProps {
  project: Project;
  agents: Agent[];
  activeAgent: Agent | null;
  sidebarJobs: ComputeJob[] | null;
  onNavigate: (tab: ConsoleTab) => void;
  onOpenProjectSettings: () => void;
  onContinueDialogue: () => void;
  onOpenWorkbench: () => void;
  onSelectAgent?: (agentId: string) => void;
  onOpenDialogue?: (agentId: string) => void;
  onError: (err: unknown) => void;
  onToast: (text: string, kind?: 'info' | 'warn' | 'error') => void;
}

export function ConsoleIndexPage({
  project,
  agents,
  activeAgent,
  sidebarJobs,
  onNavigate,
  onOpenProjectSettings,
  onContinueDialogue,
  onOpenWorkbench,
  onSelectAgent,
  onOpenDialogue,
  onError,
  onToast,
}: ConsoleIndexPageProps) {
  const { t, lang } = useI18n();

  const [goal, setGoal] = useState<{
    objective: string;
    completion_criteria: string;
    current_focus: string;
  } | null>(null);
  const [editingGoal, setEditingGoal] = useState(false);
  const [goalDraft, setGoalDraft] = useState({
    objective: '',
    completion_criteria: '',
    current_focus: '',
  });
  const [savingGoal, setSavingGoal] = useState(false);
  const [hubPostsCount, setHubPostsCount] = useState<number | null>(null);
  const [dagSummary, setDagSummary] = useState<{
    mode: string;
    nodeCount: number;
    edgeCount: number;
    accepted: boolean;
  } | null>(null);

  const activeJobs = sidebarJobs ? sidebarJobs.filter((j) => ['running', 'queued', 'ready', 'cancel_requested'].includes(j.state)) : [];
  const stoppingJobs = activeJobs.filter((j) => j.state === 'cancel_requested');
  const dagModeActive =
    project.settings.orchestration_mode === 'dag_guided' ||
    project.settings.defaults?.orchestration_mode === 'dag_guided' ||
    dagSummary?.mode === 'dag_guided' ||
    dagSummary?.mode === 'dag_record';

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

  const renderAgentNode = (agent: Agent, depth: number): React.ReactNode => {
    const roleMeta = getRoleMeta(agent.role_id, t);
    const stateMeta = getStateMeta(agent.state, t);
    const isActive = activeAgent?.id === agent.id;
    const children = childrenOf.get(agent.id) ?? [];

    return (
      <div key={agent.id} className="portal-agent-node-wrap">
        <div
          className={`portal-agent-card ${roleMeta.colorClass} ${isActive ? 'is-active' : ''}`}
          style={{ marginLeft: depth > 0 ? `${depth * 28}px` : undefined }}
          onClick={() => onSelectAgent?.(agent.id)}
        >
          {depth > 0 && <span className="tree-branch-guide" />}
          <div className="agent-card-main">
            <div className={`agent-role-icon-box ${roleMeta.colorClass}`}>
              {roleMeta.icon}
            </div>
            <div className="agent-details">
              <div className="agent-title-row">
                <span className="agent-name">{agent.display_name}</span>
                <span className={`agent-role-pill ${roleMeta.colorClass}`}>{agent.role_id}</span>
                {isActive && <span className="agent-active-tag">{t.currentChatBadge}</span>}
              </div>
              {agent.current_task && (
                <div className="agent-task-banner" title={agent.current_task}>
                  <span className="task-banner-pulse" />
                  <span className="task-banner-label">{t.currentTaskLabel}:</span>
                  <span className="task-banner-text">{agent.current_task}</span>
                </div>
              )}
              <div className="agent-desc-row">
                <span className="agent-desc-text">{roleMeta.desc}</span>
                <span className="agent-id-tag" title={agent.id}>
                  ID: {agent.id.slice(0, 8)}…
                </span>
              </div>
            </div>
          </div>

          <div className="agent-card-actions">
            <div className="agent-status-box">
              <span className={`state-badge ${stateMeta.dotClass}`}>
                <span className="badge-dot" />
                <span>{stateMeta.label}</span>
              </span>
              {agent.current_run && (
                <span className="agent-run-badge" title={agent.current_run.run_id}>
                  run #{agent.current_run.run_id.slice(0, 7)}
                </span>
              )}
            </div>
            <div className="agent-btn-group">
              {onOpenDialogue && (
                <button
                  type="button"
                  className="btn ghost sm agent-open-chat-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenDialogue(agent.id);
                  }}
                  title={t.openChat}
                >
                  <ChatBubbleSvg />
                  <span>{t.openChat}</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {children.length > 0 && (
          <div className="portal-agent-sub-tree">
            {children.map((c) => renderAgentNode(c, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  // Load Goal
  useEffect(() => {
    if (!activeAgent) {
      setGoal(null);
      return;
    }
    api.getGoal(activeAgent.id)
      .then((res) => {
        if (res.goal) {
          setGoal(res.goal);
          setGoalDraft(res.goal);
        } else {
          setGoal(null);
        }
      })
      .catch(() => setGoal(null));
  }, [activeAgent?.id]);

  // Load Hub Posts Count
  useEffect(() => {
    api.hubPosts(project.id)
      .then((res) => {
        setHubPostsCount(Array.isArray(res.posts) ? res.posts.length : 0);
      })
      .catch(() => setHubPostsCount(null));
  }, [project.id]);

  // Load DAG Summary
  useEffect(() => {
    api.dagDelivery(project.id)
      .then((res) => {
        const g = res.graph as { nodes?: unknown[]; edges?: unknown[] } | null;
        setDagSummary({
          mode: res.mode || 'standard',
          nodeCount: g?.nodes?.length ?? 0,
          edgeCount: g?.edges?.length ?? 0,
          accepted: Boolean(g),
        });
      })
      .catch(() => setDagSummary(null));
  }, [project.id]);

  const handleSaveGoal = async () => {
    if (!activeAgent) return;
    setSavingGoal(true);
    try {
      const res = await api.setGoal(activeAgent.id, goalDraft);
      setGoal(res.goal);
      setEditingGoal(false);
      onToast(t.goalSavedToast, 'info');
    } catch (err) {
      onError(err);
    } finally {
      setSavingGoal(false);
    }
  };

  return (
    <div className="console-index-page">
      {/* Top Section: Project Overview & Scientific Goal */}
      <section className="portal-overview-card">
        <div className="portal-overview-header">
          <div className="portal-title-block">
            <div className="portal-project-eyebrow">
              <span className="mono-label">{t.projectWorkbench}</span>
              <span className="eyebrow-sep">/</span>
              <span className="mono-path" title={project.workspace_dir || undefined}>
                {project.workspace_dir || t.defaultWorkspace}
              </span>
            </div>
            <h1 className="portal-project-name">{project.name}</h1>
          </div>

          <div className="portal-tags-group">
            <span className={`portal-tag ${dagModeActive ? 'active' : 'neutral'}`}>
              <span className="tag-dot" />
              {dagModeActive ? t.dagModeActive : t.dagModeInactive}
            </span>
            <span className={`portal-tag ${project.settings.defaults?.yolo ? 'yolo' : 'safe'}`}>
              {project.settings.defaults?.yolo ? t.yoloActive : t.safeActive}
            </span>
            <span className="portal-tag neutral">
              {t.agentCount(agents.length)}
            </span>
            <button
              type="button"
              className="btn outline sm portal-setting-shortcut"
              onClick={onOpenProjectSettings}
              title={t.projectRunConfigTip}
            >
              {t.projectRunConfig}
            </button>
          </div>
        </div>

        <nav className="portal-task-actions" aria-label={lang === 'zh' ? '研究操作' : 'Research actions'}>
          <button className="btn primary" onClick={onContinueDialogue}>{lang === 'zh' ? '继续研究对话' : 'Continue research conversation'}</button>
          <button className="btn outline" onClick={onOpenWorkbench}>{lang === 'zh' ? '打开分子工作台' : 'Open molecular workbench'}</button>
          <button className="btn outline" onClick={() => onNavigate('research')}>{lang === 'zh' ? '查看研究结果' : 'View research results'}</button>
          <button className="btn outline" onClick={() => onNavigate('compute')}>{lang === 'zh' ? '查看计算任务' : 'View compute jobs'}{activeJobs.length > 0 && (lang === 'zh' ? `（${activeJobs.length} 个进行中）` : ` (${activeJobs.length} active)`)}</button>
        </nav>

        {/* Core Scientific Objective / Hypothesis Card */}
        <div className="portal-goal-container">
          <div className="portal-goal-head">
            <div className="goal-label-wrap">
              <span className="goal-head-title">{t.goalCardTitle}</span>
              <span className="goal-hint-badge">{t.goalCardTag}</span>
            </div>
            {!editingGoal ? (
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => {
                  setGoalDraft(goal || { objective: '', completion_criteria: '', current_focus: '' });
                  setEditingGoal(true);
                }}
              >
                {goal ? t.editGoal : t.setGoal}
              </button>
            ) : (
              <div className="btn-group sm">
                <button
                  type="button"
                  className="btn ghost sm"
                  onClick={() => setEditingGoal(false)}
                  disabled={savingGoal}
                >
                  {t.cancel}
                </button>
                <button
                  type="button"
                  className="btn primary sm"
                  onClick={handleSaveGoal}
                  disabled={savingGoal}
                >
                  {savingGoal ? t.savingGoal : t.saveGoal}
                </button>
              </div>
            )}
          </div>

          {editingGoal ? (
            <div className="portal-goal-editor">
              <div className="goal-field">
                <label className="goal-field-label">{t.objectiveLabel}</label>
                <textarea
                  className="input goal-textarea"
                  rows={2}
                  placeholder={t.objectivePlaceholder}
                  value={goalDraft.objective}
                  onChange={(e) => setGoalDraft({ ...goalDraft, objective: e.target.value })}
                />
              </div>
              <div className="goal-row-2col">
                <div className="goal-field">
                  <label className="goal-field-label">{t.completionCriteriaLabel}</label>
                  <input
                    type="text"
                    className="input sm"
                    placeholder={t.completionCriteriaPlaceholder}
                    value={goalDraft.completion_criteria}
                    onChange={(e) => setGoalDraft({ ...goalDraft, completion_criteria: e.target.value })}
                  />
                </div>
                <div className="goal-field">
                  <label className="goal-field-label">{t.currentFocusLabel}</label>
                  <input
                    type="text"
                    className="input sm"
                    placeholder={t.currentFocusPlaceholder}
                    value={goalDraft.current_focus}
                    onChange={(e) => setGoalDraft({ ...goalDraft, current_focus: e.target.value })}
                  />
                </div>
              </div>
            </div>
          ) : goal ? (
            <div className="portal-goal-content">
              <div className="goal-main-objective">
                <span className="goal-quote-mark">“</span>
                <span className="goal-text">{goal.objective || '—'}</span>
                <span className="goal-quote-mark">”</span>
              </div>
              <div className="goal-pills-row">
                {goal.completion_criteria && (
                  <div className="goal-pill">
                    <span className="pill-k">{t.criteriaPill}</span>
                    <span className="pill-v">{goal.completion_criteria}</span>
                  </div>
                )}
                {goal.current_focus && (
                  <div className="goal-pill focus">
                    <span className="pill-k">{t.focusPill}</span>
                    <span className="pill-v">{goal.current_focus}</span>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="portal-goal-empty">
              <p className="goal-empty-text">
                {t.goalEmptyHint}
              </p>
            </div>
          )}
        </div>
      </section>

      <details className="portal-details">
        <summary>{lang === 'zh' ? '协作与运行详情' : 'Collaboration & runtime details'}</summary>
      {/* Middle Section: Agent Fleet & Collaboration Hierarchy */}
      <section className="portal-agent-section">
        <div className="portal-agent-header">
          <div className="agent-header-left">
            <span className="agent-header-svg">
              <NetworkSvg />
            </span>
            <div>
              <div className="agent-header-title-row">
                <h2 className="agent-header-title">{t.agentFleetTitle}</h2>
                <span className="badge sm neutral">{t.agentNodesCount(agents.length)}</span>
              </div>
              <div className="agent-header-sub">
                {t.agentFleetSub}
              </div>
            </div>
          </div>
          <div className="agent-header-meta">
            <span className="agent-count-pill running">
              <span className="status-dot-pulse green" />
              <span>{agents.filter((a) => a.state === 'running').length} {t.stateRunning}</span>
            </span>
            <span className="agent-count-pill waiting">
              <span className="status-dot-pulse amber" />
              <span>{agents.filter((a) => a.state.startsWith('waiting')).length} {t.stateWaiting}</span>
            </span>
            <span className="agent-count-pill idle">
              <span className="status-dot-pulse gray" />
              <span>{agents.filter((a) => a.state === 'idle').length} {t.stateIdle}</span>
            </span>
          </div>
        </div>

        <div className="portal-agent-body">
          {agents.length === 0 ? (
            <div className="portal-agent-empty">
              <span className="empty-svg-wrap icon-purple">
                <NetworkSvg />
              </span>
              <div className="empty-content">
                <span className="empty-title">{t.agentEmptyTitle}</span>
                <span className="empty-desc">
                  {t.agentEmptyDesc}
                </span>
              </div>
            </div>
          ) : (
            <div className="portal-agent-tree-list">
              {rootAgents.map((r) => renderAgentNode(r, 0))}
            </div>
          )}
        </div>
      </section>

      {/* Bottom Section: Navigation Portal Cards Grid */}
      <section className="portal-nav-section">
        <div className="portal-nav-section-title">
          <span>{t.navSectionTitle}</span>
          <span className="nav-subtitle">{t.navSectionSubtitle}</span>
        </div>

        <div className="portal-cards-grid">
          {/* Card 1: DAG Exploration */}
          <div
            className={`portal-nav-card ${dagModeActive ? 'card-highlight' : ''}`}
            onClick={() => onNavigate('research')}
          >
            <div className="nav-card-top">
              <div className="nav-card-icon-wrap icon-cyan">
                {/* Vector SVG: Molecular Graph */}
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="6" cy="6" r="3" />
                  <circle cx="18" cy="6" r="3" />
                  <circle cx="12" cy="18" r="3" />
                  <line x1="8.5" y1="7.5" x2="15.5" y2="7.5" />
                  <line x1="7.5" y1="8.5" x2="10.5" y2="15.5" />
                  <line x1="16.5" y1="8.5" x2="13.5" y2="15.5" />
                </svg>
              </div>
              <span className={`badge sm ${dagModeActive ? 'ok' : 'neutral'}`}>
                {dagModeActive ? t.cardDagBadgeActive : t.cardDagBadgeReady}
              </span>
            </div>

            <div className="nav-card-body">
              <h3 className="nav-card-heading">{lang === 'zh' ? '结构、计算与机理' : 'Structures, calculations & mechanism'}</h3>
              <p className="nav-card-desc">
                {lang === 'zh' ? '查看真实计算过程、结构与文件产物；从独立分子工作台编辑并保存。' : 'Open calculation frames, structures and artifacts; edit molecules in the independent workbench.'}
              </p>
            </div>

            <div className="nav-card-footer">
              <span className="nav-card-meta">
                {dagSummary?.nodeCount ? t.cardDagMetaActive(dagSummary.nodeCount, dagSummary.edgeCount) : t.cardDagMetaDefault}
              </span>
              <span className="nav-card-arrow">{lang === 'zh' ? '打开研究结果 →' : 'Open research results →'}</span>
            </div>
          </div>

          {/* Card 2: Compute Ops */}
          <div className="portal-nav-card" onClick={() => onNavigate('compute')}>
            <div className="nav-card-top">
              <div className="nav-card-icon-wrap icon-amber">
                {/* Vector SVG: Compute Chip / Lightning */}
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="4" y="4" width="16" height="16" rx="2" />
                  <rect x="9" y="9" width="6" height="6" />
                  <line x1="9" y1="1" x2="9" y2="4" />
                  <line x1="15" y1="1" x2="15" y2="4" />
                  <line x1="9" y1="20" x2="9" y2="23" />
                  <line x1="15" y1="20" x2="15" y2="23" />
                  <line x1="20" y1="9" x2="23" y2="9" />
                  <line x1="20" y1="14" x2="23" y2="14" />
                  <line x1="1" y1="9" x2="4" y2="9" />
                  <line x1="1" y1="14" x2="4" y2="14" />
                </svg>
              </div>
              <span className={`badge sm ${activeJobs.length > 0 ? 'running' : 'neutral'}`}>
                {stoppingJobs.length > 0
                  ? t.cardComputeBadgeStopping(stoppingJobs.length)
                  : activeJobs.length > 0 ? t.cardComputeBadgeRunning(activeJobs.length) : t.cardComputeBadgeReady}
              </span>
            </div>

            <div className="nav-card-body">
              <h3 className="nav-card-heading">{t.cardComputeTitle}</h3>
              <p className="nav-card-desc">
                {t.cardComputeDesc}
              </p>
            </div>

            <div className="nav-card-footer">
              <span className="nav-card-meta">
                {sidebarJobs ? t.cardComputeMeta(sidebarJobs.length) : t.cardComputeMetaDefault}
              </span>
              <span className="nav-card-arrow">{t.cardComputeAction}</span>
            </div>
          </div>

          {/* Card 4: Audit & Event Logs */}
          <div className="portal-nav-card" onClick={() => onNavigate('audit')}>
            <div className="nav-card-top">
              <div className="nav-card-icon-wrap icon-emerald">
                {/* Vector SVG: Clipboard / Log Stream */}
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              </div>
              <span className="badge sm neutral">{t.cardAuditBadge}</span>
            </div>

            <div className="nav-card-body">
              <h3 className="nav-card-heading">{t.cardAuditTitle}</h3>
              <p className="nav-card-desc">
                {t.cardAuditDesc}
              </p>
            </div>

            <div className="nav-card-footer">
              <span className="nav-card-meta">{t.cardAuditMeta}</span>
              <span className="nav-card-arrow">{t.cardAuditAction}</span>
            </div>
          </div>

          {/* Card 5: Token Telemetry */}
          <div className="portal-nav-card" onClick={() => onNavigate('telemetry')}>
            <div className="nav-card-top">
              <div className="nav-card-icon-wrap icon-blue">
                {/* Vector SVG: Gauge / Analytics */}
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2v4" />
                  <path d="m4.93 4.93 2.83 2.83" />
                  <path d="M2 12h4" />
                  <path d="m4.93 19.07 2.83-2.83" />
                  <path d="M12 18v4" />
                  <path d="m16.24 16.24 2.83 2.83" />
                  <path d="M18 12h4" />
                  <path d="m16.24 7.76 2.83-2.83" />
                </svg>
              </div>
              <span className="badge sm neutral">{t.cardTelemetryBadge}</span>
            </div>

            <div className="nav-card-body">
              <h3 className="nav-card-heading">{t.cardTelemetryTitle}</h3>
              <p className="nav-card-desc">
                {t.cardTelemetryDesc}
              </p>
            </div>

            <div className="nav-card-footer">
              <span className="nav-card-meta">{t.cardTelemetryMeta}</span>
              <span className="nav-card-arrow">{t.cardTelemetryAction}</span>
            </div>
          </div>

          {/* Card 6: AgentHub Collaboration Forum */}
          <div className="portal-nav-card" onClick={() => onNavigate('hub')}>
            <div className="nav-card-top">
              <div className="nav-card-icon-wrap icon-indigo">
                {/* Vector SVG: Messages / Forum */}
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
                </svg>
              </div>
              <span className="badge sm neutral">
                {hubPostsCount !== null ? t.cardHubBadge(hubPostsCount) : t.cardHubBadgeDefault}
              </span>
            </div>

            <div className="nav-card-body">
              <h3 className="nav-card-heading">{t.cardHubTitle}</h3>
              <p className="nav-card-desc">
                {t.cardHubDesc}
              </p>
            </div>

            <div className="nav-card-footer">
              <span className="nav-card-meta">{t.cardHubMeta}</span>
              <span className="nav-card-arrow">{t.cardHubAction}</span>
            </div>
          </div>
        </div>
      </section>
      </details>
    </div>
  );
}
