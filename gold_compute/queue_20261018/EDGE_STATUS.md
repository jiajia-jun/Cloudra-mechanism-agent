# IMP 实算反应边覆盖总表

最新正式交付（2026-10-18，覆盖下方旧库存快照）：2026-10-18：NR1四步、NY3三步、HI1两条syn、HL1两面共11条参考边已实际回填正式JSON并启用准确度评分。IA8/IB10移出，保留IB9首步5.65；全库50题（20/10/10/10）。剩余参考缺测，不自动排算。参照和逐题值见REFERENCE_STATUS.md。 IMP当前5道反应题6条边，除IB9_E1外5边缺测，另5道性质题缺参考；下文12IMP/7题9边/空Gold等为历史，不作为现行选择集合。

## 本轮缺测收口（2026-10-18）

按用户要求，未回填项标为本轮缺测，不再排为待算。IB9_E1=5.65保留，另外8条反应边和5道性质/态序题缺参考；已有科学证据与accessible标签不变。四道替换题的远端新成果也已同步，详见[参考状态](REFERENCE_STATUS.md)。

## 当前结果：保留IB9，首步已按用户确认回填

2026-10-18 用户确认目标反应并明确要求回填，IB9保留在12题有效集合中。**IB9_E1已将历史B3LYP 14.74更新为GFN2-xTB 5.65 kcal/mol**（TS794 − 接触体839，纯电子能）；分离单体参考4.37另列，E2仍缺测。839两软虚频保留，工具仍inconclusive；本次为人工确认的方法内参考更新，未增加strict pass计数。详见[回填记录](results/IB9/GOLD_BACKFILL_20261018.md)。下文未回填/权限阻塞为此前快照，以本段和表内最新IB9 E1行为准。

## 此前收口：排除未完成，已回滚；有效集合仍12题
用户允许回填或移出IA8/IB9，协调选择移出而不强填Gold；registry编辑被权限闸拒绝，生成器/loader先行改动已完整回滚。协调亲核原SHA和只读测试（tc_876f7f99bd474bfa，exit0），实际仍加载12题，包括IA8/IB9；不能改称10题有效集。原定义、JSON和全部科学证据保留。详见[拒绝与回滚实录](IMP_RECLASSIFICATION.md)。本表保留历史7反应题9边工作量，不表示所有边合格。

最新验收事实覆盖下文旧快照：IA8新e5b2d829接口已传同轮835/836/841/840及原watch，仍fail、无端点check（tc_58fab4b3a3644b26，[完整回执](results/IA8/new_verification_review/e5b2d829/result.json)）。IB9用户已允许完整TS/IRC通到身份正确的软模接触体，以742/745零虚频分离组分作参考，不再要求整体零虚频minimum；其新版组件验收因owner故障未完成，旧真实返回仅inconclusive missing TS geometry，不能把整体软负频继续作为新方案的否决条件，见[恢复结论](results/IB9/new_verification_review/recovery/RESULT.md)。两题均未pass/未新增Gold，无新QM或strict循环；本轮按权限阻塞收口。

2026-10-18 本轮科学取舍收稿；仅汇总 producer 的报告与证据，不代作电子态、机制或可达性裁决。范围为 **9边**（IA1/IA5/IA7/IA8/IA9各1，IB9/IB10各2）。依据：[最新PROCESS](../archive/imp-process-20261018.md)、[题目交接](IMPOSSIBLE.txt)、AgentHub「IMP PM7-xTB coordination」及下列七份REPORT。各owner已确认无后台计算、无新增授权；以下以最新PROCESS、owners报告及协调交接覆盖旧进行中/等待措辞，**未闭合不等于物理不可达**。

“最低点”仅指相应模型的优化/频率证据，不保证目标电子态或全局最低；独立端点不等于IRC外端。OptTS完成≠一阶TS；扫描峰≠势垒；入队≠已计算。表中未闭合均不意味着设计不可达。

## 最终取舍：科学可信性优先，strict pass只是必要条件
用户已明确xTB即可，但双向IRC必须实际计算，且必须`ts_guess(mode="verify",strict=true)`返回`verification_status="pass"`才算验证完成。还须审查目标反应模式、同方法零虚频且身份/映射正确的IRC外端；is_success、candidate、OptTS收敛或独立最低点不替代pass。用户最新明确只保留显然可算且科学可信的目标边，不勉强填数；即使未来strict pass，也不自动背书物理Gold。当前0 strict pass、0新增可信目标能垒，不为解析凑数重复QM/输出/文件排列试验。

旧done→Freq阻塞已由系统接续：IA1、IA5、IA8、IB9-E1、IB10-E1均有真实TS频率及双向IRC；IA9有791频率但尚未IRC。当前主要为端点geometry mismatch、目标模式/物种审查及IA9授权额度接入问题，不能再写无Freq/IRC。详见[端点几何审计](ENV_ENDPOINT_GEOMETRY_AUDIT.md)。

## 最新IA8自身IRC双端已补齐，工具未给端点判定（覆盖旧P未验证措辞）

此前strict使用explore独立参考，837/838来自旧796/800谱系，不能说已做836-own端点严格检验。现836自身B→R841、F→P840各普通Opt+NumFreq均正常/收敛/0虚频，最低503.56/1020.46cm⁻¹；结构身份和同序对应已核，[来源及几何对照](results/IA8/endpoint_strict_review/endpoint_comparison.json)mass-weighted RMSD为0.004635/0.001907Å。以835/836原日志、新双端原生final XYZ、原watch和strict=true唯一[正式返回](results/IA8/endpoint_strict_review/strict_own_endpoints.json)tc_8b3a7df380064bda仍fail，只有mode检查、IRC end路径空，无端点匹配或方向check。不能据此说端点连错，也不能称已执行端点优先验收。

[env有限审计](IA8_STRICT_BEHAVIOR_AUDIT.md)已完成：公开合同未明确端点优先控制，本次返回与早期mode拦截相符，不能推永久内部顺序。普通GFN2模式/IRC/同源双0虚频端点的计算证据已补齐，与strict未pass、旧durable几何一致性拒绝和物理适用性风险分列；不是继续加优化参数的理由。无后台，不新QM/strict试验，不擅自pass/Gold。

## 最新小步长/每周期Hessian诊断（IB9，839实际完成）

按用户新建议，从833原生最终结构仅一次同GFN2完整最低点计算：较小MaxStep/固定Trust=0.1/−0.1（内部坐标au）与Calc_Hess、NumHess、Recalc_Hess1。原生日志实证4优化周期初始+三次重算数值Hessian，末尾另NumFreq一次，并非只写标签。实际四步均远小于0.1上限，故不能将问题归因过大实际步长。末RMS/MAX梯度6.27e-8/5.385e-7 Eh/bohr；两位移指标仍NO，引擎按gradient overachieved宣布收敛，不写五项全过。

负频仍−29.79/−4.49cm⁻¹（833−29.75/−4.37），身份仍CH2N2+乙烯两组分；未得到整体零虚频minimum，不证明其不存在。完整实际次数/行号/步长/全频见[RESULT](results/IB9/hessian_step_review/RESULT.md)及[839原生日志](results/IB9/hessian_step_review/.cloudra/calc-839.out.log)。无后台，唯一诊断已收口，不再关键词循环/新TSIRC；分离单体参考继续保留，strict未pass/0新增Gold不变。普通GFN2未加DFT积分格点，SCC设置未变。

## 最新授权拆组分参考（IB9，已核完，无新增QM）

用户允许tight后仍软虚频则拆物种。798原料外帧/833为CH2N2+乙烯两完整无跨组分键的预反应接触体候选，非已验证束缚极小值。已复核复用同GFN2单体742/745，各正常/优化收敛/零虚频，原子对应与原生SHA见[组件报告](results/IB9/component_review/COMPONENT_REFERENCE.md)和[机器表](results/IB9/component_review/COMPONENT_REFERENCE.json)；不再重算。允许以E_A+E_B作明确标注的分离参考，但不同于RC minimum能量；组件0虚频不充作整体0虚频。TS保留完整体系，原strict缺TS几何与IRC方向验收要求不由拆单体消除；未填Gold、未改图/登记，无后台。IA8单分子无此拆分选择。

## 用户新增授权的一轮tight/方向复查（已完成，覆盖下表旧候选细节）

- **IB9-E1**：833真实加严无约束Opt+NumFreq，原料身份不变，末表五项均YES；RMS/MAX梯度4.940e-7/1.7926e-6 Eh/bohr，但两负频仍−29.75/−4.37cm⁻¹（原−36.41/−8.99）。未得到零虚频RC，不再迭代或strict复验。[对照与原生链接](results/IB9/tight_review/COMPARISON.md)。
- **IA8-E1（本节历史，已由上方840/841自身端点结果覆盖）**：原run唯一一次TightOpt 834→835唯一负频−950.47→836双向IRC；当时837/838后geometry mismatch、P尚未验证。新旧负模[直接重叠](results/IA8/tight_mode_review/mode_overlap.json)full/heavy abs cos均约1；重原子质量参与67.42%，[重原子与近TS第2/3帧方向](results/IA8/tight_mode_review/direction_tight_results.json)abs cos=.966–.990。支持成环伴随CH弯曲，不能说仅H在动；首帧为初始化，非独立验证。835/836原watch的[strict完整返回](results/IA8/tight_mode_review/strict_tight.json)仍fail，tc_5c084717219e41c9；不宣告误报、pass或Gold。
- 本轮两题只证实几何加严；IA8前后外部xTB仍--acc .2/SCC2e-7Eh，不能将TightSCF标签当电子精度提高。两owner无后台，新增授权已用完并收口；其余边不变，仍0 strict pass/0新增可信目标能垒，不追加QM或呈现试验。

## 逐边覆盖（xTB均为GFN2-xTB；PM7另列，不混减）

|边 / producer报告|已验证最低点|OptTS候选|一虚频及目标模式|双向IRC|外端闭合|势垒是否可报 / 具体缺口|
|---|---|---|---|---|---|---|
|IA1 E1 矩形键交替互换；[报告](results/IA1/REPORT.md)|独立823/824两侧正常、优化收敛、零虚频，固定map键长互换|760正常收敛，仅方法内候选|真实频率793及最新829一虚频；aligned不证明精度，−4610.8大虚频/方形多参考风险独立保留|797及最新830真实双向，映射R=B/P=F|独立端点身份有据；durable仍candidate_only；原字节bundle strict仍inconclusive missing TS geometry|未批准，不报barrier。12文件SHA相等、manifest valid不等科学pass；本轮停止重复计算/呈现试验|
|IA5 E1 反旋开环；[报告](results/IA5/REPORT.md)|独立RC/P及R侧815/818零虚频，但不证明反旋路径|756收敛的是顺旋竞争候选|792一虚频；最终ROTATION_AUDIT判共同轴两CH2同号旋转，即顺旋非目标反旋|799已真实双向，旋向审查已完成|candidate_only几何问题保留，不改变错误旋向|排除本候选目标回填；目标反旋未定位，无目标垒，不再旋向待定|
|IA7 E1 Bergman；[报告](results/IA7/REPORT.md)|Z起点771零虚频；772环骨架零虚频，但目标开壳单重态未证|未启动|无|无|无|否。ts_0006在guess报electronic_state_backend_unsupported；--uhf0不能表达目标开壳单重态，非共同refine故障；目标reaction_energy亦不可报|
|IA8 E1 CH2OO成环；[报告](results/IA8/REPORT.md)|本轮836B→R841/F→P840均正常收敛0虚频，原子序/开链与成环身份正确；PM7另列|739及tight834均正常收敛|835唯一−950.47，新旧模式重叠约1，成环方向有据；原watch strict仍mode fail|796及836真实双向；836自身两外帧已各Opt/Freq|本轮双同源极小值已补齐；旧837/838durable mismatch独立保留，当前strict未返回端点匹配check|未获pass，不填Gold；不把mode fail说成端点连错，待工具澄清端点一致与模式判据关系，物理适用性风险仍保留|
|IA9 E1 二氧环丁烷→两甲醛；[报告](results/IA9/REPORT.md)|xTB727 R/728甲醛零虚频；PM7 R/甲醛FORCE全正，仅组分参考|751正常收敛|791恰一虚频；自动诊断aligned，仍需路径确认|尚未跑|无|不可报。IRC numeric需auto；用户仅+1干预2→3已授权，但后端tc_dcc2d25237554e5e拒绝input revision cannot raise authorized limits，额度未生效|
|IB9 E1 原料→吡唑啉；[报告](results/IB9/REPORT.md)|821 F零虚频；单体742/745各零虚频；839保留−29.79/−4.49组分间软模|780正常收敛；794同几何电子能|794一虚频−367.39、目标成键模式；工具仍inconclusive|798真实双向；F收敛/B未收敛，F外帧优化821为吡唑啉|用户确认反应及软模接纳；未称整体零虚频或strict pass|已回填GFN2-xTB 5.65（TS794−839）；分离参考4.37另列；E2/RDS未定|
|IB9 E2 吡唑啉→环丙烷+N2；[报告](results/IB9/REPORT.md)|吡唑啉734零虚频；分离747/748各零虚频；复合物735三软虚频、不合格|782完成24点单调、CC未闭环；IDPP耦合后789终态failed，虽原生NORMAL但优化达最大步数未收敛，不列收敛候选|无已验证|无|无|不可报。最新报告已记录789 nonconvergence并blocked，旧失败结果未消化已属历史；科学搜索未成功不变，不证明不可达，全题RDS未定|
|IB10 E1 重氮乙醛→卡宾+N2；[报告](results/IB10/REPORT.md)|773 R零虚频；808/810外端正常零虚频但为O–N五元环；775不是目标卡宾|785正常收敛，仅非目标候选|795恰一虚频，不能凭aligned认脱氮|802真实双向，实证O–N成环旁路而非目标脱氮|candidate_only geometry mismatch，且错物种连接独立成立|排除本候选目标脱氮回填。不能用精度问题抹去错连接或用独立R seed掩盖旁路|
|IB10 E2 卡宾→乙烯酮（保留N2）；[报告](results/IB10/REPORT.md)|目标卡宾未核；乙烯酮786正常收敛零虚频；已核可复用IB9 N2 748，仅分离组件非完整P|path781/耦合scan784均未收敛，无收敛OptTS；完整P788 SCC250次不收敛fatal；N2 787输入解析失败|无已验证；787/788无可信频率|无|无|不可报。缺题设H6迁移方向、卡宾电子态及完整外端；775不是卡宾，组件复用不补成IRC闭合；本轮不再新增搜索|

## 原生输入/日志索引
以下链接相对于本文件；REPORT提供完整历史与结构身份分析，证据不得改写。未返回的新阶段不虚构输出链接。

- **IA1**：[矩形输入](results/IA1/rect_optfreq.inp) / [731日志](results/IA1/.cloudra/calc-731.out.log)；[759种子频率](results/IA1/.cloudra/calc-759.out.log)；[760输入](../../ts/ts_0002/jobs/declaration_0007/ts_opt/refine.inp) / [760日志](../../ts/ts_0002/jobs/declaration_0007/ts_opt/.cloudra/calc-760.out.log)。
- **IA5**：[RC输入](results/IA5/work/rc_xtb.inp) / [日志](results/IA5/work/rc_xtb.log)；[P输入](results/IA5/work/prod_strans.inp) / [日志](results/IA5/work/prod_strans.out)；[756输入](../../ts/ts_0004/jobs/declaration_0004/ts_opt/refine.inp) / [日志](../../ts/ts_0004/jobs/declaration_0004/ts_opt/.cloudra/calc-756.out.log)。
- **IA7**：[R输入](results/IA7/R_opt.inp) / [771日志](results/IA7/.cloudra/calc-771.out.log)；[P输入](results/IA7/P_opt.inp) / [772日志](results/IA7/.cloudra/calc-772.out.log)；[durable记录](../../ts/ts_0006/process.json)（电子态阻塞，无TS日志）。
- **IA8**：[xTB R输入](results/IA8/explore/opt_CH2OO.inp) / [729日志](results/IA8/explore/.cloudra/calc-729.out.log)，[P输入](results/IA8/explore/opt_dioxirane.inp) / [730日志](results/IA8/explore/.cloudra/calc-730.out.log)；[739输入](../../ts/ts_0001/jobs/declaration_0003/ts_opt/refine.inp) / [日志](../../ts/ts_0001/jobs/declaration_0003/ts_opt/.cloudra/calc-739.out.log)。PM7：[776 wrapper日志](results/IA8/pm7_validate/.cloudra/calc-776.out.log)、[自编分析脚本](results/IA8/pm7_validate/refine_minima.py)、[全部SP索引/残差/频谱](results/IA8/pm7_validate/refined_results.json)；原生逐次输入输出位于[R目录](results/IA8/pm7_validate/CH2OO_refined/)及[P目录](results/IA8/pm7_validate/dioxirane_refined/)（sp_*.mop/.out/.arc，不能以wrapper替代原生证据）。
- **IA9**：[xTB R日志](results/IA9/orca/.cloudra/calc-727.out.log)、[甲醛日志](results/IA9/orca/.cloudra/calc-728.out.log)；[751输入](../../ts/ts_0003/jobs/declaration_0003/ts_opt/refine.inp) / [日志](../../ts/ts_0003/jobs/declaration_0003/ts_opt/.cloudra/calc-751.out.log)；[PM7 R FORCE](results/IA9/pm7/R_force.out)、[甲醛 FORCE](results/IA9/pm7/CH2O_force.out)及[原生输入目录](results/IA9/pm7/)。
- **IB9 E1**：[734日志](results/IB9/calc/pyr_opt/.cloudra/calc-734.out.log)、[732日志](results/IB9/calc/rc_opt/.cloudra/calc-732.out.log)、[原料组分目录](results/IB9/calc/)；[逆向778输入](../../ts/ts_0005/jobs/declaration_0006/scan/scan.inp)；[780输入](../../ts/ts_0005/jobs/declaration_0006/ts_opt/refine.inp) / [780日志](../../ts/ts_0005/jobs/declaration_0006/ts_opt/.cloudra/calc-780.out.log)。**E2**：[782输入](../../ts/ts_0009/jobs/declaration_0002/scan/scan.inp) / [782日志](../../ts/ts_0009/jobs/declaration_0002/scan/.cloudra/calc-782.out.log)、[789输入](../../ts/ts_0009/jobs/declaration_0003/ts_opt/refine.inp) / [789失败日志](../../ts/ts_0009/jobs/declaration_0003/ts_opt/.cloudra/calc-789.out.log)、[735日志](results/IB9/calc/prod_opt/.cloudra/calc-735.out.log)、[747日志](results/IB9/calc/frag_c3h6/.cloudra/calc-747.out.log)、[748日志](results/IB9/calc/frag_n2/.cloudra/calc-748.out.log)。PM7历史直接执行来源及未审全谱见报告，不冒称公开队列验收。
- **IB10 E1**：[773日志](results/IB10/R/.cloudra/calc-773.out.log)、[775日志](results/IB10/carbene/.cloudra/calc-775.out.log)、[普通原生输入目录](results/IB10/)；[785正式输入](../../ts/ts_0007/jobs/declaration_0003/ts_opt/refine.inp) / [785日志](../../ts/ts_0007/jobs/declaration_0003/ts_opt/.cloudra/calc-785.out.log)。**E2**：[784失败日志](../../ts/ts_0008/jobs/declaration_0003/scan/.cloudra/calc-784.out.log)、[durable记录](../../ts/ts_0008/process.json)；[乙烯酮786日志](results/IB10/ketene/.cloudra/calc-786.out.log)、[N2 787解析失败日志](results/IB10/N2/.cloudra/calc-787.out.log)、[P788 SCC失败日志](results/IB10/P_clean/.cloudra/calc-788.out.log)；[复用N2 748输入](results/IB9/calc/frag_n2/frag_n2.inp) / [日志](results/IB9/calc/frag_n2/.cloudra/calc-748.out.log)。

## 能量口径与共同工程缺口

- **IA8**：xTB独立端点ΔE=-31.18715 kcal/mol；PM7 job776独立端点Δ=-21.867740 kcal/mol。后者是**含bits的参数化Hf/模型势能差，未另加显式ZPE/热项，不是严格物理0 K裸电子能**。全Cartesian梯度中心差分、质量加权并投影平移/转动后的频率是自编分析，不叫MOPAC FORCE或PySCF原生频率。两端极小值不证明路径闭合，两数都不是势垒，绝不跨方法混减。
- **IA9 PM7**：Hf差只作参数化模型端点/组分诊断，不改称裸电子反应能。IA7目标开壳单重态反应能未证；IB9两步RDS未定；旧B3LYP/顺旋数不回填。
## 当前工程与科学缺口（覆盖旧收口）

- 五题R侧Opt/Freq均真实正常/零虚频，却被durable判candidate_only geometry mismatch。[env审计](ENV_ENDPOINT_GEOMETRY_AUDIT.md)证实原子序一致，原生最终XYZ round6逐值等于保存几何、保存→frequency输入差全0；不支持保存了Opt初始帧假说。validator比较参考/阈值及根因未证，不把量化直接写为单因或pass，不再盲目重复Opt/seed。
- IA8 [strict完整返回](results/IA8/strict790_796_fail.json)与[模式径向反例](results/IA8/mode790_analysis.json)分列；模式启发式可能误拒是待处理问题，不删watch/改阈值。IB10错O–N环化独立排除目标脱氮回填；IA5已由[ROTATION_AUDIT](results/IA5/ROTATION_AUDIT.md)最终判为顺旋竞争，排除指定反旋回填。
- IA9用户授权事实与后端额度生效分开：仅+1干预已同意，但受权预算接入尚未成功，无新IRC。
- 当前仍**0/9 strict pass；IB9_E1已有1条人工确认的方法内参考更新（5.65）**。六个OptTS优化收敛只是历史覆盖计数，现均已有同几何频率，其中五题已IRC，不能再写六候选全无Freq/IRC。IB9 821/822均已完成，B后续839仍有两软虚频，strict缺TS中心的真实返回保留；IA1最新829/830与双零虚频独立端点及原字节bundle也未获strict pass。各owner本轮无后台/无新增计算授权，不再为修parser重复计算。
- PM7普通端点/外接回调不等于正式TS/IRC后端及scorer可用。方法、组分、Hf/电子PES口径仍严格分开，不混减，不把扫描峰或候选能差当垒，不推设计不可达。

## 新增原生证据索引（相对本文件）

|边|TS频率|双向IRC|当前R外端Opt/Freq目录|
|---|---|---|---|
|IA1|[793](../../ts/ts_0002/jobs/declaration_0009/frequency/.cloudra/calc-793.out.log)|[797](../../ts/ts_0002/jobs/declaration_0009/irc/.cloudra/calc-797.out.log)|[817 Opt](../../ts/ts_0002/jobs/declaration_0011/reactant_opt/)、[820 Freq](../../ts/ts_0002/jobs/declaration_0011/reactant_frequency/)|
|IA5|[792](../../ts/ts_0004/jobs/declaration_0006/frequency/.cloudra/calc-792.out.log)|[799](../../ts/ts_0004/jobs/declaration_0006/irc/.cloudra/calc-799.out.log)|[815 Opt](../../ts/ts_0004/jobs/declaration_0007/reactant_opt/)、[818 Freq](../../ts/ts_0004/jobs/declaration_0007/reactant_frequency/)|
|IA8|[790](../../ts/ts_0001/jobs/declaration_0005/frequency/.cloudra/calc-790.out.log)|[796](../../ts/ts_0001/jobs/declaration_0005/irc/.cloudra/calc-796.out.log)|[816 Opt](../../ts/ts_0001/jobs/declaration_0006/reactant_opt/)、[819 Freq](../../ts/ts_0001/jobs/declaration_0006/reactant_frequency/)|
|IA9|[791](../../ts/ts_0003/jobs/declaration_0003/frequency/.cloudra/calc-791.out.log)|未跑，不虚构日志|未闭合|
|IB9 E1|[794](../../ts/ts_0005/jobs/declaration_0006/frequency/.cloudra/calc-794.out.log)|[798](../../ts/ts_0005/jobs/declaration_0006/irc/.cloudra/calc-798.out.log)|[813 Opt](../../ts/ts_0005/jobs/declaration_0007/reactant_opt/)、[814 Freq](../../ts/ts_0005/jobs/declaration_0007/reactant_frequency/)；独立821/822终态见下文|
|IB10 E1|[795](../../ts/ts_0007/jobs/declaration_0003/frequency/.cloudra/calc-795.out.log)|[802](../../ts/ts_0007/jobs/declaration_0003/irc/.cloudra/calc-802.out.log)|[808日志](../../ts/ts_0007/jobs/declaration_0003/reactant_opt/.cloudra/calc-808.out.log)、[810日志](../../ts/ts_0007/jobs/declaration_0003/reactant_frequency/.cloudra/calc-810.out.log)|

各R目录内NAME绑定reactant_opt.inp/reactant_opt.xyz，以及reactant_frequency.inp/optimized.xyz/source与原生日志的精确模式和hash见env审计，不用NumFreq位移帧冒充参考中心。IB9独立普通输入：[F/821](results/IB9/independent_endpoints/F/optfreq.inp)、[B/822](results/IB9/independent_endpoints/B/optfreq.inp)；由798原生外帧而非SMILES重建；已完成[F821原生日志](results/IB9/independent_endpoints/F/.cloudra/calc-821.out.log)、[B822原生日志](results/IB9/independent_endpoints/B/.cloudra/calc-822.out.log)，完整strict请求/返回见[STRICT_FULL_RECORD](results/IB9/independent_endpoints/STRICT_FULL_RECORD.json)。

## 最新覆盖与最终边界

- IA1最新原生链位于[declaration_0013](../../ts/ts_0002/jobs/declaration_0013/)：829频率、830 IRC；[823 R日志](results/IA1/independent_endpoints/R_B/.cloudra/calc-823.out.log)及[824 P日志](results/IA1/independent_endpoints/P_F/.cloudra/calc-824.out.log)双零虚频与映射键长互换已核。唯一12文件原字节共定位包[manifest](results/IA1/strict_native_bundle/manifest.json) valid=true、源目标SHA全相等，但[完整strict返回](results/IA1/strict_bundle_result.json) tc_0790a535075c4cbf仍inconclusive missing TS geometry；只作工具复现/方法内候选，不批准势垒。
- 本表覆盖REPORT保留的历史等待措辞：IA1“P未提交”由823/824覆盖；IA5“IRC启动/旋向待核”由799实算及最终[旋向审计](results/IA5/ROTATION_AUDIT.md)覆盖；IB9“821/822 ready/strict待执行”由两端终态及完整strict记录覆盖。IA8旧缺Freq/IRC由790/796覆盖；IB9-E2旧失败结果未消化由最新blocked覆盖。IA9追加1干预仍被后端拒绝raise，无IRC，不写额度已生效。
- IA7电子态能力、IA8 strict fail与电子态适用性、IA9执行授权接入、IB9-E2及IB10-E2旧搜索未成功均按原证据保留。工程量化/解析问题不能消除科学风险或错误通道。
- 最终为**0 strict pass、0新增可信目标能垒**，不等于9边物理不可达。仅将已有计算与科学取舍分层交付；未来如有新科学依据、低风险目标边，仍须另行授权。当前无后台/无新增授权，不为凑数或解析反复计算。本次仅编辑此表，未改其他报告、PROCESS、registry或原生证据。
