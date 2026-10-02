# TS 状态机实现验收（2026-10-02）

分支 `codex/ts-state-machine`。接口行为与本地回归已完成；独立审查另记在本文结尾。当前仅通过替代计算器、原生输入/日志 fixture 和真实账本/Agent dispatch 验证；未启动真实 ORCA/Gaussian 全链，未远端关闭 issue 或合并分支。

## 四个 issue

| Issue | 本次修复 | 直接回归证据 | 边界 |
| --- | --- | --- | --- |
| #108 | 普通计算/TS/bash/公共 spawn/新旧 Hub call/Launcher 均不能放大只读能力，证据 post 不唤醒 producer；自动提交读取当前 owner 权限 | test_runtime_v2_production_permissions：readonly_role_cannot_submit_compute_or_mutate_ts、readonly_peer_call_cannot_create_or_activate_producer、public_spawn_cannot_amplify_readonly_parent_or_peer、readonly_evidence_post_delivers_without_waking_producer、automatic_pipeline_uses_current_owner_permissions | 原有 QM 和锁不被取消；用真实 runtime/dispatch 测，不仅 mock TS |
| #109 | 元素排列不能清除图身份/对称绑定问题；实际种子在优化前、搜索前、提交前核验，绑定摘要和输入版本；最终端点证明保留 | test_ts_input_evidence：element_consistent_map_cannot_clear_identity_mismatch、explicit_map_keeps_ambiguous_concrete_binding_inconclusive、identity_is_rechecked_after_geometry_source_changes、conformer_identity_checked_before_optimizer_submission；test_ts_process 的端点/立体化学/方向区间用例 | 构造绑定来自现有 atom_identity；外部未标记对称结构需补来源 |
| #110 | 第一点 SHARK/临时目录失败不能只改点数重跑；恢复绑定实际失败和相关权威成功证据，同 run 修订历史、回执和额度保留 | test_ts_resume_transitions：failed_scan_point_count_only_does_not_requeue、unbound_recovery_artifact_cannot_authorize_retry、environment_repair_evidence_allows_same_input_new_attempt；test_runtime_v2_ts_workflow_scenarios：ts_failed_scan_repair_same_run | 回归使用第一点故障 fixture；没有重现真实远端 SHARK 环境 |
| #111 | 分组科学方法独立；入 READY 前核验实际原生任务/方法/完整关键词/溶剂块/电荷/自旋及可信项目契约，未知来源暂停 | test_ts_method_contract：unauthorized_method_and_missing_keyword_block_before_ready、authorized_semiempirical_scan_differs_from_formal_method、native_blocks_and_gaussian_links_are_all_checked、undeclared_frequency_block_and_gaussian_trailing_settings_are_differences | 测试涵盖原生输入语法及现有写入器；真实引擎验收仍待进行 |

## Spec §10 行为映射

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

## 本地验证

`python -m compileall -q cloudra tests`、`ruff check cloudra tests` 已通过。聚焦组合首次通过 618 项、4 项环境跳过；公共核心命令及最后字段路径变更另通过 106 项。最终组合与审查后的结果在下方补记。未运行 tests 全集。

最终组合的文件清单：

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

## 实现裁决与代价

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
