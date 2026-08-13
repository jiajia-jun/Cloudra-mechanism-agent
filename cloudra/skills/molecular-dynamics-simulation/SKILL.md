---
name: molecular-dynamics-simulation
description: Provide domain expertise for classical molecular dynamics (MD) simulations using GROMACS, AMBER, etc. Use when selecting force fields, configuring MDP parameters, determining equilibration/production protocols, setting up enhanced sampling or free energy calculations, and diagnosing trajectory issues.
license: MIT
metadata: {"original-skill": "molecular-dynamics", "source": "https://github.com/K-Dense-AI/scientific-agent-skills", "adapted-by": "Cloudra"}
---

# 1. Local toolchain mapping (Toolchain Mapping)
When running molecular dynamics (MD), you must map the underlying theory onto an executable code path:
- **Topology and configuration generation**: prefer Python scripts for complex MDP files. For a specific force field (e.g. CHARMM36m) or system setup, never use blind global regex replacement; use a dedicated config parser for key–value pairs.
- **OpenMM toolchain**: with OpenMM, use `pdbfixer` to repair PDBs, `Modeller.addHydrogens` to add hydrogens, `Modeller.addSolvent` for the solvent box, and `ForceField.createSystem` to build the system. OpenMM supports CUDA / OpenCL / CPU automatic fallback, and `StateDataReporter`, `DCDReporter`, `CheckpointReporter` for logs, trajectories, and checkpoints.
- **Job dispatch**: every MD stage (EM, NVT, NPT, Production) is compute-heavy; you must call `submit_compute_job` with `is_async=True` and run in the background.
- **Trajectory monitoring and status**: do not read raw large binary `.trr` / `.xtc` files. Use a local wrapper to extract thermodynamic quantities (e.g. `gmx energy` output), or use `MDAnalysis` to programmatically analyze RMSD, RMSF, contact matrices, etc., and automatically judge density, temperature, and energy convergence.

# 2. Constraints and exceptions (Constraints & Exceptions)
The following are common MD best practices, with reasonable exceptions. When they conflict, prefer **the official notes for the current force-field version and the system’s character**.

1. **Force-field pairing red line**: water models and ion parameters should match the chosen biomolecular force field. Mixing parameters can introduce systematic error, but not every mix “destroys the system”.
   - AMBER (e.g. ff19SB) common pairings: OPC, TIP3P-FB, or TIP4P-Ew.
   - CHARMM (e.g. CHARMM36m) common pairing: CHARMM-modified TIP3P (mTIP3P).
   - If you must mix (e.g. small-molecule GAFF ligand + CHARMM protein), validate against literature or benchmarks and interpret results cautiously.
2. **Thermostat / barostat red line**:
   - **Production**: prefer a barostat that yields the correct ensemble, such as `Parrinello-Rahman`, `C-rescale`, or `MTTK`; recommended thermostats are `Nosé-Hoover` or `v-rescale`.
   - **Pre-equilibration**: `Berendsen` thermo/barostats are still often used for initial relaxation because they converge quickly and are stable, but they **do not strictly correspond to any ensemble**. GROMACS officially advises against Berendsen for new production simulations.
   - If the system is sensitive to pressure coupling (membranes/interfaces, position-restrained systems), stabilize first with `Berendsen` or `C-rescale`, then switch to `Parrinello-Rahman`.
3. **Ion-model choice**:
   - For high charge-density, tightly coordinated transition-metal ions (e.g. Zn²⁺, Mg²⁺, Mn²⁺ at enzyme active sites), a standard 12-6 Lennard-Jones model may simultaneously over- and underestimate hydration free energy and coordination distance; consider a **12-6-4 model** or a **bonded model**.
   - For simple monovalent ions in dilute solution or weakly coordinating environments, 12-6 is usually enough.

# 3. Scientific knowledge base: force fields and parameters (Scientific Knowledge Base)

## 3.1 Cutoffs and long-range interactions
- **PME (Particle Mesh Ewald)**: the standard electrostatics method; almost always recommended.
- **Cutoff distance**:
  - AMBER family: commonly `0.8`–`1.0` nm; follow the force-field version notes.
  - CHARMM36/CHARMM36m: traditionally `1.2` nm with force-switch (`vdw-modifier = Force-switch`, `rvdw-switch = 1.0`). Later CHARMM36m literature also uses `1.0` nm or a shifted switch start, so follow the official/benchmark paper.
- **Dispersion correction (dispcorr)**:
  - Homogeneous solvent systems may enable `EnerPres`.
  - Lipid membranes, interfaces, or heterogeneous systems usually **turn it off**, because dispersion correction can change interfacial tension.

## 3.3 OpenMM and Python analysis toolchain

*Some code examples and best practices in this section are adapted from K-Dense-AI/scientific-agent-skills (MIT License). The original skill targets OpenMM + MDAnalysis; here it is rewritten and extended for Cloudra’s GROMACS/AMBER/CHARMM workflow.*

### Quick force-field and system selection

| System | Recommended Force Field | Water Model |
|--------|------------------------|-------------|
| Standard proteins | AMBER14 (`amber14-all.xml`) | TIP3P-FB |
| Proteins + small molecules | AMBER14 + GAFF2 / OpenFF | TIP3P-FB |
| Membrane proteins | CHARMM36m | mTIP3P / TIP3P |
| Nucleic acids | AMBER99-bsc1 or AMBER14 | TIP3P |
| Disordered proteins | ff19SB or CHARMM36m | OPC / TIP4P-Ew |

*Note: CHARMM protein systems should prefer CHARMM36m + mTIP3P; AMBER protein systems may pair with OPC, TIP3P-FB, or TIP4P-Ew. Small-molecule ligands commonly use GAFF2 or OpenFF; after parameterization, always check charges and rotatable bonds.*

### Minimal runnable OpenMM EM → NVT → NPT example

The following shows a complete OpenMM equilibration flow; adjust parameters to the real system.

```python
from openmm.app import *
from openmm import *
from openmm.unit import *

# 1. Prepare the system
pdb = PDBFile('cleaned.pdb')
forcefield = ForceField('amber14-all.xml', 'amber14/tip3pfb.xml')
modeller = Modeller(pdb.topology, pdb.positions)
modeller.addHydrogens(forcefield)
modeller.addSolvent(forcefield, model='tip3p', padding=10*angstroms,
                    ionicStrength=0.15*molar)

system = forcefield.createSystem(
    modeller.topology,
    nonbondedMethod=PME,
    nonbondedCutoff=1.0*nanometer,
    constraints=HBonds,
    rigidWater=True,
    ewaldErrorTolerance=0.0005
)

# 2. Platform selection: CUDA -> OpenCL -> CPU
for platform_name, props in [('CUDA', {'DeviceIndex': '0', 'Precision': 'mixed'}),
                             ('OpenCL', {}),
                             ('CPU', {})]:
    try:
        platform = Platform.getPlatformByName(platform_name)
        properties = props
        break
    except Exception:
        continue

# 3. Energy minimization
integrator = LangevinMiddleIntegrator(300*kelvin, 1/picosecond, 0.002*picoseconds)
simulation = Simulation(modeller.topology, system, integrator, platform, properties)
simulation.context.setPositions(modeller.positions)
simulation.minimizeEnergy(maxIterations=1000)

# 4. NVT equilibration (100 ps)
simulation.context.setVelocitiesToTemperature(300*kelvin)
simulation.reporters = [
    StateDataReporter('nvt_log.txt', 1000, step=True, temperature=True,
                      potentialEnergy=True, speed=True),
    DCDReporter('nvt_traj.dcd', 1000)
]
simulation.step(50000)

# 5. NPT production (1 ns)
system.addForce(MonteCarloBarostat(1.0*bar, 300*kelvin, 25))
simulation.context.reinitialize(preserveState=True)
simulation.reporters = [
    StateDataReporter('npt_log.txt', 5000, step=True, temperature=True,
                      density=True, potentialEnergy=True, speed=True),
    DCDReporter('npt_traj.dcd', 5000),
    CheckpointReporter('npt_checkpoint.chk', 50000)
]
simulation.step(500000)
```

### MDAnalysis trajectory-analysis example

```python
import MDAnalysis as mda
from MDAnalysis.analysis import rms, align, contacts
import numpy as np

u = mda.Universe('topology.pdb', 'npt_traj.dcd')

# RMSD (after alignment)
align.AlignTraj(u, u, select='backbone', in_memory=True).run()
R = rms.RMSD(u, select='backbone', ref_frame=0)
R.run()
rmsd_data = R.results.rmsd  # columns: frame, time, RMSD

# RMSF (residue-averaged)
atoms = u.select_atoms('backbone')
RMSF = rms.RMSF(atoms)
RMSF.run(start=int(0.2 * u.trajectory.n_frames))  # discard first 20%

# Protein–ligand contact analysis
protein = u.select_atoms('protein')
ligand = u.select_atoms('resname LIG')
contact_residues_per_frame = []
for ts in u.trajectory[int(0.2 * u.trajectory.n_frames):]:
    dist = contacts.contact_matrix(protein.positions, ligand.positions, radius=4.5)
    contact_residues_per_frame.append({protein.atoms[i].resid
                                        for i in range(dist.shape[0])
                                        if dist[i].any()})
```

### PDB preprocessing (PDBFixer)

```python
from pdbfixer import PDBFixer
from openmm.app import PDBFile

def fix_pdb(input_pdb, output_pdb, ph=7.0):
    fixer = PDBFixer(filename=input_pdb)
    fixer.findMissingResidues()
    fixer.findNonstandardResidues()
    fixer.replaceNonstandardResidues()
    fixer.findMissingAtoms()
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(ph)
    with open(output_pdb, 'w') as f:
        PDBFile.writeFile(fixer.topology, fixer.positions, f)
    return output_pdb
```

*Note: PDBFixer’s `removeHeterogens(True)` deletes water and small-molecule ligands. To keep a ligand, explicitly retain the corresponding residue, or use another parameterization path.*

### Small-molecule parameterization (OpenFF / GAFF2)

```python
from openff.toolkit import Molecule
from openff.interchange import Interchange
from openff.toolkit import ForceField as OFFForceField

mol = Molecule.from_smiles('CCO')  # example: ethanol
mol.generate_conformers(n_conformers=1)
off_ff = OFFForceField('openff-2.0.0.offxml')
interchange = off_ff.create_interchange(mol.to_topology())
# can later export as OpenMM System or GROMACS topology
```

## 3.4 General best practices

- **Always minimize before MD**: raw PDBs often have steric clashes; EM is essential.
- **Equilibrate before production**: NVT (50–100 ps) → NPT (100–500 ps) → Production.
- **Use GPU when available**: OpenMM on CUDA/OpenCL is typically 10–100× faster than CPU.
- **2 fs timestep with HBonds constraints**: standard; with HMR (hydrogen mass repartitioning) you may try 4 fs.
- **Analyze only equilibrated trajectory**: usually discard the first 20–50% as equilibration.
- **Save checkpoints**: MD can interrupt; checkpoints support restart.
- **Periodic boundary conditions**: solvated systems must handle PBC correctly.
- **PME for electrostatics**: prefer PME over a simple cutoff for charged systems.

## 3.5 References

- [OpenMM documentation](https://openmm.org/documentation.html)
- [MDAnalysis user guide](https://docs.mdanalysis.org/)
- [GROMACS manual](https://manual.gromacs.org/)
- [NAMD](https://www.ks.uiuc.edu/Research/namd/)
- [CHARMM-GUI](https://charmm-gui.org/)
- [AmberTools](https://ambermd.org/AmberTools.php)
- Eastman P et al. (2017) PLOS Computational Biology. PMID: 28278240
- Michaud-Agrawal N et al. (2011) J Computational Chemistry. PMID: 21500218
- Original OpenMM/MDAnalysis skill: [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) (MIT License)

# 5. Diagnostics and circuit breakers (Circuit Breakers)
If the system crashes in the first few nanoseconds, you must diagnose these classic dead-ends from the logs:

1. **Flying ice cube**:
   - Symptom: the system appears frozen, but temperature spikes.
   - Fix: remove center-of-mass translation: `comm-mode = Linear`, `nstcomm = 100`.
2. **Vacuum bubbles and box explosion**:
   - Symptom: NPT reports LINCS breaks after a few steps; atoms collide violently.
   - Fix: usually too little solvent padding. Return to solvation and enlarge the box, or use a 0.5 fs timestep in early NVT/NPT.
3. **Ligand wildly escaping the pocket**:
   - Symptom: the ligand unbinds from the protein on a short timescale.
   - Fix: check Antechamber ligand charge fitting; very likely the ligand charges are completely wrong and cause electrostatic repulsion.
