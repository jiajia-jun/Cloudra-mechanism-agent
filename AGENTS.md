# AGENTS.md — Cloudra 项目指南

给 AI 助手与新贡献者的仓库导航。项目定位与三层架构（control plane / research runtime / execution plane）见 `README.md`，这里只讲代码布局、边界约定与开发命令。

## 命令

```bash
uv run pytest -q tests/            # 全套测试
uv run pytest -q tests/test_dag*   # 聚焦某个子系统（按文件名前缀选）
uv run ruff check cloudra tests    # lint（line-length 120，select E/F/W/I）
uv run python -m compileall -q <改动文件>   # 改完先做语法检查
CLOUDRA_UPDATE_TUI_SNAPSHOT=1 uv run pytest tests/test_tui_visual*  # 更新 TUI 视觉基线
```

入口：`cloudra`（CLI，`cloudra/cli.py`）、`cloudra-api`（FastAPI 控制面，`cloudra/services/api.py`）、`flet_app.py`（GUI/APK 打包入口）。Python >= 3.11。

## 模块地图（cloudra/ 包）

根目录只留 `cli.py` / `__main__.py` / `__init__.py`（惰性兼容导出）；实现按职责分五个子包：

**`core/` — 核心运行时（推理与编排）**

- `react.py` — ReAct 推理循环主体（流式 LLM、工具调度、取消/重试）。
- `agent.py` — `Agent`/`Coordinator`/`Follower` 角色与 prompt 加载。
- `supervisor.py` — 科学督导（SupervisorAgent、GraphSupervisor），只在 `dag_guided` 模式有写图权限。
- `main.py` — 薄封装；实际执行在 `runtime/`：`runner.py`（任务入口）、`executor.py`（子 Agent 子进程）、`compute_executor.py` + `monitor.py`（计算任务与日志监视）、`workers.py`（后台线程池）、`prompt_assembler.py`（确定性 system prompt 组装）、`environment_observer.py`（工作区快照）。
- `dag/` — DAG 引导编排子系统（仍在包根一级），见下节。

**`services/` — 服务层 / 控制面**

- `service.py` — 应用服务层，CLI 与 HTTP API 共用（Session 提交、审批、取消、DAG 用户变更）。
- `api.py` / `api_v1.py` — FastAPI 路由；v1 为远程控制（SSE、审批、产物）。
- `backends.py` — UI 后端边界：本地桌面 vs 远程 Android 的统一抽象。
- `session_store.py` — Session/子任务/审批状态迁移的**唯一写入入口**。
- `control_store.py` — 幂等远程控制命令持久化；`interactions.py` — 非审批类用户交互等待。
- `nodes.py` — 多节点/工作区注册表路由；`device_broker.py` — Android 设备配对与调用。

**`persistence/` — 持久化 / 状态**

- `database.py` — 会话级 SQLite（ConversationDB）；`conversation_repo.py` — 会话查询唯一入口。
- `artifacts.py` — 不可变产物快照（ArtifactService）与短期下载授权。
- `memory.py`（长期记忆 MEMORY.md）、`case_bank.py`（经验案例库）、`context_manager.py`（Agent 上下文）、`context_stats.py`（只读按-agent 上下文统计，供 TUI `/context` 与状态栏）。
- `paths.py` — data_dir 下所有路径的**唯一事实来源**；`fs_utils.py` — 原子写；`workspace.py` — 工作区受限读写。

**`base/` — 数据类与基类**

- `skill_class.py` / `tools_class.py` — 加载器与基类。
- `session_class.py` / `conversation_class.py` / `log_class.py` — 数据类。

**`infra/` — 支撑设施**

- `config.py`（LLMConfig/CloudraConfig）、`llm_client.py`（OpenAI 兼容传输层）、`web_search_native.py`。
- `events.py`（进程内/间事件门面）、`ipc.py`（会话级事件总线）、`streaming.py`、`token_estimator.py`。
- `slurm.py`、`compute_utils.py`、`operations.py`（数据目录备份/恢复）、`yolo_guard.py`（自动审批安全守卫）。
- `presentation.py` / `tool_presentation.py`、`platform_utils.py`、`runtime_profile.py`（mobile 能力 profile）。
- `email_listener.py`、`mobile_storage.py`、`native_bridge.py`、`android_build.py`。

**包根一级子包（未动）**：`dag/`、`runtime/`、`tools/`、`subagents/`、`tui/`、`ui/`、`device/`、`prompts/`、`skills/`。

**UI 前端**

- `tui/new/` — Textual 全屏 TUI（主界面）：`screens/`（main/approval/ask_user/context/dag/help）、`widgets/`（chat_log、input_bar、side_panel、status_bar 等）、`commands.py`（斜杠命令注册）、`transcript*.py` + `render_bridge.py`（事件→屏幕渲染管线）。
- `tui/new/watchdog.py` + `runtime_proc.py` + `control.py` — **默认进程隔离**：父进程拉起本机 FastAPI runtime（Agent）与可杀的 TUI 子进程；UI 假死只重启 TUI。`CLOUDRA_TUI_INLINE=1` 回退同进程；`CLOUDRA_TUI_NO_WATCHDOG=1` 禁用界面重启；`CLOUDRA_TUI_RUNTIME_URL` 复用已有 runtime。
- `tui/legacy_app.py` — prompt_toolkit 旧版 TUI；`tui/run.py` — 入口；`tui/render.py` — IPC 终端渲染。
- `ui/app.py` — Flet 桌面/移动 GUI；根目录 `flet_app.py` 为打包入口。

**能力与角色**

- `tools/` — 按领域分组的工具（Bashtool/Chemtool/Searchtool/Writetool/Plantool 等）；`tools/registry.py` 注册；`tools/core/` 含命令分级、权限模型、文件变更审批流水线、`coord_guard.py`（手写坐标守卫：向 .gjf/.xyz/.com 写入逐字坐标块在 text_writer/edit_file/bashtools 层放行但附警告并点破"绕过 supervisor/DAG 审查"，坐标必须来自 smiles_to_mol/format_converter/gjf_writer 等工具）、`bash_habit_guard.py`（bash 习惯守卫：heredoc/echo/tee/sed -i 写文件等命令在 bashtools 层附警告；长上下文 + 连续 bash / 直调量化程序时由 reAct harness 注入系统警告）、`delegation_guard.py`（Coordinator 自行 `submit_compute_job` 时在工具结果附轻量提示，照常放行）。工具**无持久状态**，结构化输出由 DAG 适配器解释。
- `subagents/` — 领域子 Agent（dft、md、researcher 等 8 个角色）。
- `prompts/*.md`、`skills/*` — 角色 prompt 与科研方法技能包。

## dag/ 子系统（DAG 引导编排）

按会话 opt-in：`orchestration_mode` ∈ `standard`（默认，不读不写图）/ `dag_record`（只记录）/ `dag_guided`（记录 + Supervisor 引导），session 创建时写入、之后不可变。UI/CLI/API 三入口都可选择；TUI 用 `/mode off|record|guided`。

- `models.py` — 共享类型与 `build_orchestration_config()`。图元素是类型化判别联合：节点按 `node_type` 分 `PlannedNode`/`ObservedNode`（process）与 `OccurrenceNode`（delivery），边按 `edge_type` 分 `DependencyEdge`/`ElementaryStepEdge`，约定字段（status/assignee/evidence_level/role/smiles/派生证据位等）为显式字段，自由扩展位收敛为 `metadata`；`GraphOperation` 是以 `op` 判别的具名命令联合（AddNode/AddEdge/RemoveEdge/UpdateNode/UpdateEdge/AttachRef/AddLink/SetCoverageContract/WaiveGate）。`parse_dag_node`/`parse_dag_edge`/`parse_graph_operation` 对旧 data-dict 形状与旧词表（workflow/intermediate_occurrence 等）只读兼容，旧 journal 可重放。
- `store.py` — 双 DAG（process 流程图 + delivery 机理图）持久存储，变更日志 + 物化视图。证据引用存关联表 `dag_evidence_bindings`（读路径以它为准，左连接 `dag_evidence` 重建 GraphRef；节点/边的 `refs` 内联 JSON 列保留为兼容兜底，关联表无记录时回退）；写路径双写（`attach_ref` 记账带 evidence_role，物化时对账补缺并清理孤儿绑定），v11 旧库由 init 一次性迁移。
- `engine.py` — 事务化变更引擎 `DagEngine`：原子批次、乐观 revision、无环校验。按图分权：Supervisor 只读 delivery、维护 process；agent（Coordinator/子 agent）设计 delivery，process 侧只能回报 `assignee` 等于自己的节点（status/reason/blocked_reason/annotations）。`remove_edge` 两张图都放开但批次必须带 rationale；agent 对 process 的删边请求以 `edge_removal_requires_supervisor` 拒绝并记日志，由 Supervisor 复核后代为执行。
- `completion.py` — 交付覆盖率确定性评估 `evaluate_delivery()` 与 prompt 投影。
- `controller.py` — harness 集成 `DagController`：工具证据持久化、DAG prompt 注入（含按 actor 过滤的 `assigned_to_me` 区块）、Supervisor 触发（机理变更/绑定计算的成败/删边请求/交付前审计）、`rederive_delivery_element()` 事后补挂重算、`bind_evidence_for_call()`（agent 挂载证据的唯一入口：tool_call_id 反查 + 存在性/成功性确定性校验）、`review_evidence()`（Supervisor confirm/downgrade/reject 三选一，否决经 `evidence_vetoed` 事件通知挂载者与 Coordinator）。

关键不变量：图存储是权威（不在模型上下文里）；证据是不可变记录/产物的类型化引用；删除必须带理由且留在变更日志；模型声明不能标记交付完成，证据等级由 harness 确定性派生。

## 测试约定（tests/）

- 按文件名前缀分组：`test_dag_*`（DAG）、`test_tui_*` / `test_textual_tui`（TUI）、`test_react_*`（推理循环）、`test_approval_*` / `test_cancel_flow` / `test_wakeup_logic`（控制流）、`test_api` / `test_service` / `test_frontend_parity`（服务层）、`test_device_*` / `test_mobile_runtime`（Android）、`test_compute` / `test_slurm`（计算执行）、化学工具各一、其余为基础设施单测。
- `conftest.py` autouse 隔离 data_dir 到 tmp_path；不要在测试里写真实数据目录。
- 跳过均按环境探测：缺 `crest`/`xtb` 二进制、无 symlink 权限、非 POSIX、APK 未构建。无需要真实 LLM key 的测试。
- 测试替身（fake/stub）签名要对齐真实接口，建议带 `**_kwargs` 防接口加参后变红。

## 顶层散件

- `scripts/build_android.py`（APK 构建驱动）、`scripts/profile_textual_tui.py`（TUI 性能分析）。
- `extensions/cloudra_native/` — 独立子包（Android 原生服务桥，自有 pyproject）。
- `deploy/node-registry.example.json` — 多节点/Slurm 注册表示例。
- `docs/` — 专题文档索引；`docs/superpowers/plans/` 存放设计计划（如 DAG 设计）。
- `install.sh` / `install.ps1` — 安装脚本；`build/`、`.flet/`、`.worktrees/`、`cloudra.egg-info/` 为构建副产物，勿手改。
- `软著申请材料/`、`copyright_docs/`、`*.pdf` 研究报告 — 申报材料，非代码。

## 工作约定

- 最小改动：修 bug 不顺手重构；新代码跟随所在文件的既有风格与注释密度。
- **事件循环线程禁止同步阻塞调用**：`async` 函数体内不得直接调用同步 SQLite（`db.connect()`/`retry_on_locked`）、`time.sleep`、`subprocess.run`、同步网络库——一律 `asyncio.to_thread` 卸载或用 `a` 前缀异步变体。同步 SQLite 只允许在守护线程 / CLI / 测试上下文使用。曾因此造成跨进程 5 分钟级 "database is locked" 死锁（同步忙等冻结 loop → 同进程 aiosqlite 无法 commit）。护栏：运行时 `ConversationDB.connect()`/`retry_on_locked()`/`init()` 会告警（`CLOUDRA_DB_SYNC_ON_LOOP=raise` 抛错、`=off` 关闭），`tests/test_no_sync_on_loop.py` 静态扫描常驻。
- 不引入项目未依赖的库；可选能力走 `pyproject.toml` 的 extras（gui/chem/browser/pdf/dev）。
- 改了结构、命令或约定时同步更新本文件。
- 未经明确要求不做 git 提交/推送等变更操作。
