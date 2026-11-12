import { useId, useState } from 'react';
import type { EditRequest, GeometryView, WorkbenchAtom } from './workbenchTypes';

type BuilderEdit = Omit<EditRequest, 'molecule'>;
const commonElements = ['C', 'H', 'N', 'O', 'F', 'P', 'S', 'Cl', 'Br', 'I', 'Si', 'B', 'Li', 'Na', 'Mg', 'Fe', 'Cu', 'Ag', 'Pt'];
const bondNames: Record<number, string> = { 1: '单键', 1.5: '芳香键', 2: '双键', 3: '三键' };
const atomLabel = (atom: WorkbenchAtom) => `${atom.symbol}${atom.index}`;

function AtomState({ atom, bondValence, unresolved, disabled, onEdit }: {
  atom: WorkbenchAtom; bondValence: number; unresolved: boolean; disabled: boolean; onEdit: (edit: BuilderEdit) => void;
}) {
  const [charge, setCharge] = useState(String(atom.formal_charge ?? 0));
  const [valence, setValence] = useState(String(atom.target_valence ?? ''));
  const nextCharge = Number(charge);
  const nextValence = valence.trim() ? Number(valence) : null;
  const changed = nextCharge !== (atom.formal_charge ?? 0) || nextValence !== (atom.target_valence ?? null);
  const valid = !!charge.trim() && Number.isInteger(nextCharge) && nextCharge >= -128 && nextCharge <= 127
    && (nextValence == null || Number.isInteger(nextValence) && nextValence >= 0 && nextValence <= 32);
  const unfilled = atom.target_valence == null ? 0 : atom.target_valence - bondValence;
  const applyState = () => onEdit({ action: 'atom_state', atoms: [atom.index], formal_charge: nextCharge, valence: nextValence });

  return <form className="wb-atom-state" onSubmit={event => {
    event.preventDefault();
    if (!disabled && changed && valid) applyState();
  }}>
    <span className="wb-valence-readout"><strong>{atomLabel(atom)}</strong> 已占价数 {bondValence}</span>
    <label>形式电荷<input type="number" step={1} min={-128} max={127} value={charge}
      disabled={disabled} onChange={event => setCharge(event.target.value)} /></label>
    <label>目标价数<input type="number" step={1} min={0} max={32} value={valence} placeholder="未限定"
      disabled={disabled} onChange={event => setValence(event.target.value)} /></label>
    <button className="btn outline sm" type="submit" disabled={disabled || !valid || !changed}>应用价态</button>
    <button className="btn outline sm" type="button" disabled={disabled || changed || unresolved || unfilled <= 0 || !Number.isInteger(unfilled)}
      onClick={() => onEdit({ action: 'fill_valence', atoms: [atom.index] })}>补氢至目标价数</button>
  </form>;
}

export function MoleculeBuilder({ geometry, selection, disabled, onEdit }: {
  geometry?: GeometryView | null; selection: number[]; disabled: boolean; onEdit: (edit: BuilderEdit) => void;
}) {
  const [element, setElement] = useState('C');
  const [order, setOrder] = useState(1);
  const elementsId = useId();
  const selected = selection.map(index => geometry?.atoms.find(atom => atom.index === index))
    .filter((atom): atom is WorkbenchAtom => atom != null);
  const anchor = selected.length === 1 ? selected[0] : null;
  const pair = selected.length === 2 ? selected.map(atom => atom.index) : [];
  const existing = pair.length === 2 && geometry?.bonds.find(bond => pair.includes(bond.atom1) && pair.includes(bond.atom2));
  const bondValence = anchor?.bond_valence ?? geometry?.bonds.reduce(
    (total, bond) => total + (anchor && (bond.atom1 === anchor.index || bond.atom2 === anchor.index) ? bond.order : 0), 0,
  ) ?? 0;
  let hint = '点选一个原子后可添加相连原子，点选两个可设置键。';
  if (!geometry?.atoms.length) hint = '选择元素并添加第一个原子。';
  else if (anchor) hint = `新原子将接到 ${atomLabel(anchor)}。`;
  else if (pair.length) hint = `${selected.map(atomLabel).join(' · ')}　${existing ? `当前${bondNames[existing.order] ?? `键级 ${existing.order}`}` : '两原子未成键'}`;
  else if (selected.length > 2) hint = `已选 ${selected.length} 个原子。`;

  return <section className="wb-builder" aria-label="分子建模">
    <div className="wb-builder-controls">
      <label>元素<input list={elementsId} value={element} maxLength={3}
        disabled={disabled} onChange={event => setElement(event.target.value)} /></label>
      <datalist id={elementsId}>{commonElements.map(symbol => <option key={symbol} value={symbol} />)}</datalist>
      <button className="btn green sm" type="button" disabled={disabled || selected.length > 1 || !element.trim()}
        onClick={() => onEdit({ action: 'add_atom', element: element.trim(), atoms: anchor ? [anchor.index] : [], order: anchor ? order : 1 })}>添加原子</button>
      <label>键级<select disabled={disabled} value={order} onChange={event => setOrder(Number(event.target.value))}>
        {[1, 2, 3, 1.5].map(value => <option value={value} key={value}>{bondNames[value]}</option>)}
      </select></label>
      <button className="btn outline sm" type="button" disabled={disabled || pair.length !== 2 || (!!existing && existing.order === order)}
        onClick={() => onEdit({ action: 'bond', atoms: pair, order })}>设置键</button>
      <button className="btn outline sm" type="button" disabled={disabled || !existing}
        onClick={() => onEdit({ action: 'bond', atoms: pair, order: 0 })}>断开键</button>
      <button className="btn outline sm" type="button" disabled={disabled || !selected.length}
        onClick={() => onEdit({ action: 'delete_atom', atoms: selected.map(atom => atom.index) })}>删除所选原子</button>
    </div>
    <p className="wb-muted">{hint}</p>
    {anchor && <AtomState key={`${anchor.atom_id ?? anchor.index}:${anchor.formal_charge}:${anchor.target_valence}`}
      atom={anchor} bondValence={bondValence} unresolved={geometry?.graph_status === 'unresolved'}
      disabled={disabled} onEdit={onEdit} />}
  </section>;
}
