---
name: dag-operations
description: Full per-operation data shapes and conventions for the dag_graph mutate batch (add_node/add_edge/remove_edge/update_node/update_edge/attach_ref/add_link). Use when composing dag_graph mutations in dag_record or dag_guided sessions.
---

# dag_graph mutate 操作手册

每个 operation 形如 `{"op": ..., "graph": "process"|"delivery"|null, "data": {...}}`，
一个 mutate 批次按顺序应用、整体校验、原子生效；边可以引用同批次更早创建的节点。
被拒绝时错误信息会附带正确格式示例，按示例修正后带最新 `base_revisions` 重试。

## add_node

完整节点：`{"node_id", "node_type", "label", "payload"?, "refs"?}`。
自定义属性（smiles、role、status 等）一律放 `payload`；顶层未知字段会被拒绝。

- delivery 约定：`node_type="occurrence"`，
  `payload={"role": "reactant"|"intermediate"|"product", "smiles": ..., "evidence_level": "proposed"}`。
- process 排产节点约定（Supervisor 排产）：payload 携带：
  - `tool_name`：该节点排产的确切工具（如 `gaussian_log_parser`、`reaction_mapping`、`thermo_analysis`）；
  - `delivery_target_type` + `delivery_target_id`：这次调用服务的机理图元素（node 或 edge 的 id）；
  - `evidence_role`：证据角色词表——`intermediate_optimization`（中间体优化，0 虚频→structure_supported）/
    `ts_optimization_frequency`（TS 优化+频率，恰好 1 虚频→saddle_supported）/ `short_irc` /
    `endpoint_a_optimization` / `endpoint_b_optimization` / `endpoint_direction_check`（ts_guess strict）/
    `endpoint_identity_match`（reaction_mapping）/ `thermochemistry`（thermo_analysis）；
  - `assignee`：执行者的 agent id（如 `a-4`）。

  只有绑定到这种 planned 节点的工具调用才会把证据回流到 delivery DAG；
  绑定不上的调用只落为 `observed_tool_call` 记录。

## add_edge

完整边：`{"edge_id", "source_node_id", "target_node_id", "edge_type", "label"?, "payload"?, "refs"?}`；
两个端点必须已存在（或在本批次更早创建）。
delivery 约定：`edge_type="elementary_step"`，`payload={"evidence_level": "proposed"}`。

## remove_edge

`{"edge_id"}`。两张图都放开、任意端点状态可删，但**批次必须带 rationale**（删除留在变更日志供审计）。
process 图的删边由 Supervisor 执行：agent 的 remove_edge 请求会被记入日志并唤醒 Supervisor 复核——
用 rationale 说服它。delivery 图上设计者可直接删除自己的边（同样要 rationale）。

## update_node / update_edge

`{"node_id"|"edge_id", "changes": {...}}`，可变字段为 `label` 和 payload 键。
模型只能把 `evidence_level` 设为 `proposed`/`rejected`/`inconclusive`——
更高级别由 harness 从引用证据确定性派生。
process 图上，agent 还可以对 `payload.assignee` 等于自己 agent id 的节点回报
`status`/`reason`/`blocked_reason`/`annotations`。

## attach_ref

`{"target_type": "node"|"edge", "target_id": ..., "ref": {...}, "evidence_role"?}`，
其中 `ref = {"ref_type": "artifact"|"compute_job"|"tool_result"|"species", "ref_id": ..., "content_hash": ...}`。

- `ref_id` 必须从本会话的真实证据中复制（view 输出或工具结果）；凭空编造的 id 以 `invalid_reference` 拒绝。
- 把 `tool_result` 挂到 delivery 元素时带上 `evidence_role`（与排产绑定同一套 8 角色词表）：
  harness 会重跑确定性派生，让补挂的证据升级元素的 `evidence_level`——
  这是认领"计划存在之前就已产出"的证据的正规途径。

## add_link

`graph=null`，data 为 `{"link_id", "process_node_id", "delivery_element_type": "node"|"edge", "delivery_element_id"}`，
把一个 process 任务链接到它服务的 delivery 元素。
