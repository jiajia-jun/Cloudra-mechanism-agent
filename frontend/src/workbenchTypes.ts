import type { Cell } from './workbenchAnnotations';
export type WorkbenchInputFormat = 'smiles'|'xyz'|'mol'|'sdf'|'log'|'out'|'gjf'|'com'|'inp'|'pdb'|'cif'|'extxyz'|'poscar';
export interface WorkbenchSource { frame_index?: number; path?: string; artifact_id?: string; file_evidence?: {ref_type: 'file'; ref_id: string; content_hash?: string | null; revision?: number | null}; input_text?: string; input_format?: string; input_name?: string; smiles?: string }
export interface WorkbenchAtom {
  index: number; symbol: string; x: number; y: number; z: number; atom_id?: string;
  formal_charge?: number; target_valence?: number | null; bond_valence?: number;
  hybridization?: 'sp' | 'sp2' | 'sp3' | null;
  hybridization_override?: 'sp' | 'sp2' | 'sp3' | null;
  lone_pairs?: number | null;
}
export interface GeometryView {
  cell?: Cell; pbc?: [boolean, boolean, boolean]; extxyz?: string;
  molecule: string; xyz: string; atoms: WorkbenchAtom[];
  bonds: { atom1: number; atom2: number; order: number }[];
  graph_status?: string;
  total_charge?: number;
  preoptimization_blocker?: string | null;
  manual_bonds?: boolean;
  warnings?: string[];
  optimization?: { force_field: 'MMFF94' | 'UFF'; converged: boolean; initial_energy: number; final_energy: number; energy_unit: 'kcal/mol' };
  changes?: { deleted_atom_ids: string[]; deleted_atoms: number[]; index_map: Record<string, number>; moved_atoms: number[]; fragment_smiles?: string };
}
export interface FrameSummary { has_geometry?: boolean; index: number; step: number; energy_hartree?: number | null; rms_force?: number | null; max_force?: number | null; force_unit?: string | null; reaction_coordinate?: number | null; scan_coordinates?: number[]; path_number?: number | null; converged?: boolean | null }
export interface GeometryPreview extends Omit<GeometryView,'molecule'> { title?: string; task_type?: string; engine?: string; frame_count?: number; mode_count?: number; selected_frame_facts?: FrameSummary }
export interface WorkbenchMode { frequency_cm: number; displacements: number[][]; reference_frame?: number | null }
export interface WorkbenchSettings {
  engine?: 'gaussian' | 'orca'; method?: string; basis_set?: string; keywords?: string; charge?: number | null; multiplicity?: number | null; nproc?: number; mem?: string;
  task_type?: Record<string, unknown>[]; [key: string]: unknown;
}
export type CoordinateType = 'bond' | 'angle' | 'dihedral';
export interface FrozenCoordinate { coord_type: CoordinateType; atoms: number[]; value: number }
export interface ScanCoordinate { coord_type: CoordinateType; atoms: number[]; scan_start: number; scan_end: number; scan_steps: number }
export interface DocumentView {
  saved_with_input?: boolean;
  document_id: string; title: string; source_path?: string | null; task_type?: string; frames: FrameSummary[]; selected_frame: number;
  geometry: GeometryView | null; modes: WorkbenchMode[]; modes_reference_geometry?: GeometryView | null;
  settings: WorkbenchSettings; warnings: string[]; frozen_coordinates?: FrozenCoordinate[]; scan_coordinates?: ScanCoordinate[];
}
export interface Draft { atomMappingChanged?: boolean; geometry: GeometryView; settings: WorkbenchSettings; sourcePath?: string | null; sourceFrame?: number; frozen: FrozenCoordinate[]; scans: ScanCoordinate[] }
export interface EditRequest {
  molecule?: string;
  action: 'coordinate' | 'mirror' | 'bond' | 'replace_group' | 'resolve_bonds' | 'add_atom' | 'add_group' | 'delete_atom' | 'atom_state' | 'fill_valence' | 'preoptimize';
  atoms?: number[]; value?: number; fixed_side?: 'first' | 'last'; moving_atoms?: number[];
  plane?: 'xy' | 'xz' | 'yz'; order?: number; smiles?: string; attachment_atom?: number;
  position?: [number, number, number];
  element?: string; formal_charge?: number; valence?: number | null; charge?: number;
  hybridization?: 'sp' | 'sp2' | 'sp3' | null;
  force_field?: 'MMFF94' | 'UFF';
}
export interface FragmentEntry { id: string; smiles: string; name: string; use_count: number; project_use_count: number; attachment_atom?: number; geometry?: GeometryView }
export interface SaveRequest { title: string; molecule: string; source_path?: string | null; source_frame?: number; settings: WorkbenchSettings; frozen_coordinates: FrozenCoordinate[]; scan_coordinates: ScanCoordinate[]; generate_input: boolean }
export interface SaveResult { path: string; files: string[] | Record<string, string>; geometry: GeometryView; message: string }

export interface SnapshotRequest {
  title: string;
  molecule?: string;
  extxyz?: string;
  source_path?: string | null;
  source_frame?: number;
  view: 'source' | 'draft';
  warnings?: string[];
  markers: import('./workbenchAnnotations').Marker[];
  settings: WorkbenchSettings;
  frozen_coordinates: FrozenCoordinate[];
  scan_coordinates: ScanCoordinate[];
}
export interface WorkbenchShot {
  text: string;
  snapshot: SnapshotRequest;
  capture: Promise<{image: Blob; camera: number[]}>;
}
