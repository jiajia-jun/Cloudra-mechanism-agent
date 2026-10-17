# Durable共同阻塞诊断（2026-10-18）

**状态更新：旧done→Freq未接续阻塞已由系统恢复，以下旧诊断作为历史保留，不再代表当前无提交。当前Freq/IRC/端点Opt-Freq已实际执行，转为endpoint geometry mismatch；直接文件/哈希/量化对照见[当前端点几何审计](ENV_ENDPOINT_GEOMETRY_AUDIT.md)。不得因工程量化证据直接认定严格通过，IB10错物种与IA8模式问题独立。**

仅公开ts_inspect、现行[TS SOP](../../docs/TS_PROCESS_SOP.md)、[PROCESS](../../PROCESS.md)及原生日志只读检查；未读应用源码、修订run、增预算、编辑状态或原证据，未手跑TS/IRC。

## 当前结论
四个run为**已完成TS优化后未自动调度频率的工程推进缺口**，不是已证化学失败，也不是缺少frequency方法声明。没有公开可调用的reconcile/推进动作可供本env角色修复；inspect是只读且不会触发推进。原owner已有resume失败/无变化的尝试，反复改无关字段不构成可靠修复。需运行时维护者通过受权机制核终态事件消费与阶段结果认可；不能由Agent手改状态。

## 权威状态实测
|题/run|inspect call_id|revision|TS job|状态|
|---|---|---:|---:|---|
|IA8 ts_0001|tc_0488153d580d48fb|23|739|waiting/refine|
|IA1 ts_0002|tc_c7136ed8273e47d1|43|760|waiting/refine|
|IA9 ts_0003|tc_91134cf0d0fc41a0|18|751|waiting/refine|
|IA5 ts_0004|tc_deb223e3a24a4e87|25|756|waiting/refine|
四者均blocked=null、failed_attempt=null、next.action=wait_for_system、required_inputs=[]、editable_groups=[]；所有当前ts_opt均state=done、actual/planned contract matched=true。频率及IRC planned配置可解析但actual=null，frequency_analysis=null，未见frequency产物。历史ts_0002 job752失败是旧尝试，不能覆盖新760正常终止证据；IB9 ts_0005扫描失败是另一类阻塞，不纳入此共同缺陷。

原生直接证据（grep及sha256只读，退出0）：
- [IA8 739](../../ts/ts_0001/jobs/declaration_0003/ts_opt/.cloudra/calc-739.out.log)：第4516行OPTIMIZATION HAS CONVERGED、第4923行ORCA TERMINATED NORMALLY；sha256 b16c54c6ad940bb2a9df2b44c8b74309878e798b6119c56a8fd2c3403c471490。
- [IA1 760](../../ts/ts_0002/jobs/declaration_0007/ts_opt/.cloudra/calc-760.out.log)：1427/1864行；sha256 e0c9d84017326028a5b0ad8d452f301b7e7a0ec58cd8f847520a161b53c22081。
- [IA9 751](../../ts/ts_0003/jobs/declaration_0003/ts_opt/.cloudra/calc-751.out.log)：8950/9376行；sha256 aabc1d07ec11630cc9e42949b2ad03a40c1a5d3df0988a9fbae7d18de91777d0。
- [IA5 756](../../ts/ts_0004/jobs/declaration_0004/ts_opt/.cloudra/calc-756.out.log)：20238/20672行；sha256 7c9c7b0c7e597957ebe8d873cbc68be880e123507671bc4c112af9cfa84e1275。
收敛与正常终止只证明优化完成，不能代替一虚频/模式、IRC与端点验收。

## 可修复输入 vs 当前工程故障
四者TS opt均frequency_mode=auto；TS frequency均numeric，basis_set显式空，engine=orca，方法GFN2-xTB/GFN2-XTB（IA5为XTB），无planned_error。IA8还正确把端点opt设auto、freq设numeric，但仍同样卡住；因此共享“缺numeric声明”不是本故障解释。

**预防性输入修正**：IA1/IA9/IA5的reactant_opt/product_opt planned仍frequency_mode=numeric，来自复用freq profile。此前同项目出现过非Freq任务numeric冲突，故将来端点优化可能失败。原owner可在相应verification端点optimization配置独立补frequency_mode="auto"，保留端点frequency="numeric"及全部方法/块；不要改共享profile而损坏frequency。这是有科学/写入理由的后续输入修正，不是已验证的当前refine解锁参数。具体嵌套字段由owner读取自身实际ts_resume合约后构造，不凭SOP猜请求schema。IA9已interventions=2/max2，PROCESS记录ts_resume tc_87c3e5e99c96434b被intervention limit exhausted拒绝，不增预算或改状态规避。该项已即时广播owner。

## 最小工程修复需求（不是已定位实现根因）
1. 受权维护者核四job的终态通知是否已被对应owner/run接纳；保留输入修订/方法契约/日志摘要，正常重放不得重复TS opt。
2. 核ORCA外部MLIP的正常结束/优化收敛如何进入阶段成功判据。协调者报告log_parser无常规SCF块而text fallback；它是可辨别假说，不是已证实现bug位置。终态事件未消费与结果判据未认可需分别检查。
3. 若结果未合格，应返回明确failed_attempt/blocked原因，而不是done作业仍wait_for_system；若合格，应幂等接续独立numeric TS频率，保持历史证据不变。
4. 然后才验证频率→目标模式→IRC→端点Opt/Freq；不可把队列done直接改为verified。
5. 提供受权runtime reconcile/修复入口或维护者修复发布；当前env工具只有inspect。get_tool_docs请求ts_resume/ts_prepare失败call_id tc_1b5b443f0fc744d9：Unknown or unavailable tool names。此为本角色能力边界，不证明owner没有resume。

## PM7经PySCF正式链
[接口审计](ENV_PYSCF_PM7_AUDIT.md)与PROCESS记录IA8 job768实际PySCF as_pyscf_method→ASE→MOPAC PM7单点/梯度成功；这使程序调用可用，但不创建durable后端。现行SOP正式阶段写入器是ORCA/Gaussian，没有已核MOPAC/PySCF writer、方法原生输入契约、频率模式parser、IRC产物与端点绑定。故**正式PM7 TS/IRC仍属工程适配未支持/未验收**，不以shell替代；普通Freq可在普通授权计算范围保留MOPAC FORCE原生证据，但不能冒充durable TS frequency。新增后端须先支持能量口径/梯度单位/收敛与原子映射审计，完成真实全链再宣布验证。

## 附录：协调者新增复核（成功与失败终态均未消化）
本节依据协调者直接复核交接，env未重复检查/试修，保留上述四run原诊断。

- **IB9 E1 ts_0005/job780**：[原生日志](../../ts/ts_0005/jobs/declaration_0006/ts_opt/.cloudra/calc-780.out.log)，E=-15.18111429073 Eh，sha256 fb6690201d54c46dafa1b9f30bfc8d82ebe832d02a7b05614c651f9f9511c531；log_parser tc_4e64633f34c24f49 正常终止/优化收敛均true；inspect tc_94e46a7e28e94289仍waiting/refine，无Freq。此前ts_0005仅扫描失败的记录为历史状态，现已成为新的收敛候选复现。
- **IB10 ts_0007/job785**：[原生日志](../../ts/ts_0007/jobs/declaration_0003/ts_opt/.cloudra/calc-785.out.log)，E=-15.10714640019 Eh，sha256 7332bc79104f83e46148da1ddc8fbcd6deb97684861e8e45ba124b4740a7e4df；log_parser tc_637d68ec31ac44d6 正常终止/优化收敛均true；inspect tc_1796a8d81de740a1仍waiting/refine，无Freq。路径由协调者按已亲读的同一原生日志补齐，不改原证据。
- 因而协调者已复核**共六个优化收敛候选未启动频率**；它们仍不是六条已验证反应边。
- **对照失败：IB9 E2 ts_0009/job789**：[原生日志](../../ts/ts_0009/jobs/declaration_0003/ts_opt/.cloudra/calc-789.out.log)达到最大优化步数，原生NORMAL但opt_converged=false（log_parser tc_ae5e031211524dce）；sha256 23ce2e54a55dec682ca173b2cebe7c775edc43e833c0f69f8c5233af8ff84437。inspect tc_5ed41d3c494b4511 revision18仍waiting/refine，blocked/failed_attempt=null，无required_inputs。此项是**失败结果未被流程消化**，绝不是第七个成功候选；不能报垒，也不能仅因一次未收敛断言TS不存在。

最小工程修复必须同时覆盖两类终态：成功结果认可后幂等接续频率；未收敛结果写明失败原因并进入合法恢复检查点，不应两类都无条件停留wait_for_system。该对照扩展了复现范围，但仍不确定具体根因；不再启动试修或改run。

## 当前恢复复核与combined方案判定
本轮能力目录仍只有只读ts_inspect，没有受权runtime repair/replay/reconcile/advance。get_tool_docs回执 tc_62b94a60b37b4f7d 为Unknown or unavailable；**env无修复权限/工具**，不能将AgentHub通知当成运行时修复调用。向平台维护者上报下列call_id是当前可做的追踪动作，Agent不能重放未知副作用或改状态。

- IA8 [current_recovery_evidence.json](results/IA8/current_recovery_evidence.json)记录ts_resume tc_f4837158d0b94d28，tool_exception、effect_state=unknown；随后inspect tc_5e586421a75c45f3显示部分IRC auto/TightSCF声明写入，但频率/IRC actual=null。不是完整无副作用失败，不盲目重复请求。
- IA1 [recovery_round_latest.json](results/IA1/recovery_round_latest.json)记录恢复后inspect tc_4aa77b495b0d4a06 revision45；协调者报告内部失败后planned写入，不能推断已提交后继作业。
- IA5 [RESUME_AUDIT.json](results/IA5/RESUME_AUDIT.json)由owner复核：inspect tc_109cecf4c6644864、tc_3c80bf39664b4816均revision26，compute_actions=2，仅753/756；全部必要auto/numeric/TightSCF声明已齐；ts_resume tc_6b582c49f0ea4070业务拒绝no input change or failed attempt to retry; use ts_inspect，无Freq/IRC部分提交。故不能以缺声明为由继续重复。
- IB9最新verification已正确、inspect tc_5e905e2abde34e0e仍780 done却等待terminal（协调者交接）。

**combined OptTS+NumFreq**：科学上真正最终几何Hessian可用于模式分析，不能用优化初始Calc_Hess替代。但IA8原owner读取实际ts_resume完整公开合同后确认：ts_optimization虽有keywords/frequency_mode通用字段，未明示combined会生成或绑定独立verification.frequency证据；因此当前不能确认writer合同允许或会认可，不能凭通用字段盲试。即便ORCA可算，外部MLIP最终Hessian也不会自动补常规SCF块，更不保证修复终态接续；双向IRC及ts_guess strict pass仍须真实完成。env已直接与IA8/IA5沟通，不并发改run，未执行未获明确支持的组合。

## 下一步与交接
已向协调者及owner即时广播四run实测、端点opt的预防性修订及边界。本轮普通端点、接口有限差分与补充搜索已经收口（见[总表](EDGE_STATUS.md)）；六条收敛候选的正式链需工程接续，789失败需恢复检查点，不反复浪费TS优化。未找到可以确保从当前refine推进的纯输入修复；这不意味着题目设计失败或反应不可达。
