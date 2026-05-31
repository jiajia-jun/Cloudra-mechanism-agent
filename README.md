# Cloudra (agent4chem)

[中文版](README_CN.md)

Cloudra is an AI Agent collaboration framework specifically designed for chemical research. It coordinates specialized agents to handle literature search, data analysis, chemical structure processing, and code execution.

## Core Features

- **Multi-Process Architecture**: Utilizes a Manager-Worker model where the Coordinator manages multiple Follower agents in independent processes for robust task execution and isolation.
- **ReAct Reasoning Engine**: Implements a single-loop Reasoning-Acting (ReAct) architecture for more natural and efficient interaction with tools.
- **Remote Control & Notifications**: Integrated email-based interaction allowing agents to send reports, read inbox instructions, and be remotely awakened via a secure whitelist.
- **Cross-Platform Compatibility**: Full support for both Linux and Windows environments, including robust shell command analysis and output encoding handling.
- **Multimodal Chemistry Capabilities**: Integrated RDKit for molecule drawing, specialized processors for raw spectroscopy data (NMR, IR), and deep learning-based optical chemical structure recognition (DECIMER).
- **Professional Spectroscopy Suite**: Built-in `NMRProcessor` and `IRProcessor` for handling raw instrument files (Bruker, Varian, JCAMP-DX, etc.).
- **Human-in-the-Loop Interaction**: Built-in `ask_user` tool allows agents to proactively clarify requirements or collect missing information from users.
- **Specialized Agent Matrix**: A growing library of agents including `Visionary`, `Coder`, `Operator`, `Researcher`, and `Writer`.

## Project Structure

```text
cloudra/
├── agent.py               # Core Agent logic
├── cli.py                 # Command Line Interface
├── api.py                 # FastAPI-based Web/Mobile API
├── email_listener.py      # Background email wakeup service (New)
├── reAct.py               # ReAct reasoning implementation
├── subagents/             # Specialized agent definitions
│   ├── explorer.py        # Project structure navigation
│   ├── researcher.py      # Literature & data specialist
│   ├── visionary.py       # Vision & raw spectrum analysis
│   ├── writer.py          # Documentation specialist
│   ├── coder.py           # Algorithm & pipeline developer
│   └── operator.py        # High-risk execution & env manager
└── tools/                 # Toolkits for agents
    ├── Bashtool/          # Cross-platform command execution
    ├── Chemtool/          # Molecular drawing & Spectrum processing
    ├── Searchtool/        # ArXiv/ChemRxiv and PDF parsing
    ├── Managetool/        # Sub-agent control & task oversight
    ├── Interactool/       # Email interaction & ask_user
    └── Writetool/         # File management
```

## Installation

Ensure you have Python 3.10+ installed.

```bash
pip install -e .
```

## Remote Wake-up

To start the background email listener for remote control:

```bash
python -m cloudra.email_listener
```
*Note: Ensure your SMTP/IMAP settings and whitelist are configured via `cloudra config`.*

## Quick Start

### Configuration

Initialize your API keys, model preferences, and email settings:

```bash
cloudra config init
```

### Running Tasks

Run a chemistry research task directly from the CLI:

```bash
cloudra run "Search for recent papers on perovskite solar cells and send the summary to my email"
```

## Testing

Run the test suite using `pytest`:

```bash
pytest tests/
```
