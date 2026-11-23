---
name: cloudra-workbench
description: Route tasks on a running local Cloudra service via the `cloudra` MCP server — choose the right chemistry/compute stack (QM, MD, or periodic first-principles), keep DAG mode optional, and claim finished compute jobs via the watchdog.
---

# Cloudra Host Workbench (`cloudra` MCP)

Use this skill as the entry point when acting directly as Cloudra over a running local Cloudra service.

1. **Route by task type first (do not mix stacks)**:
   - **Non-computational / general tasks**: Do not force DAG mode or compute tooling; when no compute jobs are submitted, the compute watchdog stays completely silent.
   - **Small-molecule quantum chemistry, conformers, spectra, TS & reaction mechanisms (Gaussian / ORCA / xTB)** -> activate `cloudra-qm` and query tools with `list_cloudra_tools(domain="qm")`.
   - **Molecular dynamics, solvent boxes, protein PDB prep & trajectory analysis (GROMACS / Packmol / PDB)** -> activate `cloudra-md` and query tools with `list_cloudra_tools(domain="md")`.
   - **Periodic crystals, surfaces/slabs, defects, adsorption & periodic NEB first-principles (VASP / CP2K)** -> activate `cloudra-periodic` and query tools with `list_cloudra_tools(domain="periodic")`.
   - **Full autonomous delegation to Cloudra's own runtime**: use the separate `cloudra-subagent` plugin instead.
2. **Select or create a project**: Call `list_projects` or `create_project(name=..., workspace_dir=...)`. Projects default to `standard` mode (`enable_dag=false`). Only enable optional DAG mode (`enable_dag=true` or `set_project_dag_mode`) when the user wants a formal mechanism delivery graph, then inspect DAG tools via `list_cloudra_tools(domain="dag")`.
3. **Use native plugin skills & tool contracts on demand**: Cloudra's domain guides (`dft-calculation`, `molecular-dynamics-simulation`, `first-principles-calculation`, `reaction-mechanisms`, `ts-initial-guess`, `molecular-docking`, `dag-operations`, `peer-review-standards`) are bundled directly in this plugin for your host harness's native skill loader. Use `get_tool_docs` before constructing unfamiliar tool arguments.
4. **Compute jobs & watchdog claiming**:
   - Detached compute jobs stay alive under Cloudra's scheduler/guards. Never kill running compute processes; cancel only via `cancel_compute_job`.
   - Inspect status with `watchdog_compute_status` and claim finished jobs atomically with `claim_compute_jobs`, then parse outputs with `log_parser` or domain-specific analysis tools.
   - When active jobs are running, schedule a background check/timer instead of polling in a tight loop or abandoning them.
5. **Scientific decisions stay with the user**: Confirm functionals, basis sets, force fields, pseudopotentials, and energy/convergence thresholds with the user before formal submissions.
