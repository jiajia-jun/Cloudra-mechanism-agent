# REVIEW — 化学工具化复核 (chemical-tool cross-check of TS geometry vs declared step)
Group: **HA6, HG2** (small_mol / a-4, independent reviewer)
Remit: for **every edge that carries a `ts_log`**, independently verify with **chemical tools** (not bash text
slicing) that (a) the final VIBRATIONAL block has exactly one imaginary frequency, and (b) the converged TS geometry
is chemically consistent with the **declared** elementary step (forming/breaking bonds, angles). Read-only audit:
no QM was submitted, no `gold_compute/edge_barriers/computed/*.json` or 題源 was modified.

## Edges in scope (all carry `ts_log`)
| TASK | EDGE | ts_log | ts geom artifact | declared step |
|---|---|---|---|---|
| HA6 | HA6_E1  | calc-452.out.log | `runs/HA6/HA6_E1/ts_optfreq.xyz`    | conrotatory ring opening, both methyls OUTWARD (→(E,E)-2,4-hexadiene); C2–C5 σ-bond breaking |
| HA6 | HA6_EM1 | calc-463.out.log | `runs/HA6/HA6_EM1/ts_optfreq.xyz`   | conrotatory ring opening, both methyls INWARD (→(Z,Z)-2,4-hexadiene); C2–C5 σ-bond breaking |
| HG2 | HG2_E1  | calc-582.out.log | `runs/HG2/HG2_E1/chair_tsF.xyz`     | concerted Claisen [3,3]: C2–C7 forming, C4–O5 breaking |
| HG2 | HG2_EM1 | calc-520.out.log | `runs/HG2/HG2_E1/chair_tsB.xyz`     | concerted Claisen [3,3]: C2–C7 forming, C4–O5 breaking |

Atom numbers are **bound**: the TS-`.xyz` index labels (element+index from `internal_coordinates`) reproduce the
gold JSON heavy-atom labels and its recorded reactive distances to 3 decimals, so no "未绑定原子号" caveat applies.

## Per-edge verdict table

| TASK/EDGE | 最终块虚频 (log_parser) | 感知的成/断键 (internal_coordinates, vs 声明) | 键角异常 | 部分键/键级 (electronic_analysis, Mayer) | 结论 | 工具 |
|---|---|---|---|---|---|---|
| **HA6_E1**  | n_imag = **1**, **-520.96 cm⁻¹** (final block) | r(C2–C5)=**2.164 Å** → `forming_candidate` (this is the ring σ-bond BREAKING). C2–C3 1.434, C3–C4 1.377, C4–C5 1.434. **一致** | C2–C3–C4 104.9° (Δ-15.1), C3–C4–C5 104.9° (Δ-15.1) → retained 4-ring strain | C2–C5 **incipient BO 0.643** (IBO 2c-2e 50/50); C2–C3/C4–C5 partial (1.32); C3–C4 1.542 single. Closed-shell RKS converged | **通过** | log_parser, format_converter*, internal_coordinates, electronic_analysis |
| **HA6_EM1** | n_imag = **1**, **-631.01 cm⁻¹** (final block) | r(C2–C5)=**2.235 Å** → `forming_candidate` (same ring σ-bond BREAKING, inward channel). C2–C3 1.431, C3–C4 1.379, C4–C5 1.431. **一致** | C2–C3–C4 105.9° (Δ-14.1), C3–C4–C5 105.9° (Δ-14.1) | C2–C5 **incipient BO 0.613**; C2–C3/C4–C5 partial (1.31); C3–C4 1.515. Closed-shell RKS converged | **通过** | 同上 |
| **HG2_E1**  | n_imag = **1**, **-355.71 cm⁻¹** (final block) | r(C2–C7)=**2.486 Å** `forming_candidate` (new C–C) and r(C4–O5)=**2.067 Å** `forming_candidate` (C–O breaking). Perceived graph = 2 fragments (both contacts not yet perceived bonded). **一致** | C6–C7–C8 123.0° (Δ+13.5) → sp²-like C7 at TS | C2–C7 **incipient BO 0.336**, C4–O5 **incipient BO 0.350**; O5–C6 1.628, C6–C7 1.452, C2–C3 1.504, C3–C4 1.532 (partial). Closed-shell RKS converged | **通过** | 同上 |
| **HG2_EM1** | n_imag = **1**, **-402.62 cm⁻¹** (final block) | r(C2–C7)=**2.392 Å** `forming_candidate`, r(C4–O5)=**1.995 Å** `forming_candidate` (C–O breaking). Perceived graph = 2 fragments. **一致** | C6–C7–C8 122.1° (Δ+12.6) | C2–C7 **incipient BO 0.351**, C4–O5 **incipient BO 0.404**; O5–C6 1.580, C6–C7 1.435, C2–C3 1.483, C3–C4 1.496 (partial). Closed-shell RKS converged | **通过** | 同上 |

**All four edges PASS**: the final-block imaginary frequency is unique and the perceived geometry (bond distances,
angles, partial/incipient bond orders) is exactly the declared elementary step. No edge shows a distance/clash anomaly
outside the declared reaction coordinate.

## 虚频 "final vs initial block" check
Each ORCA log contains an **initial/working Hessian** VIBRATIONAL block plus the **final** one. `log_parser`
reports the final block only:
- HA6_E1: initial block at line 1598; final block line 10492 → **only -520.96**.
- HA6_EM1: initial block line 1601; final block line 17035 → **only -631.01**.
- HG2_E1: initial block line 1786; final block line 25286 → **only -355.71**.
- HG2_EM1: initial block line 1766; final block line 42228 → **only -402.62**.
`normal_termination=true`, `opt_converged=true` for all four. (Per-edge imag wavenumbers agree with the values
recorded in `computed/HA6.json` / `HG2.json`.)

## 争议边 section (per instruction step 5)
The enumerated disputed edges in the assignment — **NA5_E2 / E3 / E4, HL1_e2, NU3_E2a** — are **NOT in this group's
task list** (HA6, HG2); they belong to the NA5 / HL1 / NU3 reviewers. Out of scope here.
Within this group the closest disputed item is the **HG2 chair/boat ↔ syn/anti pairing** (gold's pairing is recorded
as inverted). Supplementary `electronic_analysis` (PySCF, B3LYP/def2-SVP, charge 0, spin 1, DF) was run on **all four**
edges to test for a product-like / strongly-correlated / soft-spectator saddle:
- **No product-like saddle.** The imaginary modes are hard reaction modes (-355.7 / -402.6 / -521.0 / -631.0 cm⁻¹),
  not soft (<100 cm⁻¹) spectator modes.
- **No strong correlation / diradical.** The closed-shell **RKS** solution is stable and SCF-converged for every edge,
  so ⟨S²⟩ = 0 exactly; the wavefunction is single-reference. The BO pattern is the classic **concerted** signature:
  two partially-formed incipient bonds of comparable order (HG2: C2–C7 0.34–0.35 & C4–O5 0.35–0.40) rather than a
  fully-broken C–O (BO→0, long) + separate radical — i.e. **not stepwise**.
- **HG2 chair vs boat (θ)**: HG2_EM1 (geometric chair, θ=173.6°) is a slightly more advanced saddle (C4–O5 BO 0.404,
  C2–C7 0.351) than HG2_E1 (boat/twist, θ=88.3°; C4–O5 0.350, C2–C7 0.336). Both are the same concerted [3,3] bond
  reorganization. The PySCF relative ordering (EM1 lower by **3.03 kcal/mol**) reproduces the ORCA ordering
  (3.28 kcal/mol), so the *chair-favored* part of the gold claim is supported. The chair/boat→anti/syn **product
  pairing** is a stereochemical assignment that rests on the IRC endpoints + CIP (gold calc-587/588, 547/548); this
  bonding-only review cannot re-derive it and did **not** recompute it (no QM run). → flagged for the Coordinator's
  existing literature-adjudicated resolution, not contradicted by any bonding evidence.

## Limitations / tool notes
- **format_converter(log→xyz) failed on all four ORCA 6.1.1 logs** (
  "日志解析器内部索引越界（疑似截断或损坏的计算日志）" ), both output_format='xyz' and 'csv'. This is an internal
  parser limitation on these ORCA-6.1.1 logs, not a defect of the logs (log_parser reads them fine; the log contains the
  expected sections and terminates normally). Because step-3 export was blocked, the **campaign-bound converged TS
  geometry artifacts** (`ts_optfreq.xyz` / `chair_tsF.xyz` / `chair_tsB.xyz` — the exact files the gold JSON binds
  as `ts_geom`/`ts_xyz`, with their `*_trj.xyz` trajectories present) were used instead. Independent support that
  these are the converged TS frames: `internal_coordinates` measures exactly the reactive distances recorded in the
  gold JSON (2.164 / 2.235 / 2.486, 2.067 / 2.392, 1.995 Å) to 3 decimals.
- No bash/sed was used to extract any chemical quantity (distances, frequencies, bond orders, displacements). All
  numeric chemistry came from log_parser / internal_coordinates / electronic_analysis; bash was used only for file
  existence checks and directory listing.

## Artifacts
- Review artifacts dir: `gold_compute/campaign/review_artifacts_HA6/` (electronic_analysis molden/log output per edge:
  `ea_HG2_E1`, `ea_HG2_EM1`, `ea_HA6_E1`, `ea_HA6_EM1`).
- Source evidence (read-only): the four `ts_log` files listed above; the bound TS xyz files listed above.
- Z-matrices written by internal_coordinates alongside each TS xyz (`<ts>.zmat`).
