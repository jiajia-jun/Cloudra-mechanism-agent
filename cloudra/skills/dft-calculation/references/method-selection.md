# Method, basis and thermochemistry choices

Read when the method is not already fixed, when interpreting its limits, or when free energies/properties are requested. The mechanism SOP determines which calculations are needed; this reference helps choose their level. Engine keyword spelling belongs in `orca-inputs.md` / `gaussian-inputs.md`.

## 1. Select a level for the claim

Keep the user's current calculation requirements, budget and actual software availability first. Only active Benchmark projects apply their actual task MethodPolicy; ordinary research projects have no default method/basis whitelist. Do not infer restrictions from global configuration, examples or earlier tasks. If a production level is specified, use it consistently rather than selecting another functional for every job. With a free choice, use benchmarks close to the reaction class, charge/spin state and requested property. No universal accuracy order covers DFT, double hybrids, coupled cluster, xTB and MLIPs. General method-selection guidance: [ORCA recommendations](https://www.faccts.de/docs/orca/6.1/manual/contents/quickstartguide/recommendations.html).

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

Suspect multi-reference limitations for near-degenerate states, diradicals, bond homolysis, or strongly competing spin states. Use diagnostics available from the **actual** method: wavefunction stability, spin/occupation information, or correlated diagnostics when those calculations already exist or are justified. **A numerical cutoff such as T1 or ⟨S²⟩ is a warning in context, not a universal pass/fail criterion.** For open-shell work this skill uses **deviation ≳0.1 on ⟨S²⟩** as a *practical trigger* to discount single-reference barrier claims, re-check spin density/stability, and (when justified) apply spin projection — never as an automatic binary fail, and never as a reason to invent a wavefunction diagnostic an MLIP cannot emit. Modeling files that mention `0.1` mean this same trigger; this section is the authority on how to respond.

r2SCAN/TPSS can be allowed sensitivity checks in some systems; agreement with them does not repair strong multi-reference physics or license a quantitative barrier. Do not prescribe CASSCF/NEVPT2/CASPT2 without the expertise, scope and allowed-method support to define that calculation. If no permitted method can support the requested claim, explain why and refuse that claim. An optimizer failing repeatedly alone is not that diagnosis.

## 4. Thermochemistry only when needed

Use electronic energies directly for a requested ΔE‡. Do not substitute ΔG‡ or experimental Arrhenius Ea; these quantities and their references differ.

For free energies, retain temperature/pressure from the source, the target concentration/standard state, frequency treatment and energy sources. In a composite protocol, `G_composite = E_high + (G_low − E_low)` at each structure before taking stoichiometric differences. `thermo_analysis` takes signed stoichiometric coefficients and distinguishes raw RRHO from the explicit GoodVibes treatment. Missing data/backend support means incomplete analysis, not silent fallback.

### 4.1 Operational free-energy checklist (required for any ΔG‡ / ΔΔG‡ delivery)

1. **Same surface for opt/freq** (and IRC when connectivity is claimed). A higher-level single point is an explicit composite correction, labeled as such.
2. **Standard state (1 atm ↔ 1 M).** RRHO ideal-gas entropy is a 1 atm standard state (molar volume `RT/P° ≈ 24.46 L mol⁻¹` at 298.15 K). Convert every profile to the **1 M solution standard state** before comparing to solution kinetics or to other 1 M profiles:
   `ΔG°(1 M) = ΔG°(1 atm) + Δn · R T · ln(24.46)`
   with `Δn = n_species(TS-side) − n_species(reference-side)` (e.g. A+B→TS has `Δn = −1`, so **add `RT ln(24.46) ≈ 1.89 kcal mol⁻¹` at 298.15 K** to a bimolecular ΔG‡). State T, the standard state, and whether the correction was applied. Unimolecular steps (`Δn = 0`) need no concentration correction.
3. **Quasi-harmonic treatment when low modes matter.** Harmonic RRHO entropies diverge for floppy modes. **Project default: Grimme-style quasi-RRHO with a 100 cm⁻¹ frequency cutoff** (GoodVibes `--freespace` / quasi-RRHO family). Report cutoff, backend/version, and whether frequencies were scaled. Do not silently mix raw RRHO and quasi-RRHO species in one profile.
4. **Conformer populations.** If more than one conformer is thermally accessible for a reactant or TS ensemble, combine with a Boltzmann sum at the stated T:
   `G_eff = −RT ln Σᵢ exp(−Gᵢ/RT)` (degeneracy factors `gᵢ` multiply each term when symmetry-distinct).
   Apply the same rule to both sides of ΔΔG‡. “Lowest conformer only” is allowed only when others are shown negligible (e.g. ≳3–4 kcal mol⁻¹ above at that T) and that claim is recorded.
5. **Cross-engine thermochemistry.** `thermo_analysis backend="raw_rrho"` is **Gaussian-only**. For ORCA use `log_parser` native totals/corrections in a saved arithmetic table (or a verified GoodVibes path on those logs). **Never mix Gaussian `raw_rrho` totals and ORCA native G in one profile** without an explicit, written bridge. An unsupported adapter does not justify rerunning a finished frequency job or relabeling its engine.
6. **Uncertainty on delivered barriers.** Every reported ΔG‡/ΔΔG‡ carries a method-sensitivity note (typical DFT spread on main-group barriers is several kcal mol⁻¹; state what was checked: basis, conformer, standard state, quasi-harmonic). Selectivity claims with |ΔΔG‡| ≲ 2 kcal mol⁻¹ must flag that the prediction is inside normal method noise unless higher-level validation is cited.

- Use a documented frequency scale factor for the actual method/basis when required; do not copy a universal 0.96. Consult [NIST frequency-scaling data](https://cccbdb.nist.gov/vibscalejust.asp) (or the installed CCCBDB mirror). Keep ZPE and thermal corrections distinct from total H/G.
- Eyring's `k = (k_B T/h) exp(−ΔG‡/RT)` assumes an appropriate transition-state-theory model and **the same standard state used in ΔG‡**. Bimolecular rate constants need the corresponding concentration convention (1 M). Hydrogen-transfer rates/KIE may need tunneling and isotope treatment; request that work when it resolves the user's question.
- ΔΔG‡ can predict selectivity under the relevant kinetic assumptions. Reversibility, competing resting states and subsequent chemistry can change observed selectivity; a barrier table alone does not settle those effects.
- **Literature-backed judgment:** when choosing standard-state conventions, quasi-harmonic settings, or whether a barrier claim is trustworthy, search AgentHub and the literature (researcher / `literature-search`) before inventing a number. Cite the protocol you followed in the delivery summary.
