# Modeling sanity: the pre-compute audit and the unreasonable-modeling blacklist

A core-hour spent on a bad model is worse than no result: it produces confident wrong numbers. Run this audit **before** any barrier/mechanism compute; any "no" means fix the model first.

## 1. The audit checklist

1. **Solvent & charge.** Does the mechanism involve ions, zwitterions, or strong charge separation? Then nothing runs in vacuum: geometry, frequencies, TS, IRC all in implicit solvent from the start. Gas-phase optimization + solvent single-point does **not** rescue a wrong gas-phase stationary point — the TS geometry and charge distribution rearrange with solvent.
2. **Counterions & explicit solvent.** In low-polarity solvents (THF, toluene, CH₂Cl₂, ethers), charged intermediates need explicit counterions (inner-sphere ion pairs) — ion-pair state changes barriers and selectivity by several kcal/mol and can flip mechanisms. Alkali cations must be coordination-saturated (explicit solvent/ donors), never bare Na⁺. For proton transfer, never model a bare H⁺: use the actual acid/base pair (H₃O⁺/H₂O, substrate conjugate pair), and for long-range proton shuttles add 2–3 explicit waters (Grotthuss relay) on top of the continuum.
3. **Conformer sampling.** Flexible molecule (rotatable chains, multiple coordination poses, H-bond networks)? `conformer_search` first. Whenever there is any possibility of forming hydrogen bonds (intramolecular or intermolecular), boldly use `conformer_search` (`mode="nci"` for non-covalent complexes/networks). Conformational neglect produces **qualitatively** wrong activation energies (systematically demonstrated on 300+ reactions), and TS-conformer cherry-picking can manufacture any selectivity — <1 kcal/mol of TS energy error flips predicted selectivity through the exponential. Rules of thumb: ensemble window 6 kcal/mol at the sampling level, re-rank at DFT before quoting, and map reactant↔TS conformer pairs (the lowest reactant conformer need not connect to the lowest TS conformer).
4. **Spin states.** Open-shell or transition-metal centers: screen adjacent multiplicities (±2) with opt+freq, report the spin gap. DFT spin-state ordering is functional-sensitive; a single-multiplicity mechanism is an unsupported claim.
5. **Anions in gas phase.** Before trusting a gas-phase anion minimum, check electronic stability: a positive HOMO energy is the red flag of an unbound/dipole-bound artifact. Weakly bound anions need diffuse functions (def2-SVPD/ma-/aug-); solvation usually restores a valence-bound state — re-judge with solvent on.
6. **Standard states.** QM thermochemistry is 1 atm ideal gas; solution 1 M needs **+1.89 kcal/mol (RT·ln 24.46) per gas-phase species** at 298 K on every step that changes particle count. Solvent as reactant uses its pure-liquid concentration (water 55.5 M, methanol 24.7 M), never 1 M. One solvent, one solvation model, one standard state per energy diagram.
7. **Method consistency.** Every number on one energy diagram comes from the same level (functional, basis, grid, solvation). The standard protocol "cheap-level geometries + high-level single points" is legitimate — the geometry must be a verified stationary point at its own level first. Mixing method A's energy for species X with method B's energy for species Y on the same diagram is fabrication.
8. **Charge/multiplicity bookkeeping.** Total charge and spin are declared from the actual model, never inferred from leftover files (`.CHRG`/`.UHF` residue silently changes xtb charge).

## 2. Solvation model quick reference

- Molecular DFT solvation free energies (ions, pKa, ΔG): **SMD** first choice (neutral MUE ~0.6–0.8 kcal/mol; ions several times worse — cross-validate critical values). Geometries/relative barriers: CPCM/IEF-PCM usually within 1–2 kcal/mol and cheaper.
- Engine defaults: Gaussian = IEF-PCM (`scrf=(smd,solvent=...)` for SMD); ORCA = CPCM (`! CPCM(Water)`; SMD via `%cpcm smd true`); xtb = **ALPB** (`--alpb water`; GFN0 has no ALPB parameterization — do not combine).
- Use the **actual reaction solvent's** dielectric (THF ε≈7.6, CH₂Cl₂ ≈8.9, MeCN ≈36, DMSO ≈47, water ≈78.4). ε=∞ or "water" is not a generic stand-in for "polar environment".
- Anchors worth knowing: ΔG_solv(H⁺, aq) ≈ −265.9 kcal/mol; gas-phase zwitterions are generally not minima at all (glycine zwitterion ~20 kcal/mol unstable in vacuum).
- Implicit models miss specific first-shell hydrogen bonding (F⁻, OH⁻ in water): cross-check with a few explicit waters when such groups drive the chemistry.
- Low-frequency/floppy systems: report ΔG with quasi-RRHO (~100 cm⁻¹ cutoff), never bare RRHO — soft-mode entropy diverges otherwise.

## 3. The unreasonable-modeling blacklist

Each of these has produced wrong published or published-then-retracted conclusions; treat any of them as a delivery blocker:

1. Single-conformer barrier/selectivity on a flexible molecule (see §1.3).
2. Gas-phase bare-ion mechanism presented as solution chemistry (see §1.1 — the classic S_N2 artifact: gas-phase double-well with a near-zero central barrier whose entire height in solution comes from desolvation).
3. Free proton (H⁺) as a species or reactant anywhere on the diagram.
4. Low-polarity-solvent ionic mechanism without counterions.
5. Single-multiplicity mechanism on an open-shell/transition-metal system.
6. Energies mixed across functionals/bases/grids/solvation models on one diagram; or single points on geometries never verified as stationary at their own level.
7. Constrained-optimization convergence delivered as a stationary point (frozen-direction gradient is non-zero by construction).
8. Scan peak or frozen-bond optimum delivered as a TS (it is a seed; §TS playbook).
9. TS claimed without same-level frequency, with ≠1 imaginary modes, or with the imaginary mode's displacement off the reacting heavy atoms (pseudo-saddle).
10. "Optimization completed" / exit code 0 treated as convergence (engines print their own convergence marker; Gaussian's secondary criterion can false-converge on flat surfaces — verify forces, verify with freq).
11. xTB/GFNn-xTB energies delivered as quantitative barriers (~12 kcal/mol MAE; geometry/sampling layer only).
12. Force-field geometry taken straight to a DFT single point and quoted as a barrier (garbage in, garbage out).
13. Only successful jobs reported; failed attempts deleted or left undocumented (failures are data: class, evidence, next move).
14. Numbers recalled from memory instead of grounded (literature barriers, solvation free energies, U values, correction schemes) — search literature/agent_hub first; provenance is part of the number.

## 4. The "should this model be computed at all" gate

Answer before queueing, in order; stop at the first "no":

1. Are both endpoints verified minima at the target level (opt + 0-imaginary freq)?
2. Is the atom map between endpoints complete and numbering-aligned?
3. Are charge and multiplicities correct, and (if open-shell) is a spin screen planned?
4. Do solvent model, counterions, and explicit-solvent needs reflect the stated experiment?
5. Has the flexible system been conformer-sampled, and are reactive poses verified (`internal_coordinates`)?
6. Is the seed provenance traceable (interpolation path / scan peak / NEB climbing image) — "looks like a TS" is not provenance?
7. Are method, basis, and reference data mutually consistent?
8. Is the acceptance test written down (convergence marker + same-level freq with exactly one assigned imaginary mode + IRC endpoints + barrier against verified minima)?
9. Is the budget proportionate (cheap-level pre-screen for big systems; NEB cost ∝ images)?
10. If this attempt fails, what diagnosis gets recorded and what is the next physical move? No answer → do not burn the queue yet.
