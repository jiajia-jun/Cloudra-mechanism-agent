# Changelog

## [Unreleased]

### 新增
- **子 Agent 领域化名册**：角色从按权限划分改为按科研领域划分——`explorer`（探索+审查）、`writer`（论文写作）、`researcher`（文献）、`small_mol`（小分子量化）、`md`（分子动力学）、`dft`（第一性原理）、`experiment`（实验设计）、`env`（环境管理），删除 visionary/operator/coder。权限简化：explorer 只读、writer 读写、其余全权限，危险操作统一走审批流。
- **领域 prompt 方法论**：计算类 prompt 确立"数据可靠性第一准则"（与可靠参照不一致且无法解释 = 错误数据），教 SOP 与翻车直觉而非知识清单，起手经 `getskill` 加载对应 skill。
- **AgentHub（agent 论坛）**：新增 `hub_posts` 表（schema v6）与 `agent_hub` 工具（post/browse/read/search，支持问答串），并行子 Agent 经共享 SQLite 跨进程交换发现；只读 Agent 亦可发帖。
- **通用网页搜索**：新增 `web_search` 工具，后端链 Tavily / Brave（需 key）→ Bing / DuckDuckGo（免 key）自动 fallback，与 `web_fetcher` 组成"摘要筛选→全文抓取"两段式。
- **规划工具**：`todo_write`（多步任务清单，in_progress 唯一）与 `goal_set`（目标锚点，压缩后仍固定在上下文）。
- **Textual 全屏 TUI**：`cloudra/tui/` 重构为全屏应用——对话式消息渲染、会话（conversation）切换、主/子 Agent 上下文分屏查看与用户介入、绿/黄主题、"Cloudra Research System"横幅。
- **harness 加固**：context_window/timeout 进配置（废除硬编码）；工具参数校验失败回喂 LLM；LLM 传输层超时与状态事件；bashtools 返回 exit_code 且超长输出首尾截断；主循环死循环检测与步数预算；上下文压缩梗概持久化。

### 变更
- **`chemrxiv_searcher` 更名 `openalex_searcher`**：如实反映其实际检索 OpenAlex 全库（从未过滤 ChemRxiv）；Android 工具白名单与文档同步。
- **工具描述统一改写**：全部工具描述改为"功能/适用/不适用（改用谁）/关键纪律"结构，补齐工具间分工边界（搜索链路、PDF 链路、文件修改链路、计算流水线）。
- CLI 横幅版本号改为读取 `cloudra.__version__`，与 `pyproject.toml` 统一（2.0.0-beta）。

### 修复
- **YOLO 审批不返回 tool_call**：YoloGuard 遇到模型未返回 `submit_approval_decision` tool_call（或参数无法解析）时，不再把 "未返回 tool_call" 这类内部实现错误作为拒绝原因抛给主 Agent，而是在 Guard 内部打印告警、纠正模型并重试（最多 3 次）；耗尽后按默认安全策略拒绝，返回给主 Agent 的是不含实现细节的中性原因。

## [1.8.0] - 2026-07-18

### 新增
- **ASE 建模参考库**：`first-principles-calculation` skill 新增 `references/`（`ase-guide.md`、`ase-quick-reference.md`、3 个可运行示例脚本），内容引自 [jkitchin/skillz](https://github.com/jkitchin/skillz)（MIT，已保留版权声明），写 ASE 脚本前可经 `getskill` 的 `other` 参数按需加载。
- **全链路异步化**：LLM 调用全部迁移到 `AsyncOpenAI`（agent / yolo_guard / supervisor / context_manager / memory），消除同步调用冻结事件循环的问题。
- **Token 级流式输出**：`reAct` 以节流方式把 LLM 增量写入 `llm_chunk` 事件，前端 SSE 实时渲染；子 Agent（Follower）默认开启流式。
- **任务打断**：API/前端可请求打断 Session（先置 `cancel_requested` 由 Agent 自行退出，超时 SIGTERM 兜底），支持级联取消子 Agent 与计算任务。
- **对话式运行视图**：前端运行区改为按 Session 分面板的 transcript（思考/内容/工具气泡），Coordinator 与子 Agent 各自署名；终态后在对话末尾展示唯一"最终结果"总结。
- **前端对齐 CLI 全部功能**：YOLO 按 Session 勾选（contextvar + 子进程 env 传播）、设置弹窗（`GET/POST /api/config`）、日志查看器（`/logs`）、跨会话 Sessions 监控（`/api/sessions` 聚合）、Skills 列表。
- **Tauri 桌面端**：`frontend/src-tauri` 原生壳 + sidecar 自动拉起后端；`frontend/scripts/package-desktop.sh` 一键产出含独立 Python 运行时的 `dist-app/` 分发目录（目标机零依赖）。
- **配置 API**：`GET /api/config`（脱敏）与 `POST /api/config/set`（含类型 coercion），与 `cloudra config set` 共用实现。

### 修复
- **数据库锁冲突**：遥测写入改异步可丢弃，LLM 调用增加 429/5xx 指数退避重试。
- **reAct stop 结果**：`session.result` 改为最后一条 assistant 正文，不再保存 stop 工具的原始 JSON 返回。
- **pip 包缺数据文件**：`pyproject.toml` 补充 package-data（prompts / skills / calculator.sh），修复 wheel 安装后 `_load_prompt` 报错。

## [1.7.1] - 2026-07-12

### 新增
- **前端 UI 从零实现**：像素风格（Unifont）、纯黑主题、绿/黄强调色；左侧会话列表、消息渲染、Session Trace、审批面板、JSON 结构化查看器、Markdown 自动渲染、清空会话二次确认弹窗。
- **前端构建产物**：`frontend/dist/` 已生成，后端直接挂载。
- **会话清空**：左侧栏新增“清空会话”按钮，二次确认后删除所有 Conversation / Session / 消息 / 审批记录。
- **Tool JSON 结构化渲染**：tool 消息解析为可折叠 JSON 树；字符串值若含 Markdown 则自动渲染，并支持 TXT/MD 切换。

### 改进
- **后端 API**：新增 `DELETE /api/conversations` 与 `CloudraService.delete_all_conversations()`；CORS 支持 DELETE。
- **后端数据模型**：调整 `session` 表结构以支持新的 Session 生命周期与事件记录。

## [1.7.0] - 2026-07-09

### 新增
- **自我学习与记忆** (Self-learning memory)：引入记忆机制，让 Agent 可以从过去的对话和成功案例中进行学习和反思。
- **科研监督员** (Scientific Supervisor)：新增用于监督实验进度、确保科研严谨性并验证结果的独立 Agent。
- **全局案例库** (Case Bank)：重构案例存储结构，将原先跟随对话生命周期的局部 DB 升级并迁移到全局 Case Bank，支持跨对话检索与经验复用。

### 改进
- **PDF 解析优化**：使用 `PyMuPDF` 彻底重构 PDF 提取逻辑，并在后台线程异步执行。
- **YOLO Guard 网络增强**：在遇到请求头被 OpenAI 或中转站拦截时，自动切换 User-Agent 进行 fallback 请求。
- **Function Calling 健壮性**：增加根据参数自动反推工具名的兜底机制，以兼容部分中转站返回的空工具名。

## [1.6.3] - 2026-07-07

### 新增
- **论文写作 Skill**：新增 `research-paper-writing` skill，指导 AI 进行学术论文写作、Markdown/LaTeX 排版、期刊模板格式化。
  - 包含 storytelling、introduction、abstract、method、experiments、conclusion、related-work 等章节写作指南
  - 包含 LaTeX 期刊模板指南（IEEE/Nature/Elsevier/ACM/APA）
  - 包含命令行工具使用指南（Pandoc/LaTeX 编译/参考文献管理）

### 改进
- **Writer Prompt**：更新 writer prompt，明确论文写作时调用 `research-paper-writing` skill，约束行文风格，禁止夸大其词。

## [1.6.2] - 2026-07-04

### 新增
- **Coordinator 异步计算等待与事件唤醒**：异步提交计算任务后，Coordinator 不再立即退出，而是保持进程存活并轮询后台任务；当 `guard` 注入计算完成事件后，Coordinator 会被唤醒继续处理结果。
  - 扩展 `_wait_for_subtasks` 为 `_wait_for_background_tasks`，同时等待子 Agent 任务和计算任务。
  - `run_task_async` 新增事件唤醒循环。
  - 新增 `tests/test_run_task_async.py` 测试。

## [1.6.1] - 2026-07-04

### 新增
- **YOLO 全自动模式**：新增 `--yolo` CLI 选项，危险操作不再等待用户审批，而是由独立的 LLM Agent 自动判断是否合理。
  - 新增 `cloudra/yolo_guard.py` 安全判断模块
  - 新增 `prompts/yolo_guard.md` 审计员 prompt
  - 新增 `tests/test_yolo_guard.py` 测试
- **上下文压缩**：当上下文超过模型上下文窗口一半时，自动对最近 10 轮 assistant 之前的历史消息调用 LLM 生成梗概，避免无限增长。
  - 新增 `cloudra/token_estimator.py` 轻量级 token 估算器
  - 新增 `tests/test_context_manager.py` 测试
- **多模态渲染优化**：图片 base64 编码、视觉降级、视觉历史窗口（最近 10 轮）全部下沉到 `ContextManager.build_messages()`，简化 `Agent.llm_call()`。
- **模型视觉能力配置**：`LLMConfig` 新增 `supports_vision` 字段，可在 `config.yaml` 中分别为 Coordinator/Follower 配置。

### 改进
- `Agent.llm_call()` 大幅简化，移除重复的消息构建和异常驱动降级逻辑。
- `ContextManager` 成为上下文的唯一渲染来源，职责更清晰。
- 区分 `max_tokens`（生成限制）与 `context_window`（上下文窗口），避免大上下文模型配置冲突。
- 统一依赖源到 `pyproject.toml`，删除独立的 `requirements.txt`，并补齐 `fastapi`/`uvicorn`。
- `cloudra.__version__` 现在作为唯一版本来源，`cli.py` 与 `api.py` 同步读取。

### 移除
- 删除 `draw_caffeine.py`（废弃的临时脚本）。

## [1.6.0] - 2026-06-18

### 新增
- 异步计算任务基础设施
- `ContextManager` 统一上下文管理
- sqlite 迁移到 aiosqlite

## [1.5.1] - 2026-05-23

### 改进
- 重构 prompts
- 限制 Coordinator 可用工具范围
- 改进 UX 反馈
