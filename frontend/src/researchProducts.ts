import type { WorkbenchSource } from './workbenchTypes.ts';
export interface ChemicalObject { kind: 'node'|'edge'; id: string }
export interface ProductAssociation extends ChemicalObject { label: string; stage?: string; ref_type: string; ref_id: string }
export interface AssociationReference { ref_type: 'artifact'|'file'|'compute_job'|'tool_result'|'species'; ref_id: string; content_hash?: string; revision?: number }
export interface ResearchProduct { association_ref?: AssociationReference; id: string; kind: 'structure'|'calculation'|'artifact'; title: string; path: string; artifact_id?: string; created_at?: string; state: string; job_type?: string; job_id?: string; source_path?: string; source_frame?: number; can_open: boolean; associations: ProductAssociation[]; files: {path:string;role:string}[]; preview_xyz?: string }
export function productSource(product: ResearchProduct): WorkbenchSource { return product.artifact_id ? {artifact_id:product.artifact_id} : {path:product.path}; }
export function filterProducts(products: ResearchProduct[], selected: ChemicalObject | null, search: string) {
  const query=search.trim().toLowerCase();
  return products.filter(p=>(!selected || p.associations.some(a=>a.kind===selected.kind && a.id===selected.id)) && (!query || [p.title,p.path,p.job_type,p.state,...p.associations.map(a=>a.label)].filter(Boolean).join(' ').toLowerCase().includes(query)));
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
