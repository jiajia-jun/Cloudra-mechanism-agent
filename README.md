# Cloudra (agent4chem)

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

---

# Cloudra (agent4chem) - 中文版

Cloudra 是专为化学科研设计的 AI Agent 协作框架。它通过协调多个专业化代理，协助研究人员进行文献检索、数据分析、化学结构处理以及代码执行。

## 核心特性

- 多进程协作架构：采用 Manager-Worker 模型，由协调者（Coordinator）在独立进程中管理多个执行者（Follower），确保任务执行的稳定性与隔离性。
- ReAct 推理引擎：采用单循环 ReAct（Reasoning-Acting）架构，使 Agent 能够更自然、高效地调用工具。
- 化学多模态能力：集成 RDKit 分子绘图功能，并配备视觉专家 Agent，可解析核磁共振（NMR）、红外光谱（IR）、电镜图像及各类化学图表。
- 科学文献检索：内置 ArXiv 和 ChemRxiv 检索工具，支持 PDF 自动转 Markdown 以供 Agent 阅读。
- 安全执行沙箱：提供独立的 Bash 环境，用于运行化学模拟计算、数据处理脚本及 Git 操作。

## 项目结构

```text
cloudra/
├── agent.py               # 核心 Agent 逻辑
├── cli.py                 # 命令行界面
├── coordinator.py         # 任务协调管理
├── reAct.py               # ReAct 推理实现
├── subagents/             # 专业化 Agent 定义
│   ├── explorer.py        # 文件与项目探索
│   ├── researcher.py      # 文献与科研专家
│   ├── visionary.py       # 视觉与多模态分析
│   └── writer.py          # 文档与代码专家
└── tools/                 # 工具集
    ├── Bashtool/          # 命令执行
    ├── Chemtool/          # 分子绘图 (SMILES/RDKit)
    ├── Searchtool/        # 文献检索与 PDF 解析
    └── Writetool/         # 文件管理
```

## 安装指南

确保系统中已安装 Python 3.10+。

```bash
pip install -e .
```

## 快速开始

### 配置初始化

设置 API Key 和模型偏好：

```bash
cloudra config init
```

### 运行任务

通过命令行启动化学科研任务：

```bash
cloudra run "搜索钙钛矿太阳能电池的最新论文并让 researcher 进行总结"
```

### 查看历史

查看之前的对话记录：

```bash
cloudra history
```

### 查看日志

查看特定对话的详细推理日志：

```bash
cloudra logs [对话ID]
```
