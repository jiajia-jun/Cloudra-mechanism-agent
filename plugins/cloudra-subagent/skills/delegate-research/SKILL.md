---
name: delegate-research
description: Delegate a chemical mechanism research task to a running Cloudra instance, resume an existing project, check blockers, or retrieve its conclusions and evidence.
---

# Delegate research to Cloudra

The local plugin needs the Cloudra package with its `mcp` extra, the `cloudra` executable on Codex's PATH, and an already running Cloudra service. In the Cloudra repository, install **cloudra-subagent** from the **cloudra** marketplace. If the desktop app was already open when the marketplace file was added, restart it so the marketplace is discovered.

1. For ongoing work, use `list_projects` and `get_progress` to find the intended project and the exact Agent instance. Send follow-up instructions with `send_message` and check each recipient's delivery status.
2. For a new task, call `start_task` with a name and the research request, including the user's constraints. Save the returned project and Coordinator IDs. Use `workspace_dir` only for a distinct local directory explicitly selected by the user. Refer to its inputs using paths relative to that directory.
3. If start returns a project ID with an error, inspect that project and correct the failure. Use the existing project ID with `start_task` if it still has no Coordinator. If a write response is lost, inspect Cloudra before repeating it. If the intended write cannot be identified, ask the operator to confirm it.
4. Use `get_progress` to find blockers and `get_agent_progress` for the relevant Agent's recent output. Use `answer_question` for pending questions. For scientific choices, relay the user's confirmed decision. Approval requests are handled by the user in Cloudra. Cloudra handles Supervisor review.
5. Use `get_result` on the Coordinator, optionally waiting up to 20 seconds per call. A pending result can include background calculations or requests for input. When the result is finished, report its conclusion, verification label, completion basis, and unresolved items. Read the returned artifact URIs through MCP resources when available.
