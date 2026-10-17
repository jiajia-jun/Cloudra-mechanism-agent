import { useEffect, useState } from 'react';
import { api } from './api';
import type { RuntimeConfig } from './types';

type SearchProvider = RuntimeConfig['search_provider'];

export default function SearchConfigSection({ config, onSaved, onToast }: {
  config: RuntimeConfig;
  onSaved: (config: RuntimeConfig) => void;
  onToast: (kind: 'ok' | 'error', text: string) => void;
}) {
  const [provider, setProvider] = useState<SearchProvider>(config.search_provider);
  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setProvider(config.search_provider);
    setKey('');
  }, [config.search_provider, config.deepseek_api_key_set]);

  async function save(clearKey = false) {
    setSaving(true);
    setError('');
    try {
      const changes = clearKey ? { deepseek_api_key: '' } : {
        search_provider: provider,
        ...(key.trim() ? { deepseek_api_key: key.trim() } : {}),
      };
      const updated = await api.patchSearchConfig(changes);
      onSaved(updated);
      setProvider(updated.search_provider);
      setKey('');
      onToast('ok', '搜索设置已保存，将用于下一次搜索或网页读取。');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="modal-section" aria-label="网页搜索与读取">
      <div className="modal-section-title">网页搜索与读取（Search / Fetch）</div>
      <div className="muted-note">用于网页搜索和正文读取，所有模型共用。</div>
      <label className="field">搜索服务
        <select className="input" value={provider} disabled={saving}
          onChange={(event) => setProvider(event.target.value as SearchProvider)}>
          <option value="deepseek">DeepSeek（默认）</option>
          <option value="auto">自动选择</option>
          <option value="tavily">Tavily</option>
          <option value="brave">Brave</option>
          <option value="bing">Bing</option>
          <option value="duckduckgo">DuckDuckGo</option>
        </select>
      </label>
      <label className="field">DeepSeek API 凭据
        <input className="input" type="password" autoComplete="new-password" value={key} disabled={saving}
          placeholder={config.deepseek_api_key_set ? '已设置；留空保留原凭据' : '填写 Search / Fetch 共用凭据'}
          onChange={(event) => setKey(event.target.value)} />
        <span className="field-hint">搜索与网页读取共用，保存后不显示原凭据。留空保留当前设置。</span>
      </label>
      {error && <div role="alert">{error}</div>}
      <div className="modal-actions">
        {config.deepseek_api_key_set && <button className="btn ghost sm" disabled={saving}
          onClick={() => void save(true)}>清除 DeepSeek 凭据</button>}
        <button className="btn primary sm" disabled={saving} onClick={() => void save()}>
          {saving ? '保存中…' : '保存搜索设置'}
        </button>
      </div>
    </section>
  );
}
