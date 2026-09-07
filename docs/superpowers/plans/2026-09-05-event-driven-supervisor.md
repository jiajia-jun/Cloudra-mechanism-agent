# Event-driven Supervisor Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. 本计划交给 k3 执行；先读仓库 AGENTS.md，再核对当前代码，不启动真实科研任务或调用付费模型验证。

**Goal:** 将同步嵌套督导改为普通 runtime_v2 agent：工具完成只登记可选证据，agent 筛选并显式送审后才通知，Supervisor 独立裁决，真实执行和 UI 生命周期统一。

**Architecture:** 每项目一个真实 Supervisor AgentSession，由现有 AgentRunner / TurnPipeline / InvocationService 驱动。持久化 DAG 信箱只保存显式送审及明确督导请求；消息只提示信箱变化，休眠则唤醒，运行则下一轮消费。删除同步 GraphSupervisor 执行链和投影壳，不引入独立 review daemon、合并窗口或第二套调度器。

**Tech Stack:** Python 3.11+、asyncio、SQLite、runtime_v2 事件 / CommandBus / AgentHost、pytest；沿用现有 JS 与 traditional 工具协议。

**Spec:** 本文“设计契约”是本次对话已确认方案的完整落地规格；实施不依赖聊天记录。

## Global Constraints

- 只在 dag_guided 启用自动督导；standard / dag_record 保持现有语义。
- runtime 状态只能通过事件及 apply_event 应用；DAG 图、review、裁决仍由既有 DAG store / engine 事务维护。
- 工具权限唯一来源为 registry / capabilities；禁止复制工具名白名单。
- Supervisor 对 delivery 图只读，保留现有阶段裁决与草稿审批权限，不赋予研究写文件、bash、计算提交或创建子 agent 的能力。
- 不将 asyncio.create_task(GraphSupervisor.run(...)) 作为最终实现。
- 不修改研究文件、运行数据、模型配置和用户未提交改动；不提交与本任务无关文件。
- 仓库可能已变化，文中位置按符号定位。计划提议的新接口不是已有 API，实施时须统一定义与调用。

## 已验证的故障基线

2026-09-05 本地 UTC+8，项目 prj_6a1de9104a7c4d1d：

- Coordinator as_d11fd1d4e1a54c86 于 23:06:44 提交 exec_bfdfbb749adc4c80，JS 串行解析 24 个 opt/hess 日志，末尾才 text 汇总。
- 23:13:22 E1 子 agent 完成消息已进入主 agent 信箱；主 agent 没进入下一轮。
- 某次 log_parser 在 23:18:27 产生 tool.result_recorded，23:29:54 才 tool.finished。
- 23:36:37 程序取消，duration_ms=1792633，只开始了 12 次解析。
- Supervisor 壳 as_4288ad4ed3714a9e 在 23:36:27 被用户取消，23:36:34 仍输出，23:36:35 被自动重启。

根因路径：InvocationService 后处理 await DagController.on_tool_finished → _wake_supervisor_for_reviews → maybe_supervise → GraphSupervisor.run；每次读日志都阻塞到完整裁决结束。_SupervisionShell 仅投影状态，不拥有真实执行任务。

## 设计契约

### 1. 生产与消费

研究工具执行 → 持久化结果/证据与可确定事实 → 返回；不创建 review、不通知 Supervisor。

agent 筛选证据 → 显式 dag_bind_evidence → 持久化送审请求/review → 通知 Supervisor → 返回 queued。两条路径都不等待督导 LLM 或裁决完成，仍等待必要持久化。

Supervisor 每轮读取当前 pending reviews、待审批 drafts 和显式督导请求。通知不能携带一份被当作事实来源的旧待办快照；读取信箱时取得最新状态。处理多条 pending 是普通 agent 工作，不设批处理时间窗口。

保留机制草稿提交、用户 replan 和显式 dag_message_supervisor；tool_call_review 仅由显式证据送审产生。停止门禁保持确定性检查，指出缺失证据供 agent 选择提交，不自动将历史工具调用批量送审，也不每次 stop 触发一次重复 LLM 审查。实施时枚举全部触发入口，删除绕过显式选择的自动入口。

### 2. 生命周期

| 状态 | 系统新增待办行为 |
| --- | --- |
| 尚未创建 | 创建项目唯一 Supervisor，经正常调度启动 |
| queued / running | 注入信箱变更消息；不 restart、不重置上下文、不再创建 runner |
| waiting | 依现有 waiting 语义处理；审批/输入等待不可被普通通知绕过，消息保留 |
| succeeded（正常休眠） | 正常 wake，开新 run，并重读持久化信箱 |
| failed | 保留待办和失败状态；不由每条系统通知反复 reopen，显式恢复后继续 |
| cancelled（用户取消） | 仅保留待办，不自动复活；明确恢复后重新扫描信箱 |

项目内唯一性包括并发的首次通知。复用已有 CommandBus / 调度的序列化边界；如果必须加创建锁，只作为易失互斥，不作为 Supervisor 身份事实来源。身份由 core.agents 的项目+角色投影确定。

Supervisor 的正常 stop 表示本轮信箱工作完成，不要求整个科研 delivery 达标；Coordinator 的实质计算与交付门禁仍有效。不得让 Supervisor 的 stop 被 Coordinator 门禁阻止，也不能让有意挂起的审批因 pending 不为空进入忙循环。

### 3. 权限和反馈

- 普通管线中的 Supervisor 仍使用 supervisor_access 能力投影及 SupervisorToolExecutor 的路径/动作限制，并经过 InvocationService 的持久化与策略边界。
- Supervisor 为裁决而调用 log_parser 等只读工具，不能再次制造自己的 review 或唤醒自身。裁决和通知也不能产生递归复核。
- 裁决后 Coordinator 在下一轮收到反馈；Coordinator 正在运行时不重启，正常休眠可唤醒，用户取消则不复活。
- 最终报告只保留一个投递口，避免普通子 agent 完成通知与旧 _deliver_supervisor_report 双重投递。如沿用 notice pin 保存最新结论，它只作上下文投影，不再单独重复发相同报告。
- 异步迁移后 dag_propose / 显式请求返回 accepted/queued 或既有等价提交状态；不得在裁决未完成时伪报已接受草稿。前端/API 调用方与测试同步调整。

### 4. 持久性和竞态

DAG store 是持久化待办来源，runtime mailbox 是易失通知队列。不要为了异步重建所有 review 数据到第二份 runtime 投影。

- 证据入库成功、通知前崩溃：启动或项目加载后扫描持久化待办，补通知。
- 显式请求有正文而无法从 draft/review 推导：复用并核实既有持久化请求表示；如果缺失，增加最小持久化请求及完成标记，禁止只放内存消息。保留原问题正文与请求身份。
- 正常恢复沿用 runtime 的 interrupted run → failed 规则；扫描不得把失败/用户取消视作正常睡眠而绕过恢复策略。用户恢复后必须重读全部待办。
- 信箱为空判断与正常结束之间到达新待办：通过调度边界的再次检查或结束后补调度保证没有 lost wakeup；不用固定 sleep，也不靠下一次偶然工具调用救活。
- 重复通知不重复创建 agent；已经裁决的 review 不因通知重跑。允许现有“显式重提产生新 review”的产品语义，不扩展为跨历史永久去重。
- 持久化失败不可伪报成功。已落库但通知失败保留可恢复待办，输出明确的可诊断错误/记录。

### 5. 显式选择送审与裁决证据约束（2026-09-06 追加，覆盖旧自动入箱假设）

用户要求由 agent 决定送审内容，并担忧 Supervisor 幻觉。此次范围包含显式送审，不可只做自动复核异步化。幻觉严重程度尚无独立评估，不在实现报告宣称已证实或已消除。

- 保留自动证据快照/事实提取及审计，但删除 log_parser、reaction_mapping、thermo_analysis、ts_guess 的自动 review 创建语义。清理 registry/capabilities 中已无消费者的 dag_review 元数据或明确重命名语义，不能把现有自动开关原样保留。
- 移除计算终态自动 enqueue_compute_review 路径（至少 guided 下）；计算完成/失败仍正常通知研究 agent，研究 agent 解析、筛选后显式提交。dag_record 的直接绑定不受影响，清理其无用待督导队列须有回归。
- 复用 dag_bind_evidence，不再发明同义工具。单条/批量都指定 tool_call_id、bind_target、stage_kind；加入简短 claim/rationale 说明“要证明什么”，将其持久化为提交者主张而不是已证事实。研究子 agent 按现有角色权限提交自身或合法共享证据；跨项目引用必须拒绝。
- 提交需校验目标/阶段存在、调用已结束、证据可解析、引用属于项目。失败工具结果允许作为负证据，但不能因此把成功阶段置为 complete。
- 重复键须包含证据身份、目标和阶段，不能只按工具结果去重：同一日志支持 geometry/frequency/single_point 的三条声明都不能丢。对相同 pending 声明的重复提交返回既有 review_id 并视作幂等成功；不同声明仍独立保存。批量先全部校验再事务提交，不能前几项入箱、后面失败且返回信息掩盖副作用。
- Supervisor 围绕明确 claim 和提交的不可变快照审查。当前 workspace 同名文件不能覆盖旧快照含义；需要额外材料时返回 needs_evidence（采用既有等价状态亦可），列出具体缺失证据，本轮不自动再审，不自行发起研究计算。
- 确定性校验保证裁决引用存在、项目/目标/阶段匹配、证据调用已完成；科学解释要求引用实际证据中的字段/位置，区分观察与推断。程序不能靠字符串引用证明科学推理正确，测试和报告不要夸大保证。
- 不允许在无 pending 请求时自行扫描整个工作区、根据文件名猜身份后输出新裁决。明确的草稿审查/用户问题仍可读相关材料，但不能衍生无限审查任务。
- 新版本恢复历史 pending 自动 reviews 时不能全量唤醒督导。增加来源标记区分 explicit/legacy_auto；无法可靠识别的历史记录保留但不自动消费，向 Coordinator 给出一次待筛选提示；只有明确重新提交后进入可消费信箱。保留审计，不删除旧证据/裁决。

### 6. 所有自主结束路径统一审计（2026-09-06 追加）

已检查当前实现：TurnPipeline 在 response.tool_calls 为空时直接返回 decision=stop；AgentRunner 的 on_run_end 仅为 DAG Coordinator 记录 unaudited partial，随后 finish_run(succeeded)。这绕过显式 stop 的完整覆盖率和部分退出审批。GoalStage 只注入目标；ScheduleStage 允许连续第二次 stop 自我确认，不能作为目标完成证据。

- 引入唯一的运行结束判定边界，显式 stop 与无工具调用的最终回复必须到达同一判定；不能靠模型是否调用工具决定是否审计。避免在 before_tool 和 runner 各执行一次有副作用的审批。
- 判定返回明确结果：continue_work（具体缺口）、wait_background（有可核实的后续唤醒来源）、wait_review（已持久化退出请求，等待裁决）、allow_final（确定性完成或有效部分退出批准）。复用现有 StopGate 命名亦可；只保留一个事实源，不建立第二套相同门禁。
- DAG Coordinator 完成交付必须满足 delivery 覆盖契约；没有显式 disposition 的纯文本结束不得默认为 complete，也不能自动登记 partial 后放行。在 DAG guided 下无批准的部分结束进入同一退出请求流程；DAG record 保留允许 partial 的既有语义，但同样经过判定并明确记录。
- standard 模式不强行要求 DAG，也不假称有通用确定性目标验证器；保留普通问答可结束。Schedule 模式的纯文本退出也须经过其结束策略，有可核实未完成后台工作时不能靠第二次 stop 放行。无结构化完成标准时准确标识为 agent 声明，不能把自我确认写成已验证完成。
- continue_work 反馈具体缺口、目标和可采取的下一步，不只注入“继续”。DAG 缺证据时由 agent 选择送审，不能恢复自动全量复核。
- wait_review 对同一交付版本/退出声明复用既有请求，挂起等待裁决或相关新输入，不在每轮 stop 重建请求/调用 Supervisor。拒绝后带理由继续；证据/范围变更后重新按有效性校验。
- wait_background 必须对应运行中子 agent、调度计算或有效 reminder 等实际可唤醒来源；普通无归属后台脚本不能仅凭模型声明视为可靠唤醒。复用现有后台事实查询，不将所有非终态 agent（例如被审批挂起且无进展者）盲目当作任务会自然完成。
- Supervisor 的结束以其可处理信箱是否完成为准，不要求科研 delivery 全部完成；研究子 agent 以自身任务/已有角色约束为准，不强加 Coordinator 的整个项目覆盖要求。
- 用户取消/服务关闭走取消生命周期，不受完成审计阻拦，不触发退出审批、继续提示或新增 LLM。门禁不负责复活用户取消的执行。
- 门禁阻止结束时不能 finish_run(succeeded)，也不能把被拒绝的最终回复作为已完成交付展示。允许展示为中间说明，但状态和交付处置要一致。
- 统一门禁也要防无进展自循环：相同状态下重复退出不能无限消耗模型请求。复用现有有限重试/loop guard；若没有可用机制，为重复无进展结束设置有界次数，耗尽后记录 blocked/failed 或现有等价可恢复状态并提示用户，不伪报完成、不自动重新唤醒。

## 文件地图

| 文件 | 责任 / 预期变化 |
| --- | --- |
| cloudra/runtime_v2/supervision.py（新） | 小型运行时接入：项目唯一 Supervisor 查找/创建、持久待办查询、通知/恢复协调；不运行 LLM 循环 |
| cloudra/runtime_v2/policies/dag_stage.py | 删除 _SupervisionShell 与 GraphSupervisor 构造；生产端非阻塞通知；Supervisor 的观察/停止策略区分 |
| cloudra/dag/supervision.py | 将同步 trigger/run/report 生命周期改为提交请求；删除 pending trigger 合并循环 |
| cloudra/dag/evidence_inbox.py | 保留事务化证据/review 登记，移除研究工具自动入箱；显式送审才通知 |
| cloudra/dag/store.py / models.py | 复用持久化信箱；仅在显式请求缺少表示时最小扩展 |
| cloudra/runtime_v2/roles.py / adapters.py / tool_catalog.py | 真实 Supervisor 角色、prompt 与受限工具执行接入两种协议 |
| cloudra/dag/supervisor_tools.py | 保留权限/路径守卫，接入 InvocationService 里的执行器；不再独立绕过调用生命周期 |
| cloudra/core/supervisor.py | 迁移仍需要的 prompt/context 构建后删除旧执行循环及无人使用类型 |
| cloudra/runtime_v2/agent_runner.py / agent_host.py / commands.py | 复用生命周期；只补实际缺失的完成/唤醒竞态，不另造通用调度框架 |
| cloudra/runtime_v2/subagent_bridge.py / notices.py | 唯一报告投递路径、取消保护、上下文通知 |
| cloudra/runtime_v2/core.py / persistence.py / services/api_v2/app.py | 初始化及项目恢复接入，避免事件重放执行 LLM 副作用 |
| cloudra/prompts/supervisor.md | 每轮读持久待办、裁决、无待办则 stop；保持科学审查规则 |
| tests/test_runtime_v2_supervision.py（新） | 生命周期、异步边界、竞态与恢复的核心回归 |
| tests/test_dag_supervisor*.py / test_runtime_v2_dag_stage.py | 旧同步假设迁移、权限与裁决保持 |

## 追加事故：停止后仍有活跃执行 / LLM 调用（最高优先级）

用户在本次诊断后报告“大量 Cloudra 僵尸进程在调用 LLM”，要求将停止失效纳入本次实施，不能只解决同步复核阻塞。

证据分层：本次进程检查确认 API、scheduler、知识服务、2 个 JS host、多个脱离父进程的 MACE 服务仍存活，并有 2 个 `<defunct>` 条目；紧急清理目标共 25 个，清理后按相关命令模式复查无残留。这里没有抓取到逐进程 LLM 网络请求，不能把全部 25 个目标都认定为 LLM 调用者。严格的 OS zombie（defunct）已退出，不能发请求；需调查的是仍存活的孤儿进程、后台 task、线程及取消后新建的请求。

静态代码给出了必须核查的具体入口（不是已经证明的请求归因）：

- `agent_runner.py::_schedule_run_finalize` 使用脱离 runner 的 create_task；cancelled / failed 路径仍调度 finalize，检查其摘要 LLM 是否在取消后继续或新建请求。
- `llm_client.py` 中 requests 经 asyncio.to_thread / executor 执行；取消 await 不等于底层阻塞线程和连接已停止，必须覆盖 Responses、Chat、SSE、fallback 与 retry。
- `api_v2/app.py` lifespan、daemon_supervisor 的 watchdog，以及 JS host / 外部 MLIP 进程的生命周期，必须拥有可核实的关闭和回收路径。

### 停止语义（新增强制契约）

1. 用户取消一个 agent：立刻禁止该执行及其后台收尾新发 LLM 请求，取消实际 runner、重试和该执行拥有的 finalize/压缩/摘要任务。保留必要的本地终态持久化，取消收尾不得再付费请求摘要。任务作用域按 session + run 标识，不能误取消同身份后来由用户明确开启的新 run。
2. 项目取消：传播到项目所有推理 agent，包括真实 Supervisor；具体 UI/API 若没有项目取消入口，实施时明确指出并提供现有入口的可用停止方案，不能声称单 agent 取消覆盖全项目。
3. 服务关闭：先停止新任务准入及 watchdog 拉起，再取消并 await 所有注册推理/收尾任务，关闭客户端和流，最后回收本服务拥有的 JS host 等子进程。收尾设明确有界时间，超时终止实际执行资源并记录。
4. 已发送到 provider 的请求不能承诺撤销远端计算或账单；本地必须停止后续读取/重试和新请求，尽可能关闭现有连接，并暴露无法立即中断的传输限制。
5. 单 agent 取消仍遵守现有“科研计算独立于推理运行”的契约，不连带杀 scheduler/guard/QM。用户显式要求“停止全部 Cloudra 及计算”时才关闭全套服务和归属计算进程，并防止 watchdog 重新拉起。两种范围须在文档和测试中区分。
6. 只终止有明确归属的任务/进程；禁止用宽泛 python/node/用户名字符串匹配杀进程。处理子进程退出需 wait/reap，不能仅发送信号后假定已回收。

## Task 0：停止失效取证与回归（先于功能迁移）

- [x] 枚举全部 LLM 请求入口及后台 task 创建点，包括 finalize、compaction、Supervisor、retry/fallback；建立 session/run → task → PID（如适用）→ request 的归属。请求日志只记录身份、用途、开始/终止/取消时间及结果，不记录凭据或完整 prompt。
- [x] 新建 `tests/test_runtime_v2_cancellation.py` 与 `tests/test_llm_cancellation.py`。用本地 fake HTTP/SSE 服务记录请求数及连接关闭，不调用真实 provider。
- [x] 精确构造取消时序：请求前、SSE 中、重试退避中、fallback 切换前、正常 finalize 已开始、cancelled 分支准备 finalize。取消完成后请求计数保持不变；释放所有阻塞门闩后仍不能新增请求。
- [x] 使用独立测试进程验证 requests 线程仍运行的情况，避免把 asyncio task cancelled 当成传输已停。对不可取消阻塞调用给出明确改造：优先可取消 async transport；如必须保留同步兼容路径，提供可关闭连接和有界退出，无法满足时用受控隔离进程，不保留无限悬挂线程。
- [x] 把这些失败用例与 Task 1 的督导壳取消用例一起确认失败；记录实际命中路径，勿仅凭用户用词或进程名字断定根因。

## Task 1：锁定回归与接口

- [x] 阅读上述入口，列出所有 maybe_supervise / GraphSupervisor / on_supervision 调用方，以及 API、benchmark 中的装配；在提交说明记录实际影响面。
- [x] 新建 tests/test_runtime_v2_supervision.py，复用现有 RuntimeCore(strict_events=True)、CommandBus 和 fake LLM / executor 测试夹具。
- [x] 加入门闩控制的回归：Supervisor LLM 故意挂起时，研究 agent 的 log_parser 必须完成；门闩释放之前不能发生真实裁决。用 asyncio.Event 控制阶段，wait_for 只作失败上限，不以耗时阈值证明性能。

```python
# 测试时序；fixture 按现有 pipeline 测试装配。
entered = asyncio.Event()
release = asyncio.Event()
async def blocked_supervisor_response():
    entered.set()
    await release.wait()
# 创建带该 fake 响应的真实 supervisor runner，调用生产端工具。
# 等 entered 后，断言生产端工具 task 已可完成且 review 仍 pending。
# finally: release.set()，收束并取消测试 runner，避免悬挂 task。
```

- [x] 再加入取消回归：用户取消后，释放 fake LLM 或发送新 review 都不能生成新 run/继续裁决。
- [x] 运行 `uv run pytest -q tests/test_runtime_v2_supervision.py`，确认因现有同步/壳语义失败。
- [x] 定义接入接口（以下为提议名称，落地后全程统一）：

```python
async def notify_supervisor(core: RuntimeCore, project_id: str) -> None:
    # 调用方已持久化待办；只确保 agent 身份及通知/调度，不等待裁决。
    ...
async def reconcile_supervision(core: RuntimeCore, project_id: str) -> None:
    # 项目装载/显式恢复后读取持久化待办；遵守 failed/cancelled 策略。
    ...
```

函数体由后续任务实现，不将省略号提交为完成实现；不引入含旧待办副本的内存队列服务。

## Task 2：将 Supervisor 接入普通推理与工具生命周期

- [x] 先加测试：真实 Supervisor 使用 AgentRunner；JS 和 traditional 都能列出并执行合法裁决工具；bash/compute/write/越界 read 仍拒绝。
- [x] 从 GraphSupervisor 中提取现有 prompt 与审查上下文构造，接入普通 pipeline；逐项保留原有科学约束，不复制其 LLM while 循环。
- [x] 实现 registry/capabilities 驱动的 Supervisor 工具投影和执行器路由。核对 legacy_agent_id 映射能识别 supervisor，不能按未知研究角色处理。
- [x] Supervisor 读证据不 enqueue review；正常 stop 不触发 Coordinator delivery gate。测试它读两次 log_parser 后 review 数量没有增长。
- [x] 验证 InvocationService 事件顺序：requested → started → result_recorded → finished；审批、取消、JS 中断沿用标准机制。
- [x] 运行 `uv run pytest -q tests/test_runtime_v2_supervision.py tests/test_dag_supervisor_tools.py tests/test_runtime_v2_invocation_protocol.py`，检查新旧权限测试。

## Task 2A：显式送审选择与证据约束（Task 3 前完成）

- [x] 在 `tests/test_runtime_v2_supervision.py` 加入 24 次研究 log_parser 不创建 review、不启动 Supervisor 的测试；分别覆盖 registry 的四类原自动工具和计算 done/failed 通知路径。
- [x] 在 `tests/test_dag_evidence_bindings.py`、`tests/test_dag_review_requests.py` 加入：从 24 份证据选 2 份，仅这 2 份入箱；同一调用的三阶段声明均保存；相同声明重发返回既有 ID；批量一项非法则全部不提交。
- [x] 修改 `dag_bind_evidence.py` 的 schema 与说明、`submit_evidence_for_review` 和 store 事务接口，实现 claim/rationale、来源、精确幂等键及批量原子性。先定位历史 schema 的初始化/兼容策略，保留已有数据。
- [x] 删除工具后处理和计算终态自动入箱，只保留证据登记、事实提取及研究 agent 完成通知。更新 prompt，明确“先筛选，再送审；未被提交的探索结果不会被督导读取为待办”。
- [x] 修改裁决入口与 Supervisor prompt：围绕请求中的目标/阶段/主张，引用快照结果；证据不足明确返回且结束本次处理，不 busy-loop 重试。增加同名文件被覆盖后仍以原快照裁决的测试。
- [x] 覆盖无依据引用、跨项目引用、失败证据冒充成功、错目标/阶段、缺失证据的拒绝测试。对科学解释用固定 fixture 核对观察/推断标注，不能把 fake LLM 测试称为幻觉率评估。
- [x] 在 `tests/test_runtime_v2_persistence.py` 加历史自动 pending 恢复测试：不消费、不丢审计，显式重提后才调度；显式请求重启后仍可恢复。
- [x] 运行 `uv run pytest -q tests/test_runtime_v2_supervision.py tests/test_dag_evidence_bindings.py tests/test_dag_review_requests.py tests/test_dag_review_call.py tests/test_runtime_v2_persistence.py`。

## Task 3：持久信箱通知替换同步督导

- [x] 实现 notify_supervisor，项目唯一身份取自事件投影；并发首次通知只生成一个 Supervisor。
- [x] 加状态表覆盖测试：running 不重启；succeeded 唤醒；failed/cancelled 不被系统通知复活；waiting 审批不被绕过。
- [x] 研究工具证据登记完成后直接返回；只有显式送审/机制草稿/明确督导请求创建持久待办并通知。特别核对用户 replan 与显式问题正文。
- [x] 删除 _SupervisionShell 和父工具栈中的 GraphSupervisor.run 调用；删除 trigger 合并锁/while pending 的旧执行职责。
- [x] 更新工具/API 返回语义与测试：提交成功并不代表草稿已获批；未获批仍被实质计算门禁拒绝，获批后才放行。
- [x] 增加 24 个解析的端到端 fake 测试：先显式提交一份证据使督导进入门闩，再执行另外 24 个研究解析：均可返回且不增加 review；随后主 agent 下一轮可收到已投递的子 agent 消息。不要承诺任意长 JS 程序中途可抢占接收消息。
- [x] 运行 `uv run pytest -q tests/test_runtime_v2_supervision.py tests/test_dag_propose.py tests/test_dag_substantive_gate.py tests/test_runtime_v2_dag_stage.py tests/test_dag_review_requests.py`。

## Task 4：反馈、结束竞态和恢复

- [x] 选择普通子 agent 完成回传作为最终报告唯一投递口，移除同步 _deliver_supervisor_report 的重复发送。确保 Supervisor parent 指向 Coordinator，而不是首次提交证据的研究子 agent。
- [x] 测试 Coordinator running / succeeded / cancelled 三种状态下反馈行为；报告只投递一次，最新裁决能进入下一轮上下文。
- [x] 用门闩精确构造“读到空信箱 → 新 review 到达 → stop 提交”时序，断言最终有消费者处理新 review，且最多一个 runner。若普通 agent 的握手已满足，直接复用并保留回归；否则只补缺失边界。
- [x] 实现 reconcile_supervision，挂到项目装载与明确恢复路径；恢复扫描只安排通知，不在 apply_event / 重放中执行任务。
- [x] 测试证据落库后通知前中断、处理前中断、裁决后通知重复、用户取消后重启、failed 后显式恢复。待办不丢，已裁决记录不重复处理。
- [x] 测试退出 dag_guided 后停止自动消费；返回 guided 时只对可运行的 Supervisor 补通知，不绕过用户取消。不要清空持久化未决事项。
- [x] 运行 `uv run pytest -q tests/test_runtime_v2_supervision.py tests/test_dag_supervisor_feedback.py tests/test_runtime_v2_subagent_bridge.py tests/test_runtime_v2_persistence.py tests/test_runtime_v2_replay_equivalence.py`。

## Task 4A：统一结束门禁，封闭纯文本提前退出（Task 5 前完成）

- [x] 新建 `tests/test_runtime_v2_completion_gate.py`，使用相同不完整 delivery fixture 分别驱动显式 stop 与无 tool_calls 的最终回复；两条路径必须得到相同的不允许完成结果，且不能落 succeeded/未经批准 partial。
- [x] 阅读 `turn_pipeline.py` 的无工具调用分支、`agent_runner.py` 的 stop 收尾、`dag_stage.py::_audit_stop/on_run_end`、`dag/stop_audit.py`、`schedule_stage.py`，选择 runner 收尾前作为统一判定边界；工具侧如仍预检只做无副作用验证，审批请求只能创建一次。
- [x] 将 DAG audit 的输入结果传递/复用到统一边界，区分 explicit disposition、隐式最终回复、正常后台等待。移除 record_unaudited_partial 作为无条件退出捷径，保留可审计历史兼容。
- [x] 实现 continue_work 时返回缺口给下一轮，wait_review 持久化请求后等待，wait_background 验证唤醒来源，allow_final 才落最终交付处置。角色分流复用 capabilities/role，不把 Supervisor 放进项目交付门禁。
- [x] 测试完整 DAG 可结束；不完整 guided partial 无批准不能结束；批准有效才可结束；过期批准拒绝；dag_record partial 和 standard 普通问答保持可用。
- [x] 测试 Schedule 模式纯文本不能绕过策略；实际后台工作尚未完成时连续两次 stop 不代表任务完成；后台完成消息到达后能够继续处理。
- [x] 测试同一版本反复退出只生成一份审批；等待裁决期间 fake LLM 请求数不增长；裁决拒绝后的反馈明确。固定上限的无进展回归必须最终进入可恢复非成功状态，不无限循环。
- [x] 用 asyncio.Event 覆盖门禁检查期间收到消息/用户取消/服务关闭：消息不丢，取消优先，任何检查或迟到批准都不能在取消后启动新 run/LLM。
- [x] 更新 UI/API 状态说明（如受影响），区分 run 结束和科研交付完成；调整原有仅断言 unaudited partial 的测试，不直接删掉反例。
- [x] 运行 `uv run pytest -q tests/test_runtime_v2_completion_gate.py tests/test_runtime_v2_pipeline.py tests/test_runtime_v2_dag_stage.py tests/test_dag_completion.py tests/test_dag_exit_approval.py tests/test_runtime_v2_supervision.py tests/test_runtime_v2_cancellation.py`。

## Task 5：停止、传输与进程回收修复（发布门禁）

- [x] 按 Task 0 证据修复取消传播。将 detached finalize 纳入 runner/core 的任务所有权登记，完成后移除；用户取消及 shutdown 会取消并 await 同作用域后台任务。正常成功时仍可异步 finalize，不能重新阻塞主运行结束。
- [x] cancelled 收尾只写本地可确定的交接/终态，不启动摘要 LLM；failed 的自动收尾同样不得借此形成无限调用，重试保持有界。
- [x] 每次实际 HTTP 发送及 retry/fallback 前检查当前执行是否仍获准运行，检查与传输取消配套；仅在外层捕获 CancelledError 不算完成。异常处理不得吞掉取消并转入 fallback。
- [x] 修复 lifespan shutdown 的先后顺序与客户端关闭；测试关闭时仍有 runner、Supervisor、finalize 和 SSE 四类活动，关闭完成后没有新增请求或残留归属执行。
- [x] 审计 `js_runtime.py`、`compute_executor.py`、`monitor.py`、`compute_utils.py`、`daemon_supervisor.py`、`calculator.sh` 的子进程归属及退出路径。针对观察到的 orphan MACE 服务定位启动者，修复父退出/显式全停时的归属回收；不要把正常允许独立运行的计算守护进程当作孤儿一概杀掉。
- [x] 用短命测试子进程覆盖：父正常关闭、取消、被 SIGKILL；核实哪些路径能保证子进程退出。必要时增加父存活检测或所有权清理机制，不能声称父被 SIGKILL 时 finally 仍会执行。
- [x] 明确全停操作入口，优先复用已有 CLI；若缺失，增加可测试的最小显式入口，先关闭控制面/自动拉起方，再终止归属执行与计算，等待回收并复查。不给普通 agent cancel 扩大杀进程范围。
- [x] 运行 `uv run pytest -q tests/test_runtime_v2_cancellation.py tests/test_llm_cancellation.py tests/test_runtime_v2_supervision.py`，保留 fake 服务请求计数和进程退出断言作为发布证据。

## Task 6：清理、文档与总验收

- [x] 查找残余同步装配，包括 API user_replan 与 benchmark；迁移现有调用方，删除不再使用的 GraphSupervisorResult、旧独立 session 生命周期和只验证壳状态的测试，不保留隐藏同步回退。
- [x] 更新 AGENTS.md、角色说明和相关架构文档：真实独立 Supervisor、信箱事实来源、取消/失败策略、恢复与反馈边界。
- [x] 语法检查实际改动 Python 文件：`uv run python -m compileall -q <改动文件>`。
- [x] 运行 `uv run ruff check cloudra tests` 和 `uv run pytest -q tests/`。
- [x] 若更改 JS host，运行对应 npm 测试；若改前端/API 消费 UI，执行 `npm --prefix frontend run build`。没有这些改动不额外改动依赖。
- [x] 审阅 diff：工具后处理无督导 LLM await；不存在壳执行双轨；没有新 review worker、轮询 daemon、合并窗口；权限未放宽；全部新 runtime 状态可重放。
- [x] 按完整可测任务提交相关文件；向用户汇报实际测试结果、残余限制及是否需要重启服务，不替用户启动生产运行。

## 最终验收标准

1. 慢督导不阻塞研究工具完成；24 日志场景不再把 24 次督导耗时串入主 agent 的 JS 执行。
2. Supervisor 是普通运行时 agent，工具调用出现在其自身持久事件流，取消其 runner 就取消实际工作。
3. 每项目一个 Supervisor；运行中仅接收通知，正常休眠可唤醒，用户取消/失败不反复自启。
4. Supervisor 读取证据不会产生自身复核循环；pending 已裁决后不会因旧通知重复工作。
5. 待审批草稿、显式督导请求、工具 review 三类入口完整保留，科学权限和 DAG 门禁不退化。
6. 结束边界无漏唤醒；通知丢失可由持久待办恢复，重放本身无执行副作用。
7. Coordinator 收到一次有效报告并保持运行上下文；取消状态不被报告复活。

8. 用户取消后不产生新的摘要/重试/fallback LLM 请求；真实传输与后台收尾被取消，不能仅有 UI 终态。
9. 服务关闭及显式全停的归属进程得到回收，无自愈复活；本地 fake HTTP 请求计数和子进程测试通过。
10. 明确区分已发远端请求不可撤回与本地停止失效，实施报告说明取消保证边界。

11. 研究工具和计算终态不自动送审；24 份探索证据只选择 2 份时仅产生对应请求。
12. 批量提交原子且声明幂等，裁决以不可变证据为依据；历史自动 pending 不会在升级后触发审查风暴。

13. 显式 stop 与纯文本最终回复经过唯一结束门禁；不完整 guided 交付不能以 unaudited partial 绕过批准。
14. 正常后台等待、Supervisor 信箱休眠、standard 问答和用户取消保持可用；结束审批及缺口反馈不会形成无限 LLM 循环。

## 给 k3 的执行提示

按 Task 0、1、2、2A、3、4、4A、5、6 顺序执行；Task 0 取证回归最先做，已定位的停止失效可提前修复，Task 5 是不可省略的发布门禁。后续，先用 fake LLM + asyncio.Event 验证因果链。目标是复用现有 agent 系统，不是再造后台复核系统。若当前 checkout 已包含 review-worker 或相近重构，先对照以上验收标准复用/收敛，避免叠加第三条执行路径。遇到与现有语义冲突时在实现报告说明具体冲突与选择，不悄悄放宽取消、权限或持久性要求。

## 修订：显式送审的通知所有权（2026-09-06 追加）

`submit_evidence_for_review` 只验证并持久化 explicit review；真实 `dag_bind_evidence` 成功返回后，由运行时 DAG policy 的完成钩子（`DagPolicyStage.after_tool` → `DagController.on_tool_finished` → `_trigger_supervisor_after_tool`）按新建 review 回执（`review_id` + `enqueued=True`）通知 Supervisor。直接存储调用不启动督导；中断窗口由 reconcile 扫持久信箱恢复。工具完成本身不自动筛选研究证据。

送审方法内部不再持有通知副作用——工具自建的无 core 控制器曾使内部通知静默跳过（真实 bind 成功入库但 Supervisor 不被唤醒的断点，见 `docs/superpowers/plans/2026-09-06-dag-guided-submission-notification.md`），通知唯一所有权收敛到运行时完成钩子后消除。
