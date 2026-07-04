# ⚗️ Cloudra 项目协作指南 (Team Guide)

Cloudra 是一个面向化学科研的 AI Agent 协作框架。本指南帮助新成员快速理解项目设计哲学、核心架构和贡献方式。

---

## 1. 设计哲学：人机耦合 (Human-in-the-Loop)

我们坚持 **“AI 是副驾驶，人类是机长”**。

- **不追求 100% 无人自动化**：化学实验环境复杂，遇到异常时让 AI 停下来问人，比盲目继续更安全。
- **关键决策点交还给人类**：泛函选择、反应路径确认、异常数据甄别、耗时 DFT 任务提交前，都应通过 `ask_user` 寻求确认。
- **专家协作而非单模型包办**：Coordinator 负责任务拆解，Follower（Researcher / Visionary / Coder / Operator 等）负责执行，模仿真实课题组。

---

## 2. 核心架构

| 组件 | 关键文件/类 | 职责 |
| :--- | :--- | :--- |
| 协调者 | `agent.py` (`Agent`, `Coordinator`) | 与 LLM 底层通信，Coordinator 维护全局 Prompt |
| 推理循环 | `reAct.py` (`reAct`) | Thought → Action → Observation 循环，解析工具调用 JSON |
| 执行引擎 | `executor.py` (`Executor`) | 运行工具类，处理并发与错误捕获 |
| 上下文管理 | `context_manager.py` (`ContextManager`) | 统一渲染消息、图片 base64、上下文压缩 |
| 持久化 | `session_manager.py` (`SessionManager`) | SQLite 存储对话、审批、计算任务 |
| 工具协议 | `tools_class.py` (`BaseTool`, `ToolOutput`) | 工具输入 Schema 与注册规范 |
| 配置 | `config.py` (`CloudraConfig`) | API Key、模型、路径、YOLO 模式等 |
| CLI/API | `cli.py` / `api.py` | 命令行入口与 FastAPI 服务 |
| YOLO 守卫 | `yolo_guard.py` (`YoloGuard`) | 自动审批危险操作的独立 LLM Agent |

数据流：`cli.py` 捕获输入 → 实例化 `Coordinator` → 进入 `reAct` 循环 → `Executor` 调用 `tools/` 下工具 → `SessionManager` 持久化 → 输出结果。

---

## 3. 安全与审批

每个工具声明位标志权限：`READ`、`WRITE`、`SCRIPT`、`DESTRUCTIVE`、`MANAGE`。

- `READ`：安全读取。
- `WRITE`：写文件/报告。
- `SCRIPT`：运行外部脚本（中危）。
- `DESTRUCTIVE`：删除、改系统设置（高危）。
- `MANAGE`：管理子 Agent 或审批流。

默认模式下，危险操作会挂起并写入 `approvals` 表，等待人工在 CLI/API 中批准。`--yolo` 模式启用 `YoloGuard`，由独立 LLM 自动判断操作合理性；请在可信环境中使用。

开发新工具时，如果涉及写文件或系统操作，务必在类中正确声明权限（如 `is_write() -> bool`），不要绕过审计流。

---

## 4. Skill 系统（知识注入）

Skill 是 **“封装好的专家经验”**，以 Markdown 形式放在 `cloudra/skills/` 中，通过 `skill_class.py` 加载。

写好 Skill 的建议：

- 多写结构化 SOP，少写泛泛描述。
- 提供负面案例：如果出现 X 现象，通常意味着 Y 错误，此时应询问用户。
- 给出明确路径：数据在哪、该调哪个工具。

目前内置示例：

- `cloudra/skills/dft-calculation/SKILL.md`
- `cloudra/skills/subagent-prompting/SKILL.md`

---

## 5. 如何贡献

1. **完善 Skill 库**：在 `cloudra/skills/` 添加专业知识。
2. **扩展工具**：在 `cloudra/tools/` 继承 `BaseTool`，实现 `get_class()`。
3. **增加测试**：在 `tests/` 添加单元测试，保持现有测试通过。
4. **保持代码风格**：使用 `ruff check cloudra tests` 检查。

---

## 6. 开发命令速查

```bash
# 安装（可编辑模式）
pip install -e .

# 运行测试
pytest tests -q

# 代码风格检查
ruff check cloudra tests

# 启动 CLI
cloudra config init
cloudra run "你的任务"

# 启动 API 服务
python -m cloudra.api
```

---

## 7. 为什么不用 LangChain？

我们自研框架是为了：

- **精准控制**：科研场景需要对 Token、工具调用、审批流有完全掌控。
- **灵活扩展**：多进程隔离、异步并发、自定义安全审计更容易实现。
- **可读可维护**：核心逻辑集中在 `agent.py` 和 `reAct.py`，新成员能快速上手。

---

**代码由我们维护，智慧由你们注入。让我们一起让 AI 学会化学！**
