import { useEffect, useMemo, useRef, useState } from 'react';
import type { AtomSpec, AtomStyleSpec, GLViewer, Label } from '3dmol';
import { api } from './api';
import { useAppearance } from './appearance';
import { parseXyz, initializeRenderModel, fitProjectedScale, toRenderAtoms, validModeDisplacements } from './moleculeRendering';
import type { Atom3D } from './moleculeRendering';
import './moleculeViewer.css';
export { parseXyz } from './moleculeRendering';
export type { Atom3D } from './moleculeRendering';

export interface Molecule3DViewerProps {
  smiles?: string;
  xyz?: string;
  title?: string;
  isTransitionState?: boolean;
  saddleEvidenceSupported?: boolean;
  className?: string;
  compact?: boolean;
  geometry?: { atoms: Atom3D[]; bonds: { atom1: number; atom2: number; order: number }[]; graph_status?: string };
  selectedAtoms?: number[];
  onAtomPick?: (index: number) => void;
  modeDisplacements?: number[][];
  modePlaying?: boolean;
  preserveView?: boolean;
  coordinateHighlights?: number[][];

}

const NO_SELECTION: number[] = [];
const NO_HIGHLIGHTS: number[][] = [];
type MolecularEngine = typeof import('3dmol');
// The library has no destroy API. Keep only the interactive viewers actually needed,
// and one renderer for all static thumbnails, rather than leaking constructor listeners.
interface ViewerSlot { viewer: GLViewer; host: HTMLDivElement; available: boolean }
const interactiveSlots: ViewerSlot[] = [];
let thumbnailSlot: ViewerSlot | null = null;
let parkingHost: HTMLDivElement | null = null;
function parking() {
  if (!parkingHost) {
    parkingHost=document.createElement('div');
    parkingHost.setAttribute('aria-hidden','true');
    Object.assign(parkingHost.style,{position:'fixed',left:'-10000px',top:'0',width:'600px',height:'400px',visibility:'hidden',pointerEvents:'none'});
    document.body.append(parkingHost);
  }
  return parkingHost;
}
function newViewer(engine: MolecularEngine, compact: boolean): ViewerSlot {
  const host=document.createElement('div');
  Object.assign(host.style,{position:'absolute',inset:'0',width:'100%',height:'100%'});
  parking().append(host);
  const viewer=engine.createViewer(host,{
    backgroundAlpha:0,antialias:true,upscale:!compact,orthographic:true,
    nomouse:compact,disableFog:true,hoverDuration:120,minimumZoomToDistance:0.5,
    defaultcolors:{...engine.elementColors.Jmol,C:0x526173,H:0xf1f3f5},
  });
  viewer.setViewStyle({style:'outline ambientOcclusion',color:0x26313b,width:0.012,strength:0.45,radius:2.2});
  return {viewer,host,available:false};
}
function acquireViewer(engine: MolecularEngine, mount: HTMLElement, compact: boolean): ViewerSlot {
  if (compact) {
    thumbnailSlot??=newViewer(engine,true);
    return thumbnailSlot;
  }
  let slot=interactiveSlots.find(candidate=>candidate.available);
  if (!slot) {slot=newViewer(engine,false);interactiveSlots.push(slot);}
  slot.available=false;
  // Move its existing container, not setContainer(), which would rebind canvas handlers.
  mount.append(slot.host);
  slot.viewer.resize();
  return slot;
}


export function Molecule3DViewer({
  smiles, xyz, title, isTransitionState = false, saddleEvidenceSupported = false,
  className = '', compact = false, geometry, selectedAtoms = NO_SELECTION, onAtomPick,
  modeDisplacements, modePlaying = false, preserveView = false, coordinateHighlights = NO_HIGHLIGHTS,
}: Molecule3DViewerProps) {
  const appearance = useAppearance();
  const hostRef = useRef<HTMLDivElement>(null);
  const pickRef = useRef(onAtomPick); pickRef.current = onAtomPick;
  const [engine, setEngine] = useState<MolecularEngine | null>(null);
  const [viewer, setViewer] = useState<GLViewer | null>(null);
  const [thumbnail, setThumbnail] = useState('');
  const [visible, setVisible] = useState(!compact);
  const [legacyGeometry, setLegacyGeometry] = useState<{atoms: Atom3D[]; bonds: {atom1:number;atom2:number;order:number}[]; graph_status?: string}>({atoms:[],bonds:[]});
  const [loading, setLoading] = useState(false);
  const [sourceError, setSourceError] = useState('');
  const [renderError, setRenderError] = useState('');
  const [numFragments, setNumFragments] = useState(1);
  const [autoSpin, setAutoSpin] = useState(false);
  const [showLabels, setShowLabels] = useState(false);
  const [showCoords, setShowCoords] = useState(false);
  const [renderMode, setRenderMode] = useState<'ball_stick'|'spacefill'|'wireframe'>('ball_stick');
  const lastDataRef = useRef<{atoms: ReturnType<typeof toRenderAtoms>; preserveView: boolean} | null>(null);
  const initialViewRef = useRef<number[] | null>(null);
  const fittedModeRef = useRef('');
  const active = !compact || visible;
  const structure = geometry ?? legacyGeometry;
  const inferDisplayBonds = structure.graph_status === 'unresolved' && structure.bonds.length === 0;
  const modeIsReal = validModeDisplacements(structure.atoms, modeDisplacements);
  const renderData = useMemo(() => {
    try { return {atoms:toRenderAtoms(structure.atoms,structure.bonds,modeDisplacements),error:''}; }
    catch(error) { return {atoms:[],error:error instanceof Error ? error.message : String(error)}; }
  },[structure,modeDisplacements]);

  useEffect(() => {
    let cancelled = false;
    setSourceError(''); setNumFragments(1);
    if (geometry) { setLoading(false); return; }
    if (xyz?.trim()) {
      // XYZ has no graph; distance links exist only in the display model.
      setLegacyGeometry({atoms:parseXyz(xyz).map(atom=>({...atom,index:atom.index+1})),bonds:[],graph_status:'unresolved'});
      setLoading(false); return;
    }
    setLegacyGeometry({atoms:[],bonds:[]});
    if (!smiles?.trim()) { setLoading(false); return; }
    setLoading(true);
    api.chemSmilesToXyz(smiles).then(result => {
      if (cancelled) return;
      if (!result.success || !result.xyz) throw new Error(result.error ?? '无法从 SMILES 生成三维构象');
      setLegacyGeometry({atoms:parseXyz(result.xyz).map(atom=>({...atom,index:atom.index+1})),bonds:(result.bonds??[]).map(bond=>({...bond,atom1:bond.atom1+1,atom2:bond.atom2+1}))});
      setNumFragments(result.num_fragments??1);
    }).catch(error=>{if(!cancelled)setSourceError(error instanceof Error?error.message:String(error));}).finally(()=>{if(!cancelled)setLoading(false);});
    return ()=>{cancelled=true;};
  },[xyz,smiles,!!geometry]);

  useEffect(() => {
    if (!compact) return;
    const host = hostRef.current;
    if (!host) return;
    const observer = new IntersectionObserver(entries=>setVisible(entries.some(entry=>entry.isIntersecting)));
    observer.observe(host);
    return ()=>observer.disconnect();
  },[compact]);

  useEffect(() => {
    if (!active || engine) return;
    let cancelled = false;
    import('3dmol/build/3Dmol.es6-min.js').then(module=>{if(!cancelled)setEngine(module);}).catch(error=>{if(!cancelled)setRenderError(String(error));});
    return ()=>{cancelled=true;};
  },[active,engine]);

  useEffect(() => {
    const host = hostRef.current;
    if (!engine || !host || !active) return;
    let slot: ViewerSlot;
    try {
      slot=acquireViewer(engine,host,compact);
      lastDataRef.current=null;initialViewRef.current=null;fittedModeRef.current='';
      setRenderError(''); setViewer(slot.viewer);
    } catch(error) {
      setRenderError(`WebGL 三维显示不可用：${error instanceof Error?error.message:String(error)}`);
      return;
    }
    const resize = new ResizeObserver(()=>{if(!compact)slot.viewer.resize();});
    resize.observe(host);
    return ()=>{
      resize.disconnect();
      if (!compact) {
        slot.viewer.spin(false);slot.viewer.stopAnimate();slot.viewer.clear();
        parking().append(slot.host);slot.available=true;
      }
      setViewer(null);
    };
  },[engine,active,compact]);

  useEffect(() => {
    if (!viewer || !engine || !active) return;
    const host=hostRef.current;
    if (!host) return;
    const theme=getComputedStyle(host);
    const background=theme.getPropertyValue('--molecule-bg-top').trim();
    const foreground=theme.getPropertyValue('--fg').trim();
    const highlight=theme.getPropertyValue('--yellow').trim();
    if (compact) {
      const parent=parking();parent.style.width=`${host.clientWidth || 300}px`;parent.style.height=`${host.clientHeight || 165}px`;
      viewer.resize();viewer.setView([0,0,0,0,0,0,0,1]);
    }
    viewer.stopAnimate(); viewer.clear();
    if (!renderData.atoms.length) { viewer.render(); return; }
    const model=viewer.addModel();
    initializeRenderModel(model,renderData.atoms,inferDisplayBonds);
    const style: AtomStyleSpec = renderMode==='spacefill' ? {sphere:{scale:1}} : renderMode==='wireframe' ? {line:{linewidth:2},sphere:{scale:0.075}} : {sphere:{scale:0.27},stick:{radius:0.115}};
    model.setStyle({},style);
    if (selectedAtoms.length) model.setStyle({index:renderData.atoms.filter(atom=>selectedAtoms.includes(atom.serial)).map(atom=>atom.index)},{...style,sphere:{scale:renderMode==='spacefill'?1:renderMode==='wireframe'?0.13:0.3,color:highlight}});
    model.setClickable({},!!pickRef.current,(atom:AtomSpec)=>{if(atom.serial!=null)pickRef.current?.(atom.serial);});
    let hovered: Label | null = null;
    if (!compact) model.setHoverable({},true,(atom:AtomSpec)=>{
      if (hovered) viewer.removeLabel(hovered);
      const position=structure.atoms.find(source=>source.index===atom.serial);
      if (!position) return;
      hovered=viewer.addLabel(`${atom.elem}${atom.serial}`,{position,fontSize:12,fontColor:foreground,backgroundColor:background,backgroundOpacity:0.94,borderThickness:0,screenOffset:new engine.Vector2(0,22),inFront:true,alignment:'center'});
      viewer.render();
    },()=>{if(hovered){viewer.removeLabel(hovered);hovered=null;viewer.render();}});
    if (!compact) for (const atom of structure.atoms) {
      const order=selectedAtoms.indexOf(atom.index);
      if (!showLabels && order<0) continue;
      viewer.addLabel(`${atom.symbol}${atom.index}${order>=0?` · 选${order+1}`:''}`,{
        position:atom,screenOffset:new engine.Vector2(0,order>=0?25:19),alignment:'center',
        font:'system-ui',fontSize:order>=0?13:11,fontColor:order>=0?highlight:foreground,
        backgroundColor:background,backgroundOpacity:0.93,borderColor:highlight,borderThickness:order>=0?1:0,
        inFront:true,
      });
    }
    for (const indices of coordinateHighlights) for (let index=1;index<indices.length;index++) {
      const start=structure.atoms.find(atom=>atom.index===indices[index-1]);
      const end=structure.atoms.find(atom=>atom.index===indices[index]);
      if(start && end)viewer.addLine({start,end,color:highlight,dashed:true,linewidth:2});
    }
    const keepCamera = preserveView && lastDataRef.current?.preserveView;
    const geometryChanged = lastDataRef.current?.atoms!==renderData.atoms;
    if (compact || !initialViewRef.current || (!keepCamera && geometryChanged) || fittedModeRef.current!==renderMode) {
      if (compact || !initialViewRef.current) viewer.setView([0,0,0,0,0,0,0,1]);
      viewer.zoomTo();
      if (compact || !initialViewRef.current) { viewer.rotate(17,'x'); viewer.rotate(-24,'y'); }
      const padding=renderMode==='spacefill'?2.2:renderMode==='wireframe'?0.2:0.6;
      const bounds=(['x','y','z'] as const).map(axis=>[Math.min(...structure.atoms.map(atom=>atom[axis]))-padding,Math.max(...structure.atoms.map(atom=>atom[axis]))+padding]);
      const corners=bounds[0].flatMap(x=>bounds[1].flatMap(y=>bounds[2].map(z=>({x,y,z}))));
      const viewport=compact?parking():host;
      viewer.zoom(fitProjectedScale(viewer.modelToScreen(corners),viewport.clientWidth,viewport.clientHeight,compact?0.74:0.82));
      fittedModeRef.current=renderMode;
      initialViewRef.current=viewer.getView();
    }
    lastDataRef.current={atoms:renderData.atoms,preserveView};
    viewer.render();
    if (compact) setThumbnail(viewer.pngURI());
    if (!compact && modePlaying && modeIsReal) {
      model.vibrate(20,0.7,true);
      viewer.animate({loop:'backAndForth',interval:35,startFrame:20});
    }
    return ()=>{viewer.stopAnimate();};
  },[viewer,engine,active,renderData,structure,inferDisplayBonds,selectedAtoms,renderMode,showLabels,modePlaying,modeIsReal,preserveView,coordinateHighlights,compact,appearance,!!onAtomPick]);

  useEffect(()=>{if(viewer && active && !compact)viewer.spin(autoSpin?'y':false,0.45,true);},[viewer,autoSpin,active,compact]);
  const error=sourceError || renderData.error || renderError;
  const reset=()=>{if(viewer && initialViewRef.current){viewer.setView(initialViewRef.current);viewer.render();}};
  return <div className={`molecule-3d-container molecule-webgl ${compact?'molecule-compact':''} ${className}`}>
    {!compact && <><div className="viewer-3d-badge viewer-evidence-note" role="note">{modeDisplacements?'实际计算简正模 · 位移幅度已缩放':'当前显示几何未与科学证据绑定'}</div>
      <div className="viewer-3d-header"><div className="viewer-3d-title"><span className="viewer-3d-badge">3D 分子结构</span>{title && <span className="viewer-3d-molname">{title}</span>}{isTransitionState && <span className="badge-ts-marker">{saddleEvidenceSupported?'鞍点证据已支持':'候选 TS · 未确证'}</span>}{structure.atoms.length>0 && <span className="viewer-3d-atomcount">{numFragments>1?`${numFragments} 分子体系 · `:''}{structure.atoms.length} 原子 · {inferDisplayBonds?'按距离显示连线':`${structure.bonds.length} 键`}</span>}</div>
        <div className="viewer-3d-controls"><div className="btn-group sm viewer-mode-switch" role="group" aria-label="分子显示方式">{([['ball_stick','球棍'],['spacefill','填充'],['wireframe','线框']] as const).map(([value,label])=><button key={value} type="button" className={`btn outline sm ${renderMode===value?'active':''}`} aria-pressed={renderMode===value} onClick={()=>setRenderMode(value)}>{label}</button>)}</div>
          <button type="button" className={`btn outline sm ${showLabels?'active':''}`} aria-pressed={showLabels} onClick={()=>setShowLabels(!showLabels)}>编号</button><button type="button" className={`btn outline sm ${autoSpin?'active':''}`} aria-pressed={autoSpin} onClick={()=>setAutoSpin(!autoSpin)}>{autoSpin?'停止自转':'自转'}</button><button type="button" className="btn ghost sm" onClick={reset}>复位</button><button type="button" className={`btn ghost sm ${showCoords?'active':''}`} aria-pressed={showCoords} onClick={()=>setShowCoords(!showCoords)}>XYZ</button>
        </div>
      </div></>}
    <div className="viewer-3d-canvas-wrap"><div ref={hostRef} className="viewer-webgl-host" aria-label={title?`${title} 三维分子结构`:'三维分子结构'}>{compact && thumbnail && <img className="viewer-webgl-snapshot" src={thumbnail} alt="实际分子结构预览"/>}</div>
      {(error || loading || !structure.atoms.length || !viewer && active) && <div className={`viewer-webgl-status ${error?'viewer-webgl-error':''}`} role={error?'alert':'status'}>{error || (loading?'正在生成三维构象…':!structure.atoms.length?'暂无三维坐标':'正在载入三维视图…')}</div>}
      {!compact && <div className="viewer-3d-hint"><span>{onAtomPick?'点击原子选择 · ':''}拖动旋转 · 滚轮缩放 · 右键拖动平移</span></div>}
      {showCoords && !compact && <div className="viewer-3d-coords-drawer"><div className="drawer-header"><span>笛卡尔坐标 (Å)</span><button type="button" className="btn ghost sm" onClick={()=>setShowCoords(false)}>✕</button></div><div className="drawer-body"><pre className="mono-code">{structure.atoms.map(atom=>`${atom.index.toString().padStart(4)} ${atom.symbol.padEnd(3)} ${atom.x.toFixed(6).padStart(12)} ${atom.y.toFixed(6).padStart(12)} ${atom.z.toFixed(6).padStart(12)}`).join('\n')}</pre></div></div>}
    </div>
  </div>;
}
