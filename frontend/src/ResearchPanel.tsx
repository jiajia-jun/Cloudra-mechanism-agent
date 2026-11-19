import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import DagPanel from './DagPanel';
import { Molecule3DViewer } from './Molecule3DViewer';
import type { Project } from './types';
import type { GeometryPreview, WorkbenchSource } from './workbenchTypes';
import { researchPageSize, workbenchApi } from './workbenchApi';
import { associationOperation, groupProducts, productSource } from './researchProducts';
import type { ChemicalObject, ResearchProduct } from './researchProducts';
import './researchProducts.css';

function ProductCard({project,product,objects,onOpen,onSelect,onAssociate}:{project:Project;product:ResearchProduct;objects:(ChemicalObject & {label:string})[];onOpen:(source:WorkbenchSource)=>void;onSelect:(object:ChemicalObject)=>void;onAssociate:(product:ResearchProduct,object:ChemicalObject & {label:string},reason:string)=>Promise<void>}) {
  const [associationOpen,setAssociationOpen]=useState(false);
  const [associationTarget,setAssociationTarget]=useState('');
  const [associationReason,setAssociationReason]=useState('');
  const [associationBusy,setAssociationBusy]=useState(false);
  const [associationError,setAssociationError]=useState('');
  const associate=async()=>{
    const object=objects.find(item=>`${item.kind}:${item.id}`===associationTarget);
    if (!object) return;
    setAssociationBusy(true);setAssociationError('');
    try { await onAssociate(product,object,associationReason);setAssociationOpen(false); }
    catch(error) { setAssociationError(error instanceof Error?error.message:String(error)); }
    finally { setAssociationBusy(false); }
  };
  const [preview,setPreview]=useState<GeometryPreview|null>(null);
  const [previewError,setPreviewError]=useState('');
  const container=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    let cancelled=false;
    setPreview(null);setPreviewError('');
    if (!product.can_open) return;
    const element=container.current;
    if (!element) return;
    const observer=new IntersectionObserver(entries=>{
      if (!entries.some(e=>e.isIntersecting)) return;
      observer.disconnect();
      workbenchApi.preview(project.id,productSource(product)).then(g=>{if(!cancelled)setPreview(g);}).catch(e=>{if(!cancelled)setPreviewError(e instanceof Error?e.message:String(e));});
    });
    observer.observe(element);
    return ()=>{cancelled=true;observer.disconnect();};
  },[project.id,product.id,product.path,product.artifact_id,product.can_open]);
  const extension=product.title.split('.').pop()?.toLowerCase();
  const image=product.artifact_id && ['png','jpg','jpeg','gif','svg','webp'].includes(extension??'');
  const role = product.files.find(file => file.path === product.path)?.role;
  const resultLabel = role === 'path' ? '打开路径轨迹' : role === 'scan' ? '打开扫描轨迹'
    : role === 'candidate' ? '打开候选结构' : '打开结果结构';
  return <article className="research-product-card" ref={container}>
    {preview ? <div className="research-preview" role="button" tabIndex={0} aria-label={`打开 ${product.title}`} onClick={()=>onOpen(productSource(product))} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onOpen(productSource(product));}}}>
      <Molecule3DViewer geometry={preview} cell={preview.cell} compact/>
    </div> : product.can_open ? <div className="research-preview"><span>{previewError || '正在读取结构预览…'}</span></div>
      : image ? <a href={api.artifactDownloadUrl(project.id,product.artifact_id!)} target="_blank" rel="noreferrer"><img className="research-image" src={api.artifactDownloadUrl(project.id,product.artifact_id!)} alt={product.title}/></a> : null}
    <div className="research-product-info"><div className="research-card-title">{product.job_id != null && `#${product.job_id} · `}{product.title}</div><div className="research-product-meta"><span>{product.kind==='structure'?'保存结构':product.kind==='calculation'?'计算记录':'文件产物'}</span><span>{preview?.task_type || product.job_type}</span><span>{product.state || '状态未知'}</span></div>
      {preview && <div className="research-product-meta">{preview.engine && <span>{preview.engine}</span>}{preview.frame_count!=null && <span>{preview.frame_count} 帧</span>}{preview.mode_count!=null && <span>{preview.mode_count} 个实际模式</span>}{preview.selected_frame_facts?.energy_hartree!=null && <span>{preview.selected_frame_facts.energy_hartree} Hartree</span>}{preview.selected_frame_facts?.converged!=null && <span>{preview.selected_frame_facts.converged?'原生记录已收敛':'原生记录未收敛'}</span>}</div>}
      <div className="research-source" title={product.path}>{product.path}</div>{product.source_path && <div className="research-source">派生自 {product.source_path}{product.source_frame!=null?` · 帧 ${product.source_frame+1}`:''}</div>}
      <div className="research-associations">{product.associations.length ? product.associations.map((a,i)=><button key={`${a.kind}:${a.id}:${i}`} type="button" className="btn outline sm" onClick={()=>onSelect({kind:a.kind,id:a.id})} title={`明确记录 ${a.ref_type}: ${a.ref_id}`}>{a.label || a.id}{a.stage?` · ${a.stage}`:''} ↗</button>) : <span>未关联化学对象</span>}</div>
      <div className="research-card-actions">
        {preview && <button className="btn outline sm" onClick={()=>onOpen(productSource(product))}>{product.kind === 'calculation' ? resultLabel : '打开工作台'}</button>}
        {product.artifact_id && <a className="btn ghost sm" href={api.artifactDownloadUrl(project.id,product.artifact_id)} download={product.title}>下载原文件</a>}
        {product.job_id != null && product.files.some(f => f.role === 'output') && <a className="btn outline sm" href={api.jobFileUrl(project.id,product.job_id,'output',false)} target="_blank" rel="noreferrer">查看原始日志</a>}
        {product.files.filter(f => f.role === 'input' && f.can_open).map(f => <button key={f.path} className="btn outline sm" onClick={()=>onOpen({path:f.path})}>打开输入结构</button>)}
      </div>
      {objects.length>0 && product.association_ref && <div className="research-association-editor"><button className="btn ghost sm" onClick={()=>setAssociationOpen(!associationOpen)}>关联对象</button>{associationOpen && <div><label>关联到现有对象<select aria-label={`关联对象 ${product.title}`} className="select sm" value={associationTarget} onChange={event=>setAssociationTarget(event.target.value)}><option value="">选择物种或反应步</option>{objects.map(object=><option key={`${object.kind}:${object.id}`} value={`${object.kind}:${object.id}`}>{object.kind==='node'?'物种':'反应步'} · {object.label || object.id}</option>)}</select></label><label>理由（可选）<input className="input sm" value={associationReason} onChange={event=>setAssociationReason(event.target.value)}/></label><button className="btn outline sm" disabled={!associationTarget || associationBusy} onClick={()=>void associate()}>{associationBusy?'关联中…':'确认关联'}</button><span className="dim">仅记录来源关联，不改变科学验收状态。</span>{associationError && <p role="alert">{associationError}</p>}</div>}</div>}
      {product.files.length>0 && <details><summary>本记录文件（{product.files.length}）</summary>{product.files.map(f => {
        const fileName = f.path.split('/').pop() || f.path;
        const download = f.artifact_id ? api.artifactDownloadUrl(project.id, f.artifact_id)
          : product.job_id != null ? api.jobFileUrl(project.id, product.job_id, f.role) : null;
        return <div className="research-file" key={f.role + f.path}><span title={f.path}>{fileName}</span>
          {download && <a href={download} download={fileName} className="btn ghost sm" aria-label={`下载 ${fileName}`}>下载</a>}
          {(product.kind === 'structure' || f.can_open) && <button className="btn ghost sm" onClick={()=>onOpen(f.artifact_id ? {artifact_id:f.artifact_id} : {path:f.path})}>{f.role === 'candidate' ? '打开候选结构' : f.role === 'path' ? '打开路径轨迹' : f.role === 'scan' ? '打开扫描轨迹' : '打开'}</button>}
        </div>;
      })}</details>}

    </div>
  </article>;
}

export function ResearchPanel({project,onOpenMolecule,onError,onToast,refreshVersion=0,initialJobId}:{project:Project;onOpenMolecule:(source:WorkbenchSource|null)=>void;onError:(e:unknown)=>void;onToast:(kind:'error'|'ok'|'info',text:string)=>void;refreshVersion?:number;initialJobId?:number}) {
  const [products,setProducts]=useState<ResearchProduct[]>([]);
  const [objects,setObjects]=useState<(ChemicalObject & {label:string})[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [search,setSearch]=useState(initialJobId == null ? '' : `#${initialJobId}`);
  const [offset,setOffset]=useState(0);
  const [total,setTotal]=useState(0);
  const resultsRef=useRef<HTMLElement>(null);
  const [selected,setSelected]=useState<ChemicalObject|null>(null);
  const [kind,setKind]=useState<'all'|'structure'|'calculation'|'artifact'>('all');
  const [refresh,setRefresh]=useState(0);
  const refreshAll=useCallback(()=>setRefresh(value=>value+1),[]);
  const dagMode=project.settings.orchestration_mode!=='standard';
  const onErrorRef=useRef(onError);onErrorRef.current=onError;
  useEffect(()=>{if(initialJobId != null) resultsRef.current?.scrollIntoView({block:'start'});},[initialJobId]);
  useEffect(()=>{
    let cancelled=false;
    setLoading(true);setError('');
    const timer=window.setTimeout(() => {
      workbenchApi.products(project.id,search,kind,selected,offset).then(result => {
        if(cancelled) return;
        setProducts(result.products);setObjects(result.objects);setTotal(result.total);setOffset(result.offset);
        if(selected && !result.objects.some(object => object.kind === selected.kind && object.id === selected.id)) {
          setSelected(null);setOffset(0);
        }
      }).catch(e => {if(!cancelled){setError(e instanceof Error ? e.message : String(e));onErrorRef.current(e);}})
        .finally(() => {if(!cancelled)setLoading(false);});
    }, 160);
    return ()=>{cancelled=true;window.clearTimeout(timer);};
  },[project.id,refresh,refreshVersion,search,kind,selected,offset]);
  const selectObject=useCallback((object:ChemicalObject|null)=>{setSelected(object);setOffset(0);},[]);
  const associate=async(product:ResearchProduct,object:ChemicalObject & {label:string},reason:string)=>{
    const projection=await api.dagProjection(project.id);
    const revisions=(projection?.revisions as Record<string,number>|undefined)??{};
    const result=await api.dagMutations(project.id,[associationOperation(product,object)],revisions,reason.trim() || `人工关联来源到 ${object.label || object.id}`);
    if(result.accepted===false) throw new Error(String(result.rejection_reason??result.rejection_code??'关联未被接受'));
    onToast('ok','已记录文件与化学对象的关联。');
    refreshAll();
  };
  const groups=groupProducts(products);
  return <div className="research-panel"><div className="research-header"><div><strong>结构、计算与机理</strong><span className="dim">{loading ? '…' : total} 项记录</span></div><div className="research-actions"><button className="btn outline sm" onClick={()=>onOpenMolecule(null)}>新建／导入分子</button><button className="btn ghost sm" onClick={refreshAll} disabled={loading}>刷新</button></div></div>
    {dagMode && <div className="research-dag"><DagPanel project={project} onError={onError} onToast={onToast} onOpenMolecule={onOpenMolecule} onSelectObject={selectObject} selectedObject={selected} refreshVersion={refresh+refreshVersion} onChanged={refreshAll}/></div>}
    <section className="research-products" ref={resultsRef}><div className="research-filters"><input className="input sm" aria-label="搜索结构与计算" placeholder="搜索结构、来源文件或 #作业号" value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}}/><select className="select sm" aria-label="结果类型" value={kind} onChange={e=>{setKind(e.target.value as typeof kind);setOffset(0);}}><option value="all">全部结果</option><option value="structure">保存结构</option><option value="calculation">计算记录</option><option value="artifact">文件产物</option></select>{selected && <button className="btn outline sm" onClick={()=>selectObject(null)}>显示全部（已筛选 {selected.kind==='node'?'物种':'反应步'} {selected.id}）×</button>}</div>
      {error ? <p role="alert">{error}</p> : loading ? <div className="chat-empty">正在读取项目结构与计算记录…</div> : !groups.length ? <div className="chat-empty">{search || selected || kind !== 'all' ? '当前筛选条件下没有匹配记录。' : '尚无保存结构或计算产物，可直接新建或导入分子。'}</div> : groups.map(group=><section key={group.key} className="research-group"><h3>{group.label}</h3><div className="research-cards">{group.products.map(product=><ProductCard key={product.id} project={project} product={product} objects={objects} onOpen={onOpenMolecule} onSelect={selectObject} onAssociate={associate}/>)}</div></section>)}
      {!loading && !error && (offset>0 || total>products.length) && <nav className="research-actions" aria-label="研究结果分页">
        <button type="button" className="btn outline sm" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-researchPageSize))}>上一页</button>
        <span>{offset+1}–{offset+products.length} / {total}</span>
        <button type="button" className="btn outline sm" disabled={offset+products.length>=total} onClick={()=>setOffset(offset+products.length)}>下一页</button>
      </nav>}
    </section>
  </div>;
}
