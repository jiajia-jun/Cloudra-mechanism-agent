> 历史验收记录。当前接口、流程与科学要求统一维护在 [TS 指南](../TS_PROCESS_SOP.md)。下文“当前”指原记录更新时点。

# TS 状态机实现验收（更新至 2026-10-18）

当前入口和科学验收口径以下表及[TS 流程说明](../TS_PROCESS_SOP.md)为准。工具调用成功、工作流结束、工程回归通过与真实计算的科学验收分别记录；本次文档更新没有运行新的 ORCA/Gaussian 全链，不把后文的历史 fixture 测试数字算作本轮真实引擎验收。

## 当前接口与验收口径

| 项目 | 当前行为 | 实现依据 |
| --- | --- | --- |
| 创建与修订 | `ts_prepare` 只接收分组科学 `input`；`ts_resume` 接收 `run_id`、可省略的 `changes`（默认空）和必填 `reason`。调用身份和并发修订号由程序绑定，Agent 不填写 `request_key` 或 `expected_revision` | `cloudra/tools/Chemtool/ts_search_process.py` 的公共 schema、`_request_key` 与 `revise_run` |
| 只读状态 | `ts_inspect` 只接收 `run_id`；返回权威状态、当前结构、方法、作业与失败记录，不推进计算。`details_path` 只在导出与当前修订/结构一致时提供 | `cloudra/tools/core/ts_state_view.py` |
| 当前记录 | 内部格式为 7；旧记录保持只读隔离，不自动迁移科学输入或触碰既有作业。格式号属于程序内部协议 | `TsProcessRecord`、`_read_resume_record`、`build_process_view` |
| 失败与修订 | 保留同一 run 的旧尝试；可提交新的科学输入，也可用空 `changes` 重试。公共输入已无 `scan_recovery`。仅排队中的作业允许修订并撤回旧队列；正在执行或等待取消收尾的作业阻止修订 | `TsResume`、`ts_revision.py`、`services/ts_pipeline_store.py` |
| 停止 | `ts_stop` 接收 `run_id` 和 `reason`。撤回排队作业，向运行作业写入 `cancel_requested` 由执行端安全收尾；停止工作流不等于科学失败 | `TsStop`、`ts_process.stop` |
| 科学结论 | `is_success` 仅表示工具调用成功；只有 `result.verified=true` 才表示通过已记录的科学检查。TS 优化须收敛，频率须一虚频，目标结构/原子对应需成立 | `TsProcess_output_schema`、`TsProcessView` 与 `ts_process.py` |
| IRC 方向 | 同一已验证 TS 的真实双向 IRC 外帧分别经收敛优化到身份正确的零虚频极小值，即接受方向证明。IRC 本身无需跑到极小值；几何区间失败或无法判断只报告警告，不能推翻已成立的真实端点链 | `cloudra/tools/core/irc_evidence.py::_endpoint_optimization_proof` |
| 编号与不可变证据 | 当前结构/反应引用为 1-based；扫描/冻结参数按相应引擎编号（ORCA 0-based，Gaussian/xTB 1-based）。新输入在执行边界转换，历史输入/日志保持原编号与字节 | `TsPrepare_input_schema`、`TsResume_input_schema`、`normalize_ts_input_atoms` |
| 方法与额度 | 每阶段显式声明方法；Benchmark 另受当前题目 MethodPolicy 约束，普通项目不凭旧样例套白名单。介入次数只累计、不设置 TS 介入次数上限；预算声明仍按实际动作/模型调用记录 | `ts_inputs.py`、`ts_revision.py`、`ts_process.py` |

当前 50 题及原始证据的实际到货/缺件情况见[参考状态](../../gold_compute/queue_20261018/REFERENCE_STATUS.md)与[Drive 交付说明](../../gold_compute/evidence/REPRODUCE.md)。这些归档不等于在本文重新完成真实引擎验收。

## 历史工程验收记录（2026-10-02）

以下保留当时 `codex/ts-state-machine` 分支的回归、审查与集成记录，不能作为现行公共入参说明；其中调用者填写幂等键、显式修订号和扫描恢复对象等旧要求，已由上表对应行为取代。原有测试通过数字仅描述当时运行，当前全套状态以最新 CI 为准。

### 四个 issue

| Issue | 本次修复 | 直接回归证据 | 边界 |
| --- | --- | --- | --- |
| #108 | 普通计算/TS/bash/公共 spawn/新旧 Hub call/Launcher 均不能放大只读能力，证据 post 不唤醒 producer；自动提交读取当前 owner 权限 | test_runtime_v2_production_permissions：readonly_role_cannot_submit_compute_or_mutate_ts、readonly_peer_call_cannot_create_or_activate_producer、public_spawn_cannot_amplify_readonly_parent_or_peer、readonly_evidence_post_delivers_without_waking_producer、automatic_pipeline_uses_current_owner_permissions | 原有 QM 和锁不被取消；用真实 runtime/dispatch 测，不仅 mock TS |
| #109 | 元素排列不能清除图身份/对称绑定问题；实际种子在优化前、搜索前、提交前核验，绑定摘要和输入版本；最终端点证明保留 | test_ts_input_evidence：element_consistent_map_cannot_clear_identity_mismatch、explicit_map_keeps_ambiguous_concrete_binding_inconclusive、identity_is_rechecked_after_geometry_source_changes、conformer_identity_checked_before_optimizer_submission；test_ts_process 的端点/立体化学/方向区间用例 | 构造绑定来自现有 atom_identity；外部未标记对称结构需补来源 |
| #110 | 第一点 SHARK/临时目录失败不能只改点数重跑；恢复绑定实际失败和相关权威成功证据，同 run 修订历史、回执和额度保留 | test_ts_resume_transitions：failed_scan_point_count_only_does_not_requeue、unbound_recovery_artifact_cannot_authorize_retry、environment_repair_evidence_allows_same_input_new_attempt；test_runtime_v2_ts_workflow_scenarios：ts_failed_scan_repair_same_run | 回归使用第一点故障 fixture；没有重现真实远端 SHARK 环境 |
| #111 | 分组科学方法独立；入 READY 前核验实际原生任务/方法/完整关键词/溶剂块/电荷/自旋及可信项目契约，未知来源暂停 | test_ts_method_contract：unauthorized_method_and_missing_keyword_block_before_ready、authorized_semiempirical_scan_differs_from_formal_method、native_blocks_and_gaussian_links_are_all_checked、undeclared_frequency_block_and_gaussian_trailing_settings_are_differences | 测试涵盖原生输入语法及现有写入器；真实引擎验收仍待进行 |

### 当时 Spec §10 行为映射

1. 单次 prepare 自动七步、重复通知幂等：test_ts_stage_inputs / test_runtime_v2_ts_workflow_scenarios。
2. 同 run 更换路线/方法、端点独立恢复和失败历史：test_ts_resume_transitions / test_ts_revision_store / test_ts_pipeline_recovery。
3. prepare/resume 共用字段和部分替换规则、成功状态不可写入：test_ts_inputs / test_ts_revision_store。
4. 独立阶段方法、guess 判别分支原子替换、缺配置 checkpoint：test_ts_inputs / test_ts_stage_inputs。
5. inspect 只读快照、权威 revision 与导出滞后、只读审查：test_ts_inspect / test_ts_search_process_tools / Agent 场景。
6. stale revision、跨项目、幂等键冲突和在途禁止改动：test_ts_revision_store / test_ts_pipeline_driver。
7. 无时间预估准入、未知实测不补零、实际模型请求/梯度动作计数：test_ts_execution_accounting / test_conformer_model_budget / test_geometry_optimization。
8. 各 issue 的生产入口及科学证据回归：见上表。
9. 运行作业与锁在拒绝/权限收窄/旧格式隔离中保持：test_runtime_v2_production_permissions / test_ts_execution_accounting。
10. 旧格式隔离不影响新流程：test_ts_execution_accounting / test_ts_pipeline_driver。

### 当时本地验证

`python -m compileall -q cloudra tests`、`ruff check cloudra tests` 已通过。聚焦组合首次通过 618 项、4 项环境跳过；公共核心命令及最后字段路径变更另通过 106 项。审查修复后的最终组合通过 655 项、4 项环境跳过、7 项警告（49.91 秒，退出码 0）。未运行 tests 全集。

最终组合的文件清单：

- tests/test_ts_review_regressions.py
- tests/test_ts_candidate_continuation.py
- tests/test_ts_execution_accounting.py
- tests/test_ts_guess.py
- tests/test_ts_input_evidence.py
- tests/test_ts_inputs.py
- tests/test_ts_inspect.py
- tests/test_ts_method_contract.py
- tests/test_ts_pipeline_driver.py
- tests/test_ts_pipeline_recovery.py
- tests/test_ts_pipeline_store.py
- tests/test_ts_process.py
- tests/test_ts_resume_transitions.py
- tests/test_ts_revision_store.py
- tests/test_ts_search_process_tools.py
- tests/test_ts_selected_optimizer.py
- tests/test_ts_stage_inputs.py
- tests/test_ts_workflow_scan.py
- tests/test_geometry_inputs.py
- tests/test_geometry_optimization.py
- tests/test_manual_ts_submission.py
- tests/test_calculation_intent.py
- tests/test_reaction_mapping.py
- tests/test_qm_input_writer.py
- tests/test_runtime_v2_method_policy.py
- tests/test_runtime_v2_production_permissions.py
- tests/test_runtime_v2_hub_bridge.py
- tests/test_runtime_v2_subagent_bridge.py
- tests/test_runtime_v2_core.py
- tests/test_runtime_v2_guidance.py
- tests/test_runtime_v2_compute_notify.py
- tests/test_runtime_v2_ts_workflow_scenarios.py
- tests/test_conformer_model_budget.py
- tests/test_no_sync_on_loop.py
- tests/test_role_identity.py

### 当时实现裁决与代价

- Ruling: AGENTS.md focused-test rule overrides skill full-suite commands — run affected modules only — unrelated failures may remain for CI.
- Ruling: plan says explicit TS calculation objects; shared intent comparison consumes a plain normalized mapping to avoid reverse dependency — no scientific choice added.
- Ruling: native worktree is outside initial writable roots; use reviewed worktree-scoped file operations — cost is approval latency, not broader mutations.
- Task 4/5: Ruling: grouped input migration and revision planning are implemented together because the old flat adjustment cannot operate on the new record — keep both tasks open until their focused checks pass — cost if wrong: a larger review range.
- Task 4: Ruling: preserve native TS/Freq/IRC/endpoint proof tests; replace old implicit force-field selection, synchronous path completion and terminal-closed assertions with explicit-source, queue and durable-revision tests — approved spec supersedes those behaviors — cost if wrong: CI may expose missed integration coverage.
- Task 4/6/7/8: Ruling: native submission, grouped methods, trusted runtime authority and non-time budgets share the same boundary — implement the connected boundary in one range rather than retaining an intermediate flat shim — cost if wrong: wider review range.
- Task 6: Ruling: the repository has no complete confirmed calculation record; use the existing trusted project MethodPolicy, add optional per-purpose complete contracts in that same setting, and block TS submission when the trusted policy is unavailable — no Agent argument grants authorization — cost if wrong: projects without configured policies stop at a checkpoint until configured.
- Task 6: Ruling: constructed seeds use the existing input_atom_index identity table, including declared rotations; external symmetric unlabelled structures remain inconclusive — cost if wrong: a defective construction table could bind the wrong symmetric atom, so final endpoint proof remains mandatory.
- Task 7: Ruling: resolve authority from the current runtime owner on every submit rather than persisting an authorized snapshot or adding a second permission model — cost if wrong: unavailable runtime context blocks continuation until restored.
- Task 7: Ruling: read-only evidence posts may reach a producer inbox but cannot wake it; explicit calls that amplify permissions are rejected — preserves evidence communication without delegation bypass — cost if wrong: an intended production reply waits for an authorized wake.
- Task 4/9: Ruling: endpoint seed only exposes the existing explicit file/evidence replacement capability; source optimization belongs to conformers — avoids accepted but ignored generate/catalog/optimization endpoint fields — cost if wrong: broader endpoint sources require a later approved capability.
- Task 4/9: Ruling: reused IRC requires existing TS input-digest binding and compares geometry at the writer's existing eight-decimal precision — preserves native provenance without new chemistry tolerances — cost if wrong: other valid external IRC jobs need explicitly bound evidence.
- Task 9: Ruling: replace obsolete automatic candidate selection/supplement sampling/flat-adjustment tests with explicit catalog choice, journal, dependency and optimizer tests, while preserving scientific/crash/remote/stereo gates — removed semantics contradict approved no-default design — cost if wrong: incidental old paths lose coverage.
- Task 9: Ruling: repository DFT skill edits are API-reference corrections verified by structured harness and guidance tests; no new behavioral skill is deployed — existing scientific recipes stay — cost if wrong: stochastic model uptake remains unmeasured.


### 当时独立审查与单轮修复

独立审查范围 `089c5fa5..2b4bdf22`，由 fresh `gpt-6-astra` reviewer 只读完成；未修改工作树或运行真实引擎。审查原结论是需修复后再合并。作者核实并在一轮集中修复中处理下列问题，不另发起重复审查，也不将作者测试宣称为 reviewer 批准。

| 发现 | 最终处理 | 回归（test_ts_review_regressions） |
| --- | --- | --- |
| P1：IRC Hessian 只比较 engine/method/keywords | 同时比较显式原生科学设置；差异时重新计算 Hessian；保留相同声明的原有复用测试 | irc_hessian_requires_complete_scientific_settings |
| P1：旧 MOL 键图掩盖实际 XYZ 身份改变 | 预优化、绑定及最终端点复用同一现有连通性判据；几何无法证明时 inconclusive，不花计算额度 | mol_cannot_mask_dissociated_xyz_before_conformer_optimization；原有身份/端点/立体化学回归 |
| P1：prepare 缺键时随机 UUID 重复建路径 | 当时公共及核心 prepare 均要求稳定 request_key；现已改为运行时调用身份内部生成，公共输入不再暴露此字段 | prepare_requires_nonblank_stable_request_key；原有 response_replay 用例 |
| P2：scan 漏掉显式原生块/尾部 | 完整传递 ORCA blocks 与 Gaussian end_setting；不支持的引擎字段组合明确拒绝 | scan_preserves_declared_native_scientific_settings |
| P2：相同输入的 done 作业放行 wrong_mode | 环境捷径只用于执行失败并核验官方正常终止；频率修复另核验实际频率，TS 一虚频、端点零虚频；不凭通用正常终止宣称其他科学失败已修复 | same_bytes_done_job_cannot_clear_wrong_mode；repaired_frequency_requires_valid_result_and_uses_original_input_engine |
| P2：换搜索路线被要求证明旧路线成功 | 将新路线的相关结构/来源证据与原失败绑定；保留旧失败，新路线继续经正常提交和最终科学判据 | failed_scan_can_change_route_with_bound_new_route_artifacts；route_change_rejects_unrelated_failure_provenance；包括不写文件/不改旧记录断言 |
| P2：catalog 丢失原子表 | 绑定选定候选的稳定 atom ID、顺序、fragment ID、来源和摘要；assemble 可核验 reaction_center | catalog_source_binds_stable_atom_table_before_assemble |
| Reviewer Minor，经复核改为 Important：映射提示指导 ORCA 输入非法编号 | 提示统一 reaction.atom_map 为 1-based，避免阻塞点指导错误 | missing_atom_map_prompt_uses_the_grouped_structure_numbering |

RED 复现后 GREEN。初始新回归 fixture 的 ORCA 尾部字段及不可变 qualification 设置错误已校正；catalog 的旧提交函数另做只读 RED 复现。最终相关组合含 16 项审查回归：655 passed / 4 skipped。缺少真实引擎与科学验收不记作通过。没有未处理的已确认 Critical/Important 或 Deferred Minor。

补充裁决和成本：

- 历史裁决（已被当前实现取代）：当时公共 prepare 要求调用者传入 request_key。现公共字段已删除，由运行时调用身份产生稳定重放键；不能再按这条旧裁决要求 Agent 填写。
- Ruling: reuse existing final endpoint connectivity perception for MOL+XYZ preflight, including charged-fragment handling — no new chemistry thresholds — cost if wrong: legitimate distorted entrance geometries may remain inconclusive and require concrete corrected sources.
- Ruling: full Hessian declaration equality excludes only frequency_mode, which selects the derivative algorithm rather than changing the theory — includes engine/method/keywords/orca_blocks/end_setting — cost if wrong: equivalent spellings may trigger a fresh Hessian calculation.
- Ruling: changed search branch recovery binds old failure and checked new-route artifacts; provided is a candidate, xTB requires checked concrete endpoints and full mapping — old branch success is not required, live submission policy and later scientific gates remain — cost if wrong: a new route may still fail but preserves the original attempt.
- Ruling: catalog geometry/table alignment uses the existing eight-decimal writer precision, while copied artifact bytes retain their exact archived hash — no new chemistry tolerance — cost if wrong: identity metadata incompatible with the artifact stops at a checkpoint.
- Ruling: regrade the atom-map-missing message from Minor to Important because it directly instructs ORCA callers to supply rejected indices at a blocked decision checkpoint, contrary to the requested interface clarity — fixed in the same author pass with RED/GREEN prompt-semantic regression — cost if wrong: only clarification wording changes.
- Ruling: reviewer Declined to judge real ORCA/Gaussian numerical convergence, scientific validity and remote execution — accept this as unverified native-engine acceptance, not as a pass — no real QM jobs were authorized/run; cost if wrong: fixture success may not predict real-engine behavior.


### 当时推送前与 master 整合

2026-10-02 用户授权推送并合并。先合入 `origin/master` 的 `3ec0b6ea`，保留其 ORCA 原生基组写法、辅助基组关键词、SHARK 原始失败诊断、严格审批决策、lint 范围与原生 TS/IRC fixture 回归。旧 flat 接口用例迁移到已批准的分组输入和只读 inspect；不添加兼容垫片。

上游反应中心更改测试先复现 `assemble` 未重建几何的问题，再将该修订依赖恢复为 `build`，保留旧尝试。native fixture 继续断言真实解析器、不可变输入、错误虚频、IRC 边文件缺失、端点优化/频率相同几何、重复终态无重复作业。Agent 用真实工具调用验证相同 scan 修订不增加介入次数、不清除失败、不入新作业。

整合后的本地验证：compileall 与 `ruff check --no-cache .` 通过；相关 TS/原生 fixture/runtime/Agent 组合 **715 passed / 4 skipped**（23.38 秒，退出码 0）；MCP/审批/lint 边界组合 **62 passed**（2.25 秒，退出码 0）。合计 777 passed / 4 skipped。没有在本地跑全套测试；全套交由 PR CI。真实 ORCA/Gaussian 作业没有运行。

PR CI 首轮基础 Python 作业在收集 test_ts_input_evidence 时暴露可选 RDKit 缺失。按 AGENTS 环境探针规范，仅为消费真实化学栈的用例添加 importorskip/依赖 fixture；纯输入、账本及恢复测试保留执行。独立导入环境模拟缺少 RDKit：97 passed / 17 skipped；完整 RDKit 相同相关组合：119 passed。compileall 与仓库 Ruff 通过；没有改科学判据或将失败断言改为跳过。


### 当时合并前 CI 集成修复（2026-10-02）

CI 全套测试暴露了旧测试的只读权限前提与新接口不一致：peer completion 的正向场景改为可委派的 coordinator；DAG 和方法拦截测试显式提供其要验证的计算写权限。Supervisor Hub 的正向创建改为只读 explorer，另有可写 peer 拒绝回归。生产权限守卫保持启用。

真实 Node/QuickJS 督导场景还复现了 DAG 工具继承 MANAGE 声明的问题：只读 DAG 查看声明 READ，研究侧证据送审和督导请求声明 READ/WRITE；图管理工具保留 MANAGE，实际图操作仍经 DAG actor 判定。新增执行层回归验证只读不可送审、研究角色可送审，以及只读可查看。

四档 52 个题库 JSON 从现有生成器重新生成。程序逐项比较确认唯一变化为 method_policy.calculation_contracts 的空映射，既有科学数据、方法及评分参数均未改变。

自动审查反馈逐项复现：Gaussian 无等号括号 route 需正确识别任务与数值频率；scan_parse_failed 不能由泛化的正常终止作业认作恢复；构象来源替换需清除该端活动 catalog 身份；旋转产物失败的 needs 必须指向 conformers.product。修复均有定向回归，不增加科学阈值或方法默认值。

最终定向验证：真实 Node/QuickJS 督导场景与 DAG/TS 权限、反馈回归组合 61 项通过；扩大相关模块组合通过 1021 项、跳过 4 项，并发现旧 Agent 恢复场景误把扫描解析失败当执行故障。该场景改为真实 ledger failed 的执行故障；最终 TS 反馈、Agent 场景、原生意图、方法契约与事件循环组合 93 项通过。compileall 与全仓 Ruff 通过；全套最终结果以本次 PR 最新 CI 为准。
