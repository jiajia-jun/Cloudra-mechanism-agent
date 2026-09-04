# Method, basis and thermochemistry choices

Read when the method is not already fixed, when interpreting its limits, or when free energies/properties are requested. The mechanism SOP determines which calculations are needed; this reference helps choose their level. Engine keyword spelling belongs in `orca-inputs.md` / `gaussian-inputs.md`.

## 1. Select a level for the claim

Keep the user's method policy and actual software availability first. If a production level is specified, use it consistently rather than selecting another functional for every job. With a free choice, use benchmarks close to the reaction class, charge/spin state and requested property. No universal accuracy order covers DFT, double hybrids, coupled cluster, xTB and MLIPs. General method-selection guidance: [ORCA recommendations](https://www.faccts.de/docs/orca/6.1/manual/contents/quickstartguide/recommendations.html).

Useful candidates retained from the project's method guide are below. They are starting choices for a justified comparison, not claims that each is best for every member of a class. Check implementation and derivative availability in the installed engine before choosing a production protocol.

| Task | Candidate methods / basis strategy | Main qualification |
| --- | --- | --- |
| Main-group geometries and frequencies | B3LYP-D3(BJ), PBE0 with an appropriate dispersion model; def2-SVP screening, def2-TZVP refinement | Validate sensitive barriers/conformers; choose one consistent geometry level |
| Organic thermochemistry / noncovalent energies | ωB97M-V, ωB97X-V; M06-2X for suitable main-group cases | Check class-specific benchmarks and basis convergence; do not double-add dispersion |
| More expensive final single points | Suitable double hybrid, e.g. PWPB95-D3(BJ), or justified correlated method | Derivatives may be unavailable; single-reference assumptions and cost still apply |
| Transition-metal mechanisms | PBE0, TPSSh, M06 and other class-benchmarked choices | Spin states, ligand/metal chemistry and relativistic treatment matter more than a universal ranking |
| Excitation / charge-transfer properties | PBE0/TDDFT; CAM-B3LYP or an appropriate range-separated hybrid | Ground-state TS workflow does not validate an excited-state path |
| Electrical response | PBE0, ωB97M-V or a benchmarked range-separated method | Diffuse basis and response-property validation matter |
| NMR shifts | B3LYP or revTPSS with a property-oriented basis such as pcSseg | Use a consistent referencing/scaling protocol |

Plain HF lacks correlation and plain MP2 is not a universal improvement over DFT; use them for a justified reference/comparison, not as automatic fallbacks. M06-2X's main-group performance does not establish open-shell transition-metal accuracy. Check the supported dispersion parameterization rather than guessing a suffix. See the original [M06 family study](https://comp.chem.umn.edu/truhlar/docs/773fin_plus_supp_info.pdf) and [ORCA functional definitions](https://www.faccts.de/docs/orca/6.1/manual/contents/modelchemistries/DensityFunctionalTheory.html).

## 2. Basis and solvent

- Keep optimization, frequencies and IRC on the same method/basis/environment surface. A higher-level single point may supply an energy correction; label the two levels explicitly and use comparable corrections across the profile.
- Def2-SVP is a screening option; triple-zeta def2-TZVP/TZVPP provides a larger refinement basis. Pople families remain usable in a validated protocol; do not mix levels between species unknowingly. Check diffuse augmentation for anions, weak binding and response properties; names/spellings differ by engine.
- Diffuse functions are not forbidden in population/bond-order analysis. Such quantities can depend strongly on the basis and partitioning; report that dependence. Do not remove diffuse functions needed to describe an anion merely to make a bond-order diagnostic look conventional.
- Select ECP or compatible all-electron relativistic bases according to element and Hamiltonian; not every fourth-period atom requires an ECP. Use the engine's basis definitions rather than inferring core-electron treatment from a name.
- For a solution claim, represent that environment consistently. SMD or an appropriate continuum model can be a useful starting point; explicit solvent/counterions are needed when their participation is part of the mechanism, such as a proton shuttle. Their number comes from a chemical model, not a fixed “1–3 molecules” rule. A deliberately gas-phase benchmark remains gas-phase and must be reported as such.
- A solvent single point on a gas-phase geometry is a documented approximation, not a solvent-optimized structure. Gaussian `SCRF` and ORCA `%cpcm`/native solvent syntax are not interchangeable. Adding either to an external MLIP job does not establish that the external potential includes solvent response.

Basis and solvation definitions: [ORCA basis sets](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/basisset.html), [implicit solvation](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/solvationmodels.html).

## 3. Cheap methods and reliability boundaries

| Tier | Useful role | Boundary |
| --- | --- | --- |
| MMFF/UFF or another classical force field | Initial clash-free structures, conformer generation within its parameterization | Fixed bonding does not describe a reactive TS surface |
| GFN-xTB | Fast conformer/geometry exploration and qualitative scans when appropriate | Path and barrier errors are reaction-dependent; a strange scan warrants diagnosis |
| A specified MLIP checkpoint | Fast energies/gradients and searches within its validated domain; final results when the task explicitly targets that model | Accuracy of training labels is not accuracy of every predicted TS; checkpoint, charge/spin and domain matter |
| DFT / higher-level calculation | Allowed production validation or a targeted method comparison | Higher cost does not guarantee the relevant electronic state or mechanism is described correctly |

Do not attach a universal kcal/mol error to one tier or assert “MLIP ≥ DFT”. If xTB and an MLIP disagree, inspect structures and model assumptions. If the higher-level calculation used only xTB geometries, it did not independently search the higher-level surface. See `mlip-gaussian-external.md` for routing and refusal discipline.

Suspect multi-reference limitations for near-degenerate states, diradicals, bond homolysis, or strongly competing spin states. Use diagnostics available from the **actual** method: wavefunction stability, spin/occupation information, or correlated diagnostics when those calculations already exist or are justified. A numerical cutoff such as T1 or ⟨S²⟩ is a warning in context, not a universal pass/fail criterion.

r2SCAN/TPSS can be allowed sensitivity checks in some systems; agreement with them does not repair strong multi-reference physics or license a quantitative barrier. Do not prescribe CASSCF/NEVPT2/CASPT2 without the expertise, scope and allowed-method support to define that calculation. If no permitted method can support the requested claim, explain why and refuse that claim. An optimizer failing repeatedly alone is not that diagnosis.

## 4. Thermochemistry only when needed

Use electronic energies directly for a requested ΔE‡. Do not substitute ΔG‡ or experimental Arrhenius Ea; these quantities and their references differ.

For free energies, retain temperature/pressure from the source, the target concentration/standard state, frequency treatment and energy sources. In a composite protocol, `G_composite = E_high + (G_low − E_low)` at each structure before taking stoichiometric differences. `thermo_analysis` takes signed stoichiometric coefficients and distinguishes raw RRHO from the explicit GoodVibes treatment. Missing data/backend support means incomplete analysis, not silent fallback.

**Current adapter limit:** `thermo_analysis backend="raw_rrho"` extracts Gaussian thermochemistry only. For ORCA, `log_parser` exposes native totals/corrections; use those structured values in a transparent, saved arithmetic table when they suffice for the requested quantity, retaining units and state conventions. For quasi-harmonic corrections, verify installed GoodVibes/backend support for those logs. An unsupported thermochemistry adapter does not justify rerunning a completed ORCA frequency job or relabeling its output as Gaussian. Report any unmet correction or delivery requirement.

- Use a documented frequency scale factor for the actual method/basis when required; do not copy a universal 0.96. Consult [NIST frequency-scaling data](https://cccbdb.nist.gov/vibscalejust.asp).
- Low-frequency modes can make harmonic entropies unstable; choose and report the quasi-harmonic treatment when the requested accuracy needs it. Keep ZPE and thermal corrections distinct from total H/G.
- Treat accessible conformers consistently for reactants and TSs; the lowest initial conformer is not necessarily the relevant reactive conformer. State whether populations/equilibration justify combining them.
- Eyring's `k = (k_B T/h) exp(−ΔG‡/RT)` assumes an appropriate transition-state-theory model and standard state. Bimolecular rate constants need the corresponding concentration convention. Hydrogen-transfer rates/KIE may need tunneling and isotope treatment; request that work when it resolves the user's question.
- ΔΔG‡ can predict selectivity under the relevant kinetic assumptions. Reversibility, competing resting states and subsequent chemistry can change observed selectivity; a barrier table alone does not settle those effects.
