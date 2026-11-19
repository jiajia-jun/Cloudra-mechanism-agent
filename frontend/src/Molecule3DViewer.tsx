import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type Ref } from 'react';
import type { AtomSpec, AtomStyleSpec, GLModel, GLViewer, Label } from '3dmol';
import { api } from './api';
import { useAppearance } from './appearance';
import { parseXyz, initializeRenderModel, fitProjectedScale, pointOnCanvasPlane, toRenderAtoms, validModeDisplacements } from './moleculeRendering';
import type { Atom3D } from './moleculeRendering';
import { cellEdges, type Cell, type DisplayMarker, type Vec3 } from './workbenchAnnotations';
import './moleculeViewer.css';
export { parseXyz } from './moleculeRendering';
export type { Atom3D } from './moleculeRendering';

export interface ViewerCapture {
  capture: () => Promise<{ image: Blob; camera: number[] }>;
}
const xyzPoint = ([x,y,z]: Vec3) => ({x,y,z});
export interface Molecule3DViewerProps {
  captureRef?: Ref<ViewerCapture>;
  markers?: DisplayMarker[];
  cell?: Cell;
  atomLabels?: Map<number, string>;
  smiles?: string;
  xyz?: string;
  title?: string;
  isTransitionState?: boolean;
  saddleEvidenceSupported?: boolean;
  className?: string;
  compact?: boolean;
  geometry?: { atoms: Atom3D[]; bonds: { atom1: number; atom2: number; order: number }[]; graph_status?: string; manual_bonds?: boolean };
  selectedAtoms?: number[];
  movingAtoms?: number[];
  onAtomPick?: (index: number) => void;
  onBackgroundClick?: (position: [number, number, number]) => void;
  editing?: boolean;
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
  captureRef, markers, cell, atomLabels, smiles, xyz, title, isTransitionState = false, saddleEvidenceSupported = false,
  className = '', compact = false, geometry, selectedAtoms = NO_SELECTION, movingAtoms = NO_SELECTION, onAtomPick, onBackgroundClick, editing = false,
  modeDisplacements, modePlaying = false, preserveView = false, coordinateHighlights = NO_HIGHLIGHTS,
}: Molecule3DViewerProps) {
  const appearance = useAppearance();
  const hostRef = useRef<HTMLDivElement>(null);
  const pickRef = useRef(onAtomPick); pickRef.current = onAtomPick;
  const backgroundClickRef = useRef(onBackgroundClick); backgroundClickRef.current = onBackgroundClick;
  const pickedRef = useRef(false);
  const primaryPick = useRef(false);
  const modelRef = useRef<GLModel | null>(null);
  const selectionModelRef = useRef<GLModel | null>(null);
  const hoveredRef = useRef<Label | null>(null);
  const handleAtomPick = useCallback((atom:AtomSpec)=>{
    if (!primaryPick.current) return;
    pickedRef.current=true;
    if(atom.serial!=null)pickRef.current?.(atom.serial);
  },[]);
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
  const inferDisplayBonds = structure.graph_status === 'unresolved' && structure.bonds.length === 0 && !geometry?.manual_bonds;
  const bondCaption = structure.graph_status === 'distance-inferred' ? '按距离推断连接，键级未知'
    : structure.graph_status === 'unresolved' ? (inferDisplayBonds ? '按距离显示连线，键级未知' : '已手动指定部分连接，键级图未确定')
    : structure.graph_status === 'perceived' ? `${structure.bonds.length} 键 · 已感知键级` : `${structure.bonds.length} 键`;
  const modeIsReal = validModeDisplacements(structure.atoms, modeDisplacements);
  const renderData = useMemo(() => {
    try { return {atoms:toRenderAtoms(structure.atoms,structure.bonds,modeDisplacements),error:''}; }
    catch(error) { return {atoms:[],error:error instanceof Error ? error.message : String(error)}; }
  },[structure.atoms,structure.bonds,modeDisplacements]);
  // Parent inputs may allocate these arrays on every render without changing them.
  useImperativeHandle(captureRef, () => ({
    async capture() {
      if (!viewer || !modelRef.current || !hostRef.current || renderData.error || renderError) {
        throw new Error('三维画布尚未就绪，无法截取当前视角。');
      }
      const camera = [...viewer.getView()];
      viewer.render();
      const glCanvas = viewer.getCanvas();
      const canvas = document.createElement('canvas');
      canvas.width = glCanvas.width;
      canvas.height = glCanvas.height;
      const ctx = canvas.getContext('2d');
      if (!ctx || !canvas.width || !canvas.height) throw new Error('无法截取当前画布。');
      ctx.fillStyle = getComputedStyle(hostRef.current).getPropertyValue('--molecule-bg-top').trim();
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(glCanvas, 0, 0);
      const image = await new Promise<Blob>((resolve, reject) => canvas.toBlob(
        blob => blob ? resolve(blob) : reject(new Error('无法生成截图。')), 'image/png'));
      return {image, camera};
    },
  }), [viewer, renderData, renderError]);
  const selectionKey = JSON.stringify(selectedAtoms);
  const movingKey = JSON.stringify(movingAtoms);
  const highlightKey = JSON.stringify(coordinateHighlights);
  // Thumbnails share a renderer, so each one must reload its own molecule when
  // the theme changes before capturing a new snapshot.
  const thumbnailAppearance = compact ? appearance : null;

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

  // The molecule and its vibration frames belong to the geometry, not to selection.
  useEffect(() => {
    if (!viewer || !engine || !active) return;
    const host=hostRef.current;
    if (!host) return;
    if (compact) {
      const parent=parking();parent.style.width=`${host.clientWidth || 300}px`;parent.style.height=`${host.clientHeight || 165}px`;
      viewer.resize();viewer.setView([0,0,0,0,0,0,0,1]);
    }
    viewer.stopAnimate();viewer.clear();
    modelRef.current=null;selectionModelRef.current=null;hoveredRef.current=null;
    if (!renderData.atoms.length) {
      if (preserveView && !initialViewRef.current) {
        viewer.setView([0,0,0,0,0,0,0,1]);
        viewer.zoomTo();
        viewer.zoom(0.12);
        initialViewRef.current=viewer.getView();
        fittedModeRef.current=renderMode;
      }
      lastDataRef.current={atoms:renderData.atoms,preserveView};
      viewer.render(); return;
    }
    const model=viewer.addModel();
    modelRef.current=model;
    initializeRenderModel(model,renderData.atoms,inferDisplayBonds);
    if (!compact) {
      model.setClickable({},true,handleAtomPick);
      model.setHoverable({},true,(atom:AtomSpec)=>{
        if (hoveredRef.current) viewer.removeLabel(hoveredRef.current);
        const position=structure.atoms.find(source=>source.index===atom.serial);
        if (!position) return;
        const theme=getComputedStyle(host);
        hoveredRef.current=viewer.addLabel(atomLabels?.get(atom.serial!) ?? `${atom.elem}${atom.serial}`,{
          position,fontSize:12,fontColor:theme.getPropertyValue('--fg').trim(),
          backgroundColor:theme.getPropertyValue('--molecule-bg-top').trim(),backgroundOpacity:0.94,
          borderThickness:0,screenOffset:new engine.Vector2(0,22),inFront:true,alignment:'center',
        });
        viewer.render();
      },()=>{
        if(hoveredRef.current){viewer.removeLabel(hoveredRef.current);hoveredRef.current=null;viewer.render();}
      });
      if (modeIsReal) model.vibrate(20,0.7,true);
    }
  },[viewer,engine,active,renderData,inferDisplayBonds,compact,thumbnailAppearance]);

  useEffect(() => {
    const model=modelRef.current, host=hostRef.current;
    if (!viewer || !model || !host || !active) return;
    const style: AtomStyleSpec = renderMode==='spacefill' ? {sphere:{scale:1}} : renderMode==='wireframe' ? {line:{linewidth:2},sphere:{scale:0.075}} : {sphere:{scale:0.27},stick:{radius:0.115}};
    model.setStyle({},style);
    const keepCamera = preserveView && lastDataRef.current?.preserveView;
    const geometryChanged = lastDataRef.current?.atoms!==renderData.atoms;
    if (compact || !initialViewRef.current || (!keepCamera && geometryChanged) || fittedModeRef.current!==renderMode || (cell && geometryChanged && lastDataRef.current?.atoms.length !== renderData.atoms.length)) {
      if (compact || !initialViewRef.current) viewer.setView([0,0,0,0,0,0,0,1]);
      viewer.zoomTo();
      if (compact || !initialViewRef.current) { viewer.rotate(17,'x'); viewer.rotate(-24,'y'); }
      const padding=renderMode==='spacefill'?2.2:renderMode==='wireframe'?0.2:0.6;
      const extent = cell ? [...structure.atoms, ...cellEdges(cell).flat().map(xyzPoint)] : structure.atoms;
      const bounds=(['x','y','z'] as const).map(axis => {
        let low = Infinity, high = -Infinity;
        for (const atom of extent) { low = Math.min(low,atom[axis]); high = Math.max(high,atom[axis]); }
        return [low-padding,high+padding];
      });
      if (cell) {
        const camera = viewer.getView();
        bounds.forEach(([low,high], i) => { camera[i] = -(low+high)/2; });
        const diagonal = Math.hypot(...bounds.map(([low,high]) => high-low));
        viewer.setSlab(-diagonal,diagonal);
        viewer.setView(camera);
      }
      const corners=bounds[0].flatMap(x=>bounds[1].flatMap(y=>bounds[2].map(z=>({x,y,z}))));
      const viewport=compact?parking():host;
      viewer.zoom(fitProjectedScale(viewer.modelToScreen(corners),viewport.clientWidth,viewport.clientHeight,compact?0.74:0.82));
      fittedModeRef.current=renderMode;
      initialViewRef.current=viewer.getView();
    }
    lastDataRef.current={atoms:renderData.atoms,preserveView};
    viewer.render();
  },[viewer,active,renderData,inferDisplayBonds,renderMode,compact,thumbnailAppearance]);

  useEffect(()=>{
    if(lastDataRef.current)lastDataRef.current.preserveView=preserveView;
  },[preserveView]);

  // Only the selected atoms have an extra sphere model. Changing it leaves the
  // molecule's cached WebGL geometry intact, including its bonds and pick shapes.
  useEffect(() => {
    const host=hostRef.current;
    if (!viewer || !engine || !modelRef.current || !host || !active) return;
    const theme=getComputedStyle(host);
    const background=theme.getPropertyValue('--molecule-bg-top').trim();
    const foreground=theme.getPropertyValue('--fg').trim();
    const highlight=theme.getPropertyValue('--yellow').trim();
    const movingColor=theme.getPropertyValue('--green').trim();
    const moving=new Set(movingAtoms);
    if (selectionModelRef.current) viewer.removeModel(selectionModelRef.current);
    selectionModelRef.current=null;
    viewer.removeAllLabels();viewer.removeAllShapes();hoveredRef.current=null;
    if (selectedAtoms.length || moving.size) {
      const overlay=viewer.addModel();
      selectionModelRef.current=overlay;
      initializeRenderModel(overlay,renderData.atoms.filter(atom=>selectedAtoms.includes(atom.serial) || moving.has(atom.serial)).map(atom=>({...atom,bonds:[],bondOrder:[]})));
      // A small lift avoids coplanar spheres in the space-filling view.
      const scale=renderMode==='spacefill'?1.005:renderMode==='wireframe'?0.13:0.3;
      overlay.setStyle({},{sphere:{scale,color:highlight}});
      if (moving.size) overlay.setStyle({predicate:atom=>atom.serial!=null && moving.has(atom.serial)},{sphere:{scale,color:movingColor}});
      if (!compact) {
        overlay.setClickable({},true,handleAtomPick);
        if (modeIsReal) {
          overlay.vibrate(20,0.7,true);
          void overlay.setFrame(modePlaying ? viewer.getFrame() : 20);
        }
      }
    }
    if (!compact) for (const atom of structure.atoms) {
      const order=selectedAtoms.indexOf(atom.index);
      const isMoving=moving.has(atom.index), highlighted=order>=0 || isMoving;
      if (!showLabels && order<0) continue;
      const color=isMoving?movingColor:order>=0?highlight:foreground;
      viewer.addLabel(`${atomLabels?.get(atom.index) ?? (atom.symbol + atom.index)}${order>=0?` · 选${order+1}`:''}${isMoving?' · 移动':''}`,{
        position:atom,screenOffset:new engine.Vector2(0,highlighted?25:19),alignment:'center',
        font:'system-ui',fontSize:highlighted?13:11,fontColor:color,
        backgroundColor:background,backgroundOpacity:0.93,borderColor:color,borderThickness:highlighted?1:0,
        inFront:true,
      });
    }
    if (cell) for (const [start, end] of cellEdges(cell)) {
      viewer.addLine({start:xyzPoint(start), end:xyzPoint(end), color:foreground, opacity:0.6});
    }
    for (const marker of markers ?? []) {
      const center = xyzPoint(marker.center);
      for (const point of marker.points) {
        viewer.addSphere({center:xyzPoint(point), radius:0.22, color:highlight, opacity:0.85});
        if (marker.points.length > 1) viewer.addLine({start:xyzPoint(point), end:center, color:highlight, dashed:true});
      }
      if (marker.kind === 'site') viewer.addSphere({center,radius:0.16,color:highlight});
      viewer.addLabel(marker.label, {position:center, screenOffset:new engine.Vector2(0,-17),
        alignment:'center', font:'system-ui',fontSize:16,fontColor:foreground,backgroundColor:background,
        borderThickness:2,borderColor:highlight,inFront:true});
    }
    for (const indices of coordinateHighlights) for (let index=1;index<indices.length;index++) {
      const start=structure.atoms.find(atom=>atom.index===indices[index-1]);
      const end=structure.atoms.find(atom=>atom.index===indices[index]);
      if(start && end)viewer.addLine({start,end,color:highlight,dashed:true,linewidth:2});
    }
    viewer.render();
    if (compact) setThumbnail(viewer.pngURI());
  },[viewer,engine,active,renderData,inferDisplayBonds,selectionKey,movingKey,highlightKey,markers,cell,atomLabels,renderMode,showLabels,compact,appearance]);

  useEffect(() => {
    if (!viewer || !active || compact || !modelRef.current) return;
    let cancelled=false;
    if (modePlaying && modeIsReal) viewer.animate({loop:'backAndForth',interval:35,startFrame:20});
    else if (modeIsReal) void viewer.setFrame(20).then(()=>{if(!cancelled)viewer.render();});
    return ()=>{cancelled=true;viewer.stopAnimate();};
  },[viewer,active,compact,renderData,inferDisplayBonds,modePlaying,modeIsReal]);

  useEffect(() => {
    if (!viewer || !active || compact) return;
    const canvas=viewer.getCanvas();
    let press: {id:number;x:number;y:number;moved:boolean;released:boolean;touch:boolean} | null=null;
    const down=(event:PointerEvent)=>{
      pickedRef.current=false;
      press=event.isPrimary && event.button===0 && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey
        ? {id:event.pointerId,x:event.clientX,y:event.clientY,moved:false,released:false,touch:event.pointerType==='touch'} : null;
      primaryPick.current=!!press;
    };
    const move=(event:PointerEvent)=>{
      if (press && event.pointerId === press.id) {
        const tolerance=press.touch ? 5 : 0;
        if (Math.abs(event.clientX-press.x)>tolerance || Math.abs(event.clientY-press.y)>tolerance) {
          press.moved=true; primaryPick.current=false;
        }
      }
    };
    const up=(event:PointerEvent)=>{
      move(event);
      if(press && event.pointerId===press.id)press.released=event.target===canvas;
    };
    const cancel=()=>{press=null;primaryPick.current=false;};
    const click=(event:MouseEvent)=>{
      const tap=press;press=null;
      if (!tap || (tap.touch && !editing) || !tap.released || tap.moved || pickedRef.current || event.button!==0 || event.target!==canvas) return;
      const bounds=canvas.getBoundingClientRect();
      const x=2*(event.clientX-bounds.left)/bounds.width-1;
      const y=1-2*(event.clientY-bounds.top)/bounds.height;
      if (!backgroundClickRef.current || viewer.targetedObjects(x,y,{}).length) return;
      const position=pointOnCanvasPlane(viewer.getView(), points=>viewer.modelToScreen(points), event.pageX, event.pageY);
      if (position) backgroundClickRef.current(position);
    };
    canvas.addEventListener('pointerdown',down);
    document.addEventListener('pointermove',move);
    document.addEventListener('pointerup',up);
    canvas.addEventListener('pointercancel',cancel);
    canvas.addEventListener('wheel',cancel);
    canvas.addEventListener('click',click);
    return ()=>{
      canvas.removeEventListener('pointerdown',down);
      document.removeEventListener('pointermove',move);
      document.removeEventListener('pointerup',up);
      canvas.removeEventListener('pointercancel',cancel);
      canvas.removeEventListener('wheel',cancel);
      canvas.removeEventListener('click',click);
    };
  },[viewer,active,compact,editing]);

  useEffect(()=>{if(viewer && active && !compact)viewer.spin(autoSpin?'y':false,0.45,true);},[viewer,autoSpin,active,compact]);
  const error=sourceError || renderData.error || renderError;
  const reset=()=>{if(viewer && initialViewRef.current){viewer.setView(initialViewRef.current);if(!cell && preserveView && structure.atoms.length)viewer.zoomTo();viewer.render();}};
  return <div className={`molecule-3d-container molecule-webgl ${compact?'molecule-compact':''} ${editing?'wb-drawing':''} ${className}`}>
    {!compact && <><div className="viewer-3d-badge viewer-evidence-note" role="note">{modeDisplacements?'实际计算简正模 · 位移幅度已缩放':'当前显示几何未与科学证据绑定'}</div>
      <div className="viewer-3d-header"><div className="viewer-3d-title"><span className="viewer-3d-badge">{cell ? '周期结构' : '3D 分子结构'}</span>{title && <span className="viewer-3d-molname">{title}</span>}{isTransitionState && <span className="badge-ts-marker">{saddleEvidenceSupported?'鞍点证据已支持':'候选 TS · 未确证'}</span>}{structure.atoms.length>0 && <span className="viewer-3d-atomcount">{numFragments>1?`${numFragments} 分子体系 · `:''}{structure.atoms.length} {cell ? '个可见原子位置' : '原子'}{cell ? '' : ' · '}{cell ? '' : bondCaption}</span>}</div>
        <div className="viewer-3d-controls"><div className="btn-group sm viewer-mode-switch" role="group" aria-label="分子显示方式">{([['ball_stick','球棍'],['spacefill','填充'],['wireframe','线框']] as const).map(([value,label])=><button key={value} type="button" className={`btn outline sm ${renderMode===value?'active':''}`} aria-pressed={renderMode===value} onClick={()=>setRenderMode(value)}>{label}</button>)}</div>
          <button type="button" className={`btn outline sm ${showLabels?'active':''}`} aria-pressed={showLabels} onClick={()=>setShowLabels(!showLabels)}>编号</button><button type="button" className={`btn outline sm ${autoSpin?'active':''}`} aria-pressed={autoSpin} onClick={()=>setAutoSpin(!autoSpin)}>{autoSpin?'停止自转':'自转'}</button><button type="button" className="btn ghost sm" onClick={reset}>复位</button><button type="button" className={`btn ghost sm ${showCoords?'active':''}`} aria-pressed={showCoords} onClick={()=>setShowCoords(!showCoords)}>XYZ</button>
        </div>
      </div></>}
    <div className="viewer-3d-canvas-wrap"><div ref={hostRef} className="viewer-webgl-host" aria-label={title?`${title} 三维分子结构`:'三维分子结构'}>{compact && thumbnail && <img className="viewer-webgl-snapshot" src={thumbnail} alt="实际分子结构预览"/>}</div>
      {(error || loading || !structure.atoms.length || !viewer && active) && <div className={`viewer-webgl-status ${error?'viewer-webgl-error':''}`} role={error?'alert':'status'}>{error || (loading?'正在生成三维构象…':!structure.atoms.length?(editing?'点击画布放置第一个原子或基团':'暂无三维坐标'):'正在载入三维视图…')}</div>}
      {!compact && <div className="viewer-3d-hint"><span>{editing?'点击原子接单键 · 点击空白独立放置 · ':onAtomPick?'点击原子选择 · ':''}{!editing && onBackgroundClick?'点击空白清空 · ':''}左键拖动旋转 · 滚轮缩放 · 中键或 Ctrl + 左键拖动平移</span></div>}
      {showCoords && !compact && <div className="viewer-3d-coords-drawer"><div className="drawer-header"><span>笛卡尔坐标 (Å)</span><button type="button" className="btn ghost sm" onClick={()=>setShowCoords(false)}>✕</button></div><div className="drawer-body"><pre className="mono-code">{structure.atoms.map(atom=>`${(atomLabels?.get(atom.index) ?? atom.index.toString()).padStart(4)} ${atom.symbol.padEnd(3)} ${atom.x.toFixed(6).padStart(12)} ${atom.y.toFixed(6).padStart(12)} ${atom.z.toFixed(6).padStart(12)}`).join('\n')}</pre></div></div>}
    </div>
  </div>;
}
