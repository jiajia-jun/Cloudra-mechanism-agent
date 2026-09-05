# Task 1 影响面清单：事件驱动 Supervisor 迁移

配套计划：`docs/superpowers/plans/2026-09-05-event-driven-supervisor.md`（2026-09-06 修订，
§5 显式送审契约：研究工具完成不再自动创建 review，只有显式 `dag_bind_evidence` 送审才
通知 Supervisor）。本清单由 Task 1 实际核对代码产生（2026-09-06），行号按当前 checkout。

## 1. `maybe_supervise`（定义：cloudra/dag/supervision.py:114）

D14 合并锁 `_SUPERVISION_STATES`（supervision.py:104）+ while pending 折叠循环
（:139-147）+ `_run_supervision`（:150）同步阻塞 `GraphSupervisor.run`。

生产调用方（全部要迁移为"持久化待办 + notify_supervisor，不等待裁决"）：

| 调用方 | 触发 | 迁移去向 |
| --- | --- | --- |
| cloudra/dag/supervision.py:57（`_trigger_supervisor_after_tool`，dag_propose_mechanism 草稿落库） | mechanism_proposed | 草稿已持久化（dag_drafts open）→ notify_supervisor |
| cloudra/dag/supervision.py:70（同函数，dag_add_species/dag_add_step/dag_update_delivery_element accepted） | delivery_updated | 图变更已在 store → notify_supervisor（或并入 §6 统一结束门禁，Task 3/4A 定） |
| cloudra/dag/supervision.py:78（同函数，dag_message_supervisor 纯文本） | coordinator_message | 正文须持久化（计划 §4：缺表示则最小扩展）→ notify_supervisor |
| cloudra/dag/supervision.py:97（`_wake_supervisor_for_reviews`） | tool_call_review | **删除**：§5 起研究工具完成不再自动入箱/通知；仅显式送审产生 review |
| cloudra/dag/stop_audit.py:159（complete 有缺口时 pre_delivery 同步督导） | pre_delivery | 删除同步"再给一次机会"；走 §6 统一结束门禁的 wait_review 持久化请求 |
| cloudra/runtime_v2/policies/dag_stage.py:287（subagent_launcher/swarm 窗口指纹变化） | delivery_updated | 同 delivery_updated 行 |
| cloudra/services/api_v2/routers/dag.py:204（POST /dag/replan，现场 new controller 同步跑完整督导） | user_replan | 持久化请求 + notify_supervisor，HTTP 立即返回 queued（不得伪报已裁决） |

测试调用方（随迁移改写或删除）：tests/test_dag_supervisor.py:136,570,600,685,692,1159；
tests/test_dag_review_call.py:410,413,414；tests/test_dag_supervisor_feedback.py:83,113,121,139；
tests/test_runtime_v2_dag_delta.py:50（stub 覆盖，随接口消亡清理）。

## 2. `GraphSupervisor` / `GraphSupervisorResult`（定义：cloudra/core/supervisor.py:118 / :106；`run` :302-309 同步阻塞循环）

| 调用方 | 迁移去向 |
| --- | --- |
| cloudra/runtime_v2/policies/dag_stage.py:153-161（guided 模式 `_controller()` 构造注入 DagController） | 删除构造；Supervisor 改由 runtime_v2/supervision.py 经 CommandBus 正常 spawn |
| cloudra/services/api_v2/app.py:102,114（`review_supervisor` factory 供 ReviewWorker） | 随 ReviewWorker 一起收敛（Task 3/6） |
| cloudra/services/api_v2/routers/dag.py:165,190（user_replan 现场构造） | 同上 replan 行 |
| cloudra/benchmark/backend.py:184-205（guided 任务 per-task ReviewWorker + GraphSupervisor factory） | benchmark 改用真实 supervisor agent（复用 runtime 装配），不保留第二执行路径 |
| tests/test_dag_supervisor.py（:412-1087 的 agent 循环/只读/崩溃/折叠等 ~20 处直接用例） | prompt 与科学约束迁入普通 pipeline 后逐项改写（Task 2/6） |
| tests/test_dag_supervisor_feedback.py:19-27（FakeSupervisor 返回 GraphSupervisorResult） | 随反馈路径迁移（Task 4） |
| tests/test_runtime_v2_review_worker.py:10,110-133（real GraphSupervisor + worker 集成） | 随 ReviewWorker 收敛 |

保留再迁移的资产：prompt/审查上下文构造（计划 Task 2 逐项保留科学约束，不复制 LLM while 循环）。

## 3. `on_supervision`（DagController 投影回调）

- 挂载点：cloudra/dag/controller.py:40,65（构造参数 + 实例属性）。
- 触发点：cloudra/dag/supervision.py:155-157（"start"）、193-195（"finish"），均 best-effort
  （投影故障只记 warning，见 CHANGELOG.md:67 的历史事故）。
- 唯一生产实现：`_SupervisionShell`（cloudra/runtime_v2/policies/dag_stage.py:171 注入）。
- 测试：tests/test_dag_supervisor.py:1146-1159（exploding projection 不炸督导）。
- 迁移去向：**整体删除**——壳投影消亡，真实 Supervisor 的生命周期就是自身事件流
  （agent.spawned/run.started/run.finished），UI 不再需要投影回调。

## 4. `_SupervisionShell`（定义：cloudra/runtime_v2/policies/dag_stage.py:41-119；使用 :171）

- 只投影状态：CommandBus spawn role_id="supervisor" 壳 agent + start_run/finish_run +
  message_emitted，不走 LLM 管线；故障基线（壳被取消后仍输出并被自动重启）源于此。
- 测试：tests/test_runtime_v2_dag_stage.py:241-252（壳生命周期）、283-289（spawn 被拒降级）。
- 迁移去向：**删除**（Task 3）；roles.py:77-83 的 supervisor 角色从"壳"升级为真实角色
  （Task 2 配 prompt/工具投影）。

## 5. `_deliver_supervisor_report`（定义：cloudra/dag/supervision.py:200；调用 :187）

- 现行双投递：notices.pin(coordinator, "supervisor") + 非 a-0 触发时 CommandBus
  agent.message 唤醒（supervision.py:243-257）；无 core 句柄时仅靠 DAG 投影（:218-225）。
- 迁移去向：Task 4 选普通子 agent 完成回传为唯一投递口，删除本函数；Supervisor
  parent 指向 Coordinator（不指向首次提交证据的研究子 agent）。

## 6. `ReviewWorker`（定义：cloudra/runtime_v2/review_worker.py:24）

- 装配：cloudra/services/api_v2/app.py:104,122（`core.review_worker`；lifespan
  start/close 在 :133/:152）；cloudra/benchmark/backend.py:187,200（guided per-task）。
- 依赖的持久化表族：dag_review_requests/decisions/notifications（cloudra/dag/store.py
  :526-1114 一带；list_review_requests :700、pending_review_notifications :766）——
  **表族保留复用**（显式请求/退出审批的持久化表示），轮询 worker 收敛删除。
- 测试：tests/test_runtime_v2_review_worker.py:22,87,159,213,269,348（含
  test_review_store_ensures_schema_on_legacy_db :365 对 app.py:62 `_review_store` 的守卫，
  该守卫语义应随 store 工厂的新宿主保留）。
- 迁移去向：后续任务收敛删除；Task 1 新测试不依赖其存续。

## 7. 触发入口锚点树核实（计划"现状关键锚点"逐条对账）

生产端链（当前同步阻塞根因）：
`DagPolicyStage.after_tool`（cloudra/runtime_v2/policies/dag_stage.py:267）→
`DagController.on_tool_finished`（cloudra/dag/evidence_inbox.py:142）→
- 非观察工具（`is_dag_observable` False）→ `_trigger_supervisor_after_tool`
  （evidence_inbox.py:154 → supervision.py:32）；
- 观察工具 → register_evidence + `_derive_facts` + `_enqueue_call_review`
  （evidence_inbox.py:159-177）→ guided 且新入箱 → `_wake_supervisor_for_reviews`
  （evidence_inbox.py:179 → supervision.py:83）→ `maybe_supervise` →
  `_run_supervision` → `GraphSupervisor.run`（cloudra/core/supervisor.py:302 同步阻塞）。

七个触发入口核实结果：

1. dag_propose_mechanism → mechanism_proposed：✔ supervision.py:56-61。
2. 观察工具（log_parser/reaction_mapping/thermo_analysis/ts_guess，registry
   dag_review=True）→ tool_call_review：✔ evidence_inbox.py:175-179。**§5 起删除自动入箱**。
3. dag_bind_evidence → submit_evidence_for_review：✔
   cloudra/tools/Plantool/dag_tools/dag_bind_evidence.py:146 → evidence_inbox.py:209，
   入箱后 :246-247 同样走 `_wake_supervisor_for_reviews`。**保留为唯一显式送审口**，
   改为持久化 + notify_supervisor。
4. delivery_updated（含 subagent 窗口）：✔ supervision.py:62-74 + dag_stage.py:279-287。
5. dag_message_supervisor：纯文本 → coordinator_message（supervision.py:75-81）；
   结构化 → ReviewRequest 持久化（走 dag_review_requests 表族，由 ReviewWorker 消费）。
6. API user_replan：✔ services/api_v2/routers/dag.py:163-223（:185-201 现场 new
   controller + GraphSupervisor，:204 同步 `await maybe_supervise` 并把结果直接回 HTTP）。
7. stop 审计：pre_delivery 同步督导 stop_audit.py:155-177（:159）；
   exit review enqueue stop_audit.py:237-259（`_enqueue_exit_review`，partial 无批准 →
   wait_review :188-218）。

补充发现（计划锚点未列全的相关面）：

- 计算终态自动入箱 `enqueue_compute_review`（evidence_inbox.py:839，guard/executor
  进程内调用，不直接唤醒 Supervisor）：调用方 cloudra/runtime/compute_executor.py:46-48、
  130-132；cloudra/runtime/monitor.py:387-389、564-566；
  cloudra/tools/Chemtool/mark_compute_job_failed.py:93-95。**§5 起 guided 下移除**。
- `_enqueue_call_review` 的 registry 白名单判定（evidence_inbox.py:102，
  `is_dag_reviewed`）与 `dag_review` 元数据消费方将随 §5 清理。
- on_tool_finished 的测试面（迁移时需批量改写）：tests/test_dag_supervisor.py 约 20 处、
  tests/test_dag_tools.py:533,606,760、tests/test_dag_propose.py:284,319、
  tests/test_dag_requirements.py:267、tests/test_dag_evidence_facts.py:315、
  tests/test_dag_review_call.py:122,332-384,445,460、tests/test_runtime_v2_dag_delta.py:47。
