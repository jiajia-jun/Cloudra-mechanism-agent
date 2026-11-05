import { useEffect, useRef, useState } from 'react';
import type { Project } from './types';
import { Molecule3DViewer } from './Molecule3DViewer';
import { workbenchApi } from './workbenchApi';
import type { DocumentView, Draft, EditRequest, FragmentEntry, FrameSummary, GeometryView, SaveResult, WorkbenchSource, WorkbenchInputFormat } from './workbenchTypes';
import { applyGeometry, draftFromFrame, coordinateType, curvePoints, defineFrozenCoordinate, detectImportFormat, measureCoordinate, selectionAfterEdit, toggleAtomSelection, undoDraft, validateSettings } from './molecularWorkbench';
import './molecularWorkbench.css';

export interface MolecularWorkbenchProps { project: Project; source: WorkbenchSource | null; onClose: () => void; onSaved: (result: SaveResult) => void; onError: (error: string) => void }
const fromDocument = (doc: DocumentView): Draft | null => doc.geometry ? ({ geometry: doc.geometry, settings: { ...doc.settings }, sourcePath: doc.source_path, sourceFrame: doc.selected_frame, frozen: doc.frozen_coordinates ?? [], scans: doc.scan_coordinates ?? [] }) : null;
const atomList = (value: string): number[] => value.split(',').flatMap(s => s.trim().split(' ')).filter(Boolean).map(Number);
const metricLabel = { energy_hartree: '能量 / Hartree', rms_force: 'RMS 力', reaction_coordinate: '反应坐标' };
type Metric = keyof typeof metricLabel;

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

export function MolecularWorkbench({ project, source, onClose, onSaved, onError }: MolecularWorkbenchProps) {
  const [doc, setDoc] = useState<DocumentView | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [history, setHistory] = useState<Draft[]>([]);
  const [frame, setFrame] = useState(0);
  const [frameGeometry, setFrameGeometry] = useState<GeometryView | null>(null);
  const [view, setView] = useState<'draft'|'source'>('draft');
  const [selection, setSelection] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [dirty, setDirty] = useState(false);
  const [discardAction, setDiscardAction] = useState<{kind:'close'|'import'|'source'; source?:WorkbenchSource|null} | null>(null);
  const [inputKind, setInputKind] = useState<WorkbenchInputFormat|'path'>('smiles');
  const [input, setInput] = useState('');
  const [title, setTitle] = useState('');
  const [target, setTarget] = useState('');
  const [fixedSide, setFixedSide] = useState<'first'|'last'>('first');
  const [moving, setMoving] = useState('');
  const [scanStart, setScanStart] = useState('');
  const [scanEnd, setScanEnd] = useState('');
  const [scanSteps, setScanSteps] = useState('');
  const [showCoordinates, setShowCoordinates] = useState(true);
  const [bondOrder, setBondOrder] = useState(1);
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
  const closed = useRef(false);
  const loadedProject = useRef<string | null>(null);
  const onErrorRef = useRef(onError); onErrorRef.current = onError;
  const fail = (e: unknown) => { const text = e instanceof Error ? e.message : String(e); setError(text); onErrorRef.current(text); };
  const refreshFragments = async () => {
    const version = requestVersion.current;
    const result = await workbenchApi.fragments(project.id);
    if (!closed.current && version === requestVersion.current) setFragments(result.fragments);
  };

  useEffect(() => {
    closed.current = false;
    return () => { closed.current = true; requestVersion.current++; };
  }, []);
  const loadSource = (nextSource: WorkbenchSource | null) => {
    setDiscardAction(null);
    loadedProject.current = project.id;
    const version = ++requestVersion.current;
    setDoc(null); setDraft(null); setHistory([]); setSelection([]); setPreview(null); setDirty(false); setPlaying(false); setModeIndex(-1); setModePlaying(false); setError(''); setMessage(''); setFragmentPreview(null);
    if (nextSource) {
      setBusy(true);
      workbenchApi.open(project.id, nextSource).then(result => {
        if (version !== requestVersion.current || closed.current) return;
        setDoc(result); setDraft(fromDocument(result)); setFrame(result.selected_frame); setFrameGeometry(result.geometry); setTitle(result.title); setView('draft'); setDirty(!!nextSource.smiles || !!nextSource.input_text);
      }).catch(e => { if (version === requestVersion.current) fail(e); }).finally(() => { if (version === requestVersion.current) setBusy(false); });
    } else setBusy(false);
    workbenchApi.fragments(project.id).then(r => { if (version === requestVersion.current) setFragments(r.fragments); }).catch(e => { if (version === requestVersion.current) fail(e); });
  };
  useEffect(() => {
    if (loadedProject.current === project.id && dirty) { setDiscardAction({kind:'source',source}); return; }
    loadSource(source);
  }, [project.id, source]);

  const originalGeometry = view === 'source' ? frameGeometry : draft?.geometry;
  const mode = modeIndex >= 0 ? doc?.modes[modeIndex] : null;
  const geometry = preview?.geometry ?? (mode ? doc?.modes_reference_geometry : originalGeometry) ?? originalGeometry;
  const visibleSelection = preview ? selectionAfterEdit(selection, preview.geometry.changes) : selection;
  const visibleDraft = preview ? applyGeometry(preview.base, preview.geometry).draft : draft;
  const measured = geometry ? measureCoordinate(geometry.atoms, visibleSelection) : null;
  const coordType = coordinateType(visibleSelection.length);
  const unit = visibleSelection.length === 2 ? 'Å' : '°';
  const editable = !!originalGeometry && !mode && !preview && !busy;
  const operationBase = (): Draft => {
    if (!originalGeometry) throw new Error('请先打开有实际坐标的结构帧。');
    if (!draft) return {geometry:originalGeometry,settings:{...doc?.settings},sourcePath:doc?.source_path,sourceFrame:frame,frozen:doc?.frozen_coordinates??[],scans:doc?.scan_coordinates??[]};
    if (view !== 'source') return draft;
    if (draft.atomMappingChanged && (draft.frozen.length || draft.scans.length)) setMessage('已从原始帧建立新稿；之前拓扑编辑中的冻结／扫描定义保留在撤销记录中，请为此帧重新定义。');
    return draftFromFrame(draft,originalGeometry,doc?.source_path,frame);
  };
  const commit = (next: Draft) => {
    if (draft) setHistory(h => [...h,draft]);
    setDraft(next); setView('draft'); setDirty(true); setPreview(null); setModeIndex(-1); setModePlaying(false); setSelection([]);
  };
  const updateSettings = (settings: Draft['settings']) => {
    if (!draft) return;
    setHistory(h => [...h,draft]); setDraft({...draft,settings}); setDirty(true);
  };
  const perform = async (action: Omit<EditRequest,'molecule'>, fragment?: string) => {
    setError(''); setMessage(''); setBusy(true);
    const version = requestVersion.current;
    try {
      const base = operationBase();
      const edited = await workbenchApi.edit(project.id, {...action,molecule:base.geometry.molecule});
      if (version === requestVersion.current && !closed.current) setPreview({geometry:edited,base,fragment});
    } catch(e) { if (version === requestVersion.current && !closed.current) fail(e); } finally { if (version === requestVersion.current && !closed.current) setBusy(false); }
  };
  const confirmPreview = async () => {
    if (!preview) return;
    const version = requestVersion.current;
    const result = applyGeometry(preview.base,preview.geometry);
    commit(result.draft);
    setMessage(result.invalidated ? `已移除 ${result.invalidated} 条引用被删除原子的冻结／扫描定义，请重新定义。` : '已确认修改，原始计算帧保持原样。');
    if (preview.fragment) {
      try { await workbenchApi.useFragment(project.id,preview.geometry.changes?.fragment_smiles ?? preview.fragment,fragmentName); if (version === requestVersion.current && !closed.current) await refreshFragments(); }
      catch(e) { if(version === requestVersion.current && !closed.current) fail(e); }
    }
  };
  const selectFrame = async (index: number) => {
    if (!doc || busy) return;
    const version = requestVersion.current;
    setBusy(true); setError(''); setPreview(null); setModeIndex(-1); setModePlaying(false); setFrame(index); setFrameGeometry(null); setView('source');
    if (doc.frames[index]?.has_geometry === false) { setBusy(false); setMessage('此原生采样点未输出几何，保留标量事实；请选取有实际坐标的帧进行编辑。'); return; }
    try { const g = await workbenchApi.frame(project.id,doc.document_id,index); if(version !== requestVersion.current || closed.current) return; setFrame(index); setFrameGeometry(g); setView('source'); setSelection([]); }
    catch(e) { if(version === requestVersion.current && !closed.current) { fail(e); setPlaying(false); } } finally { if (version === requestVersion.current && !closed.current) setBusy(false); }
  };
  useEffect(() => {
    if (!playing || busy || !doc || doc.frames.length < 2) return;
    const timer = window.setTimeout(() => { void selectFrame((frame+1)%doc.frames.length); },450);
    return () => window.clearTimeout(timer);
  },[playing,busy,frame,doc]);
  const close = () => { if (dirty) setDiscardAction({kind:'close'}); else onClose(); };
  const importSource = async (confirmed = false) => {
    if (!input.trim()) return;
    if (dirty && !confirmed) { setDiscardAction({kind:'import'}); return; }
    setDiscardAction(null);
    setBusy(true); setError('');
    const version = requestVersion.current;
    try {
      const result = await workbenchApi.open(project.id,inputKind === 'path' ? {path:input.trim()} : inputKind === 'smiles' ? {smiles:input.trim()} : {input_text:input,input_format:inputKind});
      if(version !== requestVersion.current || closed.current) return;
      setDoc(result); setDraft(fromDocument(result)); setFrame(result.selected_frame); setFrameGeometry(result.geometry); setTitle(result.title); setHistory([]); setSelection([]); setPreview(null); setDirty(true); setView('draft'); setModeIndex(-1); setModePlaying(false); setPlaying(false);
    } catch(e) { if (version === requestVersion.current && !closed.current) fail(e); } finally { if (version === requestVersion.current && !closed.current) setBusy(false); }
  };
  const coordinateEdit = (): Omit<EditRequest,'molecule'> => {
    if (measured == null || !target.trim() || !Number.isFinite(Number(target))) throw new Error('请依次选择 2／3／4 个原子并填写目标数值。');
    return {action:'coordinate',atoms:selection,value:Number(target),fixed_side:fixedSide,...(moving.trim() ? {moving_atoms:atomList(moving)} : {})};
  };
  const defineCoordinate = async (kind: 'freeze'|'scan') => {
    if (!coordType || measured == null) return;
    setError('');
    const version = requestVersion.current;
    try {
      const base = operationBase();
      if (kind === 'freeze') {
        commit(defineFrozenCoordinate(base,selection,target));
      } else {
        if (!scanStart.trim() || !scanEnd.trim() || !scanSteps.trim() || !Number.isFinite(Number(scanStart)) || !Number.isFinite(Number(scanEnd)) || !Number.isInteger(Number(scanSteps)) || Number(scanSteps)<1) throw new Error('请填写有限的扫描起点、终点和正整数步数。');
        commit({...base,scans:[...base.scans.filter(c=>c.atoms.join(',')!==selection.join(',')),{coord_type:coordType,atoms:[...selection],scan_start:Number(scanStart),scan_end:Number(scanEnd),scan_steps:Number(scanSteps)}]});
      }
    } catch(e) { if (version === requestVersion.current && !closed.current) fail(e); } finally { if (version === requestVersion.current && !closed.current) setBusy(false); }
  };
  const save = async () => {
    if (!draft) return;
    const invalid = validateSettings(draft.settings,generateInput);
    if (invalid) { fail(invalid); return; }
    setBusy(true); setError('');
    const version = requestVersion.current;
    try {
      const result = await workbenchApi.save(project.id,{title:title || 'molecule',molecule:draft.geometry.molecule,source_path:draft.sourcePath,source_frame:draft.sourceFrame,settings:draft.settings,frozen_coordinates:draft.frozen,scan_coordinates:draft.scans,generate_input:generateInput});
      if(version !== requestVersion.current || closed.current) return;
      setDraft({...draft,geometry:result.geometry}); setDirty(false); setMessage(`${result.message} ${result.path}`); onSaved(result);
    } catch(e) { if (version === requestVersion.current && !closed.current) fail(e); } finally { if (version === requestVersion.current && !closed.current) setBusy(false); }
  };
  const csv = async () => {
    if (!doc) return;
    try { const data = await workbenchApi.csv(project.id,doc.document_id); const url = URL.createObjectURL(new Blob([data],{type:'text/csv;charset=utf-8'})); const a = document.createElement('a'); a.href=url; a.download=`${doc.title || 'calculation'}.csv`; a.click(); window.setTimeout(() => URL.revokeObjectURL(url),1000); } catch(e) { fail(e); }
  };
  const previewFragment = async () => {
    setBusy(true); setError('');
    const version=requestVersion.current;
    try { const result=await workbenchApi.previewFragment(project.id,fragmentSmiles,fragmentName); if(version === requestVersion.current && !closed.current) setFragmentPreview(result); } catch(e) { if (version === requestVersion.current && !closed.current) fail(e); } finally { if (version === requestVersion.current && !closed.current) setBusy(false); }
  };
  const frameFacts = doc?.frames[frame];
  const scanDimensions = Math.max(0,...(doc?.frames.map(f => f.scan_coordinates?.length ?? 0) ?? []));
  const scanFrames = doc?.frames.filter(f => f.scan_coordinates?.length && Object.entries(scanSlice).every(([dim,value]) => Number(dim) === scanAxis || !value || f.scan_coordinates?.[Number(dim)] === Number(value))) ?? [];

  return <div className="wb-backdrop"><section className="molecular-workbench" role="dialog" aria-modal="true" aria-label="分子工作台">
    <header className="wb-header"><div><strong>分子工作台</strong><span className="wb-muted">{project.name} · {dirty ? '编辑稿未保存' : '结构与计算查看'}</span></div><button className="btn ghost" onClick={close}>关闭 ✕</button></header>
    <div className="wb-open"><select aria-label="来源类型" value={inputKind} onChange={e=>setInputKind(e.target.value as typeof inputKind)}><option value="smiles">SMILES 新建</option><option value="path">项目文件路径</option><option value="xyz">XYZ 文本</option><option value="mol">MOL 文本</option><option value="sdf">SDF 文本</option><option value="log">Gaussian／ORCA 日志 (.log)</option><option value="out">计算输出 (.out)</option><option value="gjf">Gaussian 输入 (.gjf)</option><option value="com">Gaussian 输入 (.com)</option><option value="inp">ORCA 输入 (.inp)</option><option value="pdb">PDB 文本</option><option value="cif">CIF 文本</option></select>
      <textarea aria-label="结构来源" placeholder={inputKind === 'path' ? '项目内文件路径，可打开 Gaussian／ORCA／结构文件' : '粘贴 SMILES 或结构文本'} value={input} onChange={e=>setInput(e.target.value)} rows={2}/><button className="btn outline" disabled={busy || !input.trim()} onClick={()=>void importSource()}>新建／打开</button>
      <label className="btn ghost wb-file">本地结构／计算文件<input type="file" accept=".xyz,.mol,.sdf,.smi,.smiles,.log,.out,.gjf,.com,.inp,.pdb,.cif" onChange={e=>{ const file=e.target.files?.[0]; if (!file) return; const format=detectImportFormat(file.name); if(!format){fail('不支持的文件类型。');return;} setInputKind(format); void file.text().then(setInput).catch(fail); }}/></label>
    </div>
    {discardAction && <div className="wb-preview" role="alert"><span>编辑稿尚未保存。继续将放弃这些修改。</span><button className="btn" onClick={()=>{const action=discardAction;setDiscardAction(null);if(action.kind==='close') onClose();else if(action.kind==='import') void importSource(true);else loadSource(action.source??null);}}>继续并放弃修改</button><button className="btn outline" onClick={()=>setDiscardAction(null)}>保留编辑稿</button></div>}
    {error && <div className="wb-error" role="alert">{error}</div>}{message && <div className="wb-message" role="status">{message}</div>}{busy && <div className="wb-muted" role="status">正在处理…</div>}
    <div className="wb-body"><main className="wb-main">
      <div className="wb-toolbar"><button className={`btn outline sm ${view==='draft'?'active':''}`} disabled={!draft || !!preview} onClick={()=>{setView('draft');setModeIndex(-1);setModePlaying(false);}}>编辑稿</button><button className={`btn outline sm ${view==='source'?'active':''}`} disabled={!doc || !!preview} onClick={()=>{setView('source');setModeIndex(-1);setModePlaying(false);}}>来源帧</button><button className="btn outline sm" disabled={!history.length || busy} onClick={()=>{if(draft){const restored=undoDraft(history,draft);setDraft(restored.draft);setHistory(restored.history);setView('draft');setDirty(true);setPreview(null);setSelection([]);}}}>撤销</button>{view==='source' && <button className="btn outline sm" disabled={!frameGeometry || busy || !!preview} onClick={()=>{try{commit(operationBase());}catch(e){fail(e);}}}>以此帧建立编辑稿</button>}<span className="wb-muted">{mode ? '简正模使用其真实参考几何' : preview ? '修改预览' : view==='draft' ? `派生自 ${draft?.sourcePath ?? '新结构'} · 帧 ${(draft?.sourceFrame ?? 0)+1}` : `原始来源帧 ${frame+1}`}</span></div>
      {geometry ? <Molecule3DViewer geometry={geometry} title={doc?.title} selectedAtoms={visibleSelection} onAtomPick={i=>{if(!preview && !mode){setSelection(s=>toggleAtomSelection(s,i));setTarget('');}}} modeDisplacements={mode?.displacements} modePlaying={modePlaying} coordinateHighlights={showCoordinates && visibleDraft && !(view==='source' && visibleDraft.atomMappingChanged) ? [...visibleDraft.frozen.map(c=>c.atoms),...visibleDraft.scans.map(c=>c.atoms)] : []} className="wb-viewer"/> : <div className="wb-empty">{doc ? '此点没有可用的原生几何，选择其他帧查看结构。' : '输入 SMILES、粘贴结构，或打开项目内的计算结果。'}</div>}
      {preview && <div className="wb-preview"><span>检查移动部分、连接关系和镜像结果。</span><button className="btn" onClick={()=>void confirmPreview()}>确认修改</button><button className="btn outline" onClick={()=>setPreview(null)}>取消预览</button></div>}
      {doc && <section className="wb-section"><div className="wb-toolbar"><strong>{doc.task_type || '来源结构'} · {doc.frames.length} 帧</strong><button className="btn outline sm" disabled={doc.frames.length<2} onClick={()=>setPlaying(!playing)}>{playing?'暂停帧播放':'播放各帧'}</button><button className="btn outline sm" onClick={()=>void csv()}>导出 CSV</button></div>
        <label>来源帧 {frame+1} / {doc.frames.length}<input aria-label="来源帧" type="range" min={0} max={Math.max(0,doc.frames.length-1)} value={frame} disabled={busy} onChange={e=>{setPlaying(false);void selectFrame(Number(e.target.value));}}/></label>
        <p className="wb-facts">步 {frameFacts?.step ?? '未知'} · 能量 {frameFacts?.energy_hartree ?? '未知'} Hartree · RMS 力 {frameFacts?.rms_force ?? '未知'} {frameFacts?.force_unit ?? ''} · 最大力 {frameFacts?.max_force ?? '未知'} {frameFacts?.force_unit ?? ''} · {frameFacts?.converged === true ? '原生记录已收敛' : frameFacts?.converged === false ? '原生记录未收敛' : '收敛状态未知'}{frameFacts?.path_number != null && ` · 路径 ${frameFacts.path_number}`}</p>
        <select aria-label="曲线指标" value={metric} onChange={e=>setMetric(e.target.value as Metric)}>{Object.entries(metricLabel).map(([key,value])=><option key={key} value={key}>{value}</option>)}</select><Curve frames={doc.frames} metric={metric} selected={frame} onSelect={i=>{setPlaying(false);void selectFrame(i);}}/>
        {scanDimensions>0 && <details open><summary>扫描／势能面采样点（{scanDimensions} 维）</summary><div className="wb-toolbar"><label>横轴<select value={scanAxis} onChange={e=>setScanAxis(Number(e.target.value))}>{Array.from({length:scanDimensions},(_,i)=><option key={i} value={i}>坐标 {i+1}</option>)}</select></label>{Array.from({length:scanDimensions},(_,i)=>i===scanAxis?null:<label key={i}>固定坐标 {i+1}<select value={scanSlice[String(i)]??''} onChange={e=>setScanSlice(s=>({...s,[String(i)]:e.target.value}))}><option value="">所有采样</option>{[...new Set(doc.frames.flatMap(f=>f.scan_coordinates?.[i] == null?[]:[f.scan_coordinates[i]]))].sort((a,b)=>a-b).map(v=><option key={v} value={v}>{v}</option>)}</select></label>)}</div><Curve frames={scanFrames.map(f=>({...f,reaction_coordinate:f.scan_coordinates?.[scanAxis]}))} metric="energy_hartree" selected={frame} onSelect={i=>void selectFrame(i)}/><div className="wb-scan-points">{scanFrames.map(f=><button key={f.index} className={`btn outline sm ${frame===f.index?'active':''}`} onClick={()=>void selectFrame(doc.frames.indexOf(f))}>帧 {doc.frames.indexOf(f)+1}: ({f.scan_coordinates?.join(', ')}) · {f.energy_hartree ?? '?'} Eh</button>)}</div></details>}
        <div className="wb-toolbar"><label>实际频率<select aria-label="实际简正模" value={modeIndex} onChange={e=>{setModeIndex(Number(e.target.value));setModePlaying(false);setPlaying(false);setSelection([]);}}><option value={-1}>显示当前结构</option>{doc.modes.map((m,i)=><option key={i} value={i} disabled={!doc.modes_reference_geometry}>模式 {i+1}: {m.frequency_cm} cm⁻¹{m.frequency_cm<0?'（虚频）':''}</option>)}</select></label><button className="btn outline sm" disabled={!mode || !doc.modes_reference_geometry} onClick={()=>setModePlaying(!modePlaying)}>{modePlaying?'暂停模式':'播放真实位移'}</button>{!doc.modes.length && <span className="wb-muted">未取得配对的频率与位移。</span>}</div>
        {doc.warnings.map((w,i)=><p className="wb-muted" key={i}>{w}</p>)}
      </section>}
    </main><aside className="wb-sidebar">
      <section className="wb-section"><h3>有序点选与内坐标</h3><p>画面点选原子；再次点击可取消。编号是结构编号，选 1／2／3／4 是点击顺序。</p><div className="wb-toolbar">{visibleSelection.map((i,n)=><button disabled={!!preview} key={i} className="btn outline sm" onClick={()=>setSelection(s=>s.filter(a=>a!==i))}>{n+1} → {geometry?.atoms.find(a=>a.index===i)?.symbol}{i} ×</button>)}<button className="btn ghost sm" onClick={()=>setSelection([])}>清空</button></div>
        <div className="wb-atoms" aria-label="原子列表">{geometry?.atoms.map(a=><button key={a.index} disabled={!!mode || !!preview} className={`btn ghost sm ${visibleSelection.includes(a.index)?'active':''}`} onClick={()=>{setSelection(s=>toggleAtomSelection(s,a.index));setTarget('');}}>{a.symbol}{a.index}</button>)}</div>
        <p><strong>{coordType ? {bond:'距离',angle:'键角',dihedral:'二面角'}[coordType] : '选择 2、3 或 4 个原子'}{measured != null && `：${measured.toFixed(5)} ${unit}`}</strong></p>
        <label>目标值 {unit}<input aria-label="内坐标目标值" type="number" step="any" value={target} placeholder={measured?.toFixed(5)} onChange={e=>setTarget(e.target.value)}/></label>
        <label>固定侧<select value={fixedSide} onChange={e=>setFixedSide(e.target.value as typeof fixedSide)}><option value="first">固定前侧，移动末侧基团</option><option value="last">固定末侧，移动前侧基团</option></select></label><label>手动指定移动原子（逗号分隔，可留空）<input value={moving} onChange={e=>setMoving(e.target.value)} placeholder="如 4,5,6"/></label>
        <button className="btn outline" disabled={!editable || measured==null} onClick={()=>{try{void perform(coordinateEdit());}catch(e){fail(e);}}}>预览结构调整</button><button className="btn outline" disabled={!editable || measured==null} onClick={()=>void defineCoordinate('freeze')}>定义冻结坐标</button>
        <div className="wb-row"><label>扫描起点<input type="number" step="any" value={scanStart} onChange={e=>setScanStart(e.target.value)}/></label><label>终点<input type="number" step="any" value={scanEnd} onChange={e=>setScanEnd(e.target.value)}/></label><label>步数<input type="number" min={1} value={scanSteps} onChange={e=>setScanSteps(e.target.value)}/></label></div><button className="btn outline" disabled={!editable || measured==null} onClick={()=>void defineCoordinate('scan')}>添加独立扫描坐标</button>
        <label className="wb-check"><input type="checkbox" checked={showCoordinates} onChange={e=>setShowCoordinates(e.target.checked)}/>画面标注冻结／扫描</label>
        {visibleDraft?.frozen.map((c,i)=><div className="wb-definition" key={`f${i}`}><button className="btn ghost sm" disabled={!!preview} onClick={()=>{setView('draft');setModeIndex(-1);setSelection(c.atoms);setTarget(String(c.value));}}>冻结 {c.atoms.join(' → ')} = {c.value} · 当前 {geometry && !(view==='source' && visibleDraft.atomMappingChanged) ? measureCoordinate(geometry.atoms,c.atoms)?.toFixed(4) ?? '?' : '?'}</button><button className="btn ghost sm" disabled={!!preview} onClick={()=>draft && commit({...draft,frozen:draft.frozen.filter((_,n)=>n!==i)})}>删除</button></div>)}
        {visibleDraft?.scans.map((c,i)=><div className="wb-definition" key={`s${i}`}><button className="btn ghost sm" disabled={!!preview} onClick={()=>{setView('draft');setModeIndex(-1);setSelection(c.atoms);setScanStart(String(c.scan_start));setScanEnd(String(c.scan_end));setScanSteps(String(c.scan_steps));}}>扫描 {c.atoms.join(' → ')}: {c.scan_start} → {c.scan_end}, {c.scan_steps} 步</button><button className="btn ghost sm" disabled={!!preview} onClick={()=>draft && commit({...draft,scans:draft.scans.filter((_,n)=>n!==i)})}>删除</button></div>)}
      </section>
      <section className="wb-section"><h3>连接关系与镜像</h3><p className="wb-muted">图状态：{geometry?.graph_status ?? '未知'}。坐标文件不会自动推断化学键。</p><select aria-label="键级" value={bondOrder} onChange={e=>setBondOrder(Number(e.target.value))}><option value={0}>删除键</option><option value={1}>单键</option><option value={1.5}>芳香键</option><option value={2}>双键</option><option value={3}>三键</option></select><button className="btn outline" disabled={!editable || selection.length!==2} onClick={()=>void perform({action:'bond',atoms:selection,order:bondOrder})}>预览连接修改</button><button className="btn ghost" disabled={!editable} onClick={()=>void perform({action:'resolve_bonds'})}>明确感知连接关系</button>
        <label>镜面<select value={plane} onChange={e=>setPlane(e.target.value as typeof plane)}><option value="xy">XY</option><option value="xz">XZ</option><option value="yz">YZ</option></select></label><button className="btn outline" disabled={!editable} onClick={()=>void perform({action:'mirror',plane,...(moving.trim()?{moving_atoms:atomList(moving)}:{})})}>预览{moving.trim()?'指定原子':'整分子'}镜像</button>
      </section>
      <section className="wb-section"><h3>基团替换与共享历史</h3><p>依次选择保留侧、被替换侧原子。预览后确认才记录使用次数。</p><label>基团 SMILES<input value={fragmentSmiles} onChange={e=>{setFragmentSmiles(e.target.value);setFragmentPreview(null);}} placeholder="带 [*:1] 连接点，或在预览中点选"/></label><label>名称（可选）<input value={fragmentName} onChange={e=>setFragmentName(e.target.value)}/></label><button className="btn outline" disabled={busy || !fragmentSmiles.trim()} onClick={()=>void previewFragment()}>预览基团／选择连接原子</button>
        {fragmentPreview && <div className="wb-fragment-preview"><Molecule3DViewer geometry={fragmentPreview} selectedAtoms={attachment?[Number(attachment)]:[]} onAtomPick={i=>setAttachment(String(i))} title="基团连接位置"/></div>}
        <label>基团连接原子编号（有标记时可空）<input type="number" min={1} value={attachment} onChange={e=>setAttachment(e.target.value)}/></label><button className="btn outline" disabled={!editable || selection.length!==2 || !fragmentSmiles.trim()} onClick={()=>void perform({action:'replace_group',atoms:selection,smiles:fragmentSmiles,...(attachment?{attachment_atom:Number(attachment)}:{})},fragmentSmiles)}>预览替换结果</button>
        <input aria-label="搜索基团历史" placeholder="搜索名称或 SMILES" value={fragmentSearch} onChange={e=>setFragmentSearch(e.target.value)}/><div className="wb-fragments">{fragments.filter(f=>`${f.name} ${f.smiles}`.toLowerCase().includes(fragmentSearch.toLowerCase())).map(f=><div key={f.id}><button className="btn ghost" onClick={()=>{setFragmentSmiles(f.smiles);setFragmentName(f.name);setFragmentPreview(f.geometry??null);setAttachment(f.attachment_atom?String(f.attachment_atom):'');}}>{f.name || f.smiles}<small>{f.project_use_count?'本项目用过 · ':''}累计 {f.use_count} 次 · {f.smiles}</small></button><button className="btn ghost sm" aria-label={`删除基团 ${f.name || f.smiles}`} onClick={()=>{void workbenchApi.deleteFragment(project.id,f.id).then(refreshFragments).catch(fail);}}>×</button></div>)}</div>
      </section>
      {draft && <fieldset disabled={!!preview || busy} className="wb-section wb-settings"><h3>下一次计算与保存</h3><label>结构名称<input value={title} onChange={e=>{setTitle(e.target.value);setDirty(true);}}/></label><label>引擎<select value={draft.settings.engine ?? ''} onChange={e=>updateSettings({...draft.settings,engine:e.target.value as 'gaussian'|'orca'})}><option value="" disabled>请选择</option><option value="gaussian">Gaussian</option><option value="orca">ORCA</option></select></label>
        {(['method','basis_set','keywords'] as const).map(key=><label key={key}>{{method:'方法',basis_set:'基组（可明确留空）',keywords:'原生关键词'}[key]}<input value={String(draft.settings[key]??'')} onChange={e=>updateSettings({...draft.settings,[key]:e.target.value})}/></label>)}
        <label className="wb-check"><input type="checkbox" checked={draft.settings.basis_set === ''} onChange={e=>updateSettings({...draft.settings,basis_set:e.target.checked?'':undefined})}/>明确使用无需独立基组的方法</label>
        <div className="wb-row">{(['charge','multiplicity'] as const).map(key=><label key={key}>{key==='charge'?'电荷':'多重度'}<input type="number" value={draft.settings[key]??''} onChange={e=>updateSettings({...draft.settings,[key]:e.target.value===''?null:Number(e.target.value)})}/></label>)}</div>
        <label>计算类型<select value={Object.keys(draft.settings.task_type?.[0]??{})[0]??''} onChange={e=>updateSettings({...draft.settings,task_type:[{[e.target.value]:null}]})}><option value="" disabled>请选择</option><option value="opt">几何优化</option><option value="freq">频率</option><option value="irc">IRC</option><option value="sp">单点能</option></select></label><label className="wb-check"><input type="checkbox" checked={generateInput} onChange={e=>setGenerateInput(e.target.checked)}/>同时生成原生计算输入</label><p className="wb-muted">保存编辑稿、连接关系、来源与设置，并通知主 Agent。</p><button className="btn" disabled={busy || !!preview} onClick={()=>void save()}>保存编辑稿到项目</button>
      </fieldset>}
    </aside></div>
  </section></div>;
}
