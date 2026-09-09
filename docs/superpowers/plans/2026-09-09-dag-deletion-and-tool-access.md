# DAG 删除权限与工具接入实施计划

> **For agentic workers:** 使用 superpowers:executing-plans 逐项执行；步骤用复选框跟踪。本文件是待执行计划，本次不修改业务代码、不提交或推送。

**Goal:** 让研究 agent 能有理由地删除交付图中的边和节点，并真正调用已有的送审、阶段裁决、证据查看工具，解决 issue #28 暴露的工具断链。

**Architecture:** 所有图删除经过现有 DagEngine 事务、版本检查和变更日志。工具注册以 TOOL_REGISTRY 为唯一事实源，通过 capabilities 和 runtime tool catalog 投影到角色、运行模式和两种调用协议；不新增旁路工具清单。删除同步收敛相关审查待办，保留历史证据。

**Tech Stack:** Python、Pydantic、SQLite、pytest、runtime_v2；JS 协议验收使用现有 Node/QuickJS 宿主。

**Spec:** 用户本轮要求“给 agent 删边删节点的权利，还有那些工具也要接上”；具体行为约定见下文。本计划不决定 TS 的科学表示或修改验收阈值。

## 行为约定与范围

1. Coordinator 和普通研究子 agent 在 dag_record / dag_guided 下，可删除自己所在项目交付图的节点、边；不限制只能删除自己创建的元素。仍服从既有显式权限限制和项目隔离。
2. Supervisor 保留审查职责，不顺带获得直接删图权限。standard 模式不暴露 DAG 工具。
3. 删除必须附非空理由，不增加逐次用户批准。允许删除已有证据或 required 的元素，与现有删边规则一致；删除是修改交付图，不等于把该元素审为 supported。
4. 节点还有入边或出边时，拒绝删除并返回关联边 ID/名称，agent 先明确删边再删节点。不提供隐式级联删除；引擎允许在同一原子批次内先删相关边再删节点。
5. 删除后当前图不再展示该元素；原始日志、文件证据快照、历史裁决和图变更日志继续保留。当前图绑定表可清理孤儿关联。
6. 删除目标对应的待审项必须退出待办；晚到的裁决不能复活已删元素，也不能误绑定到同名新元素。通知遵守 durable 写入及唯一 flush 出口。
7. 交付完成度按修改后的图重新计算。不得直接设置 complete，不得借本次改动改变阶段判据或允许模型降低全局 coverage contract；若现有契约独立要求某个目标，删除不等于撤销该要求。
8. 本次不处理 issue 附带的 ORCA 解析、热化学、内存校验及草稿重复名称问题，不通过禁止 TS 节点来替代删除能力。

### 为什么选这个方案

- 采用：显式删边、删孤立节点。沿用已有权限和事务模型，删除范围容易理解。
- 不采用自动连带删除：一个节点可能连着多条研究分支，隐式扩大操作范围。
- 不采用只增加节点级 not_applicable：那不能满足用户明确提出的删图需求，也容易盖过阶段缺口。

## 当前代码事实与工作区基线

- `cloudra/tools/Plantool/dag_tools/dag_remove_edge.py` 已存在；DagEngine 支持 RemoveEdge，要求批次 rationale。
- `cloudra/dag/models.py` 尚无 RemoveNode；引擎尚无对应分支。
- `dag_review_call` 已支持 skip/not_applicable；`cloudra/dag/completion.py` 已认可带理由的阶段处置。
- 本地 `cloudra/tools/registry.py` 有既存未提交修改：补入 dag_bind_evidence、dag_review_call、dag_review_evidence、dag_view_evidence、dag_set_coverage_contract、dag_message_supervisor。`tests/test_dag_tools.py` 也已有修改。执行时先核对这些差异，不覆盖、不重复添加，不声称是本次新写。
- `dag_set_coverage_contract` 是加强契约入口，不是 agent 自助降低标准的入口。
- 当前目录存在其他未跟踪科研产物；不改动、不删除。

## 全局约束

- 遵守根目录 AGENTS.md；不引入依赖、不加兼容 shim、不进行无关重构。
- 每项行为改动先写能测红的测试，再实施修复。既有未提交修复已使测试通过时，在隔离测试副本恢复提交版注册表验证红灯，不回滚用户工作区。
- async 路径中的 SQLite 操作使用 asyncio.to_thread 或已有异步入口。
- 图持久化走 DagEngine；runtime 状态变化走事件/命令路径，不直接改 agent 内存状态。
- 删除图元素不得终止计算、删除计算作业或修改 scheduler/guard 生命周期。
- 不自动提交、推送、发布 issue 评论；本计划没有新增科学标准。

## Task 1：补齐工具注册与可见性测试

**修改：** `cloudra/tools/registry.py`；必要时修正 `cloudra/tools/capabilities.py`、`cloudra/runtime_v2/tool_catalog.py` 的现有投影逻辑。

**测试：** `tests/test_dag_tools.py`、`tests/test_runtime_v2_tool_catalog.py`、`tests/test_runtime_v2_supervisor_tools.py`、`tests/test_dag_tool_budget.py`。

**接口约定：** 保留六个现有工具的名称和输入类型，不复制实现。dag_bind_evidence / dag_message_supervisor 给研究侧；dag_review_call / dag_review_evidence / dag_set_coverage_contract 给 guided 督导；dag_view_evidence 保留工具原有研究侧可用性并给督导 evidence_read 权限。

- [ ] 添加注册回归测试，逐个断言上述工具能被实际加载，且 schema 来自真实工具类；删除把仍在使用的新审查入口当成“已删除工具”的错误断言。
- [ ] 添加角色 × 模式 × traditional/javascript 的可见性与准入测试。standard 隐藏全部 DAG 工具；dag_record 隐藏督导裁决；guided 督导可查看证据和裁决，但不可删图。
- [ ] 对照提交版确认缺失注册测试会失败；保留并完善工作区已有注册修改。
- [ ] 验证 JS declarations 中实际出现相应函数，且真实 InvocationService 准入不误拦截；不能仅断言名称在列表里。
- [ ] 运行：`uv run pytest -q tests/test_dag_tools.py tests/test_runtime_v2_tool_catalog.py tests/test_runtime_v2_supervisor_tools.py tests/test_dag_tool_budget.py`。

## Task 2：实现事务化删节点

**修改：** `cloudra/dag/models.py`、`cloudra/dag/engine.py`。

**测试：** `tests/test_dag_engine.py`、`tests/test_dag_evidence_bindings.py`。

**新增接口：** 将下列类型纳入 GraphOperation 判别联合；不新增 delete_node 同义命令。

```python
class RemoveNode(_OperationBase):
    op: Literal["remove_node"]
    graph: GraphKind
    node_id: str
```

- [ ] 按现有 `_batch` / `_op` 测试辅助函数新增 remove_node 分支，先写以下红灯案例：孤立节点可删；空理由拒绝；目标不存在拒绝；有入边或出边拒绝；supervisor 拒绝；旧 revision 拒绝。
- [ ] 节点删除校验放在引擎内部，不能只放在工具。关联边存在返回 `node_has_edges` 和关联边标识；找不到节点返回 `missing_target`。
- [ ] 扩展现有 rationale 检查至 RemoveNode；删除成功移除 state.nodes 与 node_created 对应项，沿用 `_write_graph`、journal 和 revision 更新。
- [ ] 测试批次先删边再删节点成功；批次任一步失败时，图、绑定、revision 和审查变化全部回滚。
- [ ] 测试节点有证据时仍可删：当前绑定清理，原始证据和历史 journal 保留；重建快照/重放不恢复已删节点。
- [ ] 运行：`uv run pytest -q tests/test_dag_engine.py tests/test_dag_evidence_bindings.py`。

## Task 3：给研究 agent 暴露删节点与删边能力

**新增：** `cloudra/tools/Plantool/dag_tools/dag_remove_node.py`。

**修改：** `cloudra/tools/Plantool/dag_tools/dag_remove_edge.py`、`cloudra/tools/registry.py`；如需共享唯一解析逻辑，放入现有 `_common.py`。

**测试：** `tests/test_dag_tools.py`、`tests/test_runtime_v2_tool_catalog.py`、`tests/test_runtime_v2_supervisor_tools.py`。

**输入：** 与现有删边保持一致，`DagRemoveNodeInput(name: str, reason: str)`；name 可为名称或 ID，优先精确 ID，否则匹配名称。字符串 trim 后不能为空。

```python
RemoveNode(op="remove_node", graph=GraphKind.DELIVERY, node_id=node.node_id)
```

- [ ] 先测试普通研究 agent 和 Coordinator 都能在 record/guided 删除；standard、督导以及既有权限不允许的调用被拒绝。
- [ ] 使用 DagToolBase 的 `_prepare` / `_apply` 和 `asyncio.to_thread(ctx.engine.snapshot)`，不直接操作数据库。注册 `dag_remove_node`，不授予 supervisor_access。
- [ ] 修正删边工具只写“Coordinator”的说明，使其与实际研究侧权限一致；验证工具可见性和真实执行权限同时成立。
- [ ] 测试 ID/名称解析、重名歧义防护、空白理由、跨项目目标、重复删除、有连线时返回可操作错误信息。两个删除工具使用一致解析规则。
- [ ] 成功回执包含删除目标、结果 revision；模型收到的说明及错误文本全部英文。
- [ ] 运行：`uv run pytest -q tests/test_dag_tools.py tests/test_runtime_v2_tool_catalog.py tests/test_runtime_v2_supervisor_tools.py`。

## Task 4：删除与审查待办、通知一起收敛

**修改：** `cloudra/dag/engine.py`、`cloudra/dag/store.py`、`cloudra/dag/review_context.py`、`cloudra/dag/evidence_inbox.py`、`cloudra/dag/review_requests.py`；仅在通知接入确有缺口时修改 `cloudra/runtime_v2/supervision.py`。

**测试：** `tests/test_dag_review_call.py`、`tests/test_dag_review_requests.py`、`tests/test_dag_supervisor_feedback.py`。

**接口约定：** 复用 CallReview 的 ignored 终态和结构化请求的 superseded 终态；删除理由区分“目标已删除”和科学驳回。审查退出待办、通知落库与图删除同一事务，投递仍走 flush_review_notifications。

- [ ] 先写红灯场景：删掉有 pending CallReview 的节点/边，待办不再出现；定向到被删目标的 queued 请求退出待办；active review 不能继续提交过期裁决。
- [ ] 在图删除事务内收敛这些待办，保留原始 claim、证据 ID、历史已完成裁决；记录目标删除原因，并通过现有通知表告知提交者。不要删除审查历史行。
- [ ] 审查有效性检查必须使用目标 ID 和现有版本/指纹约束；同名新建节点使用新 ID，不继承旧裁决。删除后重新提交到旧 ID 明确失败。
- [ ] 测试裁决与删除并发：先裁决则历史保留后正常删图；先删图则后续裁决失败，不能重新创建节点或绑定。
- [ ] 测试多次 reconcile / flush 不重复通知，failed/cancelled 收件人 parked 不唤醒；删除事务失败不产生“已删除”通知。
- [ ] 运行：`uv run pytest -q tests/test_dag_review_call.py tests/test_dag_review_requests.py tests/test_dag_supervisor_feedback.py tests/test_runtime_v2_supervisor_tools.py`。

## Task 5：覆盖 issue #28 的真实工具链并更新说明

**测试：** `tests/test_dag_completion.py`、`tests/test_dag_tools.py`、`tests/test_runtime_v2_completion_gate.py`、`tests/test_runtime_v2_js_protocol.py`。

**文档：** 根目录 `AGENTS.md`；在 `cloudra/prompts/` 中定位实际 Coordinator/Supervisor 的 DAG 使用说明后更新对应段落。

- [ ] 构造确定性的交付图 fixture：保留研究目标及其他必需阶段，额外节点缺 geometry。验证初始 incomplete；经实际删边/删节点工具移除误建元素后，该元素不再制造缺口，其他缺口仍阻止完成。
- [ ] 通过显式送审 → dag_view_evidence → dag_review_call(not_applicable, reason) → dag_delivery_report，验证现有阶段处置链真实可调用且满足已有完成规则；不使用本次新定的化学判据。
- [ ] 验证只更新节点 status 不会盖过 pending 阶段；dag_set_coverage_contract 接上后仍不能让 agent 降低契约。
- [ ] 为 JS 协议增加真实 Node/QuickJS 路径用例，调用新删节点工具以及阶段审查入口；使用假 LLM 驱动，无需真实 key，不接受全部跳过。
- [ ] 更新 AGENTS.md 模块地图与删除约定；prompt 写明如何先删边后删节点、理由要求、历史保留、阶段 skip/not_applicable 的正确入口。不得宣称 TS 必须是哪一种图元素。
- [ ] 对所有改动 Python 文件执行 `uv run python -m compileall -q <改动文件>`。
- [ ] 最终执行 `uv run pytest -q tests/`、`uv run ruff check cloudra tests`、`npm --prefix cloudra/runtime_v2/js_host test`。若缺 QuickJS 依赖，按 AGENTS.md 指定 npm ci 命令手动安装后验收。
- [ ] 核对 diff 仅覆盖计划范围及用户已有修改，报告测试结果和既存失败；不自动提交或推送。

## 验收结果应能用这几句话描述

- agent 建错图后，能自己写明理由、删掉边和节点，不再只能不停向督导求助。
- 节点有连线时系统明确指出该先处理哪些边，不会悄悄连带删除。
- 已有送审、证据查看和阶段裁决工具真正可见、可执行。
- 删除不会留下永远待审的事项，不会抹掉计算证据，也不会影响计算作业。
- 完成报告反映修改后的图，尚未解决的其他缺口仍然保留。
