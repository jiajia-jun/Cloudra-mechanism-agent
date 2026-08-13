---
name: first-principles-calculation
description: Provide domain expertise for periodic DFT / first-principles calculations (VASP, CP2K, Quantum ESPRESSO). Use when setting up INCAR parameters, optimizing k-points and ENCUT, configuring DFT+U, calculating surfaces/adsorption, troubleshooting SCF convergence, or handling charged periodic systems (background charge / Makov-Payne / PSOLVER), CP2K input generation, and CP2K convergence tuning order.
---

# 1. Local toolchain mapping (Toolchain Mapping)
When planning and running periodic first-principles calculations (VASP / CP2K), rely on the `CLOUDRA` local environment:

## 1.1 VASP toolchain
- **Config generation and structure operations**: prefer the ASE (Atomic Simulation Environment) library. Write lightweight Python scripts using ASE `ase.io` and the corresponding Calculators to automate crystal structures and generate POSCAR, INCAR, KPOINTS. Avoid blindly hand-typing and concatenating input files with shell `echo`, which easily omits parameters and introduces typos; for extremely simple single-point tests or one-off debugging, it may be used with care.
- **Required reading before writing ASE scripts**: do not recite the ASE API from memory. First obtain the full code-pattern library via `getskill("first-principles-calculation", other="ase-guide.md")` (bulk/surface/adsorbate modeling, FixAtoms constraints, Vasp/GPAW calculators, BFGS/MD/NEB, structure validation and debugging), and inspect runnable complete scripts under `examples/` via `getskill("first-principles-calculation", other="examples")` (adsorption energy `adsorption_energy.py`, lattice optimization `lattice_optimization.py`, NEB barrier `neb_barrier.py`), then adapt them. For a cheat sheet use `other="ase-quick-reference.md"`.
- **Job submission**: always call `submit_compute_job` with `job_type` set to `vasp`. VASP jobs are usually very long; set `is_async=True`.
- **Result parsing and status monitoring**: avoid `cat` on a huge `OUTCAR`. Prefer a local log parser or Python to parse `vasprun.xml` / `OUTCAR` (final energy, ionic steps, magnetic moments); for a quick convergence check, read the tail summary of OUTCAR.

## 1.2 CP2K toolchain
- **Input generation**: prefer **Multiwfn** for conveniently creating CP2K `.inp` files (recent versions; detailed tutorial at `sobereva.com/587`). Its defaults (e.g. `EPS_SCF 2.0E-06`, `MAX_SCF 128`, OT vs diagonalization, `&OUTER_SCF`) are suitable for most systems; **do not randomly change them if you do not know CP2K**. Generating with ASE’s `CP2K` calculator is also fine, but the defaults fit real systems less well than Multiwfn.
- **Job submission**: call `submit_compute_job` with `job_type` `cp2k` (input is a `.inp` file); long jobs `is_async=True`.
- **Result parsing**: in CP2K `.out` files watch `SCF run converged` / `*** WARNING ... SCF run NOT converged ***`, `Total energy`, and geometry-step `MAX gradient` / `MAX force`; read in slices with `text_reader` or parse with Python regex. Do not `cat` the whole file (large-system `.out` can be hundreds of MB).

# 2. Constraints and exceptions (Constraints & Exceptions)
The following are common VASP best practices, with reasonable exceptions in specific settings. When they conflict, prefer **convergence tests on the current system and literature convention**.

1. **K-point dimension limit**: for 2D materials, surfaces, or slab models, the vacuum-direction (usually Z) k-point **should usually be 1** (e.g. `5 5 1`). Only some interlayer-coupling properties may need a small increase.
2. **Smearing (ISMEAR) choice**:
   - **Metals / semimetals**: usually `ISMEAR = 1` or `2` (Methfessel–Paxton), `SIGMA` 0.1–0.2 eV, and check that `entropy TS` is < 1 meV/atom.
   - **Larger-gap semiconductors / insulators**: for high-accuracy single-point energy / DOS prefer `ISMEAR = -5` (tetrahedron method), which requires at least 4 k-points to form tetrahedra.
   - **Small-gap semiconductors or unknown-gap systems**: when k-points are sparse and the VBM/CBM crossing the Fermi level causes SCF oscillation or a jagged band structure, use `ISMEAR = 0` (Gaussian) with a small `SIGMA` (0.03–0.05 eV) to stabilize, then extrapolate to σ→0 if needed. This is the physical basis of ChemBench-style “small artificial smearing and extrapolate to zero smearing”.
   - If the system is known to be an insulator/semiconductor and k-points are sufficient, prefer `ISMEAR = -5` over Gaussian smearing.
3. **POTCAR concatenation limit**: when merging POTCARs, concatenate in POSCAR element order; do not scramble. Do not mix POTCAR versions.
4. **Strongly correlated systems (DFT+U)**: when the system contains **open-shell transition-metal oxides/sulfides or rare-earth/lanthanide compounds**, plain GGA (e.g. PBE) usually underestimates correlation — **evaluate** turning on `LDAU = .TRUE.`. For elemental metals, simple intermetallics, or main-group systems, +U is usually unnecessary.

# 3. Scientific knowledge base (Scientific Knowledge Base)

## 3.1 Cutoff energy and smearing
- **ENCUT**:
  - Routine geometry optimization (fixed volume): ENCUT at 1.0–1.3 × the highest `ENMAX` among element POTCARs is usually enough; confirm with a convergence test.
  - **Cell-volume optimization (ISIF=3)**: VASP officially recommends ENCUT ≥ 1.3 × max(ENMAX) to reduce Pulay stress. If resources allow, raise to 1.5× or run an ENCUT convergence test.
  - Note: an excessively large ENCUT wastes compute and can cause pseudopotential errors such as `PSMAXN too small`.
- **ISMEAR and SIGMA**:
  - **Metals**: `ISMEAR = 1` or `2`, `SIGMA` 0.1–0.2.
  - **Semiconductors / insulators**: default `ISMEAR = 0`, `SIGMA = 0.05`; you may also try `ISMEAR = -5` first.
  - **High-accuracy single-point energy / DOS**: use `ISMEAR = -5` (tetrahedron method). If the gap is very small, SCF is hard to converge, or k-points are extremely sparse, switch to `ISMEAR = 0` with a small SIGMA, then extrapolate to zero smearing.
  - **Unknown gap**: VASP officially recommends starting high-throughput / first-pass jobs with `ISMEAR = 0` + `SIGMA = 0.03–0.1`, then switching to a more accurate method once stable.

## 3.2 Strongly correlated systems (DFT+U)
- **Parameter setup (`LDAUTYPE=2`)**: `LDAUL`, `LDAUU`, `LDAUJ` must follow POSCAR element order.
- **LMAXMIX**: after adding U, you must set `LMAXMIX = 4` (d electrons) or `6` (f electrons) so spatial mixing is correct; otherwise it is easy to fall into a metastable state.

## 3.3 k-point mesh and Brillouin-zone sampling
- **Hexagonal/trigonal lattices, 2D materials**: prefer **Γ-centered + odd k-points** (e.g. `11 11 1`, `13 13 1`). A Monkhorst–Pack even mesh may miss Γ or the high-symmetry K point, causing periodic numerical oscillation along Γ–K.
- **Orthogonal/cubic lattices**: Monkhorst–Pack and Γ-centered are both fine; usually follow energy/stress convergence tests.
- **Undersampling vs mesh type vs smearing**:
  - Oscillation clearly shrinks or vanishes after densifying k-points → undersampling; keep increasing density.
  - Oscillation lessens but does not vanish after densifying k-points, the gap is large, and the oscillation looks like a periodic mesh artifact along a high-symmetry direction → more likely mesh type or lattice symmetry; try a Γ-centered odd mesh.
  - Small-gap / near-metal systems show jagged oscillation near the Fermi level that survives denser k-points → prefer Gaussian/Methfessel–Paxton smearing and extrapolate to zero smearing rather than immediately changing the mesh. This is the physical basis of ChemBench-style “small artificial smearing and extrapolate to zero smearing”.

## 3.4 Slab models and adsorption
- **Vacuum thickness**: at least 15 Å; for highly polar or long-range-interaction systems, 20 Å or more is recommended.
- **Dipole correction**: for one-sided adsorption or asymmetric top/bottom surfaces, enable `LDIPOL = .TRUE.` and `IDIPOL = 3`.
- **Dispersion correction**: adsorption energies usually need dispersion; prefer DFT-D3(BJ) (`IVDW = 12`).

## 3.5 Hybrid functionals and HSE06
- **When to use**: HSE06 / PBE0 mainly correct the band gap and improve electronic localization. **They do not remove k-point sampling artifacts**.
- **Order of use**: first optimize with GGA and test k-point convergence, then compute HSE06 single points / bands.
- **Key parameters (VASP)**: `LHFCALC = .TRUE.`, `HFSCREEN = 0.2`, `AEXX = 0.25`; `ALGO` commonly `Damped` or `All`; you may read PBE `WAVECAR`/`CHGCAR` as the initial guess.
- **Note**: hybrids are far more expensive than GGA and demand denser k-points.

# 4. Agent workflow: VASP calculation pipeline (Workflow State Machine)
**Step 1: Structure setup and K/E convergence tests**
- Prefer online crystal databases (e.g. Materials Project) for a base CIF, then read and process with ASE.
- Before production, write an ASE-based automation script to sweep ENCUT and KPOINTS (criterion: energy change < 1–2 meV/atom).

**Step 2: Geometry optimization (Relaxation)**
- Choose `ISIF` by system:
  - `ISIF=2`: in-plane optimization of slabs or 2D materials (fixed volume).
  - `ISIF=3`: full optimization of 3D bulk materials.
- If there are unpaired electrons (especially transition metals), you must enable spin polarization (`ISPIN=2`) and assign a reasonable initial magnetic moment (`MAGMOM`).

**Step 3: High-accuracy calculation (Static/DOS/Band)**
- After optimization, extract `CONTCAR` over `POSCAR`.
- Set `NSW` to 0 and `ISMEAR=-5` for a high-accuracy single-point calculation.

# 5. Diagnostics and circuit breakers (Circuit Breakers)
When VASP electronic steps (SCF) diverge or hit `NELM` without converging, diagnose as follows:
1. **Collapsed structure**: check whether the first ionic-step energy is absurdly large (e.g. 1E5 eV). If so, atoms overlap badly; stop immediately and recheck the structure-modeling code.
2. **Mixing-parameter adjustment (the killer move for metals/magnetic systems)**:
   - Dynamically change INCAR: `AMIX = 0.2`, `BMIX = 0.0001`, `AMIX_MAG = 0.8`, `BMIX_MAG = 0.0001`.
3. **Smearing adjustment**: for metals, temporarily raise `SIGMA` (e.g. 0.2), then after a coarse convergence read `WAVECAR` and rerun with a smaller value.
4. **Algorithm downgrade**: drop `ALGO` from `Fast` to `Normal`; if it still diverges, try `All` or `Damped`.
*Important: if the above still diverges after 2 attempts, you must stop calling and report to the user.*

# 6. CP2K essentials and common pitfalls
The following is synthesized from hands-on experience on the Computational Chemistry Community (bbs.keinsci.com) and Thinker's Club (sobereva.com). When a CP2K job fails, diagnose in this section’s order.

## 6.1 CP2K input and basic parameters
- **Basis and pseudopotential must be paired**: in CP2K, MOLOPT bases and GTH pseudopotentials are used together (`.inp` `&KIND` must give both `BASIS_SET` and `POTENTIAL`).
  - Routine accuracy: `DZVP-MOLOPT-SR-GTH`; high accuracy / interaction energies: `TZV2P-MOLOPT-GTH` (BSSE is small; counterpoise is usually unnecessary).
  - **Do not use the old `TZV2P-GTH`** (not the MOLOPT family) — outdated and clearly worse.
- **CUTOFF / REL_CUTOFF**: need a convergence test (especially for interaction/adsorption energies, where convergence of the energy difference matters more than the total energy). Note that default `REL_CUTOFF` around 60 is usually a low starting point; Multiwfn generation gives a more reasonable pair.
- **Default MAX_SCF 50 is too small**: CP2K’s default `MAX_SCF = 50` is often not enough; Multiwfn-generated files default to 128. Raise it for long jobs or hard-to-converge systems.
- **k-points**: CP2K supports k-point sampling via `&KPOINTS`, but **DFT+U does not support k-points** (with U you can only use Γ); CP2K also does not use lattice symmetry to reduce k-points, so equivalent sampling is more expensive — budget density accordingly.
- **Spin**: spin-polarized systems must set `UKS`; otherwise even with `MULTIPLICITY > 1` CP2K runs closed-shell and the result is completely wrong.

## 6.2 Charged periodic systems (major pitfall)
- **3D periodic charged systems**: CP2K automatically adds a **uniform compensating background charge** (jellium / compensating charge) to neutralize net charge. The `CHARGE` keyword is the **system net charge** (not “background charge”); e.g. a +2 cell is `CHARGE 2`.
- **Makov–Payne correction**: CP2K has **no built-in** Makov–Payne (or SCPC) correction (VASP 6.2+ has SCPC). Absolute energies of 3D periodic charged systems need a **manual Makov–Payne-class correction**, which makes energy converge faster with box size. Therefore:
  - 3D charged systems must have a **box-size convergence test**; when reporting energy, state box size and correction method.
  - If you treat charged slab adsorption as 3D periodic, you must consider a Makov–Payne-class correction (otherwise adsorption energies are badly distorted, e.g. Zn²⁺ on a metal surface giving an absurd −26 eV).
- **2D periodicity is a major CP2K advantage over VASP/QE**: charged slab adsorption, or adsorption of charged species, **should be run as 2D periodic** (`&POISSON` with `PSOLVER MT`). The adsorbate and the slab itself should use the **same box** as the adsorption system so errors cancel as much as possible in the energy difference (adsorption energy).
- **Hard requirement of PSOLVER MT**: the box size in the non-periodic direction must be **at least twice the span of the electron-density distribution** (otherwise you get pathological bonding, system disintegration, etc.).
- **1D charged systems**: may be treated fully as 1D periodic (`PSOLVER ANALYTIC`); or `PSOLVER PERIODIC` with 3D periodicity plus a Makov–Payne correction, depending on system details, net-charge distribution, and the property of interest.
- **Charged defects**: first decide whether the defect should be charged and by how much (neutral vs charged). Absolute energies of charged defects converge poorly; you must do a box-size convergence test. Geometry optimization of a charged system needs no extra correction (forces are unaffected by the uniform field of the compensating background).
- **Ionic adsorption energies**: in the gas phase, electrostatics of ion adsorption are too strong and adsorption energies are abnormally large; a reasonable value usually needs solvent (implicit or explicit). Note that CP2K’s implicit solvent (SCCS) is poorly supported and often fails to converge; switch to QE or similar if needed. When computing adsorption energy, keep boxes identical across models (adsorbed system / adsorbate / slab).

## 6.3 SCF not converging: diagnosis order and parameter order
**Step 0: distinguish “SCF not converging” from “geometry optimization not converging”**. Geometry-opt failure needs geometry-opt remedies (tune `OPTIMIZER`, `MAX_ITER`, `TRUST_RADIUS`, geometry convergence criteria); **changing SCF settings is pointless**. Coarsening `EPS_SCF` (e.g. 2.0E-06 → 2.0E-04) only makes geometry optimization oscillate and hinders convergence further. Diagnose in this order:

1. **Check the structure**: overlapping atoms? Reasonable cell size (under PBC, are atoms too close, e.g. a long chain sticking out of the box)? For low-dimensional systems, is the periodic direction set correctly (treating a 2D material as a 3D vacuum box causes dangling-bond problems)? Is the vacuum thick enough?
2. **Check settings**: UKS/spin, net charge (`CHARGE`), multiplicity, k-point density, `CUTOFF`/`REL_CUTOFF` reasonable? Is the functional appropriate (functionals with large HF fractions have a larger HOMO–LUMO gap and often converge more easily)?
3. **Change the initial guess (highest cost/benefit step)**:
   - `SCF_GUESS RESTART` + `WFN_RESTART_FILE_NAME` to read a converged `.wfn`/`.kp`.
   - Converge first with a small basis (e.g. DZVP), then read the guess and continue with a larger basis.
   - Converge first with a hybrid, then read the guess and switch to a pure functional (hybrids must use `SCREEN_ON_INITIAL_P` and a previously converged wavefunction, otherwise the result is meaningless and hard to converge).
   - Magnetic systems: set `MAGNETIZATION` in `&KIND`, or use `&BS` to specify atomic configurations in detail (e.g. Na⁺/Cl⁻ configurations for ionic crystals, Fe1=3/Fe2=−3 for antiferromagnets).
   - DFT+U can sometimes help SCF converge (note: no k-points).
4. **Raise numerical precision**: increase `CUTOFF`/`REL_CUTOFF`, decrease `EPS_DEFAULT`, or switch `GPW`↔`GAPW`.
5. **Diagonalization algorithm (inside &SCF)**:
   - Metals / gapless systems: smearing (e.g. Fermi–Dirac) + `ADDED_MOS` to add occupied orbitals.
   - `LEVEL_SHIFT` 0.3–0.4 Hartree to shift levels and stabilize hard cases.
   - `MIXING`: `DIRECT_P_MIXING` performs very poorly; default `BROYDEN_MIXING`; when hard to converge, drop `ALPHA` from 0.4 to 0.1–0.3 and raise `NBROYDEN` from default 4 to 8–12; `PULAY` as a backup.
   - Under GAPW you may try `GMIX_P` (with `MAX_GVEC_EXP 3.0`) — **GAPW only** (community empirical experience).
   - Empirical recipe (hard diagonalization): `MODIFIED_BROYDEN_MIXING`, `ALPHA 0.2`, `BETA 1.5`, `NBROYDEN 24`, `GMIX_P`, `MAX_GVEC_EXP 3.0`, `N_SIMPLE_MIX 16`.
6. **OT algorithm (inside &SCF, OT=T)**:
   - Enable `&OUTER_SCF` (Multiwfn default; helps convergence a lot).
   - Preconditioner `FULL_ALL` is usually best; when budget is tight use `FULL_SINGLE_INVERSE`/`FULL_KINETIC`.
   - Change `ALGORITHM` from `STRICT` to `IRAC` for more robustness.
   - Change `MINIMIZER` from `DIIS` to `CG` + `LINESEARCH 3PNT` for more stability.
   - A wavefunction after OT convergence can be saved as the guess for a diagonalization calculation.
7. **SCF failure during geometry optimization / MD**:
   - Occasional SCF failure mid-opt can continue (2024.1 and later need `IGNORE_CONVERGENCE_FAILURE=.TRUE.`).
   - Early-opt SCF failure can be lived with; SCF often improves once the geometry becomes reasonable.
   - `EXTRAPOLATION ASPC` is the default and usually best; when k-points do not support extrapolation, prefer `EXTRAPOLATION USE_PREV_P`.
   - MD may reduce `TIMESTEP`; GEO_OPT may reduce `TRUST_RADIUS`.
8. **Last resort**: loosen `EPS_SCF` (geometry opt 1E-5–1E-6 is usually enough; high-accuracy single points 1E-6–1E-7), but do not drop precision so far that it “looks converged” (e.g. 1E-4) — geometry opt will oscillate and results will not be trustworthy.

## 6.4 Other high-frequency CP2K pitfalls
- **Hybrid functionals**: accelerate with ADMM; `SCREEN_ON_INITIAL_P` must be paired with reading a converged wavefunction (otherwise the screening term is based on a meaningless initial density matrix: wrong results and hard convergence). See sobereva.com/690.
- **Band-structure calculations**: pure-functional bands can use the band.bs method (`&BAND` + a high-symmetry k-path), with Multiwfn post-processing; see the forum featured post (tid=44474).
- **Implicit solvent**: CP2K’s SCCS solvent model is poorly supported and often fails to converge; when solvent is needed, consider switching to QE (more mature EnvSCCS etc.) or using explicit solvent.
- **Performance and memory**: GAPW is much more expensive than GPW; too large a `CUTOFF` or too many k-points easily runs out of memory; do not blindly pile on precision.

# 7. Case sources (Computational Chemistry Community / Thinker's Club)
Original sources of key claims (for further reading and checking):
- **How to handle hard SCF convergence in CP2K** (Sobereva post, containing the full §6.3 methodology): http://sobereva.com/665
- **Key points and simple examples for hybrid-functional calculations in CP2K**: http://sobereva.com/690
- **Using Multiwfn to conveniently create CP2K input files**: http://sobereva.com/587
- **Personal experience with hard SCF in CP2K diagonalization** (GMIX_P, MODIFIED_BROYDEN_MIXING recipe): http://bbs.keinsci.com/forum.php?mod=viewthread&tid=59859
- **Thoughts and questions on CP2K adsorption energies for periodic charged + dipolar systems** (3D charged automatic jellium background, manual Makov–Payne, PCCP 2018 reference): http://bbs.keinsci.com/forum.php?mod=viewthread&tid=44444
- **How to accurately compute metal-ion adsorption energies on Zn(100)** (charged slabs as 2D periodic, same box for all adsorption-energy models, SCCS implicit solvent often fails): http://bbs.keinsci.com/forum.php?mod=viewthread&tid=57736
- **Requirements for PSOLVER MT 2D periodic calculations** (non-periodic box ≥ twice the electron-density span; TZV2P-MOLOPT-GTH better than old TZV2P-GTH): http://bbs.keinsci.com/forum.php?mod=viewthread&tid=58830
- **PSOLVER choice for 1D charged systems** (ANALYTIC or PERIODIC + Makov–Payne): http://bbs.keinsci.com/forum.php?mod=viewthread&tid=58999
- **Geometry optimization not converging in CP2K** (geo-opt failure ≠ SCF failure; changing SCF settings is pointless): http://bbs.keinsci.com/forum.php?mod=viewthread&tid=31404
- **Brief notes on charged-system calculations**: http://bbs.keinsci.com/forum.php?mod=viewthread&tid=28546
- **A simple method for CP2K band-structure calculations with pure functionals** (featured post): http://bbs.keinsci.com/forum.php?mod=viewthread&tid=44474
