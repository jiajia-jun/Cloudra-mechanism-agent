# Cloudra

AI Agent collaboration framework for chemical research.

[中文版](README_CN.md)

## Highlights

- **Self-Built ReAct Framework**: Not built on LangChain or AutoGPT. A lightweight, custom reasoning-acting loop designed for traceability and full control in scientific workflows.
- **Human-in-the-Loop by Design**: Every destructive or script execution is gated by an explicit approval flow. Agents can also pause and ask the user via `ask_user` when clarification is needed.
- **Full Chemistry Toolkit**: Molecule drawing, image-to-SMILES (DECIMER), NMR/IR raw data processing, Gaussian input generation, format conversion, log parsing, and DFT job submission/monitoring.
- **Multi-Process & Secure**: Coordinator and Follower agents run in isolated processes. SQLite WAL mode, permission bit-flags, and audit logs keep operations safe.

## Installation

```bash
pip install -e .
```

Requires Python 3.10+.

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

Cloudra uses bit-flag permissions (`READ`, `WRITE`, `SCRIPT`, `DESTRUCTIVE`, `MANAGE`). Dangerous operations are paused and logged to the `approvals` table until a human approves or denies them via CLI/API.

## License

See [copyright_docs/](copyright_docs/).
