# Cloudra Subagent Plugin (Codex & Antigravity)

Use the plugin to delegate chemical research to an existing Cloudra service and retrieve the outcome.

1. From this checkout, install Cloudra with its MCP extra in the Python environment your host agent will use. Make sure the resulting `cloudra` command is on PATH (or point `command` in the installed MCP config to your virtual environment's `cloudra` binary).
2. Run Cloudra from this version and leave the service running.
3. Install the plugin for your host agent from the repository root:

### Codex

```sh
python -m pip install -e '.[mcp]'
codex plugin marketplace add .
codex plugin add cloudra-subagent@cloudra
```

In Codex desktop, open the **cloudra** marketplace in the Plugins Directory and install **Cloudra Subagent**. If the directory was already open when the marketplace was added, restart the app to reload it.

### Antigravity (AGY)

```sh
python -m pip install -e '.[mcp]'
agy plugin install ./plugins/cloudra-subagent
```

You can verify the plugin bundle with `agy plugin validate ./plugins/cloudra-subagent` and check active installation with `agy plugin list`. Open a new chat (or refresh MCP Servers) so Antigravity loads the `cloudra-subagent` MCP server defined in `mcp_config.json`.

Open a new chat and ask the agent to list Cloudra projects or delegate a research question. It can follow the Coordinator's progress, relay answers to pending questions, and report the conclusion and its verification status. If a user supplied a local workspace, put the input files there and refer to them by relative path in the task. A JavaScript history filter uses the same Node and QuickJS setup as Cloudra's JavaScript tools.

The adapter finds the local API from Cloudra's runtime ownership metadata. For a manual MCP configuration, set the command to `cloudra mcp --mode subagent --api-url http://127.0.0.1:PORT` when using a nondefault connection. Configure the URL without query parameters. Remote URLs use HTTPS with `CLOUDRA_MCP_API_TOKEN` in the adapter process environment.

> Looking to let your host agent directly call Cloudra's chemistry/compute tools and compute-job claim watchdog instead of delegating to Cloudra's own runtime? Install `./plugins/cloudra` (`cloudra` MCP).
