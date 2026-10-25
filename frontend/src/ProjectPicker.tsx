import { useEffect, useRef, useState } from 'react';
import { useI18n } from './i18n';

export default function ProjectPicker({ value, choices, disabled, onChange, onCreate }: {
  value: string;
  choices: string[];
  disabled: boolean;
  onChange: (workspace: string) => void;
  onCreate: () => void;
}) {
  const { lang } = useI18n();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const folderName = (path: string) => path.split('/').filter(Boolean).pop() || path;
  useEffect(() => {
    if (!open) return;
    searchInput.current?.focus();
    const dismiss = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [open]);
  function choose(workspace: string) {
    onChange(workspace);
    setOpen(false);
    trigger.current?.focus();
  }
  return <div className="project-picker" ref={root} onKeyDown={(event) => {
    if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); }
  }}>
    <button type="button" ref={trigger} className="project-picker-trigger" disabled={disabled} aria-label={lang === 'zh' ? '选择项目' : 'Choose project'} aria-expanded={open} aria-haspopup="dialog" onClick={() => { setSearch(''); setOpen((prev) => !prev); }}>
      <svg className="sidebar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 7V5h6l2 2h10v12H3V7Z" /></svg>
      <span>{value ? folderName(value) : (lang === 'zh' ? '选择项目' : 'Choose project')}</span>{value && <span aria-hidden="true">⌄</span>}
    </button>
    {open && <div className="project-picker-popover" role="dialog" aria-label={lang === 'zh' ? '项目选择' : 'Project selection'}>
      <input className="project-picker-search" ref={searchInput} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={lang === 'zh' ? '搜索项目' : 'Search projects'} aria-label={lang === 'zh' ? '搜索项目' : 'Search projects'} />
      <div className="project-picker-list" role="listbox" aria-label={lang === 'zh' ? '项目列表' : 'Projects'}>
        {choices.filter((path) => path.toLowerCase().includes(search.toLowerCase())).map((path) => <button type="button" key={path} role="option" aria-selected={value === path} className="project-picker-option" title={path} onClick={() => choose(path)}>
          <svg className="sidebar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 7V5h6l2 2h10v12H3V7Z" /></svg>{folderName(path)}
        </button>)}
        {!choices.some((path) => path.toLowerCase().includes(search.toLowerCase())) && <div className="project-picker-empty">{lang === 'zh' ? '没有匹配的项目' : 'No matching projects'}</div>}
      </div>
      <div className="project-picker-footer">
        <button type="button" className="project-picker-option" onClick={() => { setOpen(false); onCreate(); }}><span aria-hidden="true">＋</span>{lang === 'zh' ? '新建项目' : 'New project'}</button>
        <button type="button" className="project-picker-option" onClick={() => choose('')}><span aria-hidden="true">×</span>{lang === 'zh' ? '不在项目中工作' : 'Work without a project'}</button>
      </div>
    </div>}
  </div>;
}
