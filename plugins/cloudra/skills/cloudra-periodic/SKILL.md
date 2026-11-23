---
name: cloudra-periodic
description: Periodic first-principles calculations, crystal/slab modeling, defects, surface adsorption, and periodic NEB transition states (VASP, CP2K) via the `cloudra` MCP server.
---

# Cloudra Periodic / First-Principles Stack (`domain="periodic"`)

Use this skill for periodic boundary condition (PBC) systems: bulk crystals, surface slabs, point defects, adsorbate placement, and periodic NEB saddle-point searches using VASP or CP2K (`periodic_model`, `periodic_ts`).

1. **Discover periodic tools only**: Call `list_cloudra_tools(domain="periodic")` (includes shared compute/log/format-conversion tools while hiding small-molecule QM and MD tools).
2. **Activate bundled domain skill as needed** (loaded natively by your host harness):
   - `first-principles-calculation` for VASP / CP2K conventions, k-point/cutoff settings, slab/vacuum geometry, and NEB convergence criteria.
3. **Key discipline**:
   - Do not mix small-molecule QM tools (`qm_input_writer`, `ts_prepare`) into periodic VASP/CP2K workflows; use `periodic_model`, `periodic_ts`, and `submit_compute_job(job_type="vasp" | "cp2k", is_async=True, ...)`.
   - Keep projects in `standard` mode unless the user explicitly asks for a formal DAG delivery graph.
   - Claim completed VASP/CP2K runs via `claim_compute_jobs` and confirm exchange-correlation functional, pseudopotentials/basis, k-mesh, spin polarization, and dispersion corrections with the user.
