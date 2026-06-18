# Changelog

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
