# NU3 路径工具与部分交付修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 删除本轮已复现的机械阻塞，提供真实原生扫描候选与短引导，再用同题同方法复跑。

**Architecture:** 复用已有扫描、DAG有效报告、消息事件和单槽提示。不新增公开字段、配置层或科学前置门；未完成交付如实保留缺口。

**Tech Stack:** Python/Pydantic、runtime-v2事件、原生ORCA/xTB、pytest零API场景。

**Spec:** 本聊天用户授权与 AGENTS.md；上轮证据 research-subtraction-normal-NU3-20261014-73733325/diagnosis/agy-decisions-engineering-20261014.json，以及AGY已确认的部分交付/两句话提示裁决（同目录保存）。

## Global Constraints

- 上轮已正式结束，51项计算全部终态且锁释放；旧源码与证据不再修改。
- 不改题目、方法、Gold、rubric、评分权重和阈值，不向活Agent发送纠正或Gold。
- 新注入最多当前一条两三句话，详情给路径；保留历史事实但不重注入历史。
- 不新增模型手填版本、哈希、幂等或恢复字段；内部并发和不可变证据仍由程序负责。
- 本地仅跑相关模块，compileall/ruff和真实回归；全套交CI。测试不得读取真实运行数据目录。

## Review Focus

- 边界是全局最高点但内部存在局部峰时，不能丢失现有原生候选。
- ORCA同步双坐标输出的第二坐标不能被当作能量；独立网格不能被当作一维路径。
- 正式审查通过的目标在prompt和查询中显示相同有效结果；验收标准不变。
- 部分交付不能逼未找到TS的边填写错误鞍点；额外探索材料不能被强迫删除。
- 同子Agent的新任务能回报并唤醒父Agent；计算唤醒不重复完成回报，权限不变。

## Task 1: 原生扫描能力与候选

**Files:** cloudra/tools/core/ts_inputs.py、ts_process.py、calculation_intent.py、xtb_scan_runner.py、cloudra/tools/Chemtool/ts_guess.py、log_parser.py及相应tests。
**Interfaces:** 保留现有ScanGuess.scans/mode、TsGuess.scan_mode和provided-guess路径；不加公开字段。
- [x] 先复现两坐标ORCA拒绝、同步多列能量解析和边界最高点掩盖局部峰。
- [x] 对显式concerted双坐标写原生Simul_Scan true并正确传递已有mode；不扩大到不支持的网格语义。
- [x] 切换引擎仅清理继承的不适用参数，不暗改显式科学输入。
- [x] 暴露局部峰的点号、能量和原生XYZ；一个候选可继续，多候选通过既有provided接口选择。
- [x] 修正无峰/路径候选表述与原生日志引用，跑相关模块并独立审阅。

## Task 2: 有效DAG报告与诚实部分交付

**Files:** cloudra/dag/delivery_artifact.py、stop_audit.py、controller.py、completion.py、cloudra/tools/Plantool/dag_tools/dag_view.py、_common.py及相应tests。
**Interfaces:** 复用controller.delivery_report既有有效结果；stop已有delivery_disposition=partial。
- [x] 先复现正式accepted但prompt/view仍pending、未决边via=null被拒、探索extra被拒。
- [x] view/prompt沿用正式报告的同一验收结果，不复制新状态。
- [x] 部分交付可保留未决via=null和无能垒；探索extra明确不产生DAG完成信用。
- [x] 已验收/声称验收的科学与日志完整性检查保留；评分实现不改。
- [x] 跑相关DAG与completion模块回归。

## Task 3: 子Agent交接

**Files:** cloudra/runtime_v2/hub_bridge.py、subagent_bridge.py、tests/test_runtime_v2_hub_bridge.py、test_runtime_v2_subagent_bridge.py、test_agent_scenarios.py。
**Interfaces:** 复用注入消息ID、现有manifest/父子关系与terminal_event_id，不新增公开任务ID。
- [x] 先复现复用子Agent二次任务完成被抑制、已分配任务答案驻留不唤醒。
- [x] 分配投递前绑定真实父子关系；每次真实任务完成去重，计算/提醒不重置任务。
- [x] 期待的科研回报唤醒等待父Agent，真实call/spawn/tool权限检查不变。
- [x] 补零API复用任务场景与恢复不重复测试，跑对应模块。

## Task 4: 短提示与共享笔记

**Files:** cloudra/runtime_v2/notices.py、policies/guidance.py、cloudra/runtime/prompt_assembler.py、cloudra/prompts/supervisor.md、cloudra/tools/core/ts_process.py及相应tests。
**Interfaces:** 复用当前单槽科学提示，不增预算配置或恢复协议。
- [x] 复现同一批多个旧提示更新进入下一轮上下文；只保留最后有效的一条。
- [x] 优化不收敛时两句话区分初猜失败与通路不存在，并引导读原生日志/改变工具初猜。
- [x] PROCESS引导做增量证据更新，区分已算/待提交/已审查，未经检验解释仍为假设。
- [x] 人类可读键对错误按公开1-based显示，不改内部原子映射或科学判据。

## Task 5: 验证与新轮

- [x] 各修复拆小本地commit，朴素消息；不自行推送。
- [x] 相关模块、compileall/ruff、JS宿主验证；一次独立审阅，修确认缺陷。
- [x] 正确cwd导入新源码，只读重评上轮，记录模块来源；直接基线正式0.2491。
- [ ] 保存新题目输入授权清单、provenance并冻结源码，用现有授权模型启动一次。
- [ ] 更新已有observer与heartbeat指向新轮；期间只读，终态再判真实科学验收和正式分数。
