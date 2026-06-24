# Changelog

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

## [1.2.1] - 2026-06-18

### 新增
- **HTTP 爬虫/下载工具 (`web_fetcher`)**：支持抓取网页 HTML、提取正文文本，以及下载文件到本地。
- **无头浏览器工具 (`headless_browser`)**：基于 Playwright Chromium，支持 JS 渲染页面抓取与截图；浏览器环境未就绪时自动降级为静态 HTTP 抓取。

### 修复
- 修复 `text_writer` 多行文本写入失败的问题（`reAct` 中 JSON 参数解析改为 `strict=False`，允许未转义换行符）。
- 修复 `SubAgentLauncher` 未写入 `conversation_id` 导致 `main.py` 等待子任务时直接退出的问题。
- 修复 `SubAgentLauncher` 与 `executor` 之间 `session_id` 不一致的问题。
- 修复 `Subagent_hash` 每次实例化都重复扫描/导入子 agent 模块的问题，新增模块级缓存。
- 修复 `executor` 处理 `context` 字符串列表时的 `TypeError`。
- Coordinator 的 system prompt 现在会列出当前工作目录的顶层内容，便于子 Agent 定位文件。

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
