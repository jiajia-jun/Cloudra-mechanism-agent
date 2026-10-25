/**
 * GlobalConfig — global settings for language, appearance and LLM config.
 *
 * Edits the two fallback slots (coordinator / follower) of the shared
 * `~/.config/cloudra/config.yaml`. These are what empty per-agent settings
 * fall back to at request time, so changes are live on the next LLM request.
 * API keys are write-only: the UI never receives the stored value, only
 * `key_set`, and "clear key" sends an explicit empty string.
 */

import { useEffect, useState } from 'react';
import { api } from './api';
import CodexAuthPanel from './CodexAuthPanel';
import SearchConfigSection from './SearchConfigSection';
import ToolDocumentLoadingSection from './ToolDocumentLoadingSection';
import { isTrustedAuthMessageOrigin } from './runtimeUrl';
import type { ProviderPreset, RuntimeConfig } from './types';
import { useI18n } from './i18n';

interface GlobalConfigProps {
  mode: 'preferences' | 'models';
  onClose: () => void;
  onToast: (kind: 'ok' | 'error', text: string) => void;
  theme: 'glass' | 'emerald';
  onThemeChange: (theme: 'glass' | 'emerald') => void;
  wallpaper: string;
  onWallpaperChange: (wallpaper: string) => void;
}

interface SlotDraft {
  provider: string;
  model: string;
  url: string;
  context_window: string;
  timeout: string;
  key: string;
  supports_vision: boolean;
  reasoning_effort: string;
}

type Slot = 'coordinator' | 'follower';

const EMPTY_DRAFT: SlotDraft = {
  provider: '',
  model: '',
  url: '',
  context_window: '',
  timeout: '',
  key: '',
  supports_vision: true,
  reasoning_effort: '',
};

function draftFrom(cfg: RuntimeConfig, slot: Slot): SlotDraft {
  const s = cfg[slot];
  return {
    provider: s.provider ?? '',
    model: s.model,
    url: s.url,
    context_window: String(s.context_window),
    timeout: String(s.timeout),
    key: '',
    supports_vision: s.supports_vision !== false,
    reasoning_effort: s.reasoning_effort ?? '',
  };
}

function SlotSection({
  title,
  hint,
  slot,
  draft,
  presets,
  savedCfg,
  saving,
  onChange,
  onSave,
  onConnectOpenRouter,
}: {
  title: string;
  hint: string;
  slot: Slot;
  draft: SlotDraft;
  presets: ProviderPreset[];
  savedCfg: RuntimeConfig;
  saving: boolean;
  onChange: (patch: Partial<SlotDraft>) => void;
  onSave: (slot: Slot, clearKey: boolean) => void;
  onConnectOpenRouter: (slot: Slot) => void;
}) {
  const { lang } = useI18n();
  const zh = lang === 'zh';
  const keySet = savedCfg[slot].key_set;
  const usesCodex = draft.provider === 'openai-codex';
  const currentPreset = presets.find((p) => p.id === draft.provider);

  const handleProviderChange = (newProviderId: string) => {
    const p = presets.find((x) => x.id === newProviderId);
    if (p && p.id !== 'custom') {
      onChange({
        provider: p.id,
        url: p.default_url,
        model: p.default_model,
        context_window: String(p.context_window),
        supports_vision: p.supports_vision,
        ...(p.id === 'openai-codex' ? { key: '' } : {}),
      });
    } else {
      onChange({ provider: 'custom' });
    }
  };

  const handleUrlChange = (newUrl: string) => {
    const lower = newUrl.toLowerCase();
    const matched = presets.find(
      (p) => p.id !== 'custom' && p.match_hosts?.some((h) => lower.includes(h.toLowerCase()))
    );
    onChange({
      url: newUrl,
      provider: matched ? matched.id : 'custom',
    });
  };

  return (
    <div className="modal-section">
      <div className="modal-section-title">
        {title}
        <span className={`api-key-state ${keySet ? 'ok' : ''}`}>
          {usesCodex ? 'OAuth' : (zh ? (keySet ? '已配置密钥' : '未配置密钥') : (keySet ? 'Key set' : 'Key not set'))}
        </span>
      </div>
      <div className="muted-note">{hint}</div>

      <label className="field">
        {zh ? '模型供应商' : 'Provider'}
        <select
          className="input"
          value={draft.provider || 'custom'}
          onChange={(e) => handleProviderChange(e.target.value)}
        >
          {presets.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
          {!presets.some((p) => p.id === 'custom') && <option value="custom">{zh ? '自定义' : 'Custom'}</option>}
        </select>
        <span className="field-hint">
          {zh ? '选择供应商后自动填写接口地址与候选模型' : 'Selecting a provider fills its API endpoint and available models.'}
        </span>
      </label>

      <label className="field">
        {zh ? '接口地址' : 'API endpoint'}
        <input
          className="input"
          value={draft.url}
          disabled={usesCodex}
          onChange={(e) => handleUrlChange(e.target.value)}
          placeholder="https://…"
        />
      </label>

      <label className="field">
        {zh ? '模型名称' : 'Model name'}
        <input
          className="input"
          value={draft.model}
          list={`model-suggestions-${slot}`}
          onChange={(e) => onChange({ model: e.target.value })}
          placeholder="e.g. deepseek-v4-pro, gpt-6-astra, claude-sonnet-5"
        />
        <datalist id={`model-suggestions-${slot}`}>
          {(currentPreset?.models && currentPreset.models.length > 0
            ? currentPreset.models
            : presets.flatMap((p) => p.models)
          ).map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        <span className="field-hint">
          {zh ? '可直接输入模型名称或选择候选模型' : 'Enter a model name or select a suggested model.'}
        </span>
      </label>

      {!usesCodex && <label className="field">
        {zh ? '接口密钥' : 'API key'}
        <input
          className="input"
          type="password"
          autoComplete="off"
          value={draft.key}
          onChange={(e) => onChange({ key: e.target.value })}
          placeholder={
            keySet
              ? (zh ? '输入新密钥以替换' : 'Enter a new key to replace')
              : currentPreset?.key_hint
                ? `type to set key (${currentPreset.key_hint})…`
                : 'type to set a key…'
          }
        />
        <span className="field-hint">
          {zh ? '已保存的密钥不会显示，留空则保留当前密钥。' : 'Stored keys are never displayed. Leave empty to keep the current key.'}
        </span>
      </label>}

      {draft.provider === 'openrouter' && (
        <div style={{ marginTop: '0.35rem', marginBottom: '0.65rem' }}>
          <button
            type="button"
            className="btn secondary sm"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
            onClick={() => onConnectOpenRouter(slot)}
          >
            {zh ? '连接 OpenRouter' : 'Connect OpenRouter'}
          </button>
          <span className="field-hint" style={{ display: 'inline-block', marginLeft: '0.6rem' }}>
            {zh ? '通过官方页面授权，无需手动输入密钥' : 'Authorize on the official site without entering a key.'}
          </span>
        </div>
      )}

      <div className="field-row">
        <label className="field" style={{ flex: 1, marginBottom: 0 }}>
          {zh ? '上下文窗口（Token）' : 'Context window (tokens)'}
          <input
            className="input"
            type="number"
            min={1}
            value={draft.context_window}
            onChange={(e) => onChange({ context_window: e.target.value })}
          />
          <span className="field-hint">
            {zh ? '输入与输出共享此容量。扣除最大输出上限后预留余量，提前压缩历史；未单独设置窗口的智能体从下一轮继承。' : 'Input and output share this capacity. History is compressed early to leave room for the maximum output; agents without an override inherit the window on their next turn.'}
          </span>
        </label>
        <label className="field" style={{ flex: 1, marginBottom: 0 }}>
          {zh ? '超时（秒）' : 'Timeout (seconds)'}
          <input
            className="input"
            type="number"
            min={1}
            value={draft.timeout}
            onChange={(e) => onChange({ timeout: e.target.value })}
          />
        </label>
      </div>

      <label className="field-row" title="Send image content to this model (multimodal/vision-capable)">
        <input
          type="checkbox"
          checked={draft.supports_vision}
          onChange={(e) => onChange({ supports_vision: e.target.checked })}
        />
        {zh ? '支持图像输入' : 'Image input'}
      </label>

      <label className="field" title="Reasoning effort passed as the OpenAI-compatible reasoning_effort parameter">
        {zh ? '推理强度' : 'Reasoning effort'}
        <select
          className="input"
          value={draft.reasoning_effort}
          onChange={(e) => onChange({ reasoning_effort: e.target.value })}
        >
          <option value="">{zh ? '默认' : 'Default'}</option>
          <option value="minimal">{zh ? '最小' : 'Minimal'}</option>
          <option value="low">{zh ? '低' : 'Low'}</option>
          <option value="medium">{zh ? '中' : 'Medium'}</option>
          <option value="high">{zh ? '高' : 'High'}</option>
          <option value="max">{zh ? '最大' : 'Max'}</option>
          <option value="ultra">{zh ? '超强（最大 + 并行智能体）' : 'Ultra (max + parallel agents)'}</option>
        </select>
        <span className="field-hint">
          {zh ? '未单独设置的聊天使用此强度，默认值由供应商决定。' : 'Used by chats without an override. The provider controls the default.'}
        </span>
      </label>

      <div className="modal-actions">
        {keySet && !usesCodex && (
          <button
            className="btn ghost sm"
            disabled={saving}
            onClick={() => onSave(slot, true)}
          >
            {zh ? '清除密钥' : 'Clear key'}
          </button>
        )}
        <button className="btn primary sm" disabled={saving} onClick={() => onSave(slot, false)}>
          {saving ? (zh ? '保存中…' : 'Saving…') : (zh ? '保存' : 'Save')}
        </button>
      </div>
    </div>
  );
}

export default function GlobalConfig({
  mode,
  onClose,
  onToast,
  theme,
  onThemeChange,
  wallpaper,
  onWallpaperChange,
}: GlobalConfigProps) {
  const { lang, setLang } = useI18n();
  const [section, setSection] = useState<'general' | 'appearance' | 'models'>(mode === 'models' ? 'models' : 'general');
  const [cfg, setCfg] = useState<RuntimeConfig | null>(null);
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [drafts, setDrafts] = useState<Record<Slot, SlotDraft>>({
    coordinator: EMPTY_DRAFT,
    follower: EMPTY_DRAFT,
  });
  const [saving, setSaving] = useState<Slot | null>(null);

  useEffect(() => {
    let cancelled = false;
    const urlParams = new URLSearchParams(window.location.search);
    const authCode = urlParams.get('openrouter_code') || urlParams.get('code');
    const verifier = sessionStorage.getItem('openrouter_pkce_verifier');
    const targetSlot = (sessionStorage.getItem('openrouter_pkce_slot') as Slot) || 'coordinator';

    const handleAuth = async () => {
      if (authCode && verifier) {
        sessionStorage.removeItem('openrouter_pkce_verifier');
        sessionStorage.removeItem('openrouter_pkce_slot');
        urlParams.delete('code');
        urlParams.delete('openrouter_code');
        const remainingQuery = urlParams.toString();
        const cleanUrl = window.location.pathname + (remainingQuery ? `?${remainingQuery}` : '');
        window.history.replaceState({}, '', cleanUrl);

        try {
          await api.exchangeOpenRouterCode(authCode, verifier, targetSlot);
          onToast('ok', `OpenRouter 账号授权成功！API Key 已自动绑定至 ${targetSlot}`);
        } catch (err) {
          onToast('error', `OpenRouter 授权交换失败: ${err instanceof Error ? err.message : String(err)}`);
        }
      }
    };

    handleAuth().then(() => {
      if (section !== 'models') return;
      Promise.all([api.runtimeConfig(), api.providers().catch(() => [])])
        .then(([loadedCfg, loadedPresets]) => {
          if (cancelled) return;
          setPresets(loadedPresets);
          setCfg(loadedCfg);
          setDrafts({
            coordinator: draftFrom(loadedCfg, 'coordinator'),
            follower: draftFrom(loadedCfg, 'follower'),
          });
        })
        .catch((e) => {
          if (!cancelled) onToast('error', e instanceof Error ? e.message : String(e));
        });
    });

    const onMessage = async (event: MessageEvent) => {
      if (!isTrustedAuthMessageOrigin(event.origin, window.location.origin)) {
        return;
      }
      if (event.data && event.data.type === 'OPENROUTER_AUTH_CODE' && event.data.code) {
        const storedVerifier = sessionStorage.getItem('openrouter_pkce_verifier');
        const slot = (sessionStorage.getItem('openrouter_pkce_slot') as Slot) || 'coordinator';
        sessionStorage.removeItem('openrouter_pkce_verifier');
        sessionStorage.removeItem('openrouter_pkce_slot');

        if (storedVerifier) {
          try {
            await api.exchangeOpenRouterCode(event.data.code, storedVerifier, slot);
            onToast('ok', `OpenRouter 账号授权成功！API Key 已自动绑定至 ${slot}`);
            const updated = await api.runtimeConfig();
            setCfg(updated);
            setDrafts({
              coordinator: draftFrom(updated, 'coordinator'),
              follower: draftFrom(updated, 'follower'),
            });
          } catch (err) {
            onToast('error', `OpenRouter 授权交换失败: ${err instanceof Error ? err.message : String(err)}`);
          }
        }
      }
    };
    window.addEventListener('message', onMessage);

    return () => {
      cancelled = true;
      window.removeEventListener('message', onMessage);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section]);

  async function connectOpenRouter(slot: Slot) {
    try {
      const callbackUrl = `${window.location.origin}/api/v2/runtime/providers/openrouter/callback`;
      const res = await api.getOpenRouterPkce(callbackUrl);
      sessionStorage.setItem('openrouter_pkce_verifier', res.code_verifier);
      sessionStorage.setItem('openrouter_pkce_slot', slot);

      // 优先通过弹窗打开以避免主页面重载
      const popup = window.open(
        res.auth_url,
        'openrouter_auth_popup',
        'width=640,height=780,menubar=no,toolbar=no,location=no,status=no'
      );
      if (!popup || popup.closed || typeof popup.closed === 'undefined') {
        window.location.href = res.auth_url;
      }
    } catch (e) {
      onToast('error', `发起 OpenRouter 授权失败: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function save(slot: Slot, clearKey: boolean) {
    if (!cfg) return;
    if (
      clearKey &&
      !window.confirm(
        `Clear the stored ${slot} API key?\n\n` +
          'This cannot be undone: the key is never shown, so you will have to paste it again. ' +
          'Agents falling back to this slot will fail on the next LLM request until a new key is set.',
      )
    ) {
      return;
    }
    setSaving(slot);
    try {
      const d = drafts[slot];
      const changes: Record<string, unknown> = {
        provider: d.provider || null,
        model: d.model.trim(),
        url: d.url.trim(),
        supports_vision: d.supports_vision,
        reasoning_effort: d.reasoning_effort || null,
      };
      const cw = parseInt(d.context_window, 10);
      if (Number.isFinite(cw) && cw >= 1) changes.context_window = cw;
      const timeout = parseInt(d.timeout, 10);
      if (Number.isFinite(timeout) && timeout >= 1) changes.timeout = timeout;
      if (clearKey || d.provider === 'openai-codex') {
        changes.key = '';
      } else if (d.key.trim()) {
        changes.key = d.key.trim();
      }
      const updated = await api.patchRuntimeConfig(slot, changes);
      setCfg(updated);
      setDrafts((prev) => ({ ...prev, [slot]: { ...draftFrom(updated, slot), key: '' } }));
      onToast('ok', `${slot} config saved — live on the next LLM request`);
    } catch (e) {
      onToast('error', e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="modal-backdrop settings-backdrop">
      <div className={`modal ${mode === 'models' ? 'model-configuration-modal' : 'global-settings'}`} role="dialog" aria-modal="true" aria-label={mode === 'models' ? (lang === 'zh' ? '模型配置' : 'Model configuration') : (lang === 'zh' ? '全局设置' : 'Settings')}>
        <div className="modal-head">
          <button type="button" className="settings-back" aria-label={lang === 'zh' ? '返回聊天' : 'Back to chat'} title={lang === 'zh' ? '返回聊天' : 'Back to chat'} onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m10 5-7 7 7 7M3 12h18" /></svg>
          </button>
          <span className="modal-title">{mode === 'models' ? (lang === 'zh' ? '模型配置' : 'Model configuration') : (lang === 'zh' ? '设置' : 'Settings')}</span>
        </div>
        <div className={`settings-layout ${mode === 'models' ? 'model-configuration-layout' : ''}`}>
          {mode === 'preferences' && <nav className="settings-navigation" aria-label={lang === 'zh' ? '设置分类' : 'Settings sections'}>
            {(['general', 'appearance'] as const).map((id) => <button type="button" key={id} className={`sidebar-nav-action ${section === id ? 'active' : ''}`} aria-current={section === id ? 'page' : undefined} onClick={() => setSection(id)}>{id === 'general' ? (lang === 'zh' ? '常规' : 'General') : (lang === 'zh' ? '外观' : 'Appearance')}</button>)}
          </nav>}
          <div className="settings-content">
            <h2>{section === 'general' ? (lang === 'zh' ? '常规' : 'General') : section === 'appearance' ? (lang === 'zh' ? '外观' : 'Appearance') : (lang === 'zh' ? '模型' : 'Models')}</h2>
            {section === 'general' && <div className="settings-group">
              <label className="settings-row"><span><strong>{lang === 'zh' ? '语言' : 'Language'}</strong><small>{lang === 'zh' ? '应用界面语言' : 'Application language'}</small></span><select className="select" aria-label={lang === 'zh' ? '语言' : 'Language'} value={lang} onChange={(e) => setLang(e.target.value === 'en' ? 'en' : 'zh')}><option value="zh">简体中文</option><option value="en">English</option></select></label>
            </div>}
            {section === 'appearance' && <div className="settings-group">
              <label className="settings-row"><span><strong>{lang === 'zh' ? '主题' : 'Theme'}</strong><small>{lang === 'zh' ? '界面的配色与质感' : 'Interface colors and materials'}</small></span><select className="select" aria-label={lang === 'zh' ? '界面主题' : 'Theme'} value={theme} onChange={(e) => onThemeChange(e.target.value === 'emerald' ? 'emerald' : 'glass')}><option value="glass">{lang === 'zh' ? '浅蓝玻璃' : 'Sky glass'}</option><option value="emerald">{lang === 'zh' ? '暗绿终端' : 'Green terminal'}</option></select></label>
              <label className="settings-row"><span><strong>{lang === 'zh' ? '壁纸' : 'Wallpaper'}</strong><small>{lang === 'zh' ? '聊天窗口背景' : 'Chat background'}</small></span><select className="select" aria-label={lang === 'zh' ? '壁纸' : 'Wallpaper'} value={wallpaper} onChange={(e) => onWallpaperChange(e.target.value)}><option value="default">{lang === 'zh' ? '跟随主题' : 'Theme default'}</option><option value="none">{lang === 'zh' ? '纯色' : 'Solid color'}</option><option value="blue">{lang === 'zh' ? '浅蓝柔光' : 'Blue glow'}</option><option value="green">{lang === 'zh' ? '绿色柔光' : 'Green glow'}</option></select></label>
            </div>}
            {section === 'models' && <>
        <div className="modal-sub">{lang === 'zh' ? '设置供应商、接口与默认模型，保存后用于后续请求。' : 'Configure providers, API endpoints and default models for subsequent requests.'}</div>


        {cfg === null ? (
          <div className="empty-hint">{lang === 'zh' ? '正在读取模型配置…' : 'Loading model configuration…'}</div>
        ) : (
          <>
            {(drafts.coordinator.provider === 'openai-codex' || drafts.follower.provider === 'openai-codex') && (
              <CodexAuthPanel onToast={onToast} />
            )}
            <SlotSection
              title={lang === 'zh' ? '主控模型' : 'Coordinator model'}
              hint={lang === 'zh' ? '用于主控对话，聊天内的模型设置优先。' : 'Default for coordinator chats; chat settings take precedence.'}
              slot="coordinator"
              draft={drafts.coordinator}
              presets={presets}
              savedCfg={cfg}
              saving={saving === 'coordinator'}
              onChange={(patch) =>
                setDrafts((prev) => ({ ...prev, coordinator: { ...prev.coordinator, ...patch } }))
              }
              onSave={(s, clearKey) => void save(s, clearKey)}
              onConnectOpenRouter={connectOpenRouter}
            />
            <SlotSection
              title={lang === 'zh' ? '协作模型' : 'Follower model'}
              hint={lang === 'zh' ? '用于研究、计算等协作角色。' : 'Default for research and compute roles.'}
              slot="follower"
              draft={drafts.follower}
              presets={presets}
              savedCfg={cfg}
              saving={saving === 'follower'}
              onChange={(patch) =>
                setDrafts((prev) => ({ ...prev, follower: { ...prev.follower, ...patch } }))
              }
              onSave={(s, clearKey) => void save(s, clearKey)}
              onConnectOpenRouter={connectOpenRouter}
            />
            <SearchConfigSection config={cfg} onSaved={setCfg} onToast={onToast} />
            <ToolDocumentLoadingSection config={cfg.tool_document_loading}
              onSaved={setCfg} onToast={onToast} />
          </>
        )}
            </>}
          </div>
        </div>
      </div>
    </div>
  );
}
