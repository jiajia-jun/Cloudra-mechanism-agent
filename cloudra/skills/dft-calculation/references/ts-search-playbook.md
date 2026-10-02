# TS search playbook

**Temporary restriction:** The engine recipes below describe scientific methods; manual TS/IRC submission is currently disabled. Use `ts_prepare`/`ts_resume` for TS/IRC jobs, including OptTS, ScanTS and NEB-TS. Ordinary exploratory scans remain available. If the durable workflow cannot express the required calculation, report the limitation for repair instead of submitting a manual chain or executing the engine through `bash`.

How to get from "we know the step" to a validated first-order saddle point, without burning the queue. The doctrine in one line: **convergence is decided by guess quality and Hessian quality, not optimizer settings** — the best-documented replays after failure are physical (new conformer, new path, better endpoints), and IDPP-class guesses cut MEP-search cost by half or more relative to naive interpolation.

## 1. Seed hierarchy (use the highest rung that fits)

1. **`ts_prepare` process** — declare grouped reaction, explicit conformer/guess sources and independent methods; it builds/maps/assembles/guesses/validates/submits/refines autonomously. `blocked` names the offending declaration; fix and `ts_resume`.
2. **Mapped interpolation → NEB** — endpoints optimized at the same level, atom numbering aligned 1:1, all-atom map complete. `ts_guess mode=interpolate` with **IDPP** (distance-space interpolation; never Cartesian-linear, which overlaps atoms and kills SCF). For ORCA, `! NEB-TS` (CI-NEB coarse → eigenvector-following refine) is the reference workflow; **NEB is the ceiling — QST2/QST3 are banned** (§2).
3. **Relaxed scan (1D or 2D)** — the workhorse when 1–2 internal coordinates describe the step. `ts_guess scan_prepare` (1 coordinate for ORCA, 1–2 for Gaussian; higher-dimensional or direction-sensitive cases belong to NEB instead). Scan peak → **fresh unconstrained** TS job. The peak is a seed.
Use a MethodPolicy-permitted, available semiempirical method for exploratory PES scans (e.g. Gaussian PM7 or ORCA GFN2-xTB when supported). This is a choice of exploration level, not a last rung after expensive routes fail. Refine candidate regions at the agreed DFT level; low-level energies never enter delivered barriers.

For endpoint-based paths, check endpoint structures and atom correspondence. Exploratory scans can investigate an unknown endpoint; label their structures as candidates. A delivered path/barrier still needs the verified endpoints and comparable energies required by its evidence contract. Pre-orient complexes toward the hypothesized reactive pose.

## 2. Why QST2/QST3 are banned

QST interpolates a single quadratic transit curve between endpoint geometries and maximizes along it. It fails systematically when the "averaged" geometry is chemically meaningless (classic: HCN→CNH midpoint puts H inside the C≡N bond), demands identical atom ordering with no error if violated, and offers no path correction — a bad initial interpolation can only fail. NEB optimizes the whole MEP with a climbing image (correctable, resumable, exposes intermediates/multi-peaks); scans are cheaper and controllable when the coordinate is known. QST has no unique advantage — **do not write QST2/QST3 inputs, and do not revive them as a "quick try".** The ceiling is NEB.

## 3. NEB-TS practice (ORCA)

- `! NEB-TS` is the default one-shot (Loose-NEB-TS internally: CI-NEB to loose tolerances, then EF/P-RFO refine). `Fast-NEB-TS` (single NEB iteration → TS opt) is the budget variant; `ZOOM-NEB-TS` for long-tailed paths.
- Images: default `NImages 8` (excluding endpoints); 5–10 intermediate images per energy maximum. Do not inflate to dozens — convergence gets slower and less stable.
- After launch, **inspect the initial path** (`*_initial_path_trj.xyz`) before anything else: atom collisions and absurd bond cleavage show up immediately. `*_MEP.allxyz` enables restart.
- Cheap path pre-refinement: `Interpolation XTB2` or an xTB-level NEB-TS run first.
- NEB gives a **candidate**: still run freq (exactly one imaginary mode) and IRC before calling it a TS.

## 4. Scan practice (1D and 2D)

- **Choose the level before submitting.** `ts_guess scan_prepare` requires an explicit `method`. Favor permitted semiempirical methods for broad PES exploration, checking the target engine's availability and solvent/model support. If no suitable cheap combination is available, report that limitation and choose within the authorized scope; do not silently substitute DFT. If a profile is discontinuous or implausible, inspect the model and frame geometries before changing coordinates or methods. Refine a selected seed with a fresh unconstrained DFT TS job and verify its frequency and connectivity. A low-level peak is not a final barrier.
- Typical grid: 12–15 steps per coordinate; bond stretch 0.05–0.1 Å/step, dihedral 2–10°/step. Start from the equilibrium side, scan toward the forming/breaking direction.
- SCF struggling near the barrier top is normal (`SlowConv`-class settings are acceptable there).
- **When 2D is worth it**: two coordinates move concertedly (concerted double-bond shifts, proton transfer coupled to donor–acceptor distance), a 1D profile jumps/discontinues (another degree of freedom relaxed abruptly), or NEB initial paths keep collapsing. Cost is N² constrained optimizations (10×10 = 100) and results depend on scan direction/coordinate order — so confirm NEB cannot take the case before going beyond 2D. A diagonal alternative is a synchronous multi-coordinate scan (ORCA `Simul_Scan`), cost of one 1D scan but only the diagonal slice.
- Keep per-point `*.NNN.xyz` and the `*.relaxscanact.dat` sidecar for `scan_parse`; it reports the peak as a `candidate` with `scan_index`/`energy`/`geometry_ref` and never substitutes the last frame for a missing peak.
- Pass relevant software-native `watch_pairs` (Gaussian 1-based, ORCA 0-based) to `scan_parse` and inspect its per-frame `distance_table` alongside the energy profile and perceived connectivity changes, including hydrogen motion outside the scanned coordinate. Missing frames leave gaps in the audit. Distance-based connectivity changes are clues, not identified products or validated reaction paths.
- **The peak is a seed**: extract it, write a fresh input without any `Scan`/`Constraints` remnants, refine as TS.

## 5. TS refinement and the convergence ladder

Default templates:

- ORCA: `! OptTS Freq TightSCF` + `%geom Calc_Hess true end` (exact initial Hessian; a model/force-field Hessian knows only positive curvature and cannot describe a saddle). Local mode → `Hess_Internal` from scan neighbors (ScanTS automates); delocalized/concerted mode → `Hybrid_Hess {reactive atoms}`.
- Gaussian: `Opt=(TS,CalcFC,NoEigenTest) Freq`. CalcFC (exact Hessian at point 1) is the minimum; CalcAll (every step) is the last resort for pathological cases, not a default. NoEigenTest only suppresses mid-optimization curvature aborts — **it transfers all saddle validation to the final freq**, never skip that.

When refinement struggles, climb in order:

1. **Check the followed mode first** (steps 1–5): ORCA prints the TS-mode composition — if it is not the intended coordinate, redirect with `TS_Mode {M n}` / `{B i j}` instead of burning more steps.
2. **Rebuild the guess** (closer scan peak, better conformer, NEB climbing image) — proximity to the saddle beats every knob.
3. `Recalc_Hess 5` (every 5 steps; value 1 only for truly pathological cases — it costs a full Hessian per step).
4. Small fixed step: ORCA `Trust -0.1`/`MaxStep 0.1`; Gaussian `iop(1/8=10)` or `Opt=MaxStep=10`, plus `Opt=NoTrustUpdate` if every step needs it.
5. Coordinate/Hessian-level moves: ORCA `TS_Active_Atoms`, `modify_internal`, `COPT`; Gaussian restart with `CalcFC` after 10–15 deforming steps, or `Opt=ReadFC` continuing from a freq chk.
6. Flat-PES numerical noise: `Tight`/`VeryTight` + `Int=UltraFine` (G09-era Fine grids make opt and freq convergence fight each other).
7. Still failing → change strategy (NEB-TS instead of single-ended refinement), or record the unresolved claim with the diagnosis. **Do not stack parameter tweaks onto retry #4.**

## 6. Soft modes and floppy/ionic complexes

H-bonded complexes, ion–molecule complexes, and long floppy chains give the Hessian near-zero positive eigenvalues; RFO steps then diverge and the optimizer oscillates forever (energy and RMS force plateau, steps pinned at the trust radius). Expect that **some of these TS searches cannot converge** — plan for that outcome instead of forcing it.

Regime moves, in order:

- Isolate the slack from the reaction coordinate: pre-optimize the encounter complex with only the reactive region free (`Constraints`/`ConstrainFragments`), freeze irrelevant floppy dihedrals during scan/NEB, release them for the final refinement.
- Keep fragments from flying apart: ORCA `%geom SPHEREPOT 2` / `BOXPOT` wall potentials; CREST `--nci`-style ellipsoidal walls for ensembles.
- Cheap curvature: GFN2-xTB Hessian first (`InHess XTB2` or read an xTB freq `.hess`), then DFT OptTS.
- Small fixed trust radius + frequent exact Hessian (approximate-Hessian updates are poor in soft-mode-dominated systems).
- Consider that the question may be an ensemble/loose-TS one: conformer ensemble + quasi-RRHO treatment of <100 cm⁻¹ modes instead of a single-structure answer.

## 7. Imaginary modes: chemical assignment is mandatory

A "TS" is delivered only when all hold:

1. Optimization converged by the engine's own marker (`THE OPTIMIZATION HAS CONVERGED` / `Stationary point found` with verified forces — never `ORCA TERMINATED NORMALLY` alone, never exit code 0).
2. Frequency at the **same level** (functional, basis, grid) shows **exactly one** imaginary mode. Multiple small imaginaries (≲50i cm⁻¹) are usually numerical noise or methyl rotors: re-optimize Tight+UltraFine and re-check rather than hand-waiving extras.
3. The imaginary mode's displacement **lives on the reacting heavy atoms** (the bond-making/breaking pair moving toward each other). If it sits on methyl rotation, loose torsions, or proton wobbles of a floppy ion–molecule complex, it is a **pseudo-saddle** — a conformational/complex-rearrangement saddle, not the reaction TS. Record as unresolved with the evidence. **Never judge a mode by its number alone**: `log_parser` on the frequency log returns per-imaginary-mode composition (`imaginary_modes`: top displaced atom pairs, heavy-atom fraction, and — when you pass the step's declared forming/breaking pairs as `watch_pairs` — the fraction of the mode on the claimed coordinate). Low watch fraction = the mode is not your reaction coordinate; respond to it explicitly (re-search or document the pseudo-saddle), do not wave it through.
4. IRC (or optimized endpoints from both IRC directions) connects to the intended minima; endpoint identities verified.

Start with a purposefully bounded bidirectional IRC, choosing its extent for the direction evidence needed, path topology and coupling, and compute cost; no universal count applies. Then optimize each outer frame without constraints at the same agreed model. Confirm minimum frequencies, endpoint identities and direction against the TS; keep native convergence status and label partial paths. Extend only when partial geometry still cannot establish direction or identity, not to satisfy a step count or intrinsic IRC convergence flag. The short path alone does not prove the full path or dynamics.

Magnitude sanity: |ν| ≥ 100 cm⁻¹ is a healthy saddle signal; 20–100 cm⁻¹ is usable but flags care with IRC and thermochemistry.

## 8. Failure bookkeeping

One-shot TS success is under half even in good pipelines; experts land ~3/4 of cases only after physical replans. Every failed attempt gets: the input kept, the failure class recorded (mode followed, wrong basin, SCF, pseudo-saddle, soft-mode oscillation), and the next physical move decided **before** resubmission. A failure without a recorded diagnosis is a promise to pay for the same compute twice.

### Automated scan continuation

With declared endpoints, call `ts_prepare` once with grouped `input`: `reaction`, explicit `conformers` sources, typed `guess`, `ts_optimization`, independent `verification` calculations, and `execution`. A scan is `guess={kind:"scan", calculation:{engine,method,keywords}, scans, freeze}`; the Agent chooses its exploration method independently of the formal TS method, subject to the trusted project policy. Every calculation supplies its own method and keywords; omitted science stops at a named checkpoint. Successful jobs advance automatically. Read status/evidence/actual methods with `ts_inspect(run_id)`. Use `ts_resume(run_id, changes, reason, request_key, expected_revision)` for future revisions on that same run, including after an attempt ends. Failed attempts may be revised or retried directly; failure history remains recorded and new results must pass scientific verification. Active jobs prevent revisions. A scan peak remains a candidate and requires fresh unconstrained formal refinement and verification. Ordinary unknown-endpoint exploration may use standalone scans; manual TS/IRC submission remains disabled.

All atom fields in an engine workflow use Gaussian 1-based or ORCA 0-based numbers, including maps, ring_order, distance_filters, scans, freeze and watch_pairs. `conformer_search`, `internal_coordinates` and `reaction_mapping` use 1-based numbers: subtract one when transferring their atom numbers to ORCA. Ring and filters work independently or together; both guide generation and qualify output. Ring shape labels describe final geometry and do not establish minima or TS validity.


## 实验性构象档案与选择

regions 模式保存原始候选及其父子谱系；结构区域卡片中的内坐标、能量来源和失败证据用于选择下一步。固定容差分区仅作对照；statistical_partition 输出探索性全搜索校准评分与稳定性，记录抽样假设，不给正式 p 值。显式选择坐标/理由、接受建议并更新 partition_revision。没有测量的能量、未验证的种子和未计算的分支不能标记成功；预算不足保留未完成证据。选择已有候选优先复用身份/映射和已完成独立分支；选择、补采样和预算通过同库原子 READY 绑定执行；普通完成由系统续接，能力缺失或预算不足明确受阻，不绕过手动提交禁令。
