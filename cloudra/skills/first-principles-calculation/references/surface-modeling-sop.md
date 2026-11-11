# Surface & Slab Modeling SOP (First-Principles Calculations)

---

## 1. Bulk Optimization, Cleaving, and Surface Termination

### 1.1 Bulk Full Relaxation (ISIF=3) Protocol & Numerical Convergence
Before constructing any slab model, the bulk crystal structure must be thoroughly relaxed at the target theoretical level. Cleaving slabs directly from experimental CIF files without bulk relaxation introduces artificial strain, distorting surface energies and adsorption energies.

*   **VASP Full Relaxation Settings**:
    *   `ISIF = 3` (full degrees of freedom: cell volume, cell shape, and internal atomic positions).
    *   `IBRION = 2` (Conjugate Gradient, CG) or `IBRION = 1` (RMM-DIIS for near-equilibrium geometries).
    *   `EDIFF = 1E-6` to `1E-8` eV (electronic self-consistency criterion).
    *   `EDIFFG = -0.01` to `-0.005` eV/Å (ionic force convergence criterion).
    *   `PSTRESS = 0`, with convergence judged by average external pressure $|P| < 0.5\text{ kbar}$ ($< 0.05\text{ GPa}$) and all stress tensor components $\sigma_{ij} < 0.5\text{ kbar}$.
*   **Pulay Stress Elimination & Plane-Wave Cutoff (ENCUT)**:
    *   In a plane-wave basis, when cell volume varies during relaxation, a fixed cutoff sphere causes the basis set size to jump discontinuously, generating an artificial inward Pulay stress that underestimates equilibrium volume.
    *   **Remediation Protocol**:
        1.  Set `ENCUT` $\ge 1.3 \sim 1.5 \times \max(\text{ENMAX})$ of the POTCARs (e.g., $500 \sim 600\text{ eV}$ for transition metal oxides).
        2.  Execute a **two-step relaxation protocol**: Step 1 coarse relaxation (`ISIF=3`); copy `CONTCAR` to `POSCAR`, reset plane-wave basis, and run Step 2 fine relaxation (`ISIF=3`).
        3.  For ultimate precision, fit an Equation of State (EOS, e.g. Birch-Murnaghan) across 7–11 fixed-volume points ($\pm 10\%$ volume range with `ISIF=4` or `2`) to extract true equilibrium volume $V_0$ and bulk modulus $B$.
*   **k-Point Sampling Convergence**:
    *   Use Monkhorst-Pack or $\Gamma$-centered grids (hexagonal/trigonal lattices strictly require $\Gamma$-centered with odd divisions, e.g. $9\times 9\times 9$).
    *   Density criterion: $k\text{-spacing} \le 0.02 \sim 0.03\text{ \AA}^{-1}$ ($k_i \times a_i \ge 30 \sim 40\text{ \AA}$), with total energy converged within $\le 1\text{ meV/atom}$.

---

### 1.2 Slab Cleaving (Miller Indices (hkl)) & Surface Termination

*   **Slab Geometry Classifications**:
    *   **Symmetric Slabs**: Top and bottom surfaces share identical atomic arrangements, stoichiometry, and point-group symmetry (inversion center $C_i$ or horizontal mirror plane $\sigma_h$).
        *   *Advantage*: Intrinsic net dipole is zero; eliminates macroscopic electrostatic potential jump across vacuum; surface energy can be calculated unambiguously.
        *   *Limitation*: Layer thickness is constrained by stoichiometry; non-centrosymmetric crystals cannot yield non-polar symmetric slabs.
    *   **Asymmetric Slabs**: Top and bottom surfaces differ (e.g. metal-terminated on one side, oxygen-terminated on the other; or one-sided adsorption).
        *   *Physical Problem*: Unequal surface charges produce a net dipole moment $\mu_z$ along the surface normal ($z$-axis). Under 3D periodic boundary conditions (PBC), this generates a sawtooth electrostatic potential artifact, causing artificial Kohn-Sham band tilting and spurious charge transfer.
*   **Dipole Correction Protocol**:
    *   For an asymmetric slab under 3D periodicity, evaluate a dipole correction. This VASP example assumes the vacuum axis is the third lattice direction. [VASP LDIPOL](https://vasp.at/wiki/LDIPOL)
        ```ini
        LDIPOL = .TRUE.
        IDIPOL = 3       # Apply dipole correction along the surface normal (z-axis)
        DIPOL  = x y z   # Center of dipole correction (typically slab geometric center)
        ```
    *   *Mechanism*: Introduces a compensating electrostatic field in the vacuum region to cancel periodic dipole interactions, restoring a flat vacuum electrostatic potential.

---

### 1.3 Surface Polarity (Tasker's Rules) & Surface Reconstruction

According to Tasker's classification (*J. Phys. C: Solid State Phys.* 1979, 12, 4974), ionic crystal surfaces are classified into three types based on layer stacking:

1.  **Tasker Type I (Non-polar neutral planes)**:
    *   Each atomic plane contains stoichiometric proportions of cations and anions, net charge $q = 0$, no layer dipole (e.g., $\text{TiO}_2(110)$, $\text{NaCl}(100)$).
    *   *Stability*: Thermally stable, easily cleaved without electrostatic reconstruction.
2.  **Tasker Type II (Symmetric charged layers with zero net dipole)**:
    *   Individual planes carry net charge, but groups of layers form symmetric unpolarized repeat units (e.g. $+ - +$ stacking in fluorite $\text{CeO}_2(111)$ $\text{O-Ce-O}$ trilayers).
    *   *Stability*: Stable if cleaved at the natural neutral stoichiometric boundary (e.g., stoichiometric oxygen termination).
3.  **Tasker Type III (Polar surfaces with diverging electrostatic energy)**:
    *   Alternating charged planes of opposite sign along the surface normal (e.g., rocksalt $\text{NiO}(111)$, perovskite $\text{SrTiO}_3(111)$, wurtzite $\text{ZnO}(0001)$).
    *   *Electrostatic Catastrophe*: Carries a non-zero dipole per unit cell; electrostatic surface energy diverges with slab thickness. Unreconstructed bulk-truncated surfaces are unphysical.
    *   *Compensation Mechanisms*:
        *   **Stoichiometric reconstruction**: Removal of 50% of surface ions (e.g., removing half of the top and bottom oxygen atoms).
        *   **Adsorbate compensation**: Adsorption of charged counter-ions (e.g. $\text{H}^+$ or $\text{OH}^-$).
        *   **Electronic reconstruction**: Surface valence change or metallization to cancel the dipole.

---

### 1.4 Surface Energy Calculation & Wulff Construction

*   **Stoichiometric Slab Surface Energy**:
    $$\gamma = \frac{E_{\text{slab}} - N_{\text{bulk}} E_{\text{bulk}}}{2 A}$$
    where $E_{\text{slab}}$ is the fully relaxed slab energy, $E_{\text{bulk}}$ is the bulk formula unit energy, $N_{\text{bulk}}$ is the number of formula units in the slab, and $A$ is the single-side surface area ($2A$ accounts for top and bottom surfaces of a symmetric slab).
*   **Non-Stoichiometric Oxide Surface Energy (Chemical Potential Dependent)**:
    For a multinary oxide $M_xO_y$:
    $$\gamma(\mu_O) = \frac{1}{2A} \left( E_{\text{slab}} - N_M E_{\text{bulk}, M_xO_y}^{\text{per-M}} - \left(N_O - N_M \frac{y}{x}\right) \mu_O \right)$$
    with physical bounds on oxygen chemical potential:
    $$\frac{1}{y}\Delta H_f(M_xO_y) \le \mu_O - \frac{1}{2} E_{O_2} \le 0$$
*   **Wulff Construction**:
    By Gibbs-Wulff theorem, the equilibrium crystal shape minimizes $\sum_i \gamma_i A_i$, where the distance from crystal center to face $(hkl)$ is proportional to $\gamma_{hkl}$:
    $$\frac{\gamma_{hkl}}{d_{hkl}} = \text{constant}$$

---

## 2. Slab Sizing & Vacuum Convergence SOP

### 2.1 Slab Thickness Convergence & Interlayer Relaxation
Slabs must be thick enough that the central layers reproduce bulk electronic structure, coordination, and bond lengths.

*   **Testing Procedure**:
    1.  Fix vacuum thickness (e.g., $15\text{ \AA}$), increment number of layers $L$ (e.g. 3, 4, 5, 6, 7, 8 layers).
    2.  Check convergence of:
        *   **Interlayer relaxation**: $\Delta d_{ij} = \frac{d_{ij} - d_{\text{bulk}}}{d_{\text{bulk}}} \times 100\%$. Central layer distance change should satisfy $|\Delta d_{\text{center}}| < 0.5\% \sim 1.0\%$.
        *   **Surface energy convergence**: $\Delta \gamma < 1\text{ meV/\AA}^2$ ($< 0.01\text{ J/m}^2$).
        *   **Work function convergence**: $\Phi = V_{\text{vacuum}} - E_{\text{Fermi}}$ converged to $\Delta \Phi < 0.02 \sim 0.05\text{ eV}$.

---

### 2.2 Selective Dynamics: Fixing Bottom Substrate Atoms

*   **Physical Rationale**:
    1.  **Simulate Semi-Infinite Bulk**: Slabs connect to rigid bulk below. Free relaxation of thin slabs can trigger unphysical macroscopic warping or artificial phase transitions.
    2.  **Decouple Bottom Relaxation from Top Adsorption**: Keeps bottom surface as unperturbed bulk reference.
    3.  **Computational Efficiency**: Restricting degrees of freedom speeds up ionic optimization and Hessian builds.
Build the fixed substrate mask on the clean slab using layer membership along its actual surface normal. Carry the chosen substrate atom numbers into the adsorbed system and check them against the atom order in the final engine input. Use the same fixed substrate mask for the clean slab and the matched adsorption runs. Select the depth of the mobile region based on convergence of the target observable.

---

### 2.3 Vacuum Layer Thickness & Potential Decay
*   **Thickness Guideline**: Standard $15 \sim 20\text{ \AA}$ (ensure at least $12\text{ \AA}$ clearance between adsorbate head and upper periodic image).
*   **Convergence Metric (LOCPOT)**:
    *   Inspect planar-averaged electrostatic potential $\bar{V}(z) = \frac{1}{A} \iint V(x, y, z) \, dx dy$.
    *   $\bar{V}(z)$ must exhibit a strictly flat plateau of width $\ge 5\text{ \AA}$ in the vacuum middle ($\frac{d\bar{V}}{dz} \approx 0$).
    *   Electron density (CHGCAR) in vacuum center must decay to $< 10^{-5} \sim 10^{-6}\text{ }e/\text{\AA}^3$.

---

### 2.4 Supercell Sizing, Coverage & Lateral Interaction Removal
*   **Lateral Periodic Image Repulsion**:
    Small unit cells ($1\times 1$, $2\times 1$) place adsorbates too close to their periodic images, overestimating dipole-dipole and steric repulsion.
*   **Sizing Rules**:
    *   **Low-coverage single-molecule limit**: Minimum lateral separation $d_{\text{image-image}} \ge 5 \sim 7\text{ \AA}$.
    *   For FCC(111), standard choices are $p(2\times 2)$ ($\theta = 0.25\text{ ML}$), $p(3\times 3)$ ($\theta = 0.11\text{ ML}$), or $(\sqrt{3}\times\sqrt{3})R30^\circ$ ($\theta = 0.33\text{ ML}$).
    *   **Coverage-dependent studies**: Sample coverage ladder $\theta = 1/9, 1/4, 1/3, 1/2, 2/3, 1.0\text{ ML}$ to fit $E_{\text{ads}}(\theta)$.

---

## 3. Adsorption Sites & Polyatomic Adsorbate Placement SOP

### 3.1 Symmetry Adsorption Sites on Metals and Oxides

| Surface Type | Site Name | Local Coordination / Geometry | Typical Preferred Adsorbates |
| :--- | :--- | :--- | :--- |
| **FCC (111)** | **Top (Atop)** | Directly above single surface atom ($CN=1$) | *CO (on Pt/Rh), *OH, *CH3 |
| | **Bridge** | Midpoint between two adjacent surface atoms ($CN=2$) | *CO (on Pd), *H |
| | **Hollow-fcc** | 3-fold hollow with no atom directly in layer 2 below ($CN=3$) | *O, *N, *H, *S |
| | **Hollow-hcp** | 3-fold hollow with atom in layer 2 directly below ($CN=3$) | *O, *H, *N |
| **FCC (100)** | **Top / Bridge** | 1-fold / 2-fold coordination | Weakly bound adsorbates |
| | **4-fold Hollow** | Square hollow of 4 surface atoms ($CN=4$) | *C, *N, *O, *S, strong chemisorption |
| **BCC (110)** | **Top / Short-bridge / Long-bridge / Quasi-3-fold** | Asymmetric bridge and hollow sites | *H, *O, *CO on Fe/W/Mo |
| **Rutile (110)** | **5-fold CUS Metal ($\text{Ti}_{5c}$)** | Coordinatively unsaturated metal cation | *H2O, *OOH, *OH, Lewis base molecules |
| | **Bridging Oxygen ($\text{O}_{2c}$)** | Protruding 2-fold bridging oxygen | *H (protonation to form surface hydroxyl) |
| | **In-plane Oxygen ($\text{O}_{3c}$)** | 3-fold lattice oxygen | Generally inactive for primary adsorption |
| | **Oxygen Vacancy ($V_O$)** | Reduced center from bridging oxygen removal | *O2 activation, *CO2 capture |

---

### 3.2 Polyatomic Adsorbate Placement & Initial Geometry Rules

```
       *H, *O (Hollow/Top)           *CO (Top)             *OH (Top, Tilted)            *OOH (Top, Zigzag)
             [X]                        (O)                       (H)                        (H)
            / | \                        |                       /                          /
          (M)(M)(M)                     (C)                     (O)                       (O)
                                         |                     /                         /
                                        (M)                  (M)                       (O)
                                                                                        |
                                                                                       (M)
```

| Adsorbate | Anchor Atom & Mode | Initial $d_{\text{M-Anchor}}$ (Å) | Key Internal Geometry | Recommended Initial Orientation |
| :--- | :--- | :--- | :--- | :--- |
| **\*H** | H (Top / Hollow) | $1.60 \sim 1.80$ | — | Along surface normal |
| **\*O** | O (Hollow / Bridge) | $1.80 \sim 2.10$ | — | Centered on hollow/bridge |
| **\*OH** | O (Top / Bridge) | $1.90 \sim 2.15$ | $d_{\text{O-H}} \approx 0.98\text{ \AA}$ | $\angle\text{M-O-H} \approx 105^\circ \sim 115^\circ$ (H tilted away) |
| **\*OOH** | Terminal O (Top) | $1.95 \sim 2.20$ | $d_{\text{O-O}} \approx 1.45$, $d_{\text{O-H}} \approx 0.98$ | $\angle\text{M-O-O} \approx 110^\circ$, $\angle\text{O-O-H} \approx 105^\circ$ (Zigzag) |
| **\*CO** | C (Top / Bridge) | $1.85 \sim 2.05$ | $d_{\text{C-O}} \approx 1.15 \sim 1.18$ | Perpendicular, $\angle\text{M-C-O} \approx 175^\circ \sim 180^\circ$ |
| **\*CHO** | C (Top) | $1.95 \sim 2.10$ | $d_{\text{C-O}} \approx 1.22$, $d_{\text{C-H}} \approx 1.10$ | Planar $sp^2$, O and H pointing upward |
| **\*COOH** | C (Top, monodentate) | $1.95 \sim 2.15$ | $d_{\text{C=O}} \approx 1.21$, $d_{\text{C-OH}} \approx 1.35$ | Plane tilted $20^\circ \sim 40^\circ$ from normal |
| **\*N2** | N (End-on) | $1.90 \sim 2.10$ | $d_{\text{N-N}} \approx 1.12 \sim 1.16$ | Perpendicular, $\angle\text{M-N-N} \approx 175^\circ \sim 180^\circ$ |
| **\*NNH** | N (End-on) | $1.85 \sim 2.05$ | $d_{\text{N-N}} \approx 1.25$, $d_{\text{N-H}} \approx 1.02$ | $\angle\text{M-N-N} \approx 120^\circ$, $\angle\text{N-N-H} \approx 110^\circ$ |
| **\*NH3** | N (Top) | $2.10 \sim 2.30$ | $d_{\text{N-H}} \approx 1.02$, $\angle\text{H-N-H} \approx 107^\circ$ | Umbrella pointing away from surface |
| **\*OCH3** | O (Top / Bridge) | $1.90 \sim 2.10$ | $d_{\text{O-C}} \approx 1.42$, $d_{\text{C-H}} \approx 1.10$ | $\angle\text{M-O-C} \approx 120^\circ \sim 130^\circ$, tetrahedral methyl |

---

### 3.3 Staged Relaxation of Molecular Adsorbates

Start from a relaxed clean slab and chemically plausible molecular conformers or adsorbed parents. For each trial, record the starting file, site, anchor, height, orientation and declared composition, charge and spin. Compare plausible poses that differ in site, orientation or binding group. Inspect the closest contacts, including periodic images. Set the electronic method, dispersion treatment, final force criteria and fixed substrate layers using the task's scientific requirements.

| Starting condition | First ionic pass |
| --- | --- |
| Plausible contacts and reproducible initial forces | Start directly with the production mobile region at fixed cell. |
| Molecule starts far from the surface or the pose drifts before approaching | Consider a short fixed-slab approach. Allow motion along the actual surface normal or relax the molecule on the fixed slab. Use an explicit temporary anchor restraint when the intended approach requires one. |
| Strong bonding, possible dissociation or local reconstruction | Let the adsorbate and nearby surface atoms move together early. Preserve distinct molecular, dissociated or reconstructed endpoints as separate outcomes. |
| Second adsorbate added to a relaxed complex | Seed from the verified first complex. Include plausible sites on the first adsorbate and exposed substrate as appropriate. If the placement needs a local first pass, release the first adsorbate and chosen surface layers in the coupled pass. |

In the coupled pass, use an evaluated geometry from the preceding run. Set a fresh constraint mask from that file's atom order, free all adsorbates and the chosen active substrate layers, and keep the fixed cell and declared bulk-like substrate layers. Recheck atom numbers after an export that groups by element. Carry coordinates across stages and reuse electronic restart files only when the engine and new input are compatible. A change in composition, such as adding Li, calls for checking species, basis/pseudopotential mappings, electron count and the electronic starting guess.

**Check force quality and convergence.** If forces are noisy, recompute them on the same geometry with tighter electronic convergence. For GPW, check grid sensitivity with `CUTOFF` and `REL_CUTOFF`. If reliable forces still give unstable ionic steps, reduce the trust radius or step length, or use a more robust optimizer for the early steps. At the final geometry check the engine's electronic and ionic termination, the force criterion on the mobile degrees of freedom, and the actual binding site, contact geometry and bonding. Record migration, desorption and starting poses that converge to the same structure. Use the native evaluated geometry and its log together. A saved frame from a step limit, interruption or unconverged run can seed a retry with its status recorded. Compare energies of verified endpoints at matched production settings and name the lowest-energy structure among the tested candidates. [CP2K force and optimizer guidance](https://manual.cp2k.org/trunk/methods/optimization/geometry.html) · [GPW grid convergence](https://manual.cp2k.org/trunk/methods/dft/cutoff.html) · [VASP structure optimization](https://vasp.at/wiki/Structure_optimization)

| Engine | Fixed-cell relaxation and constraint handoff |
| --- | --- |
| VASP | Use ionic relaxation with `ISIF = 2`. Set the `Selective dynamics` mask on the current POSCAR. Flags follow direct lattice directions even with Cartesian coordinates. For a force-based stop use a negative `EDIFFG`. Match the evaluated output geometry to the ionic and SCF logs before using it in the next stage. [ISIF](https://vasp.at/wiki/ISIF) · [POSCAR](https://vasp.at/wiki/POSCAR) · [EDIFFG](https://vasp.at/wiki/EDIFFG) |
| CP2K | Use `RUN_TYPE GEO_OPT` and set `MOTION / CONSTRAINT / FIXED_ATOMS` by 1-based `LIST` in input coordinate order. Components are fractional. When constraints change, use the evaluated coordinates and rebuild the mask. Check restart input for retained constraints. Read `MAX_FORCE`, `RMS_FORCE`, `MAX_DR` and `RMS_DR` against the chosen criteria and units. [FIXED_ATOMS](https://manual.cp2k.org/trunk/CP2K_INPUT/MOTION/CONSTRAINT/FIXED_ATOMS.html) · [GEO_OPT](https://manual.cp2k.org/cp2k-2026_2-branch/CP2K_INPUT/MOTION/GEO_OPT.html) · [EXT_RESTART](https://manual.cp2k.org/trunk/CP2K_INPUT/EXT_RESTART.html) |
| ABACUS | Use `calculation relax` and set movement flags in the new `STRU`, with 0 for fixed and 1 for mobile components. Check the evaluated frame and the configured force threshold in the log, including the threshold's units. [ABACUS geometry optimization](https://abacus-rtd.readthedocs.io/en/latest/advanced/opt.html) |
| Quantum ESPRESSO | Use `calculation='relax'`. Set Cartesian force multipliers `if_pos(1..3)` in `ATOMIC_POSITIONS` for the current stage. Check both the force and energy stopping criteria from `&CONTROL`. [PW input reference](https://www.quantum-espresso.org/Doc/INPUT_PW.html) |

Published examples illustrate different entry routes. In a pre-relaxation benchmark for B2O starting far above Ag(111), the first pass allowed molecular motion along the surface normal with the Ag fixed. The second pass relaxed the molecule and three upper Ag layers together. For quinones on Ag(111), a search over position and rotation preceded joint relaxation with two upper Ag layers. Use these as evidence for staging and multiple poses. Select the mobile region for the system at hand. [B2O on Ag(111)](https://doi.org/10.1039/D2DD00016D) · [Quinones on Ag(111)](https://doi.org/10.1021/acsnano.0c10065)

---

### 3.4 Adsorption Energy & Free Energy Calculation

*   **Electronic Adsorption Energy (Gas-Phase Reference)**:
    $$E_{\text{ads}} = E_{\text{slab+adsorbate}} - E_{\text{slab}} - E_{\text{adsorbate(gas)}}$$
    $E_{\text{ads}} < 0$ is exothermic relative to the declared references. Use compatible production settings and the same substrate mask for the clean and covered slabs. For incremental adsorption on a pre-covered slab, use the verified pre-covered slab and the declared incoming-species reference.
*   **Electrochemical Reference (CHE Model, Nørskov)**:
    $$\Delta G_{*\text{OH}} = G_{*\text{OH}} + \frac{1}{2} G_{\text{H}_2} - G_{*} - G_{\text{H}_2\text{O}} - eU$$
*   **ZPE & Vibrational Entropy Corrections**:
    $$G = E_{\text{DFT}} + \text{ZPE} - T S_{\text{vib}} + E_{\text{solv}}$$
    $$\text{ZPE} = \sum_{i} \frac{1}{2} h \nu_i, \quad S_{\text{vib}} = k_B \sum_i \left[ \frac{h\nu_i / (k_B T)}{e^{h\nu_i / (k_B T)} - 1} - \ln\left(1 - e^{-h\nu_i / (k_B T)}\right) \right]$$

---

### 3.5 Partial Hessian Vibrational Analysis (PHVA) SOP

*   **VASP Setup**:
    ```ini
    IBRION = 5       # Finite differences for Hessian matrix
    POTIM  = 0.015   # Step size (0.015 ~ 0.02 Å)
    NFREE  = 2       # Central differences (± displacements)
    NSW    = 1       # Single ionic pass
    EDIFF  = 1E-8    # Tight electronic convergence required for reliable force derivatives
    ```
*   **Selective Dynamics Restriction**:
    Set all substrate atoms to `F F F` in `POSCAR`. Set only **adsorbate atoms and the 1–2 directly coordinating surface atoms to `T T T`**.
*   **Quasi-RRHO Cutoff**:
    For modes $< 50 \sim 100\text{ cm}^{-1}$, use Grimme's quasi-RRHO approximation or raise to $100\text{ cm}^{-1}$ to avoid unphysical entropy divergence ($\nu \to 0$).
