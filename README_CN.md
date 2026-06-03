# Cloudra (agent4chem) - 中文版

Cloudra 是专为化学科研设计的 AI Agent 协作框架。它通过协调多个专业化代理，协助研究人员进行文献检索、数据分析、化学结构处理以及代码执行。

## 核心特性

- **多进程协作架构**：采用 Manager-Worker 模型，由协调者（Coordinator）在独立进程中管理多个执行者（Follower），确保任务执行的稳定性与隔离性。
- **ReAct 推理引擎**：采用单循环 ReAct（Reasoning-Acting）架构，使 Agent 能够更自然、高效地调用工具。
- **远程控制与通知**：集成了基于邮件的交互系统，支持发送实验报告、读取收件箱指令，并可通过安全白名单进行远程邮件唤醒。
- **跨平台兼容性**：全面支持 Linux 和 Windows 系统，内置健壮的 Shell 指令分析引擎和终端编码自动处理机制。
- **化学多模态能力**：集成 RDKit 分子绘图功能、基于 DECIMER 深度学习的化学结构图像识别（图片转 SMILES）。
- **专业光谱解析套件**：内置 `NMRProcessor` 和 `IRProcessor`，支持解析 Bruker、Varian、JCAMP-DX 等多种原始仪器数据格式。
- **DFT 后处理集成**：集成 `VASPKIT-Py` 工具包，支持能带结构、态密度（DOS）、电荷密度等 DFT 计算数据的自动化后处理与绘图。
- **人机交互闭环**：内置 `ask_user` 工具，允许 Agent 在执行任务过程中主动向用户澄清需求或收集缺失信息。
- **专业 Agent 矩阵**：拥有 `Visionary` (视觉分析)、`Coder` (算法实现)、`Researcher` (文献调研)、`Operator` (环境管理) 等多位专家。

## 项目结构

```text
cloudra/
├── agent.py               # 核心 Coordinator 逻辑
├── reAct.py               # ReAct 推理实现
├── executor.py            # 工具执行引擎
├── session_manager.py     # 会话与历史管理
├── cli.py                 # 命令行界面
├── api.py                 # 基于 FastAPI 的 Web/移动端接口
├── email_listener.py      # 后台邮件唤醒服务
├── vaspkit_py/            # VASP 后处理工具包
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
    ├── Skilltool/         # 领域知识 (Skill) 管理
    └── Writetool/         # 文件写入与管理
```

## 系统架构与数据流

Cloudra 采用模块化架构，将协调、推理和执行职责严格分离。

### 🧩 核心组件映射

| 文件 | 主要类 | 职责描述 |
| :--- | :--- | :--- |
| `agent.py` | `Coordinator`, `Follower` | **身份层 (Identity)**: 定义 Agent 的角色、Prompt 模板及身份持久化。 |
| `reAct.py` | `reAct` | **思维层 (Brain)**: 核心推理循环（想-做-看），驱动 AI 的逻辑链。 |
| `executor.py` | `Executor` | **执行层 (Nervous System)**: 负责工具调用的分发、并发管理及安全审计。 |
| `session_manager.py` | `SessionManager` | **记忆层 (Memory)**: 管理会话历史、上下文加载及 SQLite 数据持久化。 |
| `tools_class.py` | `BaseTool` | **感知层 (Limbs)**: 工具的抽象基类，定义输入规范 (Schema) 与执行逻辑。 |

### 🔄 任务执行全生命周期

1. **输入 (Input)**: 用户指令通过 `cli.py` (命令行) 或 `api.py` (FastAPI) 进入系统。
2. **调度 (Dispatch)**: `Coordinator` (导师) 接收指令并初始化任务环境。
3. **推理 (Reasoning)**: 进入 `reAct` 循环，AI 产出 **Thought** (推理过程)。
4. **行动 (Execution)**: 如需调用工具，`Executor` 负责执行（如 `nmr_processor`）并捕获输出。
5. **记忆 (Memory)**: 执行结果由 `SessionManager` 记录，并作为 **Observation** (观察结果) 回馈给 AI。
6. **交互 (Interaction)**: 若 AI 决定调用 `ask_user`，流程会挂起并等待人类“机长”的反馈。

## 安全审计与权限控制

Cloudra 建立了严格的安全审计模型，确保 AI Agent 在科研环境中的操作安全可控。

### 🛡️ 多级权限模型
系统采用基于位标志（Bit-flag）的权限管理机制（`Permission` 类）：
- **READ (读取)**：读取文件、文献和数据库的权限。
- **WRITE (写入)**：创建、修改本地文件的权限。
- **MANAGE (管理)**：启动和管理子 Agent 的权限。
- **SCRIPT (脚本)**：执行 Python 代码或 Shell 脚本的权限。
- **DESTRUCTIVE (破坏)**：执行高危操作（如删除文件、修改环境配置）的权限。

### 🚦 人工审批流 (Human-in-the-Loop)
任何被标记为 `DESTRUCTIVE` 或 `SCRIPT` 的工具调用都会触发**人工审批流**：
1. **触发**: Agent 尝试执行危险指令（例如 `rm -rf` 或安装未经授权的包）。
2. **挂起**: 系统自动暂停该 Agent 的任务，并将操作详情记录至数据库的 `approvals` 表。
3. **审核**: 用户（导师/机长）通过 CLI 或管理界面查看详情并决定“通过”或“驳回”。
4. **恢复**: 只有在获得显式审批通过后，Agent 才会继续执行相关指令。

## 技术栈与设计初衷

与许多 AI Agent 项目不同，Cloudra **没有基于 LangChain、AutoGPT 或其他重型框架构建**。

### 🚀 为什么要自研框架？
- **极简与灵活性**：重型框架往往引入了过多的抽象和“黑盒”逻辑，这在严谨的科学研究场景中会增加调试和自定义的难度。我们构建了自己的轻量级编排层，以实现对推理循环 100% 的掌控。
- **透明度**：在化学研究中，每一步操作都必须可追溯。自研的 ReAct 实现确保了思维链（Chain of Thought）清晰、可复现，且不会被复杂的库内部逻辑所遮蔽。
- **针对化学优化**：通过自主控制工具执行和记忆管理，我们能更高效地处理大规模化学数据、波谱原始文件以及复杂的 DFT 工作流，而这些往往是通用框架的痛点。

### 🛠️ 关键技术选型
- **核心语言**：Python 3.10+
- **数据库**：SQLite (WAL 模式确保高并发稳定性)
- **数据规范**：Pydantic v2 (严格的类型安全与 OpenAI Schema 自动生成)
- **API 接口**：FastAPI (高性能 Web/移动端接口)
- **化学专业库**：RDKit, NMRGlue, SpectroChemPy, DECIMER
- **交互界面**：Rich (精美的命令行输出)

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
