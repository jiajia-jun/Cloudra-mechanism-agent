/**
 * GlobalConfig — sidebar entry modal for the global LLM config.
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
import ToolDocumentLoadingSection from './ToolDocumentLoadingSection';
import { isTrustedAuthMessageOrigin } from './runtimeUrl';
import type { ProviderPreset, RuntimeConfig } from './types';

interface GlobalConfigProps {
  onClose: () => void;
  onToast: (kind: 'ok' | 'error', text: string) => void;
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
          {usesCodex ? 'OAuth' : `key ${keySet ? 'set' : 'not set'}`}
        </span>
      </div>
      <div className="muted-note">{hint}</div>

      <label className="field">
        provider (模型供应商)
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
          {!presets.some((p) => p.id === 'custom') && <option value="custom">自定义 (Custom)</option>}
        </select>
        <span className="field-hint">
          选择供应商可自动填入官方 API 端点、推荐上下文并带出候选模型
        </span>
      </label>

      <label className="field">
        base_url (API 地址)
        <input
          className="input"
          value={draft.url}
          disabled={usesCodex}
          onChange={(e) => handleUrlChange(e.target.value)}
          placeholder="https://…"
        />
      </label>

      <label className="field">
        model (模型名称)
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
          可直接输入任意模型，或双击/点击下拉选择常见推荐模型
        </span>
      </label>

      {!usesCodex && <label className="field">
        api key
        <input
          className="input"
          type="password"
          autoComplete="off"
          value={draft.key}
          onChange={(e) => onChange({ key: e.target.value })}
          placeholder={
            keySet
              ? 'type a new key to replace…'
              : currentPreset?.key_hint
                ? `type to set key (${currentPreset.key_hint})…`
                : 'type to set a key…'
          }
        />
        <span className="field-hint">
          write-only: the stored key is never shown. Leave empty to keep the current key.
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
            登录 OpenRouter 账号授权 (OAuth PKCE)
          </button>
          <span className="field-hint" style={{ display: 'inline-block', marginLeft: '0.6rem' }}>
            无需手动查找或粘贴 Key，跳转 OpenRouter 官网一键授权绑定
          </span>
        </div>
      )}

      <div className="field-row">
        <label className="field" style={{ flex: 1, marginBottom: 0 }}>
          context_window
          <input
            className="input"
            type="number"
            min={1}
            value={draft.context_window}
            onChange={(e) => onChange({ context_window: e.target.value })}
          />
        </label>
        <label className="field" style={{ flex: 1, marginBottom: 0 }}>
          timeout (s)
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
        Supports vision
      </label>

      <label className="field" title="Reasoning effort passed as the OpenAI-compatible reasoning_effort parameter">
        reasoning effort
        <select
          className="input"
          value={draft.reasoning_effort}
          onChange={(e) => onChange({ reasoning_effort: e.target.value })}
        >
          <option value="">default (not sent)</option>
          <option value="minimal">minimal</option>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
        </select>
        <span className="field-hint">
          global fallback for agents without a per-agent override; empty = parameter not sent
        </span>
      </label>

      <div className="modal-actions">
        {keySet && !usesCodex && (
          <button
            className="btn ghost sm"
            disabled={saving}
            onClick={() => onSave(slot, true)}
          >
            clear key
          </button>
        )}
        <button className="btn primary sm" disabled={saving} onClick={() => onSave(slot, false)}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  );
}

export default function GlobalConfig({
  onClose,
  onToast,
}: GlobalConfigProps) {
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
  }, []);

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
    <div className="modal-backdrop">
      <div className="modal">
        <div className="modal-head">
          <span className="modal-title">Global config</span>
          <button className="btn ghost sm" style={{ marginLeft: 'auto' }} onClick={onClose}>
            close
          </button>
        </div>
        <div className="modal-sub">
          The two fallback slots behind empty per-agent settings: the coordinator role falls back to
          the <b>coordinator</b> slot, every other role to the <b>follower</b> slot. Changes are
          written to <span className="mono-path">{cfg?.config_file ?? '…'}</span> and apply on the
          next LLM request.
        </div>


        {cfg === null ? (
          <div className="empty-hint">Loading config…</div>
        ) : (
          <>
            {(drafts.coordinator.provider === 'openai-codex' || drafts.follower.provider === 'openai-codex') && (
              <CodexAuthPanel onToast={onToast} />
            )}
            <SlotSection
              title="Coordinator slot"
              hint="Fallback for the coordinator role (per-agent settings take precedence)."
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
              title="Follower slot"
              hint="Fallback for every non-coordinator role (researcher, dft, md, …)."
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
            <ToolDocumentLoadingSection config={cfg.tool_document_loading}
              onSaved={setCfg} onToast={onToast} />
          </>
        )}
      </div>
    </div>
  );
}
