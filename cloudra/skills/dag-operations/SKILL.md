---
name: dag-operations
description: How to use dag_graph in dag_record/dag_guided sessions — design the mechanism (mutate), bind evidence to delivery nodes (bind_evidence), report status, and what to do when a call is rejected. Use when composing dag_graph calls.
---

# dag_graph 意图手册

你在 DAG 会话里常用意图：**建骨架、设计机理、挂载证据、向 Supervisor 留言、（可选）回报状态**。
版本号、证据 id、process 图内部记录都由系统管理，不需要你关心。

- `init_from_template`：开工第一步，双图为空时播种机理研究骨架。
- `mutate`：设计机理的唯一入口（见下）。
- `bind_evidence`：把一次成功计算的结果挂到机理图元素（见下）。
- `message_supervisor`：Coordinator 向 Supervisor 留言（催排产、说明卡点、请求复核），不改图。子 Agent 不可用。
- `update_node`（mutate 的一种 op）：改已有节点的**允许字段**（见下）；process 上主要给
  自己的 assignee 节点补状态说明。
- `delivery_report` / `view`：交付自查与看图。

## dag_guided 工作流

按这个顺序推进（harness 会硬拦越级操作，错误消息会指明下一步）：

1. **用户输入任务** → Coordinator 被唤醒。
2. **初步调研**：读 skill、搜文献/领域共识；需要时可派 `explorer(a-1)` /
   `researcher(a-3)`。写文件、开算、派计算类子 Agent 此时仍被拦。
3. **提交初步机理**：`mutate` 把假设写入 delivery（非模板占位），rationale
   说清计算方案。
4. **Supervisor 审核与排产**：机理变更被接受后自动唤醒 Supervisor，由它在
   process 上安排非模板计划任务（并非每次都必须新建节点；已有覆盖性排产时可只说明）。
   督导结论文本会钉进你的上下文（`[Supervisor]`）；Coordinator 需要反馈时用
   `dag_graph(action="message_supervisor", message="...")`（子 Agent 不可用）。
5. **按 process 拆解**：看默认 `view` 投影里的 **frontier**（依赖已满足且
   status 为 `proposed` 或 `ready` 的 planned 节点——不要只用
   `status_filter=ready`）。按节点 `assignee`（合法 id 如 `a-4`）派
   `small_mol` / `dft` 等子 Agent，或自行执行已排产的工具级工作。
6. **证据回流**：`log_parser` 等工具结果由 harness 自动维护图；若出现意外
   （先算后建图、绑定漏挂），用 `bind_evidence` 自行认领。
7. **交付**：`delivery_report` 确认覆盖率满足后才可 stop 交付；有缺口则继续
   补证或明确 partial / 请用户豁免。

空图时任何实质性操作都会被拦——先 `init_from_template`（或 mutate 建节点）。
模板骨架 alone 不算「机理已提交」或「Supervisor 已排产」。

## 设计机理：mutate

每个 operation 是一条以 `op` 区分的具名命令，参数是 schema 里的显式字段（写错时
报错会带出正确形状）。一个批次按顺序应用、整体校验、原子生效；边可以引用同批次
更早创建的节点。被拒绝时错误信息会附正确格式与下一步，按提示修正后直接重发同批
operations 即可。

调用形态：`dag_graph(action="mutate", rationale="...", operations=[...])`。
`operations` 必须是 **对象数组**（不要把整段 JSON 再包成字符串）。

### add_node vs update_node（易混）

| | `add_node` | `update_node` |
|---|---|---|
| 用途 | **新建**尚不存在的节点 | **改已有**节点的部分字段 |
| 载荷 | 嵌套完整 `node: {...}` | 顶层 `node_id` + 部分 `changes: {...}` |
| `role` / `smiles` / `metadata` / `assignee` / `node_type` | 创建时一次性写进 `node` | **不能**改（会报 `model update exceeds its mutable fields`） |
| 模板占位 `occ_reactants` / `occ_products` | 已存在 → 不要再 add 同 id | 只改 `label` / `annotations` / `reason` 等；物种 SMILES 用 **新** `add_node` 表达，或把 SMILES 写进 `annotations` |

**可写进 `changes` 的字段**（模型侧）：`label`、`annotations`、`reason`、`blocked_reason`、
`status`、`priority`、`evidence_level`、`required`、`supersedes`。
`evidence_level` 模型只能设 `proposed` / `rejected` / `inconclusive`（更高级别由挂证派生）。

### 示范 schema（delivery 机理一批写完）

下面是「模板占位改标签 + 新建中间体 + 两条基元步骤边」的正确形状（id 按你的机理替换）：

```json
{
  "action": "mutate",
  "rationale": "简述机理假设与计算方案（级别、每步要做的 TS/IRC/端点核对等）",
  "operations": [
    {
      "op": "update_node",
      "graph": "delivery",
      "node_id": "occ_reactants",
      "changes": {
        "label": "乙烯 + 臭氧",
        "annotations": "smiles refs: C=C ; [O-][O+]=O"
      }
    },
    {
      "op": "update_node",
      "graph": "delivery",
      "node_id": "occ_products",
      "changes": {
        "label": "Criegee 中间体 + 甲醛",
        "annotations": "smiles refs: C=[O+][O-] ; C=O"
      }
    },
    {
      "op": "add_node",
      "graph": "delivery",
      "node": {
        "node_id": "occ_poz",
        "node_type": "occurrence",
        "label": "初级臭氧化物 POZ",
        "role": "intermediate",
        "smiles": "C1COOO1",
        "evidence_level": "proposed"
      }
    },
    {
      "op": "add_edge",
      "graph": "delivery",
      "edge": {
        "edge_id": "e_step1",
        "edge_type": "elementary_step",
        "source_node_id": "occ_reactants",
        "target_node_id": "occ_poz",
        "label": "环加成 → POZ",
        "evidence_level": "proposed"
      }
    },
    {
      "op": "add_edge",
      "graph": "delivery",
      "edge": {
        "edge_id": "e_step2",
        "edge_type": "elementary_step",
        "source_node_id": "occ_poz",
        "target_node_id": "occ_products",
        "label": "裂解 → Criegee + HCHO",
        "evidence_level": "proposed"
      }
    }
  ]
}
```

### 错误形状（不要这样写）

```json
{"op": "add_node", "graph": "delivery", "node_id": "occ_poz", "label": "...", "smiles": "..."}
```
↑ 缺嵌套 `node`；字段摊在顶层会报 `Field required: node` / `graph`。

```json
{"op": "update_node", "graph": "delivery", "node_id": "occ_reactants",
 "changes": {"smiles": "C=C", "role": "reactant"}}
```
↑ `smiles`/`role` 不在可更新集合；模板节点 role 已固定，物种信息用 `label`/`annotations`，或 `add_node` 新建带 smiles 的 occurrence。

```json
{"op": "update_node", "graph": "delivery", "node": {"node_id": "occ_poz", "label": "..."}}
```
↑ `update_node` 没有 `node` 字段，要用 `node_id` + `changes`。

### add_node

`{"op": "add_node", "graph": "delivery", "node": {...}}`：`node` 是完整节点对象，
`node_id` / `node_type` / `label` 必填；约定属性（`role`、`smiles`、`evidence_level`
等）都是具名字段，未列出的自定义属性放 `metadata`（仅创建时可写）。

- delivery：`node_type="occurrence"`，
  `role="reactant"|"intermediate"|"product"`，`evidence_level="proposed"`。

### add_edge

`{"op": "add_edge", "graph": "delivery", "edge": {...}}`：`edge` 是完整边对象
（`edge_id` / `source_node_id` / `target_node_id` / `edge_type` 必填，`label` 可选）；
两个端点必须已存在（或在本批次更早创建）。
delivery：`edge_type="elementary_step"`，`evidence_level="proposed"`。

### remove_edge

`{"op": "remove_edge", "graph": ..., "edge_id": ...}`。两张图都放开，但
**批次必须带 rationale**（删除留在变更日志供审计）。
process 图的删边由 Supervisor 复核后执行——用 rationale 说服它。

### update_node / update_edge（process 回报）

process 上只更新 **`assignee` 等于你自己** 的节点，例如：

```json
{
  "op": "update_node",
  "graph": "process",
  "node_id": "p_ts_search_step1",
  "changes": {
    "status": "blocked",
    "blocked_reason": "缺合理 TS 初猜，需先柔性扫描",
    "reason": "等待扫面结果后再 Opt=TS"
  }
}
```

写别人的节点或结构性字段会被拒——错误消息会给出当前 assignee 与建议。

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
