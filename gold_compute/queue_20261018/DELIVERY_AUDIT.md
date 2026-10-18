# IMP用户交付库存审计

## 最新收口：两题尚未移出，代码已恢复（覆盖下文旧后续计划）
用户允许回填或移出IA8/IB9，协调选择后者；registry编辑被后端权限闸拒绝，先行生成器/loader改动已回滚。协调亲核原SHA并独立测试（tc_876f7f99bd474bfa，exit0），实际仍12题、IA8/IB9仍加载，生成器check通过；不是已完成12→10。原定义/JSON/日志/数值保留，没有新Gold、QM或strict。拒绝原因与变更/恢复证据见[重分类实际记录](IMP_RECLASSIFICATION.md)。需平台接入已有用户授权后才能真正排除，本轮为权限阻塞的部分交付，不另放配置绕过。

2026-10-18；回答“还有能算没算的、成果是什么、回填了吗”。这是文档合成，不是新增计算授权或科学验收。
依据：[最新PROCESS](../../PROCESS.md)、[逐边总表](EDGE_STATUS.md)、各题报告与下列原生证据；以最新追加结论覆盖报告保留的历史等待措辞。

## 一、先给结论

- **范围为12题：7个反应题共9条边，另5个非TS性质/态序题。** 不能以9边总表宣称12题全已完成。
- 9条反应边均有实际尝试；6个收敛TS候选都有最终频率，其中5题已真实双向IRC。这是计算覆盖，不等于目标路径合格或物理Gold。
- **当前0 strict pass、0新增可信目标barrier，正式Gold未回填。** 数值收敛、单独一虚频、strict pass本身都不能自动背书物理精度。
- 有可复用结构、频率、IRC、接口与防错回填成果；也有5道未完整做的性质题。未做不等于算不出，搜索未成功不等于物理不可达。
- 当前无后台计算。IA8新接口已实际复验仍fail；IB9故障恢复审计已结束，新组件验收未完成，不继续等待失败owner。最新转为排除两题，但被编辑闸阻塞并已回滚；不恢复QM/strict循环或泛开新难题。

## 二、反应题实际成果及为何未交付目标垒

|题/边|可审计成果|当前限制与交付取舍|
|---|---|---|
|IA8 E1|本轮834 TS优化、835最终频率、836双向IRC；836自身B→R841、F→P840均正常/收敛/零虚频，原序及开链/三元环身份、方向证据较强|最新新接口tc_58fab4b3a3644b26已传841/840端点日志，仍mode fail、未返回端点check，见[新完整回执](results/IA8/new_verification_review/e5b2d829/result.json)；不说端点连错。方法/电子态适用性风险独立，非Gold|
|IB9 E1|目标环加成模式与798真实IRC；吡唑啉端821零虚频；742/745单体可复用为明确分离参考|整体822/833/839仍两软负频如实保留，但用户已允许TS/IRC通到该身份正确接触体、不再要求整体0虚频；742/745为分离参考，不冒充整体minimum。新版组件验收因owner故障未完成，旧真实返回inconclusive missing TS geometry，见[恢复审计](results/IB9/new_verification_review/recovery/RESULT.md)；不是新拆分方案已被否决，仍无pass/Gold|
|IA1 E1|真实频率/IRC（最新829/830），同源823/824双零虚频且固定map矩形键互换；原字节12文件bundle源目标SHA一致|strict仍inconclusive missing TS geometry；异常大虚频−4610.8及方形静态关联风险独立。bundle valid/aligned不等可信物理垒|
|IA5 E1|792一虚频、799真实IRC与完整逐帧旋向审查|实为顺旋竞争，不是题设反旋；排除本候选目标回填，是防错成果|
|IB10 E1|795频率、802 IRC及零虚频外端揭示连接|实为O–N五元环旁路，不是目标脱N2；排除目标回填，几何精度问题不能洗掉错物种|
|IA9 E1|751收敛、791最终一虚频；普通xTB/PM7端点已算|尚无IRC。用户追加1干预已同意，但后端拒raise authorized limits，额度未接入，不写已生效|
|IA7 E1|Z起点/环状骨架独立Opt/Freq均零虚频|目标开壳单重态未证，接口electronic_state_backend_unsupported；无TS/IRC，不以闭壳m1冒充目标态|
|IB9 E2|实际CN扫描与耦合IDPP/OptTS789尝试|789优化未收敛，不能把NORMAL字样、扫描末点或峰当TS/垒；RDS未定|
|IB10 E2|指定迁氢path/扫描及普通产物尝试|路径/扫描未收敛；卡宾种子775塌至ketene，目标卡宾minimum未验，不证明不存在|

关键源文件：
- IA8：[报告](results/IA8/REPORT.md)、[834日志](../../ts/ts_0001/jobs/declaration_0007/ts_opt/.cloudra/calc-834.out.log)、[835日志](../../ts/ts_0001/jobs/declaration_0007/frequency/.cloudra/calc-835.out.log)、[836日志](../../ts/ts_0001/jobs/declaration_0007/irc/.cloudra/calc-836.out.log)、[P840](results/IA8/endpoint_strict_review/.cloudra/calc-840.out.log)、[R841](results/IA8/endpoint_strict_review/.cloudra/calc-841.out.log)。
- IA8：[同源端点比较](results/IA8/endpoint_strict_review/endpoint_comparison.json)、[strict全返回](results/IA8/endpoint_strict_review/strict_own_endpoints.json)、[env有限行为审计](IA8_STRICT_BEHAVIOR_AUDIT.md)。本次返回仅有一虚频/mode检查、IRC paths为空；没有端点配对/方向check，不推断永久内部顺序。
- IB9：[报告](results/IB9/REPORT.md)、[794频率](../../ts/ts_0005/jobs/declaration_0006/frequency/.cloudra/calc-794.out.log)、[798 IRC](../../ts/ts_0005/jobs/declaration_0006/irc/.cloudra/calc-798.out.log)、[821](results/IB9/independent_endpoints/F/.cloudra/calc-821.out.log)、[833对照](results/IB9/tight_review/COMPARISON.md)、[839结果](results/IB9/hessian_step_review/RESULT.md)及[原生日志](results/IB9/hessian_step_review/.cloudra/calc-839.out.log)。
- IB9：[完整strict记录](results/IB9/independent_endpoints/STRICT_FULL_RECORD.json)、[分离组件映射/同级证据](results/IB9/component_review/COMPONENT_REFERENCE.md)。839原生证明初始加三次周期重算Hessian，末NumFreq另一次；不将“输入有标签”当实际次数。
- IA1：[报告](results/IA1/REPORT.md)、[最新原生链目录](../../ts/ts_0002/jobs/declaration_0013/)、[823](results/IA1/independent_endpoints/R_B/.cloudra/calc-823.out.log)、[824](results/IA1/independent_endpoints/P_F/.cloudra/calc-824.out.log)、[bundle manifest](results/IA1/strict_native_bundle/manifest.json)、[strict返回](results/IA1/strict_bundle_result.json)。
- 防错及其余限制：[IA5旋向审计](results/IA5/ROTATION_AUDIT.md)、[IB10报告](results/IB10/REPORT.md)、[IA9报告](results/IA9/REPORT.md)、[IA7报告](results/IA7/REPORT.md)；两E2原生日志详见[逐边证据索引](EDGE_STATUS.md)。

## 三、非TS的5题：尚有未完整做的库存，但不应泛开

有限审计范围：读取5份TaskSpec及本轮results目录，不是全项目历史搜索。AgentHub researcher报告evt_fb792cb8945d4092及修正evt_8b4a9562344e461c确认：五题无独立本轮结果包/完整交付，spec的reference_properties为空；本次库存目录亦仅有7个反应题目录。

|题与原始定义|已有/未做|适当边界，不是开算承诺|
|---|---|---|
|[IC3 苯基氮烯态序](../../ideapool/tasks/impossible/IC3.json)|本轮未完整做单三态差及最低单态性质|研究者指出普通spin-independent GFN2直接限制gap解释，不能凭m1/m3收敛认目标开壳态|
|[ID2 FOOF结构/BDE](../../ideapool/tasks/impossible/ID2.json)|本轮未完整做|FOOF几何Opt/Freq是唯一较合理的有条件新子目标；异常成键仍需精度核验。F/FOO开壳碎片及BDE不预承诺|
|[IE2 N2解离曲线](../../ideapool/tasks/impossible/IE2.json)|无本题完整包；但N2平衡组件748已做，可复用|不要重复算N2平衡点。曲线、N原子m4、正确解离态及De/D0仍未交付，平衡点不替代整题|
|[IF3 三角烯态序](../../ideapool/tasks/impossible/IF3.json)|本轮未完整做|同类GFN2自旋处理限制，不能把普通态差直接认真实最低态序|
|[IG8 Cr2曲线](../../ideapool/tasks/impossible/IG8.json)|本轮未完整做|强关联高风险、低优先；不把任意收敛曲线当六重键可信参考|

IE2可复用源：[748输入](results/IB9/calc/frag_n2/frag_n2.inp)、[原生几何](results/IB9/calc/frag_n2/frag_n2.xyz)、[原生日志](results/IB9/calc/frag_n2/.cloudra/calc-748.out.log)。协调/研究者已核同GFN2正常、优化收敛、零虚频，N–N约1.0982 Å、唯一伸缩2437.61 cm⁻¹；只作平衡组件，不补成解离能/曲线。该复用事实纠正“IE2完全无可用计算”的过强表述。

## 四、接口与方法内端点成果，也不是目标能垒

IA8已实际打通PySCF通用scanner→自定义回调→ASE/MOPAC PM7；不是PySCF原生PM7 Hamiltonian。
[桥接原生输出与字段](results/IA8/pm7_bridge/results.json)、[原生R输出](results/IA8/pm7_bridge/CH2OO.out)、[PM7最低点全索引](results/IA8/pm7_validate/refined_results.json)及[报告](results/IA8/REPORT.md)保留。
IA8两PM7模型内minimum的ΔHf_model=−21.867740 kcal/mol，含bits、未另加显式ZPE/热项，不叫严格物理0 K电子能；频率是自编全Cartesian梯度差分并投影刚体运动，不是MOPAC FORCE。它是接口/端点成果，不是xTB或PM7反应垒，不跨方法混减。

## 五、到底回填了什么？

1. **本轮没有新增正式Gold或可信目标barrier回填。** 根目录mechanism_graph.json本次只读ls未发现；AgentHub env有限审计evt_1d76a0aa42d444f1的限定git状态未见registry/TaskSpec工作树改动，不是跨全历史/全字节不变证明。本次交付未改root图/registry。
2. **不能说“任何图都没有数”。** [IA8局部非Gold草稿图](results/IA8/mechanism_graph.json)确有历史独立端点性质isomerization_energy_kcal_mol=−31.1871478816，来源[729](results/IA8/explore/.cloudra/calc-729.out.log)/[730](results/IA8/explore/.cloudra/calc-730.out.log)。它不是barrier、不是正式Gold，也未被840/841替换。
3. IA8 owner仅更新局部图过时status/证据说明：现写有834/835/836及840/841，strict仍fail且未返回endpoint-match。原性质数字与729/730来源保留，无新增barrier。局部accessible=false为历史未认证标志，不作物理不可达裁决。
4. 正式交付区分三层：原生日志/方法内计算成果；未通过或不适合目标的候选；通过科学审查的Gold。当前前两层有实质库存，第三层新增目标垒为0。

## 六、工具修复后的优先次序（非新增授权）

优先澄清IA8现有同源端点与模式验收的能力关系、IB9完整体系/分离参考及strict中心消费；然后仅在额度合法接入时恢复IA9。每项仍须目标身份、电子态、模式与物理适用性审查，strict pass不是充分条件。
不为凑数重复QM、改watch/阈值或改原生日志；不重算已有N2平衡点，不泛开五道性质难题。ID2结构子目标若未来另获授权，可先限定低风险验证范围；本审计不授权开算或承诺BDE。
