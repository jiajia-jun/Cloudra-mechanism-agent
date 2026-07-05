---
name: subagent-prompting
description: Provide best practices and templates for writing effective prompts for sub-agents (e.g., explorer, writer, researcher). Use when delegating tasks via SubAgentLauncher to ensure sub-agents operate correctly, avoid hallucinations, manage context, and handle errors robustly.
---

# 1. 本地工具链映射 (Toolchain Mapping)
在复杂的 Agent 架构（如 ReAct 或多智能体协作）中，主 Agent 通过 `SubAgentLauncher` 等工具派发任务给子 Agent 时，应做好状态和工具权限的物理映射：
- **剥离不必要的依赖**：子 Agent 不一定继承父 Agent 的全部工具和状态。在 prompt 中，若子 Agent 只需要计算能力，应明确限制其调用网络搜索或其他不相关工具。
- **使用绝对路径**：子 Agent 的工作目录 (CWD) 是独立的。任何需要子 Agent 读取或修改的文件，建议在指令中写明**绝对路径**（如 `/home/yyy2333/.../file.txt`），避免相对路径或模糊指代。

# 2. 限制与防幻觉护栏 (Constraints & Guardrails)
若不对子 Agent 施加约束，大模型容易“假装完成任务”并编造结果。
1. **避免指代不明**：在指令中尽量避免“处理上面那个结果”等模糊词汇，应指名道姓地重述核心实体与目标。
2. **信任但要验证 (Trust but Verify)**：不要轻信子 Agent 宣称的“文件已修改”或“已找到数据”。应在其指令中要求：完成关键步骤后，调用对应读取工具（如 `log_parser` 或文件片段读取），将结果呈现在回复中作为证明。
3. **消除日志海啸**：在 prompt 中限制子 Agent 直接提取极长文件（如 1000 行以上的 `OUTCAR` 或日志），要求其使用特定工具或脚本解析关键部分。

# 3. 科学知识库：S.C.A.R.F. 标准模板 (Scientific Knowledge Base)
向子 Agent 发送指令时，推荐对复杂任务使用以下标准结构块（S.C.A.R.F.）封装 Prompt；简单任务可适当裁剪，不必生搬硬套。

- **(S) System Role / 角色边界**：定义专业角色和行为红线。
  *(示例：你是只处理晶体对称性的解析型 Agent，避免感性推断。)*
- **(C) Context / 上下文事实**：前置传入已确认的事实，让其不必重复验证。
  *(示例：已为你确认该体系的总电子数为 120，目标文件位于 /path/to/log.out。)*
- **(A) Actionable Goal / 精确目标**：不可随意发散的原子级任务。
  *(示例：提取末尾 SCF 能量并转为 kcal/mol。)*
- **(R) Restrictions / 限制与退路**：遇到问题时的熔断机制和错误退路。
  *(示例：如果提取结果为空，返回 `[Result: Empty]`，不许编造数字充数。)*
- **(F) Format / 输出规范**：约定 JSON 或特定标签的输出格式。

# 4. Agent 工作流：并行与异步调度 (Workflow State Machine)
在决定子 Agent 是同步阻塞（Wait）还是异步后台（Async）执行时，遵循以下逻辑决策树：

**Step 1: 判定任务依赖性**
- 如果是线性工作流的强前置依赖（如检查环境是否安装配置好），建议设定为**同步阻塞**。
- 如果是大规模数据处理（如 10 个不同的对接构象独立打分）或广度文献搜索，应设为**异步后台**执行。

**Step 2: 解决异步冲突**
- 所有并行的异步子 Agent，在保存结果时应向指定路径写入带有**独立 UUID 或进程号后缀**的文件（如 `result_1234.txt`），避免多个并发 Agent 覆写同一个通用结果文件导致脏写。

# 5. 异常诊断与排障断路器 (Circuit Breakers)
子 Agent 最危险的崩溃模式是陷入工具调用的死循环。在派发任务时，可在 Prompt 中植入“退步推理（Step-back Reasoning）”：

1. **设定强制重试阈值**：在指令中明确：“如果你使用某个工具连续产生 2 次相同的 Error，应无条件放弃该工具的使用。”
2. **熔断汇报要求**：在放弃后，子 Agent 应使用 `send_message` 通知主 Agent，并附上：
   - 原始报错信息（Stderr）。
   - 最后一次尝试的方法。
   - 阻塞任务的具体环节。
