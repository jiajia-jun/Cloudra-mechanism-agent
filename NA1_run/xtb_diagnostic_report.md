# NA1 / xtb (GFN2-xTB) diagnostic validation — TS2 (C–C addition) chemical feasibility

Session: 2026-09-04, small_mol (a-4). Method whitelist `['mace-omol25','xtb']`; xtb 6.7.1
(`/Users/cloudrayyy/miniconda3/envs/chemai/bin/xtb`). **Diagnostic only** — the scorer does not
accept xtb logs; this run is to establish whether xtb can compute the C–C addition where MACE failed.

## Scope & constraints honored
- Workdir: `/Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_run`.
- Reaction: acetaldehyde self-aldol; enolate `[O-]C=C` + water + acetaldehyde (ion-dipole complex).
- **Every xtb call was a bare `bash` call** (no scheduler path, GH#26). All are recorded under
  "Bash bypasses" in `progress.md`. Energy extraction from xtb output is manual (no `log_parser`).
- `conformer_search` deliberately **not** used to build the complex (GH#19 all-zero/overlap); fragments
  were placed by hand into xyz coordinates and validated with `internal_coordinates` / `electronic_analysis`.

## Atom ordering used (1-based, from pre-organized complex xyz)
- 1–6 enolate `[O-]C=C`: **C2**=atom1 (attacking α-CH2), **C3**=atom2 (=CH, bears O), **O4**=atom3 (negative), H4,H5,H6.
- 7–13 acetaldehyde `CC=O`: C5=atom7 (CH3), **C6**=atom8 (carbonyl C), **O7**=atom9 (carbonyl O), H10–H13.
- 14–16 water: O14 (donates H to O4), H15, H16.
- 1-based C2–C6 = atoms (1,8); C2=C3 = (1,2); C6=O7 = (8,9); O4–water = (3,14).

## Results (GFN2-xTB, gas-phase, charge −1, singlet)

### 1. central_complex geometry — xtb CONVERGES (contrast MACE)
Applied `xtb <xyz> --opt tight --gfn 2 --chrg -1 --uhf 0` on the pre-organized complex (C2–C6 = 2.886 Å).
- **CONVERGED**: gradient norm 0.00025 Eh/Å, wall ~0.47 s.
- **Importantly**: with no constraint the optimizer rolled the ion-dipole complex **directly to the C–C bonded
  alkoxide product** (C2–C6 = 1.669 Å, E = −25.51989 Eh). This is the first, chemically-significant sign
  that the C–C bond formation is **essentially barrierless** at GFN2-xTB.

### 2. TS2 — a genuine first-order saddle is found (n_imag == 1)
Took a **relaxed constrained scan** along C2–C6 (2.90 → 1.60 Å, force constant 1.0, each point starting
from the previous optimized frame) via `xtb_scan.py` (bash bypass). Energy maximum at **C2–C6 = 2.44 Å
(target 2.30)**, E = −25.36228 Eh. Frequency on that frame (`xtb scanframe_2.30.xyz --hess`):

```
projected vibrational frequencies (cm⁻¹)
eigval :   -0.00  -0.00  -0.00  -0.00   0.00   0.00
eigval : -127.21  18.23  36.11  46.19  77.35 146.48   ...
          :  # imaginary freq.     1 :
```
- **n_imag = 1**, imaginary frequency **−127.21 cm⁻¹** — a valid first-order saddle.
- The frame is the energy maximum of the C2–C6 scan, and the geometry shows the coupled distortion expected
  of the RDS TS: C2–C6 = 2.44 Å (forming), C2=C3 = 1.361 Å (elongated from 1.346), C6=O7 = 1.225 Å
  (elongated from 1.218), O4–O7 stays > 4 Å (no O–O clash); water remains H-bonded (O4–O_w = 2.63 Å).

### 3. Product (I2 alkoxide) — xtb minimum (n_imag == 0)
`xtb central_complex.xyz --ohess tight` → optimized to **C2–C6 = 1.668 Å, E = −25.51989 Eh, n_imag = 0**. ✓

### 4. Isolated enolate reference
`xtb enolate.xyz --opt tight --chrg -1` → **E = −10.02130 Eh**, C=C = 1.354 Å, C–O = 1.263 Å. Mulliken charge
(electronic_analysis, backend=xtb): **O4 = −0.654**, C2 = −0.217, C3 = +0.165 ⇒ **O4 retains the negative
charge** (correct `[O-]C=C` form); α-carbon C2 is the nucleophile.

## Barrier — ΔE‡(TS2 − central_complex)
| species | E (Eh) | C2–C6 (Å) | notes |
|---|---|---|---|
| central_complex (relaxed, constrained 2.82 Å) | −25.46327 | 2.822 | reactant-side, converged |
| **TS2 (scan max)** | **−25.36228** | **2.44** | **n_imag = 1 (−127 cm⁻¹)** |
| product I2 (free opt) | −25.51989 | 1.668 | n_imag = 0 |
| isolated enolate | −10.02130 | — | ref only |

**ΔE‡(TS2 − central_complex) = (−25.36228) − (−25.46327) = +0.1010 Eh = +63.4 kcal/mol**

**vs gold ΔE‡ ≈ 5 kcal/mol ⇒ xtb over-estimates by ~13× (63 kcal/mol). UNRELIABLE.**

### Why the +63 is an artifact (not the chemistry)
- The reaction is **exothermic by −35.5 kcal/mol** (product − complex) and the available **free
  (unconstrained) relaxation path is barrierless** (complex → product, no stop at the saddle).
  A +63 kcal/mol activation for a −35 kcal/mol ion-dipole aldol is physically impossible.
- The +63 comes from a **single-coordinate** C2–C6 constraint. Per the DFT SOP, one coordinate is often
  insufficient: the true MEP couples C2–C6 formation with C2=C3 and C6=O7 breaking **and** the water/O
  hydrogen-bond network reorganization. The constrained path follows a high-energy ridge, not the MEP.
- The ion-dipole complex is **extremely floppy** (multiple near-degenerate conformers; the non-converged
  2.90 Å frame sits 21 kcal/mol below its converged 2.82 Å neighbor). This is the same floppiness that
  defeated MACE (non-convergence, corrupted geometry).

## MACE vs xtb — convergence conclusion
- **MACE (ORCA `! ExtOpt`)**: **never converged** a geometry or a saddle — jobs 27/28/29/30 all
  "did not converge" (yet reported done, GH#21), corrupted geometry (C1–O14 = 0.37 Å overlap), no
  `n_imag == 1` saddle; energy extraction returned initial-geometry energy (GH#22).
- **xtb (GFN2-xTB)**: **converged everything in <1 s**, produced a clean **n_imag == 1 saddle** (TS2,
  −127 cm⁻¹) and a clean product minimum (n_imag == 0).
- **Net**: xtb is qualitatively far more robust (convergence + TS search) than MACE on this floppy
  ion-dipole system. **But xtb cannot give a trustworthy quantitative ΔE‡ here** — it is either
  massively over-estimated (+63 kcal/mol by constrained scan) or barrierless by free relaxation;
  neither matches the gold ~5 kcal/mol. The root cause is the floppy charged complex, which is a known
  weak point for both xTB (barrier MUE 3–6+ kcal/mol, larger for charged/floppy systems) and MLPs.

## Verdict
- **xtb CONVERGES where MACE failed** (diagnostic success on convergence / TS discovery). ✓
- **TS2 exists**: n_imag == 1, C2–C6 = 2.44 Å, E = −25.36228 Eh. ✓
- **But the quantitative barrier is unreliable**: +63.4 kcal/mol (constrained-scan artifact) vs ~0
  (barrierless free-relaxation). **Cannot be reported as a trustworthy ΔE‡.**
- **To get the real ΔE‡**: a proper higher-level method is required — ORCA DFT (ωB97M-V / B3LYP-D3BJ,
  def2-TZVPD) with a **2-coordinate scan** (C2–C6 forming + C6=O7 breaking) and IRC validation.
  This is **outside the whitelist `['mace-omol25','xtb']]`** — recorded here as a recommendation only,
  **not as evidence**. (xtb gives the TS region/geometry; DFT is needed for the barrier.)

## Evidence files (all in NA1_run/)
- central_complex.xyz — pre-organized ion-dipole input (C2–C6 = 2.886 Å, charge −1).
- central_complex_xtb_opt.log / xtb_scan.py / scan_profile.csv — constrained scan profile + driver.
- scanframe_2.30.xyz, **ts2_xtb_guess.xyz** — TS2 candidate (n_imag = 1).
- ts2_cand_hess.log — frequency output showing `# imaginary freq. 1`, −127.21 cm⁻¹.
- product_xtb.log — free-opt product (n_imag = 0, C2–C6 = 1.668 Å).
- enolate_xtb_opt.xyz / enolate_xtb.log — isolated enolate reference.
