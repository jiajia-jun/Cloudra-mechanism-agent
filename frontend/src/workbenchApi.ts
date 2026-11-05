import { request, requestText } from './api';
import type { DocumentView, EditRequest, FragmentEntry, GeometryView, GeometryPreview, SaveRequest, SaveResult, WorkbenchSource } from './workbenchTypes';
export type * from './workbenchTypes';
const base = (project: string) => `/api/v2/projects/${encodeURIComponent(project)}/workbench`;
const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });
export const workbenchApi = {
  products: (project: string) => request<{products: import('./researchProducts').ResearchProduct[]; objects: (import('./researchProducts').ChemicalObject & {label:string})[]}>(`${base(project)}/products`),
  preview: (project: string, source: WorkbenchSource) => request<GeometryPreview>(`${base(project)}/preview`, post(source)),
  open: (project: string, source: WorkbenchSource) => request<DocumentView>(`${base(project)}/open`, post(source)),
  frame: (project: string, document: string, index: number) => request<GeometryView>(`${base(project)}/documents/${encodeURIComponent(document)}/frames/${index}`),
  csv: (project: string, document: string) => requestText(`${base(project)}/documents/${encodeURIComponent(document)}/csv`),
  edit: (project: string, edit: EditRequest) => request<GeometryView>(`${base(project)}/edit`, post(edit)),
  fragments: (project: string) => request<{ fragments: FragmentEntry[] }>(`${base(project)}/fragments`),
  previewFragment: (project: string, smiles: string, name = '') => request<GeometryView>(`${base(project)}/fragments/preview`, post({ smiles, name })),
  useFragment: (project: string, smiles: string, name = '') => request<FragmentEntry>(`${base(project)}/fragments`, post({ smiles, name })),
  deleteFragment: (project: string, id: string) => request<unknown>(`${base(project)}/fragments/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  save: (project: string, body: SaveRequest) => request<SaveResult>(`${base(project)}/save`, post(body)),
};
