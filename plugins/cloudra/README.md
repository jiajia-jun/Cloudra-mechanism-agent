# Cloudra Plugin (Host Mode: Tools + Compute Claim Watchdog)

Turn your host agent (Antigravity, Codex, etc.) into Cloudra by connecting it directly to a running local Cloudra service:

- Reuses Cloudra's authoritative chemistry/compute tools, detached calculation scheduler/guards, and optional DAG ledger.
- Splits skills and `list_cloudra_tools(domain=...)` by technical stack — `qm` (Gaussian/ORCA/xTB), `md` (GROMACS/Packmol/PDB), and `periodic` (VASP/CP2K) — with `cloudra-workbench` routing tasks to the right stack on demand.
- Runs on your host agent's own model / subscription (no separate Cloudra LLM runtime required).
- Keeps **DAG mode optional** (`standard` by default) so general tasks are never blocked by mechanism-graph gates.
- Includes a lightweight **compute-job claim watchdog** (`hooks.json` -> `cloudra watchdog`) that stays completely silent when no compute jobs exist, reminds you when finished jobs await claiming, and prevents abandoning active detached calculations.

> Looking to delegate full autonomous research runs to Cloudra's own `runtime_v2` multi-agent kernel instead? Install `./plugins/cloudra-subagent` (`cloudra-subagent` MCP).

## Setup

1. Install Cloudra with the `mcp` extra in the Python environment on your host agent's `PATH`:

```sh
python -m pip install -e '.[mcp]'
```

2. Start your local Cloudra service (and compute scheduler) and leave it running.
3. Install the plugin from the repository root:

### Antigravity (AGY)

```sh
agy plugin install ./plugins/cloudra
agy plugin validate ./plugins/cloudra
```

Open a new chat (or refresh MCP Servers) so Antigravity loads the `cloudra` MCP server (`mcp_config.json`) and compute watchdog (`hooks.json`).

### Codex

```sh
codex plugin marketplace add .
codex plugin add cloudra@cloudra
```

For manual MCP configuration against a non-default local or remote HTTPS endpoint, run `cloudra mcp --api-url http://127.0.0.1:PORT` (remote HTTPS uses `CLOUDRA_MCP_API_TOKEN`).
