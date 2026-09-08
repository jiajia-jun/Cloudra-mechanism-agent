# DAG 声明式交互与证据复核重构实施计划

> 执行者：按任务使用 superpowers:executing-plans；每项先写能测红的测试，再实现并验证。本文仅为计划，不授权提交、推送或清理用户数据。

**Goal:** 将 DAG 模型交互收敛到体系名称、步骤关系、自由文字与证据文件，删除无意义的类型和阶段负担，后台承担身份、证据固定、校验和裁决路由。

**Architecture:** 单张无环交付图保存整个络合物体系的状态及其转化步骤。模型提出声明式图、按名称提交文件；harness 固定证据并复用既有 TS 合法性校验，Supervisor 在后台绑定的待审上下文中裁决。状态、证据和通知持久化分别沿用图事务、证据存储与运行时事件通道。

**Tech Stack:** Python >=3.11、Pydantic、SQLite、asyncio、React/TypeScript；不增加依赖。

**Spec:** 本文第 1–5 节是根据本次用户评审确认的设计依据，取代外部 `implementation_plan.md` V2；外部文件保留不改。仓库约束见根目录 `AGENTS.md`。

## 1. 已确认的设计及边界

1. 每个节点直接对应整个络合物体系的状态，不是孤立催化剂。催化剂再生不等于体系回到原状态；保留 DAG 无环约束，不为催化循环增加有环图。
2. 删除 occurrence 概念，内部使用 `SpeciesNode`，模型不填写 `node_type`。不建立物种实体与出现实例两层模型。
3. 删除 `role` 字段及前端消费，不再推导 reactant/intermediate/product。
4. 节点名称在项目交付图内唯一，步骤名称在同一图内另行唯一；内部 ID 自动生成。相同 SMILES 不自动合并对象。
5. 不新增改名流程。现有更新入口不得绕过唯一性约束；不设计别名、旧名称回退或兼容解析。
6. 模型不传内部 ID、tool_call_id、session_id、revision、basis_fingerprint、graph、stage 数组。后台一致性约束不等于模型输入字段。
7. 研究声明使用宽松文字与落盘证据，不通过 DAG schema 强绑 ClaimSpec、逐项 findings 或事实清单。
8. 步骤绑定后复用现有 TS 合法性工具；不新增科学阈值，不另外强制 endpoint_a/b、direction、identity、IRC 连通性等独立验收门禁。IRC 文件可作为补充材料。
9. 谁提交送审，裁决就回给谁。复用现有 durable 通知闭环，failed/cancelled 收件人只投信箱、不自动复活。
10. 无兼容层：删除旧 schema、读取映射、兼容属性、旧工具别名及死代码；不以“标记废弃”收尾。不得自动删除或重置用户现有数据库。

## 2. 模型交互契约

以下示例是线缆形状，文字内容不代表新增科学验收规则。内部 DTO 可更丰富，但不得投影为模型必填参数。

### 2.1 提案与局部维护

```json
{
  "rationale": "拟考察的体系转化路径及理由",
  "species": [
    {"name": "初始络合物体系", "smiles": "..."},
    {"name": "产物络合物体系", "smiles": "..."}
  ],
  "steps": [
    {"name": "关键转化", "from": "初始络合物体系", "to": "产物络合物体系"}
  ]
}
```

- `dag_propose_mechanism` 接收以上结构；后台解析名称引用、生成 ID、验证唯一性/无环性并原子保存草稿。guided 接受草稿前不开算；record 自动接受；standard 不读写图。
- `dag_add_species` 接收 `name, smiles`；`dag_add_step` 接收 `name, from, to`；`dag_remove_step` 接收 `step, rationale`。
- 名称去首尾空白后按精确字符串比较，不做模糊匹配。空名称拒绝；节点与边分别判重。草稿接受与增量写入均在事务内重新判重，不仅在工具层预查。
- 不要求模型手写标准阶段。删除固定 opt/freq/sp 和十阶段数组，不在后台重新偷偷注入等价的强制流程。
- `barrierless` 不作为自动通行布尔值。无 TS 的步骤由文字与证据说明，经明确的有理由处置处理；不把所有步骤默认为获准豁免。

### 2.2 文件送审

```json
{"step":"关键转化","ts_log":"runs/ts.out","irc_log":"runs/irc.out","summary":"计算结果与需要复核的结论"}
```

```json
{"species":"初始络合物体系","log_path":"runs/complex.out","summary":"结构证据说明"}
```

- 工具为 `dag_submit_step_evidence` 与 `dag_submit_species_evidence`。
- `summary` 为自由文字；`irc_log` 为可选补充材料，不因未提供而新增拒绝门禁。步骤说明可附证据路径列表承载非 TS 材料；没有 TS 文件不自动变为 supported，而进入带理由的复核/处置路径。
- 文件路径按项目工作区解析，不能落到进程 cwd。采用现有受限文件读取边界。
- 固定文件字节、内容摘要、来源路径与解析结果；后续文件覆盖不得改变已送审证据。依赖 sidecar 的解析必须一并固定相关文件，不能复核时重新读取可变源。
- 缺文件、未完工或解析失败返回明确原因，保留审计材料，不提升为 supported。文件 I/O、解析和同步 SQLite 卸载线程。
- 提交者身份从运行时上下文取得；显式调用送审工具才入复核队列，普通工具完成不自动送审。
- 同一提交者、目标、内容与说明的重复待审提交幂等；新证据建立新版本，旧记录保留。后台用证据版本辨别过期裁决。

### 2.3 后台绑定的审查上下文

```json
{"verdict":"agree","reason":"对当前待审事项的裁决理由"}
```

`dag_review_step` 与 `dag_review_species` 面向当前待审事项；`dag_accept_mechanism` 面向当前待审草稿，输入只需 accept/reject 与理由。

- 每个 Supervisor 当前审查上下文只允许一个明确的活动事项，包含内部提交记录、提交者、目标和证据版本。复核材料给出人类可读的名称、说明、证据及校验结果。
- 在调用请求产生时捕获上下文快照，executor 不得临时查“最新一条”。禁止在同一个模型工具调用批次中切换活动事项。
- 裁决与活动事项不匹配、上下文缺失、对象已删除或依据过期时拒绝，不猜选；harness 刷新材料后再审。内部版本检查及身份均不要求 LLM 输入。
- 活动事项与恢复行为须持久化：重启不得把旧回复套到另一个待审项。保持单 Supervisor 调用串行与事务校验。
- verdict 可为 agree/disagree/needs_evidence/skip/not_applicable；后两者必须有理由。disagree 和 needs_evidence 保持开放缺口。
- agree 只认可该项，不命令子 Agent 无条件退出；子 Agent 根据剩余任务与运行结束门禁决定是否完成。

## 3. 后台权威与完成度

- 删除强 schema 声明协议及 `evaluate_claim` 对 DAG 完工的强绑。已有反证、失败结果和历史裁决作为证据材料进入审查，不因后来成功记录而丢弃。
- 复用 TS 工具现有算法与判据；内部结构化校验结果允许持久化，不要求模型重述为结构化事实。已有 `_passes_saddle_check` 只是当前入口，实施时追到实际 deriver/工具实现，不能把单字段判断误当作完整工具校验。
- 图元素保存单一权威审查状态及绑定证据；删除旧阶段序列、7 个派生布尔位与重复 evidence_level 状态来源。投影字段从权威状态产生。
- 物种证据由现有解析能力提供材料，guided 由 Supervisor 审查；不新增固定频率/单点验收要求。
- 单一完成度函数检查：有效非空交付、未解决必需元素、待审项、否决与补证项，以及带理由的 skip/not_applicable。TS 校验失败不能被 agree 提升为正常 supported；明确处置单独展示，不伪称验证通过。
- 不额外引入强制热化学门槛或结构化能垒声明；研究结论的具体要求由自由文字、证据和 Supervisor 审查承载。
- record 没有 Supervisor，复用同一证据摄取与确定性校验并记录结果；不能让缺失校验材料在 record 自动变为 supported。guided 等待裁决。standard 无 DAG 副作用。
- `dag_delivery_report`、`dag_view`、UI 和隐式/显式运行结束门禁使用同一评估结果，不只修改 stop 工具。

## 4. 通知与运行时约束

复用 `cloudra/runtime_v2/supervision.py::flush_review_notifications`：裁决状态和通知行同事务写入，先投递并持久化事件，再标记通知已发送；恢复 reconcile 补投。

- 收件人固定为送审时提交者，不路由到当前步骤负责人或 Coordinator。
- failed/cancelled 保持 park-don’t-wake；其余状态沿用既有 wake 状态机，不自建 task 或直接改 agent 状态。
- 崩溃重投不得丢通知；保留当前投递幂等/重复可容忍语义，不虚称信箱消息绝对恰好一次。
- Coordinator 通过图查看进度，正常子 Agent 完成汇报保持现有机制。
- 不触碰 scheduler/guard/QM 生命周期；解析证据不重新发起计算。

## 5. 模型与前端视图

模型视图只返回名称、关系、审查状态、简短缺口与可读证据摘要。前端可通过专用序列化保留内部稳定 ID 作为 React/连线键，不把 ID 回流为模型参数。

```json
{
  "species":[{"name":"初始络合物体系","status":"supported"}],
  "steps":[{"name":"关键转化","from":"初始络合物体系","to":"产物络合物体系","status":"needs_evidence"}],
  "unresolved_gaps":[{"target":"关键转化","reason":"尚待补充可通过现有 TS 校验的证据"}]
}
```

不输出 occurrence、role、AST、阶段数组或 7 个布尔位。不把 skipped 显示成科学验证通过。待审队列可以展示多个摘要，但可裁决上下文必须唯一。

## 6. 实施任务

### Task 1：图模型与声明式提案

**修改：** `cloudra/dag/models.py`、`engine.py`、`store.py`、`drafts.py`、`cloudra/tools/Plantool/dag_tools/proposal_inputs.py`、`dag_propose_mechanism.py`、`dag_add_species.py`、`dag_add_step.py`、`dag_remove_edge.py`、`dag_update_delivery_element.py`。

**接口：** 输入第 2.1 节 DTO；输出内部原子图操作与草稿记录。保留内部事务操作，不向线缆投影。

- [ ] 在 `tests/test_dag_propose.py`、`test_dag_engine.py`、`test_dag_store.py` 写失败测试：无 ID/role/type 提案成功；同批和并发同名写入拒绝；未知端点/自环/环拒绝；同 SMILES 不合并；删除缺理由拒绝；批次失败零部分写入。
- [ ] 运行上述测试确认新契约测红。
- [ ] 实现 `SpeciesNode`、唯一名称、自动 ID 与声明式装配；删除 occurrence/role 的写读结构和兼容映射。草稿接受时重新校验最新图。
- [ ] 重跑上述测试，确认图的无环与事务边界保持。

### Task 2：文件证据摄取与现有校验复用

**新增：** `cloudra/dag/evidence_ingest.py`（文件固定与解析调度）；`cloudra/tools/Plantool/dag_tools/dag_submit_step_evidence.py`、`dag_submit_species_evidence.py`。

**修改：** `cloudra/dag/evidence_inbox.py`、`store.py`、`fact_adapters.py`、`cloudra/persistence/database.py`；复用 `cloudra/tools/Chemtool/log_parser.py`、`ts_guess.py` 与 `cloudra/tools/core/` 既有解析/校验能力。

**接口：** 模型输入名称、路径、文字；内部输出固定证据引用、校验结果、目标 ID 与提交者身份，全部由 harness 填充。

- [ ] 在 `tests/test_dag_evidence_bindings.py`、`test_dag_tools.py` 写失败测试：路径送审不需调用 ID；覆盖原文件不改变旧证据；不同工作区同名路径不串用；缺文件/失败日志不支持；TS 合法/非法结果与现有工具一致；缺 IRC 不新增独立门禁；重复提交幂等。
- [ ] 运行测试确认测红；以现有 TS fixture 和工具结果作为一致性基准，不改科学阈值。
- [ ] 实现摄取并固化解析依赖，全部同步操作卸载线程；显式送审才写队列。移除 `dag_bind_evidence` 旧线缆工具，不保留别名。
- [ ] 重跑测试及 `tests/test_no_sync_on_loop.py`。

### Task 3：内部复核上下文与定向裁决

**新增：** `cloudra/dag/review_context.py`（持久活动事项与版本检查）；`cloudra/tools/Plantool/dag_tools/dag_review_step.py`、`dag_review_species.py`。

**修改：** `cloudra/dag/review_requests.py`、`supervision.py`、`evidence_inbox.py`、`drafts.py`、`store.py`、`cloudra/runtime_v2/supervision.py`、`invocation_context.py`、`policies/dag.py`、`cloudra/tools/Plantool/dag_tools/dag_accept_mechanism.py`。

**接口：** Supervisor 模型只交 verdict/reason；调用上下文携带被冻结的内部审查目标。内部事务返回状态变化和一条 durable 通知。

- [ ] 在 `tests/test_dag_review_requests.py`、`test_dag_review_call.py`、`test_runtime_v2_supervision_verdicts.py` 写失败测试：两个事项不串审；多草稿不猜选；新证据使旧裁决失效；重复裁决不重复落态；原提交者收到通知；取消/失败者不复活；崩溃窗口恢复补投；无上下文裁决拒绝。
- [ ] 确认测试测红后实现活动事项持久化、调用捕获与串行审查；复用通知 flush，不新增第二套通道。
- [ ] 删除旧逐阶段裁决工具与 ClaimSpec/findings 强绑协议；保留证据历史与后台依据版本验证。
- [ ] 重跑以上测试和 `tests/test_runtime_v2_recovery.py`、`test_runtime_v2_cancel_cascade.py`。

### Task 4：单一状态与完成度收敛

**修改：** `cloudra/dag/models.py`、`completion.py`、`requirements.py`、`stop_audit.py`、`store.py`、`cloudra/runtime_v2/policies/dag.py`、`agent_runner.py` 相关接入点。

**接口：** 单一元素状态及证据产生统一报告；不依赖旧阶段或布尔位。runner 仍经既有 `_evaluate_completion_gate`。

- [ ] 在 `tests/test_dag_completion.py`、`test_dag_exit_approval.py`、`test_runtime_v2_completion_gate.py` 写失败测试：待审/否决/补证保持缺口；合法 TS 获批后关闭相应缺口；无理由处置拒绝；有理由处置单独显示；空图不完成；显式 stop 与纯文本退出一致。
- [ ] 确认测红后移除重复评估与旧强 schema 声明协议，删除阶段序列/7 个布尔位的存储与派生分支；仅无调用者的模块才整文件删除。
- [ ] 验证 `standard/dag_record/dag_guided` 分别无副作用、确定性记录、等待审查；保持现有 run-end 有界重试和失败语义。
- [ ] 重跑以上测试及 `tests/test_runtime_v2_orchestration_mode.py`。

### Task 5：工具投影、提示词、前端与旧结构清理

**修改：** `cloudra/tools/registry.py`、`capabilities.py`、`runtime_v2/tool_catalog.py`、`dag/supervisor_tools.py`、`dag/substantive_gate.py`、`tools/Plantool/dag_tools/__init__.py`、`dag_view.py`、`dag_delivery_report.py`、`frontend/src/DagPanel.tsx`、`types.ts`、`api.ts`、`dagStatus.ts`；更新相关 `cloudra/prompts/*.md` 与根 `AGENTS.md`。

- [ ] 在 `tests/test_runtime_v2_tool_catalog.py`、`test_public_tool_contracts.py`、`test_dag_tools.py` 和 `frontend/src/dagStatus.test.ts` 写失败测试：新工具可见性按模式/角色正确；模型 schema 无内部字段；旧工具不存在；前端无 role/occurrence 消费；处置与验证通过显示不同。
- [ ] 确认测红后更新注册与 capability 声明，通过已有唯一工具投影口生成 schema，不创建工具名平行集合。
- [ ] 更新模型提示：按名称与文件交工、收到补证理由继续工作、认可一个步骤不等于整个任务完成。
- [ ] 删除 process 旧模型、AddLink、读取兼容属性及相应 legacy-only 测试；更新回放测试为新结构，保留新结构恢复等价性测试。
- [ ] 更新 AGENTS.md：节点语义、无角色/无 occurrence、唯一名称、文件证据、后台审查上下文和新测试命令；不把本文方案在实现前描述为当前事实。
- [ ] 运行前端测试和构建，再运行最终验收。

## 7. 最终验收

实施时每项保留先红后绿的记录；不能只把旧测试断言删掉使 suite 变绿。以下命令均从项目根目录执行：

```bash
uv run python -m compileall -q cloudra/dag cloudra/runtime_v2 cloudra/tools/Plantool/dag_tools
uv run pytest -q tests/test_dag* tests/test_runtime_v2* tests/test_no_sync_on_loop.py
uv run pytest -q tests/
uv run ruff check cloudra tests
npm --prefix cloudra/runtime_v2/js_host test
npm --prefix frontend run test:timeline
npm --prefix frontend run test:attention
node --experimental-strip-types frontend/src/dagStatus.test.ts
npm --prefix frontend run build
```

若 JS 依赖未安装，按 AGENTS.md 手动安装后验收真实 Node 路径，不接受全部 skip。前端现有脚本为 test:timeline 与 test:attention；dagStatus 测试直接通过 Node 执行。

人工验收：在隔离测试项目创建完整体系状态提案；确认模型无需 ID/role/stages；子 Agent 按名称交文件；Supervisor 无内部参数完成审查；结果回原提交者；取消后迟到结果不复活；失败 TS 留缺口；旧证据文件覆盖不改变裁决材料；前端无角色和碎片阶段；纯文本退出仍被未完成项拦截。

本次重构不实现历史数据读取兼容。若现有库含旧记录，明确报告不支持该格式，不自动清库；实现阶段不得把“无兼容”解释为用户授权销毁已有项目。
