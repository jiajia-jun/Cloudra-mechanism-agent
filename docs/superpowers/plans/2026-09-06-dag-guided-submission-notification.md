# DAG-guided 显式送审通知修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本次仅编写计划，尚未实施；未经用户要求不提交、不推送，不自动派生子 agent。

**Goal:** 让真实 `dag_bind_evidence` 调用在显式送审成功入库后通知项目 Supervisor，使休眠督导能够继续裁决，并用真实工具入口覆盖传统和 JS 协议。

**Architecture:** 送审方法只负责验证与原子持久化；运行时通知统一经过已有 `DagPolicyStage.after_tool → DagController.on_tool_finished → SupervisionMixin._trigger_supervisor_after_tool`。删除送审方法内部的通知副作用，避免出现两套通知入口或把整个 RuntimeCore 注入普通工具。继续复用 `notify_supervisor` 状态表和 `reconcile_supervision` 恢复机制。

**Tech Stack:** Python 3.11+、asyncio、SQLite、pytest、runtime_v2 InvocationService、Node/QuickJS-WASM；不新增依赖。

**Spec:** [事件驱动督导设计](2026-09-05-event-driven-supervisor.md) §1、§2、§4、§5、§6；本计划细化其中“显式送审持久化后通知”的调用边界，不改变科学审查标准。

## Global Constraints

- 遵守根目录 AGENTS.md：先红后绿、架构级根治、最小改动、禁止兼容 shim 与死代码。
- DAG store 是待办唯一事实源；工具结果只用于识别本次成功持久化，不成为第二份待办队列。
- 不修改化学阈值、方法选择、阶段科学判据、评分、拒答或完成覆盖规则。
- async 路径的同步 SQLite 必须经 `asyncio.to_thread`，禁止新增轮询守护或固定 sleep。
- `notify_supervisor` 的 failed/cancelled 不复活、waiting 不绕过等待、succeeded 开新 run 语义保持。
- 不触碰 scheduler/guard/QM 进程，不使用真实 API key，不向 provider 发请求。
- 测试使用临时 data_dir；保留工作区已有科研产物及用户改动。
- 不做 git commit/push。JS 验收必须真实运行，不接受全 skip。

## 已验证基线与测试缺口

2026-09-06 检查：317 项 DAG、督导、completion gate、JS acceptance/pipeline、工具目录和同步阻塞护栏测试通过，无跳过；有 6 条依赖弃用告警。

临时复现经过真实 `DagBindEvidence.tool_call` 再调用运行时同款 `on_tool_finished`，得到：

```text
tool_success=True
pending_reviews=1
runtime_notify_calls=0
AssertionError: persisted review but never notified Supervisor
```

原因：`dag_bind_evidence.py` 创建的控制器无 core，`submit_evidence_for_review` 内部通知静默跳过；带 core 的运行时控制器完成钩子只处理提案和督导消息，没有处理送审。现有 24 解析端到端用例直接调用带 core 控制器的送审方法，绕过了实际工具入口。

## 方案选择

采用已有 policy 完成钩子承接送审通知，与提案/督导消息保持相同职责边界。仅给工具控制器补 core 会扩大通用工具对运行时的耦合；仅在完成钩子补通知而保留原方法通知，会产生依赖调用入口的双重副作用。因此这两种做法均不采用。

生产链路变为：

```text
LLM traditional call / JS guest tools.dag_bind_evidence
  → InvocationService → LegacyToolExecutor → DagBindEvidence
  → submit_evidence_for_review → validate + atomic store.submit_call_reviews
  → DagToolOutput(result.attachments[].review_id/enqueued)
  → DagPolicyStage.after_tool → on_tool_finished
  → _trigger_supervisor_after_tool → notify_supervisor
  → Supervisor 读取持久信箱 → 裁决 → 阶段绑定 / 反馈 / 结束审计
```

成功批量有至少一条 `enqueued=True` 且有 `review_id` 时通知一次；全部幂等重复不新增通知。送审失败、空结果、只带 accepted 的结果均不通知。持久化后通知失败保留 pending，项目装载时由既有 reconcile 补通知；本次不增加“在线自动重试通知”的新承诺。

## Task 1：用真实工具入口锁定断点，并统一通知所有权

**Files:**
- Create: `tests/test_runtime_v2_dag_submission.py`，专门覆盖真实送审工具与运行时接线。
- Modify: `cloudra/dag/evidence_inbox.py`，送审方法收敛为验证与持久化。
- Modify: `cloudra/dag/supervision.py`，完成钩子承接显式送审通知。
- Modify: `tests/test_dag_supervisor.py`，修正“bind 完成永不通知”的旧测试语义。
- Modify: `tests/test_runtime_v2_supervision.py`，替换直接送审来验证通知的测试入口。

**Interfaces:**
- 保持 `submit_evidence_for_review(self, attachments: list[dict[str, str]]) -> dict[str, Any]` 的参数、返回值与事务语义。
- 消费 `DagToolOutput.result["attachments"]` 中已有 `review_id: str` 与 `enqueued: bool`。
- 保持 `_trigger_supervisor_after_tool(self, tool_name, arguments, result, success) -> None`、`notify_supervisor(core, project_id, *, reason="") -> None` 签名。

- [ ] **1.1 新建失败回归。** 使用 `tests/test_runtime_v2_supervisor_tools.py` 的生产装配方式：`RuntimeCore(strict_events=True)`、`default_stages(core)`、`LegacyToolExecutor`、`InvocationService`、`TurnPipeline`、`AgentRunner`，通过 CommandBus 建项目和 Coordinator。仅 LLM 使用脚本替身。

  测试命名 `test_real_bind_tool_notifies_after_persistence`。临时 DB 建 `r → step1 → p` 与 `ts_opt` 契约、登记一条完成证据；可参考 `tests/test_dag_tools.py::_seed_staged_step` 的建图数据，但生产调用必须走当前 runtime agent 身份。同步准备集中放进 `asyncio.to_thread`。脚本 LLM 返回如下业务调用，协议显式设为 traditional：

  ```python
  ToolCall(
      id="submit-1", name="dag_bind_evidence",
      arguments={"attachments": [{
          "tool_call_id": "parse-1", "bind_target": "step1",
          "stage_kind": "ts_opt", "claim": "fixture evidence for the declared stage",
      }]},
  )
  ```

  在 `cloudra.runtime_v2.supervision.notify_supervisor` 使用 AsyncMock 包装读取断言：通知执行时，数据库已经存在该 explicit pending review。该测试只隔离通知末端，不替换 bind 工具、executor 或 policy；断言真实工具成功且通知一次。用事件作为等待点，有界超时仅作失败上限，finally 调用 `core.aclose()`。

  ```python
  assert pending[0].source == "explicit"
  assert pending[0].tool_call_id == "parse-1"
  assert pending[0].claim == "fixture evidence for the declared stage"
  notify.assert_awaited_once()
  ```

- [ ] **1.2 运行并记录红灯。**

  ```bash
  .venv/bin/python -m pytest tests/test_runtime_v2_dag_submission.py::test_real_bind_tool_notifies_after_persistence -v -o addopts=''
  ```

  必须因为送审成功但通知次数为 0 失败；fixture、权限、导入或 schema 失败不算复现成功。

- [ ] **1.3 修改通知所有权。** 删除 `submit_evidence_for_review` 末尾的通知分支及无消费者的 `_notify_supervisor_of_submission` 方法。将下面分支加入 `_trigger_supervisor_after_tool`，复用其 mode gate 和既有 `_notify_supervisor`：

  ```python
  if tool_name == "dag_bind_evidence" and success and accepted:
      attachments = inner.get("attachments") if isinstance(inner, dict) else None
      if isinstance(attachments, list) and any(
          isinstance(item, dict)
          and bool(item.get("review_id"))
          and item.get("enqueued") is True
          for item in attachments
      ):
          await self._notify_supervisor("explicit evidence submission")
      return
  ```

  此处是已有 verb 分派，不创建新的工具名集合。不要修改 adapter 增加 RuntimeCore 字段，不在 tool 内创建第二条通知路径。

- [ ] **1.4 修正测试假设。** `test_dag_verdict_tool_completions_do_not_notify` 拆清“无入库回执的 bind 不通知”和“督导裁决不自我通知”。24 解析用例改为通过真实 bind executor + InvocationService 送审；不能用补调 `_notify_supervisor` 让测试变绿。只测存储的直接送审测试继续保留，明确不承诺启动运行时。

- [ ] **1.5 验证绿灯及通知矩阵。** 加参数化测试：新增单条一次、新增多条一次、新旧混合一次、全重复零次、失败零次、无 review_id 零次、dag_record 零次、Supervisor 自身工具零次。检查同一 pending 声明重复提交返回同一 review_id、DB 行数不增加。

  ```bash
  .venv/bin/python -m compileall -q cloudra/dag/evidence_inbox.py cloudra/dag/supervision.py
  .venv/bin/python -m pytest tests/test_runtime_v2_dag_submission.py tests/test_dag_supervisor.py tests/test_runtime_v2_supervision.py tests/test_dag_review_call.py tests/test_dag_tools.py -ra -o addopts=''
  ```

## Task 2：补足跨协议与恢复的真实运行时验收

**Files:**
- Modify: `tests/test_runtime_v2_dag_submission.py`。
- Reference: `tests/test_runtime_v2_supervisor_tools.py` 的 JS host 入口、`tests/test_runtime_v2_supervision.py` 的督导状态与反馈事件同步方式。

**Interfaces:**
- 输入为 Task 1 的真实装配和既有 `dag_bind_evidence` 工具 schema。
- 观察 `find_project_supervisor(core, project_id)`、持久 review 状态、`tool.*`/`program.*` 事件及阶段绑定结果；不观察私有通知实现作为端到端成功标准。

- [ ] **2.1 增加真实 Supervisor 往返用例。** 对 traditional/javascript 参数化，LLM 使用按角色路由的脚本替身，真实 Supervisor executor 完成 `dag_view` 读取与 `dag_review_call` 裁决。裁决参数按 `dag_review_call.py` 的当前 schema 构造，引用刚读到的 review_id。用既有合法 fixture 支持阶段，不创造新科学判据。除通知之外，还必须断言 pending 变为已裁决、目标阶段已绑定该证据，且只存在一个项目 Supervisor。

  JS 分支通过顶层 `js_exec` 执行以下 guest 程序；不能直接调用 Python 送审方法替代：

  ```javascript
  const result = await tools.dag_bind_evidence({attachments: [{
    tool_call_id: "parse-1", bind_target: "step1", stage_kind: "ts_opt",
    claim: "fixture evidence for the declared stage"
  }]});
  text(result);
  ```

  Supervisor 的 JS 裁决同样走 guest tools。断言 `program.finished` 和 bind/review 的 `tool.requested → started → result_recorded → finished` 生命周期。通过 `core.aclose()` 回收 host。

- [ ] **2.2 在真实送审入口验证状态表。** 参数化预存 Supervisor 的 succeeded、running、waiting、failed、cancelled 状态；状态准备经 CommandBus/事件路径，不直接写 core 投影。succeeded 后 run_id 更新；running 不 restart；waiting 保留消息不绕过；failed/cancelled 保留 pending 不新发 LLM。用事件/LLM 调用计数验证，禁止依赖固定 sleep。

- [ ] **2.3 验证恢复窗口。** 第一阶段用真实 bind 工具单独入库而不运行 after_tool，模拟“入库后、完成钩子前中断”；第二阶段调用 `reconcile_supervision`。必须在没有重新执行 bind 的情况下通知并处理 explicit pending。另测通知抛错时工具已持久化记录仍在，reconcile 能补通知；failed/cancelled 的恢复行为继续遵守状态表。

- [ ] **2.4 排除测试偶然唤醒。** 主测试的 Coordinator 在断言送审唤醒发生前不能触发 partial stop/退出审查，不能发 `dag_message_supervisor`，不能依赖项目重新装载。否则其它通知会掩盖本次断点。完成全链路断言后再释放脚本 LLM 门闩并关闭 runtime。

- [ ] **2.5 执行跨协议验收。**

  ```bash
  .venv/bin/python -m pytest tests/test_runtime_v2_dag_submission.py tests/test_runtime_v2_supervisor_tools.py tests/test_runtime_v2_completion_gate.py tests/test_runtime_v2_js_acceptance.py tests/test_runtime_v2_js_pipeline.py -ra -o addopts=''
  npm --prefix cloudra/runtime_v2/js_host test
  ```

  预期全部通过；JS 宿主测试实际执行。当前检查环境已有可用 JS host，若执行环境变化，先检查 node 版本与 quickjs-emscripten 安装，不得以 skip 代替验收。

## Task 3：同步约定并完成回归验收

**Files:**
- Modify: `AGENTS.md` 中 DAG evidence_inbox/supervision 的职责说明。
- Modify: `cloudra/dag/controller.py`、`cloudra/dag/evidence_inbox.py`、`cloudra/dag/supervision.py`、`cloudra/runtime_v2/supervision.py` 中指向旧通知位置的注释。
- Modify: `docs/superpowers/plans/2026-09-05-event-driven-supervisor.md`，追加通知所有权说明。

**Interfaces:** 无新增运行时接口；文档描述与 Task 1 最终实现一致。

- [ ] **3.1 写明新边界。** 使用以下表述同步上述文档：

  > `submit_evidence_for_review` 只验证并持久化 explicit review；真实 `dag_bind_evidence` 成功返回后，由运行时 DAG policy 的完成钩子按新建 review 回执通知 Supervisor。直接存储调用不启动督导；中断窗口由 reconcile 扫持久信箱恢复。工具完成本身不自动筛选研究证据。

- [ ] **3.2 扫描旧假设。**

  ```bash
  rg -n '_notify_supervisor_of_submission|送审通知发生在 submit_evidence_for_review 内部|submit_evidence_for_review' cloudra tests AGENTS.md docs/superpowers/plans/2026-09-05-event-driven-supervisor.md
  ```

  被删方法必须无引用；直接送审调用只用于持久化测试，依赖唤醒的测试必须经过真实工具/完成钩子。

- [ ] **3.3 执行最终回归和 lint。** 优先使用仓库规定的 uv 命令；当前 shell 无 uv，等价地使用现有 `.venv`，不得改依赖配置来解决 PATH 问题。

  ```bash
  .venv/bin/python -m pytest tests/ -ra -o addopts=''
  .venv/bin/python -m ruff check cloudra tests
  git diff --check
  ```

  若 ruff 模块缺失，先查已有可用 ruff/uv 路径；如仍无，明确记录未执行 lint，不声称通过。全量失败需定位是否与变更有关，不能忽略相关回归；无关失败以证据单列。

- [ ] **3.4 检查最终 diff 并交付。** 确认没有科研产物、真实 data_dir、配置或计算进程变更。交付包含红灯证据、最终测试数/跳过项、真实 JS host 结果和剩余限制；不把脚本 LLM 的协议往返等同于真实模型的科学判断质量。本轮不提交、不推送。

## 完成标准

- 原有“成功入库但不通知”的真实工具回归先红后绿。
- 送审持久化与运行时通知各只有一个明确责任入口，删除旧内部通知方法。
- traditional 与 JS 均能经真实 bind → Supervisor → 裁决绑定走通。
- 批量/重复/失败/角色/模式/恢复/取消状态没有改变既有契约。
- 无新增科学规则、同步阻塞、轮询 worker 或 RuntimeCore 工具耦合。
- 文档与最终实现一致，完成必要测试并如实报告环境限制。
