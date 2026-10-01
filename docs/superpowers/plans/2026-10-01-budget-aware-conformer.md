# Cloudra 构象分区与按预算选择计算 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本计划默认由当前执行者逐项完成；需要多 agent 执行时由用户选择。

**Goal:** 保存可解释的构象选择空间，让程序和 AI 按证据与预算选择新计算，并在失败后复用已有结果接续。

**Architecture:** 在现有生成器与 TS 执行链之间新增候选档案、结构分区和确定性选择层。compute.db 保存候选/动作/预算预留，文件保存不可变几何与可读卡片。AI 只提出受校验的决策，由既有执行账本提交；预算控制新动作，不限制运行中的引擎寿命。

**Tech Stack:** Python >=3.11、现有 Pydantic、SQLite、RDKit 与数组能力、既有 runtime/compute 入口；无新依赖。

**Spec:** [构象选择补充设计](../specs/2026-10-01-budget-aware-conformer-design.md)；执行层依赖 [TS 自动化设计](../specs/2026-10-01-ts-prepare-autode-design.md) 和 [现有 TS 计划](2026-10-01-ts-prepare-autode.md)。新补充设计决定计算对象与顺序，原设计决定已选任务的后端及可靠执行。

## Global Constraints

- 不增加 `autode` 安装、运行时 import、CLI 调用或隐式下载。上游参考版本固定 `e7e71b33d8659fe921c16f877f9c1adddc4f9cff`。
- 无新依赖；不把上游的默认候选数、计算池、优化次数或化学模型当作产品策略。
- 不在 Mac 跑 QM，不停止现有计算，不重启承载正在运行 agent 的服务，不启动正式 benchmark。
- 预算不足只阻止新提交，不取消已接受或运行中的任务；没有显式预算不暗设搜索上限。
- 原设计的 xTB 优先只作用于已经选定的优化任务，不要求全候选逐个优化。缺少该执行层时不伪造实现。
- 方法、溶剂、电荷、自旋、身份、能垒参考态和科学验收不能由 AI 或预算隐式改变。
- 保留所有生成过的候选及失败来源；归类/展示筛减不删除档案。原始候选不代表构象空间完整。
- 仅操作本任务文件，不清理当前工作区改动。实施时使用隔离工作树，明确带入所需的已审查基础改动。
- 提交按任务限定文件；本次只交付文档，不自动开始实施、提交、推送或部署。

## Review Focus

1. 相同 SMILES 的不同立体或质子化身份不被合并；对称重编号不产生虚假新区。Task 1/2。
2. 二面角 ±180°、共线原子、缺失内坐标不能造成错误分区或伪造标签。Task 2/4。
3. 优化后的候选合并/迁移区域，仍能追溯父候选、旧分区、实际作业和失败。Task 1/2。
4. 并发选择、响应丢失与重启不重复提交/扣费，也不释放活跃作业的预算。Task 5/7。
5. 预算不足、模型调用失败和没有可比能量时，输出未完成/可回退证据，不偷偷降验收或换方法。Task 4/5/6/7。

---

## 范围和交付顺序

Task 1–4 交付独立可用的构象档案/分区/卡片，仍兼容原工具输出。Task 5–7 接入预算与 TS/AI 选择，依赖原 TS 计划的原子作业绑定和事件推进。Task 8 提供离线对照及远端验收协议；不以离线结果声明科学收益。

当前 `ts_process.resume` 仍有空 adjustment 推进和提交后禁止 guidance 修改逻辑；原 TS 新设计尚不是代码事实。Task 7 必须核对原计划实现状态，不能仅增加候选字段就宣称可靠恢复完成。

暂不移植 RR/CRF、不搜索 TS 外围构象、不开发全空间可视化、不改变已有科学判据。结构分区容差是版本化工程初值，后续依据对照数据校准。

## 文件与类型边界

| 文件 | 职责 |
| --- | --- |
| `cloudra/tools/core/conformer_catalog.py`（新增） | 可校验候选/能量/资格/谱系模型与规范摘要 |
| `cloudra/services/conformer_store.py`（新增） | compute.db 中候选与分区版本存取 |
| `cloudra/tools/core/conformer_regions.py`（新增） | 内坐标定义、测量和确定性分区 |
| `cloudra/tools/core/conformer_cards.py`（新增） | 可追溯卡片与分页摘要 |
| `cloudra/tools/core/conformer_selection.py`（新增） | 默认排序、失败分类、AI 决策校验 |
| `cloudra/services/exploration_budget_store.py`（新增） | 预算、动作、原子预留、结算/恢复 |
| `cloudra/tools/core/complex_assembly.py`（现有） | 保留定向采样，提供按需独立片段采样 |
| `cloudra/tools/core/ts_process.py`、`cloudra/tools/Chemtool/ts_search_process.py`（现有） | 候选选择和 blocked/resume 接口 |

类型放在负责模块并显式导入，禁止未校验 arbitrary dict 和 pickle。ID 按稳定物种/原子身份、坐标摘要和生成来源生成；不依赖能量排序或文件位置。文件引用核对项目/所有者/摘要。

### Task 1: 候选档案与优化谱系

**Files:** Create `cloudra/tools/core/conformer_catalog.py`, `cloudra/services/conformer_store.py`, `tests/test_conformer_catalog.py`; Modify `cloudra/persistence/database.py`。

**Interfaces:**
- `CandidateRecord`：schema_version、candidate_id、species_key、atom_ids、fragment_ids、geometry_ref/hash、generator/parameters/seed、parent_id、qualification、state、energies、job_ids。
- `EnergyObservation`：value/unit/kind、method_fingerprint、charge/multiplicity/solvent/reference、convergence、artifact_ref；缺能量用缺失值，不用 0。
- `put_candidate(db: ComputeDB, record: CandidateRecord) -> str`：重复同摘要返回原 ID，冲突拒绝。
- `list_candidates(db: ComputeDB, catalog_id: str) -> list[CandidateRecord]`。

- [ ] 写失败测试 `test_candidate_id_survives_move_and_retry`、`test_optimization_child_preserves_parent`、`test_failed_candidate_keeps_artifacts`、`test_identity_variants_stay_separate`、`test_cross_method_energy_not_comparable`：分别断言重复写入只有一条、子结果不覆盖父坐标、失败无伪零能量、身份集合隔离、混合方法不能产生共同相对能量。
- [ ] 运行 `pytest tests/test_conformer_catalog.py -q`，确认因新契约缺失失败。
- [ ] 实现模型和同库表，复用现有 migration/短事务模式；保存文件前后摘要并拒绝引用冲突。
- [ ] 重跑该测试文件，要求通过；验证旧数据库和已有 compute_jobs 不被重写。
- [ ] 仅提交本任务文件，提交信息 `feat: preserve conformer candidates and optimization lineage`。

### Task 2: 内坐标描述与结构分区

**Files:** Create `cloudra/tools/core/conformer_regions.py`, `tests/test_conformer_regions.py`, `tests/fixtures/conformer_selection/README.md`, `tests/fixtures/conformer_selection/geometries.json`; Modify `cloudra/services/conformer_store.py`。

**Interfaces:**
- `DescriptorSpec`：kind（distance/angle/dihedral/ring/fragment_pose）、stable_atom_ids、unit、tolerance、source、required；结构描述符不包含能量。
- `RegionConfig`：version、descriptor_specs；默认容差 0.5 Å/15°/30°，来源 `engineering_initial`。
- `DescriptorRecord`：candidate_id、测量值/单位、缺失原因、资格引用；`RegionSnapshot`：catalog_id、revision、config、region_id 到 representative_id/member_ids 的映射、previous_revision/region_mapping。
- `describe_candidate(candidate: CandidateRecord, specs: list[DescriptorSpec]) -> DescriptorRecord`。
- `partition_candidates(candidates: list[CandidateRecord], config: RegionConfig) -> RegionSnapshot`；snapshot 记录版本、代表/成员、缺失描述、旧新区域映射。
- `build_descriptor_specs(graph: object, reaction_atom_ids: list[str], explicit: list[DescriptorSpec]) -> list[DescriptorSpec]`：既有 RDKit 图，稳定身份，显式描述优先，补充可旋转键二面角。

- [ ] 写失败测试：`test_periodic_dihedral_distance` 断言 179°/-179° 差 2°；`test_local_reaction_difference_survives_small_global_rmsd`；`test_symmetry_relabel_preserves_region`；`test_missing_or_degenerate_descriptor_never_merges_silently`；`test_repartition_keeps_old_snapshot`；`test_energy_change_does_not_change_region`；`test_optimized_children_share_region_keep_two_parents`。
- [ ] 运行 `pytest tests/test_conformer_regions.py -q`，确认新契约失败。
- [ ] 实现周期距离、最大归一化差和稳定代表聚类，采用补充设计 §3 的顺序/平局规则。近重复标注不删除候选；不支持的描述类型明确报告缺失。fixture 标明合成坐标/预期几何关系，不冒充 QM 数据。
- [ ] 重跑测试并验证乱序输入结果一致、距离窗口资格未被聚类容差放宽。
- [ ] 仅提交本任务文件，提交信息 `feat: partition conformers using reaction relevant coordinates`。

### Task 3: 在既有生成器筛减前保存候选，并补充独立取向采样

**Files:** Modify `cloudra/tools/Chemtool/conformer_search.py`, `cloudra/tools/core/preorganization.py`, `cloudra/tools/core/complex_assembly.py`; Modify `tests/test_conformer_search.py`, `tests/test_preorganization.py`, `tests/test_complex_assembly.py`; Create `tests/test_conformer_catalog_adapters.py`。

**Interfaces:**
- `CandidateSink = Callable[[CandidateRecord], None]`，生成/每次优化结束调用；`search_guided` 和 `assemble` 增加可选 keyword `candidate_sink=None`，旧调用兼容。
- `Placement` 定义于 complex_assembly：positions、fragment_transforms、seed、sampling_method、qualification；坐标单位 Å，角度与旋转表示明示。
- `sample_independent_placements(mol: object, groups: list[list[int]], *, seed: int, count: int, parameters: AssemblyParameters) -> list[Placement]`；`Placement` 记录坐标、每片段旋转/平移、seed 和采样方法。
- 构象工具新增可选 `catalog_mode: Literal['legacy','regions']='legacy'`；regions 模式输出 catalog/region/card 引用，旧 selected ensemble 字段保留为视图。

- [ ] 写失败测试 `test_archive_precedes_energy_and_rmsd_filters`（高能新区及重复成员都在档案）；`test_raw_geometry_saved_before_mmff`（未优化父候选仍在）；`test_guided_rejected_candidates_keep_reason`；`test_legacy_output_unchanged`；`test_three_fragments_have_independent_rotations`；`test_independent_sampler_reproducible_and_no_collision`。
- [ ] 运行 `pytest tests/test_conformer_catalog_adapters.py tests/test_complex_assembly.py -q`，确认新增断言失败。
- [ ] 在筛减前挂接 sink，生成和优化分别记录；CREST 可记录软件实际返回的 ensemble，不宣称取得软件内部已删除结构。独立取向仅按显式补充请求调用，不默认叠加全部采样预算；保留现有碰撞、片内几何和约束检查。
- [ ] 运行本任务四个测试文件及 `tests/test_structure_builder.py`，要求既有语义回归通过。
- [ ] 仅提交本任务文件，提交信息 `feat: archive generated conformers and supplement complex sampling`。

### Task 4: 可追溯语义卡片与默认选择

**Files:** Create `cloudra/tools/core/conformer_cards.py`, `cloudra/tools/core/conformer_selection.py`, `tests/test_conformer_cards.py`, `tests/test_conformer_selection.py`。

**Interfaces:**
- `build_region_cards(snapshot: RegionSnapshot, candidates: list[CandidateRecord], attempts: list[AttemptEvidence]) -> list[RegionCard]`。
- `RegionCard` 定义于 conformer_cards：region_id、revision、candidate_ids、measurements/labels/evidence_refs、comparable_energies、qualification、attempts、unknowns、cost_estimates；不包含无证据的势垒推断。
- `select_default(cards: list[RegionCard], context: SelectionContext) -> SelectionDecision`：结果为 action/candidate_id/region_id/evidence_refs/reason，或 blocked。
- `validate_selection(decision: SelectionDecision, context: SelectionContext) -> SelectionDecision`。
- `AttemptEvidence`：动作/阶段/作业/失败类别/原始证据；`SelectionContext`：所有者、声明摘要、卡片版本、已有动作、方法、可用预算。新字段强类型定义于 selection 模块。

- [ ] 写失败测试 `test_label_links_to_measurement`、`test_cards_expose_missing_energy`、`test_pagination_lists_omitted_regions`、`test_selects_unattempted_region_before_repeat`、`test_energy_orders_only_comparable_candidates`、`test_ambiguity_returns_decision_needed`、`test_infrastructure_failure_reuses_job`、`test_same_input_failed_attempt_not_requeued`。
- [ ] 运行 `pytest tests/test_conformer_cards.py tests/test_conformer_selection.py -q`，确认新增契约失败。
- [ ] 实现资格优先、未尝试区域覆盖优先和同方法能量次序；无可比能量按窗口偏差/稳定 ID 排序。首次不同进攻面/质子转移声明无法确定时 blocked；标签不得推导势垒或机理。摘要显示区域总数和遗漏 ID，不把低能截断当全空间。
- [ ] 重跑测试；断言每个选择理由可回到当前版本的真实卡片证据。
- [ ] 仅提交本任务文件，提交信息 `feat: expose semantic conformer cards and deterministic selection`。

### Task 5: 新动作预算预留与恢复

**Files:** Create `cloudra/services/exploration_budget_store.py`, `tests/test_exploration_budget_store.py`; Modify `cloudra/persistence/database.py`, `cloudra/services/compute_store.py`。提交绑定复用原计划 `ts_pipeline_store.py`，存在后再接入，禁止另建队列。

**Interfaces:**
- `ExplorationBudget`：source、optional max_compute_actions/estimated_cpu_hours/max_model_calls；无配置为缺失，不能填默认限制。
- `CostEstimate`：action_kind、cpu_hours、source、uncertainty、model_cost；未知为缺失。
- `Reservation`：reservation_id、process_id、decision_id、action_keys、reserved_cost、state；`ActualCost`：job_id、terminal_state、allocated_cpu_hours、measurement_source、model_calls/tokens、optional monetary_cost。模型量度缺失要明确，不能写 0；按分配核数乘实际运行时长计 CPU 小时并记录口径，不冒充 CPU 使用率测量。
- `reserve_actions(db: ComputeDB, *, process_id: str, decision_id: str, estimates: list[CostEstimate]) -> Reservation`：原子 all-or-none。
- `bind_reserved_job(db: ComputeDB, *, reservation_id: str, action_key: str, stage_job_payload: dict) -> int`：同事务预算消费与已有 stage/job 绑定；payload 经原 TS 契约校验。
- `settle_action(db: ComputeDB, *, action_key: str, actual: ActualCost) -> None`；`reconcile_reservations(db: ComputeDB, process_id: str) -> None`。

- [ ] 写失败测试 `test_two_connections_cannot_exceed_budget`、`test_duplicate_decision_reserves_once`、`test_ready_job_counts_as_accepted`、`test_failed_job_retains_cost`、`test_active_job_reservation_not_released_on_restart`、`test_unknown_cpu_estimate_blocks_under_cpu_cap`、`test_budget_exhaustion_never_kills_job`、`test_validation_chain_shortfall_blocks_before_ts`。
- [ ] 运行 `pytest tests/test_exploration_budget_store.py -q`，确认新增契约失败。
- [ ] 实现显式预算/套餐来源、事务预留与实际/估计分账。作用域覆盖优化/梯度/路径/TS/验证子动作及模型调用；READY 即占额度。验证链先预留已知动作，未知优化步数披露不能保证总成本；原生计算参数不被预算覆盖。
- [ ] 重跑测试及已有 compute store/准入测试；断言没有新增 terminate/kill、Slurm 时间限制、maxiter/nrun 注入。
- [ ] 仅提交本任务文件，提交信息 `feat: reserve exploration budget without cancelling accepted work`。

### Task 6: AI 决策契约与受控回退

**Files:** Modify `cloudra/tools/core/conformer_selection.py`, `cloudra/tools/Chemtool/ts_search_process.py`, `cloudra/prompts/small_mol.md`, `cloudra/skills/dft-calculation/references/ts-search-playbook.md`; Create `tests/test_conformer_ai_decision.py`。

**Interfaces:**
- `SelectionDecision.action` 仅允许 `select_candidate/refine_representative/supplement_sampling/propose_adjustment/stop`；附 decision_id、catalog/partition_revision、声明摘要、理由和 evidence_refs。
- `validate_selection` 拒绝未知/外项目候选、旧卡片、缺理由、已失败相同输入、不支持采样、方法/身份/硬预算越权。
- tool blocked 输出添加 `decision_needed`、卡片索引、合法动作、预算/缺失信息；工具不直接调用新模型服务，由既有 agent 获取证据并通过 resume 提交决定。

- [ ] 写失败测试 `test_rejects_stale_or_foreign_candidate`、`test_ai_cannot_raise_hard_budget_or_change_method`、`test_reason_requires_current_evidence`、`test_model_failure_preserves_catalog_and_process`、`test_model_budget_counts_retry`、`test_normal_stage_does_not_request_ai`、`test_stop_returns_incomplete_not_scientific_success`。
- [ ] 运行 `pytest tests/test_conformer_ai_decision.py -q`，确认新增契约失败。
- [ ] 实现决策校验和 blocked 证据 payload，更新提示词以选择已有区域/指出覆盖缺口；AI 输出只能成为待执行的结构化动作，不执行任意 shell 或无记录提交。调用失败保留 blocked，并沿现有 runtime 记录 token/调用来源，不无限重试。
- [ ] 重跑测试并核对与现有手动 TS/IRC 禁令一致，不能从新动作绕过准入。
- [ ] 仅提交本任务文件，提交信息 `feat: validate evidence based agent conformer decisions`。

### Task 7: 候选级 TS 接续与幂等绑定

**Files:** Modify `cloudra/tools/core/ts_process.py`, `cloudra/tools/Chemtool/ts_search_process.py`, 原计划的 `cloudra/services/ts_pipeline_store.py`、`cloudra/tools/core/ts_pipeline_driver.py`; Create `tests/test_ts_candidate_continuation.py`; Modify `tests/test_ts_process.py`。

**Prerequisite:** 原 TS 计划的阶段/作业原子绑定、异步优化入口、自动推进和跨声明复用已实现并通过测试。未实现时将此任务记录为依赖未满足，不用文件存在或旧 `resume({})` 冒充可靠执行。

**Interfaces:**
- `TsProcessRecord` 增加 catalog_id、partition_revision、selected_candidate_id、selection_decision_id、budget_ref。
- `TsAdjustment` 增加 optional `selection_decision: SelectionDecision`，不复用旧 `max_interventions` 或 `path_refinement_runs` 表示新预算。
- 阶段键含 candidate_id/input hash 和动作 ID；仍使用原 TS 账本与声明版本。选择返回 continuation_stage、invalidated_stage_keys、reused_job_ids、reservation_id。

- [ ] 写失败测试 `test_switch_seed_keeps_build_map_and_old_attempt`、`test_endpoint_only_retry_keeps_ts_frequency_other_endpoint`、`test_duplicate_resume_creates_one_job_and_one_charge`、`test_budget_change_only_preserves_geometry`、`test_waiting_process_resume_does_not_submit`、`test_restart_recovers_bound_candidate`、`test_budget_exhaustion_does_not_pass_verdict`。断言实际作业 ID、提交次数和保留文件，不只断言返回 stage。
- [ ] 运行 `pytest tests/test_ts_candidate_continuation.py -q`，确认新增契约失败。
- [ ] 替换 `_build` 对 `guided.candidates[0]` 的隐式决定为明确候选选择/引用；选定任务按原设计后端执行。切换反应物种子使实际依赖的路径及后续阶段失效，保留未变组分、图身份/映射及历史分支；候选端点不同则不得复用错误身份结果。声明调整与候选切换分别计算失效范围。
- [ ] 重跑新增测试、`tests/test_ts_process.py`、`tests/test_manual_ts_submission.py` 及原 TS ledger/driver 测试，排除 `real_xtb`；验证普通完成不唤醒 AI、重复事件不收费/不重交。
- [ ] 仅提交本任务文件，提交信息 `feat: resume TS workflows from selected conformer checkpoints`。

### Task 8: 离线回放、成本对照与 opt-in 验收

**Files:** Create `tests/test_conformer_policy_replay.py`, `tests/fixtures/conformer_selection/replay_cases.json`, `docs/benchmarks/conformer-selection-protocol.md`; Modify `docs/TS_PROCESS_SOP.md`, `cloudra/tools/Chemtool/conformer_search.py`。

**Interfaces:**
- 离线回放接收同一候选档案、预算、固定事件与决策记录，输出动作数/复用数/模型调用/实际或估计成本/区域覆盖/未完成原因。
- 基线分别是当前代表选择（真实代码行为）、区域确定性策略、区域加固定 AI 决策回放。无已测分支返回 unknown，不能推算科学结果。
- opt-in 仅显式 `catalog_mode='regions'` 或 TS 显式候选策略启用；不悄悄改变现有默认行为，不因此开放手动 TS/IRC。

- [ ] 写失败测试 `test_replay_has_equal_budget_and_evidence`、`test_unmeasured_branch_remains_unknown`、`test_llm_cost_included_separately`、`test_same_verdict_standard_across_policies`、`test_legacy_mode_does_not_enable_ai_or_new_spend`；fixture README 记录来源/许可、合成或真实、方法及可信边界。
- [ ] 运行 `pytest tests/test_conformer_policy_replay.py -q`，确认新增契约失败。
- [ ] 实现离线回放与协议。协议列真实远端矩阵：柔性单分子、反应局部差异、两/三组分、质子转移、身份保持困难、低级别非收敛；固定方法/节点/预算/验收，记录实际 CPU 小时、模型 token/费用、失败成本及复用。远端执行另行授权安排；不得在本任务生成虚假实测日志。
- [ ] 执行下面离线回归命令，要求全部通过；检查 skipped 原因，不把缺 RDKit 等依赖导致的跳过视为完整验收：

  ```bash
  pytest tests/test_conformer_catalog.py tests/test_conformer_regions.py tests/test_conformer_catalog_adapters.py tests/test_conformer_cards.py tests/test_conformer_selection.py tests/test_exploration_budget_store.py tests/test_conformer_ai_decision.py tests/test_ts_candidate_continuation.py tests/test_conformer_policy_replay.py tests/test_conformer_search.py tests/test_preorganization.py tests/test_complex_assembly.py tests/test_structure_builder.py tests/test_ts_process.py tests/test_manual_ts_submission.py -m 'not real_xtb' -q
  ruff check cloudra/tools/core/conformer_catalog.py cloudra/tools/core/conformer_regions.py cloudra/tools/core/conformer_cards.py cloudra/tools/core/conformer_selection.py cloudra/services/conformer_store.py cloudra/services/exploration_budget_store.py
  git diff --check
  ```

  原 TS ledger/driver 与 compute store/准入回归使用原计划已落地的测试文件；实施者在 Task 7 依赖核对时记录实际文件名和运行结果。现有改动模块亦运行 ruff，仅处理本任务引入的问题，不顺手清理其他改动。
- [ ] 更新 SOP 标明 opt-in、未完成状态、候选卡片与恢复语义；仅提交本任务文件，提交信息 `test: compare conformer selection cost with reproducible evidence`。

## 完成标准与交接

- 所有已生成候选可追溯；高能独立结构区域不会因展示筛减消失；不同身份/不同能量方法不混合。
- AI 可以在计算前或失败后选择候选，决定被验证并记录；程序仍可独立完成无歧义的默认选择。
- 预算、作业和阶段绑定幂等；恢复能核对旧作业 ID，已运行计算不被预算或通信超时取消。
- TS 科学验证不因预算降级；不足时可解释地报告未完成。
- 离线机制验收与真实科学收益分开。只有真实对照才能支持“省算力”的产品结论。

实施方式待用户选择；本次文档交付不启动代码实施。建议逐项在当前会话执行，先完成独立可验收的 Task 1–4，再核对原 TS 执行层依赖并进入 Task 5–7。

## 实施期间范围修订：统计启发划区

用户已明确统计检验用于指导拆区，而不是固定分区后的附加标签。Task 2 当前实现保留为对照策略；Task 4 卡片须披露该算法来源，不提供未经验证的 p 值或“统计显著”标签。统计策略另行定义反应语义描述符选择、候选拆分搜索、组内波动、选择偏差校正、周期变量和采样批次模型，再做独立离线校准任务。该方向不阻止候选档案、预算和受控决策契约实施；不得以当前 Task 2 完成声称统计划区已完成。


## 2026-10-01 实施状态（工作树，未提交）

- Task 1/2/4：候选档案、身份、谱系、固定容差对照和卡片已实现；新增探索性全搜索重采样评分/稳定性与显式拆区接受，无正式 p 值/生产阈值。
- Task 3：RDKit 原始归档、多组分独立放置、逐组分生成/优化、guided/assembly 失败来源和实际返回 CREST 帧适配器已实现。CREST regions 预算入口暂未开放，不宣称取得上游内部删除结构。
- Task 5/6：预算、READY/阶段原子绑定、实际账本成本、显式选择校验和模型物理请求/重试预算接既有 runtime；补采样使用同一计算队列，未知资格保留。
- Task 7：系统自动推进/项目加载 reconcile、声明/候选分支、重复请求、独立端点重试、预算单独下调、统计子候选分区续接有 focused fixture 验证。选中 native xTB Opt/path 排队；窗口约束优化前置依赖已补充 Cartesian RFO/KKT 与同账本逐点评估，含实际 Hessian/梯度输入、预算、数值状态和崩溃恢复。未移植完整 autodE DIC；原 TS 计划的其余范围仍不能因此被声明全部完成。
- Task 8：三策略共享预算/证据/验收的合成回放和远端协议；真实科学收益、部署未执行。
- 扩展执行链已完成一次 GPT-6.1-sol ultra fresh review 和修复；新增数值前置依赖经解析参考格式、解析导数和多维解析势能 fixture 验证。最后针对性回归结果见 .superpowers/sdd/2026-10-01-budget-aware-conformer/progress.md。
- 用户指定高级 reviewer 用 GPT-6.1-sol ultra，不使用 Astra。

## 计划交付范围核对

Task 1–8 的本地实现已接通，包括不可变候选、全部返回选择归档、语义卡片、预算/模型物理请求计费、结构化回退、自动推进与候选续接、探索性统计拆分及合成回放。逐点评估恢复使用既有账本，无额外队列。提交步骤按项目约定未执行，改动留在独立工作树供审查。统计生产阈值未设置；实际科学收益与远端部署属于协议后续验收，不能从本地 fixture 推断。完整原 TS 计划仍有独立范围，见其前置依赖进度记录。
