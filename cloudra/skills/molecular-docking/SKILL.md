---
name: molecular-docking
description: Provide domain expertise for Molecular Docking workflows (e.g., AutoDock Vina, GNINA). Use when setting up docking protocols, preparing proteins/ligands, identifying binding sites, defining grid boxes, performing post-docking analysis (MM-GBSA), and experimental validation.
---

# 1. Local toolchain mapping (Toolchain Mapping)
When running molecular docking, map the theoretical pipeline onto the current execution environment:
- **Molecule preprocessing**: use `CLOUDRA` internal `Chemtool` or the Python environment (RDKit, OpenBabel). Confirm protonation of titratable groups before docking; do not strip a PDB and start immediately.
- **Pocket prediction and definition**: if there is no co-crystal ligand, prefer pocket predictors such as `fpocket` rather than blindly setting XYZ by hand.
- **Job dispatch**: submit background docking with `submit_compute_job`; manage high-throughput or large conformational scoring in parallel with `is_async=True`.
- **Post-processing validation**: write or call a script to compute RMSD of the Top 1 pose vs the true crystal conformation as a quantitative check.

# 2. Constraints and exceptions (Constraints & Exceptions)
The following are common best practices; adjust them to the research goal.

1. **Blind docking**: for high-precision screening, focus the grid box on the co-crystal ligand or a predicted pocket. Whole-protein “blind docking” can be used for exploratory work (unknown targets, natural-product target fishing), but interpret results cautiously and follow up with pocket prediction, biological experiment, or MD. [CobDock blind docking](https://pmc.ncbi.nlm.nih.gov/articles/PMC10785400/) [Refining docking protocols](https://www.benchchem.com/pdf/Technical_Support_Center_Refining_Molecular_Docking_Protocols_for_Natural_Products.pdf)
2. **Covalent docking**: standard Vina does not handle covalent bonds. For covalent inhibitors (e.g. Cys-targeting), switch to AutoDock4, CovDock, GOLD, or another covalent method; Vina may be used for non-covalent pre-screening but not as the final evidence of a covalent binding mode.
3. **Metal coordination**: Vina’s scoring function is weak for Zn²⁺, Fe³⁺, and similar metal coordination; prefer AutoDock4Zn, GOLD, Glide, or other specialized methods. When data are limited and you only need a fast ranking, treat Vina as a reference only.
4. **Water treatment**: usually delete crystal waters to reduce false positives; keep them if the literature or a pre-calculation clearly identifies a key bridging water in the pocket.

# 3. Scientific knowledge base: ligand and receptor preparation (Scientific Knowledge Base)
Treat this section as a pre-flight checklist before submitting a docking job.

## 3.1 Extreme preparation of the protein receptor
- **Resolution**: prefer crystal structures with resolution < 2.5 Å.
- **Protonation states**: pKa of titratable residues at physiological pH (~7.4) must be predicted in advance. Pay special attention to histidine near the pocket and confirm HID, HIE, or HIP.
- **Residue repair**: missing heavy atoms must be repaired, or force-field calculations will hit vacancy errors.

## 3.2 Ligand parameterization
- **3D conformational optimization**: if the input is SMILES only, prefer `smiles_to_mol` with `generate_3d=True`.
- **Physiological ionization**: confirm the state at pH 7.4 (e.g. -COOH becomes -COO⁻).
- **Charges**: ordinary Vina can use default charges; if you later go to MM-GBSA, generate high-quality **AM1-BCC charges**.

# 4. Agent workflow: standard molecular-docking pipeline (Workflow State Machine)

**Step 1: Binding-site detection and box setup**
- *With a co-crystal ligand*: take the geometric centroid of the co-crystal ligand as the grid-box center. Extend each side by 5–10 Å (usually not beyond 30×30×30 Å).
- *Without a co-crystal ligand*: center on the highest-scoring pocket from a predictor (e.g. fpocket); preferably cross-check with biological mutation data.

**Step 2: Docking parameters and execution**
- `exhaustiveness`:
  - HTVS (high-throughput): 8.
  - Fine docking / large flexible molecules: 32–64. Higher values cost more time with diminishing returns.
- Launch `submit_compute_job` asynchronously.

**Step 3: Re-docking validation gold standard**
- Before scoring new ligands, re-dock the original co-crystal ligand.
- If Top 1 pose **RMSD > 2.0 Å**, the current box or sampling may be unsuitable; return to Step 1 to adjust box size, raise exhaustiveness, consider flexible residues, or change the docking program — do not immediately declare all results meaningless.

**Step 4: Post-processing rescoring**
- Take top poses as starting points; do not trust the Vina score alone.
- Recommended workflow: import into Amber/GROMACS for a very short MD, or compute binding free energy with MM-GBSA, to include the desolvation penalty.

# 5. Diagnostics and circuit breakers (Circuit Breakers)
1. **All scores extremely poor (>0 kcal/mol)**:
   - Check whether hydrogenation of ligand and protein produced severe steric clashes.
   - Check whether the grid box missed the pocket center and squeezed the ligand out.
2. **False positives for large molecules**:
   - Vina scores have a size-additive effect. If ligand molecular weight is large, divide by heavy-atom count and re-evaluate with ligand efficiency (LE).
3. **Missing key interactions**:
   - Verify by script or interactive feedback: if the top-scoring pose fails to form a known core hydrogen bond of the target pocket, question that pose, but do not reject it outright; correct with MD or rescoring.

# 6. Minimal runnable Vina Python example
The following shows only the standard call flow; adjust parameters to the real system. No comments in the example, to avoid parse issues.

```python
from vina import Vina

v = Vina(sf_name='vina')
v.set_receptor('receptor.pdbqt')
v.set_ligand_from_file('ligand.pdbqt')
v.compute_vina_maps(center=[10.0, 20.0, 30.0], box_size=[20, 20, 20])
energy = v.score()
v.dock(exhaustiveness=32, n_poses=9)
v.write_poses('output_poses.pdbqt', n_poses=5, overwrite=True)
```
