# ts_resume

Revise input groups on the existing TS path. Omitted calculation fields retain settings; explicit empty values clear them. Engine, method or basis changes use {replace: complete_configuration}; profile-reference changes use {replace: {ref: name}}. Proven atom reorderings are handled internally; source files remain unchanged and new incoming atom declarations convert once. Omitted conformer fields retain current state; null clears them. Future calls use the returned current atom order with each field's documented index base. Historical QM artifacts retain their original order. Declare the intended change and its reason; the runtime manages concurrency and replay identity. Revise a failed or no-peak search with new scientific inputs, or retry with changes={}; previous attempts remain recorded automatically. Queued jobs allow revisions; superseded queued jobs are withdrawn. Running jobs prevent revisions. Use ts_inspect for reads.

## Input and result contract

```typescript
interface ToolResponse<T> {
  call_id: string;
  is_success: boolean;
  summary: string;
  data: T;
  duration_ms: number;
}

type TsResumeArgs_CalculationRef = {
  "ref": string;
};

type TsResumeArgs_CalculationReplacement = {
  "replace": TsResumeArgs_QmCalculation | TsResumeArgs_CalculationRef;
};

type TsResumeArgs_ConformerGuidanceChanges = {
  /** Ordered ring atoms in the bound reactant's full coordinate order, 1-based. (default=null) */
  "ring_order"?: Array<number> | null;
  /** Distance windows whose atom pairs use the bound reactant's full coordinate order, 1-based, including explicit hydrogen rows. (default=null) */
  "distance_filters"?: Array<TsResumeArgs_DistanceWindowInput> | null;
};

type TsResumeArgs_ConformerSourceChanges = {
  /** default=null */
  "kind"?: "generate" | "file" | "catalog" | "rotate_about_bond" | null;
  /** default=null */
  "generation"?: "ETKDGv3" | null;
  /** default=null */
  "seed"?: number | null;
  /** Optional additional build-stage pre-optimization. Omit or set null to use the supplied file geometry as-is. This does not certify a minimum or replace later TS/IRC and endpoint verification. With ts_resume, patch optimization to null to clear a previous request; omitted source fields retain their values. (default=null) */
  "optimization"?: TsResumeArgs_QmCalculationChanges | TsResumeArgs_CalculationReplacement | null;
  /** default=null */
  "xyz_path"?: string | null;
  /** default=null */
  "mol_path"?: string | null;
  /** default=null */
  "evidence_refs"?: Array<string> | null;
  /** default=null */
  "catalog_id"?: string | null;
  /** default=null */
  "candidate_id"?: string | null;
  /** Bond-axis atom pair in the bound conformer's full coordinate order, 1-based; do not use SMILES heavy-atom indices. (default=null) */
  "atoms"?: [number, number] | null;
  /** default=null */
  "degrees"?: number | null;
};

type TsResumeArgs_DistanceWindowInput = {
  "atoms": Array<number>;
  /** min> 0 */
  "min_ang": number;
  /** min> 0 */
  "max_ang": number;
};

type TsResumeArgs_EndpointSeedChanges = {
  /** default=null */
  "kind"?: "file" | null;
  /** XYZ in the bound endpoint species atom order. The program applies the existing reaction atom map; accepted native IRC endpoint files already use TS working order. (default=null) */
  "xyz_path"?: string | null;
  /** MOL defining the XYZ atom order. Use the existing bound species MOL; a MOL already in TS working order is also recognized. (default=null) */
  "mol_path"?: string | null;
  /** default=null */
  "evidence_refs"?: Array<string> | null;
};

type TsResumeArgs_EndpointVerificationChanges = {
  /** default=null */
  "seed"?: TsResumeArgs_EndpointSeedChanges | null;
  /** default=null */
  "optimization"?: TsResumeArgs_QmCalculationChanges | TsResumeArgs_CalculationReplacement | null;
  /** default=null */
  "frequency"?: TsResumeArgs_QmCalculationChanges | TsResumeArgs_CalculationReplacement | null;
};

type TsResumeArgs_FrozenCoordinateInput = {
  "coord_type": "bond" | "angle" | "dihedral";
  "atoms": Array<number>;
};

type TsResumeArgs_PathSolvation = {
  "model": "alpb" | "gbsa";
  "solvent": string;
};

type TsResumeArgs_ProductEndpointVerificationChanges = {
  /** default=null */
  "seed"?: TsResumeArgs_EndpointSeedChanges | null;
  /** default=null */
  "optimization"?: TsResumeArgs_QmCalculationChanges | TsResumeArgs_CalculationReplacement | null;
  /** default=null */
  "frequency"?: TsResumeArgs_QmCalculationChanges | TsResumeArgs_CalculationReplacement | null;
  /** Native frequency logs for the independently optimized separated products. The program snapshots the files and matches each real geometry to its declared component; every component must have zero imaginary frequencies. This does not verify a bound complex minimum. (default=null) */
  "component_logs"?: Array<string> | null;
};

type TsResumeArgs_ProvidedGuess = {
  "kind": "provided";
  /** Candidate XYZ in the current bound reactant's full atom order. Coordinates and element labels must refer to the same source atoms; do not combine product-order coordinates with reactant-order labels. */
  "xyz_path": string;
  "evidence_refs": Array<string>;
};

type TsResumeArgs_QmCalculation = {
  "engine": "orca" | "gaussian" | "xtb";
  /** One native method token, e.g. B3LYP, B97-3c, HF or GFN2-xTB. Put the basis only in basis_set and additional native settings only in keywords; do not supply a route string. */
  "method": string;
  /** Explicit basis token, e.g. def2-SVP for ORCA, def2SVP for Gaussian, or 6-31G(d). Gaussian rendering also accepts the hyphenated aliases def2-SVP, def2-TZVP, def2-TZVPP, def2-QZVP and def2-QZVPP. Other names keep their native spelling. Use an explicit empty string for a method with no basis; no method or basis is chosen automatically. */
  "basis_set": string;
  /** Additional native electronic settings, including explicitly requested dispersion, SCF and solvent settings. Declare the orbital basis only in basis_set; auxiliary fitting bases such as def2/J remain in keywords. This string replaces the previous string when patched; omission in a revision preserves it. (default="") */
  "keywords"?: string;
  /** default="auto" */
  "frequency_mode"?: "auto" | "analytic" | "numeric";
  /** Explicit ORCA native blocks. Omission in a revision preserves them; explicit null clears them. (default=null) */
  "orca_blocks"?: string | null;
  /** Explicit Gaussian trailing native settings. Omission in a revision preserves them; an explicit empty string clears them. (default="") */
  "end_setting"?: string;
};

type TsResumeArgs_QmCalculationChanges = {
  /** default=null */
  "engine"?: "orca" | "gaussian" | "xtb" | null;
  /** One native method token, e.g. B3LYP, B97-3c, HF or GFN2-xTB. Put the basis only in basis_set and additional native settings only in keywords; do not supply a route string. (default=null) */
  "method"?: string | null;
  /** Explicit basis token, e.g. def2-SVP for ORCA, def2SVP for Gaussian, or 6-31G(d). Gaussian rendering also accepts the hyphenated aliases def2-SVP, def2-TZVP, def2-TZVPP, def2-QZVP and def2-QZVPP. Other names keep their native spelling. Use an explicit empty string for a method with no basis; no method or basis is chosen automatically. (default=null) */
  "basis_set"?: string | null;
  /** Additional native electronic settings, including explicitly requested dispersion, SCF and solvent settings. Declare the orbital basis only in basis_set; auxiliary fitting bases such as def2/J remain in keywords. This string replaces the previous string when patched; omission in a revision preserves it. (default=null) */
  "keywords"?: string | null;
  /** default=null */
  "frequency_mode"?: "auto" | "analytic" | "numeric" | null;
  /** Explicit ORCA native blocks. Omission in a revision preserves them; explicit null clears them. (default=null) */
  "orca_blocks"?: string | null;
  /** Explicit Gaussian trailing native settings. Omission in a revision preserves them; an explicit empty string clears them. (default=null) */
  "end_setting"?: string | null;
};

type TsResumeArgs_ScanCoordinateInput = {
  /** default="bond" */
  "coord_type"?: "bond" | "angle" | "dihedral";
  "atoms": Array<number>;
  /** default=null */
  "scan_start"?: number | null;
  "scan_end": number;
  /** min 1 */
  "scan_steps": number;
};

type TsResumeArgs_ScanGuessChanges = {
  /** default=null */
  "kind"?: "scan" | null;
  /** default=null */
  "calculation"?: TsResumeArgs_QmCalculationChanges | TsResumeArgs_CalculationReplacement | null;
  /** Coordinates in the concrete scan-input atom order. ORCA references are 0-based; Gaussian/xTB references are 1-based. Convert concrete coordinate indices, not SMILES positions. (default=null) */
  "scans"?: Array<TsResumeArgs_ScanCoordinateInput> | null;
  /** Frozen coordinates in the same concrete input atom order and engine-specific numbering as scans. (default=null) */
  "freeze"?: Array<TsResumeArgs_FrozenCoordinateInput> | null;
  /** xTB restraint force constant in atomic units; explicitly declared (default=null) */
  "force_constant"?: number | null;
  /** Two ORCA coordinates require grid (independent surface) or concerted (simultaneous path, equal steps). xTB supports concerted/sequential. Omit for one coordinate or Gaussian grids. (default=null) */
  "mode"?: "concerted" | "sequential" | "grid" | null;
  /** default=null */
  "solvation"?: TsResumeArgs_PathSolvation | null;
};

type TsResumeArgs_TsConformersChanges = {
  /** default=null */
  "reactant"?: TsResumeArgs_ConformerSourceChanges | null;
  /** default=null */
  "product"?: TsResumeArgs_ConformerSourceChanges | null;
  /** default=null */
  "guidance"?: TsResumeArgs_ConformerGuidanceChanges | null;
};

type TsResumeArgs_TsExecutionChanges = {
  /** default=null */
  "cpus"?: number | null;
  /** default=null */
  "memory_mb"?: number | null;
  /** default=null */
  "limits"?: TsResumeArgs_TsExecutionLimitsChanges | null;
};

type TsResumeArgs_TsExecutionLimitsChanges = {
  /** default=null */
  "source"?: string | null;
  /** default=null */
  "max_compute_actions"?: number | null;
  /** default=null */
  "max_model_calls"?: number | null;
};

type TsResumeArgs_TsInputChanges = {
  /** default=null */
  "reaction"?: TsResumeArgs_TsReactionChanges | null;
  /** Complete local named calculations. Stages explicitly select a ref; nothing inherits an exploration or formal method automatically. (default=null) */
  "calculations"?: {
  [key: string]: TsResumeArgs_QmCalculationChanges | TsResumeArgs_CalculationReplacement | null;
} | null;
  /** default=null */
  "conformers"?: TsResumeArgs_TsConformersChanges | null;
  /** default=null */
  "guess"?: TsResumeArgs_ScanGuessChanges | TsResumeArgs_XtbPathGuess | TsResumeArgs_ProvidedGuess | null;
  /** default=null */
  "ts_optimization"?: TsResumeArgs_QmCalculationChanges | TsResumeArgs_CalculationReplacement | null;
  /** default=null */
  "verification"?: TsResumeArgs_TsVerificationChanges | null;
  /** default=null */
  "execution"?: TsResumeArgs_TsExecutionChanges | null;
};

type TsResumeArgs_TsReactionChanges = {
  /** default=null */
  "reactant_smiles"?: string | null;
  /** A dot-joined SMILES declares a bound complex; a list declares separated products, displayed with +. (default=null) */
  "product_smiles"?: string | Array<string> | null;
  /** default=null */
  "charge"?: number | null;
  /** default=null */
  "multiplicity"?: number | null;
  /** Optional declared electronic character, including open-shell singlets. This describes the requested seed state; it does not choose a ground state, wavefunction method or spin initialization. (default=null) */
  "electronic_character"?: "closed_shell" | "open_shell" | null;
  /** Choose an inspected complete concrete mapping candidate by its 0-based index only when correspondence is ambiguous. A unique complete mapping is adopted automatically; omitted/null never silently selects candidate 0. (default=null) */
  "selected_candidate"?: number | null;
  /** Forming/breaking atom pairs in the bound reactant's full coordinate order, 1-based and including explicit hydrogens. Use reaction_mapping.concrete_watch_pairs for the same concrete structure. (default=null) */
  "reaction_center"?: Array<[number, number]> | null;
};

type TsResumeArgs_TsVerificationChanges = {
  /** default=null */
  "frequency"?: TsResumeArgs_QmCalculationChanges | TsResumeArgs_CalculationReplacement | null;
  /** default=null */
  "irc"?: TsResumeArgs_QmCalculationChanges | TsResumeArgs_CalculationReplacement | null;
  /** default=null */
  "irc_log"?: string | null;
  /** The declared reaction.reactant_smiles species, never a fixed IRC A/B direction. An explicit seed uses this species atom order; default IRC sources are provisional until optimization, frequency and direction checks pass. (default=null) */
  "reactant_endpoint"?: TsResumeArgs_EndpointVerificationChanges | null;
  /** The declared reaction.product_smiles species, never a fixed IRC A/B direction. An explicit seed uses this species atom order (or an accepted native IRC working order); the runtime applies the bound atom map. (default=null) */
  "product_endpoint"?: TsResumeArgs_ProductEndpointVerificationChanges | null;
};

type TsResumeArgs_XtbPathGuess = {
  "kind": "xtb_path";
  "method": string;
  /** default=null */
  "solvation"?: TsResumeArgs_PathSolvation | null;
  /** xTB path refinement cap; omitted/null uses the runner default of 100. This is a compute limit, not a convergence criterion. (default=null) */
  "refinement_runs"?: number | null;
};

type TsResumeArgs = {
  "run_id": string;
  /** Within the same calculation, omitted fields retain existing keywords, frequency_mode, orca_blocks and end_setting; explicit empty values clear them. Changing engine, method or basis_set requires {replace: complete_configuration}; changing a named reference uses {replace: {ref: name}}. calculations profile-map omissions remain unchanged, and null removes an unused profile. A scan-coordinate-only patch need not copy calculation. Use the current atom identities/order reported in structures with each field's documented index base: structure/reaction references are 1-based; ORCA scan/freeze references are 0-based; Gaussian/xTB scan references are 1-based. A source patch retains omitted fields and null clears them. Explicit file paths import the current file bytes once, including an unchanged path. Proven incoming atom reorderings convert new atom declarations once within owned molecular state; source files remain unchanged. */
  "changes"?: TsResumeArgs_TsInputChanges;
  "reason": string;
};

type TsResumeData_TsEvidenceReference = {
  /** min 1 */
  "declaration_revision": number;
  "stage_key": string;
  /** min 1 */
  "attempt": number;
  /** default=null */
  "job_id"?: number | null;
};

type TsResumeData_TsRevisionReceipt = {
  "request_key": string;
  "request_digest": string;
  "reason": string;
  /** min 0 */
  "previous_revision": number;
  /** min 1 */
  "revision": number;
  /** min 1 */
  "previous_input_revision": number;
  /** min 2 */
  "input_revision": number;
  "changes": Array<string>;
  "retained": Array<TsResumeData_TsEvidenceReference>;
  "invalidated": Array<TsResumeData_TsEvidenceReference>;
  "released_action_keys"?: Array<string>;
  "source_hashes"?: {
  [key: string]: {
  [key: string]: string;
};
};
  /** default="accepted" */
  "status"?: "accepted";
};

type TsResumeData_TsVerdict = {
  "outcome": "verified" | "candidate_only" | "search_failed" | "invalid_input";
  "verified": boolean;
  "reason": string;
  "evidence_refs": Array<string>;
};

type TsResumeData = {
  /** default="" */
  "run_id"?: string;
  /** default=0 */
  "revision"?: number;
  /** default="" */
  "run_dir"?: string;
  /** default=null */
  "status"?: "running" | "waiting" | "blocked" | "ended" | "stopped" | "isolated" | null;
  /** default="" */
  "stage"?: string;
  /** Scientific verdict: outcome, verified, recorded reason and evidence references. Tool-call success and an ended workflow do not imply scientific verification. (default=null) */
  "result"?: TsResumeData_TsVerdict | null;
  "waiting_for"?: Array<{
  [key: string]: unknown;
}>;
  /** Recorded artifacts retain their original input atom order. input_revision_relation identifies current, historical or unknown source revisions; historical QM artifacts are unchanged. */
  "available_results"?: Array<{
  [key: string]: unknown;
}>;
  /** Read-only atom tables derived from the owned molecular state, with 1-based structure numbers. Source files are never overwritten. Engine-specific scan numbering is converted at the execution boundary. */
  "structures"?: {
  [key: string]: {
  [key: string]: unknown;
};
};
  /** default=null */
  "blocked"?: {
  [key: string]: unknown;
} | null;
  /** default=null */
  "failed_attempt"?: {
  [key: string]: unknown;
} | null;
  /** Recorded TS imaginary-mode composition, source job/revision and log digest. Atoms and reaction_center_pairs are 1-based in the frequency input's atom order. Atom fractions use unweighted squared displacements, not mass weighting or a pass/fail cutoff; modes=null means mode vectors or geometry were unavailable. mode_alignment reuses the ts_guess diagnostic: misaligned/undecidable notifies the owner for a decision without blocking IRC or cancelling jobs. This report does not establish that the motion belongs to the declared reaction. (default=null) */
  "frequency_analysis"?: {
  [key: string]: unknown;
} | null;
  "next"?: {
  [key: string]: unknown;
};
  /** Per-stage resolved planned configurations, immutable actual job snapshots and native input contracts, including a separately recorded scan. A reference identifies the selected local profile; planned_error reports an invalid current declaration without hiding historical actual inputs. Isolated older formats retain their raw recorded fields. */
  "methods"?: Array<{
  [key: string]: unknown;
}>;
  "usage"?: {
  [key: string]: unknown;
};
  /** JSON export path only when its revision and current structure files were verified. Empty for absent or stale exports, or unavailable current structures; this returned view at revision is authoritative. (default="") */
  "details_path"?: string;
  /** Revision of the JSON export, or null if absent. When this differs from revision, exported atom tables are historical; use this returned current view. (default=null) */
  "export_revision"?: number | null;
  /** default="" */
  "message"?: string;
  /** Tool call succeeded; this is not scientific validation. Only result.verified=true means the TS passed the recorded scientific checks. (default=true) */
  "is_success"?: boolean;
  /** Durable accepted revision receipt. Imported source hashes identify immutable snapshots. Future references use the current atom table with each field's documented index base. Historical QM files retain their original numbering. (default=null) */
  "receipt"?: TsResumeData_TsRevisionReceipt | null;
};

declare const tools: {
  /** Revise input groups on the existing TS path. Omitted calculation fields retain settings; explicit empty values clear them. Engine, method or basis changes use {replace: complete_configuration}; profile-reference changes use {replace: {ref: name}}. Proven atom reorderings are handled internally; source files remain unchanged and new incoming atom declarations convert once. Omitted conformer fields retain current state; null clears them. Future calls use the returned current atom order with each field's documented index base. Historical QM artifacts retain their original order. Declare the intended change and its reason; the runtime manages concurrency and replay identity. Revise a failed or no-peak search with new scientific inputs, or retry with changes={}; previous attempts remain recorded automatically. Queued jobs allow revisions; superseded queued jobs are withdrawn. Running jobs prevent revisions. Use ts_inspect for reads. */
  ts_resume(args: TsResumeArgs): Promise<ToolResponse<TsResumeData>>;
};

declare function text(value: unknown): void;
```

## Calling pattern

Construct args from the contract and the actual task declarations. This pattern does not supply scientific methods or other task inputs.

```javascript
const r = await tools.ts_resume(args);
if (r.is_success) text(r.data); else text(r.summary);
```