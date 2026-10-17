# IB10 本轮计算报告（未完成证据闭合）


## IB10 — 逐步Wolff（owner）
气相热解q0/m1，温度/压强未指定，无外加水酸碱或对离子；孤立GFN2-xTB闭壳PES不证明最低自旋纯单重态。假说为先N2脱离，再题设H6由C4到C3，不能拿协同旁路替代。RC [773](gold_compute/queue_20261018/results/IB10/R/.cloudra/calc-773.out.log)正常收敛零虚频E=-15.118382145640 Eh。独立卡宾种子 [775](gold_compute/queue_20261018/results/IB10/carbene/.cloudra/calc-775.out.log)正常收敛零虚频，但internal_coordinates核真实输出C1同时连H4/H5且C1=C2=O3：实际成乙烯酮，**不是已核卡宾极小值**。这一次塌陷不证明卡宾不存在。
E1 durable [ts_0007](ts/ts_0007/process.json) path779达20轮上限无可用TS猜测；E2 [ts_0008](ts/ts_0008/process.json)已补真实结构中心4–7断/3–7成/3–4升阶（H7对应题设H6），path781达20轮上限失败；后续E2耦合扫描784达到优化上限未收敛（[原日志](ts/ts_0008/jobs/declaration_0003/scan/.cloudra/calc-784.out.log)）。E1扫描783有两峰，实际核第9峰O–N旁路成键不选；第4峰C–N1.648Å/N–N1.114Å且醛H仍原位，已通过ts_resume tc_3b019b053295484e送正式OptTS785（[输入](ts/ts_0007/jobs/declaration_0003/ts_opt/refine.inp)），785原生正常且优化收敛E=-15.10714640019Eh；refine.xyz核C–N回缩1.289Å/N–N1.136Å，醛H仍原位，只有未定指数驻点候选。ts_inspect tc_89c54b75a04b4f4f为waiting/refine，next=wait_for_system且无required_inputs/editable_groups，Freq未启动，共同工程阻塞；不据done认TS。合法另目录修复普通产物：ketene786、N2 787、完整复合物788的Opt/NumFreq均已终态审计（见下）。多组分卡宾普通writer被unsupported_spin拒绝仅属结构装配能力；P774/777为原生输入解析失败，旧证据完整保留，完整P复合物尚无正常收敛的Opt/Freq证据。日志导出xyz工具失败，已改用原生opt.xyz核身份。没有任何可报势垒；本轮停止新增搜索，正式TS/IRC仍只durable，后续须先修复流程推进缺口。


### IB10 收口审计（本轮未闭合边）
普通终产物修复结果：ketene [786](ketene/.cloudra/calc-786.out.log)正常、优化收敛、0虚频，E=-9.318187047870 Eh，最低383.96 cm⁻¹；独立原生opt.xyz确认为C2H2O两H同碳，与775塌陷终态一致。N2 [787](N2/.cloudra/calc-787.out.log)终态failed，原生输入解析expect a $/!错误、无能量频率；完整P [788](P_clean/.cloudra/calc-788.out.log)终态failed，后端Single point calculation terminated fatal error，无正常终止/可信频率（log_parser tc_b62581e8ba1b4870），不得将其opt.xyz称优化终态。均保留输入原日志，不再无依据重试。
E1：785原生正常且优化收敛，但durable后继频率未启动，tc_89c54b75a04b4f4f waiting/refine/next wait_for_system且无必填字段，为公共工程阻塞；无目标模式/双向IRC/外端极小闭合，不能报ΔE‡。E2：路径781与指定H6迁移耦合扫描784均真实失败，尚未在尝试中找到经验证甲酰卡宾极小；775只是一次塌陷，不证明该极小不存在。闭壳GFN2-xTB/uhf0不提供自旋纯最低开壳单重态证明，不能以收敛证明卡宾电子态。
未新增PM7桥接测试（由IA8唯一owner负责），未换Hamiltonian、改registry或根图，无任何新Gold/accessible结论。两边均未完成验证；扫描峰非垒、候选能差不填边。目前无后台计算，等待工程修复不是化学不可达。

### 同项目N2组件复用（不新增计算）
经核原生输入，IB9 job748与ketene786均为气相q0/m1、ORCA6.1.1调用GFN2-xTB 6.7.1(edcfbbe)、Opt+NumFreq、无溶剂/额外Hamiltonian；资源4核与2核不同但不改变计算模型。可复用[N2原生日志](../IB9/calc/frag_n2/.cloudra/calc-748.out.log)、[输入](../IB9/calc/frag_n2/frag_n2.inp)、[原生几何](../IB9/calc/frag_n2/frag_n2.xyz)作为**分离N2组件**证据：正常终止/优化收敛/零虚频，唯一伸缩2437.61 cm⁻¹，E=-5.763935420240 Eh。本题787输入失败不是N2科学不可算。此证据不是本题IRC外端或完整P复合物，不补成E1/E2已验证边；不另报组件能差。


## 最新续审：推进后发现非目标连接（取代先前停滞作为当前结论）
系统后来完成[TS频率795](../../../../ts/ts_0007/jobs/declaration_0003/frequency/.cloudra/calc-795.out.log)、[IRC802](../../../../ts/ts_0007/jobs/declaration_0003/irc/.cloudra/calc-802.out.log)、[外端优化808](../../../../ts/ts_0007/jobs/declaration_0003/reactant_opt/.cloudra/calc-808.out.log)、[外端频率810](../../../../ts/ts_0007/jobs/declaration_0003/reactant_frequency/.cloudra/calc-810.out.log)。795正常且恰一虚频−247.87cm⁻¹，模式组成parser为null，不仅凭aligned标签认脱氮。802正常、两向各20点、未内禀收敛；实际[前向外帧](../../../../ts/ts_0007/jobs/declaration_0003/irc/irc_IRC_F.xyz)C3–N4仍1.276Å，[后向外帧](../../../../ts/ts_0007/jobs/declaration_0003/irc/irc_IRC_B.xyz)O1–N5缩至1.640Å并形成O-C-C-N-N五元环。808正常优化收敛，原生reactant_opt.xyz中O1–N5=1.369Å/C3–N4=1.355Å，仍五元环而不是声明的链状原料或卡宾+N2；810正常零虚频。上述internal_coordinates辨别支持候选走O–N成环旁路，**不能算目标E1脱N2边**，也不代替H6迁移E2。
当前ts_inspect ended/candidate_only另报optimization log/saved frequency source/frequency log几何不匹配（endpoint_unconfirmed）；此工具一致性诊断与实际错物种连接分列，不猜根因。不能单改reactant seed为独立773掩盖IRC错连接，不新增该修订或计算。先前waiting/refine仅历史工程阻塞，现已推进，当前未完成原因是目标连接未证、旁路结构及端点一致性未过。E2先前路径与扫描失败状态不变；无目标势垒/Gold，零虚频环形外端也非题设反应物极小。
