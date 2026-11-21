import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { useI18n } from './i18n';
import { groupDiagnosticsChecks } from './onboardingState';
import type { DiagnosticCheck, DiagnosticGroup, DiagnosticStatus, RuntimeDiagnostics } from './types';

interface EnvironmentDiagnosticsPanelProps {
  onOpenSettings?: () => void;
  compact?: boolean;
  onReportLoaded?: (report: RuntimeDiagnostics) => void;
}

function groupLabel(group: DiagnosticGroup, lang: 'zh' | 'en'): string {
  const zh: Record<DiagnosticGroup, string> = {
    llm: '大模型连接',
    chemistry: '基础化学与运行环境',
    compute: '计算节点与量化软件',
    storage: '本地存储与数据目录',
  };
  const en: Record<DiagnosticGroup, string> = {
    llm: 'LLM Connectivity',
    chemistry: 'Chemistry & Core Runtime',
    compute: 'Compute Nodes & Engines',
    storage: 'Local Storage',
  };
  return lang === 'zh' ? zh[group] : en[group];
}

function checkTitle(id: string, lang: 'zh' | 'en'): string {
  const zh: Record<string, string> = {
    llm_config: '模型接口配置',
    python_runtime: 'Python 运行时',
    rdkit: 'RDKit 分子处理库',
    nodejs_host: 'Node.js（默认工具协议）',
    xtb_binary: 'xTB 半经验引擎（可选）',
    compute_nodes: '计算节点注册表',
    local_qm_engines: '本地量化 / MD 软件（可选）',
    data_dir: 'Cloudra 数据目录',
  };
  const en: Record<string, string> = {
    llm_config: 'Model Configuration',
    python_runtime: 'Python Runtime',
    rdkit: 'RDKit Chemistry Library',
    nodejs_host: 'Node.js (Default Tool Host)',
    xtb_binary: 'xTB Semiempirical Engine (Optional)',
    compute_nodes: 'Compute Node Registry',
    local_qm_engines: 'Local QM / MD Binaries (Optional)',
    data_dir: 'Cloudra Data Directory',
  };
  return (lang === 'zh' ? zh[id] : en[id]) ?? id;
}

function hintText(hint: string, lang: 'zh' | 'en'): string {
  if (!hint) return '';
  const zh: Record<string, string> = {
    open_global_settings_llm: '打开“全局设置”填入 API Key，或使用 ChatGPT / Codex 账号登录。',
    configure_follower_optional: '主控模型已就绪；如需降低子任务成本，可顺手在全局设置中单独配置 Follower 模型。',
    upgrade_python_311: 'Cloudra 需要 Python 3.11 或更高版本。',
    install_rdkit: '未检测到 RDKit，分子结构校验与三维构象预处理功能将受限。',
    install_nodejs_or_use_traditional_protocol: '未检测到 Node.js：可安装 Node.js 22+，或在项目设置中切换为 traditional 工具协议。',
    install_xtb_optional: '仅本地运行 xTB 预优化或构象筛选时需要；如只用远程集群或查文献可忽略。',
    check_nodes_config: '请检查节点配置文件格式，确认本地或 SSH/Slurm 节点定义有效。',
    configure_local_or_remote_qm: '本地 PATH 未检测到 ORCA / Gaussian / GROMACS；如通过 SSH/Slurm 远程节点计算或仅做文献/脚本任务，可忽略。',
    fix_data_dir_permissions: '请检查该目录的读写权限，或通过配置更换可写的数据目录。',
  };
  const en: Record<string, string> = {
    open_global_settings_llm: 'Open Global Settings to enter an API key or sign in with ChatGPT / Codex.',
    configure_follower_optional: 'Coordinator is ready; optionally configure a separate Follower model in Global Settings.',
    upgrade_python_311: 'Cloudra requires Python 3.11 or newer.',
    install_rdkit: 'RDKit is missing; structure validation and 3D conformer tools will be limited.',
    install_nodejs_or_use_traditional_protocol: 'Node.js not found on PATH: install Node.js 22+ or switch to the traditional tool protocol in project settings.',
    install_xtb_optional: 'Optional for local xTB preoptimization; safe to skip if using remote clusters or literature workflows.',
    check_nodes_config: 'Check your node registry configuration for local or SSH/Slurm nodes.',
    configure_local_or_remote_qm: 'No local ORCA / Gaussian / GROMACS on PATH; safe to skip if computing via remote SSH/Slurm nodes or doing non-QM work.',
    fix_data_dir_permissions: 'Ensure the data directory is writable or point data_dir to a writable path.',
  };
  return (lang === 'zh' ? zh[hint] : en[hint]) ?? hint;
}

function statusBadgeLabel(status: DiagnosticStatus, lang: 'zh' | 'en'): string {
  const zh: Record<DiagnosticStatus, string> = {
    ready: '已就绪',
    optional_missing: '可选未装',
    warning: '待配置',
    error: '异常',
  };
  const en: Record<DiagnosticStatus, string> = {
    ready: 'Ready',
    optional_missing: 'Optional',
    warning: 'Needs setup',
    error: 'Error',
  };
  return lang === 'zh' ? zh[status] : en[status];
}

export default function EnvironmentDiagnosticsPanel({
  onOpenSettings,
  compact = false,
  onReportLoaded,
}: EnvironmentDiagnosticsPanelProps) {
  const { lang } = useI18n();
  const [report, setReport] = useState<RuntimeDiagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const runCheck = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.runtimeDiagnostics();
      if (data && Array.isArray(data.checks)) {
        setReport(data);
        onReportLoaded?.(data);
      } else {
        setError(lang === 'zh' ? '环境检测返回格式异常。' : 'Unexpected diagnostics response.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [lang, onReportLoaded]);

  useEffect(() => {
    void runCheck();
  }, [runCheck]);

  const groups = groupDiagnosticsChecks(report?.checks);

  const overallLabel = (() => {
    if (!report) return '';
    if (report.overall_status === 'ready') {
      return lang === 'zh' ? '核心环境已就绪，可以直接开始研究' : 'Core environment ready';
    }
    if (report.overall_status === 'needs_setup') {
      return lang === 'zh' ? '核心能力还差几项基础配置（不影响先浏览界面）' : 'Some setup recommended before running tasks';
    }
    return lang === 'zh' ? '检测到必须处理的基础环境异常' : 'Critical environment issue detected';
  })();

  const renderCheckRow = (item: DiagnosticCheck) => {
    const resolvedHint = hintText(item.hint, lang);
    return (
      <div key={item.id} className={`diag-row diag-status-${item.status}`}>
        <div className="diag-row-main">
          <div className="diag-row-head">
            <span className="diag-row-title">{checkTitle(item.id, lang)}</span>
            <span className={`diag-pill diag-pill-${item.status}`}>
              {statusBadgeLabel(item.status, lang)}
            </span>
          </div>
          <div className="diag-row-detail">{item.detail}</div>
          {resolvedHint && <div className="diag-row-hint">{resolvedHint}</div>}
        </div>
        {item.id === 'llm_config' && item.status !== 'ready' && onOpenSettings && (
          <button type="button" className="btn outline sm" onClick={onOpenSettings}>
            {lang === 'zh' ? '去配置模型' : 'Configure LLM'}
          </button>
        )}
      </div>
    );
  };

  return (
    <div className={`diag-panel ${compact ? 'compact' : ''}`}>
      <div className="diag-toolbar">
        <div className="diag-summary-line">
          {report ? (
            <>
              <span className={`diag-overall-dot diag-overall-${report.overall_status}`} />
              <span>{overallLabel}</span>
            </>
          ) : (
            <span>{lang === 'zh' ? '正在检查本机与配置环境…' : 'Checking local & configured environment…'}</span>
          )}
        </div>
        <button
          type="button"
          className="btn outline sm"
          disabled={loading}
          onClick={() => void runCheck()}
        >
          {loading
            ? (lang === 'zh' ? '检测中…' : 'Checking…')
            : (lang === 'zh' ? '重新检测' : 'Re-check')}
        </button>
      </div>

      {error && (
        <div className="diag-error-banner">
          {lang === 'zh' ? `环境自检暂时失败：${error}` : `Diagnostics failed: ${error}`}
        </div>
      )}

      {groups.map(({ group, items }) => (
        <div key={group} className="diag-group">
          <div className="diag-group-title">{groupLabel(group, lang)}</div>
          <div className="diag-group-list">{items.map(renderCheckRow)}</div>
        </div>
      ))}
    </div>
  );
}
