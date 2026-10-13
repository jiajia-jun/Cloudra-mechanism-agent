# 惰性工具中断恢复实施计划

> **For agentic workers:** Use superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** 移除启动时的全局工具生命周期扫描，在中断会话重新开启时局部补齐记录。

**Architecture:** 启动仍只对恢复出的运行中 Agent 标记失败。有效命令准备重开失败会话时，在线程中读取该会话最后一个 Run 的终态和该 Run 的调用，补偿整批落盘后发布，再重新决定原命令，避免订阅者重入重复开启。只读投影显示 interrupted / unknown。

**Tech Stack:** Python、SQLite、现有 CommandBus / EventWriter、pytest。

**Spec:** `/Users/cloudrayyy/.gemini/antigravity/brain/1f00269c-1d90-4027-9eaf-9855726f1d15/spec_lazy_tool_recovery.md`

## 约束与实际调用链调整

- 不增加模型输入字段，不改科学规则，不调用计算执行器或发送进程信号。
- 正常运行、系统通知驻留、无效命令不查询恢复历史。
- 实际代码在 run.finished 后清空 current_run；FAILED 会话接受消息和重启，不会产生规范假设的 state_conflict。恢复放在有效命令的 FAILED → QUEUED 分支，不制造人为冲突。
- 本次移除全局 tool/program 生命周期扫描；其他元数据、通知和信箱恢复仍有历史查询，不宣称整个冷启动严格 O(1)。

## 实施与验证

- [x] 重构 tests/test_runtime_v2_js_recovery.py：真实中断 Run、启动无补偿、重开局部补偿、超过缓存窗口的记录、幂等及落库失败。
- [x] persistence.py 移除全局生命周期规划；events.py / persistence.py 增加 session + run 过滤及索引，完整读取一个 Run。
- [x] commands.py 在已验证的失败会话重开决定之前补入局部补偿草稿，保留现有持久化和调度顺序。
- [x] observability.py 将虚拟中断调用投影为 unknown，测试纯读且不影响新 Run。
- [x] tests/agent_scenarios.py / tests/test_agent_scenarios.py 加入宕机、恢复、新消息和真实脚本 Provider 回复的场景。
- [x] 运行 compileall、ruff、相关恢复/事件/命令/观测测试和目标场景；审查差异，保留已有 AGENTS.md 和申报材料改动。

复核补充：覆盖事件订阅者重入以及上次恢复在 FAILED 已落盘、run.finished 未落盘时退出的场景；后者只补齐内存中残留 Run 的终态，不扫描调用历史。
