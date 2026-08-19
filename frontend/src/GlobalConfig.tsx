/**
 * GlobalConfig — sidebar entry modal for the global LLM config.
 *
 * Edits the two fallback slots (coordinator / follower) of the shared
 * `~/.config/cloudra/config.yaml`.  These are what empty per-agent settings
 * fall back to at request time, so changes are live on the next LLM request.
 * API keys are write-only: the UI never receives the stored value, only
 * `key_set`, and "clear key" sends an explicit empty string.
 */

import { useEffect, useState } from 'react';
import { api } from './api';
import type { RuntimeConfig } from './types';

interface GlobalConfigProps {
  onClose: () => void;
  onToast: (kind: 'ok' | 'error', text: string) => void;
}

interface SlotDraft {
  model: string;
  url: string;
  context_window: string;
  timeout: string;
  key: string;
}

type Slot = 'coordinator' | 'follower';

const EMPTY_DRAFT: SlotDraft = { model: '', url: '', context_window: '', timeout: '', key: '' };

function draftFrom(cfg: RuntimeConfig, slot: Slot): SlotDraft {
  const s = cfg[slot];
  return {
    model: s.model,
    url: s.url,
    context_window: String(s.context_window),
    timeout: String(s.timeout),
    key: '',
  };
}

function SlotSection({
  title,
  hint,
  slot,
  draft,
  savedCfg,
  saving,
  onChange,
  onSave,
}: {
  title: string;
  hint: string;
  slot: Slot;
  draft: SlotDraft;
  savedCfg: RuntimeConfig;
  saving: boolean;
  onChange: (patch: Partial<SlotDraft>) => void;
  onSave: (slot: Slot, clearKey: boolean) => void;
}) {
  const keySet = savedCfg[slot].key_set;
  return (
    <div className="modal-section">
      <div className="modal-section-title">
        {title}
        <span className={`api-key-state ${keySet ? 'ok' : ''}`}>
          key {keySet ? 'set' : 'not set'}
        </span>
      </div>
      <div className="muted-note">{hint}</div>
      <label className="field">
        model
        <input
          className="input"
          value={draft.model}
          onChange={(e) => onChange({ model: e.target.value })}
          placeholder="e.g. deepseek-chat"
        />
      </label>
      <label className="field">
        base_url
        <input
          className="input"
          value={draft.url}
          onChange={(e) => onChange({ url: e.target.value })}
          placeholder="https://…"
        />
      </label>
      <label className="field">
        api key
        <input
          className="input"
          type="password"
          autoComplete="off"
          value={draft.key}
          onChange={(e) => onChange({ key: e.target.value })}
          placeholder={keySet ? 'type a new key to replace…' : 'type to set a key…'}
        />
        <span className="field-hint">
          write-only: the stored key is never shown. Leave empty to keep the current key.
        </span>
      </label>
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
      <div className="modal-actions">
        {keySet && (
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

export default function GlobalConfig({ onClose, onToast }: GlobalConfigProps) {
  const [cfg, setCfg] = useState<RuntimeConfig | null>(null);
  const [drafts, setDrafts] = useState<Record<Slot, SlotDraft>>({
    coordinator: EMPTY_DRAFT,
    follower: EMPTY_DRAFT,
  });
  const [saving, setSaving] = useState<Slot | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .runtimeConfig()
      .then((loaded) => {
        if (cancelled) return;
        setCfg(loaded);
        setDrafts({
          coordinator: draftFrom(loaded, 'coordinator'),
          follower: draftFrom(loaded, 'follower'),
        });
      })
      .catch((e) => {
        if (!cancelled) onToast('error', e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save(slot: Slot, clearKey: boolean) {
    if (!cfg) return;
    setSaving(slot);
    try {
      const d = drafts[slot];
      const changes: Record<string, unknown> = {
        model: d.model.trim(),
        url: d.url.trim(),
      };
      const cw = parseInt(d.context_window, 10);
      if (Number.isFinite(cw) && cw >= 1) changes.context_window = cw;
      const timeout = parseInt(d.timeout, 10);
      if (Number.isFinite(timeout) && timeout >= 1) changes.timeout = timeout;
      if (clearKey) {
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
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
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
            <SlotSection
              title="Coordinator slot"
              hint="Fallback for the coordinator role (per-agent settings take precedence)."
              slot="coordinator"
              draft={drafts.coordinator}
              savedCfg={cfg}
              saving={saving === 'coordinator'}
              onChange={(patch) =>
                setDrafts((prev) => ({ ...prev, coordinator: { ...prev.coordinator, ...patch } }))
              }
              onSave={(s, clearKey) => void save(s, clearKey)}
            />
            <SlotSection
              title="Follower slot"
              hint="Fallback for every non-coordinator role (researcher, dft, md, …)."
              slot="follower"
              draft={drafts.follower}
              savedCfg={cfg}
              saving={saving === 'follower'}
              onChange={(patch) =>
                setDrafts((prev) => ({ ...prev, follower: { ...prev.follower, ...patch } }))
              }
              onSave={(s, clearKey) => void save(s, clearKey)}
            />
          </>
        )}
      </div>
    </div>
  );
}
