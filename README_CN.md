# Cloudra

专为化学科研设计的 AI Agent 协作框架。

[English](README.md)

## 核心亮点

- **自研 ReAct 框架**：不依赖 LangChain、AutoGPT 等重型框架，拥有完全可控的轻量级推理-行动循环，适合需要可追溯性的科研场景。
- **人机协同闭环**：高危/脚本操作强制进入人工审批流；Agent 可通过 `ask_user` 主动暂停任务、向用户澄清需求。
- **YOLO 全自动模式**：通过 `--yolo` 标志，可由独立的 LLM Agent 自动审批危险操作，实现无人值守流水线。GUI 中为按 Session 生效的勾选项（contextvar 隔离并传播到子 Agent 进程），互不影响。
- **流式输出与任务打断**：Coordinator 与每个子 Agent 的 LLM 增量以 `llm_chunk` 事件经 SSE 实时渲染，运行区按 Session 分面板展示对话式 transcript；任意 Session 可从 GUI/API 打断（先 `cancel_requested` 优雅退出，超时 SIGTERM 兜底，并级联取消子 Agent 与计算任务）。
- **原生 GUI 与 Linux TUI**：Windows 和 Android 使用基于 Flet 的原生 GUI（无需浏览器），Linux 保留轻量级终端 TUI，通过 `cloudra` / `cloudra run` 进入。
- **上下文压缩**：当上下文超过模型上下文窗口一半时，自动对较早的历史消息进行摘要，避免无限增长。
- **自我学习与全局案例库**：Agent 可将成功经验沉淀至全局 Case Bank，支持跨对话的记忆与经验复用。
- **科研监督员**：引入独立的 Supervisor 角色，用于监督实验过程并验证结果的科学严谨性。
- **化学工具齐全**：覆盖分子绘图、图片转 SMILES、NMR/IR 原始数据处理、Gaussian 输入生成、格式转换、输出日志解析、DFT 任务提交与监控。
- **多进程安全架构**：Coordinator 与 Follower 在独立进程中运行，基于 SQLite WAL、位标志权限、审批日志以及可选的 YOLO Guard 保障安全。
- **事件驱动架构（v2.0.0-beta）**：基于按会话隔离的 Unix domain socket 事件总线取代轮询，实现 cancel、外部事件、计算任务、子 Agent 调度的即时唤醒；数据库仍是持久化真相来源，事件仅作为唤醒机制。

## v2.0.0-beta 新特性

这是事件驱动重构的预览版本。

- **彻底消灭轮询**：`cancel_requested`、外部事件、计算任务就绪、子 Agent 请求均通过 `cloudra.ipc`（Unix domain socket）投递，不再轮询 SQLite。
- **guard 作为 calculator 父进程**：`cloudra.runtime.monitor` 改为 `wait()` 等待 calculator 退出后再解析日志，移除文件 mtime 轮询。
- **真实 token usage**：`LLMClient` 请求 `stream_options.include_usage` 并暴露 `last_usage`，不再唯一依赖 token 估算。
- **更安全的默认权限**：无 sub-agent 绑定的 `Bashtools` 默认只允许只读命令，不再放行全部权限。
- **Coordinator 子 Agent 状态快照**：每次 `_build_messages` 都会附加子 Agent session 的实时状态快照。

> **测试版说明**：公开 Python/CLI/API 接口保持不变，但内部事件总线为新增实现。如发现唤醒丢失或陈旧 IPC socket 残留，请反馈。

## 环境要求

- Python 3.10+
- 一个 OpenAI 兼容的 API Key，供 Coordinator 使用（Follower 可复用同一 Key，也可单独配置）

## 安装

### 一键安装（推荐）

**Linux / macOS：**

```bash
./install.sh
```

**Windows（PowerShell，建议以管理员身份运行）：**

```powershell
irm https://your-domain/install.ps1 | iex
# 或已克隆仓库时：
.\install.ps1
```

该脚本会检查 Python 版本、创建虚拟环境、安装完整依赖，
并交互式初始化配置，同时把 `cloudra` 命令加入 PATH。

如果系统没有 Python，脚本会自动从 python-build-standalone 下载独立 Python
运行时到项目目录，无需系统级安装或管理员权限。
无需 Rust 或 Node.js。

### 手动安装

```bash
pip install -e ".[all]"
```

所有依赖均声明在 `pyproject.toml` 中，不再维护单独的 `requirements.txt`。
无需 Rust 或 Node.js。

可选依赖：
- `pip install -e ".[all]"`：安装完整化学/浏览器/PDF 工具链。
- `pip install -e ".[gui]"`：安装 Flet GUI（Windows/Android）。
- `pip install -e ".[chem]"` / `"[browser]"` / `"[pdf]"`：单独安装某类工具。

> **集群用户注意**：运行状态保存在数据目录下的按会话 SQLite 数据库中
> （WAL 模式，默认 `~/.local/share/cloudra`）。WAL 依赖本地文件系统的可靠
> 文件锁——如果你的 home 目录挂载在 NFS/Lustre 上（集群常见），请把
> `CLOUDRA_DATA_DIR` 指向本地磁盘（如 `/tmp` 或本地 SSD）。

## 快速开始

初始化配置：

```bash
cloudra config init
```

运行任务：

```bash
cloudra run "搜索钙钛矿太阳能电池最新论文并总结关键发现"
```

交互模式（Linux 为 TUI，Windows/Android 为 GUI）：

```bash
cloudra
```

任意平台强制启动 GUI：

```bash
cloudra gui
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

> **⚠️ 严重事故警示（影响 v1.7.0–v1.7.1，已在当前代码修复）**：Supervisor 模块的 `_get_client()` 曾因一处笔误自我递归调用（`self._openai_client = self._get_client()`）。由于 Case Bank 的经验沉淀（`_persist_case` → `extract_case`）在**每次**任务结束后都会执行，该递归在每次运行时都会被触发——哪怕只是发一句“你好”。在 Python 3.13 上此递归不会抛出 `RecursionError`，栈帧以约 500MB/s 的速度持续占用内存，约 30 秒内即可耗尽整机 RAM（实测单进程 anon-rss 达 7.5GB），最终被内核 OOM killer 杀死。由于发生在任务输出打印完之后，表象为“任务结束、程序待机，随后内存被写爆”。**当前代码已改为直接构造 OpenAI 客户端、彻底消除递归；如果你在使用旧版本代码，请务必升级后再运行。**

## CLI 命令参考

```bash
# 顶层选项
cloudra --version
cloudra --coordinator-model gpt-4o --coordinator-key $KEY run "..."

# 运行任务
cloudra                                   # 交互式 TUI（Linux）或 GUI（Windows/Android）
cloudra gui                               # 强制启动 Flet GUI
cloudra run "你的任务"                    # 启动或自动恢复上次对话
cloudra run "你的任务" --new              # 强制新建对话
cloudra run "你的任务" --conv-id ID       # 继续指定对话
cloudra run "你的任务" --dry-run          # 只打印配置，不执行
cloudra run "你的任务" --yolo             # 由 LLM 自动审批危险操作

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

## API 服务（前端开发预览）

Cloudra 提供基于 FastAPI 的 HTTP API。API 与 CLI 共用 `CloudraService`
业务层。前端的一次请求对应 conversation 数据库中的一个 Coordinator Session；
Session 保存 query、状态、结果、错误和运行时间等信息。服务重启后仍能查询记录，
但正在执行的 Session 目前不会自动恢复。

```bash
python -m cloudra.api
```

服务默认只监听 `127.0.0.1:8000`。打开 `http://127.0.0.1:8000/docs`
可以使用 FastAPI 自动生成的交互式接口文档。

先创建 Conversation：

```bash
curl -X POST http://127.0.0.1:8000/api/conversations
```

然后在该 Conversation 中启动 Session：

```bash
curl -X POST http://127.0.0.1:8000/api/conversations/CONV_ID/sessions \
  -H 'Content-Type: application/json' \
  -d '{"query":"总结水分解催化剂的研究进展"}'
```

接口会立即返回 `session_id`；随后通过
`GET /api/conversations/{conversation_id}/sessions/{session_id}` 查询运行状态。
`subagent_requests` 和 `compute_jobs` 仍表示 Session 执行期间派生的内部工作。

实时事件可通过 SSE 订阅：

```text
GET /api/conversations/{conversation_id}/sessions/{session_id}/events/stream
```

Session 使用 SQLite 原子状态更新避免多个 API worker 重复领取，运行期间定时写入
`heartbeat_at`。服务启动时，失去心跳的旧 `running` Session 会变为 `interrupted`；
系统不会自动重跑它，以免重复执行写文件、发邮件或提交计算等有副作用的操作。
`parent_session_id` 连接 Coordinator 和子 Agent，`compute_jobs.session_id` 连接计算任务与发起它的 Session。

API 同时复刻了 CLI 的其他能力：

- `GET /api/config` / `POST /api/config/set`：查看与修改配置（敏感字段脱敏，值按类型 coercion）
- `GET /api/conversations/{id}/logs`：按会话读取 Agent 日志
- `GET /api/sessions?state=...`：跨会话聚合的 Session 列表
- `GET /api/skills`：可用 Skills
- `POST .../sessions` 接受 `yolo` 字段（按 Session 自动审批）；`POST .../cancel` 打断 Session

需要局域网访问时必须先配置 Token：

```bash
export CLOUDRA_API_TOKEN='请替换为足够长的随机字符串'
export CLOUDRA_API_HOST='0.0.0.0'
python -m cloudra.api
```

客户端请求需携带 `Authorization: Bearer <token>`。生成物只允许放在并访问
`<data_dir>/artifacts`，不再公开整个 Cloudra 数据目录。

### Flet GUI（原生桌面与移动端）

Cloudra 使用基于 Flutter 的 Flet 框架构建原生 GUI，同一份 Python 代码同时覆盖
桌面（Windows / macOS / Linux）和 Android。Windows 和 Android 上直接运行
`cloudra` 命令就会自动启动 GUI；任意平台也可以强制启动：

```bash
cloudra gui
```

GUI 直接调用 `CloudraService` 业务层，不经过 HTTP 中间层，响应更快。界面是自适应
布局：窗口宽度低于 720px（手机竖屏）时侧边栏自动折叠成汉堡菜单，输入框宽度自适应，
移动端单手操作也没问题。

**Android 打包：**

```bash
flet build apk
```

Flet 会把 `flet_app.py` → `cloudra/ui/app.py` 整套 Python 代码编译进 APK。
打包配置在 `pyproject.toml` 的 `[tool.flet.android]` 段，目标架构 `arm64-v8a`，
已开启 `usesCleartextTraffic` 以支持你自部署的局域网 HTTP API。

Android 上的 Cloudra 会自动屏蔽 `bashtools`、`submit_compute_job` 等依赖 shell
或外部可执行文件的工具，子 Agent 也用 asyncio 任务代替了子进程——这些运行时的细节
都在 `cloudra/runtime_profile.py` 和 `cloudra/runtime/mobile_tasks.py` 里。

**桌面打包：**

```bash
flet build windows   # 或 macos / linux
```

Flet 打包产出的桌面应用自带嵌入式 Python 运行时，目标机器不需要装 Python。
旧版 Tauri + React 前端（`frontend/`）已经完全移除，现在不需要 Rust、Node.js、
npm 这些东西了。

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
├── database.py           # SQLite 持久化
├── supervisor.py         # 科学监督与决策验证
├── tools_class.py        # BaseTool 与工具注册
├── config.py             # 配置管理
├── cli.py                # 命令行入口
├── api.py                # FastAPI 服务
├── yolo_guard.py         # YOLO 模式安全守卫
├── platform_utils.py     # 平台检测（Windows / Android / Linux）
├── runtime_profile.py    # Android 工具白名单与运行时能力画像
├── mobile_storage.py     # Flet 打包应用持久化存储
├── tools/                # 工具实现
├── subagents/            # Follower Agent 角色
├── skills/               # Markdown 格式 Skill 库
├── prompts/              # Agent Prompt 模板
├── runtime/              # 运行时调度（workers、mobile_tasks）
└── ui/                   # Flet GUI（app.py 主界面）
flet_app.py               # Flet 打包入口（Android APK / 桌面应用）
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
