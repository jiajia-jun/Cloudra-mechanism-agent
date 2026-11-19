import { request, requestText } from './api';
import type { ChemicalObject, ResearchProduct } from './researchProducts';
import type { DocumentView, EditRequest, FragmentEntry, GeometryView, GeometryPreview, SaveRequest, SaveResult, SnapshotRequest, WorkbenchSource } from './workbenchTypes';
export type * from './workbenchTypes';
const base = (project: string) => `/api/v2/projects/${encodeURIComponent(project)}/workbench`;
const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });
export const researchPageSize = 24;
export const workbenchApi = {
  products: (project: string, query: string, kind: ResearchProduct['kind'] | 'all', object: ChemicalObject | null, offset: number) => {
    const params = new URLSearchParams({query, offset: String(offset), limit: String(researchPageSize)});
    if (kind !== 'all') params.set('kind', kind);
    if (object) { params.set('object_kind', object.kind); params.set('object_id', object.id); }
    return request<{products: ResearchProduct[]; objects: (ChemicalObject & {label:string})[]; total: number; offset: number}>(
      `${base(project)}/products?${params}`);
  },
  preview: (project: string, source: WorkbenchSource) => request<GeometryPreview>(`${base(project)}/preview`, post(source)),
  open: (project: string, source: WorkbenchSource) => request<DocumentView>(`${base(project)}/open`, post(source)),
  frame: (project: string, document: string, index: number) => request<GeometryView>(`${base(project)}/documents/${encodeURIComponent(document)}/frames/${index}`),
  csv: (project: string, document: string) => requestText(`${base(project)}/documents/${encodeURIComponent(document)}/csv`),
  edit: (project: string, edit: EditRequest) => request<GeometryView>(`${base(project)}/edit`, post(edit)),
  snapshot: (project: string, body: SnapshotRequest & {camera:number[]}) =>
    request<{structure_path:string; annotations_path:string; markers: {label:string; kind:'atoms'|'site'; atoms:{element:string;index:number;image:number[]}[]; xyz_angstrom?:number[]}[]}>
      (`${base(project)}/snapshots`, post(body)),
  fragments: (project: string) => request<{ fragments: FragmentEntry[] }>(`${base(project)}/fragments`),
  previewFragment: (project: string, smiles: string, name = '') => request<GeometryView>(`${base(project)}/fragments/preview`, post({ smiles, name })),
  useFragment: (project: string, smiles: string, name = '') => request<FragmentEntry>(`${base(project)}/fragments`, post({ smiles, name })),
  deleteFragment: (project: string, id: string) => request<unknown>(`${base(project)}/fragments/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  save: (project: string, body: SaveRequest) => request<SaveResult>(`${base(project)}/save`, post(body)),
};
