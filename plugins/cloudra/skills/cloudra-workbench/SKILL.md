---
name: cloudra-workbench
description: Act directly as Cloudra using a running local Cloudra service via the `cloudra` MCP server — call Cloudra's chemistry/compute tools, optionally enable DAG mode, and claim finished compute jobs tracked by the watchdog.
---

# Cloudra Host Workbench (`cloudra` MCP)

Use this skill when the user wants you to run chemistry tools, quantum-chemistry / MD compute jobs, or optional DAG-guided mechanism workflows directly through the local Cloudra service using your own model/subscription instead of delegating to Cloudra's internal runtime.

1. **Select or create a project**: Call `list_projects` to reuse an existing project, or `create_project` with a name (and optional `workspace_dir`).
2. **DAG mode is optional**: Projects start in `standard` mode (`enable_dag=false`) so non-computational or ad-hoc tasks incur zero DAG overhead. Only set `enable_dag=true` (or call `set_project_dag_mode`) when the user is doing a formal reaction-mechanism study that benefits from Cloudra's delivery graph.
3. **Discover and invoke Cloudra tools**: Call `list_cloudra_tools` (pass `include_dag=true` only when DAG mode is enabled; pass `include_schemas=true` or invoke `get_tool_docs` for exact parameter contracts), then execute tools through `run_cloudra_tool(project_id, tool_name, arguments)`.
4. **Compute job lifecycle & watchdog claiming**:
   - Jobs submitted via `submit_compute_job` (or TS pipelines) run under Cloudra's detached scheduler/guards and remain alive even if your host session pauses or restarts. Never kill running compute processes; cancel only via `cancel_compute_job`.
   - Use `watchdog_compute_status` to inspect active jobs and finished jobs awaiting claim.
   - When the watchdog reports finished compute jobs (or on wake-up), call `claim_compute_jobs` to atomically claim them, inspect their `log_path` / `state` / `last_error`, and parse results with `log_parser` or other Cloudra tools.
   - If you have active long-running jobs, schedule a background check/timer rather than polling in a tight loop or abandoning them.
5. **Scientific decisions stay with the user**: Never silently choose chemical methods, functionals, basis sets, or energy thresholds on the user's behalf; confirm scientific choices before submitting formal calculations.
