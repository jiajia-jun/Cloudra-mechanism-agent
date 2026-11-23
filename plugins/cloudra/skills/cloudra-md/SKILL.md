---
name: cloudra-md
description: Molecular dynamics simulations, solvent-box building, protein PDB preparation, and trajectory/energy analysis (GROMACS, Packmol, PDB) via the `cloudra` MCP server.
---

# Cloudra MD Stack (`domain="md"`)

Use this skill for classical molecular dynamics, Packmol solvent boxes, PDB inspection/cleaning, and GROMACS energy/trajectory/structure/transport analyses (`md_box`, `md_energy`, `md_trajectory`, `md_rmsd`, `md_rmsf`, `md_rdf`, `md_msd`, `pdb_inspect`, `pdb_clean`).

1. **Discover MD tools only**: Call `list_cloudra_tools(domain="md")` (includes shared compute submission/query/conversion tools while hiding QM and periodic tools).
2. **Activate bundled domain skills as needed** (loaded natively by your host harness):
   - `molecular-dynamics-simulation` for system preparation, equilibration/production workflow, and GROMACS diagnostics.
   - `molecular-docking` if the task also involves protein-ligand docking setup.
3. **Key discipline**:
   - Keep projects in `standard` mode (do not enable DAG mode for ordinary MD workflows).
   - Submit long GROMACS / shell simulation scripts through `submit_compute_job(job_type="shell", is_async=True, ...)` so Cloudra's detached scheduler/guards keep them alive, then claim finished jobs with `claim_compute_jobs`.
   - Confirm force field, water model, ensemble/temperature/pressure, and simulation length with the user before production runs.
