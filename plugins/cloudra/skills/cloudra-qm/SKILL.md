---
name: cloudra-qm
description: Small-molecule quantum chemistry, conformer search, spectroscopy, transition-state search, and reaction mechanisms (Gaussian, ORCA, xTB) via the `cloudra` MCP server.
---

# Cloudra QM Stack (`domain="qm"`)

Use this skill for isolated molecules, organometallic complexes, conformer ensembles, electronic/thermochemical properties, IR/NMR spectra, and reaction-mechanism / transition-state workflows using Gaussian, ORCA, or xTB.

1. **Discover QM tools only**: Call `list_cloudra_tools(domain="qm")` (this includes shared compute/log/conversion tools automatically and hides unrelated MD and periodic tools).
2. **Activate bundled domain skills as needed** (loaded natively by your host harness):
   - `dft-calculation` for Gaussian / ORCA / xTB input preparation, convergence, and frequency checks.
   - `reaction-mechanisms` and `ts-initial-guess` before formal TS searches (`ts_prepare` / `ts_resume` / `ts_inspect`).
   - `dag-operations` only if the user opted into DAG mode (`set_project_dag_mode(enable_dag=true)`).
   - `peer-review-standards` when critically interpreting barriers or computational claims.
3. **Key discipline**:
   - Respect native atom-index conventions (Gaussian 1-based vs ORCA 0-based; structure tools 1-based) and always verify tool contracts with `get_tool_docs`.
   - Submit long QM jobs asynchronously with `submit_compute_job`, then claim completed jobs via `claim_compute_jobs` and parse logs with `log_parser` / `thermo_analysis`.
   - Confirm method, functional, basis set, solvent model, and verification criteria with the user before formal runs.
