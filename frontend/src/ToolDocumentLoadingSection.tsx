import { useEffect, useState } from 'react';
import { api } from './api';
import type { RuntimeConfig, ToolDocumentLoadingConfig } from './types';

type Backend = ToolDocumentLoadingConfig['semantic_backend'];
type Strategy = ToolDocumentLoadingConfig['strategy'];
interface ConnectionDraft {
  endpoint: string;
  model: string;
  key: string;
  boundary: string;
  maxTools: string;
}

function connectionDraft(config: ToolDocumentLoadingConfig, backend: Backend): ConnectionDraft {
  const connection = config[backend];
  const boundary = backend === 'jev' ? config.jev.min_probability : config.reranker.min_score;
  return { endpoint: connection.endpoint, model: connection.model, key: '',
    boundary: boundary == null ? '' : String(boundary),
    maxTools: connection.max_tools == null ? '' : String(connection.max_tools) };
}

export default function ToolDocumentLoadingSection({ config, onSaved, onToast }: {
  config: ToolDocumentLoadingConfig;
  onSaved: (config: RuntimeConfig) => void;
  onToast: (kind: 'ok' | 'error', text: string) => void;
}) {
  const [strategy, setStrategy] = useState<Strategy>(config.strategy);
  const [backend, setBackend] = useState<Backend>(config.semantic_backend);
  const [drafts, setDrafts] = useState<Record<Backend, ConnectionDraft>>({
    jev: connectionDraft(config, 'jev'), reranker: connectionDraft(config, 'reranker'),
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    setStrategy(config.strategy);
    setBackend(config.semantic_backend);
    setDrafts({ jev: connectionDraft(config, 'jev'), reranker: connectionDraft(config, 'reranker') });
  }, [config]);
  const draft = drafts[backend];
  const change = (patch: Partial<ConnectionDraft>) =>
    setDrafts((previous) => ({ ...previous, [backend]: { ...previous[backend], ...patch } }));

  async function save(clearKey = false) {
    setSaving(true);
    setError('');
    try {
      const changes: Record<string, unknown> = {
        strategy: clearKey ? 'llm' : strategy, semantic_backend: backend,
      };
      if (clearKey) {
        changes[backend] = { key: '' };
      } else if (strategy === 'semantic') {
        const boundary = Number(draft.boundary);
        const maxTools = draft.maxTools.trim() ? Number(draft.maxTools) : null;
        if (!draft.boundary.trim() || !Number.isFinite(boundary) ||
            (backend === 'jev' && (boundary < 0 || boundary > 1)) ||
            (maxTools !== null && (!Number.isInteger(maxTools) || maxTools < 1))) {
          throw new Error('请填写有效的筛选边界；工具数须为正整数或留空。');
        }
        changes[backend] = {
          endpoint: draft.endpoint.trim(), model: draft.model.trim(), max_tools: maxTools,
          [backend === 'jev' ? 'min_probability' : 'min_score']: boundary,
          ...(draft.key.trim() ? { key: draft.key.trim() } : {}),
        };
      }
      onSaved(await api.patchToolDocumentLoading(changes));
      onToast('ok', '工具说明设置已保存，将用于新上下文的首次任务。');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="modal-section" aria-label="工具说明加载">
      <div className="modal-section-title">工具说明加载</div>
      <div className="muted-note">首次任务先挑选需要的完整说明，执行中可继续按名称读取。所有可用工具的简介始终保留。</div>
      <label className="field">选择方式
        <select className="input" value={strategy} disabled={saving}
          onChange={(event) => setStrategy(event.target.value as Strategy)}>
          <option value="llm">现有模型</option><option value="semantic">语义筛选</option>
        </select>
      </label>
      {strategy === 'llm' ? (
        <div className="muted-note">复用 Agent 当前的模型与凭据，无需另外配置服务。</div>
      ) : (
        <>
          <label className="field">语义服务
            <select className="input" value={backend} disabled={saving}
              onChange={(event) => setBackend(event.target.value as Backend)}>
              <option value="jev">Jev</option><option value="reranker">本地 Reranker</option>
            </select>
          </label>
          <div className="muted-note">{backend === 'jev'
            ? 'Jev 按每个工具的相关概率筛选，概率范围为 0–1。'
            : '连接已部署的 Reranker 服务。相关分数范围由模型决定，独立设置边界。'}</div>
          <label className="field">服务地址
            <input className="input" type="url" value={draft.endpoint} disabled={saving}
              placeholder={backend === 'jev' ? 'Jev 完整接口地址' : 'http://127.0.0.1:9997/v1/rerank'}
              onChange={(event) => change({ endpoint: event.target.value })} />
          </label>
          <label className="field">模型名称
            <input className="input" value={draft.model} disabled={saving}
              onChange={(event) => change({ model: event.target.value })} />
          </label>
          <label className="field">{backend === 'jev' ? '最低概率' : '最低相关分数'}
            <input className="input" type="number" step="any" value={draft.boundary} disabled={saving}
              min={backend === 'jev' ? 0 : undefined} max={backend === 'jev' ? 1 : undefined}
              onChange={(event) => change({ boundary: event.target.value })} />
          </label>
          <label className="field">最多预加载工具数
            <input className="input" type="number" min={1} step={1} value={draft.maxTools} disabled={saving}
              placeholder="留空不限制" onChange={(event) => change({ maxTools: event.target.value })} />
          </label>
          <label className="field">API 凭据
            <input className="input" type="password" autoComplete="new-password" value={draft.key} disabled={saving}
              placeholder={config[backend].key_set ? '已设置；留空保留原凭据' : backend === 'jev' ? '必填' : '可选'}
              onChange={(event) => change({ key: event.target.value })} />
          </label>
          {config[backend].key_set && <button className="btn ghost sm" disabled={saving}
            onClick={() => void save(true)}>清除凭据并使用现有模型</button>}
        </>
      )}
      {error && <div role="alert">{error}</div>}
      <div className="modal-actions">
        <button className="btn primary sm" disabled={saving} onClick={() => void save()}>
          {saving ? '保存中…' : '保存工具说明设置'}
        </button>
      </div>
    </section>
  );
}
