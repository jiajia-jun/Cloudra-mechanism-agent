---
name: first-principles-calculation
description: Provide domain expertise for periodic DFT / first-principles calculations (VASP, CP2K, Quantum ESPRESSO, ASE). Use when setting up INCAR parameters, optimizing k-points and ENCUT, configuring DFT+U, calculating surface slabs, adsorption energies, heterogeneous catalysis mechanisms (LH/ER/MvK), electrocatalytic CHE free energy diagrams (HER, OER, ORR, CO2RR, NRR), CI-NEB surface transition states, partial Hessian vibrations, or troubleshooting SCF/ZBRENT/EDDAV errors.
---

# 1. Local Toolchain Mapping (Toolchain Mapping)
When planning and executing periodic first-principles calculations (VASP / CP2K), anchor all actions in the `CLOUDRA` toolchain:

## 1.1 VASP Toolchain & Python Automation
- **Configuration generation and crystal modeling**: Rely on the ASE (Atomic Simulation Environment) library. Write Python automation scripts using `ase.io`, `ase.build` (`bulk`, `surface`, `add_adsorbate`), and `FixAtoms` constraints. Avoid blindly hand-typing POSCAR coordinates or concatenating raw text with shell `echo`.
- **Extended methodology & reference library**: Before starting surface modeling, reaction network construction, or production runs, load the detailed reference guides:
  - Surface & Slab Modeling SOP: `get_skill("first-principles-calculation", reference="surface-modeling-sop.md")` (bulk lattice relaxation, slab thickness/vacuum convergence, Tasker surface polarity, adsorption site catalogs, and adsorbate placement rules).
  - Heterogeneous Catalysis & CHE Electrocatalysis: `get_skill("first-principles-calculation", reference="heterogeneous-catalysis-mechanisms.md")` (LH/ER/MvK models, CHE standard free energy corrections, HER/OER/CO2RR/NRR reaction networks, scaling relations, and CI-NEB / Partial Hessian SOP).
  - Production INCAR / CP2K Blueprints & Troubleshooting: `get_skill("first-principles-calculation", reference="vasp-cp2k-production-blueprints.md")` (bulk opt, slab relaxation, PDOS/d-band center, DFT+U table, HSE06 two-stage acceleration, and failure diagnosis decision trees).
  - ASE code library: `get_skill("first-principles-calculation", reference="ase-guide.md")` and `examples/` (`adsorption_energy.py`, `lattice_optimization.py`, `neb_barrier.py`, `che_electrocatalysis.py`).
- **Job submission**: Submit compute tasks via `submit_compute_job` with `job_type="vasp"`. Set `is_async=True` for long relaxation, DOS, or NEB jobs.
- **Result parsing and monitoring**: Avoid running `cat` on giant `OUTCAR` or `vasprun.xml` files. Use Python scripts (`ase.io.read`, `pymatgen`, or regex log parsers) via `bash` to extract energies, forces, magnetic moments, and stress tensors.

## 1.2 CP2K Toolchain
- **Input generation**: Use Multiwfn or ASE's `CP2K` calculator for `.inp` files. For 2D surface slabs, strictly use `&POISSON` with `PSOLVER MT` (Martyna-Tuckerman) and `PERIODIC XY`.
- **Job dispatch**: Call `submit_compute_job` with `job_type="cp2k"`.
- **Result parsing**: Monitor `SCF run converged`, total energies, and `MAX gradient` in `.out` files. Read slices using `read` or parse with Python.

---

## 2. Starting Values & Convergence Gates (not universal laws)

Numeric settings below are **production starting points**. A number is accepted only when its **convergence metric** is met and recorded; if the metric fails, stop and do not deliver that quantity.

1. **Slab & Vacuum Dimensions**:
   - For 2D materials, surface slabs, and adsorption systems, the vacuum-direction (usually $Z$) k-point **must be 1** (e.g. `4 4 1` or `5 5 1`).
   - **Start** vacuum at $15\text{–}20\text{ \AA}$; accept a smaller vacuum (metals often OK at $12\text{–}15\text{ \AA}$) only if electron density in the vacuum center decays to $< 10^{-5}\ e/\text{\AA}^3$ **and** the electrostatic potential plateaus ($V(z)$ flat within a few meV). Otherwise increase vacuum.
2. **Selective Dynamics on Slabs**:
   - **Start** with $\ge 4$ atomic layers for close-packed metals and $\ge 6$ for oxides/2D (system-dependent). Fix the bottom $2$ layers (more if needed); relax the rest and adsorbates. **Acceptance:** forces on fixed layers stay small and key observables (lattice parameter of the slab, $E_{\text{ads}}$, barrier) change $\lesssim 0.05$ eV when adding another relaxed layer or extending vacuum — otherwise thicken.
3. **Dipole Correction**:
   - Asymmetric slabs (different top/bottom terminations) and single-sided adsorption models **enable dipole correction** (`LDIPOL = .TRUE.`, `IDIPOL = 3`). Symmetric slabs usually omit it; report the choice.
4. **Smearing (ISMEAR) Selection**:
   - **Metals / semimetals**: start `ISMEAR = 1` or `2`, `SIGMA = 0.1 ~ 0.2 eV`. **Gate:** `entropy T S` $< 1\text{ meV/atom}$ (tighten SIGMA or switch method if not).
   - **Semiconductors / insulators**: `ISMEAR = 0` (Gaussian, `SIGMA = 0.05 eV`) for relaxation; `ISMEAR = -5` for high-accuracy static DOS/single points on gapped systems.
5. **POTCAR Ordering & Concatenation**:
   - Concatenate strictly in the elemental order declared in the `POSCAR` header. Never mix pseudopotential versions or LDA/GGA families. Record the POTCAR set in the delivery.
6. **Strongly Correlated Systems (DFT+U)**:
   - For open-shell $3d$ TM oxides/sulfides and $4f$ systems, plain GGA often underestimates gaps/localization — **default to DFT+U** (`LDAU=.TRUE.`, `LDAUTYPE=2`, `LMAXMIX=4` for d, `6` for f).
   - **Do not reuse a U table blindly.** Cite the U source for **this system / oxidation state / property** (literature or a documented U-raster). Report U values and a short sensitivity note when barriers or $E_{\text{vac}}$ matter (U shifts can exceed 0.5 eV). Blind table reuse is not delivery-grade.

### 2.1 Accept / refuse gates (periodic analog of the molecular SOP)

| Observation | Action |
| --- | --- |
| Vacuum $V(z)$ not flat / density not decayed | Increase vacuum; do not deliver $E_{\text{ads}}$ or barriers. |
| Slab thickness not converged | Thicken; do not quote absolute surface energies. |
| CI-NEB end states not at minima, or climbing image has 2+ significant imaginaries in the PHVA subspace | Fix path/ends first; do not quote a barrier. |
| Polar Tasker III surface without compensation | Model compensation or refuse that surface energy. |
| Functional / U / dispersion outside session method policy | Fail closed; do not “improve” the method silently. |
| CO/CO₂/O₂ empirical correction needed but scheme/functional mismatched | Do not apply a foreign offset; state the scheme or refuse the thermodynamic cycle. |

**Literature-backed judgment:** for U values, empirical corrections, and scaling relations, search literature (researcher) before inventing numbers. Record functional + correction scheme in every thermodynamic cycle.

---

## 3. Scientific Knowledge Base

### 3.1 Bulk Lattice Optimization & Two-Pass Protocol
- **Pulay Stress**: Plane-wave basis truncation at varying cell volume creates an unphysical inward stress.
- **Protocol**: Execute a two-stage relaxation: Step 1 coarse `ISIF=3` ($\text{ENCUT} \ge 1.3 \times \text{ENMAX}$); copy `CONTCAR` to `POSCAR`, reset wavefunction, and run Step 2 fine `ISIF=3`. Verify external pressure $|P| < 0.5\text{ kbar}$ and volume change $\Delta V/V < 0.1\%$.

### 3.2 Surface Energy & Wulff Construction
- **Stoichiometric surface energy**: $\gamma = \frac{E_{\text{slab}} - N_{\text{bulk}} E_{\text{bulk}}}{2A}$.
- **Non-stoichiometric surfaces**: $\gamma(\mu_O)$ depends on oxygen chemical potential bounds $\frac{1}{y}\Delta H_f(M_xO_y) \le \mu_O - \frac{1}{2} E_{O_2} \le 0$.
- **Wulff Equilibrium Morphology**: Distances from center to facet $(hkl)$ scale as $d_{hkl} \propto \gamma_{hkl}$.

### 3.3 Adsorption Energy & Thermochemical Corrections
- **Adsorption Energy**: $E_{\text{ads}} = E_{\text{slab+adsorbate}} - E_{\text{slab}} - E_{\text{adsorbate(gas)}}$ ($E_{\text{ads}} < 0$ is exothermic).
- **Free Energy Correction**: $G = E_{\text{DFT}} + \text{ZPE} - T S_{\text{vib}} + E_{\text{solv}}$.
  - Adsorbates lose translation/rotation; only calculate vibrational entropy $S_{\text{vib}}$ using partial Hessian analysis.
  - Apply quasi-RRHO cutoff ($100\text{ cm}^{-1}$) for low-frequency modes to prevent entropy divergence ($\nu \to 0$).

### 3.4 Electrocatalytic Computational Hydrogen Electrode (CHE) Model
- **Electrochemical Potential Coupling**: $\mu(\text{H}^+ + \text{e}^-) = \frac{1}{2} \mu(\text{H}_2(\text{g})) - eU$.
- **Standard Gibbs Free Energy Step**:
  $$\Delta G(U) = \Delta E_{\text{DFT}} + \Delta \text{ZPE} - T\Delta S - neU + \Delta G_{\text{pH}} + \Delta G_{\text{solv}}$$
- **Gas-Phase Reference Artifacts (scheme-specific — never “universal offsets”)**:
  - **$\text{O}_2$ triplet overbinding**: Never use computed gas-phase $\text{O}_2$ energy directly on the DFT surface. One common water-splitting anchor is $G(\text{O}_2) = 2 G(\text{H}_2\text{O}(\text{l})) - 2 G(\text{H}_2) + 4.92\text{ eV}$ — **state that you used this scheme**; other experimental anchors exist.
  - **$\text{CO} / \text{CO}_2$ gas errors**: Literature empirical shifts (e.g. $E_{\text{CO}} \leftarrow E_{\text{DFT}} - 0.33\text{ eV}$; $E_{\text{CO}_2} \leftarrow E_{\text{DFT}} + 0.45\text{ eV}$) are **PBE-era values**. Use only when the functional/scheme matches the source; otherwise re-derive or refuse the cycle. Always print the functional and the correction in the report.
- **Scaling Relations (associative CHE assumption)**:
  - OER intermediate scaling $\Delta G_{*\text{OOH}} = \Delta G_{*\text{OH}} + 3.20\ (\pm 0.20)\text{ eV}$ and $\eta_{\text{min}} = 0.37\text{ V}$ hold for **associative** OER pathways where that linear relation is valid. Lattice-oxygen / broken-scaling mechanisms (MvK) can violate it — do not treat 0.37 V as a universal ceiling without checking the pathway.

### 3.5 Surface Transition States: CI-NEB & Partial Hessian
- **Climbing Image NEB (CI-NEB)**: Interpolate initial path using IDPP across 4–8 images. Enable `LCLIMB = .TRUE.` and `SPRING = -5.0` with VTST optimizers (`IOPT = 1`, L-BFGS).
- **Partial Hessian Frequency Verification (`IBRION=5`)**: Fix all substrate atoms (`F F F`); unfreeze only adsorbate atoms and coordinating surface atoms (`T T T`). Verify **exactly one significant imaginary frequency in the PHVA subspace** whose eigenvector aligns with the reaction coordinate (this is not a full-crystal Hessian claim).

---

## 4. Agent Workflow: End-to-End First-Principles Pipeline

```
[Step 1: Bulk Optimization] ──> ISIF=3, Two-pass relaxation, EOS Birch-Murnaghan fit
       │
       ▼
[Step 2: Slab Cleaving]    ──> Cleave (hkl), check Tasker polarity, add 15-20 Å vacuum, fix bottom layers
       │
       ▼
[Step 3: Adsorption Search] ──> Test Top/Bridge/Hollow sites, compute E_ads, ZPE, and d-band center
       │
       ▼
[Step 4: Catalytic Pathways]──> Build reaction network (LH / ER / MvK or CHE HER/OER/CO2RR/NRR steps)
       │
       ▼
[Step 5: TS & CI-NEB]       ──> Align IS/FS, IDPP interpolate, CI-NEB climb to saddle, IBRION=5 partial Hessian
```

- **Step 1: Bulk Optimization**: Establish true ground-state lattice constants and volume.
- **Step 2: Surface Cleaving & Convergence**: Select stoichiometric/symmetric slabs where possible. Confirm slab thickness convergence ($\Delta d_{\text{center}} < 0.5\%$) and vacuum potential flatness.
- **Step 3: Adsorption Exploration**: Place adsorbates with proper initial angles/bonds (see `surface-modeling-sop.md`). Identify the global minimum binding site and compute $E_{\text{ads}}$.
- **Step 4: Reaction Energy Profile**: For thermal catalysis, compute reaction energies $\Delta E$ and surface coverage; for electrocatalysis, compute CHE free energy steps $\Delta G(U)$ and theoretical overpotentials $\eta$.
- **Step 5: Barrier & Saddle Verification**: Run CI-NEB between initial and final states; confirm the saddle point with `IBRION=5` partial Hessian analysis.

---

## 5. Diagnostics & Troubleshooting Decision Trees

When a VASP/CP2K calculation fails or diverges, follow this diagnosis hierarchy:

1. **`EDDAV: Error #2` (Subspace rotation / orthogonalization failed)**:
   - Check `POSCAR` for overlapping atoms ($d_{ij} < 0.8\text{ \AA}$) or PBC wrapping errors.
   - Run 10 electronic steps with `ALGO = Normal` / `Exact` to stabilize initial subspace, then switch to `ALGO = Fast`.
2. **`ZBRENT: fatal error in bracket` (Ionic 1D line search failed)**:
   - Gradient is too steep or step is too large. Reduce `POTIM` to `0.1` or `0.05`. Revert `IBRION = 1` (RMM-DIIS) back to `IBRION = 2` (CG).
3. **Electronic SCF Divergence / Oscillation**:
   - *Charge sloshing in slabs/metals*: Set `AMIX = 0.2`, `BMIX = 0.0001`.
   - *Spin oscillation in magnetic systems*: Set `AMIX_MAG = 0.8`, `BMIX_MAG = 0.0001`, ensure `LMAXMIX = 4` or `6`.
   - *Algorithm fallback*: Switch `ALGO` from `Fast` $\to$ `Normal` $\to$ `All`.
   - *Corrupt wavefunctions*: Delete `WAVECAR`/`CHGCAR` and restart with `ISTART = 0, ICHARG = 2`.
4. **Out-of-Memory (OOM) / SIGKILL**:
   - Reduce `KPAR` (e.g. from 4 to 2 or 1) to conserve RAM per node.
   - Enable `LREAL = Auto` to reduce plane-wave projection memory.
   - Set `PRECFOCK = Fast` for HSE06 calculations.

---

## 6. Reference Document Index

Load domain references as needed:
- `surface-modeling-sop.md`: Detailed surface cleavage, Tasker rules, slab thickness/vacuum convergence, and adsorbate placement rules.
- `heterogeneous-catalysis-mechanisms.md`: LH, ER, MvK mechanisms, CHE electrocatalysis equations, gas-phase thermodynamic corrections, scaling relations, and CI-NEB / partial frequency SOP.
- `vasp-cp2k-production-blueprints.md`: Production INCAR / CP2K .inp parameter templates, d-band center calculations, and failure diagnosis tables.
- `ase-guide.md` & `examples/`: Code libraries for ASE crystal modeling, adsorption energy, EOS lattice fitting, CI-NEB barriers, and CHE free energy calculators.
