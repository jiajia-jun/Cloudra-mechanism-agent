# Changelog

## [1.0.0] - 2026-05-20

### 重构
- **CLI 化**：从脚本升级为标准 Python CLI 工具，入口命令为 `cloudra`。
- **包化**：核心代码组织为 `cloudra/` 标准包，支持 `pip install -e .`。
- **配置系统**：引入 Pydantic Settings 多层配置（CLI 参数 > 环境变量 > 配置文件 > 默认值），兼容原有 `.env`。
- **数据隔离**：运行时数据（conversations, logs, sessions, tasks）迁移至 `~/.local/share/cloudra/`（platformdirs）。

### 新增
- `cloudra run`：运行任务，支持 `--conv-id` 和 `--dry-run`。
- `cloudra history`：历史对话列表（Rich 表格）。
- `cloudra logs <conv_id>`：查看对话日志。
- `cloudra sessions`：查看 Session 数据库状态。
- `cloudra skills`：列出可用 Skills。
- `cloudra config`：配置管理（init / show / get / set）。
- `cloudra --version`：版本信息。

### 安全
- **权限模型重构**：从 `list[bool]` 升级为 `IntFlag` 位运算模型。
- **命令解析重构**：Bashtools 改用 `shlex` 结构化解析，消除子串匹配误判（如 `echo rm` 不再被判定为 destructive）。
- 支持管道链分析（`ls | python process.py`）和变量赋值前缀识别。

### 修复
- 修复 `main.py` Banner 版本号与 `README` 不一致的问题。
- 修复 `agent.py` 中 `has_write_permission` 和 `has_manage_permission` 重复定义的问题。

## [0.2.0] - 2026-05-15
- 新增化学结构式绘制工具 `molecule_drawer`。
- 新增视觉感知工具 `image_reader`。
- 新增 `Visionary` 子 Agent。
- 重构 `llm_call` 与 `update_context`，支持多模态上下文。

## [0.1.9] - 2026-05-12
- 升级为多进程并发架构。
- 优化为单循环 ReAct。
- 实现日志会话隔离与结果实时管道转发。
