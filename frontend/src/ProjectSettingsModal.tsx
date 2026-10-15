import { useState } from 'react';
import type { Agent, Project } from './types';

interface ProjectSettingsModalProps {
  project: Project;
  agents: Agent[];
  activeAgentId: string | null;
  roles: Array<{ role_id: string; display_name: string }>;
  onClose: () => void;
  onSaveProjectSettings: (patch: {
    orchestration_mode?: 'standard' | 'dag_record' | 'dag_guided';
    defaults?: Record<string, unknown>;
    name?: string;
  }) => Promise<void>;
  onSaveAgentSettings: (agentId: string, patch: Record<string, unknown>) => Promise<void>;
  onToast: (kind: 'ok' | 'error', text: string) => void;
}

interface AgentEditDraft {
  model: string;
  orchestration_mode: string;
  invocation_protocol: string;
  temperature: string;
  reasoning_effort: string;
  context_window: string;
  max_tokens: string;
  timeout: string;
  yolo: boolean;
  visual_mode: boolean;
  unattended: boolean;
  clean_context: boolean;
}

function initAgentDraft(agent: Agent): AgentEditDraft {
  const s = agent.settings;
  return {
    model: s.model || '',
    orchestration_mode: s.orchestration_mode || 'standard',
    invocation_protocol: s.invocation_protocol || 'javascript',
    temperature: s.temperature != null ? String(s.temperature) : '',
    reasoning_effort: s.reasoning_effort || '',
    context_window: s.context_window > 0 ? String(s.context_window) : '',
    max_tokens: s.max_tokens != null ? String(s.max_tokens) : '',
    timeout: s.timeout != null ? String(s.timeout) : '',
    yolo: Boolean(s.yolo),
    visual_mode: Boolean(s.visual_mode),
    unattended: Boolean(s.unattended),
    clean_context: Boolean(s.clean_context),
  };
}

function AgentStrip({
  agent,
  projectDefaultModel,
  isExpanded,
  onToggleExpand,
  onSave,
}: {
  agent: Agent;
  projectDefaultModel: string;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onSave: (agentId: string, patch: Record<string, unknown>) => Promise<void>;
}) {
  const [draft, setDraft] = useState<AgentEditDraft>(() => initAgentDraft(agent));
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleFieldChange = (field: keyof AgentEditDraft, val: unknown) => {
    setDraft((prev) => ({ ...prev, [field]: val }));
    setSaveSuccess(false);
    setErrorMsg(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setErrorMsg(null);
    try {
      const patch: Record<string, unknown> = {
        model: draft.model.trim() || null,
        orchestration_mode: draft.orchestration_mode,
        invocation_protocol: draft.invocation_protocol,
        yolo: draft.yolo,
        visual_mode: draft.visual_mode,
        unattended: draft.unattended,
        clean_context: draft.clean_context,
      };
      const contextWindow = draft.context_window.trim() === '' ? 0 : Number(draft.context_window);
      if (!Number.isInteger(contextWindow) || contextWindow < 0) {
        throw new Error('上下文窗口须为非负整数，0 或留空可恢复全局继承');
      }
      patch.context_window = contextWindow;

      if (draft.temperature !== '') {
        const t = parseFloat(draft.temperature);
        if (!isNaN(t) && t >= 0 && t <= 2) patch.temperature = t;
      }
      if (draft.reasoning_effort) {
        patch.reasoning_effort = draft.reasoning_effort;
      } else {
        patch.reasoning_effort = null;
      }
      if (draft.max_tokens !== '') {
        const m = parseInt(draft.max_tokens, 10);
        if (!isNaN(m) && m > 0) patch.max_tokens = m;
      }
      if (draft.timeout !== '') {
        const to = parseInt(draft.timeout, 10);
        if (!isNaN(to) && to > 0) patch.timeout = to;
      }

      await onSave(agent.id, patch);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const effectiveModel =
    agent.settings.model || (projectDefaultModel ? `${projectDefaultModel} (继承)` : '(继承全局备用)');

  return (
    <div className={`agent-strip ${isExpanded ? 'expanded' : ''}`}>
      <div className="agent-strip-header" onClick={onToggleExpand}>
        <div className="agent-strip-left">
          <span className="agent-strip-toggle">{isExpanded ? '▼' : '▶'}</span>
          <span className={`state-dot ${agent.state}`} title={`State: ${agent.state}`} />
          <span className="agent-strip-name">{agent.display_name}</span>
          <span className="badge role-badge">{agent.role_id}</span>
          <span className="mono-path agent-strip-id">{agent.id.slice(0, 8)}</span>
        </div>
        <div className="agent-strip-chips">
          <span className="agent-chip" title="当前模型">
            {effectiveModel}
          </span>
          <span className="agent-chip" title="编排模式">
            {agent.settings.orchestration_mode}
          </span>
          {agent.settings.yolo && (
            <span className="agent-chip yolo-chip" title="已启用全自动放行">
              YOLO
            </span>
          )}
        </div>
      </div>

      {isExpanded && (
        <div className="agent-strip-body">
          <div className="setting-strip-list">
            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-title">独立模型覆盖</span>
                <span className="setting-desc">为此智能体指定专属模型，留空则继承全局方案</span>
              </div>
              <div className="setting-control">
                <input
                  type="text"
                  className="input"
                  value={draft.model}
                  onChange={(e) => handleFieldChange('model', e.target.value)}
                  placeholder="留空继承项目默认…"
                />
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-title">DAG 编排模式</span>
                <span className="setting-desc">机理图生成与阶段交付物审查规范</span>
              </div>
              <div className="setting-control">
                <select
                  className="select"
                  value={draft.orchestration_mode}
                  onChange={(e) => handleFieldChange('orchestration_mode', e.target.value)}
                >
                  <option value="standard">standard (标准直接推导)</option>
                  <option value="dag_record">dag_record (记录并提炼 DAG)</option>
                  <option value="dag_guided">dag_guided (导师督导与交付物审核)</option>
                </select>
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-title">工具调用协议</span>
                <span className="setting-desc">QuickJS 程序化批量执行或传统单步调用</span>
              </div>
              <div className="setting-control">
                <select
                  className="select"
                  value={draft.invocation_protocol}
                  onChange={(e) => handleFieldChange('invocation_protocol', e.target.value)}
                >
                  <option value="javascript">javascript (QuickJS 宿主程序化)</option>
                  <option value="traditional">traditional (单步标准调用)</option>
                </select>
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-title">采样温度与思考强度</span>
                <span className="setting-desc">微调输出发散度与深度推理模型的思考强度</span>
              </div>
              <div className="setting-control-pair">
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="2"
                  className="input"
                  style={{ width: 120 }}
                  value={draft.temperature}
                  onChange={(e) => handleFieldChange('temperature', e.target.value)}
                  placeholder="温度 (0.2)"
                  title="采样温度 (0.0 ~ 2.0)"
                />
                <select
                  className="select"
                  style={{ width: 150 }}
                  value={draft.reasoning_effort}
                  onChange={(e) => handleFieldChange('reasoning_effort', e.target.value)}
                  title="思考强度"
                >
                  <option value="">思考强度: 继承</option>
                  <option value="minimal">minimal (微弱)</option>
                  <option value="low">low (低)</option>
                  <option value="medium">medium (中等)</option>
                  <option value="high">high (深度思考)</option>
                </select>
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-title">上下文窗口（Token）</span>
                <span className="setting-desc">输入与输出共享的容量；0 或留空继承全局配置，下一轮生效</span>
              </div>
              <div className="setting-control">
                <input
                  type="number"
                  min="0"
                  step="1"
                  className="input"
                  value={draft.context_window}
                  onChange={(e) => handleFieldChange('context_window', e.target.value)}
                  placeholder="继承全局窗口"
                  aria-label="智能体上下文窗口"
                />
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-title">最大输出 Token 与超时</span>
                <span className="setting-desc">单次回复上限与请求时限；历史压缩按上下文窗口扣除输出上限后计算</span>
              </div>
              <div className="setting-control-pair">
                <input
                  type="number"
                  step="512"
                  min="256"
                  className="input"
                  style={{ width: 130 }}
                  value={draft.max_tokens}
                  onChange={(e) => handleFieldChange('max_tokens', e.target.value)}
                  placeholder="Max Tokens"
                  title="最大输出 Token 数"
                />
                <input
                  type="number"
                  step="10"
                  min="10"
                  className="input"
                  style={{ width: 140 }}
                  value={draft.timeout}
                  onChange={(e) => handleFieldChange('timeout', e.target.value)}
                  placeholder="超时秒数 (120s)"
                  title="超时时限 (秒)"
                />
              </div>
            </div>

            <div className="setting-row setting-row-toggles">
              <div className="setting-info">
                <span className="setting-title">运行行为特征</span>
                <span className="setting-desc">独立控制安全审批流、视觉输入与上下文记忆隔离</span>
              </div>
              <div className="toggles-cluster">
                <label className="toggle-chip">
                  <input
                    type="checkbox"
                    checked={draft.yolo}
                    onChange={(e) => handleFieldChange('yolo', e.target.checked)}
                  />
                  <span>YOLO 自动放行</span>
                </label>
                <label className="toggle-chip">
                  <input
                    type="checkbox"
                    checked={draft.visual_mode}
                    onChange={(e) => handleFieldChange('visual_mode', e.target.checked)}
                  />
                  <span>视觉感知</span>
                </label>
                <label className="toggle-chip">
                  <input
                    type="checkbox"
                    checked={draft.unattended}
                    onChange={(e) => handleFieldChange('unattended', e.target.checked)}
                  />
                  <span>无人值守</span>
                </label>
                <label className="toggle-chip">
                  <input
                    type="checkbox"
                    checked={draft.clean_context}
                    onChange={(e) => handleFieldChange('clean_context', e.target.checked)}
                  />
                  <span>纯净上下文</span>
                </label>
              </div>
            </div>
          </div>

          <div className="agent-strip-foot">
            {errorMsg && <span className="agent-msg-error">{errorMsg}</span>}
            {saveSuccess && <span className="agent-msg-success">✓ 设置已保存生效</span>}
            <div className="agent-strip-actions">
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => {
                  setDraft(initAgentDraft(agent));
                  setSaveSuccess(false);
                  setErrorMsg(null);
                }}
                disabled={saving}
              >
                重置
              </button>
              <button
                type="button"
                className="btn primary sm"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? '保存中…' : '保存此智能体配置'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProjectSettingsModal({
  project,
  agents,
  activeAgentId,
  onClose,
  onSaveProjectSettings,
  onSaveAgentSettings,
  onToast,
}: ProjectSettingsModalProps) {
  // Global Project settings state
  const [projectName, setProjectName] = useState(project.name);
  const [orchestrationMode, setOrchestrationMode] = useState<'standard' | 'dag_record' | 'dag_guided'>(
    project.settings.orchestration_mode || 'standard',
  );
  const [protocol, setProtocol] = useState<string>(
    project.settings.defaults?.invocation_protocol ?? 'javascript',
  );
  const [defaultModel, setDefaultModel] = useState<string>(
    project.settings.defaults?.model ?? '',
  );
  const [defaultReasoningEffort, setDefaultReasoningEffort] = useState<string>(
    project.settings.defaults?.reasoning_effort ?? '',
  );
  const [defaultContextWindow, setDefaultContextWindow] = useState<string>(
    project.settings.defaults?.context_window ? String(project.settings.defaults.context_window) : '',
  );
  const [savingProject, setSavingProject] = useState(false);
  const [projectSavedOk, setProjectSavedOk] = useState(false);

  // Agent expansion state
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => {
    const s = new Set<string>();
    if (activeAgentId) {
      s.add(activeAgentId);
    } else if (agents.length > 0) {
      s.add(agents[0].id);
    }
    return s;
  });

  const toggleExpand = (agentId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) {
        next.delete(agentId);
      } else {
        next.add(agentId);
      }
      return next;
    });
  };

  const handleSaveProject = async () => {
    setSavingProject(true);
    try {
      const defaultsPatch: Record<string, unknown> = {
        invocation_protocol: protocol,
      };
      const contextWindow = defaultContextWindow.trim() === '' ? 0 : Number(defaultContextWindow);
      if (!Number.isInteger(contextWindow) || contextWindow < 0) {
        throw new Error('上下文窗口须为非负整数，0 或留空可继承全局配置');
      }
      defaultsPatch.context_window = contextWindow;
      if (defaultModel.trim()) {
        defaultsPatch.model = defaultModel.trim();
      }
      if (defaultReasoningEffort) {
        defaultsPatch.reasoning_effort = defaultReasoningEffort;
      }

      await onSaveProjectSettings({
        name: projectName.trim() || project.name,
        orchestration_mode: orchestrationMode,
        defaults: defaultsPatch,
      });
      setProjectSavedOk(true);
      setTimeout(() => setProjectSavedOk(false), 2500);
    } catch (e) {
      onToast('error', `保存失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSavingProject(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal project-settings-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="项目运行配置"
      >
        <div className="settings-page-head">
          <div className="settings-page-meta">
            <h2 className="settings-page-title">项目运行配置</h2>
            <span className="mono-path settings-page-path">
              {project.name} · {project.workspace_dir || '默认工作区'}
            </span>
          </div>
          <button
            type="button"
            className="btn ghost sm modal-close-btn"
            onClick={onClose}
            title="关闭 (Esc)"
          >
            ✕
          </button>
        </div>

        <div className="settings-page-body">
          {/* ============================================================== */}
          {/* Section 1: 全局运行基准 (长条式列表设计) */}
          {/* ============================================================== */}
          <section className="settings-card-section">
            <div className="section-intro">
              <h3 className="section-title">全局方案基准</h3>
              <p className="section-desc">
                默认参数用于新建智能体；已有成员请在下方单独调整。DAG 编排模式会同步已有成员。
              </p>
            </div>

            <div className="setting-strip-list">
              <div className="setting-row">
                <div className="setting-info">
                  <span className="setting-title">项目名称</span>
                  <span className="setting-desc">工作区在会话树与历史记录中的标识名称</span>
                </div>
                <div className="setting-control">
                  <input
                    type="text"
                    className="input"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    placeholder="项目名称…"
                  />
                </div>
              </div>

              <div className="setting-row">
                <div className="setting-info">
                  <span className="setting-title">DAG 编排模式</span>
                  <span className="setting-desc">
                    {orchestrationMode === 'dag_guided'
                      ? '导师严格审查过渡态、IRC 方向证据及有向无环图节点闭合'
                      : orchestrationMode === 'dag_record'
                      ? '后台持续提炼机理图，不强制导师步骤审批'
                      : '自由直接推导模式，不启用 DAG 审查流水线'}
                  </span>
                </div>
                <div className="setting-control">
                  <select
                    className="select"
                    value={orchestrationMode}
                    onChange={(e) =>
                      setOrchestrationMode(e.target.value as 'standard' | 'dag_record' | 'dag_guided')
                    }
                  >
                    <option value="standard">standard (标准直接推导)</option>
                    <option value="dag_record">dag_record (记录并提炼 DAG)</option>
                    <option value="dag_guided">dag_guided (导师督导与交付物审核)</option>
                  </select>
                </div>
              </div>

              <div className="setting-row">
                <div className="setting-info">
                  <span className="setting-title">工具调用协议</span>
                  <span className="setting-desc">新发起会话工具执行环境，推荐使用 QuickJS 程序化批量</span>
                </div>
                <div className="setting-control">
                  <select
                    className="select"
                    value={protocol}
                    onChange={(e) => setProtocol(e.target.value)}
                  >
                    <option value="javascript">javascript (QuickJS 宿主程序化)</option>
                    <option value="traditional">traditional (单步标准调用)</option>
                  </select>
                </div>
              </div>

              <div className="setting-row">
                <div className="setting-info">
                  <span className="setting-title">项目默认模型</span>
                  <span className="setting-desc">留空时自动回退至全局备用槽位 (Coordinator / Follower)</span>
                </div>
                <div className="setting-control">
                  <input
                    type="text"
                    className="input"
                    value={defaultModel}
                    onChange={(e) => setDefaultModel(e.target.value)}
                    placeholder="例如: anthropic/claude-3-5-sonnet"
                  />
                </div>
              </div>

              <div className="setting-row">
                <div className="setting-info">
                  <span className="setting-title">默认思考强度</span>
                  <span className="setting-desc">适用于 OpenAI / DeepSeek 等带有推理思考链的模型</span>
                </div>
                <div className="setting-control">
                  <select
                    className="select"
                    value={defaultReasoningEffort}
                    onChange={(e) => setDefaultReasoningEffort(e.target.value)}
                  >
                    <option value="">未指定 (继承全局系统配置)</option>
                    <option value="minimal">minimal (微弱)</option>
                    <option value="low">low (低)</option>
                    <option value="medium">medium (中等)</option>
                    <option value="high">high (深度思考)</option>
                  </select>
                </div>
              </div>

              <div className="setting-row">
                <div className="setting-info">
                  <span className="setting-title">默认上下文窗口（Token）</span>
                  <span className="setting-desc">新建智能体的输入与输出总容量；0 或留空继承全局配置</span>
                </div>
                <div className="setting-control">
                  <input
                    type="number"
                    min="0"
                    step="1"
                    className="input"
                    value={defaultContextWindow}
                    onChange={(e) => setDefaultContextWindow(e.target.value)}
                    placeholder="继承全局窗口"
                    aria-label="项目默认上下文窗口"
                  />
                </div>
              </div>
            </div>

            <div className="section-foot">
              {projectSavedOk && <span className="agent-msg-success">✓ 全局基准已保存</span>}
              <button
                type="button"
                className="btn primary sm"
                onClick={handleSaveProject}
                disabled={savingProject}
              >
                {savingProject ? '保存中…' : '保存全局基准'}
              </button>
            </div>
          </section>

          {/* ============================================================== */}
          {/* Section 2: 智能体成员配置 (长条式展开卡片) */}
          {/* ============================================================== */}
          <section className="settings-card-section" style={{ marginTop: 28 }}>
            <div className="section-intro">
              <div className="section-title-wrap">
                <h3 className="section-title">智能体成员配置</h3>
                <span className="badge sm">{agents.length}</span>
              </div>
              <p className="section-desc">
                展开任意智能体条目以对其独立调整。可为不同角色指定差异化的模型权重与参数。
              </p>
            </div>

            <div className="agent-strips-container">
              {agents.length === 0 ? (
                <div className="empty-hint" style={{ padding: '32px 0', textAlign: 'center' }}>
                  当前项目暂无活跃智能体。发送第一条消息或从顶栏派生角色以建立会话。
                </div>
              ) : (
                agents.map((agent) => (
                  <AgentStrip
                    key={agent.id}
                    agent={agent}
                    projectDefaultModel={defaultModel}
                    isExpanded={expandedIds.has(agent.id)}
                    onToggleExpand={() => toggleExpand(agent.id)}
                    onSave={onSaveAgentSettings}
                  />
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
