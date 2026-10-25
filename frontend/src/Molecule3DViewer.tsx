import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { api } from './api';
import { useAppearance } from './appearance';

export interface Atom3D {
  index: number;
  symbol: string;
  x: number;
  y: number;
  z: number;
}

export interface Bond3D {
  atom1: number;
  atom2: number;
  order: number;
  dist: number;
}

export interface Molecule3DViewerProps {
  smiles?: string;
  xyz?: string;
  title?: string;
  isTransitionState?: boolean;
  saddleEvidenceSupported?: boolean;
  className?: string;
}

// Standard covalent radii in Angstroms for bond detection
const COVALENT_RADII: Record<string, number> = {
  H: 0.31, He: 0.28,
  Li: 1.28, Be: 0.96, B: 0.84, C: 0.76, N: 0.71, O: 0.66, F: 0.57, Ne: 0.58,
  Na: 1.66, Mg: 1.41, Al: 1.21, Si: 1.11, P: 1.07, S: 1.05, Cl: 1.02, Ar: 1.06,
  K: 2.03, Ca: 1.76, Fe: 1.32, Co: 1.26, Ni: 1.24, Cu: 1.32, Zn: 1.22,
  Br: 1.20, I: 1.39,
};

// Standard CPK element colors
const CPK_COLORS: Record<string, { base: string; light: string; dark: string; radius: number }> = {
  H:  { base: '#e2e8f0', light: '#ffffff', dark: '#94a3b8', radius: 0.32 },
  C:  { base: '#475569', light: '#64748b', dark: '#1e293b', radius: 0.60 },
  N:  { base: '#3b82f6', light: '#60a5fa', dark: '#1d4ed8', radius: 0.58 },
  O:  { base: '#ef4444', light: '#f87171', dark: '#b91c1c', radius: 0.56 },
  F:  { base: '#10b981', light: '#34d399', dark: '#047857', radius: 0.52 },
  Cl: { base: '#10b981', light: '#34d399', dark: '#047857', radius: 0.70 },
  Br: { base: '#b45309', light: '#d97706', dark: '#78350f', radius: 0.76 },
  I:  { base: '#7c3aed', light: '#a78bfa', dark: '#5b21b6', radius: 0.84 },
  P:  { base: '#f97316', light: '#fb923c', dark: '#c2410c', radius: 0.72 },
  S:  { base: '#eab308', light: '#facc15', dark: '#a16207', radius: 0.72 },
  Si: { base: '#94a3b8', light: '#cbd5e1', dark: '#475569', radius: 0.75 },
  B:  { base: '#ec4899', light: '#f472b6', dark: '#be185d', radius: 0.65 },
  Fe: { base: '#e07a5f', light: '#f2cc8f', dark: '#81171b', radius: 0.82 },
  Cu: { base: '#d97706', light: '#f59e0b', dark: '#92400e', radius: 0.80 },
  Zn: { base: '#64748b', light: '#94a3b8', dark: '#334155', radius: 0.80 },
};

const DEFAULT_CPK = { base: '#a855f7', light: '#c084fc', dark: '#7e22ce', radius: 0.60 };

export function parseXyz(xyzText: string): Atom3D[] {
  const lines = xyzText.trim().split(/\r?\n/);
  if (lines.length === 0) return [];
  
  let startIdx = 0;
  // If first line is a single integer count, skip comment line too
  if (/^\s*\d+\s*$/.test(lines[0])) {
    startIdx = 2;
  }

  const atoms: Atom3D[] = [];
  for (let i = startIdx; i < lines.length; i++) {
    const parts = lines[i].trim().split(/\s+/);
    if (parts.length >= 4) {
      const symbol = parts[0].replace(/[^a-zA-Z]/g, '');
      const x = parseFloat(parts[1]);
      const y = parseFloat(parts[2]);
      const z = parseFloat(parts[3]);
      if (!isNaN(x) && !isNaN(y) && !isNaN(z) && symbol) {
        atoms.push({ index: atoms.length, symbol, x, y, z });
      }
    }
  }
  return atoms;
}

export function detectBonds(atoms: Atom3D[]): Bond3D[] {
  const bonds: Bond3D[] = [];
  const n = atoms.length;
  for (let i = 0; i < n; i++) {
    const a1 = atoms[i];
    const r1 = COVALENT_RADII[a1.symbol] ?? 0.77;
    for (let j = i + 1; j < n; j++) {
      const a2 = atoms[j];
      const r2 = COVALENT_RADII[a2.symbol] ?? 0.77;
      const dx = a1.x - a2.x;
      const dy = a1.y - a2.y;
      const dz = a1.z - a2.z;
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
      // Bond cutoff: within 1.28 * (r1 + r2) and > 0.4 Angstroms
      const maxCutoff = (r1 + r2) * 1.28;
      if (dist > 0.4 && dist <= maxCutoff) {
        let order = 1;
        if (dist <= (r1 + r2) * 0.90 && a1.symbol !== 'H' && a2.symbol !== 'H') {
          order = 2;
        }
        bonds.push({ atom1: i, atom2: j, order, dist });
      }
    }
  }
  return bonds;
}

export function Molecule3DViewer({
  smiles,
  xyz,
  title,
  isTransitionState = false,
  saddleEvidenceSupported = false,
  className = '',
}: Molecule3DViewerProps) {
  const appearance = useAppearance();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [atoms, setAtoms] = useState<Atom3D[]>([]);
  const [explicitBonds, setExplicitBonds] = useState<Bond3D[] | null>(null);
  const [numFragments, setNumFragments] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  
  // Interactive view state
  const [rotX, setRotX] = useState<number>(0.3);
  const [rotY, setRotY] = useState<number>(0.6);
  const [zoom, setZoom] = useState<number>(1.0);
  const [panX, setPanX] = useState<number>(0);
  const [panY, setPanY] = useState<number>(0);
  const [autoSpin, setAutoSpin] = useState<boolean>(false);
  const [showLabels, setShowLabels] = useState<boolean>(false);
  const [renderMode, setRenderMode] = useState<'ball_stick' | 'spacefill' | 'wireframe'>('ball_stick');
  const [vibrating, setVibrating] = useState<boolean>(false);
  const [showCoords, setShowCoords] = useState<boolean>(false);

  // Drag interaction refs
  const isDraggingRef = useRef<boolean>(false);
  const isPanningRef = useRef<boolean>(false);
  const lastMouseRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const animFrameRef = useRef<number | null>(null);
  const vibPhaseRef = useRef<number>(0);

  // Stop illustration when selecting another structure, including identical XYZs.
  useEffect(() => { setVibrating(false); }, [xyz, smiles, title, isTransitionState]);

  // Load coordinates from XYZ or SMILES
  useEffect(() => {
    let canceled = false;
    if (xyz && xyz.trim()) {
      const parsed = parseXyz(xyz);
      setAtoms(parsed);
      setExplicitBonds(null);
      setNumFragments(1);
      setError(null);
      setLoading(false);
      return;
    }

    if (smiles && smiles.trim()) {
      setLoading(true);
      setError(null);
      api.chemSmilesToXyz(smiles)
        .then((res) => {
          if (canceled) return;
          if (res.success && res.xyz) {
            const parsed = parseXyz(res.xyz);
            setAtoms(parsed);
            if (res.bonds && res.bonds.length > 0) {
              setExplicitBonds(res.bonds.map((b) => ({
                atom1: b.atom1,
                atom2: b.atom2,
                order: b.order,
                dist: 0,
              })));
            } else {
              setExplicitBonds(null);
            }
            setNumFragments(res.num_fragments ?? 1);
          } else {
            setError(res.error ?? '无法从 SMILES 生成 3D 构象');
            setAtoms([]);
            setExplicitBonds(null);
            setNumFragments(1);
          }
        })
        .catch((err) => {
          if (canceled) return;
          setError(String(err));
          setAtoms([]);
          setExplicitBonds(null);
          setNumFragments(1);
        })
        .finally(() => {
          if (!canceled) setLoading(false);
        });
      return () => {
        canceled = true;
      };
    }

    setAtoms([]);
    setExplicitBonds(null);
    setNumFragments(1);
  }, [xyz, smiles]);

  // Compute center of mass and bonds
  const { center, maxRadius, bonds } = useMemo(() => {
    if (atoms.length === 0) {
      return { center: { x: 0, y: 0, z: 0 }, maxRadius: 1, bonds: [] };
    }
    let cx = 0, cy = 0, cz = 0;
    for (const a of atoms) {
      cx += a.x;
      cy += a.y;
      cz += a.z;
    }
    cx /= atoms.length;
    cy /= atoms.length;
    cz /= atoms.length;

    let maxR = 0.5;
    for (const a of atoms) {
      const d = Math.sqrt((a.x - cx) ** 2 + (a.y - cy) ** 2 + (a.z - cz) ** 2);
      if (d > maxR) maxR = d;
    }

    const b = explicitBonds && explicitBonds.length > 0 ? explicitBonds : detectBonds(atoms);
    return { center: { x: cx, y: cy, z: cz }, maxRadius: maxR, bonds: b };
  }, [atoms, explicitBonds]);

  // Reset view to default
  const handleReset = useCallback(() => {
    setRotX(0.3);
    setRotY(0.6);
    setZoom(1.0);
    setPanX(0);
    setPanY(0);
  }, []);

  // Main 3D Canvas Rendering Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    // 与面板共用主题变量；切换只重绘画布，坐标、选择和旋转状态保持原样。
    const style = getComputedStyle(canvas);
    const color = (name: string) => style.getPropertyValue(`--molecule-${name}`).trim();
    const palette = {
      top: color('bg-top'), bottom: color('bg-bottom'), grid: color('grid'),
      placeholder: color('placeholder'), wire: color('wire'),
      label: color('label'), labelShadow: color('label-shadow'),
    };

    let running = true;

    const render = () => {
      if (!running) return;

      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      ctx.clearRect(0, 0, width, height);

      // Background gradient
      const bgGrad = ctx.createLinearGradient(0, 0, 0, height);
      bgGrad.addColorStop(0, palette.top);
      bgGrad.addColorStop(1, palette.bottom);
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, width, height);

      // Subtle coordinate grid / floor circle
      ctx.save();
      ctx.strokeStyle = palette.grid;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.ellipse(width / 2 + panX, height / 2 + panY + 110 * zoom, 120 * zoom, 34 * zoom, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      if (atoms.length === 0) {
        ctx.fillStyle = palette.placeholder;
        ctx.font = '13px system-ui, -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(loading ? '正在生成三维分子构象…' : error ? `3D 构象不可用: ${error}` : '暂无 3D 坐标数据', width / 2, height / 2);
        return;
      }

      // Update vibration phase
      if (vibrating) {
        vibPhaseRef.current += 0.08;
      }
      const vibAmp = vibrating ? Math.sin(vibPhaseRef.current) * 0.35 : 0;

      // Auto spin
      let curRotY = rotY;
      if (autoSpin) {
        curRotY += 0.008;
        setRotY((r) => r + 0.008);
      }

      // Base scale to fit canvas nicely
      const baseScale = (Math.min(width, height) * 0.38) / (maxRadius || 1);
      const scale = baseScale * zoom;

      // Rotation matrix values
      const cosX = Math.cos(rotX);
      const sinX = Math.sin(rotX);
      const cosY = Math.cos(curRotY);
      const sinY = Math.sin(curRotY);

      // Project each atom to screen coordinates
      interface ProjectedAtom {
        index: number;
        symbol: string;
        sx: number;
        sy: number;
        sz: number;
        radiusPx: number;
        orig: Atom3D;
      }

      const projectedAtoms: ProjectedAtom[] = atoms.map((a, idx) => {
        // Shift to origin
        let x = a.x - center.x;
        let y = a.y - center.y;
        let z = a.z - center.z;

        // Purely illustrative motion; never presented as a computed normal mode.
        if (vibrating) {
          const wave = Math.sin(idx * 1.5 + vibPhaseRef.current);
          x += (x / (maxRadius || 1)) * vibAmp * 0.4;
          y += (y / (maxRadius || 1)) * vibAmp * 0.4;
          z += wave * vibAmp * 0.25;
        }

        // Rotate around Y axis
        const x1 = x * cosY + z * sinY;
        const z1 = -x * sinY + z * cosY;

        // Rotate around X axis
        const y2 = y * cosX - z1 * sinX;
        const z2 = y * sinX + z1 * cosX;

        // Perspective factor
        const distance = 800;
        const perspective = distance / (distance + z2 * scale * 0.5);

        const sx = width / 2 + panX + x1 * scale * perspective;
        const sy = height / 2 + panY - y2 * scale * perspective; // Flip Y for standard screen coordinates

        const cpk = CPK_COLORS[a.symbol] ?? DEFAULT_CPK;
        let rScale = renderMode === 'spacefill' ? 1.6 : renderMode === 'wireframe' ? 0.3 : 1.0;
        const radiusPx = Math.max(4, cpk.radius * (scale / 2.2) * perspective * rScale);

        return {
          index: idx,
          symbol: a.symbol,
          sx,
          sy,
          sz: z2,
          radiusPx,
          orig: a,
        };
      });

      // Prepare render items: atoms and bond cylinders
      type RenderItem =
        | { type: 'atom'; z: number; atom: ProjectedAtom }
        | { type: 'bond'; z: number; p1: ProjectedAtom; p2: ProjectedAtom; order: number };

      const items: RenderItem[] = [];

      for (const pa of projectedAtoms) {
        items.push({ type: 'atom', z: pa.sz, atom: pa });
      }

      if (renderMode !== 'spacefill') {
        for (const b of bonds) {
          const p1 = projectedAtoms[b.atom1];
          const p2 = projectedAtoms[b.atom2];
          if (p1 && p2) {
            const avgZ = (p1.sz + p2.sz) / 2;
            items.push({ type: 'bond', z: avgZ, p1, p2, order: b.order });
          }
        }
      }

      // Sort items by depth (back to front: smaller Z is farther away, rendered first)
      items.sort((a, b) => a.z - b.z);

      // Render each item with depth lighting
      for (const item of items) {
        if (item.type === 'bond') {
          const { p1, p2, order } = item;
          const dx = p2.sx - p1.sx;
          const dy = p2.sy - p1.sy;
          const len = Math.sqrt(dx * dx + dy * dy);
          if (len < 1) continue;

          ctx.save();
          if (renderMode === 'wireframe') {
            ctx.strokeStyle = palette.wire;
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            ctx.moveTo(p1.sx, p1.sy);
            ctx.lineTo(p2.sx, p2.sy);
            ctx.stroke();
          } else {
            // Ball and stick cylinder rendering
            const bondWidth = Math.max(2.5, 5 * (scale / 40) * (800 / (800 + item.z * scale * 0.5)));

            const c1 = CPK_COLORS[p1.symbol]?.base ?? DEFAULT_CPK.base;
            const c2 = CPK_COLORS[p2.symbol]?.base ?? DEFAULT_CPK.base;

            // Two-tone bond cylinder matching atom colors
            const grad = ctx.createLinearGradient(p1.sx, p1.sy, p2.sx, p2.sy);
            grad.addColorStop(0, c1);
            grad.addColorStop(0.5, c1);
            grad.addColorStop(0.5, c2);
            grad.addColorStop(1, c2);

            ctx.strokeStyle = grad;
            ctx.lineCap = 'round';

            if (order === 2) {
              const nx = -dy / len * (bondWidth * 0.7);
              const ny = dx / len * (bondWidth * 0.7);
              ctx.lineWidth = bondWidth * 0.65;
              ctx.beginPath();
              ctx.moveTo(p1.sx + nx, p1.sy + ny);
              ctx.lineTo(p2.sx + nx, p2.sy + ny);
              ctx.moveTo(p1.sx - nx, p1.sy - ny);
              ctx.lineTo(p2.sx - nx, p2.sy - ny);
              ctx.stroke();
            } else {
              ctx.lineWidth = bondWidth;
              ctx.beginPath();
              ctx.moveTo(p1.sx, p1.sy);
              ctx.lineTo(p2.sx, p2.sy);
              ctx.stroke();
            }
          }
          ctx.restore();
        } else if (item.type === 'atom') {
          const { atom } = item;
          const cpk = CPK_COLORS[atom.symbol] ?? DEFAULT_CPK;

          ctx.save();
          if (renderMode === 'wireframe') {
            ctx.strokeStyle = cpk.base;
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            ctx.arc(atom.sx, atom.sy, atom.radiusPx, 0, Math.PI * 2);
            ctx.stroke();
          } else {
            // Spherical radial gradient with light source at top-left
            const lightOffX = atom.radiusPx * 0.35;
            const lightOffY = atom.radiusPx * 0.35;
            const sphereGrad = ctx.createRadialGradient(
              atom.sx - lightOffX,
              atom.sy - lightOffY,
              atom.radiusPx * 0.1,
              atom.sx,
              atom.sy,
              atom.radiusPx,
            );
            sphereGrad.addColorStop(0, cpk.light);
            sphereGrad.addColorStop(0.4, cpk.base);
            sphereGrad.addColorStop(1, cpk.dark);

            ctx.fillStyle = sphereGrad;
            ctx.beginPath();
            ctx.arc(atom.sx, atom.sy, atom.radiusPx, 0, Math.PI * 2);
            ctx.fill();

            // Subtle rim shadow
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.35)';
            ctx.lineWidth = 0.8;
            ctx.stroke();
          }

          // Atom Labels
          if (showLabels || renderMode === 'wireframe') {
            ctx.fillStyle = renderMode === 'wireframe' ? palette.label : '#ffffff';
            ctx.font = `bold ${Math.max(9, Math.round(atom.radiusPx * 0.85))}px system-ui, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.shadowColor = renderMode === 'wireframe' ? palette.labelShadow : 'rgba(0, 0, 0, 0.8)';
            ctx.shadowBlur = 3;
            ctx.fillText(`${atom.symbol}${atom.index + 1}`, atom.sx, atom.sy);
            ctx.shadowBlur = 0;
          }

          ctx.restore();
        }
      }

      if (autoSpin || vibrating) {
        animFrameRef.current = requestAnimationFrame(render);
      }
    };

    render();
    // 面板框体和字体也随风格改变尺寸，静止视口需要在尺寸变化后补画。
    const resizeObserver = new ResizeObserver(() => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      render();
    });
    resizeObserver.observe(canvas);

    return () => {
      running = false;
      resizeObserver.disconnect();
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [appearance, atoms, bonds, center, maxRadius, rotX, rotY, zoom, panX, panY, autoSpin, showLabels, renderMode, vibrating, loading, error]);

  // Mouse drag & wheel handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button === 2 || e.shiftKey) {
      isPanningRef.current = true;
    } else {
      isDraggingRef.current = true;
    }
    lastMouseRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const dx = e.clientX - lastMouseRef.current.x;
    const dy = e.clientY - lastMouseRef.current.y;
    lastMouseRef.current = { x: e.clientX, y: e.clientY };

    if (isDraggingRef.current) {
      setRotY((r) => r + dx * 0.008);
      setRotX((r) => Math.max(-Math.PI / 2, Math.min(Math.PI / 2, r + dy * 0.008)));
    } else if (isPanningRef.current) {
      setPanX((px) => px + dx);
      setPanY((py) => py + dy);
    }
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
    isPanningRef.current = false;
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    setZoom((z) => Math.max(0.2, Math.min(6.0, z * factor)));
  };

  return (
    <div className={`molecule-3d-container ${className}`}>
      <div className="viewer-3d-badge" role="note">
        当前显示几何未与科学证据绑定
        {vibrating && ' · 示意动画：非计算简正模，不作为虚频证据'}
      </div>
      {/* Viewer Header / Toolbar */}
      <div className="viewer-3d-header">
        <div className="viewer-3d-title">
          <span className="viewer-3d-badge">3D 立体结构展示器</span>
          {title && <span className="viewer-3d-molname">{title}</span>}
          {isTransitionState && (
            <span className="badge-ts-marker" title="证据状态不代表当前显示几何已确证">
              {saddleEvidenceSupported ? '鞍点证据已支持' : '候选 TS · 未确证'} · 虚频未知
            </span>
          )}
          {atoms.length > 0 && (
            <span className="viewer-3d-atomcount">
              {numFragments > 1 ? `${numFragments} 分子体系 · ` : ''}
              {atoms.length} 原子 · {bonds.length} 键
            </span>
          )}
        </div>

        <div className="viewer-3d-controls">
          <div className="btn-group sm viewer-mode-switch" role="group" aria-label="分子显示方式">
            <button
              type="button"
              className={`btn outline sm ${renderMode === 'ball_stick' ? 'active' : ''}`}
              aria-pressed={renderMode === 'ball_stick'}
              onClick={() => setRenderMode('ball_stick')}
              title="球棍模型 (Ball & Stick)"
            >
              球棍
            </button>
            <button
              type="button"
              className={`btn outline sm ${renderMode === 'spacefill' ? 'active' : ''}`}
              aria-pressed={renderMode === 'spacefill'}
              onClick={() => setRenderMode('spacefill')}
              title="范德华空间填充 (Spacefill / CPK)"
            >
              填充
            </button>
            <button
              type="button"
              className={`btn outline sm ${renderMode === 'wireframe' ? 'active' : ''}`}
              aria-pressed={renderMode === 'wireframe'}
              onClick={() => setRenderMode('wireframe')}
              title="线框模型 (Wireframe)"
            >
              线框
            </button>
          </div>

          <button
            type="button"
            className={`btn outline sm ${showLabels ? 'active' : ''}`}
            aria-pressed={showLabels}
            onClick={() => setShowLabels(!showLabels)}
            title="显示/隐藏原子编号与元素符号"
          >
            编号
          </button>

          <button
            type="button"
            className={`btn outline sm ${autoSpin ? 'active' : ''}`}
            aria-pressed={autoSpin}
            onClick={() => setAutoSpin(!autoSpin)}
            title="自动三维自转"
          >
            {autoSpin ? '停止' : '自转'}
          </button>

          <button
            type="button"
            className={`btn outline sm ${vibrating ? 'active' : ''}`}
            aria-pressed={vibrating}
            onClick={() => setVibrating(!vibrating)}
            title="仅供结构展示的示意动画，不代表计算简正模"
          >
            {vibrating ? '停止示意振动' : '示意振动'}
          </button>

          <button
            type="button"
            className="btn ghost sm"
            onClick={handleReset}
            title="复位视角与缩放"
          >
            复位
          </button>

          <button
            type="button"
            className={`btn ghost sm ${showCoords ? 'active' : ''}`}
            aria-pressed={showCoords}
            onClick={() => setShowCoords(!showCoords)}
            title="查看笛卡尔坐标表 (XYZ)"
          >
            XYZ
          </button>
        </div>
      </div>

      {/* Main Canvas Viewport */}
      <div className="viewer-3d-canvas-wrap">
        <canvas
          ref={canvasRef}
          className="viewer-3d-canvas"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
          onContextMenu={(e) => e.preventDefault()}
        />

        {/* Floating guidance overlay */}
        <div className="viewer-3d-hint">
          <span>拖拽鼠标旋转 · 滚轮缩放 · Shift+拖拽平移</span>
        </div>

        {/* XYZ Coordinates drawer/modal */}
        {showCoords && (
          <div className="viewer-3d-coords-drawer">
            <div className="drawer-header">
              <span>笛卡尔坐标 (XYZ, Å)</span>
              <button type="button" className="btn ghost sm" onClick={() => setShowCoords(false)}>
                ✕
              </button>
            </div>
            <div className="drawer-body">
              <pre className="mono-code">
                {atoms.map((a) => `${a.symbol.padEnd(3)} ${a.x.toFixed(6).padStart(12)} ${a.y.toFixed(6).padStart(12)} ${a.z.toFixed(6).padStart(12)}`).join('\n')}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
