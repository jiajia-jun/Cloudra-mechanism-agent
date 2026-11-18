export interface Atom3D {
  index: number;
  symbol: string;
  x: number;
  y: number;
  z: number;
}

const whitespace = new Set([' ', '\t', '\r']);
const letters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';
export function parseXyz(xyzText: string): Atom3D[] {
  const lines = xyzText.trim().split('\n');
  const first = lines[0]?.trim() ?? '';
  const hasCount = first.length > 0 && [...first].every(character => '0123456789'.includes(character));
  const atoms: Atom3D[] = [];
  for (const line of lines.slice(hasCount ? 2 : 0)) {
    const fields: string[] = [];
    let token = '';
    for (const character of line.trim()) {
      if (whitespace.has(character)) { if (token) { fields.push(token); token = ''; } }
      else token += character;
    }
    if (token) fields.push(token);
    if (fields.length < 4) continue;
    const symbol = [...fields[0]].filter(character => letters.includes(character)).join('');
    const [x,y,z] = fields.slice(1,4).map(Number);
    if (symbol && [x,y,z].every(Number.isFinite)) atoms.push({index:atoms.length,symbol,x,y,z});
  }
  return atoms;
}

export interface RenderAtom {
  index: number; serial: number; elem: string; x: number; y: number; z: number;
  bonds: number[]; bondOrder: number[]; dx?: number; dy?: number; dz?: number;
}
export function validModeDisplacements(atoms: Atom3D[], displacements?: number[][]): boolean {
  return !!displacements && displacements.length === atoms.length && atoms.length > 0 && displacements.every(vector=>vector.length===3 && vector.every(Number.isFinite));
}
/** Adapt declared graph indices only; addAtoms must never infer connectivity. */
export function toRenderAtoms(atoms: Atom3D[], bonds: {atom1:number;atom2:number;order:number}[], displacements?: number[][]): RenderAtom[] {
  const mode = validModeDisplacements(atoms,displacements) ? displacements : undefined;
  const rendered: RenderAtom[] = atoms.map((atom,index)=>({index,serial:atom.index,elem:atom.symbol,x:atom.x,y:atom.y,z:atom.z,bonds:[],bondOrder:[],...(mode ? {dx:mode[index][0],dy:mode[index][1],dz:mode[index][2]} : {})}));
  const positions = new Map(atoms.map((atom,index)=>[atom.index,index]));
  for (const bond of bonds) {
    const first = positions.get(bond.atom1), second = positions.get(bond.atom2);
    if (first === undefined || second === undefined) throw new Error('显示连接引用了不存在的原子。');
    rendered[first].bonds.push(second); rendered[first].bondOrder.push(bond.order);
    rendered[second].bonds.push(first); rendered[second].bondOrder.push(bond.order);
  }
  return rendered;
}

export function initializeRenderModel(model: Pick<import('3dmol').GLModel,'addAtoms'|'assignBonds'|'addFrame'|'selectedAtoms'>, atoms: RenderAtom[], inferDisplayBonds = false) {
  model.addAtoms(atoms);
  // Reuse 3Dmol's distance links only in its display copy; never change the source graph.
  if (inferDisplayBonds) model.assignBonds();
  // addAtoms alone leaves 3Dmol.frames empty; vibrate/setFrame require a real reference frame.
  model.addFrame(model.selectedAtoms({}));
}

/** Fit the projected display bounds to both viewport axes, including small molecules. */
export function fitProjectedScale(points: {x:number;y:number}[], width: number, height: number, fraction: number): number {
  const spanX=Math.max(...points.map(point=>point.x))-Math.min(...points.map(point=>point.x));
  const spanY=Math.max(...points.map(point=>point.y))-Math.min(...points.map(point=>point.y));
  return Math.min(width*fraction/spanX,height*fraction/spanY);
}

// Orthographic screen axes lie in the camera plane. Projecting the three model
// basis vectors gives the inverse mapping at the current rotation and zoom.
export function pointOnCanvasPlane(view: number[], project: (points: {x:number;y:number;z:number}[]) => {x:number;y:number}[],
  pageX: number, pageY: number): [number, number, number] | null {
  const [x, y, z] = view.map(value => -value);
  const [origin, ...basis] = project([{x,y,z}, {x:x+1,y,z}, {x,y:y+1,z}, {x,y,z:z+1}]);
  const u = basis.map(p => p.x - origin.x), v = basis.map(p => p.y - origin.y);
  const u2 = u.reduce((sum, n) => sum + n*n, 0), v2 = v.reduce((sum, n) => sum + n*n, 0);
  if (!u2 || !v2) return null;
  const dx = (pageX-origin.x)/u2, dy = (pageY-origin.y)/v2;
  return [x+dx*u[0]+dy*v[0], y+dx*u[1]+dy*v[1], z+dx*u[2]+dy*v[2]];
}
