# Changelog

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
