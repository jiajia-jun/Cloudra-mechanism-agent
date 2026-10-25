import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import { useI18n } from './i18n';
import type { FsBrowseEntry, FsBrowseShortcut } from './types';

export interface PathPickerModalProps {
  isOpen: boolean;
  title?: string;
  initialPath?: string;
  extraShortcuts?: Array<{ name: string; path: string }>;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export function PathPickerModal({ isOpen, title, initialPath, extraShortcuts = [], onSelect, onClose }: PathPickerModalProps) {
  const { lang } = useI18n();
  const zh = lang === 'zh';
  const [path, setPath] = useState('');
  const [current, setCurrent] = useState('');
  const [selected, setSelected] = useState('');
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<FsBrowseEntry[]>([]);
  const [shortcuts, setShortcuts] = useState<FsBrowseShortcut[]>([]);
  const [hidden, setHidden] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [folderName, setFolderName] = useState('');
  const [saving, setSaving] = useState(false);
  const requestVersion = useRef(0);
  const folderInput = useRef<HTMLInputElement>(null);
  const busy = loading || saving;

  async function browse(target?: string, showHidden = hidden) {
    const version = ++requestVersion.current;
    setLoading(true);
    setError('');
    setSelected('');
    setEntries([]);
    try {
      const result = await api.browseFs(target || undefined, showHidden);
      if (version !== requestVersion.current) return;
      setCurrent(result.current); setPath(result.current); setSelected(result.current);
      setParent(result.parent); setEntries(result.entries.filter((entry) => entry.is_dir));
      setShortcuts(result.shortcuts);
    } catch (err) {
      if (version === requestVersion.current) setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }
  useEffect(() => {
    if (isOpen) {
      setPath(initialPath ?? ''); setCurrent(''); setParent(null); setCreating(false);
      setFolderName(''); setHidden(false);
      void browse(initialPath, false);
    }
    return () => { ++requestVersion.current; };
  }, [isOpen, initialPath]);
  useEffect(() => { if (creating) folderInput.current?.focus(); }, [creating]);
  useEffect(() => {
    if (!isOpen) return;
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !saving) onClose(); };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [isOpen, saving, onClose]);

  async function createFolder() {
    const name = folderName.trim();
    if (!name || !current || busy) return;
    if (name === '.' || name === '..' || name.includes('/') || name.includes('\\')) {
      setError('invalid folder name'); return;
    }
    setSaving(true); setError('');
    try {
      const destination = current === '/' ? `/${name}` : `${current}/${name}`;
      await api.mkdirFs(destination);
      setCreating(false); setFolderName('');
      await browse(destination);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setSaving(false); }
  }
  async function systemPicker() {
    setSaving(true); setError('');
    try {
      const result = await api.systemPickerFs();
      if (result.supported && result.path) { onSelect(result.path); onClose(); }
      else if (!result.supported) setError('system picker unavailable');
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setSaving(false); }
  }
  if (!isOpen) return null;
  const errorText = !zh ? error : error === 'invalid folder name' ? '请输入文件夹名称，不要包含路径。' : error === 'system picker unavailable' ? '当前环境不支持系统选择器，请在此选择文件夹。' : error.toLowerCase().includes('invalid token') ? '登录状态已失效，请重新连接服务。' : '无法读取文件夹，请检查路径与服务连接。';
  const allShortcuts = [...shortcuts, ...extraShortcuts.filter((item) => !shortcuts.some((entry) => entry.path === item.path))];
  const shortcutNames: Record<string, string> = { Home: '主目录', Desktop: '桌面', Documents: '文档', CWD: '工作目录', Root: '根目录' };
  return <div className="modal-backdrop folder-picker-backdrop" onClick={() => { if (!saving) onClose(); }}>
    <div className="modal folder-picker-modal" role="dialog" aria-modal="true" aria-labelledby="folder-picker-title" onClick={(event) => event.stopPropagation()}>
      <div className="folder-picker-heading">
        <h2 id="folder-picker-title">{title || (zh ? '选择文件夹' : 'Choose folder')}</h2>
        <details className="folder-picker-more">
          <summary aria-label={zh ? '更多操作' : 'More actions'}>···</summary>
          <div className="folder-picker-options" onClick={(event) => { if ((event.target as Element).closest('button')) event.currentTarget.closest('details')?.removeAttribute('open'); }}>
            <button type="button" disabled={!current || busy || Boolean(error)} onClick={() => setCreating(true)}>{zh ? '新建文件夹' : 'New folder'}</button>
            <button type="button" disabled={busy} onClick={() => void systemPicker()}>{zh ? '使用系统选择器' : 'Use system picker'}</button>
            <label><input type="checkbox" checked={hidden} disabled={busy} onChange={(event) => { setHidden(event.target.checked); void browse(current || initialPath, event.target.checked); }} />{zh ? '显示隐藏文件夹' : 'Show hidden folders'}</label>
            {allShortcuts.map((shortcut) => <button type="button" key={shortcut.path} disabled={busy} title={shortcut.path} onClick={() => void browse(shortcut.path)}>{zh ? shortcutNames[shortcut.name] ?? shortcut.name : shortcut.name}</button>)}
          </div>
        </details>
        <button type="button" className="new-project-close" aria-label={zh ? '关闭' : 'Close'} disabled={saving} onClick={onClose}>×</button>
      </div>
      <form className="folder-picker-path" onSubmit={(event) => { event.preventDefault(); void browse(path.trim()); }}>
        <button type="button" aria-label={zh ? '上一级' : 'Parent folder'} disabled={!parent || busy} onClick={() => parent && void browse(parent)}>↑</button>
        <input className="input" aria-label={zh ? '文件夹路径' : 'Folder path'} placeholder={zh ? '输入路径，按回车打开' : 'Enter a path and press Enter'} value={path} disabled={saving} onChange={(event) => { setPath(event.target.value); setSelected(''); }} />
        <button type="submit" aria-label={zh ? '打开路径' : 'Open path'} disabled={busy}>↵</button>
      </form>
      {creating && <form className="folder-picker-create" onSubmit={(event) => { event.preventDefault(); void createFolder(); }}><input ref={folderInput} className="input" aria-label={zh ? '文件夹名称' : 'Folder name'} placeholder={zh ? '文件夹名称' : 'Folder name'} value={folderName} disabled={saving} onChange={(event) => setFolderName(event.target.value)} /><button className="btn primary sm" type="submit" disabled={!folderName.trim() || busy}>{zh ? '创建' : 'Create'}</button><button className="btn ghost sm" type="button" disabled={saving} onClick={() => setCreating(false)}>{zh ? '取消' : 'Cancel'}</button></form>}
      <div className="folder-picker-list">
        {loading ? <p className="folder-picker-message">{zh ? '正在读取文件夹…' : 'Loading folders…'}</p> : error ? <div className="folder-picker-message" role="alert"><p>{errorText}</p><button type="button" className="btn ghost sm" disabled={saving} onClick={() => void browse(path.trim())}>{zh ? '重试' : 'Retry'}</button></div> : entries.length === 0 ? <p className="folder-picker-message">{zh ? '此文件夹中没有子文件夹' : 'No folders here'}</p> : entries.map((entry) => <div key={entry.path} className={`folder-picker-row ${selected === entry.path ? 'selected' : ''}`}>
          <button type="button" className="folder-picker-item" title={entry.path} aria-pressed={selected === entry.path} onClick={() => setSelected(entry.path)} onDoubleClick={() => void browse(entry.path)}><svg className="sidebar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 7V5h6l2 2h10v12H3V7Z" /></svg><span>{entry.name}</span></button>
          <button type="button" className="folder-picker-open" aria-label={`${zh ? '打开' : 'Open'} ${entry.name}`} disabled={busy} onClick={() => void browse(entry.path)}>›</button>
        </div>)}
      </div>
      <div className="folder-picker-footer"><span className="folder-picker-selected" title={selected}>{selected ? selected.split('/').filter(Boolean).pop() || '/' : ''}</span><button type="button" className="btn ghost" disabled={saving} onClick={onClose}>{zh ? '取消' : 'Cancel'}</button><button type="button" className="btn primary" disabled={!selected || busy || Boolean(error)} onClick={() => { onSelect(selected); onClose(); }}>{zh ? '选择' : 'Select'}</button></div>
    </div>
  </div>;
}
