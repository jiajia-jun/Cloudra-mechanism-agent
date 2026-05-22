# Cloudra (agent4chem) - 中文版

Cloudra 是专为化学科研设计的 AI Agent 协作框架。它通过协调多个专业化代理，协助研究人员进行文献检索、数据分析、化学结构处理以及代码执行。

## 核心特性

- 多进程协作架构：采用 Manager-Worker 模型，由协调者（Coordinator）在独立进程中管理多个执行者（Follower），确保任务执行的稳定性与隔离性。
- ReAct 推理引擎：采用单循环 ReAct（Reasoning-Acting）架构，使 Agent 能够更自然、高效地调用工具。
- 化学多模态能力：集成 RDKit 分子绘图功能，并配备专业的光谱解析引擎（NMR, IR），支持直接处理原始仪器数据而非仅限于图像解析。
- 专业光谱分析全家桶：内置 `NMRProcessor` (基于 nmrglue) 和 `IRProcessor` (基于 spectrochempy)，支持 Bruker, Varian, JCAMP-DX 等格式的读取、相位校正、基线调平和峰提取。
- 专业 Agent 矩阵：拥有 `Visionary` (视觉与定量图谱分析)、`Coder` (高质量算法实现) 和 `Operator` (环境管理与高危操作执行) 等多位专家。
- 高稳定性与 Fork 安全：具备工具加载缓存、C 扩展库延迟加载及 `safe_call` 防护机制，确保在高并发和复杂科研环境下系统运行的健壮性。

## 项目结构

```text
cloudra/
├── agent.py               # 核心 Agent 逻辑
├── cli.py                 # 命令行界面
├── reAct.py               # ReAct 推理实现
├── subagents/             # 专业化 Agent 定义
│   ├── explorer.py        # 项目结构导航
│   ├── researcher.py      # 文献与数据专家
│   ├── visionary.py       # 视觉与原始图谱解析
│   ├── writer.py          # 文档产出专家
│   ├── coder.py           # 算法与流水线开发
│   └── operator.py        # 高危操作与环境管理
└── tools/                 # 工具集
    ├── Bashtool/          # 命令执行
    ├── Chemtool/          # 分子绘图与光谱处理
    ├── Searchtool/        # 文献检索与 PDF 解析
    ├── Managetool/        # 子 Agent 调度与任务审计
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
