# Cloudra Subagent for Codex

Use the plugin to delegate chemical research to an existing Cloudra service and retrieve the outcome.

1. From this checkout, install Cloudra with its MCP extra in the Python environment Codex will use. Make sure Codex can find the resulting `cloudra` command on its PATH.
2. Run Cloudra from this version and leave the service running.
3. From the repository root, add the marketplace and install the plugin.

```sh
python -m pip install -e '.[mcp]'
codex plugin marketplace add .
codex plugin add cloudra-subagent@cloudra
```

In Codex desktop, open the **cloudra** marketplace in the Plugins Directory and install **Cloudra Subagent**. If the directory was already open when the marketplace was added, restart the app to reload it.

Open a new chat and ask Codex to list Cloudra projects or delegate a research question. It can follow the Coordinator's progress, relay answers to pending questions, and report the conclusion and its verification status. If a user supplied a local workspace, put the input files there and refer to them by relative path in the task. A JavaScript history filter uses the same Node and QuickJS setup as Cloudra's JavaScript tools.

The adapter finds the local API from Cloudra's runtime ownership metadata. For a manual MCP configuration, set the command to `cloudra mcp --api-url http://127.0.0.1:PORT` when using a nondefault connection. Configure the URL without query parameters. Remote URLs use HTTPS with `CLOUDRA_MCP_API_TOKEN` in the adapter process environment.
