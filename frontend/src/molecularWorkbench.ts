import type { Draft, FrameSummary, GeometryView, WorkbenchAtom, WorkbenchSettings, WorkbenchInputFormat } from './workbenchTypes.ts';
export function toggleAtomSelection(selection: number[], atom: number): number[] {
  return selection.includes(atom) ? selection.filter(i => i !== atom) : [...selection, atom];
}
export function selectionAfterEdit(selection: number[], changes?: GeometryView['changes']): number[] {
  return selection.filter(index => !changes?.deleted_atoms.includes(index))
    .map(index => changes?.index_map[String(index)] ?? index);
}
export function coordinateType(count: number) { return count === 2 ? 'bond' : count === 3 ? 'angle' : count === 4 ? 'dihedral' : null; }
const sub = (a: number[], b: number[]) => a.map((n, i) => n - b[i]);
const dot = (a: number[], b: number[]) => a.reduce((n, v, i) => n + v * b[i], 0);
const cross = (a: number[], b: number[]) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
const norm = (a: number[]) => Math.sqrt(dot(a, a));
export function measureCoordinate(atoms: WorkbenchAtom[], selection: number[]): number | null {
  if (!coordinateType(selection.length) || new Set(selection).size !== selection.length) return null;
  const points = selection.map(i => atoms.find(a => a.index === i)).map(a => a ? [a.x, a.y, a.z] : null);
  if (points.some(p => !p)) return null;
  const [a,b,c,d] = points as number[][];
  const u = sub(a,b);
  if (selection.length === 2) return norm(u);
  const v = sub(c,b);
  if (!norm(u) || !norm(v)) return null;
  if (selection.length === 3) return Math.acos(Math.max(-1, Math.min(1, dot(u,v)/(norm(u)*norm(v))))) * 180 / Math.PI;
  const axis = v.map(n => n/norm(v));
  const w = sub(d,c);
  const p = sub(u, axis.map(n => n*dot(u,axis)));
  const q = sub(w, axis.map(n => n*dot(w,axis)));
  if (!norm(p) || !norm(q)) return null;
  return Math.atan2(dot(cross(axis,p),q), dot(p,q))*180/Math.PI;
}
export function curvePoints(frames: FrameSummary[], metric: 'energy_hartree' | 'rms_force' | 'reaction_coordinate') {
  const observed = frames.filter(frame => typeof frame[metric] === 'number');
  const useCoordinate = observed.every(frame => typeof frame.reaction_coordinate === 'number');
  return observed.map(frame => ({ frame: frame.index, x: useCoordinate ? frame.reaction_coordinate as number : frame.index, y: frame[metric] as number, useCoordinate }));
}
export function validateSettings(settings: WorkbenchSettings, generateInput: boolean): string | null {
  if (!generateInput) return null;
  if (!settings.engine || !settings.method?.trim() || settings.basis_set === undefined || settings.charge == null || settings.multiplicity == null) return '生成输入需要明确选择引擎、方法、基组、电荷和多重度。';
  if (!Number.isInteger(settings.charge) || !Number.isInteger(settings.multiplicity) || settings.multiplicity < 1) return '电荷须为整数，多重度须为正整数。';
  return null;
}
export function applyGeometry(draft: Draft, geometry: GeometryView) {
  let invalidated = 0;
  const changes = geometry.changes;
  const remap = <T extends {atoms: number[]}>(coordinates: T[]): T[] => coordinates.flatMap(c => {
    if (changes?.deleted_atoms.some(i => c.atoms.includes(i))) { invalidated++; return []; }
    return [{...c, atoms: c.atoms.map(i => changes?.index_map[String(i)] ?? i)}];
  });
  const mappingChanged = geometry.atoms.length !== draft.geometry.atoms.length || !!changes?.deleted_atoms.length
    || !!changes && Object.entries(changes.index_map).some(([oldIndex, newIndex]) => Number(oldIndex) !== newIndex);
  return { draft: { ...draft, atomMappingChanged: draft.atomMappingChanged || mappingChanged, geometry, frozen: remap(draft.frozen), scans: remap(draft.scans) }, invalidated };
}
export function undoDraft<T extends Draft | null>(history: T[], draft: T) {
  return history.length ? { draft: history[history.length - 1], history: history.slice(0,-1) } : { draft, history };
}

export function draftFromFrame(draft: Draft, geometry: GeometryView, sourcePath: string | null | undefined, sourceFrame: number): Draft {
  return {...draft,geometry,sourcePath,sourceFrame,atomMappingChanged:false,...(draft.atomMappingChanged ? {frozen:[],scans:[]} : {})};
}

export function defineFrozenCoordinate(draft: Draft, atoms: number[], target: string): Draft {
  const kind = coordinateType(atoms.length);
  const measured = measureCoordinate(draft.geometry.atoms,atoms);
  const value = target.trim() ? Number(target) : measured;
  if (!kind || measured == null || value == null || !Number.isFinite(value)) throw new Error('请依次选择 2／3／4 个原子，并填写有限的冻结值或使用当前测量值。');
  return {...draft,frozen:[...draft.frozen.filter(coordinate=>coordinate.atoms.join(',')!==atoms.join(',')),{coord_type:kind,atoms:[...atoms],value}]};
}

export function detectImportFormat(filename: string): WorkbenchInputFormat | null {
  const suffix = filename.split('.').pop()?.toLowerCase();
  if (suffix === 'smi' || suffix === 'smiles') return 'smiles';
  const formats: WorkbenchInputFormat[] = ['xyz','mol','sdf','log','out','gjf','com','inp','pdb','cif'];
  return formats.find(format=>format===suffix) ?? null;
}
