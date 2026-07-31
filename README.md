# Cloudra

AI Agent collaboration framework for chemical research.

[中文版](README_CN.md)

> **Status note**: only the terminal TUI (Textual, `cloudra` / `cloudra run`) is actively tested and recommended at this stage. The Flet GUI (Windows/Android) ships in this repo but is **not currently tested** — do not rely on it for real work yet.

## Highlights

- **Self-Built ReAct Framework**: Not built on LangChain or AutoGPT. A lightweight, custom reasoning-acting loop designed for traceability and full control in scientific workflows.
- **Human-in-the-Loop by Design**: Destructive or script executions are gated by an explicit approval flow. Agents can also pause and ask the user via `ask_user` when clarification is needed.
- **YOLO Mode**: Optional `--yolo` flag lets an independent LLM agent auto-approve risky operations for fully automated pipelines. In the GUI it is a per-session toggle (contextvar-scoped, propagated to sub-agent processes), not a process-wide switch.
- **Streaming & Interruption**: Token-level streaming end-to-end (throttled `llm_chunk` events over SSE) for the Coordinator and every sub-agent, with chat-bubble transcripts per session; any session can be interrupted from the GUI or API (`cancel_requested` → graceful exit, SIGTERM fallback).
- **Native GUI & Linux TUI**: A Flet-based native GUI runs on Windows and Android (no browser required); Linux keeps the terminal TUI via `cloudra` / `cloudra run`. **Note: only the TUI is currently tested — the GUI is not recommended for now.**
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

**Linux / macOS:**

```bash
./install.sh
```

**Windows (PowerShell, run as Administrator):**

```powershell
irm https://your-domain/install.ps1 | iex
# or, if you already cloned the repo:
.\install.ps1
```

The script checks your Python version, creates a virtual environment,
installs Cloudra with all extras, and interactively initializes your config.
It also adds the `cloudra` command to your PATH.

No Python yet? The script can download a standalone Python runtime into the
project directory automatically — no system install or admin rights needed.
No Rust or Node.js is required.

### Manual install

```bash
pip install -e ".[all]"
```

All dependencies are declared in `pyproject.toml`. There is no separate `requirements.txt`.
No Rust or Node.js is needed.

Optional extras:
- `pip install -e ".[all]"` for the full chemistry/browser/pdf toolkit.
- `pip install -e ".[gui]"` for the Flet GUI (Windows/Android).
- `pip install -e ".[chem]"` / `"[browser]"` / `"[pdf]"` for individual feature groups.

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

Interactive mode (Linux TUI / Windows/Android GUI):

```bash
cloudra
```

Force the GUI on any platform:

```bash
cloudra gui
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
cloudra                                   # interactive TUI (Linux) or GUI (Windows/Android)
cloudra gui                               # force the Flet GUI
cloudra run "YOUR TASK"                   # start / resume last conversation
cloudra run "YOUR TASK" --new             # force new conversation
cloudra run "YOUR TASK" --conv-id ID      # continue a specific conversation
cloudra run "YOUR TASK" --dry-run         # print config without executing
cloudra run "YOUR TASK" --yolo            # auto-approve risky operations via LLM

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

# Remote email wakeup (full tutorial below)
python -m cloudra.email_listener
```

## Remote Email Wakeup Tutorial

You can drive Cloudra without sitting at the machine: send an email to a
"robot mailbox", the listener picks it up, runs the task unattended, and
emails the result back to you. Typical scenario: assigning work to an agent
on a server/workstation from your phone.

How it works:

1. The listener polls the robot mailbox for unread mail via IMAP every 60 seconds;
2. A message whose subject (or first body line) starts with `CLOUDRA:` is treated
   as an instruction; the body is passed into the task in full;
3. The task runs unattended in the most recent active conversation (no manual approvals);
4. The result is emailed back to the sender as `Re: <original subject>`; processed
   instructions are marked as read and run exactly once.

### 1. Prepare a mailbox

You need a mailbox with IMAP/SMTP enabled as the robot inbox. For QQ Mail:

- Log in to QQ Mail web → Settings → Account → enable "IMAP/SMTP service";
- Complete the verification to get a 16-character **authorization code**
  (not your QQ password);
- For Gmail, enable 2FA and create an "app password"; the default servers
  (`smtp.gmail.com` / `imap.gmail.com`) already match.

### 2. Configure

```bash
cloudra config set email.user 1591794404@qq.com
cloudra config set email.password <16-char authorization code>
cloudra config set email.smtp_server smtp.qq.com
cloudra config set email.imap_server imap.qq.com
```

Or edit `~/.config/cloudra/config.yaml` directly:

```yaml
email:
  smtp_server: smtp.qq.com
  smtp_port: 465
  imap_server: imap.qq.com
  imap_port: 993
  user: 1591794404@qq.com
  password: <16-char authorization code>
  sender_name: Cloudra Assistant
  whitelist:
    - your-address@qq.com      # only these senders may issue instructions; empty = accept anyone
```

> Configuring `whitelist` is strongly recommended: it controls who is allowed
> to drive your agent remotely.

### 3. Start the listener

```bash
python -m cloudra.email_listener                            # foreground (debugging)
nohup python -m cloudra.email_listener &                    # background, persistent
CLOUDRA_POLL_INTERVAL=30 python -m cloudra.email_listener   # custom poll interval (seconds, default 60)
```

Logs go to `email_listener.log` in the launch directory — triggers, blocked
senders, and reply deliveries are all recorded.

### 4. Use it

From a whitelisted address, send mail to the robot mailbox:

- **Subject**: `CLOUDRA:Summarize this week's preprints on solid-state electrolytes`
- **Body**: anything — it is appended to the instruction and handed to the agent in full.

You will receive a `Re: ...` reply whose body is the task result (truncated
beyond 5000 characters; the full output is available in the TUI conversation).
If a conversation happens to be running when the mail arrives, the message is
injected into that conversation as an event instead of starting a new task.

## API Server

Cloudra also exposes an HTTP API built with FastAPI:

```bash
python -m cloudra.api
```

The server binds to `127.0.0.1:8000` by default. Artifacts are immutable
snapshots downloaded through `/api/v1` metadata plus a short-lived token; the
data directory is never exposed as a static mount. If you bind to a non-loopback
address (`CLOUDRA_API_HOST`), set `CLOUDRA_API_TOKEN` first.

Besides the Conversation/Session/approval endpoints, the API also mirrors the CLI:

- `GET /api/config` / `POST /api/config/set` — view and update configuration (keys masked, values type-coerced)
- `GET /api/conversations/{id}/logs` — per-conversation agent logs
- `GET /api/sessions?state=...` — aggregated session list across conversations
- `GET /api/skills` — available skills
- `GET .../sessions/{id}/events/stream` — SSE stream of session events, including token-level `llm_chunk` deltas

Sessions created via the API accept a `yolo` flag (per-session auto-approval) and can be interrupted via `POST .../cancel`.

## Flet GUI (Desktop & Mobile)

Cloudra's GUI is built with Flet, a Flutter-Python bridge. The same Python codebase
powers native desktop (Windows / macOS / Linux) and Android apps. On Windows and
Android, running `cloudra` automatically starts the GUI; force it on any platform:

```bash
cloudra gui
```

The desktop GUI can call `CloudraService` directly for lower latency. Android
defaults to the remote `/api/v1` backend: the server remains authoritative for
Agent execution, events, approvals, and artifacts.
The layout is responsive: when the window width drops below 720 px (phone portrait),
the sidebar collapses into a hamburger menu and the input field scales to fit —
comfortable for one-handed use.

**Android packaging:**

```bash
.venv/bin/python scripts/build_android.py
```

The build helper stages only the remote UI, HTTP/SSE backend and mobile storage
boundary described by `android/pyproject.toml`. Server Agent, chemistry, database
and API-server dependencies are deliberately absent from the APK. The current
target is `arm64-v8a`; cleartext LAN transport still requires an explicit opt-in
in the server profile.

In the Android server dialog, enable the background Device Runtime to expose the
App-private workspace through `device.workspace.*` and `device.config.*`.
The Android capability dialog can separately grant a document tree through the
system Storage Access Framework; `device.documents.*` never escapes that
persisted grant. Pairing secrets are one-time and short-lived, server-side
device tokens are stored only as hashes, and Android stores the server/device
credentials as AES-GCM ciphertext protected by an Android Keystore key—never in
the JSON profile or device-state file. The selected SAF tree URI is bound to
the same encrypted store; its authority is still the system's persisted grant.
The Flet method channel also sees only
RSA-OAEP-wrapped/session-encrypted envelopes, so debug transport logging cannot
print a plaintext token.

The write capabilities `device.workspace.apply_patch` and
`device.config.patch`, SAF document writes, notifications, file selection,
camera capture, and sharing are never silent: Android first shows the target
and exact local preview. Approval applies file changes only if the SHA/revision
still matches. Permission denial, cancellation, or an approval-time conflict
returns a structured result without overwriting local data.

The APK bundles a small Kotlin/Flet extension for Keystore, persistent SAF
grants, system intents, approval deep links, and a `remoteMessaging` Foreground
Service. Enabling the runtime shows a persistent notification and raises the
process priority while the embedded Python executor is alive. It deliberately
uses `START_NOT_STICKY`: if Android kills the process, the notification
disappears instead of falsely claiming that the device remains online; the
Keystore credential, event cursor, outbox, and SAF grant are restored on the
next App launch. A not-yet-acknowledged device result remains in the durable
outbox for lossless replay; after server acknowledgement, file/camera payloads
are removed and only a compact idempotency digest remains.
Release candidates must still complete the
[Phase 7 emulator/OEM device matrix](docs/ANDROID_PHASE7_DEVICE_MATRIX.md);
source tests and a successful APK build are not substitutes for those checks.

Before every model request the server reassembles the current role, AGENTS.md,
MEMORY.md, skill manifest, and complete tool schemas, then records their
revisions in the Session diagnostics. Ordinary server files and Android
workspace/config changes are separate observations: they do not become
conversation history or alter the Agent identity prompt. Old conversations
therefore preserve their history while adopting current policy. Android change
events remain in a durable local outbox until a heartbeat acknowledges them.

**Desktop packaging:**

```bash
flet build windows   # or macos / linux
```

Flet-packaged desktop apps bundle an embedded Python runtime — the target machine
needs no Python at all. The old Tauri + React frontend (`frontend/`) has been
completely removed. No Rust, Node.js, or npm required.

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
| Chemistry | `gjf_writer`, `gaussian_log_parser`, `format_converter`, `internal_coordinates`, `molecule_drawer`, `image_to_smiles`, `smiles_to_mol`, `nmr_processor`, `ir_processor` |
| Literature & Web | `paper_searcher`, `openalex_searcher`, `web_search`, `pdf2md`, `pdf2image`, `text_reader`, `image_reader`, `web_fetcher`, `headless_browser` |
| Execution | `bashtools`, `text_writer`, `edit_file`, `subagent_launcher`, `submit_compute_job` |
| Interaction | `ask_user`, `email_sender`, `email_reader` |
| Planning & Control | `todo_write`, `goal_set`, `schedule`, `agent_hub`, `stop`, `getskill`, `get_subagent_report`, `update_memory` |

## Sub-Agent Roster

Domain-scoped follower agents launched via `SubAgentLauncher`; all share findings through `agent_hub`:

| ID | Agent | Domain |
| :--- | :--- | :--- |
| a-1 | explorer | Codebase exploration & read-only review (logic flaws, inconsistencies, risks) |
| a-2 | writer | Academic paper/report writing |
| a-3 | researcher | Literature search & methodology analysis |
| a-4 | small_mol | Molecular quantum chemistry (Gaussian/ORCA): conformers, TS, spectra |
| a-5 | md | Molecular dynamics (GROMACS/LAMMPS): setup, equilibration, sampling, analysis |
| a-6 | dft | First-principles periodic systems (VASP/QE): bulk, surfaces, defects |
| a-7 | experiment | Experimental design: DOE, controls, characterization matrix, safety |
| a-8 | env | Environment management: dependencies, conda, builds, HPC |

All except `explorer` (read-only) and `writer` (read+write) hold full permissions; dangerous operations still go through the approval flow.

## Security Model

Cloudra uses bit-flag permissions (`READ`, `WRITE`, `SCRIPT`, `DESTRUCTIVE`, `MANAGE`). Dangerous operations are paused and logged to the `approvals` table until a human approves or denies them via CLI/API. With `--yolo`, an independent LLM guard (`cloudra/yolo_guard.py`) makes the approval decision instead; use it only in trusted environments.

## Project Structure

```
cloudra/
├── agent.py              # Agent base class and Coordinator
├── react.py              # ReAct reasoning loop
├── executor.py           # Tool execution engine
├── context_manager.py    # Message/context rendering
├── database.py           # SQLite persistence
├── supervisor.py         # Scientific oversight and validation
├── tools_class.py        # BaseTool and tool registry
├── config.py             # Configuration management
├── cli.py                # Command-line interface
├── api.py                # FastAPI server
├── yolo_guard.py         # YOLO mode safety guard
├── platform_utils.py     # Platform detection (Windows / Android / Linux)
├── runtime_profile.py    # Android tool allowlist & runtime capabilities
├── mobile_storage.py     # Flet-packaged app persistent storage
├── tools/                # Tool implementations
├── subagents/            # Follower agent roles
├── skills/               # Markdown-based skill library
├── prompts/              # Agent prompt templates
├── runtime/              # Runtime scheduling (workers, mobile_tasks)
├── tui/                  # Textual full-screen TUI (run.py entry)
└── ui/                   # Flet GUI (app.py main interface)
flet_app.py               # Flet packaging entry point (Android APK / desktop)
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
