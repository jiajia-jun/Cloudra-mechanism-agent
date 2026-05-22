# Cloudra (agent4chem)

[中文版](README_CN.md)

Cloudra is an AI Agent collaboration framework specifically designed for chemical research. It coordinates specialized agents to handle literature search, data analysis, chemical structure processing, and code execution.

## Core Features

- Multi-Process Architecture: Utilizes a Manager-Worker model where the Coordinator manages multiple Follower agents in independent processes for robust task execution and isolation.
- ReAct Reasoning Engine: Implements a single-loop Reasoning-Acting (ReAct) architecture for more natural and efficient interaction with tools.
- Multimodal Chemistry Capabilities: Integrated RDKit for molecule drawing and specialized processors for raw spectroscopy data (NMR, IR), allowing for deep analysis beyond simple image interpretation.
- Professional Spectroscopy Suite: Built-in `NMRProcessor` (via nmrglue) and `IRProcessor` (via spectrochempy) for handling raw instrument files (Bruker, Varian, JCAMP-DX, etc.) with advanced preprocessing like phase correction and baseline removal.
- Specialized Agent Matrix: A growing library of agents including `Visionary` (visual analysis), `Coder` (algorithm implementation), and `Operator` (environment & risk management).
- High Stability & Fork-Safety: Robust execution engine with tool caching, lazy-loading of heavy C-extensions, and `safe_call` wrappers to prevent crashes in high-concurrency environments.

## Project Structure

```text
cloudra/
├── agent.py               # Core Agent logic
├── cli.py                 # Command Line Interface
├── reAct.py               # ReAct reasoning implementation
├── subagents/             # Specialized agent definitions
│   ├── explorer.py        # Project structure navigation
│   ├── researcher.py      # Literature & data specialist
│   ├── visionary.py       # Vision & raw spectrum analysis
│   ├── writer.py          # Documentation specialist
│   ├── coder.py           # Algorithm & pipeline developer
│   └── operator.py        # High-risk execution & env manager
└── tools/                 # Toolkits for agents
    ├── Bashtool/          # Command execution
    ├── Chemtool/          # Molecular drawing & Spectrum processing
    ├── Searchtool/        # ArXiv/ChemRxiv and PDF parsing
    ├── Managetool/        # Sub-agent control & task oversight
    └── Writetool/         # File management
```

## Installation

Ensure you have Python 3.10+ installed.

```bash
pip install -e .
```

## Testing

Run the test suite using `pytest`:

```bash
pip install pytest pytest-asyncio
pytest tests/
```

## Quick Start

### Configuration

Initialize your API keys and model preferences:

```bash
cloudra config init
```

### Running Tasks

Run a chemistry research task directly from the CLI:

```bash
cloudra run "Search for recent papers on perovskite solar cells and let the researcher summarize them"
```

### Viewing History

Check previous conversations:

```bash
cloudra history
```

### Checking Logs

View detailed reasoning logs for a specific conversation:

```bash
cloudra logs [conv_id]
```
