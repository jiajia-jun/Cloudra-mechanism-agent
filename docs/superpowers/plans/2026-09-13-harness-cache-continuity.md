# Harness 缓存连续性与全历史压缩实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. 未经用户要求不提交、不推送。

**Goal:** 消除 harness 自己造成的前缀失效，并通过同条件实测证明缓存命中率提高，同时保证压缩覆盖各轮工作且不静默丢失用户要求。

**Architecture:** 一个 agent 的模型上下文跨 run 连续，只追加已经确定的消息。静态协议固定在开头；动态观察与通知作为真实历史消息追加。compact 是显式的上下文边界，成功后原子安装新上下文；run 结束和 schedule 唤醒本身不重建历史。

**Tech Stack:** 现有 Python / asyncio / pydantic / EventWriter / pytest；不新增依赖。

**Spec:** 本文件“设计约束与验收”承载本次对话确认的需求；本次仅交付计划，不修改运行代码。

## 设计约束与验收

1. 缓存优先：同模型、同工具协议、无 compact 时，下次实际发送的 messages 必须以此前实际发送的 messages 为完整前缀。检查最终传输输入，而非仅检查 runner.history。
2. 普通工具轮次、用户追加、schedule 唤醒、审批恢复、记忆更新、工作区变化、pin 更新/撤销均不得重写旧消息。
3. “每一轮压缩”解释为每次 compact 覆盖所有历史轮次，不解释为每次 LLM 调用或 schedule 收尾都 compact。否则与缓存目标冲突。
4. 保留用户原始要求、补充、纠正、禁止项、授权范围、交付标准和开放事项；只有用户明确覆盖才标记旧要求失效。助手计划不能冒充用户要求。
5. compact 不允许用空摘要、截断结果或失败占位文本替换历史；输入超限应分段覆盖，无法完成则保留原历史并报告原因。
6. 本地硬门禁：固定协议且未 compact 的测试序列，历史前缀改写次数必须为 0；重试的已准备请求保持一致；通知不重复、不丢失。
7. 真实效果门禁：同 provider/model、工具、任务输入与调用节奏，对照旧版与新版；新版 token 加权命中率必须高于旧版，主流程未缓存输入 token 必须下降。另统计摘要调用成本、总 token 与首 token 延迟，不能靠填充重复文本刷高命中率。未达到则不验收为“缓存改善完成”。
8. 首请求、compact 后首请求、明确模型/工具协议变化分别标记为冷启动；既报告总体指标，也报告稳定区间指标，不隐藏冷启动成本。缺少 provider 缓存统计时记 unavailable，不记 0，也不以本地前缀指标冒充实测。
9. 不修改化学阈值、方法选择、计算取消与进程归属语义。同步 IO 下沉到线程；状态投影仍只经 apply_event，后台工作仍由 track_background 管理。
10. 当前工作树有用户未提交改动；实施前逐文件检查并保留，不清理、不覆盖。无兼容 shim、无额外配置平台。

## 已确认的问题

- turn_pipeline.py 每轮在 history 前调用 prompt_provider；prompt_assembler.py 将 MEMORY/AGENTS.md 合并进身份提示，并刷新前置工作区快照。
- notices.collect 每次重放 pins、排空 pushes，但 agent_runner._append_history 不保存这些消息。
- GoalStage.before_llm 删除已有 goal system 消息；与只追加不变量冲突。
- adapters.py 将 JS instructions 追加到每个请求最后，位置持续变化。
- agent_runner._run 每次创建空 history，context_tree 用最新 HANDOVER 重建前部。
- schedule stop 先 compact 当前 reminder 尾部，随后 run finalizer 又摘要；存在重复摘要与缓存重建。
- compaction._serialize 每条截到 2,000 字符，总量到 12,000 字符即停止；摘要输入缺少被保留的用户指令。context_tree 还截断用户消息与 handover。
- llm_client._translate_responses_usage 只转译输入/输出/总 token，丢弃缓存细项。仅靠现有日志可能无法准确计算命中率。

## 实施顺序

### Task 1：建立最终请求回归夹具和缓存基线

**Files:** 新建 tests/test_runtime_v2_context_cache.py；修改 tests/test_runtime_v2_adapters.py、cloudra/runtime_v2/adapters.py、cloudra/infra/llm_client.py；沿用 llm.completed usage。

**接口:** 保持 LLMProvider.complete 与 LLMResponse.usage 接口；usage 保留原始缓存细项，并测试 Responses 转译不丢 input token details。

- [ ] 用捕获传输请求的 fake client 构造两轮工具调用、pin/push、工作区变更、MEMORY 更新、schedule 再唤醒场景。先在当前实现运行，记录每个场景首次变化的位置；测试必须因前缀变化而失败。
- [ ] 对每对请求断言下面的不变量。序列化使用实际 wire message 内容；不得为了让测试通过而丢弃 role、工具参数、reasoning 或图像字段。

```python
assert current["messages"][:len(previous["messages"])] == previous["messages"]
assert current.get("tools") == previous.get("tools")
```

- [ ] 缓存 usage 测试输入包含 input_tokens_details.cached_tokens；断言翻译后保留相同值。对缺字段、0 值、流式末块分别测试，不将缺失等同于 0。
- [ ] 实施最小 usage 保真修改；只增加必要的请求指纹/首差异诊断，日志不保存 API key 或额外的完整敏感内容。将主 agent 与摘要请求分组。
- [ ] 保存旧版基线：固定场景输入与完整计数、模型/协议、调用间隔；不修改源码回退已有用户改动来获取基线。

**验证:** `uv run pytest -q tests/test_runtime_v2_context_cache.py tests/test_runtime_v2_adapters.py`。本任务完成时 usage 测试通过，已确认的前缀回归暂保持测红，后续任务逐项转绿。

### Task 2：固定静态前缀，动态内容变为追加消息

**Files:** cloudra/runtime/prompt_assembler.py、cloudra/runtime_v2/adapters.py、cloudra/runtime_v2/turn_pipeline.py；tests/test_prompt_assembler.py、tests/test_runtime_v2_context_cache.py。

**接口:** PromptAssembly 的 identity_messages/observation_messages 继续承担静态/动态区分；MEMORY、AGENTS.md 作为带来源的动态指令快照，不再每轮改写 identity。JS instructions 在上下文初始化时安装一次，adapter 不再尾部添加。

- [ ] 添加静态提示与 JS instructions 连续三轮完全一致的失败测试；更新记忆/AGENTS.md/工作区后，旧消息保持原值，新内容只出现于末尾。
- [ ] 将 base prompt、固定技能/工具协议与 JS 说明放入初始前缀；相同内容不重复发送。工具目录继续从 tool_catalog/capabilities 投影，不新建工具名集合。
- [ ] 每轮只读检查动态来源变化；发生变化时追加标明来源及替代关系的新消息。用户指令保留指令权限，工作区观察标明为观察数据。不得为了冻结前缀忽略最新用户规则。
- [ ] 工作区 change 列表以实际观察状态变化为准，避免“上一轮变化列表→本轮无新变化”单独产生无价值消息。
- [ ] 明确模型、工具 schema/协议发生真实变化属于新边界，记录原因；不要在不兼容协议之间伪称缓存连续。
- [ ] 运行 Task 1 对应夹具，确认静态与动态前缀场景转绿。

### Task 3：事件通知真实进入历史，失败与重试不丢消息

**Files:** cloudra/runtime_v2/notices.py、turn_pipeline.py、agent_runner.py、policies/goal_stage.py、policies/dag_stage.py、policies/schedule_stage.py、events.py、apply.py；tests/test_runtime_v2_context_inject.py、test_runtime_v2_goal_stage.py、test_runtime_v2_context_cache.py。

**接口:** 保留 pin/unpin/push 调用面；消费从“每轮重建快照”改为“未应用变更按顺序追加”。变更身份使用现有事件序号，消息进入上下文后才推进消费位置。

- [ ] 测红：未变化 pin 不重复，更新 pin 追加新版，unpin 追加撤销说明；push 发送后下一轮仍在原位置。
- [ ] 测红：网络失败重试使用同一批已准备消息；取消/持久化失败不提前确认消费；连续两次不同 push 不被内容去重误删。
- [ ] 将通知追加纳入统一上下文写入路径；准备请求时固定批次，LLM 重试不能再次 drain 生成不同请求。
- [ ] 删除 GoalStage 对历史 goal 的过滤；已撤销/更新状态通过追加消息表达。DAG、schedule、knowledge 通道遵循相同协议。
- [ ] 状态投影与消费位置通过事件落地，apply_event 唯一应用；事件写入失败不得发送或安装未持久化的新状态。
- [ ] 运行通知、goal 与缓存回归文件，确认重试与阶段注入均转绿。

### Task 4：上下文跨 run 连续，handover 不再自动替换对话

**Files:** cloudra/runtime_v2/agent_runner.py、core.py、context_tree.py、events.py、apply.py、persistence.py；tests/test_runtime_v2_runner.py、test_runtime_v2_context_tree.py、test_runtime_v2_recovery.py、test_runtime_v2_context_cache.py。

**接口:** 一个 session 一份上下文投影；run 仅为执行生命周期。复用现有 EventWriter/事件存储记录实际送模消息与 compact 结果，禁止从展示用 result_summary 反推完整 wire 历史。

- [ ] 测红：普通 stop→用户新消息、schedule stop→reminder、等待审批后恢复都保留前缀；不同 agent 的消息不能串入。
- [ ] 从 _run 局部 history 迁移到 session 上下文投影；发送前追加输入，响应后追加完整 assistant/tool 消息，保证恰好一次。实际模型输入保存文本、工具配对、reasoning 及稳定媒体引用，不能只存工具摘要。
- [ ] 移除正常 run 边界 build_seed_context 重建与每次 stop 自动改写 handover 的主路径。handover 归属于显式 compact 产物；原始事件仍用于审计，不建立重复摘要管线。
- [ ] 重启仅恢复持久化上下文；running/waiting 仍按现有规则落 failed，不自动执行工具、JS 或计算。显式恢复时使用记录的上下文，不悄悄改成摘要 seed。
- [ ] 测试 finalizer 与下一 run 同时发生不会覆盖新历史；取消后的后台任务不得启动新摘要请求。
- [ ] 运行 runner/context_tree/recovery 与缓存夹具；确认跨 run 前缀回归转绿。

### Task 5：compact 覆盖全部轮次，保护完整用户意图

> **决策变更（取代本 Task 下方关于「逐字指令区 / 保留活动工具尾部」的要求）**：
> 压缩改为**全量折叠**——用户指令、assistant 回复与工具调用、工具结果一起进
> 摘要，投影里不留逐字保留区；唯一不压缩的是 harness 前缀（按当前状态重新
> 装配），压缩边界之后到达的输入照常逐字可见。用户意图的无损保证改由摘要
> 契约（objective/active_requests/constraints/corrections）+ 本轮输入承担。
> 同时收紧容量口径（`TokenEstimator`/tiktoken 单一事实源，工具调用参数与
> reasoning 计入）、来源下标越界钳制并计数、摘要调用有界等待（summary_timeout）、
> 多段合并按容量分批、预算触发被拒后退避重试、摘要调用进遥测。不变量与实现见
> `cloudra/runtime_v2/compaction.py` 模块 docstring 与 AGENTS.md。

**Files:** cloudra/runtime_v2/compaction.py、agent_runner.py、context_tree.py；新建 tests/test_runtime_v2_compaction_integrity.py；修改 tests/test_runtime_v2_context_tree.py。

**接口:** 保持 compact 的“返回候选 history 与 stats”形态；调用方只在完整摘要成功、持久化成功且输入版本未过期时原子安装。移除 prior-turn/current-tail 两套重复压缩策略，统一覆盖历史、保留完整活动工具尾部。

- [ ] 测红：三轮用户目标与纠正、两轮 reminder、超过 12,000 字符的轨迹和末尾关键约束都进入摘要输入；超过 4,000 字符的用户消息不得截断。单条超长消息也必须完整分段覆盖。
- [ ] 明确摘要指令，内容采用下列契约，并以结构化字段校验摘要格式及来源引用：

```text
Preserve the original user objective, every still-active request,
constraint, prohibition, authorization boundary, and delivery criterion.
Record user corrections and which earlier requests they explicitly replace.
Do not treat assistant proposals or tool output as user instructions.
Keep completed work separate from pending requests, failed attempts,
unverified claims, evidence paths, computed values, and next actions.
Never drop an unresolved user request merely because it is old.
```

- [ ] 用户原文按消息身份完整保留在 compact 后的指令区，不依靠摘要模型独自承担“无损意图”保证；执行轨迹由模型压缩。摘要模型得到这些完整指令作背景。原文保留不等于旧要求永远有效，纠正顺序与替代关系必须可见。
- [ ] 移除 _serialize 先截断后摘要的行为。根据现有模型上下文容量分块，记录输入区段覆盖；每个区段都成功后再汇总。图像保留可回读引用及已有文本描述，不声称纯文本摘要完整理解图像。
- [ ] 空输出、结构错误、区段缺失、取消、持久化失败、摘要不缩短执行轨迹时均不替换旧上下文。若仅完整用户原文已超可用容量，明确报告无法无损压缩，禁止静默裁剪。
- [ ] 取消每个 schedule stop 的无条件 compact。仅手动 compact、达到上下文预算或实际 overflow 执行；预算使用现有 context_window 与输出预算，估算留余量；不新增用户配置。overflow 重试有界，同一输入无进展不重复压缩。
- [ ] 压缩中收到新消息，只提交被摘要的固定前缀，再保留新尾部；版本不符则放弃候选，不能覆盖新增用户纠正。
- [ ] 失败测试先红后绿；fake 摘要测试证明输入覆盖与原文保留，人工/真实模型检查语义质量，不把字段齐全当成语义完整证明。

### Task 6：实测验收与交付

**Files:** 新建 docs/superpowers/reports/2026-09-13-harness-cache-validation.md；同步 AGENTS.md 相关运行时与 compact 约定；按仓库要求重建软著源程序清单。

- [ ] 建立固定回放：同一用户任务连续工具轮次，穿插工作区写入、记忆更新、pin 更新/撤销、push、用户纠正、多个 schedule 唤醒，最后一次显式 compact。旧版与新版使用相同输入与工具结果；不访问真实科研计算。
- [ ] 分别汇总总体及稳定区间指标，计算方式固定如下；缺失计数单列，不纳入可测比例的分母。

```text
token_weighted_hit_rate = sum(cached_input_tokens) / sum(input_tokens)
uncached_input_tokens = sum(input_tokens - cached_input_tokens)
prefix_mutations = count(non_boundary_request_with_changed_old_prefix)
```

- [ ] 实测匹配 provider/model/路由和缓存有效时间条件。使用多个独立重复任务组交错执行旧/新版，避免单次网络或缓存预热差异决定结论；报告样本数、原始计数、差异和波动，不预先承诺虚构的 90% 命中率。
- [ ] 硬性结果：prefix_mutations 为 0；新版实际命中率提高且未缓存输入下降；用户原文与已授权边界回归全部通过。若 provider 数据缺失或实测没有提升，明确未通过效果验收并继续定位，不以测试通过代替目标完成。
- [ ] 检查摘要调用次数、摘要总成本、任务完成质量与首 token 延迟，防止用频繁 compact 交换表面上下文缩短。确认工具历史配对、事件恢复与取消语义无回归。
- [ ] 按 compileall → ruff → 相关测试顺序检查；跨子系统收尾再跑一次全套：`uv run pytest -q tests/`，直接检查退出码。包含 `tests/test_no_sync_on_loop.py`。不在中间反复跑全套。
- [ ] 执行 `scripts/gen_copyright_source.py` 的仓库规定重建流程，检查生成差异。交付报告说明测试结果、实测改善与剩余限制，不提交/推送。

## 方案取舍

- 只修前置 MEMORY/工作区：改动小，但通知、JS 与跨 run 仍破坏前缀，不能满足本次目标。
- 每个 schedule 都全量 compact：历史更短，但缓存反复冷启动，摘要成本与意图漂移增加，不采用。
- 采用跨 run 只追加、动态更新入历史、按容量全历史 compact：统一解决已确认根因，以可测缓存改善作为最终验收。

## 自检

- 缓存低命中：Task 1–4 消除前缀改写，Task 6 实测，不只看本地历史。
- 全轮次压缩：Task 5 统一范围与触发边界。
- 完整用户意图：Task 5 全输入覆盖、原文保留、失败不替换。
- 重试/重启/取消：Task 3–5 覆盖恰好一次、恢复不执行、并发不覆盖。
- 本计划不修改科研决策、不新增依赖、不进行 git 提交，也不执行真实 provider 调用。
