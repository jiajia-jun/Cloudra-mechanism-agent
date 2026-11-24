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
import EnvironmentDiagnosticsPanel from './EnvironmentDiagnosticsPanel';
import SearchConfigSection from './SearchConfigSection';
import ToolDocumentLoadingSection from './ToolDocumentLoadingSection';
import { UpdateCheckInline } from './UpdateCheckSection';
import { isTrustedAuthMessageOrigin, openRouterCallbackCode } from './runtimeUrl';
import {
  buildImpactResolutionPatch,
  findImpactedAgents,
  normalizedEndpoint,
  type ImpactDecision,
  type ImpactedAgent,
} from './globalConfigImpact';
import type { Agent, ProviderPreset, RuntimeConfig } from './types';
import { APPEARANCES, applyAppearance, useAppearance } from './appearance';
import { useI18n } from './i18n';

interface GlobalConfigProps {
  onClose: () => void;
  onToast: (kind: 'ok' | 'error', text: string) => void;
  onOpenOnboarding?: () => void;
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
  const endpointChanged = normalizedEndpoint(savedCfg[slot].url) !== normalizedEndpoint(draft.url);
  const keySet = savedCfg[slot].key_set && !endpointChanged;
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
        ...(p.default_url !== draft.url || p.id === 'openai-codex' ? { key: '' } : {}),
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
      key: '',
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
          {endpointChanged
            ? (lang === 'zh' ? '服务地址已更改。请为新地址输入凭据，留空将清除旧地址的密钥。' : 'New API endpoint. Enter its key, or save with no key to clear the previous credential.')
            : (lang === 'zh' ? '密钥仅写入。留空可保留此地址的已有密钥。' : 'Leave empty to keep the saved key for this endpoint.')}
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
          上下文窗口（Token）
          <input
            className="input"
            type="number"
            min={1}
            value={draft.context_window}
            onChange={(e) => onChange({ context_window: e.target.value })}
          />
          <span className="field-hint">
            输入与输出共享此容量。扣除最大输出上限后预留余量，提前压缩历史；未单独设置窗口的智能体从下一轮继承。
          </span>
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
          <option value="max">max</option>
          <option value="ultra">ultra (max + 并行智能体)</option>
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
  onOpenOnboarding,
}: GlobalConfigProps) {
  const { lang } = useI18n();
  const appearance = useAppearance();
  const [cfg, setCfg] = useState<RuntimeConfig | null>(null);
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [drafts, setDrafts] = useState<Record<Slot, SlotDraft>>({
    coordinator: EMPTY_DRAFT,
    follower: EMPTY_DRAFT,
  });
  const [saving, setSaving] = useState<Slot | null>(null);
  const [pendingImpact, setPendingImpact] = useState<{
    slot: Slot;
    changes: Record<string, unknown>;
    oldSlot: RuntimeConfig[Slot];
    items: ImpactedAgent[];
    decisions: Record<string, ImpactDecision>;
    manualKeys: Record<string, string>;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const urlParams = new URLSearchParams(window.location.search);
    const authCode = openRouterCallbackCode(urlParams);
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

  async function commitSlotSave(slot: Slot, changes: Record<string, unknown>) {
    const updated = await api.patchRuntimeConfig(slot, changes);
    setCfg(updated);
    setDrafts((prev) => ({ ...prev, [slot]: { ...draftFrom(updated, slot), key: '' } }));
    onToast('ok', `${slot} config saved — live on the next LLM request`);
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

      if (!clearKey && normalizedEndpoint(cfg[slot].url) !== normalizedEndpoint(d.url)) {
        try {
          const projects = await api.listProjects(false);
          const entries = await Promise.all(
            projects.map(async (project) => {
              const agents = await api.listAgents(project.id).catch(() => [] as Agent[]);
              return [project.id, agents] as const;
            }),
          );
          const agentsByProject = Object.fromEntries(entries);
          const impacted = findImpactedAgents({
            slot,
            oldSlot: cfg[slot],
            newUrl: d.url,
            projects,
            agentsByProject,
          });
          if (impacted.length > 0) {
            const decisions: Record<string, ImpactDecision> = {};
            for (const item of impacted) {
              decisions[item.agent.id] = 'use_new_global';
            }
            setPendingImpact({
              slot,
              changes,
              oldSlot: cfg[slot],
              items: impacted,
              decisions,
              manualKeys: {},
            });
            return;
          }
        } catch {
          // 列表查询失败时不阻塞全局配置保存
        }
      }

      await commitSlotSave(slot, changes);
    } catch (e) {
      onToast('error', e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  }

  async function confirmPendingImpact() {
    if (!pendingImpact) return;
    const { slot, changes, oldSlot, items, decisions, manualKeys } = pendingImpact;
    setSaving(slot);
    try {
      for (const item of items) {
        const decision = decisions[item.agent.id] ?? 'keep_as_is';
        const patch = buildImpactResolutionPatch({
          item,
          decision,
          oldSlot,
          manualApiKey: manualKeys[item.agent.id],
        });
        if (patch) {
          await api.patchSettings(item.agent.id, patch);
        }
      }
      await commitSlotSave(slot, changes);
      setPendingImpact(null);
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
        <div className="modal-section" role="group" aria-label={lang === 'zh' ? '界面风格' : 'Appearance'}>
          <div className="modal-section-title">{lang === 'zh' ? '界面风格' : 'Appearance'}</div>
          <div className="modal-actions">
            {APPEARANCES.map((option) => (
              <button
                key={option.id}
                type="button"
                className={`btn ${appearance === option.id ? 'primary' : 'outline'} sm`}
                aria-pressed={appearance === option.id}
                onClick={() => applyAppearance(option.id)}
              >
                {lang === 'zh' ? option.zh : option.en}
              </button>
            ))}
          </div>
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
            <SearchConfigSection config={cfg} onSaved={setCfg} onToast={onToast} />
            <ToolDocumentLoadingSection config={cfg.tool_document_loading}
              onSaved={setCfg} onToast={onToast} />
            <div className="modal-section">
              <div className="update-inline-head">
                <div>
                  <div className="modal-section-title">
                    {lang === 'zh' ? '环境自检' : 'Environment Self-Check'}
                  </div>
                  <div className="onboarding-callout-sub">
                    {lang === 'zh'
                      ? '随时复查大模型配置、基础化学库、本地或远程计算节点与数据目录权限。'
                      : 'Verify LLM config, core chemistry libraries, compute nodes, and storage permissions anytime.'}
                  </div>
                </div>
                {onOpenOnboarding && (
                  <button
                    type="button"
                    className="btn ghost sm"
                    onClick={() => {
                      onClose();
                      onOpenOnboarding();
                    }}
                  >
                    {lang === 'zh' ? '重新打开使用引导' : 'Reopen Onboarding'}
                  </button>
                )}
              </div>
              <EnvironmentDiagnosticsPanel />
            </div>
            <UpdateCheckInline onToast={onToast} />
          </>
        )}
      </div>
      {pendingImpact && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={lang === 'zh' ? '已有对话配置冲突提醒' : 'Existing conversation config warning'}>
          <div className="modal" style={{ maxWidth: 640 }}>
            <div className="modal-head">
              <span className="modal-title">
                {lang === 'zh' ? '以下已有对话的配置尚未完整' : 'Incomplete overrides on existing conversations'}
              </span>
            </div>
            <div className="modal-sub">
              {lang === 'zh'
                ? '你正在更改全局接口地址，但下列智能体只覆盖了部分字段、其余仍在继承旧全局配置。直接保存会导致模型与新地址错配或缺少密钥，请为每个智能体选择处理方式：'
                : 'You are changing the global API endpoint, but the agents below only override part of their LLM settings and rely on the old global slot for the rest. Choose how to handle each agent before saving:'}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxHeight: '50vh', overflowY: 'auto' }}>
              {pendingImpact.items.map((item) => {
                const decision = pendingImpact.decisions[item.agent.id] ?? 'use_new_global';
                const missingLabels = item.missingFields.map((f) =>
                  f === 'base_url'
                    ? (lang === 'zh' ? '接口地址' : 'base URL')
                    : f === 'api_key'
                      ? 'API Key'
                      : (lang === 'zh' ? '模型名' : 'model'),
                );
                return (
                  <div key={item.agent.id} className="modal-section" style={{ marginBottom: 0 }}>
                    <div className="modal-section-title">
                      {item.projectName} / {item.agent.display_name} ({item.agent.role_id})
                    </div>
                    <div className="muted-note">
                      {lang === 'zh'
                        ? `当前覆盖：模型=${item.agent.settings.model || '继承全局'}，地址=${item.agent.settings.base_url || '继承全局'}；缺少独立${missingLabels.join('、')}。`
                        : `Current override: model=${item.agent.settings.model || 'inherit'}, base_url=${item.agent.settings.base_url || 'inherit'}; missing standalone ${missingLabels.join(', ')}.`}
                    </div>
                    <label className="field" style={{ marginTop: 8, marginBottom: 4 }}>
                      {lang === 'zh' ? '处理方式' : 'Action'}
                      <select
                        className="input"
                        value={decision}
                        onChange={(e) => {
                          const next = e.target.value as ImpactDecision;
                          setPendingImpact((prev) =>
                            prev ? { ...prev, decisions: { ...prev.decisions, [item.agent.id]: next } } : null,
                          );
                        }}
                      >
                        <option value="use_new_global">
                          {lang === 'zh'
                            ? '覆盖为新全局设置（清除旧模型/地址覆盖）'
                            : 'Use new global config (clear stale overrides)'}
                        </option>
                        <option value="complete_old">
                          {lang === 'zh'
                            ? `补齐旧配置（保留在 ${pendingImpact.oldSlot.url}）`
                            : `Complete old config (keep on ${pendingImpact.oldSlot.url})`}
                        </option>
                        <option value="keep_as_is">
                          {lang === 'zh' ? '暂不改动此智能体' : 'Leave this agent unchanged'}
                        </option>
                      </select>
                    </label>
                    {decision === 'complete_old' && item.missingFields.includes('api_key') && (
                      <label className="field" style={{ marginTop: 6, marginBottom: 0 }}>
                        {lang === 'zh' ? '旧供应商独立 API Key（可选）' : 'Standalone API key for old endpoint (optional)'}
                        <input
                          className="input"
                          type="password"
                          autoComplete="off"
                          placeholder={lang === 'zh' ? '输入旧供应商的 API Key…' : 'Enter API key for old endpoint…'}
                          value={pendingImpact.manualKeys[item.agent.id] ?? ''}
                          onChange={(e) => {
                            const val = e.target.value;
                            setPendingImpact((prev) =>
                              prev ? { ...prev, manualKeys: { ...prev.manualKeys, [item.agent.id]: val } } : null,
                            );
                          }}
                        />
                        <span className="field-hint">
                          {lang === 'zh'
                            ? '注意：单智能体 API Key 当前仅保存在内存中，下次重启 Cloudra 服务后会失效（这是暂时遗留的技术债，后续会补上持久化）。'
                            : 'Note: per-agent API keys are currently memory-only and will expire on the next Cloudra service restart (known technical debt to be persisted in a future update).'}
                        </span>
                      </label>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="modal-actions" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="btn ghost sm"
                disabled={saving !== null}
                onClick={() => setPendingImpact(null)}
              >
                {lang === 'zh' ? '取消' : 'Cancel'}
              </button>
              <button
                type="button"
                className="btn primary sm"
                disabled={saving !== null}
                onClick={() => void confirmPendingImpact()}
              >
                {saving !== null
                  ? (lang === 'zh' ? '保存中…' : 'Saving…')
                  : (lang === 'zh' ? '确认并保存全局设置' : 'Confirm & Save Global Config')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
