# Cloudra

专为化学科研设计的 AI Agent 协作框架。

[English](README.md)

## 核心亮点

- **自研 ReAct 框架**：不依赖 LangChain、AutoGPT 等重型框架，拥有完全可控的轻量级推理-行动循环，适合需要可追溯性的科研场景。
- **人机协同闭环**：高危/脚本操作强制进入人工审批流；Agent 可通过 `ask_user` 主动暂停任务、向用户澄清需求。
- **YOLO 全自动模式**：通过 `--yolo` 标志，可由独立的 LLM Agent 自动审批危险操作，实现无人值守流水线。
- **上下文压缩**：当上下文超过模型上下文窗口一半时，自动对较早的历史消息进行摘要，避免无限增长。
- **自我学习与全局案例库**：Agent 可将成功经验沉淀至全局 Case Bank，支持跨对话的记忆与经验复用。
- **科研监督员**：引入独立的 Supervisor 角色，用于监督实验过程并验证结果的科学严谨性。
- **化学工具齐全**：覆盖分子绘图、图片转 SMILES、NMR/IR 原始数据处理、Gaussian 输入生成、格式转换、输出日志解析、DFT 任务提交与监控。
- **多进程安全架构**：Coordinator 与 Follower 在独立进程中运行，基于 SQLite WAL、位标志权限、审批日志以及可选的 YOLO Guard 保障安全。

## 环境要求

- Python 3.10+
- 一个 OpenAI 兼容的 API Key，供 Coordinator 使用（Follower 可复用同一 Key，也可单独配置）

## 安装

### 一键安装（推荐）

```bash
./install.sh
```

该脚本会检查 Python 版本、可选地创建虚拟环境、以 editable 模式安装 Cloudra，
并交互式初始化配置。如果你已有 `.env` 文件，它还可以将 LLM 设置迁移到新的
YAML 配置中。

### 手动安装

```bash
pip install -e .
```

所有依赖均声明在 `pyproject.toml` 中，不再维护单独的 `requirements.txt`。

## 快速开始

初始化配置：

```bash
cloudra config init
```

运行任务：

```bash
cloudra run "搜索钙钛矿太阳能电池最新论文并总结关键发现"
```

继续上次对话：

```bash
cloudra run "继续之前的分析"
```

## 记忆机制与全局案例库 (Self-Learning & Case Bank)

Cloudra 设计了一套跨对话的记忆与自我学习机制，核心围绕 **全局案例库 (Case Bank)** 和 **科研监督员 (Supervisor)** 展开：

1. **经验提取 (Extraction)**：在每次任务结束（或暂停与用户确认）时，独立的 Supervisor Agent 会自动阅读整个对话的行动轨迹 (Trajectory)。它负责总结任务目标、最终结果、成功/失败的原因，并提炼出可供未来参考的“经验教训 (Lesson)”。
2. **全局持久化 (Persistence)**：提取出的结构化知识将被写入全局层面的 SQLite 数据库（`case_bank.db`），打破了单次对话 (Conversation) 的生命周期隔离。
3. **经验复用 (Retrieval)**：在启动新的科研任务时，Coordinator 会自动从 Case Bank 检索历史案例，并将其注入到 System Prompt 的上下文中。
4. **自我进化**：通过该机制，系统能自动避开曾经踩过的坑（如容易报错的参数组合），并优先采用验证过的成功路径，实现真正的“越用越聪明”。

## CLI 命令参考

```bash
# 顶层选项
cloudra --version
cloudra --coordinator-model gpt-4o --coordinator-key $KEY run "..."

# 运行任务
cloudra run "你的任务"                  # 启动或自动恢复上次对话
cloudra run "你的任务" --new            # 强制新建对话
cloudra run "你的任务" --conv-id ID     # 继续指定对话
cloudra run "你的任务" --dry-run        # 只打印配置，不执行
cloudra run "你的任务" --yolo           # 由 LLM 自动审批危险操作

# 配置管理
cloudra config init                     # 交互式初始化
cloudra config show                     # 查看当前配置（敏感信息脱敏）
cloudra config get coordinator.model
cloudra config set follower.model gpt-4o

# 状态查看
cloudra history                         # 历史对话列表
cloudra logs CONV_ID                    # 查看某对话日志
cloudra sessions                        # Session 状态
cloudra skills                          # 可用 Skills

# 远程邮件唤醒
python -m cloudra.email_listener
```

## API 服务

Cloudra 同时提供基于 FastAPI 的 HTTP API：

```bash
python -m cloudra.api
```

服务默认监听 `0.0.0.0:8000`，并在 `/data` 路径下提供生成的图片、报告等静态文件。

## 计算化学工作流示例

```bash
# 1. 生成 Gaussian 输入文件
cloudra run "为苯分子生成 B3LYP/6-31g(d) 的 gjf，保存到 /tmp/benzene.gjf"

# 2. 提交计算任务（同步阻塞或异步后台）
cloudra run "提交 /tmp/benzene.gjf 作为 Gaussian 任务并等待完成"

# 3. 解析输出
cloudra run "解析 /tmp/benzene.out，报告 SCF 能量、HOMO-LUMO 能隙和振动频率"
```

## 工具一览

| 类别 | 工具 |
| :--- | :--- |
| 化学工具 | `gjf_writer`、`gaussian_log_parser`、`format_converter`、`molecule_drawer`、`image_to_smiles`、`smiles_to_mol`、`nmr_processor`、`ir_processor` |
| 文献检索 | `paper_searcher`、`chemrxiv_searcher`、`pdf2md`、`text_reader`、`image_reader`、`web_fetcher`、`headless_browser` |
| 执行协作 | `bashtools`、`text_writer`、`subagent_launcher`、`submit_compute_job` |
| 人机交互 | `ask_user`、`email_sender`、`email_reader` |
| 流程控制 | `stop`、`getskill`、`get_subagent_report` |

## 安全模型

Cloudra 使用位标志权限（`READ`、`WRITE`、`SCRIPT`、`DESTRUCTIVE`、`MANAGE`）。危险操作会被挂起并写入 `approvals` 表，等待用户在 CLI/API 中显式通过或驳回。启用 `--yolo` 后，由独立的 LLM Guard（`cloudra/yolo_guard.py`）代替人工审批；请只在受信任的环境中使用。

## 项目结构

```
cloudra/
├── agent.py              # Agent 基类与 Coordinator
├── reAct.py              # ReAct 推理循环
├── executor.py           # 工具执行引擎
├── context_manager.py    # 消息/上下文渲染
├── session_manager.py    # SQLite 持久化
├── supervisor.py         # 科学监督与决策验证
├── tools_class.py        # BaseTool 与工具注册
├── config.py             # 配置管理
├── cli.py                # 命令行入口
├── api.py                # FastAPI 服务
├── yolo_guard.py         # YOLO 模式安全守卫
├── tools/                # 工具实现
├── subagents/            # Follower Agent 角色
├── skills/               # Markdown 格式 Skill 库
└── prompts/              # Agent Prompt 模板
```

## 开发

运行测试：

```bash
pytest tests -q
```

检查代码风格：

```bash
ruff check cloudra tests
```

## 许可证

MIT。完整许可证文本见 `pyproject.toml`。
