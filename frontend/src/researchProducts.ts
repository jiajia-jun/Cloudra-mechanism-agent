import type { WorkbenchSource } from './workbenchTypes.ts';
export interface ChemicalObject { kind: 'node'|'edge'; id: string }
export interface ProductAssociation extends ChemicalObject { label: string; stage?: string; ref_type: string; ref_id: string }
export interface AssociationReference { ref_type: 'artifact'|'file'|'compute_job'|'tool_result'|'species'; ref_id: string; content_hash?: string; revision?: number }
export interface ResearchProduct { association_ref?: AssociationReference; id: string; kind: 'structure'|'calculation'|'artifact'; title: string; path: string; artifact_id?: string; created_at?: string; state: string; job_type?: string; job_id?: number; source_path?: string; source_frame?: number; can_open: boolean; associations: ProductAssociation[]; files: {path:string;role:string;artifact_id?:string;can_open?:boolean}[] }
export function productSource(product: ResearchProduct): WorkbenchSource {
  if (product.artifact_id) return {artifact_id:product.artifact_id};
  const ref = product.association_ref;
  if (ref?.ref_type === 'file') return {file_evidence:{...ref,ref_type:'file'}};
  return {path:product.path};
}
export function groupProducts(products: ResearchProduct[]) {
  const groups=new Map<string,{key:string;label:string;object:ChemicalObject|null;products:ResearchProduct[]}>();
  for (const p of products) {
    const keys=p.associations.length ? p.associations.map(a=>({key:`${a.kind}:${a.id}`,label:a.label || a.id,object:{kind:a.kind,id:a.id}})) : [{key:`source:${p.job_id ?? p.source_path ?? p.path ?? p.id}`,label:`未关联化学对象 · ${p.job_type || p.source_path?.split('/').pop() || p.title}`,object:null}];
    for (const item of keys) {
      const group=groups.get(item.key) ?? {...item,products:[]};
      if (!group.products.some(existing=>existing.id===p.id)) group.products.push(p);
      groups.set(item.key,group);
    }
  }
  return [...groups.values()];
}

export function associationOperation(product: ResearchProduct, object: ChemicalObject) {
  const ref = product.association_ref;
  if (!ref) throw new Error('此记录尚无可关联的登记引用，请先保存或导入结构。');
  return {op:'attach_ref' as const,graph:'delivery' as const,target_type:object.kind,target_id:object.id,ref};
}
