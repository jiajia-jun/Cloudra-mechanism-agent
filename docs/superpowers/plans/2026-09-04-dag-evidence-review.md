# DAG Evidence and Scientific Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让研究 Agent 自主绑定与选择性送审证据，在可靠留存、科学验证和 Supervisor 退出审批的前提下，消除 DAG 的无效等待与重复计算。

**Architecture:** 保留 delivery DAG、现有 ArtifactService、AgentHub/chem-kb 和事件内核。新增少量类型化事实与审查请求；绑定允许乱序，结论按依赖集合推导。科学策略主要通过 Supervisor prompt 与 skill 表达，运行时保证异步执行、可靠通知及不可绕过的退出门禁。

**Tech Stack:** Python/Pydantic、SQLite、asyncio、pytest；React/TypeScript。

**Spec:** [架构设计与已对齐需求](../specs/2026-09-04-dag-evidence-review-design.md)。开始每个任务前读取其对应设计章节。

## Global Constraints

- Python >= 3.11；POSIX-only；前端保持现有 React/TypeScript。
- delivery 图及其 journal 继续由 DagStore/DagEngine 管理；不恢复 process graph。
- runtime_v2 的可恢复状态只通过事件和 apply_event 变更；不直接修改 core 投影。
- 工具语义只在 tools/registry.py 声明，通过 tools/capabilities.py 消费；不新增散落的工具名白名单。
- scheduler 与中央 compute.db 保持现有职责；资源调度不通过解析输入文件推断。
- 复用 ArtifactService 与现有 chem-kb/provider；不建设第二个产物仓库或知识库。
- 模型可见工具说明、错误与 prompt 用英文；设计文档用中文。
- 保留旧 journal、证据、裁决的历史可读性；不得把旧记录无验证地升级成新标准已验证证据。
- 本轮仅提交设计与计划；不运行新的化学作业、不改评分权重、不提交或覆盖无关工作区变更。

附加范围：Supervisor 首版只允许读取、解析、skill 与受限 AgentHub；不开放 Python/Bash。dag_guided 的 partial／方法受限退出必须获 Supervisor 同意。普通证据不自动逐条审查，交付前只汇总异常。

以下所有新增文件、类型、函数都是**拟实现接口**，不是当前已存在的能力。实现任务中的提交动作，在用户授权实施后的正常开发流程执行；当前只编写本计划。

---

## 执行策略与文件边界

分三组提交，避免一次替换整个系统：A 修正科学指导和工具事实；B 更换证据／审查协议；C 改善协作并验证效果。B 内部可以逐项合并代码，但必须在所有门禁到位后才启用 contract_version=2。不能先单独打开乱序，再补正确性规则。

| 单元 | 修改／新增位置 | 只负责什么 |
| --- | --- | --- |
| 原生计算语义 | tools/core/calculation_intent.py；qm_input_writer.py、ts_guess.py、引擎 frames | 输入意图、明确拒绝、结果原语；不决定科研交付。 |
| 科学契约与事实 | dag/models.py、dag/evidence_facts.py、dag/requirements.py | 任务需要的证据、可复用事实、结论依赖；不调度工具。 |
| DAG 存储与绑定 | dag/store.py、engine.py、evidence_inbox.py、persistence/database.py | 事务、索引、不可变引用、版本化绑定。 |
| 审查协议 | dag/review_requests.py、dag/supervision.py | 请求／裁决数据、入箱与交付；不新增另一套 Agent 状态。 |
| 审查执行 | runtime_v2/review_worker.py、core/supervisor.py | 单项目审查串行消费、工具执行与通知。 |
| 科学行为 | prompts/supervisor.md、skills/dft-calculation/references/supervisor-review.md | 该查什么、何时停止、怎样要求进一步证据。 |
| 协作 | runtime_v2/hub_bridge.py、subagent_bridge.py、launch_groups.py | 消息消费、轻量任务组及 Agent 并发；不接管 compute scheduler。 |
| 可读性与验证 | API DAG/router、DagPanel、tests、benchmark 诊断脚本 | 可见状态、回归与效率测量；不修改 gold 或评分权重。 |

使用实际目录 cloudra/dag/ 和 cloudra/tools/Plantool/dag_tools/。AGENTS.md 中部分概述路径不等于当前文件路径。

## Task 0：固定诊断案例和统计口径

**Files**

- Create: tests/fixtures/dag_efficiency/README.md
- Create: tests/fixtures/dag_efficiency/cases.json
- Create: tests/fixtures/dag_efficiency/na1_constrained_opt.inp
- Create: tests/fixtures/dag_efficiency/na1_constrained_opt.out
- Create: tests/fixtures/dag_efficiency/na1_identity_mismatch.json
- Create: scripts/analyze_dag_efficiency.py
- Create: tests/test_dag_efficiency_metrics.py

**Interfaces**

- 输入：现有事件 JSON、作业 JSON、只读会话 DB；每种来源可缺失，但输出必须标记 unavailable。
- 输出：summarize_run(events: list[dict], jobs: list[dict], reviews: list[dict]) -> dict；统计窗口、计数、时延分母和缺失字段同时返回。

- [x] 从 /tmp/cloudra-na1-review 与 NA1_exam 提取最小片段，登记原文件、hash、抽取范围及关键字段；脱敏路径，不复制整份运行目录／数据库入 git。
- [x] cases.json 固定六类案例：约束 Opt＋单虚频、错误产物、对称映射歧义、收敛短 IRC、乱序证据、等待 swarm 时的中途告警。每例写预期可成立与不可成立的结论。
- [x] 实现计数与时延统计；Supervisor 累计时间与墙钟时间分别输出，不能混算；缺 consumed 事件时不凭下一条任意事件假造消费时延。
- [x] 增加下面的最小统计回归，再加入重复事件去重和不完整时间窗案例。

```python
from scripts.analyze_dag_efficiency import summarize_run

def test_missing_consumption_is_not_zero_latency():
    result = summarize_run(events=[], jobs=[], reviews=[])
    assert result["message_consumption_latency_seconds"] is None
    assert result["consumption_sample_count"] == 0
```

- [x] Run: uv run pytest -q tests/test_dag_efficiency_metrics.py。记录基线：快照 63 jobs、88 reviews、74 Supervisor sessions；不把该窗口冒充整个 benchmark。
- [x] 独立提交诊断 fixture 与脚本；不得提交原始日志大目录。

**验收：**任何后续改动都能使用同一案例验证；统计缺失不会被当成零延迟。

## Task 1（A）：Supervisor 科学 prompt、skill 与只读工具接线

**Files**

- Modify: cloudra/core/supervisor.py
- Modify: cloudra/runtime/prompt_assembler.py
- Modify: cloudra/tools/registry.py、cloudra/tools/capabilities.py
- Modify: cloudra/runtime_v2/hub_bridge.py
- Modify: cloudra/prompts/supervisor.md
- Modify: cloudra/skills/dft-calculation/SKILL.md
- Create: cloudra/skills/dft-calculation/references/supervisor-review.md
- Create: cloudra/dag/supervisor_tools.py
- Test: tests/test_dag_supervisor.py、tests/test_prompt_assembler.py
- Create: tests/test_dag_supervisor_tools.py

**Interfaces**

- 新增 capability 字段 supervisor_access：none / evidence_read / skill_read / hub / review_decision。registry 是唯一工具名单来源；Hub 另按 action 限权。
- SupervisorToolExecutor.execute(name: str, arguments: dict, *, session_id: str) -> dict；返回现有工具结果形状。构造时注入 core、project_id、workspace_root 和 artifact 根目录。
- GraphSupervisor 的发现与执行均使用同一个 capability 投影；不只改 roles.py 的壳权限。

- [x] 写执行级测试：get_skill 成功；Hub search 真正进入原生 bridge；解析引用可读；科研文件写操作、越界 symlink、compute 提交、未知工具均被拒绝。测试不得只断言工具出现在 prompt。
- [x] supervisor_tools.py 实现受限执行入口；复用 loader 与只读解析原语。读取上限、分页／截断和完整引用一并返回；解析工具若含导出副作用，先调用纯解析函数，不直接开放原工具全功能。
- [x] Hub 允许 search/browse/read/directory/post；call 仅允许已经存在的会话，找不到时返回 target_not_found，不隐式 spawn。post/裁决是显式控制面能力，不能因此获得文件写权限。
- [x] 重写 prompt 与新增 review reference，使用设计 §10 的判断表。最低应包含以下指令块：

```text
Review the requested claim under the allowed methods and available evidence.
Load the matching skill; reuse the same loaded version within this review.
Search AgentHub for unfamiliar methods, input options, or failure patterns.
Distinguish input errors, local search failure, and method limitations.
If more work is required, name the missing evidence, an executable next action,
and the information it is expected to add. Do not demand repetition solely
because a stage is unfilled or an IRC has fewer than a fixed number of points.
Approve partial or method-limited delivery only with a scoped, cited reason.
```

- [x] 删除“单分子没有 endpoint_b”等误导性示例；保留现有 v1 工具协议段直到 Task 7 接线完成，新协议段按 contract_version 选择，避免 prompt 宣称不可调用的新工具。
- [x] 通过可注入的 fake LLM 跑三个多轮工具轨迹：查原始 Opt 输入后否定完整 TS；短 IRC＋端点证据不要求补点；方法受限申请先查 skill/Hub 再决定。固定工具可达性与结构化裁决；另保存真实模型练习记录评估判断质量，不把字符串包含测试当科学评估。
- [x] Run: uv run pytest -q tests/test_dag_supervisor.py tests/test_dag_supervisor_tools.py tests/test_prompt_assembler.py。只提交本任务所改区块，保留此前角色 prompt 工作。

**验收：**Supervisor 确实可以查证据，不能改科研文件；不需要构建任意 Python 沙箱。

## Task 2（A）：ORCA 输入语义明确化，拒绝静默丢参

**Files**

- Create: cloudra/tools/core/calculation_intent.py
- Modify: cloudra/tools/Chemtool/qm_input_writer.py
- Modify: cloudra/tools/Chemtool/submit_compute_job.py
- Modify: cloudra/runtime_v2/method_policy.py
- Modify: cloudra/skills/dft-calculation/references/orca-inputs.md
- Test: tests/test_qm_input_writer.py、tests/test_runtime_v2_method_policy.py
- Create: tests/test_calculation_intent.py

**Interfaces**

calculation_intent.py 提供下列模型及函数。task_type 的旧输入在边界适配为该模型；ORCA 原生块仍保留，不另建一种外部计算 DSL。

```python
from typing import Literal
from pydantic import BaseModel, Field

class CalculationIntent(BaseModel):
    engine: str
    engine_version: str | None = None
    provider: str | None = None
    tasks: set[str] = Field(default_factory=set)
    frequency_mode: Literal["auto", "analytic", "numeric"] = "auto"
    constraints: list[dict] = Field(default_factory=list)
    charge: int | None = None
    multiplicity: int | None = None
    method_signature: str | None = None
    geometry_hash: str | None = None
    certainty: Literal["known", "partial", "unknown"] = "unknown"

# inspect_input(text: str, *, engine: str) -> CalculationIntent
# intent_from_writer(arguments: dict) -> CalculationIntent
# validate_writer_request(arguments: dict) -> list[dict]
```

tasks 新写入仅接受 minimum_opt、ts_opt、frequency、single_point、irc、relaxed_scan；解析不完整不得猜成某个类型。writer 新增 frequency_mode 参数，ORCA 的 task_type=[{"freq":null}] 配 frequency_mode="numeric" 明确生成 NumFreq；没有 frequency 任务却指定该参数时拒绝。TS 初始 Hessian 控制仍通过原生 orca_blocks 表达。validate_writer_request 的条目固定为 code/field/message，空列表表示此层没有发现输入冲突，并非科学有效性已通过。

- [ ] 写失败回归：未知 numfreq 键、Gaussian 子选项 calcfc/noeigen、ORCA end_setting、重复冲突的任务块必须给明确错误；显式 numeric frequency 路径生成 NumFreq，不带默认 Opt。
- [ ] writer 实现任务归一化和原生参数输出，回传 interpreted_intent、unapplied_options（成功时为空）、生成路径；无法实现的选项返回失败，不写出看似成功的计算文件。
- [ ] 添加 ExtOpt OptTS／NumFreq／IRC 三个完整 golden 输入；断言没有默认 DFT method/basis、没有继承扫描约束。故意保留约束的输入必须声明受限任务并输出限制信息。
- [ ] 从已生成文本重新 inspect_input，比较关键意图；不能只信 writer 的声明。检查实际方法时复用现有 MethodPolicy 的 fail-closed 规则，不因新的意图模型放宽允许方法。
- [ ] 补 provenance 注释，区分 expected_smiles 与经过证据验证的身份。对既有 benchmark smiles 绑定协议保留来源说明，禁止自动生成 verified 标签。
- [ ] 明确 mem 总量与 maxcore 每进程换算；显式申请资源不足返回诊断。调度器本身不解析输入。外部程序资源未知时说明未知，不自动推断其模型内存。
- [ ] Run: uv run pytest -q tests/test_calculation_intent.py tests/test_qm_input_writer.py tests/test_runtime_v2_method_policy.py；用临时目录生成文件，不提交作业。
- [ ] 同步 skill 的 workaround 与已修复行为，单独提交。

**验收：**传入但无法实现的选项不会静默消失；程序返回的意图与真实输入相符。

## Task 3（A）：扫描候选与 ORCA IRC 解析闭合

**Files**

- Modify: cloudra/tools/core/orca_frames.py
- Modify: cloudra/tools/Chemtool/ts_guess.py、cloudra/tools/Chemtool/log_parser.py
- Modify: cloudra/skills/dft-calculation/references/orca-inputs.md
- Test: tests/test_orca_frames.py、tests/test_ts_guess.py
- Add fixtures under: tests/fixtures/orca/，复用已有 cope_relaxed_scan 和 IRC 样本

**Interfaces**

- 复用已有 FrameRecord；新增 extract_irc_endpoints(log_path: str) -> dict，返回 forward/backward 的 geometry_ref、origin 和 availability，不直接命名 reactant/product。
- scan_parse 返回候选时必须同时有 scan_index、energy、geometry_ref、source。峰值坐标缺失时 candidate=null，另返回 candidate_unavailable。

- [ ] 写回归：最大能量点不是最后一帧时取正确坐标；峰值对应 sidecar 丢失时不得使用末帧替代；多个同名旧文件存在时按本次产物 manifest 取源。
- [ ] 在 orca_frames 增加原生 F/B trajectory 与 final endpoint 读取；ts_guess strict 复用它，log_parser 不复制解析规则。
- [ ] IRC 有终止但路径未收敛时保持缺口；少于固定点数但两侧收敛、端点已验证时不报告“必须补点”。不自动把 F/B 映射成 R/P。
- [ ] Gaussian scan_start 与真实起点不同，默认返回 start_geometry_mismatch，并建议先生成目标起点几何；不能只调整增量。若未来提供显式几何调整，另作可验证操作。
- [ ] Run: uv run pytest -q tests/test_orca_frames.py tests/test_ts_guess.py。检查现有 Gaussian 路径不退化；无需真实 ORCA/MLIP。
- [ ] 更新 skill 的已知限制，单独提交。

**验收：**Agent 不再因工具缺少端点提取或错误扫描坐标而重做有效计算。

## Task 4（B）：任务契约、事实存储与可靠来源

**Files**

- Modify: cloudra/dag/models.py、cloudra/dag/store.py、cloudra/dag/drafts.py
- Modify: cloudra/dag/evidence_inbox.py、cloudra/persistence/database.py
- Modify: cloudra/runtime_v2/compute_notify.py
- Modify: cloudra/tools/registry.py、cloudra/tools/capabilities.py
- Create: cloudra/dag/evidence_facts.py
- Test: tests/test_dag_store.py、tests/test_dag_propose.py、tests/test_dag_evidence_bindings.py
- Create: tests/test_dag_evidence_facts.py

**Interfaces**

```python
from typing import Literal
from pydantic import BaseModel, Field
from cloudra.dag.models import GraphRef

class ClaimSpec(BaseModel):  # 实际放在 models.py
    kind: Literal["mechanism", "electronic_barrier", "free_energy_barrier", "selectivity", "property"]
    quantity: str
    unit: str | None = None
    reference: dict = Field(default_factory=dict)
    scope: dict = Field(default_factory=dict)
    required_checks: set[str] = Field(default_factory=set)
    optional_checks: set[str] = Field(default_factory=set)

class EvidenceFact(BaseModel):  # 放在 evidence_facts.py
    fact_id: str
    check: str
    outcome: Literal["supports", "refutes", "inconclusive"]
    subject: dict
    source_refs: list[GraphRef]
    details: dict
    adapter_version: str
```

subject 的固定键为 candidate_id、geometry_hash、method_signature、target_hint（可以为空）；details 为解析事实。check 由版本化检查词表校验，不能接收任意自造检查。首版词表为 stationary_point、curvature、mode_relevance、path、identity、mapping、energy、thermochemistry、method_applicability。

- DagStore.record_facts(facts: list[EvidenceFact]) -> list[str]：按来源、实际尝试与解析版本幂等。
- DagStore.facts_for_target(target_id: str) -> list[EvidenceFact]：包含绑定与 target_hint 可归属条目。
- StageContract 增加 contract_version 与 claim_spec；保留旧阶段形状读取。

- [ ] 新迁移为证据登记增加 tool_call_id/compute_job_id 索引；历史可解析记录逐批回填，不能改写旧 hash；不可解析条目保留 legacy 来源状态。
- [ ] 新事实表存不可变 payload 和 adapter_version；证据关联使用现有 bindings 表扩展，不在每个节点 metadata 复制完整事实。
- [ ] 计算终态通知路径先登记可读核心文件的 ArtifactService 快照，再通知；重复解析复用 hash，独立作业 attempt 不去重合并。不可读源标记 unavailable，回收重试不丢消息。
- [ ] 显式送审和记录失败结果都不再因 is_success=false 被拒绝；但失败结果不能充作对应成功计算的支持。
- [ ] 草稿按请求量生成契约，method policy 只从项目设置读取；property 契约不继承“必须有 elementary-step 边”的空图判据。
- [ ] 已接受契约的降级或任务类型变更先产生待审批版本；未经同意不改变当前范围。测试通过删除 required_checks、改 kind、移除目标等方式都不能绕过科学范围审批。
- [ ] 持久化回归覆盖：同一文件重复解析、同名文件被覆盖、不同作业重复失败、进程中断后补收文件、legacy row 不可解析；artifact 引用校验失败保持 unresolved。
- [ ] Run: uv run pytest -q tests/test_dag_store.py tests/test_dag_propose.py tests/test_dag_evidence_bindings.py tests/test_dag_evidence_facts.py。
- [ ] 提交存储与类型层；v2 尚不启用。

**验收：**证据可复查，反证可保存；已有 API 与旧会话仍可读取。

## Task 5（B）：物种身份与按类型验证，允许乱序绑定

**Files**

- Create: cloudra/dag/requirements.py
- Modify: cloudra/dag/engine.py、cloudra/dag/models.py、cloudra/dag/completion.py
- Modify: cloudra/dag/evidence_inbox.py
- Modify: cloudra/tools/Chemtool/reaction_mapping.py、cloudra/tools/Chemtool/log_parser.py
- Modify: cloudra/tools/Plantool/dag_tools/dag_bind_evidence.py
- Test: tests/test_reaction_mapping.py、tests/test_dag_engine.py、tests/test_dag_completion.py
- Create: tests/test_dag_requirements.py

**Interfaces**

- evaluate_claim(claim: ClaimSpec, facts: list[EvidenceFact]) -> dict，固定返回 checks、missing、contradictions、scientific_status。
- scientific_status：supported / unresolved / out_of_scope。完整性与审查批准分别计算。
- identity_result(identity: str, binding: str, *, needs_mapping: bool) -> dict，返回 identity_check 与 mapping_check，分别为 supports/refutes/inconclusive/not_required。
- bind 接受 attachments=[{tool_call_id, bind_target, stage_kind}]；旧单条参数转换成一项列表，二者同时提供报参数冲突。每批次带 expected_revision。

- [ ] 先写以下纯函数回归，确认身份与具体原子对应独立。

```python
from cloudra.dag.requirements import identity_result

def test_symmetric_mapping_does_not_refute_species():
    result = identity_result("match", "inconclusive", needs_mapping=False)
    assert result == {"identity_check": "supports", "mapping_check": "not_required"}

def test_identity_mismatch_is_counterevidence():
    result = identity_result("mismatch", "complete", needs_mapping=True)
    assert result["identity_check"] == "refutes"
```

- [ ] reaction_mapping 事实适配器透传两端身份、实际组分、电荷、自旋和映射不确定性；需要立体／同位素具体对应的契约保留 mapping 缺口。
- [ ] log_parser 事实适配器按 CalculationIntent 与实际观测生成驻点、约束、频率、路径等结果；未知不等于通过。频率个数不独自构成 TS 支持，模式解释保留可审查来源。
- [ ] requirements 用明确集合实现 minimum/TS/连接/电子垒/自由能/选择性条件。每个检查实例带主体键，例如 identity:endpoint_a 与 identity:endpoint_b；只验证一端不能通过两端身份要求。skip 和 not_applicable 不进入支持事实；高低级别组合只在显式 scope 允许时接受。
- [ ] 移除 v2 的 stage_out_of_order；保留 undeclared_stage、source_unavailable、revision_conflict 等真实门禁。附件接收与其科学支持程度分开返回。
- [ ] 使用同一个 fixture 对三个事实的全部六种排列绑定，比较最终 checks／结论一致；测试先交 thermochemistry、错几何频率、错误端点、多组矛盾证据和重绑并发。中间状态不得出现虚假高等级。
- [ ] 重写 v2 derive_evidence_level 投影；不以 thermo_annotated 单一枚举替代 checks。legacy 读路径保持原记录，并标明旧口径。
- [ ] Run: uv run pytest -q tests/test_reaction_mapping.py tests/test_dag_engine.py tests/test_dag_completion.py tests/test_dag_requirements.py；提交，v2 仍不启用。

**验收：**乱序只改变到达时间，不改变最终科学结论；明确不匹配不会被 ignore 掉。

## Task 6（B）：结构化审查请求与异常汇总

**Files**

- Create: cloudra/dag/review_requests.py
- Modify: cloudra/dag/store.py、cloudra/dag/evidence_inbox.py、cloudra/dag/completion.py
- Modify: cloudra/persistence/database.py
- Modify: cloudra/tools/Plantool/dag_tools/dag_message_supervisor.py
- Create: cloudra/tools/Plantool/dag_tools/dag_review_evidence.py
- Modify: cloudra/tools/registry.py、cloudra/tools/capabilities.py
- Modify: cloudra/tools/Plantool/dag_tools/dag_view.py
- Create: tests/test_dag_review_requests.py

**Interfaces**

review_requests.py 定义以下版本化模型：

```python
from typing import Literal
from pydantic import BaseModel, Field
from cloudra.dag.models import GraphRef

class ReviewRequest(BaseModel):
    request_id: str
    kind: Literal["draft", "evidence", "exception", "exit"]
    requester: str
    target_ids: list[str]
    question: str
    supporting_refs: list[GraphRef] = Field(default_factory=list)
    counterevidence_refs: list[GraphRef] = Field(default_factory=list)
    proposal: dict = Field(default_factory=dict)
    basis_fingerprint: str

class ReviewDecision(BaseModel):
    decision_id: str
    request_id: str
    basis_fingerprint: str
    verdict: Literal["accept", "reject", "needs_evidence"]
    reason: str
    evidence_refs: list[GraphRef]
    findings: list[dict] = Field(default_factory=list)
    next_action: str | None = None
```

findings 每项为 target_id/check/outcome/reason/evidence_refs；reject／needs_evidence 必须说明缺口和可执行动作，或 operational_blocker。Supervisor 不能用 verdict 覆盖确定性反证；需解释适用范围或提交新证据。接受退出的 proposal 固定含 disposition、scope、remaining_gaps、method_limits。

- enqueue_review(request: ReviewRequest) -> str：返回新／合并请求 ID。
- resolve_review(decision: ReviewDecision, *, expected_basis: str, claim_token: int) -> dict：原子校验、落裁决及相关图变更。claim_token 由 worker 执行上下文注入，不让模型自报。
- collect_review_exceptions(target_ids: list[str]) -> list[dict]：返回设计 §6 的四类异常及稳定 exception_key。

- [ ] 写入请求／裁决表；去重依据 kind＋scope＋evidence fingerprint，绝不只合并 trigger 字符串。新反证变化必须产生新 basis。
- [ ] dag_message_supervisor 支持结构化请求；普通研究 Agent 可提出证据／异常审查，项目退出需 Coordinator 身份。所有对象强制同项目，不能传跨项目证据 ID。
- [ ] 服务端按请求 scope 补齐已登记的相关反证和未决异常，再生成 basis_fingerprint；测试请求者故意不传 counterevidence_refs 时，Supervisor 仍能看到现有 mismatch。
- [ ] dag_review_evidence 批量处理 findings，引用未登记／hash 不匹配／请求 basis 过期均拒绝。旧 dag_review_call 留给旧 contract 与历史解析，v2 模型只看到新入口。
- [ ] 实现交付异常汇总：缺口、冲突、已知 target 的漏绑、未知 target 的关键事实。按稳定 key 合并；已处置无关旧尝试保留理由，不反复成为同一异常。
- [ ] 测试重复请求、无关目标更新不作废审批、相关目标更新使审批过期、多目标原子裁决、失败证据送审、未知 target 处置、未读证据不能被摘要伪造。
- [ ] Run: uv run pytest -q tests/test_dag_review_requests.py tests/test_dag_review_call.py tests/test_dag_evidence_bindings.py；提交协议，暂不启用自动 worker。

**验收：**Supervisor 收到的是完整问题包；异常汇总补漏而不是重审全部计算。

## Task 7（B）：异步审查 worker 与可靠通知

**Files**

- Create: cloudra/runtime_v2/review_worker.py
- Modify: cloudra/dag/supervision.py、cloudra/dag/controller.py、cloudra/dag/evidence_inbox.py
- Modify: cloudra/runtime_v2/policies/dag_stage.py、cloudra/runtime_v2/core.py
- Modify: cloudra/services/api_v2/app.py、cloudra/benchmark/backend.py
- Modify: cloudra/core/supervisor.py、cloudra/prompts/supervisor.md
- Test: tests/test_dag_supervisor_feedback.py、tests/test_runtime_v2_dag_stage.py
- Create: tests/test_runtime_v2_review_worker.py

**Interfaces**

- ReviewWorker.start() / async close()；构造注入 core、项目 DAG store 获取器、Supervisor factory。
- ClaimedReview 在 review_requests.py 定义为包含 request: ReviewRequest、owner: str、claim_token: int、expires_at: str 的模型。
- DagStore.claim_review(owner: str, *, lease_seconds: int) -> ClaimedReview | None。
- DagStore.pending_review_notifications() -> list[dict]；标记通知以 decision_id 幂等。
- 真实权威是 DAG 表；core.review_worker 是刻意易失执行器，不存另一份请求状态。

- [ ] on_tool_finished 保存／提取事实后立即返回，v2 普通计算不入审查箱；只有设计 §9 的触发才 enqueue。提交请求返回 queued，而不是等待 LLM。
- [ ] worker 每项目单消费者；领取请求后加载 scoped 证据和已有裁决摘要。删除类级 _SUPERVISION_STATES 作为状态权威的依赖；旧模式路径隔离保留。
- [ ] claim 返回 owner 与递增 claim_token，处理期间续租；resolve 必须验证当前 token，阻止租约过期的旧 worker 落裁决。单次审查设置轮次／时间上限并计入项目预算，耗尽保留请求且显示操作受限。
- [ ] API 和 benchmark 两个宿主都接 start/close；关闭时释放或让租约可恢复，不能只在 Web 环境工作。
- [ ] 裁决先落账，再通知请求者与 Coordinator。进程在落账后通知前中断，恢复后补投；重复补投按 decision_id 只影响一次流程。
- [ ] 重试上限、退避和可用性错误用一个配置对象；不要硬编码化学重算次数。LLM 失败不清空请求，不自动授予批准。
- [ ] 写慢 fake Supervisor 测试：普通工具完成可立即返回；请求处理期间第二请求可持久入箱；同项目不同时启动两个审查；不同项目互不锁住；租约过期可重新领取；同 basis 裁决只生效一次。
- [ ] 新版 prompt 接通实际新接口，继续保留草稿接受前 compute gate。run 中审查工具输出一般结果字段不得依赖旧 output.accepted 属性总是存在。
- [ ] Run: uv run pytest -q tests/test_runtime_v2_review_worker.py tests/test_dag_supervisor_feedback.py tests/test_runtime_v2_dag_stage.py tests/test_dag_supervisor.py；提交。

**验收：**审查不会挡住普通工具，崩溃不会丢请求或裁决。

## Task 8（B）：退出审批和科学结论分离

**Files**

- Modify: cloudra/dag/stop_audit.py、cloudra/dag/completion.py、cloudra/dag/store.py
- Modify: cloudra/runtime_v2/policies/dag_stage.py、cloudra/runtime_v2/agent_runner.py
- Modify: cloudra/tools/Stoptool/stop_tool.py
- Modify: cloudra/benchmark/backend.py、cloudra/benchmark/refusal.py
- Test: tests/test_runtime_v2_dag_stage.py、tests/test_dag_completion.py、tests/test_benchmark.py
- Create: tests/test_dag_exit_approval.py

**Interfaces**

- StopGate 为模型：action=allow_final/wait_background/wait_review/needs_work，report，request_id（可空），reason。
- audit_stop(disposition: str, *, approval_id: str | None, user_stop_event_id: str | None) -> StopGate。
- delivery_disposition 保持 complete/partial/user_terminated；方法受限放科学结论字段 scientific_outcome=method_limited，避免同时新增多个含混 stop 值。

- [ ] 写门禁矩阵：无异常 complete 通过；有异常 complete 进入一次审查；partial 无批准等审查；匹配批准通过；过期批准拒绝；用户来源真实的终止通过；模型捏造 user_terminated 拒绝。
- [ ] 核对运行生命周期所有最终路径：显式 stop、无工具最终回复、异常／超时。record_unaudited_partial 只能记“未经审查的运行结束”，不能产生批准或 mechanism_found。
- [ ] 请求 final 与等待后台分开。Supervisor 壳／review worker 不视为可绕过审计的普通后台；普通作业存在时返回 wait_background，不落最终交付。待 launch group 集成后把未启动成员也计入等待。
- [ ] review 决定到达时恢复等待；拒绝保持 gaps 并给 next_action。相同 basis 的拒绝不触发“拒绝→重提→拒绝”空转；硬预算耗尽产生 operational blocker。
- [ ] 科学范围被批准跳过时保留缺口与范围，绝不改成支持事实。最终报告列 resolved_claims／unresolved_claims／approved_scope／method_limits。
- [ ] benchmark 保留原评分公式；新增运行状态旁注，避免把 timeout 或未批准退出冒充正确拒答。历史行为分类保持可比较，科学审批状态作为正交诊断字段。
- [ ] Run: uv run pytest -q tests/test_dag_exit_approval.py tests/test_runtime_v2_dag_stage.py tests/test_dag_completion.py tests/test_benchmark.py；提交。此任务与 Task 5–7 全部通过后才可启用 v2。

**验收：**严格监督体现在科学理由和范围审批，不能靠无限续算维持表面完整性。

## Task 9（C）：AgentHub 契约、增量读取与关键消息消费

**Files**

- Modify: cloudra/tools/Managetool/agent_hub.py
- Modify: cloudra/runtime_v2/hub_bridge.py、cloudra/runtime_v2/turn_pipeline.py
- Modify: cloudra/runtime_v2/schemas.py、cloudra/runtime_v2/apply.py、cloudra/runtime_v2/persistence.py
- Modify: cloudra/runtime_v2/knowledge.py
- Modify: cloudra/runtime/prompt_assembler.py、cloudra/prompts/coordinator.md
- Test: tests/test_runtime_v2_hub_bridge.py、tests/test_runtime_v2_knowledge.py、tests/test_runtime_v2_replay_equivalence.py

**Interfaces**

- post_id／parent_id 使用字符串；旧整数输入仅做显式兼容转换，找不到真实帖子返回 not_found，不能伪造事件映射。
- browse 增加 cursor；返回 posts/next_cursor。search 返回 posts/library/sources_status，后者区分可用无命中、未安装和失败。
- hub.notification_consumed 事件：post_id、session_id、message_id、consumed_at；只有消息进入模型上下文才产生。core 中增加消费游标投影，由 apply_event 独占更新。

- [ ] 修正 schema、tool description 与真实返回一致，尤其 library 和 directory 字段；测试通过公共 schema 调用 native bridge，不能只直接测内部函数绕过类型错误。
- [ ] 增量 browse 使用事件位置分页，分页游标绑定 project；新增帖子不重复或漏跨页项。先不增加跨 provider 缓存。
- [ ] 项目定向关键帖子的未消费状态从既有 Hub 事件及消费事件推导；恢复后只补未消费关键通知，普通 mailbox 的历史聊天不全部重放。
- [ ] 在 turn_pipeline 拼入消息时记录 consumed；只投递尚未进入上下文的通知不能假记消费。不要把 consumed 当成 Agent 已采纳决定。
- [ ] Hub search 保留 L1/L0/L2 与反驳降权语义；本地库故障时保留可用项目帖子并返回明确来源状态。
- [ ] 共用 prompt 增加“复用已有查询和证据 ID、发现可复用结论及时发帖、定向关键消息含影响和请求动作”；删除过时的强制等全组返回表述，但在 Task 10 上线前不宣称默认已非阻塞。
- [ ] Run: uv run pytest -q tests/test_runtime_v2_hub_bridge.py tests/test_runtime_v2_knowledge.py tests/test_runtime_v2_replay_equivalence.py tests/test_prompt_assembler.py；提交。

**验收：**AgentHub 是可用且可说明来源的知识入口；关键通知重启后不悄悄丢失。

## Task 10（C）：非阻塞委派与真正的运行并发限制

**Files**

- Create: cloudra/runtime_v2/launch_groups.py
- Modify: cloudra/runtime_v2/subagent_bridge.py、cloudra/runtime_v2/commands.py
- Modify: cloudra/runtime_v2/core.py、cloudra/runtime_v2/schemas.py、cloudra/runtime_v2/apply.py
- Modify: cloudra/runtime_v2/persistence.py、cloudra/runtime_v2/agent_runner.py
- Modify: cloudra/tools/Managetool/subagent_launcher.py、cloudra/tools/Managetool/subagent_swarm.py、cloudra/tools/Managetool/get_subagent_report.py
- Modify: cloudra/dag/stop_audit.py
- Test: tests/test_runtime_v2_subagent_bridge.py、tests/test_runtime_v2_replay_equivalence.py
- Create: tests/test_runtime_v2_launch_groups.py

**Interfaces**

- LaunchGroup：group_id、parent_session_id、items、max_concurrency、state。每 item 有 item_id/query/context、child_session_id、state=queued/running/succeeded/failed/cancelled。
- 新 CommandBus 命令 launch_group.create / launch_group.cancel；状态事件 launch_group.created、launch_group.item_started、launch_group.item_finished、launch_group.cancelled。
- worker 仅从事件投影选 queued 项调用现有 agent.spawn；group 状态直接改 core 属违规。
- swarm 返回 group_id、session_ids（已启动）、pending_count；get_subagent_report 支持 group_id 状态查询。

- [ ] 写并发回归：10 项、max_concurrency=2、is_wait=false；任何时刻 active children <=2，第一项终态才放行下一项。不能只测工具返回时的 session 数。
- [ ] 将许可生命周期移到 group worker；部分 spawn 被拒后记录失败并继续处理其余项，不能留下不可见的已启动孤儿。
- [ ] launcher/swarm 新默认立即返回。显式 is_wait=true 用订阅后复查的等待方式，收到相关消息时可提前返回当前状态；父 Agent 得以处理警告。同步返回不再承诺全部终态，更新 schema 与说明。
- [ ] 取消父任务才级联取消 owned children／queued items；父 run 暂停不取消。超时／失败／恢复必须释放许可或把受影响成员明确标为可恢复失败，不能无限占位。
- [ ] 重放恢复 queued/running 成员；按 AgentHost 已有重启失效规则解释旧 running，不能无授权重复创建原任务。live agent 与 group 引用冲突时先对账。
- [ ] audit_stop 将 queued group items 算作普通后台工作；不能因尚未 spawn 所有 Agent 就误判后台已排空。
- [ ] 用 Task 0 中途告警案例证明 Coordinator 在其他子任务未完成时获得一次 LLM 处理机会，且没有取消有效后台计算。
- [ ] Run: uv run pytest -q tests/test_runtime_v2_launch_groups.py tests/test_runtime_v2_subagent_bridge.py tests/test_runtime_v2_replay_equivalence.py tests/test_dag_exit_approval.py；同步 prompt 后提交。

**验收：**消息处理不会等整组任务结束；非阻塞不会突破并发上限。

## Task 11（B/C 集成）：版本迁移、API 与前端可见状态

**Files**

- Modify: cloudra/persistence/database.py、cloudra/dag/store.py
- Modify: cloudra/services/api_v2/routers/dag.py、cloudra/services/api_v2/models.py
- Modify: cloudra/runtime_v2/schemas.py、cloudra/runtime_v2/policies/dag_stage.py
- Modify: frontend/src/api.ts、frontend/src/DagPanel.tsx
- Modify: docs/DAG_ORCHESTRATION.md、AGENTS.md
- Test: tests/test_dag_legacy_replay.py、tests/test_dag_store.py
- Create: tests/test_dag_protocol_upgrade.py
- Create: frontend/src/dagStatus.ts、frontend/src/dagStatus.test.ts

**Interfaces**

- 协议选择 contract_version=1/2；新建项目默认切换的时点由 Task 12 验收决定，旧项目保留原版本。
- API 投影额外给出 checks、review_state、delivery_disposition、scientific_outcome、approval_id；不可用字段明确为 null，不推断 approved。
- 新增显式项目升级命令，通过 CommandBus 记录版本选择，DAG 迁移在可重试 effect 内幂等完成。未完成迁移不允许按 v2 写入。

- [ ] 旧 evidence/journal 不改原文；旧 verdict 标记 legacy_reviewed。旧 pending CallReview 聚合为有来源的历史请求，迁移重复执行不重复建请求。
- [ ] 保留单一开关语义：迁移＋Task 5–8 完成才启用 v2；暂停升级不启用一半的新门禁。明确向后回退为只读或恢复升级前副本，禁止旧写路径解释 v2 数据。
- [ ] 前端分开呈现：证据已收到、检查待满足、审查进行中、partial 已批准。approved partial 不显示成“完整机理已证实”。
- [ ] 在 dagStatus.ts 实现从 API 明确字段映射文案的纯函数；测试 legacy unknown、waiting_review、approved partial、complete 与矛盾未解五种状态。
- [ ] API 只读查询提供分页证据和审查引用；禁止为了前端方便在 router 直接写状态。Supervisor 证据查看打开当前请求对应版本。
- [ ] Run: uv run pytest -q tests/test_dag_protocol_upgrade.py tests/test_dag_legacy_replay.py tests/test_dag_store.py；在 frontend 运行 npm run build 与仓库已有前端测试脚本。
- [ ] 更新 AGENTS 中旧的“逐调用复核”“阶段严格顺序”描述与入口；保留 map 风格，细节链接设计文档。提交。

**验收：**新旧会话边界明确，用户看得到科学缺口，不会因 UI 合并状态而误解结果。

## Task 12：受控回归与 benchmark 验收

**Files**

- Modify: scripts/analyze_dag_efficiency.py
- Create: docs/benchmarks/dag-evidence-review-evaluation.md
- Create: tests/test_dag_efficiency_scenarios.py
- Modify: cloudra/benchmark/backend.py（仅补版本／审查状态诊断输出）

**Interfaces**

- 每个对照 run 保存：代码 SHA/工作区补丁 hash、模型、采样参数、方法策略、task_id、资源上限、prompt/skill hash、契约版本、时间窗。
- 诊断附加科学批准与操作失败信息；graph/selfconsistency/accuracy/binding_quality 的原评分计算保持不变。

- [ ] 把 Task 0 六类案例通过实际工具／pipeline 走完；覆盖 evidence capture → bind → exception → review → stop，而非仅测试纯函数。
- [ ] 补充故障注入：请求保存后崩溃、审查中断、裁决保存后通知丢失、Hub 消费前重启、group spawn 后崩溃、证据文件不可用。检查不会重复计算、虚假批准或永久等待。
- [ ] 基础验证先运行改动文件 compileall，再跑聚焦 DAG/runtime/chem tests；最后按仓库要求运行全套 pytest 和 ruff。失败先定位，不因一次环境缺依赖伪称全部通过。
- [ ] 离线回归通过后，按已授权的 benchmark 资源预算做成对真实运行：至少包含 NA1、可正常回答的对照、方法受限题及其兄弟对照；固定方法白名单，不向 Agent 暴露 gold。若尚无运行预算授权，此步骤留作实施阶段的实际运行授权点，不阻碍此前离线工作。
- [ ] 加做 prompt-only 对照，区分 prompt 改善与 harness 改善；记录所有版本，避免把已修改的 skill 偷换成原基线。
- [ ] 评估 Supervisor 总调用／等待、无关审查、参数失败、重复计算、新信息增益说明、Hub 消费延迟、遗漏和反证、错误完成／错误拒答；不能只报告更快的单条成功样本。
- [ ] 给出上线结论和未通过项。固定案例不得误接受或丢证据；真实 benchmark 若降低科学质量或增加错误拒答，不切新项目默认版本。效果幅度实测报告，不预设漂亮百分比。
- [ ] 将复现命令、数据范围、缺失项、版本与结果写入 evaluation 文档；不提交敏感原始日志或大型计算产物。

**验收：**能说明“哪里更快、有没有损失科学可靠性、结果能否复现”，再决定正式启用。

## 提交与验证纪律

建议每个 Task 独立提交；Task 4–8 是一组不可拆开的上线语义，不等于必须揉成一个巨大提交。提交前检查精确文件 diff，尤其当前工作区已存在大量未提交的 prompt、skill、paper 和 NA1 产物。

本机当前可使用 .venv/bin/python；如果 uv 不在 PATH，以上 uv run pytest 命令替换为 .venv/bin/python -m pytest 即可，不为运行测试重装环境。每个测试使用临时 data_dir，不访问真实项目数据库写路径。

默认验证：

```bash
uv run python -m compileall -q cloudra/dag cloudra/runtime_v2 cloudra/core/supervisor.py cloudra/tools
uv run pytest -q tests/test_dag* tests/test_runtime_v2* tests/test_qm_input_writer.py tests/test_ts_guess.py tests/test_orca_frames.py tests/test_reaction_mapping.py
uv run ruff check cloudra tests
uv run pytest -q tests/
```

## 需求到任务的核对表

| 需求 | 实施任务 | 完成证据 |
| --- | --- | --- |
| 科学退出判据、skill/Hub 权重 | 1、8、9 | 工具轨迹、科学场景演练、退出门禁矩阵 |
| Supervisor 只读查证据 | 1 | 真实工具调用与执行层拒绝测试 |
| 自主送审＋系统补漏 | 4、6、7 | 普通证据零自动审查、异常可恢复入箱 |
| 必须乱序 | 5 | 全排列绑定一致，中途无等级跃迁 |
| 物种身份链路 | 4、5 | mismatch 成反证，mapping 歧义独立 |
| ORCA 输入和解析 | 2、3 | golden 输入、拒绝丢参、扫描与 IRC fixture |
| 反复调参／不科学续算 | 1、8、12 | 具体下一步与预期新信息、拒绝空转、模型行为比较 |
| AgentHub 通信效率 | 9、10 | 字符串 ID、增量读取、消费事件、并发与中途通知 |
| 不能绕过 Supervisor 退出 | 8、11 | 所有结束路径与版本迁移测试 |
| 科学质量和整体效率 | 0、12 | 可复现基线、成对测量、拒答兄弟对照 |

三个用户决策均已对齐：只汇总异常；partial／方法受限退出必须由 Supervisor 同意；Supervisor 首版只读文件和解析，不执行临时 Python。其余是本计划给出的可评审实现选择，不阻塞计划交付。
