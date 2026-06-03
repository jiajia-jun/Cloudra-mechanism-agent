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
- **VASP Post-processing Integration**: Integrated `VASPKIT-Py` for automated DFT data analysis, including band structures, DOS, and charge density.
- **Human-in-the-Loop Interaction**: Built-in `ask_user` tool allows agents to proactively clarify requirements or collect missing information from users.
- **Specialized Agent Matrix**: A growing library of agents including `Visionary`, `Coder`, `Operator`, `Researcher`, and `Writer`.

## Project Structure

```text
cloudra/
├── agent.py               # Core Coordinator logic
├── reAct.py               # ReAct reasoning implementation
├── executor.py            # Tool execution engine
├── session_manager.py     # Session and history management
├── cli.py                 # Command Line Interface
├── api.py                 # FastAPI-based Web/Mobile API
├── email_listener.py      # Background email wakeup service
├── vaspkit_py/            # VASP post-processing toolkit
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
    ├── Skilltool/         # Expertise (Skill) management
    └── Writetool/         # File writing & management
```

## Architecture & Data Flow

Cloudra follows a modular architecture where responsibilities are strictly separated between coordination, reasoning, and execution.

### 🧩 Core Component Mapping

| File | Primary Class | Responsibility |
| :--- | :--- | :--- |
| `agent.py` | `Coordinator`, `Follower` | **Identity**: Defines Agent roles, prompts, and identity persistence. |
| `reAct.py` | `reAct` | **Brain**: The iterative reasoning loop (Thought-Action-Observation). |
| `executor.py` | `Executor` | **Nervous System**: Orchestrates tool calls and handles security audits. |
| `session_manager.py` | `SessionManager` | **Memory**: Manages conversation history and state persistence to SQLite. |
| `tools_class.py` | `BaseTool` | **Limbs**: Abstract base for all tools; defines input schemas and logic. |

### 🔄 Request Lifecycle

1. **Input**: User command enters via `cli.py` or `api.py`.
2. **Dispatch**: `Coordinator` (the "Professor") analyzes the request.
3. **Reasoning**: The `reAct` loop begins. AI writes a **Thought**.
4. **Execution**: If an **Action** is needed, `Executor` runs the tool (e.g., `PaperSearcher`).
5. **Memory**: Results are saved via `SessionManager` and fed back as an **Observation**.
6. **Interaction**: If clarification is needed, `ask_user` pauses the flow for human input.

## Security & Audit

Cloudra implements a rigorous security model to ensure that AI agents operate safely within the research environment.

### 🛡️ Multi-Level Permission System
We use a bit-flag permission model (`Permission` class in `permission_model.py`) to gate tool usage:
- **READ**: Access to read files and literature.
- **WRITE**: Permission to create or modify local files.
- **MANAGE**: Authority to launch and supervise sub-agents.
- **SCRIPT**: Ability to execute code (Python/Shell).
- **DESTRUCTIVE**: Access to high-risk operations (e.g., file deletion, environment changes).

### 🚦 Human-in-the-Loop Approval Flow
Any operation flagged as `DESTRUCTIVE` or `SCRIPT` (depending on configuration) triggers an **Approval Flow**:
1. **Trigger**: Agent requests a dangerous tool call (e.g., `rm -rf`).
2. **Audit**: The system pauses execution and logs the request to the `approvals` table.
3. **Approval**: A human supervisor must review the request via CLI/API and grant or deny permission.
4. **Resumption**: The agent only proceeds if explicit approval is received.

## Technology Stack & Design Rationale

Unlike many AI Agent projects, Cloudra is **not built on LangChain, AutoGPT, or other heavy frameworks**. 

### 🚀 Why a Custom Framework?
- **Minimalism & Flexibility**: Heavy frameworks often introduce unnecessary abstractions and "magic" that make debugging and customization difficult in a scientific context. We built our own lightweight orchestration layer to maintain 100% control over the reasoning loop.
- **Transparency**: In chemical research, every step must be traceable. Our custom ReAct implementation ensures that the chain of thought is clear, reproducible, and not obscured by complex library internal logic.
- **Optimized for Chemistry**: By controlling the tool execution and memory management, we can better handle large-scale chemical data, raw spectroscopy files, and complex DFT workflows that generic frameworks struggle with.

### 🛠️ Key Technologies
- **Core**: Python 3.10+
- **Database**: SQLite (WAL mode for high concurrency)
- **Schema**: Pydantic v2 (Strict type safety and OpenAI schema generation)
- **API**: FastAPI (High-performance web/mobile interface)
- **Chemistry**: RDKit, NMRGlue, SpectroChemPy, DECIMER
- **Interface**: Rich (Beautiful CLI output)

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
