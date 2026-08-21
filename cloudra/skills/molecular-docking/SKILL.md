---
name: molecular-docking
description: Domain expertise for molecular docking workflows (AutoDock Vina, GNINA, Vinardo). Use when preparing protein receptors (PDBFixer, protonation, tautomers), generating 3D ligand conformers (RDKit, Meeko, AM1-BCC/Gasteiger charges), defining grid boxes, validating via re-docking (RMSD < 2.0 Å), analyzing interaction fingerprints (PLIF, hydrogen bonds, pi-stacking), and evaluating ligand efficiency (LE, LLE) or preparing poses for MD/MM-GBSA rescoring.
---

# Molecular Docking Standard Operating Procedure (SOP)

This skill guides high-fidelity protein-ligand and receptor-substrate molecular docking, spanning receptor clean-up, ligand parameterization, grid-box calibration, docking execution, and post-docking interaction fingerprinting.

---

## 1. Local Toolchain Mapping

Anchor docking tasks in the `CLOUDRA` toolchain and Python ecosystem:

- **Receptor Preprocessing**: Use `PDBFixer` to repair missing heavy atoms/loops, remove non-structural heteroatoms, and assign protonation states at physiological pH (~7.4).
- **Ligand Preparation**: Convert SMILES to 3D structures via `smiles_to_mol(generate_3d=True)` or RDKit (`AllChem.EmbedMolecule` with `ETKDGv3`). Assign Gasteiger or AM1-BCC charges and convert to PDBQT format using `Meeko` (`mk_prepare_ligand.py`) or OpenBabel.
- **Pocket Detection & Grid Box**: If a co-crystal ligand exists, center the grid box on the ligand's geometric centroid. For unliganded apo-structures, detect binding pockets using `fpocket`.
- **Docking Engines**:
  - **AutoDock Vina**: Standard fast empirical scoring (Vina / Vinardo scoring functions).
  - **GNINA**: Deep learning enhanced docking with CNN scoring (`--cnn_scoring rescore/refinement`) for superior pose ranking and binding affinity prediction.
- **Job Submission**: Call `submit_compute_job` with `is_async=True` for high-throughput screening (HTVS) or exhaustiveness sweeps.
- **Post-Docking Analysis**: Compute RMSD relative to co-crystal reference, perform pose clustering, and extract Protein-Ligand Interaction Fingerprints (PLIF: hydrogen bonds, $\pi$-$\pi$ stacking, salt bridges, halogen bonds) via Python/PLIP.

---

## 2. Constraints & Physical Red Lines

1. **Receptor Quality Criteria**:
   - Prefer crystal structures with resolution $< 2.5\text{ \AA}$. Check for missing loops near the binding pocket.
2. **Protonation & Tautomer States (pH 7.4)**:
   - Titratable residues must be checked (PROPKA).
   - **Histidine Tautomers**: Inspect pocket hydrogen-bonding networks to assign $\text{HID}$ ($\delta$-nitrogen protonated), $\text{HIE}$ ($\epsilon$-nitrogen protonated), or $\text{HIP}$ (doubly protonated cation).
   - **Cysteines**: Distinguish catalytic free thiols ($\text{CYS}$) from structural disulfide bridges ($\text{CYX}$).
3. **Crystallographic Water Policy**:
   - Default rule: Strip bulk crystallographic water molecules to reduce false-positive sterics.
   - **Exception (Structural Waters)**: Retain tightly bound, conserved structural waters that mediate essential bridging hydrogen bonds between ligand and receptor (verified across multiple PDB structures).
4. **Blind Docking Limits**:
   - Blind docking (whole-protein search box) is exploratory only (target fishing, allosteric site search). For quantitative ranking, always use a focused grid box centered on the pocket.
5. **Covalent & Metalloenzyme Boundaries**:
   - Standard Vina does not model covalent bond formation (e.g., covalent cysteine inhibitors). Use specialized tools (CovDock, AutoDock4) or constrain reactive distances.
   - For metal-binding pockets ($\text{Zn}^{2+}, \text{Mg}^{2+}, \text{Fe}^{2+/3+}$), standard Vina electrostatics are insufficient; treat scores qualitatively and validate with MD / QM/MM.

---

## 3. Preparation & Execution Protocol

### 3.1 Receptor Clean-Up Protocol
```python
from pdbfixer import PDBFixer
from openmm.app import PDBFile

def prepare_receptor(pdb_id_or_file, output_pdb, ph=7.4):
    fixer = PDBFixer(filename=pdb_id_or_file)
    fixer.findMissingResidues()
    fixer.findNonstandardResidues()
    fixer.replaceNonstandardResidues()
    fixer.findMissingAtoms()
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(ph)
    # Remove solvent while keeping verified hetero ligands if desired
    fixer.removeHeterogens(keepWater=False)
    with open(output_pdb, 'w') as f:
        PDBFile.writeFile(fixer.topology, fixer.positions, f)
```

### 3.2 Ligand 3D & PDBQT Generation Protocol (Meeko)
```python
from rdkit import Chem
from rdkit.Chem import AllChem
from meeko import MoleculePreparation, PDBQTWriterLegacy

def prepare_ligand_from_smiles(smiles, output_pdbqt):
    mol = Chem.MolFromSmiles(smiles)
    mol = Chem.AddHs(mol)
    # Generate 3D conformer via ETKDG
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    AllChem.EmbedMolecule(mol, params)
    AllChem.MMFFOptimizeMolecule(mol)
    
    # Setup Meeko preparation (rotatable bonds, Gasteiger charges)
    preparator = MoleculePreparation()
    mol_setups = preparator.prepare(mol)
    pdbqt_string = PDBQTWriterLegacy.write_string(mol_setups[0])
    
    with open(output_pdbqt, 'w') as f:
        f.write(pdbqt_string)
```

### 3.3 Grid Box Calibration & Sizing
- **Center**: Set coordinates $(x, y, z)$ to the geometric center of the bound co-crystal ligand:
  $$\mathbf{r}_{\text{center}} = \frac{1}{N_{\text{heavy}}} \sum_{i=1}^{N_{\text{heavy}}} \mathbf{r}_i$$
- **Dimensions**: Add $8 \sim 12\text{ \AA}$ padding around the ligand envelope. Typical box sizes range from $18\times 18\times 18\text{ \AA}$ to $25\times 25\times 25\text{ \AA}$. Avoid excessively large boxes ($> 30\text{ \AA}$), which dilute conformational sampling.

---

## 4. End-to-End Docking Workflow

```
[1. Clean Receptor (PDBFixer)]      [1. Ligand 3D & PDBQT (Meeko)]
             \                                    /
              \                                  /
          [2. Re-docking Validation (RMSD < 2.0 Å)]
                           │
          [3. Production Docking (Vina / GNINA)]
           - exhaustiveness = 32 ~ 64
           - output top 9 poses
                           │
          [4. Post-Docking Analysis & Fingerprints]
           - Pose RMSD clustering (cutoff 2.0 Å)
           - Interaction profiling (H-bonds, pi-stacking, salt bridges)
           - Ligand Efficiency (LE, LLE) evaluation
                           │
          [5. Candidate Pose Export -> MD / MM-GBSA Rescoring]
```

### 4.1 Re-Docking Validation (Gold Standard)
Before docking novel compounds, extract the native co-crystal ligand, prepare it, and re-dock it into the prepared receptor.
- **Pass Criterion**: Top 1 pose **RMSD $\le 2.0\text{ \AA}$** relative to the original crystal pose.
- **Failure Remedy**: If RMSD $> 2.0\text{ \AA}$, do not proceed. Increase `exhaustiveness`, adjust grid-box boundaries, or verify histidine protonation.

### 4.2 Scoring & Efficiency Metrics
Do not rely exclusively on raw Vina score (kcal/mol), as it has an additive molecular weight bias.

1. **Ligand Efficiency (LE)**:
   $$\text{LE} = \frac{-\Delta G_{\text{bind}}}{N_{\text{heavy}}} \quad (\text{kcal/mol per heavy atom})$$
   - Acceptable drug-like benchmark: $\text{LE} \ge 0.30\text{ kcal/mol/heavy atom}$.
2. **Lipophilic Ligand Efficiency (LLE)**:
   $$\text{LLE} = \text{p}K_i - \text{cLogP} \approx \frac{-\Delta G_{\text{bind}}}{1.363} - \text{cLogP}$$
   - Measures potency gained per unit of lipophilicity. Benchmark: $\text{LLE} \ge 5.0$.

---

## 5. Diagnostics & Troubleshooting

1. **All binding scores positive ($> 0\text{ kcal/mol}$)**:
   - Severe steric clashes: Check if receptor hydrogen addition placed protons too close to active site residues.
   - Grid box offset: Verify that the box center actually encloses the cavity.
2. **High score but missing key pharmacophore interaction**:
   - The top pose lacks a known catalytic hydrogen bond: Inspect next top-ranked poses in the cluster ensemble (poses 2–5). Often, poses with slightly higher Vina energy ($+0.5\text{ kcal/mol}$) exhibit correct geometry.
3. **Flexible Loop Movements**:
   - In induced-fit binding pockets, rigid-receptor docking fails. Consider flexible residue docking (`--flex`) on 1–3 gating residues, or perform ensemble docking against multiple MD snapshots.
