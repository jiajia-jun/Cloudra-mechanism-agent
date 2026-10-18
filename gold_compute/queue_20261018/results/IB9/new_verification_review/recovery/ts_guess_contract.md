# ts_guess

Transition-state (TS) guess workflow: choose an explicit mode. Use run_id to revise the guess intent of an existing TS run through its durable queue. The run owns endpoint structures, atom correspondence, charge, multiplicity, electronic character and compute resources. Independent geometry analysis accepts complete endpoint MOL/SDF graphs and proves their mapping internally; xtb_path: execute an independent xTB metadynamics path search between confirmed all-atom endpoints; interpolate: linear or IDPP interpolation from reactant/product xyz to generate NEB candidate-path images (confirmed automatic atom correspondence, alignment, distance monitoring and a candidate frame); scan_prepare: write a Gaussian/ORCA constrained-scan input or a typed native xTB scan manifest (bond/angle/dihedral; xTB requires an explicit method and force_constant); for MLIP/external potentials pass method='ExtOpt' (ORCA, plus orca_blocks with the %method ProgExt block) or method='external' (Gaussian, plus keywords='external="mace"'); scan_parse: inspect a one-dimensional or explicitly concerted native scan path and report internal local-peak candidates. A unique peak yields a TS-guess xyz; multiple peaks list point numbers, energies and exact XYZ paths in verdicts for a provided-guess choice. ORCA uses relaxscanact.dat plus matching ts_scan.NNN.xyz frames; independent multidimensional grids are not flattened into paths. without the sidecar the log text is grouped per 'RELAXED SURFACE SCAN STEP' and each point's converged (last) energy/geometry is used, so per-cycle energies are never misread as scan points; verify: by default, frequency plus rough IRC-endpoint connectivity yields candidate/unlikely/inconclusive; with strict=True, requires one reaction-relevant imaginary frequency, bidirectional IRC from that same TS, expected endpoint structures, and native reactant_logs/product_logs proving that the actual IRC outer frames were optimized to the correct zero-imaginary minima, yielding pass/fail/inconclusive. Opt and Freq may be in combined or separate logs; geometric interval checks are advisory only. For an exploratory scan: scan_prepare (after internal_coordinates) → submit → scan_parse. For formal TS refinement and validation, provide the candidate to ts_prepare rather than submitting manual TS/IRC jobs; xtb_path/interpolate are fallbacks and never a saddle. Independent xtb_path executes a calculation directly; run-based operations always use the existing TS revision and queue; scan_prepare writes an input to submit with submit_compute_job, while interpolate/scan_parse/verify generate or inspect artifacts. Coordinates never enter context; only numeric tables, verdicts, and file paths are returned.

## Input and result contract

```typescript
interface ToolResponse<T> {
  call_id: string;
  is_success: boolean;
  summary: string;
  data: T;
  duration_ms: number;
}

type TsGuessArgs_FrozenCoordinateInput = {
  "coord_type": "bond" | "angle" | "dihedral";
  "atoms": Array<number>;
};

type TsGuessArgs_PathSolvation = {
  "model": "alpb" | "gbsa";
  "solvent": string;
};

type TsGuessArgs_ScanCoordinateInput = {
  /** default="bond" */
  "coord_type"?: "bond" | "angle" | "dihedral";
  "atoms": Array<number>;
  /** default=null */
  "scan_start"?: number | null;
  "scan_end": number;
  /** min 1 */
  "scan_steps": number;
};

type TsGuessArgs = ({
  /** Total molecular charge. MOL/SMILES may inherit the graph's formal charge; an explicit declaration must agree with that graph. XYZ calculations require an explicit charge, including 0 for a neutral system. (default=null) */
  "charge"?: number | null;
  /** Spin multiplicity (2S+1): singlet=1, doublet=2, triplet=3. (default=1; min 1) */
  "multiplicity"?: number;
  /** Declared electronic character, including open-shell singlets. Open-shell SMILES skip closed-shell force fields. This does not select a QM method or initialize spin. (default=null) */
  "electronic_character"?: "closed_shell" | "open_shell" | null;
  /** Number of CPU cores for parallel compute (Gaussian %nproc / ORCA %pal). (default=4; min 1) */
  "nproc"?: number;
  /** Gaussian/ORCA total job memory, e.g. '4GB' or '8192MB'. Gaussian writes %mem; ORCA writes %maxcore = mem/nproc. Request the same total memory_mb when submitting. (default="4GB") */
  "mem"?: string;
  /** Required sub-function; no calculation path is selected when mode is omitted. DEFAULT SEED PATH when one forming/breaking bond/angle is known: scan_prepare → submit → scan_parse (relaxed scan), then provide the peak to ts_prepare for formal TS refinement. Do NOT default to xtb_path/interpolate just because they are cheap. xtb_path: xTB metadynamics path search between endpoints (needs `xtb`); falls back to interpolate with path_kind='idpp_fallback' when xtb is absent (never silently). interpolate: IDPP/linear images — only when both endpoints and the all-atom map are already trustworthy; it is not the default TS-seed start. scan_prepare (write a scan input; atom indices should come from internal_coordinates first), scan_parse (parse a scan log and judge), verify (frequency+IRC verification). Alias: 'scan' maps to 'scan_prepare' (or 'scan_parse' if log_path is given). NOTE: xtb_path/interpolate return a PATH AND A GUESS, never a saddle point — unconstrained OptTS + frequency + IRC are still required. The former 'xtb_neb' alias is gone: xTB has no NEB. */
  "mode": "xtb_path" | "interpolate" | "scan_prepare" | "scan_parse" | "verify" | "scan" | "provided";
  /** Existing TS run in the current project and workspace. Mutually exclusive with endpoint files/text, charge/multiplicity/electronic_character and output/resource overrides. Guess changes use the existing revision transaction and automatic queue. (default=null) */
  "run_id"?: string | null;
  /** Independent endpoint analysis: choose a reported complete concrete atom-correspondence candidate (0-based). Omit when mapping is unique; genuine ambiguity requires an explicit choice. (default=null) */
  "selected_candidate"?: number | null;
  /** provided with run_id: source evidence for the supplied TS candidate. */
  "evidence_refs"?: Array<string>;
  /** Independent path/interpolation: complete reactant MOL/SDF graph; verify also accepts XYZ reference geometry. Declared graphs are retained. Absolute as-is, or relative to the Agent working directory. (default=null) */
  "reactant_path"?: string | null;
  /** Reactant XYZ/MOL/SDF text; strict verify uses it to identify the expected reactant. Path takes precedence. (default=null) */
  "reactant_text"?: string | null;
  /** Independent path/interpolation: complete product MOL/SDF graph; verify also accepts XYZ reference geometry. Declared graphs are retained. Absolute as-is, or relative to the Agent working directory. (default=null) */
  "product_path"?: string | null;
  /** Product XYZ/MOL/SDF text; strict verify uses it to identify the expected product. Path takes precedence. (default=null) */
  "product_text"?: string | null;
  /** interpolate: total image count (including endpoints), ≥2. (default=10) */
  "n_images"?: number;
  /** interpolate: interpolation method. idpp relaxes inter-image pair distances per Smidtstrup 2014; linear is linear interpolation. (default="idpp") */
  "interp_method"?: "idpp" | "linear";
  /** xtb_path/interpolate/scan_parse: pairs for distance monitoring; verify: pairs for direction proof and imaginary-mode alignment. Indices refer to the concrete reactant XYZ for path/interpolation, each scan frame for scan_parse, and the TS frequency geometry for verify, including explicit H. Gaussian/xTB are 1-based; ORCA is 0-based. Use internal_coordinates on that file or reaction_mapping's concrete_watch_pairs with complete, current structure binding; SMILES graph indices and indices from another atom order are not interchangeable. If omitted, distance/direction checks nominate bond-change and largest-distance-change pairs; imaginary-mode alignment is skipped. */
  "watch_pairs"?: Array<Array<number>>;
  /** interpolate: image output directory (default ./ts_interp/); verify: directory to write IRC endpoints (default <freq_log_stem>_verify/). Relative paths resolve against the Agent working directory. (default=null) */
  "output_dir"?: string | null;
  /** xtb_path: subprocess timeout in seconds. On expiry only this run's own process group is terminated; its logs and intermediate files are kept. (default=900) */
  "timeout"?: number;
  /** xtb_path: ceiling on the number of path-refinement cycles handed to xTB ($path nrun). This is a COMPUTE ceiling, not a convergence criterion: the engine stops by itself when its own criterion is met. Do NOT lower it: the engine's built-in default is 3 cycles, which measurably truncates the path (the highest frame then sits in the reactant's own basin, 21 deg from the start, and an OptTS started from it never converges). If a run reports termination='path_not_converged', raise this and rerun. (default=100; min 1) */
  "refinement_runs"?: number;
  /** scan_prepare: input structure file path (XYZ/MOL/SDF). Absolute as-is, or relative to the Agent working directory. (default=null) */
  "input_path"?: string | null;
  /** scan_prepare: input structure XYZ/MOL/SDF text. (default=null) */
  "input_text"?: string | null;
  /** Required explicit engine for scan_prepare. For scan_parse/verify, omit to detect Gaussian/ORCA from the native log; an explicit engine must match the log. For geometry modes this selects atom numbering, not a calculation method. (default=null) */
  "engine"?: "gaussian" | "orca" | "xtb" | null;
  /** scan_prepare: scan-coordinate list, one entry per scanned coordinate. Each entry: {"coord_type": "bond"|"angle"|"dihedral", "atoms": [2|3|4 atom indices], Atoms refer to the exact input_path/input_text XYZ order, including explicit H. Gaussian and xTB use 1-based indices; ORCA uses 0-based indices. internal_coordinates on that same structure is 1-based: subtract 1 only for ORCA. "scan_start": optional start value (default the current geometry value), "scan_end": end value, "scan_steps": step count}. A single entry drives a 1D scan. Two ORCA coordinates require scan_mode='concerted' for a simultaneous path or 'grid' for an independent potential-energy surface. Gaussian uses an independent grid; xTB requires concerted or sequential. scan_parse does not derive a TS candidate from a grid. Scanning only one geometric coordinate is often not enough: TS search frequently needs a second, coupled coordinate (e.g. both the forming and the breaking bond) to see a barrier. (default=null) */
  "scans"?: Array<TsGuessArgs_ScanCoordinateInput> | null;
  /** scan_prepare: coordinates held at the input geometry value; atoms belong to the exact input XYZ order including explicit H. Gaussian/xTB atoms start at 1; ORCA at 0. Do not freeze a scanned coordinate. */
  "freeze"?: Array<TsGuessArgs_FrozenCoordinateInput>;
  /** scan_prepare requires one native method token. Put the basis only in basis_set and additional native settings only in keywords. Use the same calculation fields as qm_input_writer and ts_prepare. Current task requirements govern the method; MethodPolicy applies only to Benchmark tasks. (default=null) */
  "method"?: string | null;
  /** scan_prepare requires an explicit basis token, or an explicit empty string for a method with no basis. A method/basis route string is not accepted in method. (default=null) */
  "basis_set"?: string | null;
  /** scan_prepare: explicitly requested native electronic keywords, e.g. D3BJ RIJCOSX def2/J TightSCF CPCM(DCM) for ORCA, or scrf=(solvent=water) for Gaussian. (default="") */
  "keywords"?: string;
  /** scan_prepare accepts only auto: this operation writes a scan, not a frequency calculation. (default="auto") */
  "frequency_mode"?: "auto" | "analytic" | "numeric";
  /** scan_prepare: path to write the Gaussian/ORCA input or xTB typed manifest (required). Absolute as-is, or relative to the Agent working directory. (default=null) */
  "output_path"?: string | null;
  /** scan_prepare, ORCA only: raw % blocks appended after generated resources/geometry. %geom/%pal/%maxcore use scans/freeze/nproc/mem instead. For example, the external-potential block '%method\n  ProgExt "/abs/path/to/mace"\n  Ext_Params "--model /abs/model --device cpu --dtype float64"\nend' when method='ExtOpt'. Rejected for engine='gaussian'. (default=null) */
  "orca_blocks"?: string | null;
  /** scan_prepare: explicit Gaussian trailing native settings, after ModRedundant coordinates. ORCA uses orca_blocks. (default="") */
  "end_setting"?: string;
  /** Native xTB scan restraint force constant in atomic units; required for engine=xtb. (default=null) */
  "force_constant"?: number | null;
  /** Two-coordinate scan intent: ORCA requires concerted (simultaneous path, equal steps) or grid (independent surface, no automatic TS candidate); xTB supports concerted or sequential. Omit for one coordinate or Gaussian grids. (default=null) */
  "scan_mode"?: "concerted" | "sequential" | "grid" | null;
  /** Native xTB solvation declaration, when used. (default=null) */
  "solvation"?: TsGuessArgs_PathSolvation | null;
  /** scan_parse: Gaussian/ORCA scan log path, or xTB typed manifest path after completion. Absolute as-is, or relative to the Agent working directory. (default=null) */
  "log_path"?: string | null;
  /** scan_parse: path to write the TS-guess xyz (default <log_stem>_ts_guess.xyz). Absolute as-is, or relative to the Agent working directory. (default=null) */
  "ts_candidate_path"?: string | null;
  /** verify: frequency-calculation log path. Absolute as-is, or relative to the Agent working directory. (default=null) */
  "freq_log"?: string | null;
  /** verify: IRC log path; optional in default mode, required in strict mode with valid frames on both rx<0 and rx>0 sides. Absolute as-is, or relative to the Agent working directory. (default=null) */
  "irc_log"?: string | null;
  /** verify strict: native Opt and Freq logs proving an actual IRC outer frame was optimized to the expected reactant zero-imaginary minimum. Combined Opt/Freq or separate logs are accepted. Paths are absolute or relative to the Agent working directory. */
  "reactant_logs"?: Array<string>;
  /** verify strict: native Opt and Freq logs proving the opposite IRC outer frame was optimized to the expected product zero-imaginary minimum. Combined Opt/Freq or separate logs are accepted. Paths are absolute or relative to the Agent working directory. */
  "product_logs"?: Array<string>;
  /** verify only: prove direction using the same TS and bidirectional IRC plus actual outer-frame Opt/Freq logs and expected endpoint structures. IRC itself need not reach minima; the optimized endpoints must have zero imaginary frequencies. Geometric intervals are advisory. (default=false) */
  "strict"?: boolean;
}) & (({
  "mode": "xtb_path";
  "nproc"?: unknown;
  "mem"?: unknown;
  "run_id"?: unknown;
  "evidence_refs"?: unknown;
  "input_path"?: unknown;
  "input_text"?: unknown;
  "scans"?: unknown;
  "freeze"?: unknown;
  "method"?: unknown;
  "basis_set"?: unknown;
  "keywords"?: unknown;
  "frequency_mode"?: unknown;
  "output_path"?: unknown;
  "orca_blocks"?: unknown;
  "end_setting"?: unknown;
  "force_constant"?: unknown;
  "scan_mode"?: unknown;
  "solvation"?: unknown;
  "log_path"?: unknown;
  "ts_candidate_path"?: unknown;
  "freq_log"?: unknown;
  "irc_log"?: unknown;
  "reactant_logs"?: unknown;
  "product_logs"?: unknown;
  "strict"?: unknown;
}) & ({
  "reactant_path": string;
} | {
  "reactant_text": string;
}) & ({
  "product_path": string;
} | {
  "product_text": string;
}) | ({
  "mode": "interpolate";
  "nproc"?: unknown;
  "mem"?: unknown;
  "run_id"?: unknown;
  "evidence_refs"?: unknown;
  "timeout"?: unknown;
  "refinement_runs"?: unknown;
  "input_path"?: unknown;
  "input_text"?: unknown;
  "scans"?: unknown;
  "freeze"?: unknown;
  "method"?: unknown;
  "basis_set"?: unknown;
  "keywords"?: unknown;
  "frequency_mode"?: unknown;
  "output_path"?: unknown;
  "orca_blocks"?: unknown;
  "end_setting"?: unknown;
  "force_constant"?: unknown;
  "scan_mode"?: unknown;
  "solvation"?: unknown;
  "log_path"?: unknown;
  "ts_candidate_path"?: unknown;
  "freq_log"?: unknown;
  "irc_log"?: unknown;
  "reactant_logs"?: unknown;
  "product_logs"?: unknown;
  "strict"?: unknown;
}) & ({
  "reactant_path": string;
} | {
  "reactant_text": string;
}) & ({
  "product_path": string;
} | {
  "product_text": string;
}) | ({
  "mode": "scan_prepare";
  "engine": "gaussian" | "orca" | "xtb";
  "method": string;
  "basis_set": string;
  "scans": Array<TsGuessArgs_ScanCoordinateInput>;
  "output_path": string;
  "run_id"?: unknown;
  "selected_candidate"?: unknown;
  "evidence_refs"?: unknown;
  "reactant_path"?: unknown;
  "reactant_text"?: unknown;
  "product_path"?: unknown;
  "product_text"?: unknown;
  "n_images"?: unknown;
  "interp_method"?: unknown;
  "watch_pairs"?: unknown;
  "output_dir"?: unknown;
  "timeout"?: unknown;
  "refinement_runs"?: unknown;
  "log_path"?: unknown;
  "ts_candidate_path"?: unknown;
  "freq_log"?: unknown;
  "irc_log"?: unknown;
  "reactant_logs"?: unknown;
  "product_logs"?: unknown;
  "strict"?: unknown;
}) & ({
  "input_path": string;
} | {
  "input_text": string;
}) | ({
  "mode": "scan";
  "engine": "gaussian" | "orca" | "xtb";
  "method": string;
  "basis_set": string;
  "scans": Array<TsGuessArgs_ScanCoordinateInput>;
  "output_path": string;
  "log_path"?: "" | null;
  "run_id"?: unknown;
  "selected_candidate"?: unknown;
  "evidence_refs"?: unknown;
  "reactant_path"?: unknown;
  "reactant_text"?: unknown;
  "product_path"?: unknown;
  "product_text"?: unknown;
  "n_images"?: unknown;
  "interp_method"?: unknown;
  "watch_pairs"?: unknown;
  "output_dir"?: unknown;
  "timeout"?: unknown;
  "refinement_runs"?: unknown;
  "ts_candidate_path"?: unknown;
  "freq_log"?: unknown;
  "irc_log"?: unknown;
  "reactant_logs"?: unknown;
  "product_logs"?: unknown;
  "strict"?: unknown;
}) & ({
  "input_path": string;
} | {
  "input_text": string;
}) | {
  "mode": "scan_parse";
  "log_path": string;
  "charge"?: unknown;
  "multiplicity"?: unknown;
  "electronic_character"?: unknown;
  "nproc"?: unknown;
  "mem"?: unknown;
  "run_id"?: unknown;
  "selected_candidate"?: unknown;
  "evidence_refs"?: unknown;
  "reactant_path"?: unknown;
  "reactant_text"?: unknown;
  "product_path"?: unknown;
  "product_text"?: unknown;
  "n_images"?: unknown;
  "interp_method"?: unknown;
  "output_dir"?: unknown;
  "timeout"?: unknown;
  "refinement_runs"?: unknown;
  "input_path"?: unknown;
  "input_text"?: unknown;
  "scans"?: unknown;
  "freeze"?: unknown;
  "method"?: unknown;
  "basis_set"?: unknown;
  "keywords"?: unknown;
  "frequency_mode"?: unknown;
  "output_path"?: unknown;
  "orca_blocks"?: unknown;
  "end_setting"?: unknown;
  "force_constant"?: unknown;
  "scan_mode"?: unknown;
  "solvation"?: unknown;
  "freq_log"?: unknown;
  "irc_log"?: unknown;
  "reactant_logs"?: unknown;
  "product_logs"?: unknown;
  "strict"?: unknown;
} | {
  "mode": "verify";
  "freq_log": string;
  "multiplicity"?: unknown;
  "electronic_character"?: unknown;
  "nproc"?: unknown;
  "mem"?: unknown;
  "run_id"?: unknown;
  "selected_candidate"?: unknown;
  "evidence_refs"?: unknown;
  "n_images"?: unknown;
  "interp_method"?: unknown;
  "timeout"?: unknown;
  "refinement_runs"?: unknown;
  "input_path"?: unknown;
  "input_text"?: unknown;
  "scans"?: unknown;
  "freeze"?: unknown;
  "method"?: unknown;
  "basis_set"?: unknown;
  "keywords"?: unknown;
  "frequency_mode"?: unknown;
  "output_path"?: unknown;
  "orca_blocks"?: unknown;
  "end_setting"?: unknown;
  "force_constant"?: unknown;
  "scan_mode"?: unknown;
  "solvation"?: unknown;
  "log_path"?: unknown;
  "ts_candidate_path"?: unknown;
} | {
  "mode": "scan";
  "log_path": string;
  "charge"?: unknown;
  "multiplicity"?: unknown;
  "electronic_character"?: unknown;
  "nproc"?: unknown;
  "mem"?: unknown;
  "run_id"?: unknown;
  "selected_candidate"?: unknown;
  "evidence_refs"?: unknown;
  "reactant_path"?: unknown;
  "reactant_text"?: unknown;
  "product_path"?: unknown;
  "product_text"?: unknown;
  "n_images"?: unknown;
  "interp_method"?: unknown;
  "output_dir"?: unknown;
  "timeout"?: unknown;
  "refinement_runs"?: unknown;
  "input_path"?: unknown;
  "input_text"?: unknown;
  "scans"?: unknown;
  "freeze"?: unknown;
  "method"?: unknown;
  "basis_set"?: unknown;
  "keywords"?: unknown;
  "frequency_mode"?: unknown;
  "output_path"?: unknown;
  "orca_blocks"?: unknown;
  "end_setting"?: unknown;
  "force_constant"?: unknown;
  "scan_mode"?: unknown;
  "solvation"?: unknown;
  "freq_log"?: unknown;
  "irc_log"?: unknown;
  "reactant_logs"?: unknown;
  "product_logs"?: unknown;
  "strict"?: unknown;
} | {
  "mode": "xtb_path";
  "run_id": string;
  "charge"?: unknown;
  "multiplicity"?: unknown;
  "electronic_character"?: unknown;
  "nproc"?: unknown;
  "mem"?: unknown;
  "selected_candidate"?: unknown;
  "evidence_refs"?: unknown;
  "reactant_path"?: unknown;
  "reactant_text"?: unknown;
  "product_path"?: unknown;
  "product_text"?: unknown;
  "n_images"?: unknown;
  "interp_method"?: unknown;
  "watch_pairs"?: unknown;
  "output_dir"?: unknown;
  "timeout"?: unknown;
  "input_path"?: unknown;
  "input_text"?: unknown;
  "engine"?: unknown;
  "scans"?: unknown;
  "freeze"?: unknown;
  "basis_set"?: unknown;
  "keywords"?: unknown;
  "frequency_mode"?: unknown;
  "output_path"?: unknown;
  "orca_blocks"?: unknown;
  "end_setting"?: unknown;
  "force_constant"?: unknown;
  "scan_mode"?: unknown;
  "log_path"?: unknown;
  "ts_candidate_path"?: unknown;
  "freq_log"?: unknown;
  "irc_log"?: unknown;
  "reactant_logs"?: unknown;
  "product_logs"?: unknown;
  "strict"?: unknown;
} | {
  "mode": "interpolate";
  "run_id": string;
  "charge"?: unknown;
  "multiplicity"?: unknown;
  "electronic_character"?: unknown;
  "nproc"?: unknown;
  "mem"?: unknown;
  "selected_candidate"?: unknown;
  "evidence_refs"?: unknown;
  "reactant_path"?: unknown;
  "reactant_text"?: unknown;
  "product_path"?: unknown;
  "product_text"?: unknown;
  "output_dir"?: unknown;
  "timeout"?: unknown;
  "refinement_runs"?: unknown;
  "input_path"?: unknown;
  "input_text"?: unknown;
  "engine"?: unknown;
  "scans"?: unknown;
  "freeze"?: unknown;
  "method"?: unknown;
  "basis_set"?: unknown;
  "keywords"?: unknown;
  "frequency_mode"?: unknown;
  "output_path"?: unknown;
  "orca_blocks"?: unknown;
  "end_setting"?: unknown;
  "force_constant"?: unknown;
  "scan_mode"?: unknown;
  "solvation"?: unknown;
  "log_path"?: unknown;
  "ts_candidate_path"?: unknown;
  "freq_log"?: unknown;
  "irc_log"?: unknown;
  "reactant_logs"?: unknown;
  "product_logs"?: unknown;
  "strict"?: unknown;
} | {
  "mode": "scan_prepare";
  "run_id": string;
  "charge"?: unknown;
  "multiplicity"?: unknown;
  "electronic_character"?: unknown;
  "nproc"?: unknown;
  "mem"?: unknown;
  "selected_candidate"?: unknown;
  "evidence_refs"?: unknown;
  "reactant_path"?: unknown;
  "reactant_text"?: unknown;
  "product_path"?: unknown;
  "product_text"?: unknown;
  "n_images"?: unknown;
  "interp_method"?: unknown;
  "watch_pairs"?: unknown;
  "output_dir"?: unknown;
  "timeout"?: unknown;
  "refinement_runs"?: unknown;
  "input_path"?: unknown;
  "input_text"?: unknown;
  "output_path"?: unknown;
  "log_path"?: unknown;
  "ts_candidate_path"?: unknown;
  "freq_log"?: unknown;
  "irc_log"?: unknown;
  "reactant_logs"?: unknown;
  "product_logs"?: unknown;
  "strict"?: unknown;
} | {
  "mode": "scan";
  "run_id": string;
  "charge"?: unknown;
  "multiplicity"?: unknown;
  "electronic_character"?: unknown;
  "nproc"?: unknown;
  "mem"?: unknown;
  "selected_candidate"?: unknown;
  "evidence_refs"?: unknown;
  "reactant_path"?: unknown;
  "reactant_text"?: unknown;
  "product_path"?: unknown;
  "product_text"?: unknown;
  "n_images"?: unknown;
  "interp_method"?: unknown;
  "watch_pairs"?: unknown;
  "output_dir"?: unknown;
  "timeout"?: unknown;
  "refinement_runs"?: unknown;
  "input_path"?: unknown;
  "input_text"?: unknown;
  "output_path"?: unknown;
  "log_path"?: unknown;
  "ts_candidate_path"?: unknown;
  "freq_log"?: unknown;
  "irc_log"?: unknown;
  "reactant_logs"?: unknown;
  "product_logs"?: unknown;
  "strict"?: unknown;
} | {
  "mode": "provided";
  "run_id": string;
  "charge"?: unknown;
  "multiplicity"?: unknown;
  "electronic_character"?: unknown;
  "nproc"?: unknown;
  "mem"?: unknown;
  "selected_candidate"?: unknown;
  "reactant_path"?: unknown;
  "reactant_text"?: unknown;
  "product_path"?: unknown;
  "product_text"?: unknown;
  "n_images"?: unknown;
  "interp_method"?: unknown;
  "watch_pairs"?: unknown;
  "output_dir"?: unknown;
  "timeout"?: unknown;
  "refinement_runs"?: unknown;
  "input_path"?: unknown;
  "input_text"?: unknown;
  "engine"?: unknown;
  "scans"?: unknown;
  "freeze"?: unknown;
  "method"?: unknown;
  "basis_set"?: unknown;
  "keywords"?: unknown;
  "frequency_mode"?: unknown;
  "output_path"?: unknown;
  "orca_blocks"?: unknown;
  "end_setting"?: unknown;
  "force_constant"?: unknown;
  "scan_mode"?: unknown;
  "solvation"?: unknown;
  "log_path"?: unknown;
  "freq_log"?: unknown;
  "irc_log"?: unknown;
  "reactant_logs"?: unknown;
  "product_logs"?: unknown;
  "strict"?: unknown;
});

type TsGuessData_QmCalculation = {
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

type TsGuessData = {
  /** Whether the operation succeeded */
  "is_success": boolean;
  /** Status or error message (default="") */
  "message"?: string;
  /** For run_id operations: authoritative TS process view after the accepted guess revision. A successful call is not scientific verification. (default=null) */
  "process"?: {
  [key: string]: unknown;
} | null;
  /** Original independent path-runner diagnostics; retained on failure and explicit interpolation fallback. */
  "diagnostics"?: Array<string>;
  /** Independent geometry analysis: complete concrete endpoint correspondences when mapping is ambiguous. Choose one with selected_candidate; these are mapping alternatives, not verified TS results. */
  "mapping_candidates"?: Array<{
  [key: string]: unknown;
}>;
  /** scan_prepare: complete settings of the written input/manifest. Preparation is not a calculation result or TS validation. (default=null) */
  "calculation"?: TsGuessData_QmCalculation | null;
  /** interpolate/xtb_path: image directory, or the retained run directory on an unsuccessful xTB path search (default="") */
  "images_dir"?: string;
  /** interpolate/scan_parse: per-frame observed distance text table; scan_parse marks missing or unaligned geometries explicitly (default="") */
  "distance_table"?: string;
  /** TS candidate frame index (0-based) (default=null) */
  "ts_candidate_index"?: number | null;
  /** TS-guess xyz path (default="") */
  "ts_candidate_path"?: string;
  /** xtb_path: what the engine's own path-refinement loop reported. 'converged' = xTB declared its convergence criterion met (the only state in which the TS candidate is handed over); 'cycles_exhausted' = the refinement hit the `refinement_runs` ceiling and the path is TRUNCATED, so is_success is False. (default="") */
  "refinement_termination"?: "" | "converged" | "cycles_exhausted";
  /** xtb_path: overall runner outcome, separate from the engine's refinement marker. (default=null) */
  "path_termination_reason"?: "completed" | "executable_missing" | "timeout" | "invalid_endpoints" | "incomplete_artifacts" | "path_not_converged" | "failed" | "unknown_failure" | null;
  /** How the path guess was produced. 'xtb_path' = xTB metadynamics path search; 'idpp_fallback' = xtb was unavailable so IDPP interpolation was used instead (a degraded route, reported explicitly); '' = this mode does not produce a path. Never treat a guess as a verified saddle point. (default="") */
  "path_kind"?: "" | "xtb_path" | "idpp_fallback";
  /** scan_prepare: generated input file path (default="") */
  "input_file_path"?: string;
  /** scan_prepare: submit/run hint (default="") */
  "run_hint"?: string;
  /** scan_parse: per-point relative-energy text table (kcal/mol) (default="") */
  "profile_table"?: string;
  /** scan_parse: whether an analyzed energy profile has an internal maximum; null when no reliable energy profile was parsed, independent of geometry availability. (default=null) */
  "scan_has_internal_peak"?: boolean | null;
  /** scan_parse: profile verdicts */
  "verdicts"?: Array<string>;
  /** scan_parse: constrained-scan diagnostic only (highest point − first point, kcal/mol) — NOT a verified ΔE‡/ΔG‡; unconstrained OptTS + freq + IRC still required before any barrier claim (default=null) */
  "barrier_kcal"?: number | null;
  /** scan_parse: unique constrained-scan local-peak candidate as {scan_index, energy, geometry_ref, source}; not a validated TS. Multiple candidates are listed in verdicts with point/energy/XYZ for an existing provided-guess choice; null when no unique candidate was selected or its geometry is unavailable. (default=null) */
  "candidate"?: {
  [key: string]: unknown;
} | null;
  /** scan_parse: an internal peak exists but its geometry could not be recovered from this run's artifacts (a missing sidecar frame is NEVER substituted with the last frame). (default=false) */
  "candidate_unavailable"?: boolean;
  /** verify: default candidate/unlikely/inconclusive; strict is pass/fail/inconclusive. (default="") */
  "verdict"?: string;
  /** verify: structured status from the verification branch; empty outside verify or when verification could not run. (default="") */
  "verification_status"?: "" | "candidate" | "pass" | "fail" | "inconclusive";
  /** verify: number of imaginary frequencies (default=null) */
  "n_imag"?: number | null;
  /** verify: imaginary frequencies (cm⁻¹, negative) */
  "imag_freqs"?: Array<number>;
  /** verify: per-check details */
  "checks"?: Array<string>;
  /** verify: IRC endpoint A xyz path (default="") */
  "irc_end_a_path"?: string;
  /** verify: IRC endpoint B xyz path (default="") */
  "irc_end_b_path"?: string;
  /** verify: whether the imaginary normal mode matches the watch_pairs reaction coordinate; None if displacements cannot be parsed. (default=null) */
  "imag_mode_aligned"?: boolean | null;
  /** verify: explanation of the imaginary-mode vs reaction-coordinate alignment check. (default="") */
  "imag_mode_alignment"?: string;
};

declare const tools: {
  /** Transition-state (TS) guess workflow: choose an explicit mode. Use run_id to revise the guess intent of an existing TS run through its durable queue. The run owns endpoint structures, atom correspondence, charge, multiplicity, electronic character and compute resources. Independent geometry analysis accepts complete endpoint MOL/SDF graphs and proves their mapping internally; xtb_path: execute an independent xTB metadynamics path search between confirmed all-atom endpoints; interpolate: linear or IDPP interpolation from reactant/product xyz to generate NEB candidate-path images (confirmed automatic atom correspondence, alignment, distance monitoring and a candidate frame); scan_prepare: write a Gaussian/ORCA constrained-scan input or a typed native xTB scan manifest (bond/angle/dihedral; xTB requires an explicit method and force_constant); for MLIP/external potentials pass method='ExtOpt' (ORCA, plus orca_blocks with the %method ProgExt block) or method='external' (Gaussian, plus keywords='external="mace"'); scan_parse: inspect a one-dimensional or explicitly concerted native scan path and report internal local-peak candidates. A unique peak yields a TS-guess xyz; multiple peaks list point numbers, energies and exact XYZ paths in verdicts for a provided-guess choice. ORCA uses relaxscanact.dat plus matching ts_scan.NNN.xyz frames; independent multidimensional grids are not flattened into paths. without the sidecar the log text is grouped per 'RELAXED SURFACE SCAN STEP' and each point's converged (last) energy/geometry is used, so per-cycle energies are never misread as scan points; verify: by default, frequency plus rough IRC-endpoint connectivity yields candidate/unlikely/inconclusive; with strict=True, requires one reaction-relevant imaginary frequency, bidirectional IRC from that same TS, expected endpoint structures, and native reactant_logs/product_logs proving that the actual IRC outer frames were optimized to the correct zero-imaginary minima, yielding pass/fail/inconclusive. Opt and Freq may be in combined or separate logs; geometric interval checks are advisory only. For an exploratory scan: scan_prepare (after internal_coordinates) → submit → scan_parse. For formal TS refinement and validation, provide the candidate to ts_prepare rather than submitting manual TS/IRC jobs; xtb_path/interpolate are fallbacks and never a saddle. Independent xtb_path executes a calculation directly; run-based operations always use the existing TS revision and queue; scan_prepare writes an input to submit with submit_compute_job, while interpolate/scan_parse/verify generate or inspect artifacts. Coordinates never enter context; only numeric tables, verdicts, and file paths are returned. */
  ts_guess(args: TsGuessArgs): Promise<ToolResponse<TsGuessData>>;
};

declare function text(value: unknown): void;
```

## Calling pattern

Construct args from the contract and the actual task declarations. This pattern does not supply scientific methods or other task inputs.

```javascript
const r = await tools.ts_guess(args);
if (r.is_success) text(r.data); else text(r.summary);
```