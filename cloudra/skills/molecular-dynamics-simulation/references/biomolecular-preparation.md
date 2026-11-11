# Prepare a protein or protein–ligand system

## Inspect and clean in Cloudra

Obtain the biological assembly or other coordinate model selected for the study. A deposited crystal asymmetric unit can contain fewer or more chains than the assembly of interest. Inspect the chosen file with `pdb_inspect`. [RCSB biological assemblies](https://pdb101.rcsb.org/learn/guide-to-understanding-pdb-data/biological-assemblies) · [Cloudra input schema](../../../tools/Chemtool/pdb_inspect.py#L11)

```json
{"input_path": "md/assembly.cif"}
```

Review `structure_summary`, `components`, `missing_atoms`, the gap lists, `water_candidates`, `metal_sites`, `analysis_status` and `warnings`. The default `model_index` is `0`, and omitting `chains` selects all chains in that model. Use the same `model_index` and author chain IDs for inspection and cleaning. Water and metal contacts are geometric observations. Decide which components and unresolved regions matter for the study before making changes.

Call `pdb_clean` with a new output path. This example produces PDB for a backend that expects it. Use a new `.cif` path when mmCIF is the intended handoff. [Cloudra input schema](../../../tools/Chemtool/pdb_clean.py#L12)

```json
{
  "input_path": "md/assembly.cif",
  "output_path": "md/assembly.cleaned.pdb",
  "purpose": "Prepare the selected biological assembly for classical MD",
  "mode": "md"
}
```

`mode: "md"` keeps waters, ligands and metals, selects the highest-occupancy alternate conformation per residue and adds missing heavy atoms by default. Gap rebuilding, nonstandard-residue replacement and hydrogen addition are opt-in. Copy exact `residue_key` values into `keep_residue_keys` or `remove_residue_keys` for requested exceptions. For approved gap rebuilding use `add_missing_residues` with `"internal"` or `"all"`, optionally narrowed by exact `gap_ids`. Where alternate conformations are coupled across a binding site, check the chosen residues together. [Cloudra defaults](../../../tools/core/pdb_workflow.py#L62) · [wwPDB alternate conformations](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_atom_site.label_alt_id.html)

Use `output_path` for the backend, and read `change_log_path`, `unresolved` and `warnings` before parameterization. Record modeled gaps separately from experimental coordinates. If requesting hydrogen addition in Cloudra, pass `add_hydrogens: true` and the approved `ph` explicitly. Check site-specific states and histidine tautomers, disulfides, termini, and ligand states against the selected force-field templates. OpenMM's automatic `addHydrogens()` uses residue rules and keeps existing hydrogens. Explicit variants can change the hydrogen assignment. [Knowledge cards `kb:dyn08:130`, `kb:dyn08:131`, `kb:dyn08:195`](../../../../vector_store/cards.jsonl#L16859) · [OpenMM hydrogen addition](https://docs.openmm.org/latest/api-python/generated/openmm.app.modeller.Modeller.html#openmm.app.modeller.Modeller.addHydrogens)

## Prepare the native files

- **GROMACS.** For a cleaned protein PDB covered by the chosen force field, run these commands from `md/`. Fill `GMX_FORCE_FIELD` and `GMX_WATER_MODEL` with the chosen installed model names, `PADDING_NM` with the chosen padding, and `WATER_GRO` with the solvent coordinates for that model. [GROMACS workflow](https://manual.gromacs.org/current/user-guide/flow.html) · [GROMACS topology preparation](https://manual.gromacs.org/current/onlinehelp/gmx-pdb2gmx.html)

  ```bash
  gmx pdb2gmx -f assembly.cleaned.pdb -o protein.gro -p topol.top -ff "$GMX_FORCE_FIELD" -water "$GMX_WATER_MODEL"
  gmx editconf -f protein.gro -o boxed.gro -c -d "$PADDING_NM"
  gmx solvate -cp boxed.gro -cs "$WATER_GRO" -o solvated.gro -p topol.top
  ```

  For a separately parameterized ligand, include its `.itp` and assemble matching complex coordinates and `[ molecules ]` entries before boxing and solvation. For ion placement, prepare `ions.tpr` with `gmx grompp -f ions.mdp -c solvated.gro -p topol.top -o ions.tpr`. Run `gmx genion -s ions.tpr -o system.gro -p topol.top` with the selected ion names and neutralization or salt options, then select the solvent group to replace. Use the resulting `system.gro` and updated `topol.top` for the next `grompp` call.
- **OpenMM.** Load the cleaned PDB with `PDBFile`, or mmCIF with `PDBxFile`, and pass its topology and positions to `Modeller`. Load the chosen force field and solvent/ion definitions, including any needed ligand templates. Add any extra particles required by the model. Supply a study-specific `boxSize`, `boxVectors` or `padding` to `addSolvent()` for a solution box, since omitting size can inherit the input crystal cell. Build the `System` with `ForceField.createSystem()` from the solvated topology, and keep it serialized with matching topology, positions and box vectors. If using a prepared Amber system, load `system.prmtop` with `AmberPrmtopFile` and `system.inpcrd` with `AmberInpcrdFile`. [OpenMM model building](https://docs.openmm.org/latest/userguide/application/03_model_building_editing.html) · [OpenMM running simulations](https://docs.openmm.org/latest/userguide/application/02_running_sims.html)
- **AmberTools/LEaP.** Load the selected force fields, water/ion definitions and ligand `.mol2`/`.frcmod`, then the prepared solute coordinates. Where TIP3P-FB has been selected, its AmberClassic setup file is `leaprc.water.fb3`. Confirm the solvent unit and resulting water and ion parameters for the installed version. Use `saveAmberParm` to write matching `.prmtop` and `.inpcrd`, including the periodic cell for a periodic run. [AmberClassic TIP3P-FB definition](https://github.com/Amber-MD/AmberClassic/blob/main/dat/leap/cmd/leaprc.water.fb3) · [Amber25 manual, sections 3.6–3.7 and 14](https://pureportal.spbu.ru/files/145851912/Amber25.pdf)

Check that the final coordinate order and molecule counts match the topology, then verify the intended atom types and chemical connections in the topology. Inspect unresolved templates or unsupported interactions before running. Carry native input files and parameter provenance with the coordinates.

## Choose and verify model details

- **Water and ions.** Use a documented pairing for the chosen force field and observable, with the matching ion parameter set. The ff19SB authors recommend OPC for the properties they tested. The CHARMM36m paper documents a CHARMM-modified TIP3P pairing. Treat supported alternatives according to their validation and preserve the exact variant name. [Knowledge card `kb:dyn03:28`](../../../../vector_store/cards.jsonl#L14921) · [ff19SB paper](https://doi.org/10.1021/acs.jctc.9b00591) · [CHARMM36m paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC5199616/) · [Ion parameter study](https://doi.org/10.1021/jp8001614)
- **Salt.** Record neutralization and added salt as two decisions, and report actual ion counts and net charge. In LEaP `addIons unit ion 0` neutralizes with one opposite-charge ion species. Request added salt separately when the study specifies it. OpenMM excludes neutralizing counterions from `ionicStrength`. GROMACS `genion -conc` computes added salt from cell volume, excludes ions already present from that count, and adds any requested `-neutral` counterions separately. [Amber25 manual, §14.6.5](https://pureportal.spbu.ru/files/145851912/Amber25.pdf) · [OpenMM solvation](https://docs.openmm.org/latest/userguide/application/03_model_building_editing.html#adding-solvent) · [GROMACS genion](https://manual.gromacs.org/current/onlinehelp/gmx-genion.html)
- **Ligand identity and parameters.** Use a chemically explicit SDF or Chemical Component Dictionary entry to check bond orders, stereochemistry, formal charge and the intended protonation or tautomer. Map it to the experimental or docked coordinates and preserve the intended bound pose. Use the actual ligand charge for Antechamber `-nc`, and check the output charge sum, atom order and missing or estimated parameters. GAFF2 with AmberTools, OpenFF, CGenFF with CHARMM, and Sobtop for suitable GROMACS workflows have different parameter and charge conventions. Use the route compatible with the chosen biomolecular model and review any CGenFF penalties. [Knowledge card `kb:266`](https://www.umsyar.com/266) · [计算化学公社原帖](https://bbs.keinsci.com/thread-428-1-1.html) · [wwPDB CCD](https://www.wwpdb.org/data/ccd) · [Amber developer workshop](https://yorkgrouptutorials-db4433.gitlab.io/WorkshopTutorials/2026_Amber_Workshop_SSB/Day3/HandsOn6-Param.html) · [CGenFF paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC3528813/)
- **Metal sites and covalent ligands.** Identify the oxidation state, coordination and covalent links needed by the research model. A geometric contact is a candidate to inspect. Distinguish bulk ions from a bonded or otherwise specifically parameterized site. Check that the target engine represents the chosen terms and that the model permits any coordination changes the study is meant to observe. If preprocessing reports missing bonded terms, identify the site, affected terms and parameter file before proceeding. [Knowledge cards `kb:dyn08`, `kb:635`](https://www.umsyar.com/635) · [Sobtop FAQ on bonded terms](https://www.umsyar.com/soft/Sobtop/#FAQ11) · [计算化学公社金属拓扑案例](https://bbs.keinsci.com/forum.php?mod=viewthread&tid=57683)
- **Ligand leaves the pocket.** Make the complex whole across periodic boundaries and inspect the trajectory. Compare the initial pose, contacts, protonation, charges, topology, metal/cofactor representation and initial relaxation with the intended model. If these checks pass, consider physical dissociation and look for support across independent trajectories before inferring affinity or kinetics. [Knowledge card `kb:632`](../../../../vector_store/cards.jsonl#L10591) · [计算化学公社配体脱离讨论](https://bbs.keinsci.com/thread-27434-1-1.html) · [计算化学公社跨盒案例](https://bbs.keinsci.com/thread-53952-1-1.html)
