import type { GeometryView, WorkbenchAtom } from './workbenchTypes.ts';

export type Vec3 = [number, number, number];
export type Cell = [Vec3, Vec3, Vec3];
export interface AtomImage { index: number; image: Vec3 }
export interface Marker { label: string; kind: 'atoms' | 'site'; atoms: AtomImage[] }
export interface BoundMarker extends Omit<Marker, 'atoms'> { atoms: (AtomImage & { atomId?: string })[] }
export interface AnnotationDraft { markers: BoundMarker[]; next: number; text: string; sentMarkers?: BoundMarker[] }
export interface SceneAtom extends WorkbenchAtom { sourceIndex: number; image: Vec3 }
export interface DisplayMarker { label: string; kind: Marker['kind']; points: Vec3[]; center: Vec3 }

const origin: Vec3 = [0, 0, 0];
const axes = [0, 1, 2] as const;

export function resolveMarkers(markers: BoundMarker[], geometry: GeometryView) {
  if (!markers.length) return {resolved:[], missing:[]};
  const byId = new Map(geometry.atoms.map(atom => [atom.atom_id, atom.index]));
  const byIndex = new Set(geometry.atoms.map(atom => atom.index));
  const resolved: Marker[] = [];
  const missing: string[] = [];
  for (const marker of markers) {
    const atoms: AtomImage[] = [];
    for (const ref of marker.atoms) {
      const index = ref.atomId ? byId.get(ref.atomId) : ref.index;
      if (index !== undefined && byIndex.has(index)) atoms.push({index, image:ref.image});
    }
    if (atoms.length === marker.atoms.length) resolved.push({label:marker.label, kind:marker.kind, atoms});
    else missing.push(marker.label);
  }
  return {resolved, missing};
}

function translated(point: Vec3, cell: Cell | undefined, shift: Vec3): Vec3 {
  if (!cell) return point;
  return axes.map(axis => point[axis] + shift.reduce((sum, n, i) => sum + n * cell[i][axis], 0)) as Vec3;
}

export function sceneAtoms(geometry: GeometryView, neighbors: boolean): SceneAtom[] {
  const offsets: Vec3[] = [origin];
  if (neighbors && geometry.cell && geometry.pbc) {
    const values = geometry.pbc.map(enabled => enabled ? [-1, 0, 1] : [0]);
    for (const a of values[0]) for (const b of values[1]) for (const c of values[2]) {
      if (a || b || c) offsets.push([a, b, c]);
    }
  }
  return offsets.flatMap((image, tile) => geometry.atoms.map(atom => {
    const [x, y, z] = translated([atom.x, atom.y, atom.z], geometry.cell, image);
    return { ...atom, x, y, z, index: tile * geometry.atoms.length + atom.index, sourceIndex: atom.index, image };
  }));
}

export function atomImageLabel(atom: SceneAtom): string {
  return atom.symbol + atom.sourceIndex + (atom.image.some(Boolean) ? ' [' + atom.image.join(',') + ']' : '');
}

export function displayMarkers(markers: Marker[], geometry: GeometryView): DisplayMarker[] {
  const atoms = new Map(geometry.atoms.map(atom => [atom.index, atom]));
  return markers.map(mark => {
    const points = mark.atoms.map(ref => {
      const atom = atoms.get(ref.index)!;
      return translated([atom.x, atom.y, atom.z], geometry.cell, ref.image);
    });
    const center = axes.map(i => points.reduce((sum, p) => sum + p[i], 0) / points.length) as Vec3;
    return { label: mark.label, kind: mark.kind, points, center };
  });
}

export function cellEdges(cell: Cell): [Vec3, Vec3][] {
  const edges: [Vec3, Vec3][] = [];
  for (let mask = 0; mask < 8; mask++) {
    const from = axes.map(axis => (mask >> axis) & 1) as Vec3;
    for (const axis of axes) {
      if (from[axis]) continue;
      const to: Vec3 = [...from];
      to[axis] = 1;
      edges.push([translated(origin, cell, from), translated(origin, cell, to)]);
    }
  }
  return edges;
}

export function markerLabel(sequence: number): string {
  const letter = String.fromCharCode(65 + sequence % 26);
  return sequence < 26 ? letter : markerLabel(Math.floor(sequence / 26) - 1) + letter;
}
