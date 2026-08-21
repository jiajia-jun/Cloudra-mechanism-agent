# VASP & CP2K Production Blueprints & Troubleshooting Decision Trees

---

## 1. Production-Grade VASP INCAR Blueprints

### 1.1 Bulk Lattice & Coordinate Relaxation
Full relaxation of 3D periodic crystals (cell volume + cell shape + internal atomic positions).

```ini
# --- Global Precision & System ---
SYSTEM = Bulk_Relaxation_Production
PREC   = Accurate      # High-density FFT grids (NGX, NGY, NGZ), avoids wrap-around errors
ENCUT  = 520           # >= 1.3 ~ 1.5 * max(ENMAX) to eliminate Pulay stress
LREAL  = .FALSE.       # Reciprocal space projection for small unit cells

# --- Electronic Relaxation ---
ALGO   = Fast          # Hybrid Davidson + RMM-DIIS
EDIFF  = 1E-6          # Electronic SCF energy tolerance (1E-8 for phonons)
NELM   = 100
NELMIN = 4

# --- Smearing & Integration ---
# Insulators/semiconductors: ISMEAR = 0, SIGMA = 0.05 (relaxation) or ISMEAR = -5 (static)
# Metals: ISMEAR = 1 or 2, SIGMA = 0.1 ~ 0.2 (verify TS entropy < 1 meV/atom)
ISMEAR = 0
SIGMA  = 0.05

# --- Ionic Relaxation & Stress ---
IBRION = 2             # Conjugate Gradient (most robust)
ISIF   = 3             # Optimize positions + cell shape + cell volume
EDIFFG = -0.01         # Force tolerance on ions (eV/Å)
NSW    = 200
POTIM  = 0.2           # Reduced step size (default 0.5 can overshoot)

# --- Spin & Magnetism ---
ISPIN  = 2             # Set to 1 for closed-shell non-magnetic systems
# MAGMOM = 4*5.0 8*0.6 # Initial magnetic moments per POSCAR element order

# --- Output Controls ---
LWAVE  = .FALSE.
LCHARG = .FALSE.
```

*   **Two-Pass Relaxation Protocol**:
    During `ISIF=3`, cell volume changes trigger discontinuous plane-wave basis set size shifts (Pulay stress).
    **Standard Rule**: After initial relaxation, copy `CONTCAR` to `POSCAR`, delete old `WAVECAR`, and rerun `ISIF=3`. The final result is valid only when volume change in the second run is $\Delta V / V < 0.1\%$.

---

### 1.2 Slab & Surface Adsorption Relaxation
Optimization of surface slab models and molecular adsorbates with fixed cell volume.

```ini
# --- Precision & Plane Waves ---
SYSTEM = Slab_Adsorption_Production
PREC   = Accurate
ENCUT  = 450           # >= 1.3 * max(ENMAX)
LREAL  = Auto          # Real-space projection recommended for large slab systems
ISYM   = 0             # Disable symmetry to prevent artificial zero-force traps on adsorbates

# --- Electronic SCF ---
ALGO   = Fast
EDIFF  = 1E-5          # 1E-5 for slab relaxation, 1E-6 for static single points
NELM   = 120

# --- Smearing ---
ISMEAR = 0
SIGMA  = 0.05

# --- Ionic Relaxation ---
IBRION = 2             # CG for initial search; switch to 1 (RMM-DIIS) near minimum
ISIF   = 2             # Relax ion positions only; lock lattice constants and vacuum thickness
EDIFFG = -0.02         # Force threshold -0.02 eV/Å
NSW    = 300
POTIM  = 0.15          # Reduced step size for adsorbate stability

# --- Dipole Correction ---
LDIPOL = .TRUE.        # Enable dipole correction
IDIPOL = 3             # Along z-axis (surface normal)

# --- Dispersion Correction ---
IVDW   = 12            # DFT-D3(BJ) empirical dispersion correction
```

---

### 1.3 High-Precision Projected DOS (PDOS) & d-Band Center Analysis
Single-point calculation based on relaxed `CONTCAR`.

```ini
SYSTEM = High_Precision_PDOS
PREC   = Accurate
ENCUT  = 500
LREAL  = .FALSE.       # Reciprocal space projection for highest eigenvalue precision
ISYM   = 2             # Exploit symmetry for Brillouin zone integration
ALGO   = Normal        # Blocked Davidson for clean wavefunctions
EDIFF  = 1E-6
NELM   = 150

# --- Smearing ---
ISMEAR = -5            # Tetrahedron method with Blöchl corrections (requires >= 4 k-points)
                       # For metals with sparse k-points: ISMEAR = 0, SIGMA = 0.02

# --- DOS Grid & Output ---
LORBIT = 11            # Output lm-decomposed PDOS (DOSCAR & PROCAR)
NEDOS  = 2001          # High-resolution energy mesh (default 301 is too coarse)
EMIN   = -20.0
EMAX   = 10.0
LWAVE  = .FALSE.
LCHARG = .TRUE.
```

*   **d-Band Center ($\varepsilon_d$) Formula**:
    $$\varepsilon_d = \frac{\int_{E_{\text{min}}}^{E_{\text{max}}} (E - E_F) \cdot \rho_d(E) \, dE}{\int_{E_{\text{min}}}^{E_{\text{max}}} \rho_d(E) \, dE}$$
    where $\rho_d(E) = \sum_{m} \rho_{d_m}(E)$ summed over all 5 d-orbitals ($d_{xy}, d_{yz}, d_{z^2}, d_{xz}, d_{x^2-y^2}$) and both spin channels. Lower integration limit $E_{\text{min}}$ is set to d-band bottom (typically $-10.0\text{ eV}$), and $E_{\text{max}} = E_F$ (occupied states) or top of the d-band.

---

### 1.4 Strongly Correlated Systems: DFT+U (Hubbard Correction)
For open-shell $3d$ and $4f$ transition-metal and rare-earth oxides.

```ini
# --- DFT+U Configuration (Dudarev Formulation) ---
LDAU      = .TRUE.
LDAUTYPE  = 2          # Dudarev formulation (U_eff = U - J)
LDAUL     = 2 -1 -1    # Angular momentum: 2 for d-electrons, 3 for f-electrons, -1 for no U
LDAUU     = 4.3 0.0 0.0# Coulomb U parameter (eV) per POSCAR element order
LDAUJ     = 0.0 0.0 0.0# Exchange J parameter (set to 0 in Dudarev method)

# --- Density Matrix Mixing ---
LMAXMIX   = 4          # Mandatory: 4 for d-electrons, 6 for f-electrons (ensures spherical charge transfer)
```

#### Standard 3d Transition Metal Oxide $U_{\text{eff}} = U - J$ Reference Table
| Element | Typical State | Recommended $U_{\text{eff}}$ (eV) | Standard Systems |
| :--- | :--- | :--- | :--- |
| **Ti** | $\text{Ti}^{4+} / \text{Ti}^{3+}$ | 2.5 ~ 4.2 | $\text{TiO}_2, \text{BaTiO}_3$ |
| **V**  | $\text{V}^{5+} / \text{V}^{4+}$ | 3.1 ~ 3.25 | $\text{V}_2\text{O}_5, \text{VO}_2$ |
| **Cr** | $\text{Cr}^{3+} / \text{Cr}^{6+}$ | 3.5 ~ 3.7 | $\text{Cr}_2\text{O}_3$ |
| **Mn** | $\text{Mn}^{2+} / \text{Mn}^{3+} / \text{Mn}^{4+}$ | 3.8 ~ 3.9 | $\text{MnO}_x, \text{LiMn}_2\text{O}_4$ |
| **Fe** | $\text{Fe}^{2+} / \text{Fe}^{3+}$ | 4.0 ~ 5.3 | $\text{FeO}, \text{Fe}_2\text{O}_3, \text{LiFePO}_4$ |
| **Co** | $\text{Co}^{2+} / \text{Co}^{3+}$ | 3.32 ~ 3.52 | $\text{CoO}, \text{LiCoO}_2, \text{Co}_3\text{O}_4$ |
| **Ni** | $\text{Ni}^{2+} / \text{Ni}^{3+}$ | 6.0 ~ 6.45 | $\text{NiO}, \text{LiNiO}_2$ |
| **Cu** | $\text{Cu}^{2+}$ | 4.0 ~ 4.5 | $\text{CuO}, \text{Cu}_2\text{O}$ |
| **Ce** | $\text{Ce}^{3+} / \text{Ce}^{4+}$ | 4.5 ~ 5.0 | $\text{CeO}_2, \text{Ce}_2\text{O}_3$ ($LDAUL=3, LMAXMIX=6$) |

---

### 1.5 Screened Hybrid Functional: HSE06

```ini
# --- HSE06 Hybrid Functional ---
LHFCALC = .TRUE.       # Enable Hartree-Fock exact exchange
HFSCREEN= 0.2          # Screening parameter omega = 0.2 Å^-1
AEXX    = 0.25         # 25% exact exchange
AGGAX   = 0.75         # 75% PBE exchange
AGGAC   = 1.0          # 100% PBE correlation
ALDAC   = 1.0

# --- Acceleration & Convergence ---
ALGO    = Damped       # Damped MD algorithm for hybrid functionals
TIME    = 0.4          # Damped step size (0.3 ~ 0.5)
PRECFOCK= Fast         # Fast FFT grid for Fock exchange (2-3x speedup, error < 1 meV/atom)
EDIFF   = 1E-5
NELM    = 80

# --- Two-Stage Initialization ---
ISTART  = 1            # Read pre-converged PBE WAVECAR
ICHARG  = 1            # Read pre-converged CHGCAR
```
*   **Two-Stage Workflow**: Run standard PBE first to generate `WAVECAR`. Restart HSE06 with `ISTART=1` + `ALGO=Damped`. Reduces hybrid electronic steps from 60+ to 10–20 iterations.

---

## 2. Production-Grade CP2K .inp Blueprints

### 2.1 2D Periodic Slab (POISSON PSOLVER MT)

```fortran
&FORCE_EVAL
  METHOD Quickstep
  &DFT
    BASIS_SET_FILE_NAME  BASIS_MOLOPT
    POTENTIAL_FILE_NAME  GTH_POTENTIALS
    UKS .TRUE.
    MULTIPLICITY 1
    CHARGE 0
    
    &MGRID
      CUTOFF 500                  # Plane-wave density cutoff (Ry)
      REL_CUTOFF 60               # Reference grid cutoff (Ry)
      NGRIDS 5
    &END MGRID
    
    &POISSON
      PERIODIC XY                 # Strictly 2D periodicity
      PSOLVER MT                  # Martyna-Tuckerman 2D Poisson solver
      &MT
        ALPHA 7.0
        REL_CUT 2.0
      &END MT
    &END POISSON
    
    &QS
      METHOD GPW
      EPS_DEFAULT 1.0E-12
    &END QS
    
    &SCF
      SCF_GUESS ATOMIC
      EPS_SCF 1.0E-06
      MAX_SCF 100
      &OT .TRUE.                  # Orbital transformation for semiconductors/insulators
        PRECONDITIONER FULL_ALL
        MINIMIZER CG
        LINESEARCH 3PNT
        ALGORITHM IRAC
      &END OT
      &OUTER_SCF .TRUE.
        EPS_SCF 1.0E-06
        MAX_SCF 20
      &END OUTER_SCF
    &END SCF
    
    &XC
      &XC_FUNCTIONAL PBE
      &END XC_FUNCTIONAL
      &VDW_POTENTIAL
        DISPERSION_FUNCTIONAL PAIR_POTENTIAL
        &PAIR_POTENTIAL
          TYPE DFTD3(BJ)
          PARAMETER_FILE_NAME dftd3.dat
          REFERENCE_FUNCTIONAL PBE
        &END PAIR_POTENTIAL
      &END VDW_POTENTIAL
    &END XC
  &END DFT
  
  &SUBSYS
    &CELL
      ABC 12.50 12.50 35.00       # Non-periodic Z dimension must satisfy MT condition
      PERIODIC XY
    &END CELL
  &END SUBSYS
&END FORCE_EVAL
```
*   **PSOLVER MT Height Constraint**: In the non-periodic $Z$-direction, box length $L_z$ must satisfy $L_z \ge 2 \times \text{span}(\rho_e)$. If $L_z$ is insufficient, boundary truncation errors trigger unphysical bonding or charge leakage.

---

### 2.2 Quickstep OT vs. Diagonalization & Basis/Potential Pairings

*   **OT (Orbital Transformation)**:
    Use for semiconductors, insulators, wide-gap slabs ($\text{gap} \ge 0.5\text{ eV}$) at $\Gamma$-point only. Unconditionally converges without density mixing.
    *Recipe*: `PRECONDITIONER FULL_ALL` + `MINIMIZER CG` + `LINESEARCH 3PNT` + `&OUTER_SCF`.
*   **Traditional Diagonalization**:
    Use for metals, zero-gap conductors, or k-point meshes.
    *Recipe*: `&SMEAR` (Fermi-Dirac) + `ADDED_MOS 30~80` + `&MIXING` (Broyden) + `LEVEL_SHIFT 0.3`.
*   **Basis & GTH Potential Pairings**:
    *   *Standard production*: `DZVP-MOLOPT-GTH` paired with `GTH-PBE-qX`.
    *   *High-precision / Adsorption*: `TZV2P-MOLOPT-GTH` (minimal BSSE; Counterpoise correction usually unnecessary).
    *   *Do NOT use*: Old `TZV2P-GTH` (non-MOLOPT family; diffuse exponents cause grid oversampling and SCF failures).

---

## 3. First-Principles Troubleshooting Decision Trees

### 3.1 EDDAV: Error #2 / ZBRENT: fatal error in bracket

*   **EDDAV: Error #2 (Subspace rotation / orthogonalization failed)**:
    1.  Check `POSCAR` for overlapping atoms ($d_{ij} < 0.8\text{ \AA}$) or wrapping artifacts across PBC boundaries.
    2.  Set `ALGO = Normal` or `Exact` with `NELM = 10` to produce a clean initial `WAVECAR`, then switch back to `ALGO = Fast`.
*   **ZBRENT: fatal error in bracket (1D line search failed)**:
    1.  Initial force gradient is too steep or step is too large.
    2.  Reduce `POTIM = 0.1` or `0.05`. If using `IBRION = 1`, switch back to `IBRION = 2` (CG).

---

### 3.2 Electronic SCF Divergence / Oscillation

| Priority | Tuning Step | Parameter Modification | Physical Rationale |
| :--- | :--- | :--- | :--- |
| **Step 1** | **Damp Charge Sloshing** | `AMIX = 0.2`<br>`BMIX = 0.0001` | Damps long-wavelength dielectric charge density sloshing in metals/slabs |
| **Step 2** | **Damp Spin Sloshing** | `AMIX_MAG = 0.8`<br>`BMIX_MAG = 0.0001`<br>`LMAXMIX = 4` | Prevents magnetic moment oscillations between FM and AFM states |
| **Step 3** | **Fermi Surface Smearing** | `ISMEAR = 1`<br>`SIGMA = 0.1 ~ 0.2` | Broadens discontinuous band occupations around Fermi level |
| **Step 4** | **Algorithm Fallback** | `ALGO = Normal` $\to$ `ALGO = All` | Switch from RMM-DIIS to Blocked Davidson or conjugate gradient |
| **Step 5** | **Reset Density Matrix** | Remove `WAVECAR`/`CHGCAR`<br>`ISTART = 0, ICHARG = 2` | Clears corrupt density matrix and restarts from atomic charge guess |

---

### 3.3 Geometry Optimization Trapped / Oscillating
1.  **Switch optimizer**: If `IBRION=1` (RMM-DIIS) oscillates, revert to `IBRION=2` (CG) and set `POTIM=0.1`.
2.  **Break artificial symmetry**: Set `ISYM = 0` for defect and adsorption slabs to allow spontaneous symmetry breaking along soft modes.
3.  **Tighten electronic SCF**: Ensure `EDIFF \le 1E-6` during optimization; noisy energy gradients from loose SCF prevent ionic force convergence.

---

### 3.4 Out-of-Memory (OOM) & Parallel Distribution

*   **VASP Parallelism Variables**:
    *   `KPAR`: Distributes k-points across nodes. Highest parallel efficiency with zero communication overhead, but multiplies memory by `KPAR`.
    *   `NCORE`: Number of cores per orbital band. Recommended: set `NCORE` = number of cores per socket (e.g. 16 or 32).
*   **OOM Diagnosis & Fixes**:
    *   *SIGKILL during subspace matrix initialization*: Reduce `KPAR` (e.g. from 4 to 2 or 1) to conserve RAM per node.
    *   *Array allocation failed in reciprocal projection*: Enable `LREAL = Auto` (real-space projection saves significant memory).
    *   *HSE06 Fock allocation overflow*: Set `PRECFOCK = Fast` and reduce `MAXMEM`.
