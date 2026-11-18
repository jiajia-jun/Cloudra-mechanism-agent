import { useEffect, useRef, useState } from 'react';
import type { Project } from './types';
import { Molecule3DViewer } from './Molecule3DViewer';
import { MoleculeBuilder } from './MoleculeBuilder';
import { WorkbenchCoordinateDialog, type CoordinateDialogSelection } from './WorkbenchCoordinateDialog';
import { workbenchApi } from './workbenchApi';
import type { DocumentView, Draft, EditRequest, FragmentEntry, FrameSummary, GeometryView, SaveResult, WorkbenchSource, WorkbenchInputFormat, FrozenCoordinate, ScanCoordinate } from './workbenchTypes';
import { applyGeometry, commonGroups, replacementBond, draftFromFrame, coordinateType, curvePoints, defineFrozenCoordinate, detectImportFormat, measureCoordinate, selectionAfterEdit, toggleAtomSelection, undoDraft, validateSettings } from './molecularWorkbench';
import './molecularWorkbench.css';

export interface MolecularWorkbenchProps { project: Project; source: WorkbenchSource | null; onClose: () => void; onSaved: (result: SaveResult) => void; onContinueInChat?: (result: SaveResult) => void; onError: (error: string) => void }
const fromDocument = (doc: DocumentView): Draft | null => doc.geometry ? ({ geometry: doc.geometry, settings: { ...doc.settings }, sourcePath: doc.source_path, sourceFrame: doc.selected_frame, frozen: doc.frozen_coordinates ?? [], scans: doc.scan_coordinates ?? [] }) : null;
const atomList = (value: string): number[] => value.split(',').flatMap(s => s.trim().split(' ')).filter(Boolean).map(Number);
const metricLabel = { energy_hartree: '能量 / Hartree', rms_force: 'RMS 力', reaction_coordinate: '反应坐标' };
type Metric = keyof typeof metricLabel;
const emptyGeometry = { atoms: [], bonds: [] };
// Preoptimization changes coordinates while retaining the last hand-edited draft.
// Undo restores both so a temporary optimization never hides earlier edits.
type DraftSnapshot = { draft: Draft | null; manualDraft: Draft | null };
const blankSnapshot: DraftSnapshot = { draft: null, manualDraft: null };

function Curve({ frames, metric, selected, onSelect }: { frames: FrameSummary[]; metric: Metric; selected: number; onSelect: (i: number) => void }) {
  const points = curvePoints(frames, metric);
  if (!points.length) return <p className="wb-muted">源文件没有可配对的{metricLabel[metric]}记录。</p>;
  const xs = points.map(p => p.x), ys = points.map(p => p.y);
  const minX = Math.min(...xs), dx = Math.max(...xs)-minX || 1, minY = Math.min(...ys), dy = Math.max(...ys)-minY || 1;
  const xy = (p: typeof points[number]) => [40+(p.x-minX)/dx*640, 150-(p.y-minY)/dy*115];
  return <div className="wb-curve"><svg viewBox="0 0 720 180" role="img" aria-label={metricLabel[metric]}>
    <path d="M40 15 V150 H690" fill="none" stroke="currentColor" opacity=".25" />
    <polyline points={points.map(p => xy(p).join(',')).join(' ')} fill="none" stroke="var(--wb-accent)" strokeWidth="1.5" />
    {points.map(p => { const [x,y] = xy(p); return <circle key={p.frame} cx={x} cy={y} r={selected === p.frame ? 6 : 4} fill={selected === p.frame ? '#f59e0b' : 'var(--wb-accent)'} tabIndex={0} role="button" aria-label={`帧 ${p.frame+1}: ${p.y}`} onClick={() => onSelect(p.frame)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onSelect(p.frame); }}><title>帧 {p.frame+1} · {p.y}</title></circle>; })}
    <text x="40" y="175" fill="currentColor" fontSize="11">{minX.toPrecision(5)}</text><text x="620" y="175" fill="currentColor" fontSize="11">{Math.max(...xs).toPrecision(5)}</text>
    <text x="45" y="16" fill="currentColor" fontSize="11">{minY.toPrecision(7)} — {Math.max(...ys).toPrecision(7)}</text>
  </svg><span className="wb-muted">横轴：{points[0].useCoordinate ? '实际坐标' : '帧序号（从 0 起）'} · 点击点查看对应结构</span></div>;
}

export function MolecularWorkbench({ project, source, onClose, onSaved, onContinueInChat, onError }: MolecularWorkbenchProps) {
  const [doc, setDoc] = useState<DocumentView | null>(null);
  const [current, setCurrent] = useState(blankSnapshot);
  const { draft } = current;
  const [history, setHistory] = useState<DraftSnapshot[]>([]);
  const [frame, setFrame] = useState(0);
  const [frameGeometry, setFrameGeometry] = useState<GeometryView | null>(null);
  const [view, setView] = useState<'draft'|'source'>('draft');
  const [canvasMode, setCanvasMode] = useState<'edit' | 'select'>(source ? 'select' : 'edit');
  const [brush, setBrush] = useState('atom');
  const [element, setElement] = useState('C');
  const editInFlight = useRef(false);
  const [selection, setSelection] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [discardAction, setDiscardAction] = useState<{kind:'close'|'import'|'source'|'blank'; source?:WorkbenchSource|null} | null>(null);
  const [inputKind, setInputKind] = useState<WorkbenchInputFormat|'path'>('smiles');
  const [input, setInput] = useState('');
  const [title, setTitle] = useState('');
  const baseline = useRef({ snapshot: blankSnapshot, title: '' });
  const manualChanges = !!draft && (current.manualDraft !== baseline.current.snapshot.manualDraft || title !== baseline.current.title);
  const dirty = !!draft && (manualChanges || draft !== baseline.current.snapshot.draft);
  const [coordinateDialog, setCoordinateDialog] = useState<CoordinateDialogSelection | null>(null);
  const [showCoordinates, setShowCoordinates] = useState(true);
  const [mirrorAtoms, setMirrorAtoms] = useState('');
  const [plane, setPlane] = useState<'xy'|'xz'|'yz'>('yz');
  const [fragmentSmiles, setFragmentSmiles] = useState('');
  const [fragmentName, setFragmentName] = useState('');
  const [attachment, setAttachment] = useState('');
  const [fragmentSearch, setFragmentSearch] = useState('');
  const [fragments, setFragments] = useState<FragmentEntry[]>([]);
  const [fragmentPreview, setFragmentPreview] = useState<GeometryView | null>(null);
  const [preview, setPreview] = useState<{geometry: GeometryView; base: Draft; fragment?: string} | null>(null);
  const [metric, setMetric] = useState<Metric>('energy_hartree');
  const [modeIndex, setModeIndex] = useState(-1);
  const [modePlaying, setModePlaying] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [generateInput, setGenerateInput] = useState(false);
  const [scanAxis, setScanAxis] = useState(0);
  const [scanSlice, setScanSlice] = useState<Record<string,string>>({});
  const requestVersion = useRef(0);
  const fragmentPreviewVersion = useRef(0);
  const frameCache = useRef(new Map<number, GeometryView>());
  const closed = useRef(false);
  const loadedProject = useRef<string | null>(null);
  const onErrorRef = useRef(onError); onErrorRef.current = onError;
  const fail = (e: unknown) => { const text = e instanceof Error ? e.message : String(e); setError(text); onErrorRef.current(text); };
  const refreshFragments = async () => {
    const version = requestVersion.current;
    const result = await workbenchApi.fragments(project.id);
    if (!closed.current && version === requestVersion.current) setFragments(result.fragments);
  };
  const installDocument = (result: DocumentView, source: WorkbenchSource) => {
    const opened = fromDocument(result);
    const snapshot = { draft: opened, manualDraft: opened };
    baseline.current = { snapshot: source.smiles || source.input_text ? blankSnapshot : snapshot, title: result.title };
    setCurrent(snapshot);
    frameCache.current = new Map(result.geometry ? [[result.selected_frame, result.geometry]] : []);
    setDoc(result); setFrame(result.selected_frame); setFrameGeometry(result.geometry); setTitle(result.title); setView('draft'); setMirrorAtoms('');
    setScanAxis(0); setScanSlice({}); setCanvasMode('select');
  };

  useEffect(() => {
    closed.current = false;
    return () => { closed.current = true; requestVersion.current++; };
  }, []);
  const loadSource = (nextSource: WorkbenchSource | null) => {
    setDiscardAction(null); setCoordinateDialog(null);
    loadedProject.current = project.id;
    setCanvasMode(nextSource ? 'select' : 'edit');
    const version = ++requestVersion.current;
    frameCache.current.clear();
    baseline.current = { snapshot: blankSnapshot, title: '' };
    setDoc(null); setCurrent(blankSnapshot); setHistory([]); setSelection([]); setPreview(null); setPlaying(false); setModeIndex(-1); setModePlaying(false); setError(''); setMessage(''); setFragmentPreview(null);
    setFrame(0); setFrameGeometry(null); setView('draft'); setTitle(''); setGenerateInput(false); setMirrorAtoms('');
    if (nextSource) {
      setBusy(true);
      workbenchApi.open(project.id, nextSource).then(result => {
        if (version !== requestVersion.current || closed.current) return;
        installDocument(result, nextSource);
      }).catch(e => { if (version === requestVersion.current) fail(e); }).finally(() => { if (version === requestVersion.current) setBusy(false); });
    } else setBusy(false);
    workbenchApi.fragments(project.id).then(r => { if (version === requestVersion.current) setFragments(r.fragments); }).catch(e => { if (version === requestVersion.current) fail(e); });
  };
  useEffect(() => {
    if (loadedProject.current === project.id && manualChanges) { setDiscardAction({kind:'source',source}); return; }
    loadSource(source);
  }, [project.id, source]);

  const originalGeometry = view === 'source' ? frameGeometry : draft?.geometry;
  const mode = !preview && modeIndex >= 0 ? doc?.modes[modeIndex] : null;
  const geometry = preview?.geometry ?? (mode ? doc?.modes_reference_geometry : originalGeometry) ?? originalGeometry;
  const visibleSelection = preview ? selectionAfterEdit(selection, preview.geometry.changes) : selection;
  const visibleDraft = view === 'draft' ? (preview ? applyGeometry(preview.base, preview.geometry).draft : draft) : null;
  const measured = geometry ? measureCoordinate(geometry.atoms, visibleSelection) : null;
  const coordType = coordinateType(visibleSelection.length);
  const unit = visibleSelection.length === 2 ? 'Å' : '°';
  const editable = view === 'draft' && !!originalGeometry && !mode && !preview && !busy;
  const builderDisabled = view !== 'draft' || busy || !!preview || !!mode || playing || (!originalGeometry && !!doc);
  const operationBase = (): Draft => {
    if (!originalGeometry) throw new Error('请先打开有实际坐标的结构帧。');
    if (!draft) return {geometry:originalGeometry,settings:{...doc?.settings},sourcePath:doc?.source_path,sourceFrame:frame,frozen:doc?.frozen_coordinates??[],scans:doc?.scan_coordinates??[]};
    if (view !== 'source') return draft;
    if (draft.atomMappingChanged && (draft.frozen.length || draft.scans.length)) setMessage('已从原始帧建立新稿；之前拓扑编辑中的冻结／扫描定义保留在撤销记录中，请为此帧重新定义。');
    return draftFromFrame(draft,originalGeometry,doc?.source_path,frame);
  };
  const rememberDraft = (next: Draft, preoptimized = false) => {
    setHistory(h => [...h, current]);
    setCurrent({ draft: next, manualDraft: preoptimized ? current.manualDraft : next });
  };
  const commit = (next: Draft, nextSelection: number[] = [], preoptimized = false) => {
    rememberDraft(next, preoptimized);
    setView('draft'); setPreview(null); setModeIndex(-1); setModePlaying(false); setPlaying(false); setSelection(nextSelection);
  };
  const updateSettings = (settings: Draft['settings']) => {
    if (!draft) return;
    rememberDraft({...draft,settings});
  };
  const perform = async (action: Omit<EditRequest,'molecule'>, { fragment, immediate }: { fragment?: string; immediate?: boolean } = {}) => {
    if (editInFlight.current) return false;
    editInFlight.current = true;
    setError(''); setMessage(''); setBusy(true); setPlaying(false);
    const version = requestVersion.current;
    try {
      const base = !originalGeometry && !doc && (action.action === 'add_atom' || action.action === 'add_group') ? null : operationBase();
      const edited = await workbenchApi.edit(project.id, { ...action, molecule: base?.geometry.molecule });
      if (version !== requestVersion.current || closed.current) return false;
      if (base && !immediate) {
        setPreview({ geometry: edited, base, fragment });
        return true;
      }
      const result = base ? applyGeometry(base, edited) : {
        draft: { geometry: edited, settings: {}, frozen: [], scans: [] }, invalidated: 0,
      };
      commit(result.draft, selectionAfterEdit(selection, edited.changes), action.action === 'preoptimize');
      setCoordinateDialog(null);
      const notes = [...(edited.warnings ?? [])];
      if (result.invalidated) notes.push(`已移除 ${result.invalidated} 条引用被删除原子的冻结／扫描定义。`);
      if (notes.length) setMessage(notes.join(' '));
      return true;
    } catch(e) { if (version === requestVersion.current && !closed.current) fail(e); return false; } finally { editInFlight.current = false; if (version === requestVersion.current && !closed.current) setBusy(false); }
  };
  const editingCanvas = canvasMode === 'edit' && view === 'draft' && !preview && !mode && !playing;
  const changeCanvasMode = (next: 'edit' | 'select') => {
    setCanvasMode(next); setSelection([]); setCoordinateDialog(null);
  };
  const place = (anchor?: number, position?: [number, number, number]) => {
    if (!editingCanvas || builderDisabled) return;
    const atoms = anchor == null ? [] : [anchor];
    const placement = position ? { atoms, position } : { atoms };
    if (brush === 'atom') {
      if (element.trim()) void perform({ action: 'add_atom', element: element.trim(), order: 1, ...placement }, { immediate: true });
    } else {
      const smiles = brush === 'custom' ? fragmentSmiles.trim() : brush;
      if (smiles) void perform({ action: 'add_group', smiles, ...placement,
        ...(brush === 'custom' && attachment ? { attachment_atom: Number(attachment) } : {}),
      }, { immediate: true });
    }
  };
  const pickAtom = (index: number) => {
    if (busy || preview || mode || playing) return;
    if (editingCanvas) place(index);
    else { setSelection(s => toggleAtomSelection(s, index)); setCoordinateDialog(null); }
  };
  const confirmPreview = async () => {
    if (!preview) return;
    const version = requestVersion.current;
    const result = applyGeometry(preview.base,preview.geometry);
    commit(result.draft);
    setMessage(result.invalidated ? `已移除 ${result.invalidated} 条引用被删除原子的冻结／扫描定义，请重新定义。` : '已确认修改。');
    if (preview.fragment) {
      try { await workbenchApi.useFragment(project.id,preview.geometry.changes?.fragment_smiles ?? preview.fragment,fragmentName); if (version === requestVersion.current && !closed.current) await refreshFragments(); }
      catch(e) { if(version === requestVersion.current && !closed.current) fail(e); }
    }
  };
  const readFrame = async (index: number) => {
    const cached = frameCache.current.get(index);
    if (cached) return cached;
    const version = requestVersion.current;
    const geometry = await workbenchApi.frame(project.id,doc!.document_id,index);
    if (version === requestVersion.current && !closed.current) frameCache.current.set(index,geometry);
    return geometry;
  };
  const showFrame = (index: number, geometry: GeometryView | null) => {
    setFrame(index); setFrameGeometry(geometry); setView('source'); setSelection([]); setCoordinateDialog(null);
  };
  const playableFrames = doc?.frames.flatMap((summary,index)=>summary.has_geometry === false ? [] : [index]) ?? [];
  const selectFrame = async (index: number) => {
    if (!doc || busy) return;
    const version = requestVersion.current;
    setPlaying(false); setError(''); setMessage(''); setPreview(null); setModeIndex(-1); setModePlaying(false);
    if (doc.frames[index]?.has_geometry === false) {
      showFrame(index,null); setMessage('此原生采样点未输出几何，保留标量事实；请选取有实际坐标的帧进行编辑。'); return;
    }
    setBusy(true);
    try {
      const geometry = await readFrame(index);
      if (version === requestVersion.current && !closed.current) showFrame(index,geometry);
    } catch(e) { if (version === requestVersion.current && !closed.current) fail(e); }
    finally { if (version === requestVersion.current && !closed.current) setBusy(false); }
  };
  const togglePlayback = async () => {
    if (playing) { setPlaying(false); return; }
    if (!doc || busy || playableFrames.length < 2) return;
    const version = requestVersion.current;
    setBusy(true); setError(''); setMessage('正在缓存动画帧…');
    let next = 0;
    try {
      // Fetch once before playback, with four requests at most. The timer never waits on I/O.
      await Promise.all(Array.from({length:Math.min(4,playableFrames.length)},async () => {
        while (next < playableFrames.length && version === requestVersion.current && !closed.current) {
          await readFrame(playableFrames[next++]);
        }
      }));
      if (version !== requestVersion.current || closed.current) return;
      const index = playableFrames.includes(frame) ? frame : playableFrames[0];
      showFrame(index,frameCache.current.get(index)!);
      setPreview(null); setModeIndex(-1); setModePlaying(false); setMessage(''); setPlaying(true);
    } catch(e) { if (version === requestVersion.current && !closed.current) { setMessage(''); fail(e); } }
    finally { if (version === requestVersion.current && !closed.current) setBusy(false); }
  };
  useEffect(() => {
    if (!playing || busy || playableFrames.length < 2) return;
    let position = playableFrames.indexOf(frame);
    const timer = window.setInterval(() => {
      position = (position+1)%playableFrames.length;
      const index = playableFrames[position];
      showFrame(index,frameCache.current.get(index)!);
    },100);
    return () => window.clearInterval(timer);
  },[playing,busy,doc]);
  const close = () => { if (manualChanges) setDiscardAction({kind:'close'}); else onClose(); };
  const switchView = (next: 'draft' | 'source') => {
    setPlaying(false); setView(next); setModeIndex(-1); setModePlaying(false); setSelection([]); setCoordinateDialog(null);
  };
  const startBlank = (confirmed = false) => {
    if (manualChanges && !confirmed) { setDiscardAction({ kind: 'blank' }); return; }
    loadSource(null);
  };
  const importSource = async (confirmed = false) => {
    if (!input.trim()) return;
    if (manualChanges && !confirmed) { setDiscardAction({kind:'import'}); return; }
    setDiscardAction(null);
    setBusy(true); setError(''); setPlaying(false);
    const version = ++requestVersion.current;
    try {
      const source = inputKind === 'path' ? {path:input.trim()} : inputKind === 'smiles' ? {smiles:input.trim()} : {input_text:input,input_format:inputKind};
      const result = await workbenchApi.open(project.id, source);
      if(version !== requestVersion.current || closed.current) return;
      installDocument(result, source); setHistory([]); setSelection([]); setPreview(null); setModeIndex(-1); setModePlaying(false);
    } catch(e) { if (version === requestVersion.current && !closed.current) fail(e); } finally { if (version === requestVersion.current && !closed.current) setBusy(false); }
  };
  const openCoordinateDialog = (next: CoordinateDialogSelection = { atoms: selection }) => {
    if (!editable || !originalGeometry || measureCoordinate(originalGeometry.atoms, next.atoms) == null) return;
    setError(''); setCanvasMode('select'); setSelection(next.atoms); setCoordinateDialog(next);
  };
  const defineCoordinate = (coordinate: FrozenCoordinate | ScanCoordinate) => {
    const base = operationBase();
    if ('value' in coordinate) {
      commit(defineFrozenCoordinate(base, coordinate.atoms, String(coordinate.value)));
    } else {
      commit({ ...base, scans: [...base.scans.filter(c => c.atoms.join(',') !== coordinate.atoms.join(',')), coordinate] });
    }
    setCoordinateDialog(null);
  };
  const save = async (continueInChat = false) => {
    if (!editable || !draft?.geometry.atoms.length) return;
    const invalid = validateSettings(draft.settings,generateInput);
    if (invalid) { fail(invalid); return; }
    setBusy(true); setError('');
    const version = requestVersion.current;
    try {
      const result = await workbenchApi.save(project.id,{title:title || 'molecule',molecule:draft.geometry.molecule,source_path:draft.sourcePath,source_frame:draft.sourceFrame,settings:draft.settings,frozen_coordinates:draft.frozen,scan_coordinates:draft.scans,generate_input:generateInput});
      if(version !== requestVersion.current || closed.current) return;
      const saved = { ...current, draft: { ...draft, geometry: result.geometry } };
      baseline.current = { snapshot: saved, title };
      setCurrent(saved); setMessage(`${result.message} ${result.path}`); onSaved(result);
      if (continueInChat) onContinueInChat?.(result);
    } catch(e) { if (version === requestVersion.current && !closed.current) fail(e); } finally { if (version === requestVersion.current && !closed.current) setBusy(false); }
  };
  const csv = async () => {
    if (!doc) return;
    try { const data = await workbenchApi.csv(project.id,doc.document_id); const url = URL.createObjectURL(new Blob([data],{type:'text/csv;charset=utf-8'})); const a = document.createElement('a'); a.href=url; a.download=`${doc.title || 'calculation'}.csv`; a.click(); window.setTimeout(() => URL.revokeObjectURL(url),1000); } catch(e) { fail(e); }
  };
  const selectFragment = (value: string | FragmentEntry) => {
    ++fragmentPreviewVersion.current;
    const entry = typeof value === 'string' ? null : value;
    setFragmentSmiles(typeof value === 'string' ? value : value.smiles);
    setFragmentPreview(entry?.geometry ?? null);
    setAttachment(entry?.attachment_atom ? String(entry.attachment_atom) : '');
    setFragmentName(entry?.name ?? '');
  };
  const previewFragment = async () => {
    setBusy(true); setError('');
    const version=requestVersion.current;
    const fragmentVersion=++fragmentPreviewVersion.current;
    try {
      const result=await workbenchApi.previewFragment(project.id,fragmentSmiles,fragmentName);
      if(version === requestVersion.current && fragmentVersion === fragmentPreviewVersion.current && !closed.current) setFragmentPreview(result);
    } catch(e) {
      if(version === requestVersion.current && fragmentVersion === fragmentPreviewVersion.current && !closed.current) fail(e);
    } finally {
      if(version === requestVersion.current && !closed.current) setBusy(false);
    }
  };
  const replaceAtoms = replacementBond(originalGeometry, selection);
  const frameFacts = doc?.frames[frame];
  const scanDimensions = Math.max(0,...(doc?.frames.map(f => f.scan_coordinates?.length ?? 0) ?? []));
  const scanFrames = doc?.frames.filter(f => f.scan_coordinates?.length && Object.entries(scanSlice).every(([dim,value]) => Number(dim) === scanAxis || !value || f.scan_coordinates?.[Number(dim)] === Number(value))) ?? [];

  return <div className="wb-backdrop"><section className="molecular-workbench" role="dialog" aria-modal="true" aria-label="分子工作台">
    <header className="wb-header"><div><strong>分子工作台</strong><span className="wb-muted">{project.name} · {dirty ? '编辑稿未保存' : '结构与计算查看'}</span></div><button className="btn ghost sm" onClick={close}>关闭 ✕</button></header>
    <div className="wb-open"><select aria-label="来源类型" value={inputKind} onChange={e=>setInputKind(e.target.value as typeof inputKind)}><option value="smiles">SMILES 新建</option><option value="path">项目文件路径</option><option value="xyz">XYZ 文本</option><option value="mol">MOL 文本</option><option value="sdf">SDF 文本</option><option value="log">Gaussian／ORCA 日志 (.log)</option><option value="out">计算输出 (.out)</option><option value="gjf">Gaussian 输入 (.gjf)</option><option value="com">Gaussian 输入 (.com)</option><option value="inp">ORCA 输入 (.inp)</option><option value="pdb">PDB 文本</option><option value="cif">CIF 文本</option></select>
      <textarea aria-label="结构来源" placeholder={inputKind === 'path' ? '项目内文件路径，可打开 Gaussian／ORCA／结构文件' : '粘贴 SMILES 或结构文本'} value={input} onChange={e=>setInput(e.target.value)} rows={2}/>
      <div className="wb-open-actions">
        <button className="btn primary sm" disabled={busy || !input.trim()} onClick={()=>void importSource()}>新建／打开</button>
        <label className="btn outline sm wb-file">本地结构／计算文件<input type="file" accept=".xyz,.mol,.sdf,.smi,.smiles,.log,.out,.gjf,.com,.inp,.pdb,.cif" onChange={e=>{ const file=e.target.files?.[0]; if (!file) return; const format=detectImportFormat(file.name); if(!format){fail('不支持的文件类型。');return;} setInputKind(format); void file.text().then(setInput).catch(fail); }}/></label>
      </div>
    </div>
    {discardAction && <div className="wb-preview" role="alert">
      <span>编辑稿尚未保存。继续将放弃这些修改。</span>
      <div className="wb-banner-actions">
        <button className="btn yellow sm" onClick={() => {
          setDiscardAction(null);
          if (discardAction.kind === 'close') onClose();
          else if (discardAction.kind === 'import') void importSource(true);
          else if (discardAction.kind === 'blank') startBlank(true);
          else loadSource(discardAction.source ?? null);
        }}>继续并放弃修改</button>
        <button className="btn outline sm" onClick={() => setDiscardAction(null)}>保留编辑稿</button>
      </div>
    </div>}
    <div className="wb-body"><main className="wb-main">
      <div className="wb-toolbar">
        <div className="wb-view-switcher">
          <button className={`btn outline sm ${view === 'draft' ? 'active' : ''}`} disabled={!draft || !!preview} onClick={() => switchView('draft')}>{view === 'source' ? '返回编辑稿' : '编辑稿'}</button>
          <button className={`btn outline sm ${view === 'source' ? 'active' : ''}`} disabled={!doc || !!preview} onClick={() => switchView('source')}>来源帧</button>
        </div>
        <button className="btn outline sm" disabled={busy} onClick={() => startBlank()}>新建空白分子</button>
        <button className="btn outline sm wb-undo-btn" disabled={!history.length || busy || !!preview} title="撤销上一次编辑"
          onClick={() => {
            const restored = undoDraft(history, current);
            setCurrent(restored.draft); setHistory(restored.history); setView('draft');
            setModeIndex(-1); setModePlaying(false); setPlaying(false); setSelection([]); setCoordinateDialog(null); setMessage(''); setError('');
          }}>撤销</button>
        {view === 'source' && <button className="btn green sm" disabled={!frameGeometry || busy || !!preview || !!mode || playing} onClick={() => { try { commit(operationBase()); } catch (e) { fail(e); } }}>以此帧建立编辑稿</button>}
        <button className="btn primary sm" disabled={!editable || !draft?.geometry.atoms.length} onClick={()=>void save()}>保存编辑稿到项目</button>
        {onContinueInChat && <button className="btn outline sm" disabled={!editable || !draft?.geometry.atoms.length} onClick={()=>void save(true)}>保存并带回当前对话</button>}
        <span className="wb-muted wb-view-desc">
          {mode ? '简正模使用其真实参考几何' : preview ? '修改预览' : view === 'source' ? `来源帧 ${frame + 1}（只读）；编辑或保存请先建立编辑稿`
            : draft?.sourcePath ? `派生自 ${draft.sourcePath} · 帧 ${(draft.sourceFrame ?? 0) + 1}` : '手工建模'}
        </span>
      </div>
      <MoleculeBuilder editing={editingCanvas} onModeChange={changeCanvasMode} brush={brush} onBrushChange={setBrush}
        element={element} onElementChange={setElement} fragments={fragments} customSmiles={fragmentSmiles} onCustomSmilesChange={selectFragment}
        attachment={attachment} onAttachmentChange={setAttachment} onPlace={()=>place()} geometry={originalGeometry} selection={selection} disabled={builderDisabled} hasFrozenCoordinates={!!draft?.frozen.length}
        onEdit={action => void perform(action, { immediate: true })} />
      {!editingCanvas && <div className="wb-selection-bar" aria-label="选择与测量">
        <div className="wb-selected-chips">{visibleSelection.map((i,n)=><button disabled={busy || !!preview || !!mode} key={i} className="wb-atom-tag" onClick={()=>setSelection(s=>s.filter(a=>a!==i))} title="点击取消选择"><span className="wb-atom-order">{n+1}</span> {geometry?.atoms.find(a=>a.index===i)?.symbol}{i} <span className="wb-remove">×</span></button>)}</div>
        <span className="wb-selection-measure">{coordType ? `${{bond:'距离',angle:'键角',dihedral:'二面角'}[coordType]}：${measured == null ? '当前几何无法定义' : `${measured.toFixed(5)} ${unit}`}` : '依次选择 2／3／4 个原子以编辑距离／键角／二面角'}</span>
        {coordType && <button className="btn green sm" disabled={!editable || measured == null} onClick={()=>openCoordinateDialog()}>编辑{{bond:'距离',angle:'键角',dihedral:'二面角'}[coordType]}</button>}
        {visibleSelection.length > 0 && <button className="btn ghost sm" disabled={busy || !!preview || !!mode} onClick={()=>setSelection([])}>清空</button>}
      </div>}
      {geometry || !doc ? <Molecule3DViewer key={`${requestVersion.current}:${doc?.document_id ?? 'blank'}`} geometry={geometry ?? emptyGeometry} preserveView editing={editingCanvas} title={view === 'source' ? doc?.title : title} selectedAtoms={visibleSelection} onAtomPick={pickAtom} onBackgroundClick={position=>{
        if (busy || preview || mode || playing) return;
        if (editingCanvas) place(undefined, position);
        else { setSelection([]); setCoordinateDialog(null); }
      }} modeDisplacements={mode?.displacements} modePlaying={modePlaying} coordinateHighlights={showCoordinates && visibleDraft && !(view==='source' && visibleDraft.atomMappingChanged) ? [...visibleDraft.frozen.map(c=>c.atoms),...visibleDraft.scans.map(c=>c.atoms)] : []} className="wb-viewer"/> : <div className="wb-empty">
        此点没有可用的原生几何，选择其他帧查看结构。
      </div>}
      {error && <div className="wb-error" role="alert">{error}</div>}{message && <div className="wb-message" role="status">{message}</div>}{busy && <div className="wb-busy-indicator wb-muted" role="status">正在处理…</div>}
      {geometry?.optimization && <p className="wb-optimization" role="status"><strong>{geometry.optimization.force_field} · {geometry.optimization.converged ? '已收敛' : '未收敛'}</strong> 能量 {geometry.optimization.initial_energy.toFixed(4)} → {geometry.optimization.final_energy.toFixed(4)} {geometry.optimization.energy_unit}（Δ {(geometry.optimization.final_energy-geometry.optimization.initial_energy).toFixed(4)}）</p>}
      {preview?.geometry.warnings?.map((warning,index)=><p className="wb-muted" key={index}>{warning}</p>)}
      {preview && <div className="wb-preview"><span>检查移动部分、连接关系和镜像结果。</span><div className="wb-banner-actions"><button className="btn primary sm" onClick={()=>void confirmPreview()}>确认修改</button><button className="btn outline sm" onClick={()=>setPreview(null)}>取消预览</button></div></div>}
      {doc && <section className="wb-section"><div className="wb-toolbar wb-trajectory-toolbar"><strong>{doc.task_type || '来源结构'} · {doc.frames.length} 帧</strong><div className="wb-trajectory-actions"><button className={`btn ${playing ? 'yellow' : 'outline'} sm`} disabled={busy || playableFrames.length<2} onClick={()=>void togglePlayback()}>{playing?'暂停帧播放':'播放各帧'}</button><button className="btn outline sm" onClick={()=>void csv()}>导出 CSV</button></div></div>
        <label>来源帧 {frame+1} / {doc.frames.length}<input aria-label="来源帧" type="range" min={0} max={Math.max(0,doc.frames.length-1)} value={frame} disabled={busy} onChange={e=>{setPlaying(false);void selectFrame(Number(e.target.value));}}/></label>
        <p className="wb-facts">步 {frameFacts?.step ?? '未知'} · 能量 {frameFacts?.energy_hartree ?? '未知'} Hartree · RMS 力 {frameFacts?.rms_force ?? '未知'} {frameFacts?.force_unit ?? ''} · 最大力 {frameFacts?.max_force ?? '未知'} {frameFacts?.force_unit ?? ''} · {frameFacts?.converged === true ? '原生记录已收敛' : frameFacts?.converged === false ? '原生记录未收敛' : '收敛状态未知'}{frameFacts?.path_number != null && ` · 路径 ${frameFacts.path_number}`}</p>
        <select aria-label="曲线指标" value={metric} onChange={e=>setMetric(e.target.value as Metric)}>{Object.entries(metricLabel).map(([key,value])=><option key={key} value={key}>{value}</option>)}</select><Curve frames={doc.frames} metric={metric} selected={frame} onSelect={i=>{setPlaying(false);void selectFrame(i);}}/>
        {scanDimensions>0 && <details open><summary>扫描／势能面采样点（{scanDimensions} 维）</summary><div className="wb-toolbar"><label>横轴<select value={scanAxis} onChange={e=>setScanAxis(Number(e.target.value))}>{Array.from({length:scanDimensions},(_,i)=><option key={i} value={i}>坐标 {i+1}</option>)}</select></label>{Array.from({length:scanDimensions},(_,i)=>i===scanAxis?null:<label key={i}>固定坐标 {i+1}<select value={scanSlice[String(i)]??''} onChange={e=>setScanSlice(s=>({...s,[String(i)]:e.target.value}))}><option value="">所有采样</option>{[...new Set(doc.frames.flatMap(f=>f.scan_coordinates?.[i] == null?[]:[f.scan_coordinates[i]]))].sort((a,b)=>a-b).map(v=><option key={v} value={v}>{v}</option>)}</select></label>)}</div><Curve frames={scanFrames.map(f=>({...f,reaction_coordinate:f.scan_coordinates?.[scanAxis]}))} metric="energy_hartree" selected={frame} onSelect={i=>void selectFrame(i)}/><div className="wb-scan-points">{scanFrames.map(f=><button key={f.index} className={`btn outline sm ${frame===f.index?'active':''}`} onClick={()=>void selectFrame(doc.frames.indexOf(f))}>帧 {doc.frames.indexOf(f)+1}: ({f.scan_coordinates?.join(', ')}) · {f.energy_hartree ?? '?'} Eh</button>)}</div></details>}
        <div className="wb-toolbar"><label>实际频率<select aria-label="实际简正模" value={modeIndex} disabled={busy || !!preview} onChange={e=>{setModeIndex(Number(e.target.value));setModePlaying(false);setPlaying(false);setSelection([]);}}><option value={-1}>显示当前结构</option>{doc.modes.map((m,i)=><option key={i} value={i} disabled={!doc.modes_reference_geometry}>模式 {i+1}: {m.frequency_cm} cm⁻¹{m.frequency_cm<0?'（虚频）':''}</option>)}</select></label><button className={`btn ${modePlaying ? 'yellow' : 'outline'} sm`} disabled={!mode || !doc.modes_reference_geometry} onClick={()=>setModePlaying(!modePlaying)}>{modePlaying?'暂停模式':'播放真实位移'}</button>{!doc.modes.length && <span className="wb-muted">未取得配对的频率与位移。</span>}</div>
        {doc.warnings.map((w,i)=><p className="wb-muted" key={i}>{w}</p>)}
      </section>}
    </main><aside className="wb-sidebar">
      {draft && <fieldset disabled={!editable} className="wb-section wb-settings"><h3>编辑稿设置</h3><label>结构名称<input value={title} onChange={e=>setTitle(e.target.value)}/></label>
        <p className="wb-muted">保存当前编辑稿到项目，保留来源与设置，并通知主 Agent。</p>
        <label className="wb-check"><input type="checkbox" checked={generateInput} onChange={e=>setGenerateInput(e.target.checked)}/>同时生成原生计算输入</label>
        {generateInput && <><label>引擎<select aria-label="引擎" value={draft.settings.engine ?? ''} onChange={e=>updateSettings({...draft.settings,engine:e.target.value as 'gaussian'|'orca'})}><option value="" disabled>请选择</option><option value="gaussian">Gaussian</option><option value="orca">ORCA</option></select></label>
        {(['method','basis_set','keywords'] as const).map(key=><label key={key}>{{method:'方法',basis_set:'基组（可明确留空）',keywords:'原生关键词'}[key]}<input value={String(draft.settings[key]??'')} onChange={e=>updateSettings({...draft.settings,[key]:e.target.value})}/></label>)}
        <label className="wb-check"><input type="checkbox" checked={draft.settings.basis_set === ''} onChange={e=>updateSettings({...draft.settings,basis_set:e.target.checked?'':undefined})}/>明确使用无需独立基组的方法</label>
        <div className="wb-row">{(['charge','multiplicity'] as const).map(key=><label key={key}>{key==='charge'?'电荷':'多重度'}<input type="number" value={draft.settings[key]??''} onChange={e=>updateSettings({...draft.settings,[key]:e.target.value===''?null:Number(e.target.value)})}/></label>)}</div>
        <label>计算类型<select value={Object.keys(draft.settings.task_type?.[0]??{})[0]??''} onChange={e=>updateSettings({...draft.settings,task_type:[{[e.target.value]:null}]})}><option value="" disabled>请选择</option><option value="opt">几何优化</option><option value="freq">频率</option><option value="irc">IRC</option><option value="sp">单点能</option></select></label></>}
      </fieldset>}
      <section className="wb-section"><h3>原子列表</h3><p>{editingCanvas ? '点击列表中的原子也可以从它接出一根单键。' : '点击切换选择，点击画布空白处清空。编号标出选择顺序。'}</p>
        <div className="wb-atoms" aria-label="原子列表">{geometry?.atoms.map(atom =>
          <button key={atom.atom_id ?? atom.index} disabled={busy || !!mode || !!preview}
            aria-label={`${atom.symbol}${atom.index}`} aria-pressed={visibleSelection.includes(atom.index)}
            className={`btn ghost sm ${visibleSelection.includes(atom.index) ? 'active' : ''}`}
            onClick={() => pickAtom(atom.index)}>
            <span className="wb-atom-sym">{atom.symbol}</span><span className="wb-atom-idx">{atom.index}</span>
          </button>)}</div>
        <details><summary>已定义的冻结与扫描{visibleDraft && (visibleDraft.frozen.length > 0 || visibleDraft.scans.length > 0) && `（冻结 ${visibleDraft.frozen.length} · 扫描 ${visibleDraft.scans.length}）`}</summary>
        <label className="wb-check"><input type="checkbox" checked={showCoordinates} onChange={e=>setShowCoordinates(e.target.checked)}/>画面标注冻结／扫描</label>
        {visibleDraft?.frozen.map((c,i)=><div className="wb-definition" key={`f${i}`}><button className="wb-def-content" disabled={!editable} onClick={()=>openCoordinateDialog({atoms:c.atoms,frozen:c})}><span className="wb-def-badge wb-freeze-badge">冻结</span><span>{c.atoms.join(' → ')} = {c.value}</span><span className="wb-def-curr">当前 {geometry && !(view==='source' && visibleDraft.atomMappingChanged) ? measureCoordinate(geometry.atoms,c.atoms)?.toFixed(4) ?? '?' : '?'}</span></button><button className="wb-def-del" title="删除定义" disabled={!editable} onClick={()=>draft && commit({...draft,frozen:draft.frozen.filter((_,n)=>n!==i)})}>×</button></div>)}
        {visibleDraft?.scans.map((c,i)=><div className="wb-definition" key={`s${i}`}><button className="wb-def-content" disabled={!editable} onClick={()=>openCoordinateDialog({atoms:c.atoms,scan:c})}><span className="wb-def-badge wb-scan-badge">扫描</span><span>{c.atoms.join(' → ')}: {c.scan_start} → {c.scan_end}</span><span className="wb-def-curr">{c.scan_steps} 步</span></button><button className="wb-def-del" title="删除定义" disabled={!editable} onClick={()=>draft && commit({...draft,scans:draft.scans.filter((_,n)=>n!==i)})}>×</button></div>)}
        </details>
      </section>
      <details className="wb-section"><summary>连接感知与镜像</summary>
        {geometry?.graph_status === 'unresolved' && <p className="wb-muted">
          {geometry.manual_bonds ? '连接关系尚未完整确定，画面显示已指定的键。' : '坐标文件按距离显示连线。感知连接后可按分子图编辑。'}
        </p>}
        <button className="btn outline sm wb-btn-full" disabled={!editable} onClick={()=>void perform({action:'resolve_bonds'})}>明确感知连接关系</button>
        <label>镜像原子（逗号分隔，留空为整分子）<input value={mirrorAtoms} onChange={e=>setMirrorAtoms(e.target.value)}/></label>
        <div className="wb-input-with-action"><label className="wb-compact-label">镜面<select value={plane} onChange={e=>setPlane(e.target.value as typeof plane)}><option value="xy">XY</option><option value="xz">XZ</option><option value="yz">YZ</option></select></label><button className="btn outline sm" disabled={!editable} onClick={()=>void perform({action:'mirror',plane,...(mirrorAtoms.trim()?{moving_atoms:atomList(mirrorAtoms)}:{})})}>预览{mirrorAtoms.trim()?'指定原子':'整分子'}镜像</button></div>
      </details>
      {!editingCanvas && <details className="wb-section"><summary>基团替换与共享历史</summary><p>选一个末端原子，或依次选保留侧和被替换侧。确认预览后记录使用次数。</p>
        <label>常用基团<select value={commonGroups.some(([smiles])=>smiles===fragmentSmiles) ? fragmentSmiles : ''} onChange={e=>selectFragment(e.target.value)}>
          <option value="">自定义或从历史选择</option>{commonGroups.map(([smiles,name])=><option key={smiles} value={smiles}>{name}</option>)}</select></label><label>基团 SMILES<input value={fragmentSmiles} onChange={e=>selectFragment(e.target.value)} placeholder="带 [*:1] 连接点，或在预览中点选"/></label><label>名称（可选）<input value={fragmentName} onChange={e=>setFragmentName(e.target.value)}/></label><button className="btn outline sm wb-btn-full" disabled={busy || !fragmentSmiles.trim()} onClick={()=>void previewFragment()}>预览基团／选择连接原子</button>
        {fragmentPreview && <div className="wb-fragment-preview"><Molecule3DViewer key={fragmentPreview.molecule} geometry={fragmentPreview} selectedAtoms={attachment?[Number(attachment)]:[]} onAtomPick={i=>setAttachment(String(i))} title="基团连接位置"/></div>}
        <label>基团连接原子编号（有标记时可空）<input type="number" min={1} value={attachment} onChange={e=>setAttachment(e.target.value)}/></label><button className="btn green sm wb-btn-full" disabled={!editable || replaceAtoms.length!==2 || !fragmentSmiles.trim()} onClick={()=>void perform({action:'replace_group',atoms:replaceAtoms,smiles:fragmentSmiles,...(attachment?{attachment_atom:Number(attachment)}:{})},{fragment:fragmentSmiles})}>预览替换结果</button>
        <input aria-label="搜索基团历史" placeholder="搜索名称或 SMILES" value={fragmentSearch} onChange={e=>setFragmentSearch(e.target.value)}/><div className="wb-fragments">{fragments.filter(f=>`${f.name} ${f.smiles}`.toLowerCase().includes(fragmentSearch.toLowerCase())).map(f=><div key={f.id} className="wb-fragment-row"><button className="wb-fragment-entry" onClick={()=>selectFragment(f)}><span className="wb-fragment-title">{f.name || f.smiles}</span><small>{f.project_use_count?'本项目用过 · ':''}累计 {f.use_count} 次 · {f.smiles}</small></button><button className="wb-fragment-del" aria-label={`删除基团 ${f.name || f.smiles}`} onClick={()=>{void workbenchApi.deleteFragment(project.id,f.id).then(refreshFragments).catch(fail);}}>×</button></div>)}</div>
      </details>}
    </aside></div>
    {coordinateDialog && originalGeometry && (() => {
      const current = measureCoordinate(originalGeometry.atoms, coordinateDialog.atoms);
      const kind = coordinateType(coordinateDialog.atoms.length);
      return current == null || !kind ? null : <WorkbenchCoordinateDialog selection={coordinateDialog} kind={kind} current={current} busy={busy} error={error}
        onClose={()=>setCoordinateDialog(null)} onDefine={defineCoordinate}
        onPreview={async action=>{if(await perform(action))setCoordinateDialog(null);}} />;
    })()}
  </section></div>;
}
