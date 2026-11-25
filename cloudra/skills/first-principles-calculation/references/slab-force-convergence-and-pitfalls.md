# Slab Force Convergence, Egg-Box Diagnostics & Engine Pitfalls

Practical rules and failure-mode diagnostics for periodic metallic slab adsorption, coadsorption, and surface post-processing across plane-wave codes (VASP, Quantum ESPRESSO, CASTEP) and Gaussian/plane-wave (CP2K GPW).

---

## 1. Engine Selection: Plane-Wave vs. CP2K GPW on Metallic Slabs

- **Prefer plane-wave codes (VASP / Quantum ESPRESSO / CASTEP) for transition-metal slabs** (e.g., Ag, Cu, Au, Pt) requiring multi-k-point sampling, surface relaxation, adsorption energetics, or work functions. Plane-wave basis functions are independent of atomic positions and carry no localized-orbital Pulay overlap-derivative drift.
- **Reserve CP2K GPW for its native strength**: large-scale insulators, semiconductors, or explicit-solvent AIMD (hundreds to thousands of atoms, $\Gamma$-point, OT solver).
- **Known CP2K GPW failure modes on metallic slabs** (when using diagonalization + smearing + k-points):
  1. **False convergence (`Specific L-BFGS convergence`)**: CP2K's internal L-BFGS curvature/step trigger can exit cleanly and write `*-FINAL-*.xyz` while actual maximum atomic forces still exceed the `MAX_FORCE` target by $10\times$–$100\times$. Always verify native `ATOMIC FORCES` directly; never trust `FINAL` filenames or exit status alone.
  2. **Low-cutoff / $\Gamma$-point false minima**: A metallic slab relaxed to $< 0.03\ \text{eV/\AA}$ at `CUTOFF 420 / REL_CUTOFF 60 Ry` and $\Gamma$-point can exhibit $10\times$–$15\times$ force jumps ($0.15$–$0.38\ \text{eV/\AA}$) when evaluated at `600–900 Ry` or denser k-point meshes, and multi-eV total-energy shifts between $\Gamma$ and converged k-point grids.
  3. **MOLOPT overlap-derivative ($W$-matrix) history noise**: Under metallic smearing, rigid eigenvalue-zero shifts between wavefunction restarts perturb the energy-weighted density matrix $W = \sum_i f_i \epsilon_i C_i C_i^T$ and inject restart-history-dependent noise ($\sim 0.01\ \text{eV/\AA}$) through the Pulay overlap term $\text{Tr}(W\,\partial S/\partial R)$ even at `EPS_SCF = 1e-11`.
  4. **Mandatory CP2K safeguards when CP2K is used**:
     - Do not combine `SCCS` implicit solvation with k-points (unvalidated cavity-state hysteresis can shift $G_{\text{solv}}$ by several eV between nearly identical geometries).
     - Export charge density cubes for Bader analysis with `E_DENSITY_CUBE` `STRIDE 1 1 1` (default `STRIDE 2 2 2` breaks total electron count conservation) and verify integrated total electrons.
     - Always pair `DFTD3(BJ)` with an explicit `REFERENCE_FUNCTIONAL` (e.g., `PBE`).

---

## 2. Egg-Box Effect, Grid Consistency & Dipole-Cut Safety

Real-space FFT grids break continuous translational invariance (the **egg-box effect**), producing spurious grid-dependent forces and energy ripples as atoms move relative to grid points.

- **VASP**:
  - Use `PREC = Accurate` so fine augmentation grids (`NGXF/NGYF/NGZF`) avoid wrap-around and coarse-grid noise.
  - While `LREAL = Auto` accelerates large slabs, real-space projection is a primary source of egg-box force noise on flat metal surfaces, weak physisorption, and finite-difference Hessians. Switch to `LREAL = .FALSE.` for final force refinement, soft modes, or tight energy differences, and test `ADDGRID = .TRUE.` when finite-difference forces remain noisy (verify against a reference, as `ADDGRID` is not universally beneficial for every PAW potential).
- **CASTEP (constrained-force projection trap)**:
  - When bottom slab layers are frozen via `IONIC_CONSTRAINTS`, residual non-zero total $z$-force from the FFT grid ($\text{AllFz} = \sum_i F_{z,i}^{\text{raw}}$, often $+1.5$ to $+4.5\ \text{eV/\AA}$ even on fine grids) is projected uniformly onto mobile atoms as $-\text{AllFz}/N$ inside `Constrained Forces` (`Fcon`). This injects $\sim 0.10$–$0.15\ \text{eV/\AA}$ of artificial $z$-bias that can invert the true gradient and stall built-in BFGS/TPSD indefinitely.
  - **Fix & check**: Verify work-energy consistency ($-\sum \bar{\mathbf{F}} \cdot \Delta \mathbf{r} \approx \Delta E$) using the sum of raw force components (`Fraw`: Ewald + local + non-local + dispersion + external/dipole + DM correction). Drive fixed-bottom CASTEP slab relaxations with an external raw-force optimizer (e.g., L-BFGS calling `SinglePoint` with `.wfc` wavefunction reuse) rather than built-in `Constrained Forces`.
- **CP2K GPW**:
  - Test both energy **and maximum force** stability against `CUTOFF` and `REL_CUTOFF`; energy convergence alone does not guarantee force convergence. If `&XC_GRID` smoothing (`XC_SMOOTH_RHO` / `XC_DERIV`) is introduced, apply it identically across all compared states because it shifts absolute total energies.
- **Dipole-correction plane clearance & egg-box-free rigid shift**:
  - Before enabling self-consistent dipole corrections (`LDIPOL = .TRUE.` in VASP, `dipole_correction : SELFCONSISTENT` in CASTEP, `tefield`/`dipfield` in QE), verify that every atom sits well away from the periodic dipole discontinuity plane (typically $z = 0 / c$): enforce **`z_min > 5.0 Å` and `c - z_max > 5.0 Å`**. Density tails crossing the cut plane trigger catastrophic dipole and energy blow-ups.
  - If the slab must be shifted along $z$ to center it, translate all atoms rigidly by an **exact integer multiple of the fine FFT grid spacing**:
    $$\Delta z = \frac{k}{N_{z,\text{fine}}} c$$
    so every atom lands on an equivalent grid phase with zero egg-box energy offset.
- **Substrate corrugation contamination**:
  - If early coarse-grid or biased relaxation leaves non-physical ripples on the top metal layer (e.g., $\Delta z > 0.05\ \text{\AA}$ on a clean/weakly perturbed facet), transplant the adsorbate onto a flat symmetric slab and re-relax on the locked production fine grid.

---

## 3. SCF Reuse Noise Floor, External Optimizers & Optimizer Pitfalls

- **Decouple electronic-structure evaluation from built-in optimizers**:
  - Do not treat a DFT package's built-in geometry optimizer as mandatory when its internal force projection, line-search heuristic, or convergence trigger fights the chemistry (e.g., CASTEP's `Constrained Forces` projection bias or CP2K's `Specific L-BFGS convergence`).
  - Whenever native raw forces pass work-energy consistency ($-\sum \bar{\mathbf{F}} \cdot \Delta \mathbf{r} \approx \Delta E$) while the built-in optimizer stalls or misfires, treat the DFT code strictly as a `SinglePoint` energy-and-force evaluator (with wavefunction reuse) and drive the coordinates with a transparent external optimizer (such as a custom L-BFGS / damped-SD loop with explicit raw-force, energy, and step convergence guards).
- **Wavefunction-reuse false plateau (valley noise floor)**:
  - *Signature*: Near convergence ($|F|_{\max} \approx 0.05$–$0.08\ \text{eV/\AA}$), reused wavefunctions exit SCF in only `3–5` iterations, yet observed $\Delta E > 0$ while force prediction $\text{pred} < 0$ for consecutive steps and line searches repeatedly backtrack.
  - *Root cause*: Loose electronic tolerances terminate SCF before density mixing fully relaxes, leaving $0.02$–$0.03\ \text{eV/\AA}$ of non-self-consistent force noise.
  - *Fix*: Keep functional, cutoff, grid, and k-points identical; tighten electronic convergence by one order of magnitude (e.g., `2e-6 → 2e-7 eV` or `EDIFF 1e-6 → 1e-7`) and restart from a clean electronic guess (drop the stale wavefunction file). Do not waste steps shrinking the ionic step size first.
- **Quantum ESPRESSO polar large-vacuum slabs**:
  - *Charge sloshing*: Avoid `local-TF` with tiny smearing (`degauss ~ 0.002 Ry`) and active `dipfield` from step 0 on long-vacuum polar slabs. Use `mixing_mode = 'plain'`, `mixing_beta <= 0.20`, `smearing = 'mv'`, `degauss = 0.015 Ry`. Run geometry pre-relaxation without `tefield`/`dipfield`, then perform a two-step restart (`startingpot='file'`, `startingwfc='file'`) to turn on the dipole field for work-function/post-processing runs.
  - *Threshold mismatch*: Ensure `forc_conv_thr` is at least $2\times$–$5\times$ looser than the observed `Total SCF correction` force noise. Never bulk-edit `conv_thr` without word boundaries (accidentally rewriting `etot_conv_thr` and `forc_conv_thr` to `1.0d-8` makes ionic exit impossible).
- **Large-system pre-optimization & coadsorption staging**:
  - For 30–60+ atom slabs, pre-relax large geometric rearrangements on a fast plane-wave setup to $|F|_{\max} < 0.05\ \text{eV/\AA}$, then refine all final production numbers inside a single consistent engine/functional/grid baseline.
  - For coadsorption (e.g., adding an alkali/ion to a pre-adsorbed organic layer), avoid ad-hoc vacuum-side placement that creates unscreened radical/dipole artifacts. Scan periodic 3D cavities to place species in comparable interfacial regimes, relax in two stages (incoming species on frozen host $\to$ coupled adsorbate + active substrate layers), and run a single-point spin-polarized check on odd-electron/metallic coadsorbates to verify whether spin is quenched.

---

## 4. Dispersion, Reference States & Post-Processing Discipline

- **Unscreened pairwise dispersion on metallic bulk references**:
  - Do not apply unscreened pairwise dispersion models (e.g., TS2009, D2) to alkali or alkaline-earth bulk metals (such as BCC Li), where missing metallic screening overestimates $C_6$ and causes runaway cell collapse or non-physical $E_{\text{disp}}/\text{atom}$ ($> 1\ \text{eV/atom}$). Always run a 5–6 point fixed-volume EOS scan to verify a physical minimum before accepting any bulk metal reference.
- **Strict comparability & energy definitions**:
  - Never mix energies across engines, functionals, dispersion schemes, cutoffs, FFT grids, or pseudopotential versions. Pin static pseudopotential files (disable on-the-fly generation) and verify identical hashes across all directories in a comparison set.
  - Explicitly distinguish **frozen-geometry vertical interaction energy** $E_{\text{int}} = E(\text{tot}) - E(\text{host, frozen}) - E(\text{guest})$ (required for charge-density difference closure) from **relaxed adiabatic binding energy** $E_{\text{bind}} = E(\text{tot}) - E(\text{host, relaxed}) - E(\text{guest})$.
- **Charge-density difference (DCD) & Bader hygiene**:
  - Compute all three DCD subsystems (`tot`, `host`, `guest`) in the exact same cell with an **explicitly locked FFT grid** (e.g., identical `nr1, nr2, nr3` in QE) so cube subtraction requires zero interpolation.
  - In QE `pp.x`, use `plot_num = 0` (pseudo-valence density) for DCD visualization/integration, and `plot_num = 17` (PAW reconstructed all-electron density) as the `-ref` file for Henkelman Bader partitioning. Verify integrated electron count conservation ($|\Delta N_e| < 0.05\ e$).

---

## 5. Rapid Force-Convergence Decision Tree

```text
Slab relaxation stalls, oscillates, or gives suspicious convergence
 ├─ Dipole moment > 20 D or dipole energy jump > 1 eV?
 │   └─ Atom too close to z=0/c dipole cut -> rigid shift by Δz = (k / N_z_fine) * c so z_min > 5 Å and c - z_max > 5 Å
 ├─ CASTEP Fcon stuck at 0.10–0.25 eV/Å while |AllFz| > 1 eV/Å?
 │   └─ Constrained-force projection bias -> verify -Fraw·Δr vs ΔE and switch to external raw-force L-BFGS
 ├─ Force stuck at 0.05–0.08 eV/Å, SCF <= 5 steps, dE > 0 but pred < 0?
 │   └─ SCF reuse noise floor -> tighten electronic tolerance 10x and restart without stale wavefunction
 ├─ Converged top metal layer ripples > 0.05 Å or energy looks elevated?
 │   └─ Legacy coarse-grid/biased corrugation -> transplant adsorbate onto flat slab and re-relax on fine grid
 ├─ QE SCF energy blows up (> 1 Ry) or BFGS never exits?
 │   ├─ Blow-up -> switch to mixing_mode='plain', mixing_beta=0.20, smearing='mv', degauss=0.015; turn off tefield during pre-opt
 │   └─ Never exits -> check forc_conv_thr vs Total SCF correction (ensure forc_conv_thr is 2–5x looser)
 └─ CP2K exits in 2–4 L-BFGS steps, or forces jump > 0.1 eV/Å at higher cutoff / k-points?
     ├─ Inspect raw ATOMIC FORCES (beware Specific L-BFGS convergence false positive)
     └─ If metallic slab shows persistent cutoff/k-point force jump -> switch to a plane-wave engine
```

---

## 6. Post-Convergence Verification Checklist

Before accepting slab energies or structures into a final table:
1. **Native force & SCF verification**: Re-read raw native forces (not `CONVERGED`/`FINAL` filenames), confirm zero unconverged SCF warnings, and confirm ionic stopping criteria are genuinely met on mobile atoms.
2. **Geometry & spin sanity**: Confirm fixed-layer drift is zero, top-layer metal corrugation is physical, covalent bonds/protonation states are intact, and odd-electron coadsorbates have a single-point spin check.
3. **Baseline & conservation closure**: Confirm identical cutoff, FFT grid, k-points, functional/dispersion, and pseudopotentials across all compared directories; verify Bader electron count conservation and exact algebraic closure of any energy decomposition ($E_{\text{ads}} = E_{\text{int}} + E_{\text{lat}}$).
