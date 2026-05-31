# Cloudra (agent4chem) - 中文版

Cloudra 是专为化学科研设计的 AI Agent 协作框架。它通过协调多个专业化代理，协助研究人员进行文献检索、数据分析、化学结构处理以及代码执行。

## 核心特性

- **多进程协作架构**：采用 Manager-Worker 模型，由协调者（Coordinator）在独立进程中管理多个执行者（Follower），确保任务执行的稳定性与隔离性。
- **ReAct 推理引擎**：采用单循环 ReAct（Reasoning-Acting）架构，使 Agent 能够更自然、高效地调用工具。
- **远程控制与通知**：集成了基于邮件的交互系统，支持发送实验报告、读取收件箱指令，并可通过安全白名单进行远程邮件唤醒。
- **跨平台兼容性**：全面支持 Linux 和 Windows 系统，内置健壮的 Shell 指令分析引擎和终端编码自动处理机制。
- **化学多模态能力**：集成 RDKit 分子绘图功能、基于 DECIMER 深度学习的化学结构图像识别（图片转 SMILES），并配备专业的光谱解析引擎。
- **人机交互闭环**：内置 `ask_user` 工具，允许 Agent 在执行任务过程中主动向用户澄清需求或收集缺失信息。
- **专业 Agent 矩阵**：拥有 `Visionary` (视觉分析)、`Coder` (算法实现)、`Researcher` (文献调研) 等多位专家。

## 项目结构

```text
cloudra/
├── agent.py               # 核心 Agent 逻辑
├── cli.py                 # 命令行界面
├── api.py                 # 基于 FastAPI 的 Web/移动端接口
├── email_listener.py      # 后台邮件唤醒服务 (新增)
├── reAct.py               # ReAct 推理实现
├── subagents/             # 专业化 Agent 定义
│   ├── explorer.py        # 项目结构导航
│   ├── researcher.py      # 文献与数据专家
│   ├── visionary.py       # 视觉与原始图谱解析
│   ├── writer.py          # 文档产出专家
│   ├── coder.py           # 算法与流水线开发
│   └── operator.py        # 高危操作与环境管理
└── tools/                 # 工具集
    ├── Bashtool/          # 跨平台命令执行
    ├── Chemtool/          # 分子绘图与光谱处理
    ├── Searchtool/        # 文献检索与 PDF 解析
    ├── Managetool/        # 子 Agent 调度与任务审计
    ├── Interactool/       # 邮件交互与人机问答
    └── Writetool/         # 文件管理
```

## 安装指南

确保系统中已安装 Python 3.10+。

```bash
pip install -e .
```

## 远程唤醒

启动后台邮件监听服务以支持远程控制：

```bash
python -m cloudra.email_listener
```
*注意：请确保已通过 `cloudra config` 配置了 SMTP/IMAP 设置及安全白名单。*

## 快速开始

### 配置初始化

设置 API Key、模型偏好以及邮件服务参数：

```bash
cloudra config init
```

### 运行任务

通过命令行启动化学科研任务：

```bash
cloudra run "搜索钙钛矿太阳能电池的最新论文并将总结发送到我的邮箱"
```

## 测试指南

使用 `pytest` 运行完整测试套件：

```bash
pytest tests/
```
