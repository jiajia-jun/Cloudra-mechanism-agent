# Changelog

## [Unreleased]

### 新增
- 子 Agent 按领域重命名：explorer（探索+审查）、writer（论文写作）、researcher（文献）、small_mol（小分子量化）、md（分子动力学）、dft（第一性原理）、experiment（实验设计）、env（环境管理），替换掉 visionary/operator/coder。explorer 只读，writer 读写，其余全权限，危险操作统一走审批。
- 计算类 prompt 方法论：教 SOP 和翻车直觉而不是知识清单，起手先 `getskill` 加载对应 skill。
- AgentHub：加 `hub_posts` 表（schema v6）和 `agent_hub` 工具（post/browse/read/search，支持问答串），并行子 Agent 可共享 SQLite 发帖，只读 Agent 也能发。
- 通用网页搜索：加 `web_search` 工具，Tavily/Brave（需 key）→ Bing/DuckDuckGo（免 key）自动 fallback，和 `web_fetcher` 两段式用。
- 规划工具：加 `todo_write`（多步清单，同一时刻只能有一个 in_progress）和 `goal_set`（目标锚点，压缩后仍钉在上下文里）。
- Textual 全屏 TUI：`cloudra/tui/` 重写成全屏应用，支持对话消息渲染、会话切换、主/子 Agent 上下文分屏、绿/黄主题。
- harness 加固：`context_window`/`timeout` 进配置（不再硬编码）；工具参数校验失败会反馈给 LLM；传输层加超时和状态事件；`bashtools` 返回 `exit_code` 且截断超长首尾输出；主循环死循环检测；上下文压缩概要持久化。
- 模型原生联网搜索：`LLMConfig.native_search`（默认 `auto`）+ `native_search_params`。按 base_url/model 自动识别适配器（openai 搜索模型 / openrouter `web` 插件 / deepseek / gemini / custom），启用后在请求里注入服务商侧搜索工具、剔除外部 `web_search` 函数工具，避免双重搜索；结果以内联引用返回。状态栏显示「联网·<provider>」，聊天区把 `web_search_call` 事件并入「思考过程」。
- DeepSeek 原生搜索走 Responses API：新增 `LLMClient.create_responses`（POST `/responses`），把 chat.completions 风格的 kwargs/响应翻译成 Responses 形状（含流式 SSE 与 tool_call 增量合并），reAct 层零改动；base_url 尾部 `/v1` 自动兼容。
- 联网搜索引导：有搜索能力（原生或 `web_search` 工具）时，在 system prompt 注入「联网搜索（重要）」段落，要求任务依赖实时/外部信息时先搜再答。
- `todo_read` 工具：与 `todo_write`/`goal_set` 配对，随时读取当前任务清单与目标锚点；每 10 轮或 supervisor 反对时注入提醒，让 todo 真正驱动每轮行为。
- 目标严格模式与 `/goal` 命令：TUI 新增 `/goal <目标>`（设置目标锚点并固定到 Coordinator 上下文）、`/goal pause`（暂停当前任务）、`/goal`（查看）。设置目标后任务只有调用 `stop` 才能结束，无工具轮会注入「确认 goal 是否完成」提醒；未设目标时保持传统语义（有正文即完成）。
- 移除 `MAX_STEPS` 步数上限：循环结束由 `stop`/取消/死循环检测决定，不再有硬性步数天花板。
- `submit_compute_job` 支持 CP2K：新增 `cp2k` job_type（`calculator.sh` 分支、PATH 检查、`.out` 日志路径），guard 用轻量文本解析 CP2K 输出（cclib 已移除 CP2K 解析器）；顺带修复 guard 未透传 job_type 导致非 Gaussian 日志路径错配的问题。

### 变更
- `chemrxiv_searcher` 改名叫 `openalex_searcher`，它其实一直检索整个 OpenAlex，没过滤过 ChemRxiv；Android 工具白名单和文档同步更新。
- 所有工具描述统一成“功能/适用/不适用/关键纪律”结构，把搜索、PDF、文件修改、计算流水线之间的分工边界写清楚。
- CLI 横幅版本号从 `cloudra.__version__` 读取，和 `pyproject.toml` 一致为 2.0.0-beta。
- 死循环检测与步数预算：移除步数预算相关逻辑，保留 `AgentStuckLoop`（相同工具+参数连续调用）作为防空转兜底。
- 联网搜索展示：`web_search_call` 状态事件改为流中段逐条上报，并入「思考过程」面板而非孤立系统框。

### 修复
- YOLO 审批时模型没返回 `submit_approval_decision` tool_call 或参数解析失败，不再把“未返回 tool_call”这种内部实现错误当拒绝理由甩给主 Agent，而是在 Guard 内部告警、纠偏并重试（最多 3 次）；耗尽后按默认安全策略拒绝，返回给主 Agent 的是不含实现细节的中性原因。
- TUI 代码块「复制」按钮失效：`on_click` 命中检测未减去边框/内边距 gutter，4×1 热区永远点不中；修复并加回归测试。
- 审批/提问弹窗 `MarkupError` 崩溃：动态内容（工具参数、命令输出）按 console markup 解析遇 `[` 抛错打崩整个 TUI；改为 `SafeStatic`（markup 解析失败自动降级纯文本）+ `markup=False`。
- DeepSeek Responses 流式翻译缺 key：chunk 的 `delta`/`message` 未常驻 `content`/`tool_calls`，reAct 直接属性访问抛 `AttributeError('tool_calls')`；统一补齐占位 key，`ResponseDictWrapper.model_dump` 尊重 `exclude_none`。
- DeepSeek Chat Completions 注入 `web_search` 工具被 400 拒绝（`tools[..].type: unknown variant`）：原生搜索一律走 `/responses`，chat 路径不再注入。

## [1.8.0] - 2026-07-18

### 新增
- `first-principles-calculation` skill 加 `references/`（`ase-guide.md`、`ase-quick-reference.md` 和 3 个可运行示例脚本），内容来自 [jkitchin/skillz](https://github.com/jkitchin/skillz)（MIT，已保留版权声明）。写 ASE 脚本前可用 `getskill` 的 `other` 参数按需加载。
- LLM 调用全链路迁到 `AsyncOpenAI`（agent / yolo_guard / supervisor / context_manager / memory），解决同步调用冻结事件循环的问题。
- Token 级流式输出：`reAct` 把 LLM 增量以流式写入 `llm_chunk` 事件，前端 SSE 实时渲染；子 Agent（Follower）默认开启流式。
- 任务打断：API/前端可请求打断 Session，先置 `cancel_requested` 由 Agent 自行退出，超时后 SIGTERM 兜底，支持级联取消子 Agent 和计算任务。
- 对话式运行视图：前端运行区改成按 Session 分面板的 transcript，区分思考/内容/工具气泡，Coordinator 和子 Agent 各自署名；终态后在对话末尾只展示一个“最终结果”总结。
- 前端补齐 CLI 全部功能：YOLO 按 Session 勾选、设置弹窗（`GET/POST /api/config`）、日志查看器（`/logs`）、跨会话 Sessions 监控（`/api/sessions` 聚合）、Skills 列表。
- 配置 API：`GET /api/config`（脱敏）和 `POST /api/config/set`（带类型 coercion），与 `cloudra config set` 共用实现。

### 变更
- 移除 Tauri 桌面端和预构建的 `frontend/dist/` 目录；当前控制界面以 Textual TUI 为准，`cloudra gui` 仅作为实验性入口保留，暂不推荐生产使用。

### 修复
- 数据库锁冲突：遥测写入改成异步可丢弃；LLM 调用对 429/5xx 加指数退避重试。
- `reAct stop` 结果：`session.result` 现在取最后一条 assistant 正文，不再保存 stop 工具的原始 JSON 返回。
- pip 包缺数据文件：`pyproject.toml` 补 `package-data`（prompts / skills / `calculator.sh`），修复 wheel 安装后 `_load_prompt` 报错。

## [1.7.1] - 2026-07-12

### 新增
- 会话清空：左侧栏加“清空会话”按钮，二次确认后删除所有 Conversation / Session / 消息 / 审批记录。

### 改进
- 后端 API：新增 `DELETE /api/conversations` 和 `CloudraService.delete_all_conversations()`；CORS 支持 DELETE。
- 后端数据模型：调整 `session` 表结构以支持新的 Session 生命周期和事件记录。

## [1.7.0] - 2026-07-09

### 新增
- 自我学习与记忆：Agent 可以从过去的对话和成功案例里学习和反思。
- 科研监督员：新增独立 Agent，监督实验进度、确保科研严谨性并验证结果。
- 全局案例库：案例存储结构从原来的局部 DB 升级到全局 Case Bank，支持跨对话检索和经验复用。

### 改进
- PDF 解析：用 PyMuPDF 重构 PDF 提取逻辑，改到后台线程异步执行。
- YOLO Guard 网络：请求头被 OpenAI 或中转站拦截时，自动切换 User-Agent 做 fallback 请求。
- Function Calling 健壮性：根据参数反推工具名的兜底机制，兼容部分中转站返回空工具名的情况。

## [1.6.3] - 2026-07-07

### 新增
- `research-paper-writing` skill：指导 AI 写学术论文、Markdown/LaTeX 排版、期刊模板格式化。覆盖 storytelling、introduction、abstract、method、experiments、conclusion、related-work 等章节；包含 IEEE/Nature/Elsevier/ACM/APA 的 LaTeX 模板；包含 Pandoc/LaTeX 编译和文献管理工具用法。

### 改进
- 更新 writer prompt，要求写论文时调用 `research-paper-writing` skill，约束行文风格，禁用夸大其词。

## [1.6.2] - 2026-07-04

### 新增
- Coordinator 异步计算等待与事件唤醒：异步提交计算任务后，Coordinator 不再立即退出，而是保持存活并轮询后台任务；当 `guard` 注入计算完成事件后，Coordinator 被唤醒继续处理结果。
  - `_wait_for_subtasks` 扩展为 `_wait_for_background_tasks`，同时等子 Agent 任务和计算任务。
  - `run_task_async` 加事件唤醒循环。
  - 新增 `tests/test_run_task_async.py` 测试。

## [1.6.1] - 2026-07-04

### 新增
- `--yolo` CLI 选项：危险操作不再等用户审批，由独立 LLM Agent 自动判断是否合理。
  - 新增 `cloudra/yolo_guard.py` 安全判断模块。
  - 新增 `prompts/yolo_guard.md` 审计员 prompt。
  - 新增 `tests/test_yolo_guard.py` 测试。
- 上下文压缩：上下文超过模型窗口一半时，自动对最近 10 轮 assistant 之前的历史消息调 LLM 生成概要，避免无限增长。
  - 新增 `cloudra/token_estimator.py` 轻量 token 估算器。
  - 新增 `tests/test_context_manager.py` 测试。
- 多模态渲染优化：图片 base64 编码、视觉降级、视觉历史窗口（最近 10 轮）全部下沉到 `ContextManager.build_messages()`，简化 `Agent.llm_call()`。
- 模型视觉能力配置：`LLMConfig` 加 `supports_vision` 字段，可在 `config.yaml` 里分别为 Coordinator/Follower 配置。

### 改进
- `Agent.llm_call()` 大幅简化，移除重复的消息构建和异常驱动降级逻辑。
- `ContextManager` 成为上下文的唯一渲染来源，职责更清晰。
- 区分 `max_tokens`（生成限制）与 `context_window`（上下文窗口），避免大上下文模型配置冲突。
- 统一依赖源到 `pyproject.toml`，删除独立的 `requirements.txt`，补齐 `fastapi`/`uvicorn`。
- `cloudra.__version__` 作为唯一版本来源，`cli.py` 和 `api.py` 同步读取。

### 移除
- 删除废弃的临时脚本 `draw_caffeine.py`。

## [1.6.0] - 2026-06-18

### 新增
- 异步计算任务基础设施。
- `ContextManager` 统一上下文管理。
- sqlite 迁到 aiosqlite。

## [1.5.1] - 2026-05-23

### 改进
- 重构 prompts。
- 限制 Coordinator 可用工具范围。
- 改进 UX 反馈。
