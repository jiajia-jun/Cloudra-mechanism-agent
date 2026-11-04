# Cloudra Subagent MVP Implementation Plan

> Use the subagent-driven development workflow. Verify focused behavior before delivery.

**Goal** — Install a Codex plugin that connects to an already running Cloudra, starts research, reads project and agent progress, and retrieves the result.

**Architecture** — A stdio MCP adapter calls authenticated HTTP routes on the owning Cloudra runtime. The HTTP routes reuse existing commands, event projections, and artifact storage. The plugin contains configuration and a short usage skill.

**Tech stack** — Python 3.11+, Pydantic, FastAPI, HTTPX, existing MCP Python SDK v2, QuickJS.

**Spec** — ../specs/2026-11-05-cloudra-subagent-plugin-schema.md

- [ ] Add scoped progress reads in routers/subagent_progress.py. Export async project_progress(ctx, project_id, include_process=True) and routes GET /api/v2/projects/{project_id}/subagent/progress, POST /api/v2/projects/{project_id}/subagent/agents/{session_id}/progress. Test transcript filtering before limit, reasoning opt-in, expression execution without host capabilities, missing PROCESS.md and project scoping.
- [ ] Add task start and result routes in routers/subagent_tasks.py. POST /api/v2/subagent/tasks starts a Coordinator with the initial message. GET /api/v2/projects/{project_id}/subagent/agents/{session_id}/result reads the current terminal report or pending progress. Test parked runs, resumed runs, artifact provenance, and the retained project ID after partial start.
- [ ] Add MCP v2 adapter in cloudra/services/subagent_mcp.py and portable plugin files. Expose list_projects, start_task, get_progress, get_agent_progress, get_result, send_message and answer_question. Test the stdio protocol and inspect discovery schemas. Resolve local runtime by its existing ownership metadata or an explicit API URL.
- [ ] Add CLI/route registration, scoped batch message sending, and a real stdio client-to-HTTP runtime test with scripted model output. Check the terminal result after closing and reopening the adapter, plus connection and auth failures. Run compileall, Ruff, and related tests. Open a PR to master.
