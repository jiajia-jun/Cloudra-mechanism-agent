# Changelog

## [1.6.0] - 2026-07-04

### 新增
- **统一计算任务基础设施**：新增 `cloudra.compute_utils` 模块，提供 `check_job_type`、`build_calculator_cmd`、`launch_compute_processes` 等共享函数，统一处理 Gaussian / VASP / ORCA 计算任务的依赖检查与进程启动。
- **ContextManager 上下文管理器**：引入 `cloudra.context_manager`，将此前分散的 `context` 列表收敛为数据库驱动的上下文源，支持外部事件注入与轮询，为邮件唤醒等异步交互提供统一入口。
- **compute_executor 预检与失败兜底**：Compute Executor 在启动计算前会校验计算程序可用性，启动失败或异常退出时会将任务状态更新为 `failed`。

### 重构
- **Agent 上下文接口异步化**：`Agent` 类的 `get_context`、`update_context`、`clear_context`、`llm_call` 全部改为 `async`，移除内部 `context` 列表，统一通过 `ContextManager` 读写。
- **会话状态机**：引入 `active / running / sleeping / archived` 四种会话状态，`run_task_async` 统一通过 `asyncio.run` 启动并在结束后正确转态。
- **sqlite3 → aiosqlite**：所有异步路径中的数据库访问统一使用 `aiosqlite`，避免同步 sqlite 阻塞事件循环。
- **calculator.sh 简化**：Gaussian 直接通过系统 PATH 调用 `g16 / g09 / g26`，不再要求用户在工作目录放置可执行副本。

### 修复
- 修复 `submit_compute_job` 同步模式未真正等待计算完成、错误未落库的问题，现在返回 `done` 或 `failed`。
- 修复 `cloudra/reAct.py` 缺失 `import sqlite3` 导致的 `NameError`。

## [1.5.1] - 2026-06-30

### 新增
- **Prompt 体系重构**：将各子 Agent 的 prompt 从 Python 类迁移到 `cloudra/prompts/*.md` 文件，便于独立维护与热更新。
- **Coordinator 工具范围精简**：为 Coordinator 配置更聚焦的工具集合，减少无关工具干扰，提升任务拆解与调度决策质量。
- **用户体验增强**：改进 Coordinator 与执行流程的反馈信息，让子任务状态、等待提示更清晰。

### 修复
- 修复 `text_writer` 多行文本写入失败的问题（`reAct` 中 JSON 参数解析改为 `strict=False`，允许未转义换行符）。
- 修复 `SubAgentLauncher` 未写入 `conversation_id` 导致 `main.py` 等待子任务时直接退出的问题。
- 修复 `SubAgentLauncher` 与 `executor` 之间 `session_id` 不一致的问题。
- 修复 `Subagent_hash` 每次实例化都重复扫描/导入子 agent 模块的问题，新增模块级缓存。
- 修复 `executor` 处理 `context` 字符串列表时的 `TypeError`。
- Coordinator 的 system prompt 现在会列出当前工作目录的顶层内容，便于子 Agent 定位文件。

## [1.5.0] - 2026-06-25

### 新增
- **计算化学任务提交 (`submit_compute_job`)**：支持将 Gaussian (`.gjf`)、VASP、ORCA 输入文件提交到 `compute_jobs` 任务队列，可选择同步阻塞或异步后台执行。
- **计算守护者 (`guard`)**：后台周期性解析 Gaussian 输出日志 (`.out`)，生成 `state_{taskid}.json`，任务完成后自动更新数据库状态为 `done` 或 `failed`，并唤醒对应会话的 Agent。
- **Gaussian 日志深度解析 (`gaussian_log_parser`)**：基于 `cclib` 提取 SCF 能量、HOMO/LUMO、偶极矩、振动频率、虚频、热力学修正、Mulliken 电荷及正常终止状态。
- **化学文件格式转换 (`format_converter`)**：基于 ASE 实现 `mol / xyz / gjf / pdb / cif / sdf` 等常见化学文件格式互转。
- **Gaussian 输入文件生成 (`gjf_writer`)**：从 SMILES、xyz 或 mol 文件自动生成完整的 `.gjf` 输入文件，支持自定义方法、基组、任务类型、内存与核数。

### 修复
- 修复 `compute_executor.py` 中参数校验 `is True` 永远失效的问题，改为 `is None`。
- 修复 `compute_executor.py` 启动 guard 时模块名和参数名错误（`guard` → `cloudra.guard`，`--taskid/--gjf_path` → `--task_id/--path`）。
- 修复 `guard.py` 中 `Path` 与字符串拼接导致的 `TypeError`。
- 修复 `guard.py` 中 `cclib.io.ccwrite(data.outputtype="cjson")` 的语法错误。
- 修复 `submit_compute_job.py` 同步执行路径中 `run_now` 未实现且未正确缩进为类方法的问题。
- 修复多个工具 ID 重复的问题（`getskill`、`chemrxiv_searcher`、`image_reader`、`headless_browser`、`email_sender`、`email_reader` 重新分配唯一 ID）。
- 修复 `guard.py` 解析失败时 `state_str` 未定义即被使用的潜在 `NameError`。

## [1.2.0] - 2026-06-01

### 新增
- **邮件远程控制与通知**：新增 `email_sender` 和 `email_reader` 工具，支持通过邮件发送实验报告、读取收件箱指令。
- **后台唤醒监听器 (`email_listener.py`)**：支持静默监听特定前缀（如 `CLOUDRA:`）的邮件并自动触发任务。
- **邮件安全白名单**：在配置中引入 `whitelist` 机制，仅允许授权发件人远程唤醒 Agent。
- **任务结束邮件提醒**：Coordinator 在任务结束后会自动巡检收件箱并提醒用户新消息。
- **Windows 全面兼容**：改进了 `Bashtools` 和 `CommandAnalyzer`，支持 Windows 指令集解析、路径识别及终端编码（GBK/UTF-8）自动回退。

## [1.1.0] - 2026-05-29

### 新增
- **化学结构图像识别 (`image_to_smiles`)**：基于 DECIMER (MIT License) 深度学习模型，支持将化学结构图（截图、手绘图）转换为 SMILES 字符串。
- **SMILES 转 MOL (`smiles_to_mol`)**：利用 RDKit 实现 2D/3D 结构转换。
- **人机交互工具 (`ask_user`)**：支持 Agent 在推理过程中主动发起多轮对话，用于澄清需求或收集参数。
- **多模态路径重写**：API 服务支持将本地绝对路径转换为 Web URL，方便移动端访问。

### 修复
- 修复了子进程执行时上下文加载可能导致的跨会话污染问题。
- 优化了 SQLite 数据库的并发锁定处理。
