import { useId, useState } from 'react';
import type { EditRequest, FragmentEntry, GeometryView, WorkbenchAtom } from './workbenchTypes';

import { commonGroups } from './molecularWorkbench';

type BuilderEdit = Omit<EditRequest, 'molecule'>;
const commonElements = ['C', 'H', 'N', 'O', 'F', 'P', 'S', 'Cl', 'Br', 'I', 'Si', 'B', 'Li', 'Na', 'Mg', 'Fe', 'Cu', 'Ag', 'Pt'];
const bondNames: Record<number, string> = { 1: '单键', 1.5: '芳香键', 2: '双键', 3: '三键' };
const atomLabel = (atom: WorkbenchAtom) => `${atom.symbol}${atom.index}`;

function AtomState({ atom, bondValence, unresolved, disabled, onEdit }: {
  atom: WorkbenchAtom; bondValence: number; unresolved: boolean; disabled: boolean; onEdit: (edit: BuilderEdit) => void;
}) {
  const [charge, setCharge] = useState(String(atom.formal_charge ?? 0));
  const [valence, setValence] = useState(String(atom.target_valence ?? ''));
  const [hybridization, setHybridization] = useState(atom.hybridization_override ?? '');
  const nextCharge = Number(charge);
  const nextValence = valence.trim() ? Number(valence) : null;
  const hybridizationChanged = hybridization !== (atom.hybridization_override ?? '');
  const changed = nextCharge !== (atom.formal_charge ?? 0) || nextValence !== (atom.target_valence ?? null) || hybridizationChanged;
  const valid = !!charge.trim() && Number.isInteger(nextCharge) && nextCharge >= -128 && nextCharge <= 127
    && (nextValence == null || Number.isInteger(nextValence) && nextValence >= 0 && nextValence <= 32);
  const unfilled = atom.target_valence == null ? 0 : atom.target_valence - bondValence;
  const applyState = () => onEdit({ action: 'atom_state', atoms: [atom.index], formal_charge: nextCharge, valence: nextValence,
    ...(hybridizationChanged ? { hybridization: (hybridization || null) as EditRequest['hybridization'] } : {}) });

  return <form className="wb-atom-state" onSubmit={event => {
    event.preventDefault();
    if (!disabled && changed && valid) applyState();
  }}>
    <span className="wb-valence-readout"><strong>{atomLabel(atom)}</strong> 已占价数 {bondValence}</span>
    <label>形式电荷<input type="number" step={1} min={-128} max={127} value={charge}
      disabled={disabled} onChange={event => setCharge(event.target.value)} /></label>
    <label>目标价数<input type="number" step={1} min={0} max={32} value={valence} placeholder="未限定"
      disabled={disabled} onChange={event => setValence(event.target.value)} /></label>
    <label>杂化方式<select aria-label="杂化方式" value={hybridization} disabled={disabled} onChange={event => setHybridization(event.target.value)}>
      <option value="">自动识别</option><option value="sp">sp</option><option value="sp2">sp²</option><option value="sp3">sp³</option>
    </select></label>
    <span className="wb-muted">当前 {atom.hybridization ?? '未确定'} · 孤对电子 {atom.lone_pairs == null ? '未确定' : `${atom.lone_pairs} 对`}</span>
    <button className="btn outline sm" type="submit" disabled={disabled || !valid || !changed}>应用价态</button>
    <button className="btn outline sm" type="button" disabled={disabled || changed || unresolved || unfilled <= 0 || !Number.isInteger(unfilled)}
      onClick={() => onEdit({ action: 'fill_valence', atoms: [atom.index] })}>补氢至目标价数</button>
  </form>;
}

export function MoleculeBuilder({ geometry, selection, disabled, hasFrozenCoordinates = false, onEdit,
  editing, onModeChange, element, onElementChange, brush, onBrushChange, fragments, customSmiles, onCustomSmilesChange,
  attachment, onAttachmentChange, onPlace }: {
  editing: boolean; onModeChange: (mode: 'edit' | 'select') => void;
  element: string; onElementChange: (s: string) => void; brush: string; onBrushChange: (s: string) => void;
  fragments: FragmentEntry[]; customSmiles: string; onCustomSmilesChange: (s: string) => void;
  attachment: string; onAttachmentChange: (s: string) => void; onPlace: () => void;
  geometry?: GeometryView | null; selection: number[]; disabled: boolean; hasFrozenCoordinates?: boolean; onEdit: (edit: BuilderEdit) => void;
}) {
  const [order, setOrder] = useState(1);
  const [forceField, setForceField] = useState<'MMFF94' | 'UFF'>('MMFF94');
  const elementsId = useId();
  const selected = selection.map(index => geometry?.atoms.find(atom => atom.index === index))
    .filter((atom): atom is WorkbenchAtom => atom != null);
  const anchor = selected.length === 1 ? selected[0] : null;
  const pair = selected.length === 2 ? selected.map(atom => atom.index) : [];
  const existing = pair.length === 2 && geometry?.bonds.find(bond => pair.includes(bond.atom1) && pair.includes(bond.atom2));
  const bondValence = anchor?.bond_valence ?? geometry?.bonds.reduce(
    (total, bond) => total + (anchor && (bond.atom1 === anchor.index || bond.atom2 === anchor.index) ? bond.order : 0), 0,
  ) ?? 0;
  const elementPicker = <label>{editing ? '元素' : '替换为'}<input list={elementsId} value={element} maxLength={3}
    disabled={disabled} onChange={event => onElementChange(event.target.value)} /></label>;
  return <section className="wb-builder" aria-label="分子建模">
    <datalist id={elementsId}>{commonElements.map(symbol => <option key={symbol} value={symbol} />)}</datalist>
    <div className="wb-builder-controls">
      <div role="group" aria-label="画布操作" className="btn-group">
        {([['select', '选择模式'], ['edit', '编辑模式']] as const).map(([mode, label]) => {
          const active = editing === (mode === 'edit');
          return <button key={mode} type="button" aria-pressed={active} className={`btn outline sm ${active ? 'active' : ''}`}
            disabled={disabled} onClick={() => { if (!active) onModeChange(mode); }}>{label}</button>;
        })}
      </div>
      {editing && <>
        <label>添加内容<select value={brush} onChange={e => onBrushChange(e.target.value)} disabled={disabled}>
          <option value="atom">原子</option>
          <optgroup label="常用基团">{commonGroups.map(([smiles, name]) => <option key={smiles} value={smiles}>{name}</option>)}</optgroup>
          {fragments.length > 0 && <optgroup label="基团历史">{fragments.map(f => <option key={f.id} value={f.smiles}>{f.name || f.smiles}</option>)}</optgroup>}
          <option value="custom">自定义基团</option>
        </select></label>
        {brush === 'atom' && elementPicker}
        {brush === 'custom' && <><label>基团 SMILES<input value={customSmiles} placeholder="例如 [*]OC" onChange={e => onCustomSmilesChange(e.target.value)} /></label>
          <label>连接原子编号<input type="number" min={1} placeholder="有 [*] 可留空" value={attachment} onChange={e => onAttachmentChange(e.target.value)} /></label></>}
        <button type="button" className="btn ghost sm" disabled={disabled || (brush === 'atom' && !element.trim()) || (brush === 'custom' && !customSmiles.trim())}
          onClick={onPlace}>独立放置</button>
      </>}
      {!editing && anchor && <>{elementPicker}
        <button className="btn outline sm" type="button" disabled={disabled || !element.trim() || anchor.symbol.toLowerCase() === element.trim().toLowerCase()}
          onClick={() => onEdit({ action: 'atom_state', atoms: [anchor.index], element: element.trim() })}>替换元素</button></>}
      {!editing && pair.length === 2 && <>
      <label>键级<select disabled={disabled} value={order} onChange={event => setOrder(Number(event.target.value))}>
        {[1, 2, 3, 1.5].map(value => <option value={value} key={value}>{bondNames[value]}</option>)}
      </select></label>
      <button className="btn outline sm" type="button" disabled={disabled || pair.length !== 2 || (!!existing && existing.order === order)}
        onClick={() => onEdit({ action: 'bond', atoms: pair, order })}>设置键</button>
      <button className="btn outline sm" type="button" disabled={disabled || !existing}
        onClick={() => onEdit({ action: 'bond', atoms: pair, order: 0 })}>断开键</button>
      <span>{existing ? `当前${bondNames[existing.order] ?? existing.order}` : '两原子未成键'}</span></>}
      {!editing && selected.length > 0 && <button className="btn outline sm" type="button" disabled={disabled}
        onClick={() => onEdit({ action: 'delete_atom', atoms: selected.map(atom => atom.index) })}>删除所选原子</button>}
    </div>
    {!editing && anchor && <AtomState key={`${anchor.atom_id ?? anchor.index}:${anchor.formal_charge}:${anchor.target_valence}:${anchor.hybridization_override}`}
      atom={anchor} bondValence={bondValence} unresolved={geometry?.graph_status === 'unresolved'}
      disabled={disabled} onEdit={onEdit} />}
    <div className="wb-force-field-controls">
      <label>预优化力场<select aria-label="预优化力场" value={forceField} disabled={disabled} onChange={event => setForceField(event.target.value as typeof forceField)}><option value="MMFF94">MMFF94</option><option value="UFF">UFF</option></select></label>
      <button className="btn outline sm" type="button" disabled={disabled || !geometry?.atoms.length || hasFrozenCoordinates || !!geometry?.preoptimization_blocker}
        onClick={() => onEdit({ action: 'preoptimize', force_field: forceField })}>力场预优化</button>
      <span className="wb-muted">{hasFrozenCoordinates ? '预优化暂不支持冻结坐标，请先移除冻结定义。' : geometry?.preoptimization_blocker
        ? (geometry.graph_status === 'unresolved' || geometry.graph_status === 'distance-inferred'
          ? '请在「连接感知与镜像」中感知键级；带电结构可指定总电荷。' : geometry.preoptimization_blocker)
        : '结果直接用于当前编辑稿，可继续编辑或撤销。'}</span>
    </div>
  </section>;
}
