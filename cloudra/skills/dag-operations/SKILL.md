---
name: dag-operations
description: How to use dag_graph in dag_record/dag_guided sessions — design the mechanism (mutate), bind evidence to delivery nodes (bind_evidence), report status, and what to do when a call is rejected. Use when composing dag_graph calls.
---

# dag_graph 意图手册

你在 DAG 会话里只需要四个意图：**建骨架、设计机理、挂载证据、（可选）回报状态**。
版本号、证据 id、process 图内部记录都由系统管理，不需要你关心。

- `init_from_template`：开工第一步，双图为空时播种机理研究骨架。
- `mutate`：设计机理的唯一入口（见下）。
- `bind_evidence`：把一次成功计算的结果挂到机理图元素（见下）。
- `update_node`（mutate 的一种 op）：只用于给你自己的节点补充状态说明。
- `delivery_report` / `view`：交付自查与看图。

## 设计机理：mutate

每个 operation 是一条以 `op` 区分的具名命令，参数是 schema 里的显式字段（写错时
报错会带出正确形状）。一个批次按顺序应用、整体校验、原子生效；边可以引用同批次
更早创建的节点。被拒绝时错误信息会附正确格式与下一步，按提示修正后直接重发同批
operations 即可。

### add_node

`{"op": "add_node", "graph": "delivery", "node": {...}}`：`node` 是完整节点对象，
字段见 schema——`node_id`/`node_type`/`label` 必填，约定属性（`role`、`smiles`、
`evidence_level` 等）都是具名字段，未列出的自定义属性放 `metadata`。

- delivery 约定：`node_type="occurrence"`，
  `role="reactant"|"intermediate"|"product"`，`evidence_level="proposed"`。

### add_edge

`{"op": "add_edge", "graph": "delivery", "edge": {...}}`：`edge` 是完整边对象
（`edge_id`/`source_node_id`/`target_node_id`/`edge_type` 必填，`label` 可选）；
两个端点必须已存在（或在本批次更早创建）。
delivery 约定：`edge_type="elementary_step"`，`evidence_level="proposed"`。

### remove_edge

`{"op": "remove_edge", "graph": ..., "edge_id": ...}`。两张图都放开，但
**批次必须带 rationale**（删除留在变更日志供审计）。
process 图的删边由 Supervisor 复核后执行——用 rationale 说服它。

### update_node / update_edge

`{"op": "update_node", "graph": ..., "node_id"|"edge_id": ..., "changes": {...}}`，
`changes` 的键是要改的字段名（`label`、`status`、`reason`、`evidence_level` 等）。
模型只能把 `evidence_level` 设为 `proposed`/`rejected`/`inconclusive`——
更高级别由 harness 从挂载的证据确定性派生。

## 挂载证据：bind_evidence

把"计划存在之前就已产出"或刚完成的计算结果认领为机理图元素的证据：

```json
{"action": "bind_evidence",
 "tool_call_id": "<你那次工具调用的 id，或 observed_ 节点 id>",
 "bind_target": "<delivery 节点或边的 id>",
 "evidence_role": "<证据角色>"}
```

harness 自动解析那次调用登记的证据、校验计算确实成功、重跑确定性派生升级
`evidence_level`，并唤醒 Supervisor 复核（它可否决，否决会以事件通知你）。
`evidence_role` 词表：

- `intermediate_optimization`（中间体优化，0 虚频→structure_supported）
- `ts_optimization_frequency`（TS 优化+频率，恰好 1 虚频→saddle_supported）
- `short_irc`
- `endpoint_a_optimization` / `endpoint_b_optimization`
- `endpoint_direction_check`（ts_guess strict）
- `endpoint_identity_match`（reaction_mapping）
- `thermochemistry`（thermo_analysis）

## 回报状态（可选兜底）

节点成败与证据回流由 harness 自动完成。需要补充说明时，对 `assignee`
等于你 agent id 的 process 节点用 `update_node` 写 `status`/`reason`/`blocked_reason`/
`annotations`。写别人的节点或结构性操作会被拒——错误消息会告诉你节点当前
assignee 与建议做法。

## 被拒怎么办

所有拒绝都是可执行的：错误消息里带正确格式、当前状态与下一步。按提示修正后
直接重发即可，不需要重新查版本号或 id。
