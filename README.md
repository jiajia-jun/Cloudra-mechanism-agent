# Cloudra (agent4chem)

[中文版](README_CN.md)

Cloudra is an AI Agent collaboration framework specifically designed for chemical research. It coordinates specialized agents to handle literature search, data analysis, chemical structure processing, and code execution.

## Core Features

- Multi-Process Architecture: Utilizes a Manager-Worker model where the Coordinator manages multiple Follower agents in independent processes for robust task execution and isolation.
- ReAct Reasoning Engine: Implements a single-loop Reasoning-Acting (ReAct) architecture for more natural and efficient interaction with tools.
- Multimodal Chemistry Capabilities: Integrated RDKit for molecule drawing and Visionary agents for analyzing spectra (NMR, IR), electron microscopy images, and complex chemical charts.
- Scientific Search: Built-in tools for searching and parsing literature from ArXiv and ChemRxiv, with automatic PDF-to-Markdown conversion.
- Execution Sandbox: Provides a secure Bash environment for running chemical simulations, data processing scripts, and git operations.

## Project Structure

```text
cloudra/
├── agent.py               # Core Agent logic
├── cli.py                 # Command Line Interface
├── coordinator.py         # Task coordination management
├── reAct.py               # ReAct reasoning implementation
├── subagents/             # Specialized agent definitions
│   ├── explorer.py        # File and project exploration
│   ├── researcher.py      # Literature and research specialist
│   ├── visionary.py       # Vision and multimodal analysis
│   └── writer.py          # Documentation and code specialist
└── tools/                 # Toolkits for agents
    ├── Bashtool/          # Command execution
    ├── Chemtool/          # Molecular drawing (SMILES/RDKit)
    ├── Searchtool/        # ArXiv/ChemRxiv and PDF parsing
    └── Writetool/         # File management
```

## Installation

Ensure you have Python 3.10+ installed.

```bash
pip install -e .
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
