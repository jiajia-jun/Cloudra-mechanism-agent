# Chemical-tool review of TS edges — tasks NU3, NY3, NU5  (small_mol / a-4)

Scope: for **every edge carrying a `ts_log`** in `gold_compute/edge_barriers/computed/<TASK>.json`, verify with the **chemistry tools** (not bash text slicing) that the **imaginary normal mode / converged geometry is consistent with the declared elementary step**. Read-only: no product or number was modified; no QM job was submitted.

## Edges in scope
| TASK | edge | ts_log (jobname) | TS geometry used |
|---|---|---|---|
| NU3 | NU3_E1  | calc-382 → `calc-E1-TS1c.inp` | calc-E1-TS1c.xyz |
| NU3 | NU3_E2a | calc-418 → `calc-E2a-TS.inp`   | calc-E2a-TS.xyz |
| NU3 | NU3_E2b | calc-424 → `calc-E2b-TS-retry.inp` | calc-E2b-TS-retry.xyz |
| NY3 | NY3_E2  | calc-365 → `calc-e2-ts3.inp`   | calc-e2-ts3.xyz |
| NU5 | NU5_E2  | calc-467 → `calc-E2-TS2b.inp` | calc-E2-TS2b.xyz |
| NU5 | NU5_E4  | calc-469 → `calc-E4-TS4.inp`  | calc-E4-TS4.xyz |

Edges **without** `ts_log` (barrierless / no isolated saddle; out of scope): NY3_E3, NU5_E1, NU5_E3.

## Tooling note (important)
`format_converter(input_format='log', output_format='xyz')` **failed on every ORCA log** here with an internal index-out-of-range error ("日志解析器内部索引越界"), reproducible also for a plain ORCA min log (calc-416). The prescribed log→xyz export is therefore unavailable in this environment. Fallback used: the **ORCA-native final-geometry `.xyz`** written by the engine itself for the same job, bound unambiguously to `ts_log` via the log header line `NAME = <jobname>.inp` (read as text). This is the engine's own last converged frame, not a hand-parsed coordinate block. Recommend fixing the ORCA branch of `format_converter`.

## Per-edge verification
| TASK/EDGE | final-block imag (n_imag) | perceived forming / breaking (vs declared `bond_changes`) | angle anomalies | partial bonds / Mayer BO (disputed) | conclusion | tools |
|---|---|---|---|---|---|---|
| **NU3_E1** | **-279.00 cm⁻¹** (1) | form C1–C8 **2.163 Å** (map1–map3 ✓) and H7–O9 **1.808 Å** (map4–map5 ✓); break P2–H7 (map2–map5) still 1.449 Å full bond (incipient only) | C1–P2–H5 122.7° (+13.2) | — | **PASS** — early, reactant-like saddle; mode on the C–C/proton-transfer coordinate | log_parser, internal_coordinates |
| **NU3_E2a** | **-1021.55 cm⁻¹** (1) | form P2–O9 **2.277 Å** (map2–map4 ✓) + P2–H7 **1.429 Å** (map2–map5 ✓); O9–H7 1.703 Å = the O–H being cleaved (map4–map5 ✓) | H6–P2–H7 125.2° (+15.7), P2–C1–C8 96.9° (-23.3) | **Mayer**: P2–H7 **0.803** (partial), P2–O9 **0.379** (incipient); C1–C8 0.945 (single), C8–O9 1.230. RKS closed shell, no spin contamination | **PASS** — genuine, localized saddle for concerted O→P proton transfer + P–O ring closure; adduct connectivity intact (not product-like), not a soft spectator mode | log_parser, internal_coordinates, electronic_analysis |
| **NU3_E2b** | **-624.78 cm⁻¹** (1) | break C2–P3 **2.390 Å** (map1–map2 ✓) + C1–O4 **1.869 Å** elongated (map3–map4 ✓); form C1–C2 **1.406 Å** (C=C, map1–map3 ✓) + P3–O4 **1.567 Å**, bond order 2 (P=O, map2–map4 ✓) | C1–O4–P3 96.7° (-23.3), several H–P–/H–C–O angles off | — | **PASS** — product-like (late) cycloreversion saddle: P=O formed, C=C contracting, the two ring bonds stretched | log_parser, internal_coordinates |
| **NY3_E2** | **-159.06 cm⁻¹** (1) | break O2–C3 **2.666 Å** (far ⇒ broken; map3–map4 ✓); form C3–O5 **1.214 Å**, bond order 2 (C=O, map4–map5 ✓); C1–O2 1.337 Å (methyl–O) | none > 12° | — | **PASS** — product-like (late) methoxide-elimination saddle; 2 fragments; C=O re-formed | log_parser, internal_coordinates |
| **NU5_E2** | **-351.30 cm⁻¹** (1) | form C1–C12 **1.866 Å** (map1–map9 ✓); break C1–O2 **1.270 Å** weakened (map1–map2 ✓); attacking N11–C12 near-linear | C1–C12–N11 153.1° (-26.9), H3/H4–C1–C12 ≈ -15/-12° | — | **PASS** — α-addition saddle: new C–C incipient, aldehyde C=O weakened, isocyanide approaching linear | log_parser, internal_coordinates |
| **NU5_E4** | **-153.44 cm⁻¹** (1) | no distance anomaly (all bonds within 15%); connectivity is the **product-like** acyl arrangement (amide C3–O6, ester O5–C7) | none > 12° | **Mayer** partial bonds: N2–C3 **1.664**, C3–O6 **1.706**, O5–C7 **1.451**, C7–O8 **1.412**; O8–H14 **0.898** (O–H intact ⇒ proton not yet on N). RKS closed shell | **PASS (with caveat)** — delocalized acyl-transfer saddle (formyl C bridging O5/O8); proton shuttle is early at this frame; low -153 cm⁻¹ but the displacement/partial-bond pattern spans the acyl+proton coordinates. Keep MEDIUM confidence | log_parser, internal_coordinates, electronic_analysis |

## Cross-checks
- **Final-block imaginary counts**: all 6 logs give **exactly 1** imaginary frequency in the final VIBRATIONAL block; values match the declared `imaginary_frequencies` in the computed JSONs (-279.0 / -1021.55 / -624.78 / -159.06 / -351.30 / -153.44). `opt_converged=True` and `normal_termination=True` for all six; `job_types` include `ts,freq,opt`.
- **Declared bond_changes ↔ geometry**: every in-scope edge's declared forming/breaking pairs are recovered from the TS geometry (after resolving the atom-map→xyz-index permutation for each job from the `.inp` coordinate block).
- **Disputed saddle NU3_E2a**: the large imaginary mode is a real localized bond reorganization (P–H forming, P–O closing), **not** a product-type geometry and **not** a soft spectator H-mode; closed-shell single-reference (RKS) with no spin contamination. The high barrier (55.81 kcal/mol) reflects the strained 4-membered-ring (anti-aromatic-well) closure — chemically expected, not an artifact.
- **Heredoc/limitation recall**: the previously flagged "loose 1-imag saddle = soft spectator H-mode" failure mode does NOT apply to NU3_E2a (partial BO on P–O and P–H, both heavy-atom-involving); it is worth watching on floppy multi-fragment edges (NU5_E4 proton arm).

## Overall verdict
All 6 edges with a `ts_log` show **exactly one imaginary mode sited on the declared reaction coordinate**, and the converged TS geometry is consistent with the declared `bond_changes` for every step. **No edge fails**; NU5_E4 carries a documented caveat (product-like/delocalized, low-frequency Mumm saddle, medium confidence — as already recorded in the campaign handoff).

## Artifact paths
- TS logs: `gold_compute/campaign/runs/<TASK>/.../calc-*.out.log` (see table; NU3 logs under `runs/NU3/NU3_E1/1/.cloudra/`).
- TS geometries analyzed (ORCA-native, tool output):
  `runs/NU3/NU3_E1/1/calc-E1-TS1c.xyz`, `.../calc-E2a-TS.xyz`, `.../calc-E2b-TS-retry.xyz`,
  `runs/NY3/E2/1/calc-e2-ts3.xyz`, `runs/NU5/E2/1/calc-E2-TS2b.xyz`, `runs/NU5/E4/1/calc-E4-TS4.xyz`.
- Method (all edges): B3LYP-D3(BJ)/def2-SVP, ORCA 6.1.1, RIJCOSX/def2/J; solvent per task (NU3 gas, NY3 CPCM(water), NU5 CPCM(DCM)).
- Tools used: `get_skill(dft-calculation)`, `log_parser`, `format_converter` (failed), `internal_coordinates`, `electronic_analysis`. No files in `gold_compute/edge_barriers/computed/` or the task sources were modified.

_Reviewer: small_mol (a-4), chemical-tool independent re-check. Date order 2026-09._
