# TS 状态机接口与四个 issue 修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 TS 流程改为参数按用途分组、状态可读、同一路径可持续续接的持久状态机，并满足 #108–#111 的关闭条件。

**Architecture:** 保留 prepare/resume 写工具，增加 inspect 读工具，使用一份输入定义及其局部修订视图。复用 compute.db、现有 driver、输入生成器、身份检查、运行权限和项目方法约束；按固定阶段依赖失效证据，不新增通用工作流引擎。正常完成自动接续，失败恢复保留原尝试和依据。

**Tech Stack:** Python >= 3.11、POSIX、Pydantic、SQLite、asyncio、RDKit、现有 Gaussian/ORCA/xTB 适配；不新增依赖。

**Spec:** [2026-10-02-ts-state-machine-interface-design.md](../specs/2026-10-02-ts-state-machine-interface-design.md)

## Global Constraints

- 同一条探索路径只创建一次，后续继续保持同一个 `run_id`；workspace 可有多个独立反应记录。
- 正常步骤自动推进，不要求 Agent 在计算完成后调用 resume。
- 不默认选择科学计算方法，不在阶段之间隐式继承方法。
- 删除 TS 预估时间及其准入限制；实际记录未知时保持缺失。
- 不新增科学阈值、搜索算法、计算队列、后台服务或通用工作流框架。
- 不考虑旧接口兼容，不留旧平铺 schema、空 resume 查询语义或双实现 shim。
- 不支持的旧记录隔离自动推进；现有计算继续运行，不重交、不误标 failed。
- 在途作业不接受输入修订；任何失败或权限变化不得 kill QM，存活判断使用 flock。
- 校验使用 Pydantic、结构化解析或明确 token/枚举；正则只用于原始 QM 输出日志解析。
- 数据路径走 `cloudra/persistence/paths.py`；测试数据使用 conftest 临时目录。
- 只运行相关模块测试；修改后按 compileall → ruff → 聚焦 pytest 验证。
- 本计划不执行远端科学计算、服务部署或自动关闭 issue；关闭须依据对应验收证据。

## Review Focus

1. 请求已落盘但工具响应丢失：重放不能重复入队，过期 revision 不能破坏已处理请求的重试。
2. 引擎切换后编号基准变化：已绑定原子不能被重新解释或误指向另一原子。
3. 部分后续方法尚未声明：只停在实际缺少输入处，不能继承方法或重复有效上游。
4. inspect 的文件导出滞后或作业刚完成：返回权威快照及导出版本，不写状态或触发推进。
5. 原生产者权限收窄或旧格式记录存在：停止新提交，不影响其他流程恢复和既有计算存活。

上述五项分别在任务 2、1/4、4、3、7/8 写入测试。

## 文件与职责

| 文件 | 职责 |
|---|---|
| 新增 `cloudra/tools/core/ts_inputs.py` | 分组输入、科学方法与来源类型、局部修订 schema；不执行计算 |
| 新增 `cloudra/tools/core/ts_state_view.py` | 从权威状态生成只读公共视图；不调用 advance |
| 新增 `cloudra/tools/core/ts_revision.py` | 输入差异、固定阶段失效范围、失败恢复核验；不自建提交链 |
| 修改 `cloudra/tools/core/ts_process.py` | 各阶段消费新输入、现有来源接入、方法逐步执行与最终判定 |
| 修改 `cloudra/services/ts_pipeline_store.py`、`cloudra/persistence/database.py` | 请求回执、修订与证据复用、旧格式识别 |
| 修改 `cloudra/services/ts_pipeline_context.py` | 系统持有的生产权限/方法上下文，与既有账本上下文同生命周期 |
| 修改 `cloudra/tools/Chemtool/ts_search_process.py`、`cloudra/tools/registry.py`、`cloudra/tools/capabilities.py` | 新接口和读写能力投影 |
| 修改现有 identity、calculation_intent、权限/方法 policy 与 bridge | 复用科学检查；修补明确缺口，不新造审批框架 |

后续任务不得引入表中未说明的新公共抽象。需要的辅助模型放在各职责文件，不建立插件注册层。

## Task 1：统一分组输入及明确编号语义

**Files:** Create `cloudra/tools/core/ts_inputs.py`, `tests/test_ts_inputs.py`; Modify `cloudra/tools/core/geometry_inputs.py`。

**Interfaces:**
- Produces `TsInput`, `TsInputChanges`, `TsCalculation`, `TsRecovery`, `TsResumeRequest`, `TsExecutionLimits`。TsCalculation 包含显式 engine/method/keywords 与现有任务 settings；TsExecutionLimits 只包含非时间类已授权额度及来源。
- `apply_input_changes(current: TsInput, changes: TsInputChanges) -> TsInput`。
- `normalize_ts_input_atoms(value: TsInput, *, atom_tables: dict) -> TsInput`；内部 0-based，来源与原生分支编号明确。

- [ ] 写 `test_input_changes_cover_every_input_group`：reaction/conformers/guess/ts_optimization/verification/execution 所有公开科学字段都有可修订表达；未知字段拒绝。
- [ ] 写 `test_omitted_null_and_empty_list_have_distinct_effects`：遗漏保留、允许的 null 清除、空列表清空；必需身份字段 null 拒绝。
- [ ] 写 `test_method_and_guess_are_replaced_atomically`：方法对象不合并关键词；scan→xtb_path 不残留 scan 坐标；缺少方法必填项拒绝。
- [ ] 写 `test_method_is_not_inherited_from_another_group` 与 `test_switching_engine_preserves_bound_atom_identity`：缺失仍缺失；ORCA/Gaussian 输入归一化后指向相同稳定身份，换引擎不再解释已绑定数字。
- [ ] 运行 `uv run pytest -q tests/test_ts_inputs.py`，确认失败来自新契约未实现。
- [ ] 实现上述模型与函数。guess 的判别值限 `xtb_path/scan/provided`；conformer 来源限现有生成、文件、档案候选、产物旋转。计算对象无默认理论方法，所有任务设置复用现有原生 schema。
- [ ] 部分修订 schema 从同一份字段定义生成；仅对 Method/来源/guess 做原子对象替换，不写第二份科学字段白名单，不将任意 dict 作为校验逃生口。
- [ ] 运行 compileall、ruff 和上述测试，提交 `refactor(ts): define grouped state machine inputs`。

## Task 2：修订、幂等回执与不可变证据记账

**Files:** Modify `cloudra/services/ts_pipeline_store.py`, `cloudra/persistence/database.py`; Create `tests/test_ts_revision_store.py`。

**Interfaces:**
- Consumes Task 1 的 `TsInput`、`TsResumeRequest`。
- Produces `TsRevisionReceipt`：请求摘要、前后版本、输入差异、retained/invalidated 阶段尝试引用、recovery 引用及已接受状态。
- `get_revision_receipt(db: ComputeDB, *, process_id: str, request_key: str) -> TsRevisionReceipt | None`。
- `commit_input_revision(db: ComputeDB, *, process_id: str, request: TsResumeRequest, record: dict, receipt: TsRevisionReceipt) -> TsRevisionReceipt`。

- [ ] 写 `test_replay_after_response_loss_reuses_revision_and_jobs`：同键同内容返回原回执，revision 和作业数不增加，先判重放再判 expected_revision。
- [ ] 写 `test_conflicting_key_and_stale_revision_do_not_mutate`：同键不同请求、过期未处理请求拒绝，声明、预算绑定、阶段和作业不变。
- [ ] 写 `test_revision_keeps_historical_inputs_and_reused_evidence`：旧输入文件不可变，保留阶段仍绑定原作业，新声明不能导致全部阶段重交。
- [ ] 运行 `uv run pytest -q tests/test_ts_revision_store.py`，确认对应失败。
- [ ] 在现有数据库增加仅 TS 修订所需回执表/索引；修订、回执、依赖失效及释放未绑定预约同事务提交。重复请求键按 scope+process 唯一，不新增请求服务。
- [ ] 在现有 process/stage record 显式记录输入格式版本和证据来源版本。实际作业绑定复用 `bind_stage_job`，禁止提交前只有内存状态。
- [ ] 聚焦运行上述测试及 `tests/test_ts_pipeline_store.py`，按 Global Constraints 检查后提交 `feat(ts): persist idempotent input revisions`。

## Task 3：独立只读 inspect 与统一公共状态

**Files:** Create `cloudra/tools/core/ts_state_view.py`, `tests/test_ts_inspect.py`; Modify `cloudra/tools/Chemtool/ts_search_process.py`, `cloudra/tools/registry.py`, `cloudra/tools/capabilities.py`, `cloudra/services/ts_pipeline_store.py`。

**Interfaces:**
- Produces `TsProcessView`，字段按 spec §6；`TsInspect`、`TsInspect_input_schema`。
- `inspect_process(db: ComputeDB, *, project_id: str, run_id: str, workspace_dir: str, can_write: bool) -> TsProcessView`。
- `build_process_view(state: dict, jobs: list[dict], *, can_write: bool) -> TsProcessView`；可供 prepare/resume/通知复用。

- [ ] 写 `test_inspect_has_no_state_or_compute_side_effects`：waiting/blocked/ended 三态下，调用前后 DB revision、作业数、介入数及导出内容相同；patch advance 为抛错仍能读取。
- [ ] 写 `test_readonly_peer_can_inspect_same_project_but_not_foreign_project`：非 owner 的只读 reviewer 可读获准同项目记录；跨项目拒绝。
- [ ] 写 `test_inspect_reports_authoritative_jobs_and_export_revision`：导出滞后时返回 DB 当前 snapshot 与导出版本；不刷新导出、不消费完成事件。
- [ ] 写 `test_next_is_state_and_permission_dependent`：只读、active、缺方法、失败扫描的 next 信息不同，不返回固定候选动作表。
- [ ] 运行 `uv run pytest -q tests/test_ts_inspect.py`，确认失败，再实现视图和工具。
- [ ] inspect 的所有 DB/文件读在 `asyncio.to_thread`；注册为只读证据访问，避免 `_SCIENCE_ROLES` 把 explorer 排除。视图只读取已记录事实，禁止运行昂贵科学解析。
- [ ] 写入阶段维护完整输入/历史导出及版本，inspect 只提供入口。各写工具不再单独拼装冲突状态文本。
- [ ] 运行上述测试与相关工具可见性测试，完成规范检查后提交 `feat(ts): expose read-only process inspection`。

## Task 4：各阶段消费分组输入，支持已有来源与独立方法

**Files:** Modify `cloudra/tools/core/ts_process.py`, `cloudra/tools/core/ts_candidate_pipeline.py`, `cloudra/tools/core/ts_sampling_pipeline.py`, `cloudra/tools/core/geometry_optimization.py`, `cloudra/tools/core/xtb_path_runner.py`, `cloudra/tools/Chemtool/ts_search_process.py`; Create `tests/test_ts_stage_inputs.py`; Modify 相关 `tests/test_ts_process.py`、`tests/test_ts_search_process_tools.py` fixture。

**Interfaces:**
- Consumes `TsInput`、`TsCalculation`、`TsProcessView`。
- 修改 `TsStartRequest` 和 `TsProcessRecord` 使用 `input: TsInput`；删除 `TsDeclaration`/旧 `TsAdjustment` 在最终接口中的使用。
- `stage_calculation(record: TsProcessRecord, purpose: str) -> TsCalculation | None`：固定 purpose 到对应分组的显式计算映射，未配置返回 None。

- [ ] 写 `test_stage_requires_its_own_calculation_without_fallback`：TS/Freq/IRC/两侧 Opt/Freq 分别使用自己的方法，缺配置停在实际子步骤并列缺项；不重跑完成的上游。
- [ ] 写 `test_provided_candidate_skips_unneeded_search_but_checks_dependencies`：有来源和身份绑定的 TS 初猜不执行初猜搜索；缺映射/目标端点资料仍可解释阻塞。
- [ ] 写 `test_existing_conformer_and_irc_sources_are_validated_before_reuse`：种子和现有 IRC 日志不是“提供路径即通过”，版本/身份不匹配拒绝复用。
- [ ] 写 `test_one_prepare_advances_complete_declared_chain_without_agent_resume`：fixture 作业终态驱动完整 TS/Freq/IRC/双端链，Agent resume 调用次数为 0。
- [ ] 运行 `uv run pytest -q tests/test_ts_stage_inputs.py`，确认失败。
- [ ] 修改 build/map/guess/各输入 writer 按分组消费。使用来源分支接入已有结构、档案候选和 provided 初猜；xTB 不可用/失败不得静默改选科学方法。
- [ ] 将现有旋转产物、候选选择、分区引用、端点替代种子能力映射至来源/verification；复杂补采样与分区分析由既有专门工具完成，再 resume 引用其产物，不丢弃既有档案。
- [ ] 将原生计算设置、Hessian 来源和结果 parser 按实际阶段引擎绑定；跨引擎不机械复用不支持的 Hessian，缺能力明确报告。
- [ ] 迁移相关旧 fixture 到统一 input，删旧平铺 schema/默认方法及无调用的特例；不保留动态转换 shim。
- [ ] 运行上述测试及直接受影响的 TS 工具/driver 测试，完成规范检查后提交 `refactor(ts): consume stage-specific inputs and sources`。

## Task 5：自由续接、固定依赖失效与失败恢复（#110）

**Files:** Create `cloudra/tools/core/ts_revision.py`, `tests/test_ts_resume_transitions.py`; Modify `cloudra/tools/core/ts_process.py`, `cloudra/tools/core/ts_pipeline_driver.py`, `cloudra/tools/Chemtool/ts_search_process.py`; Modify `tests/test_ts_workflow_scan.py`, `tests/test_ts_candidate_continuation.py`。

**Interfaces:**
- `plan_input_revision(record: TsProcessRecord, request: TsResumeRequest) -> TsRevisionReceipt`。
- `validate_recovery(record: TsProcessRecord, request: TsResumeRequest) -> None`：失败时抛明确拒因。
- `resume(record: TsProcessRecord, request: TsResumeRequest) -> TsProcessRecord` 替换旧 adjustment 参数。

- [ ] 写 `test_same_run_can_change_guess_and_formal_method_after_attempt_ends`：search_failed/candidate_only/verified 的合法新输入保留 run_id 和历史，当前旧结论不冒充新结论。
- [ ] 写 `test_endpoint_revision_retains_independent_completed_branch`：仅一端改变，TS/Freq/IRC 与另一端 job_id 保持不变；受影响端新尝试。
- [ ] 写 `test_failed_scan_point_count_only_does_not_requeue`：7→8 点且第一点优化/临时文件失败，DB/阻塞/旧日志不变；仅 reason 不足以解除阻塞。
- [ ] 写 `test_environment_repair_evidence_allows_same_input_new_attempt`：绑定 failed_attempt 和可检查恢复 artifact 后重试；无效/外部/过期引用拒绝；服务恢复后仍判同一失败。
- [ ] 写 `test_active_job_and_empty_resume_are_rejected_without_side_effects`：无动作指向 inspect；waiting/ready 作业存在时修订拒绝，无 kill/取消标志。
- [ ] 运行 `uv run pytest -q tests/test_ts_resume_transitions.py`，确认失败。
- [ ] 使用固定 TS purpose 依赖表计算最早失效步骤和独立分支复用；原输入文件不覆盖。将修订回执交任务 2 事务保存后再 advance。
- [ ] 恢复核验复用原生失败类别和实际修复 artifacts，禁止正则判断 reason 是否“有道理”，禁止增加科学失败判据。科学歧义返回决策检查点。
- [ ] 所有同路径恢复移除旧 EndpointRetry/selection 等顶层特例；使用分组输入表达对应种子/来源/设置，保留既有不可变证据档案。
- [ ] 聚焦运行上述及扫描/候选恢复测试，完成规范检查后提交 `feat(ts): resume revised attempts with evidence reuse`。

## Task 6：输入身份与完整方法提交前核验（#109、#111）

**Files:** Modify `cloudra/tools/Chemtool/reaction_mapping.py`, `cloudra/tools/core/calculation_intent.py`, `cloudra/tools/core/ts_process.py`, `cloudra/runtime_v2/method_policy.py`, `cloudra/runtime_v2/policies/method_policy.py`, `cloudra/services/ts_pipeline_context.py`; Create `tests/test_ts_input_evidence.py`, `tests/test_ts_method_contract.py`; Modify `tests/test_reaction_mapping.py`, `tests/test_runtime_v2_method_policy.py`, `tests/test_qm_input_writer.py`。

**Interfaces:**
- 从 reaction_mapping 现有具体结构绑定提取共享 `check_concrete_binding(request: ReactionMapping_input_schema, mapping_result: dict) -> dict`，工具和 TS 均调用。
- 在 calculation_intent 定义 `MethodDifference`，增加 `compare_calculation_input(content: str, expected: Mapping[str, object], *, charge: int, multiplicity: int) -> list[MethodDifference]`；expected 来自 TsCalculation 的标准化映射，公共 primitive 不反向依赖 TS。
- 方法授权上下文复用项目 `MethodPolicy` 与运行时已确认方法记录，不由 Agent 输入自授予。

- [ ] 写 `test_element_consistent_map_cannot_clear_identity_mismatch`：existing mismatch/inconclusive 与具体版本绑定；补元素排列不提交 path/QM。
- [ ] 写 `test_identity_is_rechecked_after_geometry_changes` 与 `test_unambiguous_valid_binding_keeps_final_validation`：替换/预组织输入重新核验，最终 verdict 仍验证实际端点。
- [ ] 写 `test_missing_required_keywords_and_unauthorized_method_changes_block_before_ready`：D3BJ 等完整约定遗漏、正式泛函/溶剂/电荷/自旋变更返回逐项差异，READY 行数不增加。
- [ ] 写 `test_authorized_semiempirical_scan_differs_from_formal_ts_method`：显式获准扫描与正式方法不同可提交，记录 actual method/use，能量不升级为正式证据。
- [ ] 写 `test_equivalent_basis_spelling_and_multiline_native_input`：按既有规范化规则接受等价写法；多行 route/%block 有确切 token 解析，未知字段不能猜成通过。
- [ ] 运行两个新测试文件确认失败；实现共享 binding 和方法比较。
- [ ] 与现有 MethodPolicy 的方法/基组检查共用规范化事实，在 TS 内部提交前应用同一可信约束；完整关键词差异核对不能只靠 method family whitelist。未知授权来源如实报缺项。
- [ ] 将修改范围内原生输入校验使用的正则改为显式行/token/括号状态解析；原始 QM 日志解析的正则可保留，不对未改动的其他 parser 作无关重构。
- [ ] 在 prepare/guess/submit/refine 的实际结构边界应用已有身份检查，保存结构哈希、声明版本和 binding 事实；新扫描不继承正式 freeze。
- [ ] 聚焦运行新测试及 reaction_mapping/method_policy/qm_input_writer 相关测试，完成规范检查后提交 `fix(ts): validate input identities and actual calculation methods`。

## Task 7：只读生产权限与委派边界（#108）

**Files:** Modify `cloudra/runtime_v2/policies/permission.py`, `cloudra/runtime_v2/commands.py`, `cloudra/runtime_v2/hub_bridge.py`, `cloudra/runtime_v2/subagent_bridge.py`, `cloudra/runtime_v2/adapters.py`, `cloudra/services/ts_pipeline_context.py`, `cloudra/runtime_v2/compute_notify.py`, `cloudra/tools/core/ts_pipeline_driver.py`; Create `tests/test_runtime_v2_production_permissions.py`; Modify `tests/test_runtime_v2_hub_bridge.py`。

**Interfaces:**
- `TsExecutionAuthority` 放在现有 ts_pipeline_context，包含项目/owner、有效 PermissionSet 与可信方法约束；构造来自 RuntimeCore，公开工具参数不能传入或修改。
- `require_ts_production(authority: TsExecutionAuthority, *, project_id: str, owner_id: str) -> None`；共享写入口与内部 `_submit_step` 调用，缺上下文 fail-loud。
- driver/通知/reconcile 接收 runtime 每次从当前 owner 投影的有效权限，不能只保存永久 authorized=true。

- [ ] 写 `test_readonly_role_cannot_submit_compute_or_mutate_ts`：通过实际 dispatch 调普通提交/prepare/resume/bash，拒绝发生在入队前；同角色 inspect 可用。
- [ ] 写 `test_readonly_peer_call_cannot_create_or_activate_producer`：覆盖新建 AgentHub peer、既有生产者 call、Launcher/Swarm 入口；只读证据交流仍可使用获准入口。
- [ ] 写 `test_text_assignment_does_not_grant_production_rights`：复核任务使用现有 explorer/effective permissions；工具 payload 和自然语言“授权”不提升权限。
- [ ] 写 `test_automatic_pipeline_uses_current_owner_permissions`：获准 owner 自动续接；权限收窄后不提交下一步，已运行 job 与锁保持，无 cancel_requested。
- [ ] 运行新测试与 hub bridge 场景确认失败，然后实现上述权限检查。
- [ ] 在 agent.spawn 公共命令和 hub 对既有 target 的 call 入口检查调用者有效能力，避免只检查 can_spawn 或只拦新 Agent。复用现有角色，不新建授权中心，不靠 message 文本分类生产意图。
- [ ] 构建角色/权限时选 explorer 承载只读复核；委派时不能放大 caller 的任务能力。用户通过可信控制面改变权限，Agent 不能通过传入角色补丁扩大权限。
- [ ] 在工具桥和 completion driver 构造受信上下文，内部 READY 绑定前再次核验；重启后从 runtime 已重放状态读取权限。
- [ ] 聚焦运行新测试、hub bridge、子 Agent 相关场景，完成规范检查后提交 `fix(runtime): enforce readonly production boundaries`。

## Task 8：移除 TS 时间预估，保持自动恢复与旧作业保活

**Files:** Modify `cloudra/tools/core/ts_process.py`, `cloudra/tools/core/ts_candidate_pipeline.py`, `cloudra/tools/core/ts_sampling_pipeline.py`, `cloudra/tools/core/geometry_optimization.py`, `cloudra/services/ts_pipeline_store.py`, `cloudra/services/exploration_budget_store.py`, `cloudra/tools/core/ts_pipeline_driver.py`, `cloudra/runtime_v2/compute_notify.py`; Create `tests/test_ts_execution_accounting.py`; Modify `tests/test_ts_pipeline_recovery.py`, `tests/test_conformer_model_budget.py`。

**Interfaces:**
- `TsExecutionLimits` 位于 Task 1 的 execution 分组，仅暴露已授权的 max_compute_actions/max_model_calls 及必要来源；无 CPU 小时估计。2026-10-18 用户要求移除所有 TS 任务的 max_interventions 上限，覆盖此前保留该字段的计划。
- TS 调既有 `reserve_actions`，适配为不含 estimated_cpu_hours 限制的非时间额度，保持既有计算账本绑定；不创建 `reserve_ts_actions` 新公共设施。
- `advance_process`、`reconcile_processes` 对不支持的输入格式返回明确隔离结果，并继续其他 process；不改 compute_jobs 生命状态。

- [ ] 写 `test_ts_all_subjobs_admit_without_time_estimates`：scan/path/candidate_hessian/candidate_gradient/TS/端点链无估计可入队，动作数仍计费且超已授权动作额度仍拒绝。
- [ ] 写 `test_actual_usage_is_recorded_and_unknown_is_not_zero`：真实运行时长与分配核时字段分明；没有测量的 actual 不补零。
- [ ] 写 `test_reconcile_isolates_old_record_and_keeps_active_job_alive`：混合旧/新记录，新记录续接，旧记录不重交、不标 failed、不取消，持锁 QM 保活。
- [ ] 写 `test_duplicate_completion_and_restart_do_not_repeat_work`：driver 幂等绑定、回执与权限上下文恢复后仍有效。
- [ ] 运行新测试与 recovery 测试确认失败；移除所有 TS public/current input 的 compute_estimates 和 estimated_cpu_hours 字段及相关缺估计阻塞。
- [ ] 保留共享预算服务其他调用者语义；TS 子适配的参数删除而非填零，保留动作/模型计数和实际 settlement。
- [ ] 旧格式处理只识别并隔离，不加入转换 shim；异常隔离不能吞掉新格式 bug，把格式不支持与损坏记录区分报告。
- [ ] 聚焦运行 accounting/recovery/model budget 测试，完成规范检查后提交 `refactor(ts): remove estimated-time admission and preserve recovery`。

## Task 9：接口整合、文档和四个 issue 验收

**Files:** Modify `tests/agent_scenarios.py`, `tests/test_runtime_v2_ts_workflow_scenarios.py`, `tests/test_runtime_v2_guidance.py`, `cloudra/runtime_v2/policies/guidance.py`, `cloudra/skills/dft-calculation/SKILL.md`, `cloudra/skills/dft-calculation/references/ts-search-playbook.md`, `cloudra/skills/dft-calculation/references/mechanism-elucidation-sop.md`, `docs/TS_PROCESS_SOP.md`。

**Interfaces:** Consumes 所有任务产生的工具/schema/状态视图；最终 public tools 为 ts_prepare/ts_resume/ts_inspect，方法分组与 next 信息一致。

- [ ] 在 agent_scenarios 注册 `ts_prepare_once_auto_complete`、`ts_failed_scan_repair_same_run`、`ts_readonly_inspection` 三个零真实 key 场景，断言事件、字段持久化、作业数和 run_id。
- [ ] 运行场景确认缺失/旧指引的失败后更新工具说明、guidance 和相关技能。删除空 resume 查询、完成后手动 resume、无 status 接口、旧扫描平铺字段说明。
- [ ] 把 docs/TS_PROCESS_SOP.md 更新为已实现行为；已有科学阈值和流程验收口径不变，不把本次 fixture 验证说成真实引擎验收。
- [ ] 运行 `uv run python -m compileall -q cloudra tests`。
- [ ] 运行 `uv run ruff check cloudra tests`。
- [ ] 运行任务中涉及的 TS/permission/method/input/compute_notify 聚焦测试，加 `tests/test_no_sync_on_loop.py`；以最终文件清单明确列出，不运行 `pytest tests/`。
- [ ] 搜索已删除字段/旧说明的引用，确认生产代码没有 legacy 残留，历史 spec/plans 不重写。
- [ ] 对照 spec §10 和各 issue 关闭条件形成验收表：测试文件/测试名、实际输出、任何真实引擎未验证项分别记录。
- [ ] 提交 `docs(ts): document grouped inputs inspection and automatic continuation`，进行所选执行方式要求的独立最终审查，修复有根据的反馈并仅重跑受影响检查。

## 执行方式与交付边界

推荐本会话直接实施（Native）：任务之间共享 schema、状态和证据接口，依次实现能减少上下文重复与接口偏差；完成后做独立最终审查。若选择逐任务子 Agent 实施，则按 subagent-driven-development 的实现/审查门执行，不并行改写共享状态机文件。

执行前使用 using-git-worktrees 技能检查已有附件并建立或复用隔离 worktree；起点须包含已批准 spec 和本计划。保护工作区现有 `gold_compute/supplement_20261002/`，不得纳入本任务提交。

任务按 1→2→3→4→5→6→7→8→9 执行。每次提交只包含相关代码、测试和说明。受信权限、科学方法约定及在途作业边界发现与规格冲突时，保留已完成工作并报告具体冲突；不擅自引入新的科学裁决。
