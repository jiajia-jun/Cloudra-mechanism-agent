import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import { useI18n } from './i18n';
import './ComposerModelPicker.css';

export function buildModelPickerPatch(params: {
  model?: string;
  effort?: string;
  slotModel: string;
  slotProviderModels: string[];
}): Record<string, unknown> {
  const { model, effort, slotModel, slotProviderModels } = params;
  if (effort !== undefined) {
    return { reasoning_effort: effort };
  }
  if (!model) return {};
  if (slotModel && model === slotModel) {
    // 选回当前全局槽位默认模型：清除 agent 级覆盖，恢复跟随全局槽位。
    return { model: '', base_url: '', api_key: '', context_window: 0 };
  }
  if (slotProviderModels.includes(model)) {
    // 选择当前全局供应商下的其他模型：清除可能残留的旧供应商端点/密钥覆盖。
    return { model, base_url: '', api_key: '', context_window: 0 };
  }
  return { model };
}

export default function ComposerModelPicker({ currentModel, reasoningEffort, slot, onChoose, onConfigure }: {
  currentModel?: string;
  reasoningEffort?: string | null;
  slot: 'coordinator' | 'follower';
  onChoose: (patch: Record<string, unknown>) => Promise<void>;
  onConfigure: () => void;
}) {
  const { lang } = useI18n();
  const zh = lang === 'zh';
  const [open, setOpen] = useState(false);
  const [savedModel, setSavedModel] = useState('');
  const [slotProviderModels, setSlotProviderModels] = useState<string[]>([]);
  const [effort, setEffort] = useState(reasoningEffort ?? '');
  const [groups, setGroups] = useState<Array<{ name: string; models: string[] }>>([]);
  const [search, setSearch] = useState('');
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(false);
    Promise.all([api.runtimeConfig(), api.providers()]).then(([config, providers]) => {
      if (!active) return;
      const settings = config[slot];
      const provider = providers.find((item) => item.id === settings.provider);
      const providerModels = provider?.models ?? [];
      setSavedModel(settings.model);
      setSlotProviderModels(providerModels);
      setEffort(reasoningEffort ?? settings.reasoning_effort ?? '');
      setGroups([{ name: provider?.name ?? settings.provider ?? (zh ? '自定义' : 'Custom'), models: [...new Set([currentModel, settings.model, ...providerModels])].filter((model): model is string => Boolean(model)) }]);
    }).catch(() => { if (active) setError(true); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [currentModel, reasoningEffort, slot, revision, zh]);
  useEffect(() => {
    if (!open) return;
    searchInput.current?.focus();
    const dismiss = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); }
    };
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', dismiss);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);
  async function choose(model?: string, nextEffort?: string) {
    if (saving) return;
    if (nextEffort === undefined && !model) return;
    const patch = buildModelPickerPatch({
      model,
      effort: nextEffort,
      slotModel: savedModel,
      slotProviderModels,
    });
    if (Object.keys(patch).length === 0) return;
    setSaving(true); setError(false);
    try {
      await onChoose(patch);
      if (nextEffort !== undefined) {
        setEffort(nextEffort);
      } else {
        setOpen(false);
      }
    }
    catch { setError(true); }
    finally { setSaving(false); }
  }
  const selectedModel = currentModel || savedModel;
  const levels = [['', zh ? '默认' : 'Default'], ['minimal', zh ? '最小' : 'Minimal'], ['low', zh ? '低' : 'Low'], ['medium', zh ? '中' : 'Medium'], ['high', zh ? '高' : 'High'], ['xhigh', zh ? '极高' : 'Extra high'], ['max', zh ? '最高' : 'Maximum'], ['ultra', zh ? '超高' : 'Ultra']];
  return <div className="composer-model-picker" ref={root}>
    <button type="button" ref={trigger} className="composer-model-trigger" disabled={saving} title={selectedModel || (zh ? '选择模型' : 'Choose model')} aria-label={zh ? '选择模型' : 'Choose model'} aria-haspopup="dialog" aria-expanded={open} onClick={() => { setSearch(''); setOpen((value) => !value); }}><span>{selectedModel || (zh ? '模型' : 'Model')}</span><span className="model-trigger-effort">{levels.find(([value]) => value === effort)?.[1]}</span><svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg></button>
    {open && <div className="composer-model-popover" role="dialog" aria-label={zh ? '模型选择' : 'Model selection'}>
      <div className="model-menu-main">
        <input ref={searchInput} className="model-menu-search" aria-label={zh ? '搜索模型' : 'Search models'} placeholder={zh ? '搜索模型' : 'Search models'} value={search} onChange={(event) => setSearch(event.target.value)} />
        <div className="model-menu-list">
          {loading ? <p>{zh ? '正在读取模型…' : 'Loading models…'}</p> : error ? <p role="alert">{zh ? '无法读取或更新模型，请检查服务连接。' : 'Unable to load or update models. Check the service connection.'}</p> : groups.map((group) => {
            const models = group.models.filter((model) => model.toLowerCase().includes(search.toLowerCase()));
            return models.length > 0 && <section key={group.name}><h3>{group.name}</h3>{models.map((model) => <button key={model} type="button" className="model-menu-option" disabled={saving} aria-pressed={model === selectedModel} onClick={() => void choose(model)}><span>{model}</span><span aria-hidden="true">{model === selectedModel ? '✓' : ''}</span></button>)}</section>;
          })}
          {!loading && !error && !groups.some((group) => group.models.some((model) => model.toLowerCase().includes(search.toLowerCase()))) && <p>{zh ? '没有匹配的模型' : 'No matching models'}</p>}
        </div>
        <div className="model-menu-footer">
          <button type="button" className="model-menu-option" disabled={loading || saving} onClick={() => setRevision((value) => value + 1)}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M20 7v5h-5M20 12a8 8 0 1 0-2 6" /></svg><span>{zh ? '刷新模型' : 'Refresh models'}</span></button>
          <button type="button" className="model-menu-option" disabled={saving} onClick={() => { setOpen(false); onConfigure(); }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m15 4 5 5-10 10-6 1 1-6Z" /></svg><span>{zh ? '编辑模型…' : 'Edit models…'}</span></button>
        </div>
      </div>
      <aside className="model-menu-options" aria-label={zh ? '模型选项' : 'Model options'}>
        <h3>{zh ? '选项' : 'Options'}</h3>
        <h3>{zh ? '推理强度' : 'Reasoning effort'}</h3>
        {levels.map(([value, label]) => <button key={value} type="button" className="model-menu-option" aria-pressed={effort === value} disabled={loading || error || saving || !selectedModel} onClick={() => void choose(undefined, value)}><span>{label}</span><span aria-hidden="true">{effort === value ? '✓' : ''}</span></button>)}
      </aside>
    </div>}
  </div>;
}
