import { useState } from 'react';
import { useI18n } from './i18n';

export default function NewProjectModal({ initialDirectory, onBrowse, onCreate, onClose }: {
  initialDirectory: string;
  onBrowse: (directory: string, onSelect: (directory: string) => void) => void;
  onCreate: (name: string, directory: string) => Promise<void>;
  onClose: () => void;
}) {
  const { lang } = useI18n();
  const [name, setName] = useState('');
  const [directory, setDirectory] = useState(initialDirectory);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  async function create() {
    if (!name.trim() || saving) return;
    setSaving(true);
    setError('');
    try {
      await onCreate(name.trim(), directory.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }
  return <div className="modal-backdrop new-project-backdrop" onClick={() => { if (!saving) onClose(); }}>
    <form className="modal new-project-modal" role="dialog" aria-modal="true" aria-labelledby="new-project-title" onClick={(event) => event.stopPropagation()} onSubmit={(event) => { event.preventDefault(); void create(); }} onKeyDown={(event) => {
      if (event.key === 'Escape' && !saving) { event.stopPropagation(); onClose(); }
    }}>
      <div className="new-project-heading">
        <h2 id="new-project-title">{lang === 'zh' ? '新建项目' : 'New project'}</h2>
        <button type="button" className="new-project-close" aria-label={lang === 'zh' ? '关闭' : 'Close'} disabled={saving} onClick={onClose}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button>
      </div>
      <label className="new-project-field">
        <span>{lang === 'zh' ? '项目名称' : 'Project name'}</span>
        <input className="input" autoFocus value={name} disabled={saving} onChange={(event) => setName(event.target.value)} placeholder={lang === 'zh' ? '例如：反应机理研究' : 'e.g. Reaction mechanism study'} />
      </label>
      <div className="new-project-field">
        <label htmlFor="new-project-directory">{lang === 'zh' ? '文件夹' : 'Folder'}</label>
        <div className="new-project-directory-row">
          <input id="new-project-directory" className="input" value={directory} disabled={saving} onChange={(event) => setDirectory(event.target.value)} placeholder={lang === 'zh' ? '默认工作区' : 'Default workspace'} />
          <button type="button" className="btn outline" disabled={saving} onClick={() => onBrowse(directory, setDirectory)}>{lang === 'zh' ? '选择' : 'Choose'}</button>
        </div>
      </div>
      {error && <div className="new-project-error" role="alert">{error}</div>}
      <div className="new-project-actions">
        <button type="button" className="btn ghost" disabled={saving} onClick={onClose}>{lang === 'zh' ? '取消' : 'Cancel'}</button>
        <button type="submit" className="btn primary" disabled={!name.trim() || saving}>{saving ? (lang === 'zh' ? '创建中…' : 'Creating…') : (lang === 'zh' ? '创建' : 'Create')}</button>
      </div>
    </form>
  </div>;
}
