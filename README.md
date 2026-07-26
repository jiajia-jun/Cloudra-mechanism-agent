# Cloudra

AI Agent collaboration framework for chemical research.

[中文版](README_CN.md)

## Highlights

- **Self-Built ReAct Framework**: Not built on LangChain or AutoGPT. A lightweight, custom reasoning-acting loop designed for traceability and full control in scientific workflows.
- **Human-in-the-Loop by Design**: Destructive or script executions are gated by an explicit approval flow. Agents can also pause and ask the user via `ask_user` when clarification is needed.
- **YOLO Mode**: Optional `--yolo` flag lets an independent LLM agent auto-approve risky operations for fully automated pipelines. In the GUI it is a per-session toggle (contextvar-scoped, propagated to sub-agent processes), not a process-wide switch.
- **Streaming & Interruption**: Token-level streaming end-to-end (throttled `llm_chunk` events over SSE) for the Coordinator and every sub-agent, with chat-bubble transcripts per session; any session can be interrupted from the GUI or API (`cancel_requested` → graceful exit, SIGTERM fallback).
- **Desktop App & Web UI**: A Tauri desktop app (embedded backend sidecar, optional standalone Python runtime for zero-dependency distribution) plus a web UI served directly by the API.
- **Context Compression**: Automatically summarizes older conversation history when context exceeds half of the model window, preventing unbounded growth.
- **Self-Learning & Case Bank**: Agents can distill successful workflows into a global Case Bank for cross-conversation memory and knowledge reuse.
- **Scientific Supervisor**: Introduces an independent Supervisor agent to oversee experimental progress and validate scientific rigor.
- **Full Chemistry Toolkit**: Molecule drawing, image-to-SMILES (DECIMER), NMR/IR raw data processing, Gaussian input generation, format conversion, log parsing, and DFT job submission/monitoring.
- **Multi-Process & Secure**: Coordinator and Follower agents run in isolated processes. SQLite WAL mode, permission bit-flags, audit logs, and an optional YOLO guard keep operations safe.
- **Event-Driven Architecture (v2.0.0-beta)**: Conversation-scoped Unix domain socket event bus replaces polling for cancellations, external events, compute jobs, and sub-agent scheduling. Database remains the source of truth; events are the wake-up mechanism.

## What's New in 2.0.0-beta

This is a preview release of the event-driven rewrite.

- **No more polling**: `cancel_requested`, external events, compute-job readiness, and sub-agent requests are delivered via `cloudra.ipc` (Unix domain sockets) instead of busy-waiting on SQLite.
- **Guard becomes parent of calculator**: `cloudra.runtime.monitor` now `wait()`s for the calculator process and parses the log after exit, removing the file-mtime polling loop.
- **Real token usage**: `LLMClient` requests `stream_options.include_usage` and exposes `last_usage`; token estimation is no longer the only source.
- **Safer default permissions**: `Bashtools` with no sub-agent only allows read-only commands instead of full access.
- **Coordinator state snapshot**: every `_build_messages` includes a live snapshot of sub-agent session states.

> **Beta note**: the public Python/CLI/API surface is unchanged, but the internal event bus is new. Please report any missed wake-ups or stale IPC sockets.

## Requirements

- Python 3.10+
- An OpenAI-compatible API key for the Coordinator (Follower can share the same or use a different one)

## Installation

### One-line install (recommended)

```bash
./install.sh
```

This script checks your Python version, optionally creates a virtual environment,
installs Cloudra in editable mode, and interactively initializes your config.
If you have an existing `.env` file, it can migrate the LLM settings into the
new YAML-based config.

### Manual install

```bash
pip install -e .
```

All dependencies are declared in `pyproject.toml`. There is no separate `requirements.txt`.

> **Note (HPC users)**: runtime state lives in per-conversation SQLite databases
> (WAL mode) under the data directory (`~/.local/share/cloudra` by default).
> WAL requires a local filesystem with reliable file locking — if your home
> directory is on NFS/Lustre (common on clusters), point `CLOUDRA_DATA_DIR`
> to a local disk (e.g. `/tmp` or a local SSD).

## Quick Start

Initialize configuration:

```bash
cloudra config init
```

Run a task:

```bash
cloudra run "Search for recent papers on perovskite solar cells and summarize the key findings"
```

Resume the last conversation:

```bash
cloudra run "Continue the previous analysis"
```

## Self-Learning Memory & Case Bank

Cloudra features a cross-conversation memory and self-learning mechanism powered by a **Global Case Bank** and a **Scientific Supervisor**:

1. **Experience Extraction**: At the end of every task (or when pausing for user input), the independent Supervisor agent reviews the entire conversation trajectory. It summarizes the task goal, the outcome, the root causes of success/failure, and extracts reusable "Lessons".
2. **Global Persistence**: This structured knowledge is saved into a global SQLite database (`case_bank.db`), breaking the boundary of isolated conversation lifecycles.
3. **Knowledge Retrieval**: When initiating a new task, the Coordinator automatically queries the Case Bank for recent or relevant historical cases and injects them into the system prompt context.
4. **Self-Evolution**: Through this continuous feedback loop, the system automatically learns to avoid past mistakes (e.g., problematic tool parameters) and prioritizes proven paths, becoming progressively smarter and more adapted to your workflow.

> **⚠️ Critical incident notice (affects v1.7.0–v1.7.1, fixed in current code)**: A typo in the Supervisor module made `_get_client()` call *itself* recursively (`self._openai_client = self._get_client()`). Since case-bank persistence (`_persist_case` → `extract_case`) runs after **every** task, the recursion fired on every run — even a trivial "hello". On Python 3.13 the recursion never raised `RecursionError`; stack frames consumed RAM at ~500 MB/s until the kernel OOM killer terminated the process (observed 7.5 GB anonymous RSS within ~30 seconds). Because this happened after the task output was printed, the symptom looked like "task finished, program went idle, then memory exploded". **The client is now constructed directly and the recursion is eliminated; if you are running an older checkout, upgrade before use.**

## CLI Reference

```bash
# Top-level options
cloudra --version
cloudra --coordinator-model gpt-4o --coordinator-key $KEY run "..."

# Run tasks
cloudra run "YOUR TASK"                 # start / resume last conversation
cloudra run "YOUR TASK" --new           # force new conversation
cloudra run "YOUR TASK" --conv-id ID    # continue a specific conversation
cloudra run "YOUR TASK" --dry-run       # print config without executing
cloudra run "YOUR TASK" --yolo          # auto-approve risky operations via LLM

# Configuration
cloudra config init                     # interactive setup
cloudra config show                     # display current config (keys masked)
cloudra config get coordinator.model
cloudra config set follower.model gpt-4o

# Inspection
cloudra history                         # list recent conversations
cloudra logs CONV_ID                    # view logs for a conversation
cloudra sessions                        # view agent session states
cloudra skills                          # list available skills

# Remote email wakeup
python -m cloudra.email_listener
```

## API Server

Cloudra also exposes an HTTP API built with FastAPI:

```bash
python -m cloudra.api
```

The server binds to `127.0.0.1:8000` by default and serves generated files under `/artifacts`. If you bind to a non-loopback address (`CLOUDRA_API_HOST`), set `CLOUDRA_API_TOKEN` first — `web.sh` enforces this.

Besides the Conversation/Session/approval endpoints, the API also mirrors the CLI:

- `GET /api/config` / `POST /api/config/set` — view and update configuration (keys masked, values type-coerced)
- `GET /api/conversations/{id}/logs` — per-conversation agent logs
- `GET /api/sessions?state=...` — aggregated session list across conversations
- `GET /api/skills` — available skills
- `GET .../sessions/{id}/events/stream` — SSE stream of session events, including token-level `llm_chunk` deltas

Sessions created via the API accept a `yolo` flag (per-session auto-approval) and can be interrupted via `POST .../cancel`.

## Desktop App & Web UI

The `frontend/` directory contains the shared React UI and a Tauri desktop shell:

```bash
cd frontend
npm ci
npm run desktop   # dev mode: vite + desktop window + embedded backend
```

The API serves the built web UI at `/` (after `npm run build`), so `python -m cloudra.api` alone gives you the full browser experience.

For a distributable desktop package with a **standalone Python runtime** (target machines need no Python at all):

```bash
frontend/scripts/package-desktop.sh   # assembles frontend/dist-app/
```

The script downloads a python-build-standalone runtime, installs Cloudra and all dependencies into it, builds the release binary via `tauri build`, and assembles `frontend/dist-app/` — copy that directory anywhere and run `./cloudra-desktop`. The app spawns its own backend on `127.0.0.1:18473`.

> **Note**: build the desktop binary with `npm run desktop:build` (i.e. `tauri build`), not a bare `cargo build --release` — the latter produces a binary that navigates to the dev server URL and shows a blank/connection-refused window. On Linux, WebKitGTK development packages are required (`./install.sh` can install them on Debian/Ubuntu); under WSL2 the window is displayed through WSLg.

## Chemistry Workflow Example

```bash
# 1. Generate a Gaussian input file
cloudra run "Generate a gjf for benzene at B3LYP/6-31g(d) and save it to /tmp/benzene.gjf"

# 2. Submit the job (sync or async)
cloudra run "Submit /tmp/benzene.gjf as a Gaussian job and wait for it to finish"

# 3. Parse the output
cloudra run "Parse /tmp/benzene.out and report SCF energy, HOMO-LUMO gap, and frequencies"
```

## Tool Overview

| Category | Tools |
| :--- | :--- |
| Chemistry | `gjf_writer`, `gaussian_log_parser`, `format_converter`, `molecule_drawer`, `image_to_smiles`, `smiles_to_mol`, `nmr_processor`, `ir_processor` |
| Literature | `paper_searcher`, `chemrxiv_searcher`, `pdf2md`, `text_reader`, `image_reader`, `web_fetcher`, `headless_browser` |
| Execution | `bashtools`, `text_writer`, `subagent_launcher`, `submit_compute_job` |
| Interaction | `ask_user`, `email_sender`, `email_reader` |
| Control | `stop`, `getskill`, `get_subagent_report` |

## Security Model

Cloudra uses bit-flag permissions (`READ`, `WRITE`, `SCRIPT`, `DESTRUCTIVE`, `MANAGE`). Dangerous operations are paused and logged to the `approvals` table until a human approves or denies them via CLI/API. With `--yolo`, an independent LLM guard (`cloudra/yolo_guard.py`) makes the approval decision instead; use it only in trusted environments.

## Project Structure

```
cloudra/
├── agent.py              # Agent base class and Coordinator
├── reAct.py              # ReAct reasoning loop
├── executor.py           # Tool execution engine
├── context_manager.py    # Message/context rendering
├── database.py           # SQLite persistence
├── supervisor.py         # Scientific oversight and validation
├── tools_class.py        # BaseTool and tool registry
├── config.py             # Configuration management
├── cli.py                # Command-line interface
├── api.py                # FastAPI server
├── yolo_guard.py         # YOLO mode safety guard
├── tools/                # Tool implementations
├── subagents/            # Follower agent roles
├── skills/               # Markdown-based skill library
└── prompts/              # Agent prompt templates
frontend/
├── src/                  # React web UI (shared by browser and desktop)
├── src-tauri/            # Tauri desktop shell (spawns the backend sidecar)
└── scripts/              # package-desktop.sh: standalone-runtime distribution
```

## Development

Run tests:

```bash
pytest tests -q
```

Check code style:

```bash
ruff check cloudra tests
```

## License

MIT. See `pyproject.toml` for the full license text.
