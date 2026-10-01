# Context、agent 与事件：按恢复时间段保留

## 重启前保存范围

`pre_reboot_excerpts/agents.json` 保存原 10 个 session 元数据；三份 `last-events-*.json` 每份仅 3 条事件，是有边界的片段。迁移时没有完整持久化原 v2 内存 context。后续恢复使用这些元数据和文件 HANDOFF；不能声称恢复了重启前全部旧对话。

## 重启后的持久资料

原库：`../04_databases/` 中最终 `runtime/recovery_20261001/runtime-v2.db`。

- `recovered_v2/runtime_snapshot.json`：完整 objects.snapshot，含 projects、agents、roles、runtime_defaults、session_contexts、pending_compactions、launch_groups。
- `recovered_v2/agents/<session_id>/agent.json`：保存的身份、父子关系、设置、权限、状态。
- `context.json`：当前已保存上下文完整结构；`context.md` 为可读展示，JSON 为无损依据。共有 9 份、3137 条消息。prefix_meta/压缩后消息及工具内容保留。
- `events.jsonl`：该 session 的全部已保存事件，按原 seq 排列；无 session 的事件放 `_project/`。共 20989 条，ID、run_id、seq、session_seq、created_at、type、原 data 字符串原样保留。
- `agents_index.csv/json`：11 个 agent 的状态、是否有 context、消息/事件数。

## 状态与覆盖限制

当前 context 不是“全历史 transcript”；压缩与注入可能改变消息覆盖范围。缺少 context 的两个 agent 以 CONTEXT_NOT_PRESENT.md 明示；不要从事件猜造缺失对话。

legacy `tasks/database.db` 的 session 表仍保存 running 状态；最终 v2 也有一个旧 owner 记录仍 running。这是保存时的状态字段，不表示机器仍在计算。实际 compute.db 无活跃作业、进程已结束、平台已关机；`legacy_session_states.json` 保留差异，不修改原库来抹平。

当前库、内嵌历史 backup/runtime-v2.db、迁移旧库独立存放；不会把跨库 seq 混为一条连续历史。event created_at 按源字符串保留；本轮报告时间使用 SGT(UTC+8)。

[按 agent 和角色查找](AGENTS.md)。完整设置、父子关系、prefix_meta、权限、运行对象仍见各 agent.json 与 runtime_snapshot.json。
