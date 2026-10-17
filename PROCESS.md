# IMP 难题：PM7 与 xTB 方法内参考值探索

## 最新纠正：IA8本轮IRC自身端点已补齐，strict未给端点判定（2026-10-18）
用户指出端点优化后一致应可直接判过。核原[旧strict参数](gold_compute/queue_20261018/results/IA8/tight_mode_review/strict_tight_request.json)确使用explore独立两端；837/838又是旧800/796谱系seed，非本轮836自身外帧，不能把旧fail描述为已做真正836-own端点一致检验。现已从836的F/B原生外帧各一次普通无约束Opt+NumFreq：P840/R841均正常、优化收敛、0虚频，最低1020.46/503.56cm⁻¹，协调已核原日志。原子序保持C/O/O/H/H，R是开链CH2OO，P是dioxirane；[同源端点对照](gold_compute/queue_20261018/results/IA8/endpoint_strict_review/endpoint_comparison.json)记录质量加权对齐RMSD R0.004635/P0.001907Å和完整键长/源SHA，不是端点错身份。

[本轮严格请求及完整返回](gold_compute/queue_20261018/results/IA8/endpoint_strict_review/strict_own_endpoints.json) tc_8b3a7df380064bda已用835/836原日志、两侧新原生final XYZ、原watch与strict=true；仍fail且checks仅一负频/模式失配、irc_end路径空，没有给端点匹配数值。故本次未完成用户所述“端点一致优先通过”的判定，不可称端点匹配失败或永久断言验收算法；env正在只读核公开合同/该返回，不看源码、不新调用试验。旧837/838的durable三几何报错保留为单独工程历史，不再声称P未Opt/Freq。目标模式/IRC/同源双0虚频最低点的模型内证据已补齐，实际strict仍未pass及普通GFN2物理适用性风险分开，不回填Gold或垒；无新增QM、owner无后台。

**839唯一小步长/逐周期数值Hessian诊断已完成**：原生日志证实4周期沿途初始+三次重算Hessian（review.001–004.hess、明确read recalculated），另末NumFreq第五次；MaxStep/Trust实回显0.100/0.100，但实际步长均远小于上限，不据此归因过大步长。末RMS/MAX梯度6.27e-8/5.385e-7 Eh/bohr，引擎按gradient overachieved宣布收敛，两步长指标仍NO，不能称五项全过。结构仍原料两组分，E−15.19012562713Eh；虚频−29.79/−4.49（833−29.75/−4.37），没有消失。全频/次数/行号/模式/边界见gold_compute/queue_20261018/results/IB9/hessian_step_review/RESULT.md和PARSED_839.json。没有找到本轮零虚频接触体minimum，不证明不存在；完成一次授权收口，无后台、不新QM/strict呈现/Gold或垒，单体742/745参考保留。

**Hessian/小步长诊断提交时记录（历史，已由上方839实际结果覆盖）**：researcher官方核字段语义后，从833原生最终结构!Opt NumFreq，MaxStep0.1/Trust−0.1内部坐标au，Calc_Hess/NumHess true、Recalc_Hess1；保留833 tight阈值与GFN2/SCC/占据/完整组成。官方Hessian组说明偏TS，minimum实际执行重算尚待原生日志核验，不能把标签算次数；若拒绝/不触发就如实收口不试别的。方案与输入见gold_compute/queue_20261018/results/IB9/hessian_step_review/PLAN.md、review.inp。无冻结/新TSIRC或积分grid变更，无Gold预承诺。

**IB9小步长/Hessian启动方案（历史，支持已由839实测）**：起点仅833原生tight_optfreq.xyz，完整CH2N2+乙烯GFN2/q0m1不变。假说是上轮BFGS近似曲率/步长处理可能使浅负曲率未解决；此次检验真实数值Hessian重算配合较小步长，而非再次仅加严梯度。先待researcher官方核minimum适用Calc_Hess/NumHess/Recalc_Hess及Trust/MaxStep接口，只选一个可支持配置一次普通Opt+Freq；输入标签不足，须原生证明重算次数/间隔与实际步长。若不支持则据具体证据停止，不试关键词组合、不新TSIRC/扰动循环、不改阈值或Gold。742/745零虚频分离参考保留，833软负频亦不撤回。

**IB9最新拆组分参考授权已完成（无新增QM）**：798 B/833确为CH2N2+乙烯两个无新跨组分键接触体、非金属配位；833非已验束缚minimum。工作序乙烯[1,2,6,7,8,9]，CH2N2[3,4,5,10,11]；742局部→工作序[5,4,3,10,11]、745[1,2,6,7,8,9]，题设map另列不混。已亲核复用742/745同日志OptNumFreq正常/收敛/零虚频，同ORCA6.1.1→xtb6.7.1/GFN2/q0m1/accuracy.2/SCC2e-7Eh，结构对应足够，不再拆后重算。E_A+E_B=−15.18807894276Eh，833候选相互作用−1.28431kcal/mol（非验证结合minimum）。详见gold_compute/queue_20261018/results/IB9/component_review/COMPONENT_REFERENCE.md与.json（全原子对应/源路径/哈希/全频）。新授权允许分离参考，旧“不用分离物掩盖负频”仍有效：组件零虚频不等于整体零虚频，公开strict无组件频率输入接口，不能代替完整IRC方向证明；没有strict pass/Gold/垒、无图或登记修改。

## Hessian重算早期历史核对（用户CalcAll询问时点；随后已授权并实际完成839）
用户问「calcAll之类的试过没有」。已核[IA8 tight TS输入](ts/ts_0001/jobs/declaration_0007/ts_opt/refine.inp)与[IB9 TS输入](ts/ts_0005/jobs/declaration_0006/ts_opt/refine.inp)只有`Calc_Hess true`初始Hessian；[IB9 tight最低点输入](gold_compute/queue_20261018/results/IB9/tight_review/tight_optfreq.inp)只有显式几何tight+末NumFreq，均不是每一步重新计算Hessian。不能将tight或末Freq说成已尝试CalcAll，也不能说相关补救已试尽。该询问时点每步/周期Hessian重算尚未采用；之后用户广播允许有针对性小步长/CalcAll诊断，已完成839并实证普通minimum的逐周期数值Hessian，最新结果见本文件顶端。若以后确需试，先核ORCA外接GFN2实际支持和原生回显，不照搬Gaussian关键词，不新增TS/IRC旁路。提醒对应的拆组分审计已完成、无后台，不因旧提醒重启。

## 最新授权：IB9原料复合物拆组分参考（协调，2026-10-18，已核完）
用户最新「tight还不行的话就拆物种，它是络合物吗」。带两软虚频的是IB9原料侧CH2N2+乙烯两组分弱相互作用复合物候选，不是金属配位或已证实的束缚极小值；两分子无新共价键。允许改用分别频率验证的单体作分离反应物参考，优先复核复用已有[742 CH2N2](gold_compute/queue_20261018/results/IB9/calc/frag_ch2n2/.cloudra/calc-742.out.log)与[745乙烯](gold_compute/queue_20261018/results/IB9/calc/frag_c2h4/.cloudra/calc-745.out.log)，不自动重算。原owner负责明确798原料外帧/833两组分身份、完整原子成员映射、单体同方法/电子态/版本与0虚频证据；确有缺口才每片最多一次真实来源拆分普通Opt/Freq。TS不可拆，仍须完整IRC身份/方向证明与strict pass；单体0虚频不冒充整体复合物0虚频。若能量参考改为E_A+E_B，须与相对RC的能垒明确区分，不挪用旧数或未pass回填。IA8是单分子成环，不能用拆组分解决其strict fail。本次不新TS/IRC或解析呈现试验，不改registry/Gold/root graph；审计结论已记于[IB9组件报告](gold_compute/queue_20261018/results/IB9/component_review/COMPONENT_REFERENCE.md)，无需新增QM；协调已由log_parser复核两原生日志正常/优化收敛/0虚频。

## 最新定向复查：Tight优化与虚频方向（协调，2026-10-18，已完成）
**IA8同run一次tight已完成834/835/836，仍未pass**：TS几何最大梯度由1.70086e-4降至7.85153e-5 Eh/bohr，唯一负频−950.34→−950.47cm⁻¹。两次[原生负模直接重叠](gold_compute/queue_20261018/results/IA8/tight_mode_review/mode_overlap.json)在质量加权对齐、去同一刚体空间及±号归一后full/heavy abs cos=0.9999999934/0.9999999990；新负模重原子质量参与率67.42%，与836近TS第2/3帧有限弦的重原子方向cos F=.96841/.96622、B=−.98733/−.98987，见[完整方向表](gold_compute/queue_20261018/results/IA8/tight_mode_review/direction_tight_results.json)。首帧为初始化，不作独立验证。成C1–O3伴随CH弯曲的方向证据较强，不能简化为仅H在动；但[原watch strict复验](gold_compute/queue_20261018/results/IA8/tight_mode_review/strict_tight.json) tc_5c084717219e41c9仍fail，837/838后端几何校验仍拒、P未验证，不宣布误报或Gold。实际xTB --acc .2/SCC2e-7Eh前后未变，只证实几何tight，不能称电子精度提升。源与对照见[最终报告](gold_compute/queue_20261018/results/IA8/REPORT.md)。两owner均已确认无后台，本轮定向复查收口，不追加QM或呈现试验。
**IB9定向tight唯一轮已完成833并收口**：实际原生末表五项全YES，RMS/MAX梯度由822的1.53497e-5/4.07814e-5降为4.940e-7/1.7926e-6 Eh/bohr，阈值确实加严；SCC未改。仍同原料两组分，反应距3.379/3.251→3.383/3.249Å，电子能降低0.00262446 kcal/mol。两负频−36.41/−8.99→−29.75/−4.37 cm⁻¹，未消失，绝不当零/噪声；仍H主导低模但未证纯刚体摆动。全频率/实际阈值/收敛表/模式组成及原生路径见gold_compute/queue_20261018/results/IB9/tight_review/COMPARISON.md与PARSED_833.json。没有找到本轮零虚频原料复合物最小值，不证明不存在；不再迭代、无strict复验/Gold/垒，missing TS geometry独立保留。
IB9本轮方案：仅从822 NAME=optfreq.inp绑定原生最终optfreq.xyz一次无约束普通Opt+NumFreq，保留GFN2/ORCA6.1.1外部xtb6.7.1与q0m1。822实际ORCA BFGS默认TolE5e-6/MAXG3e-4/RMSG1e-4/MAXD4e-3/RMSD2e-3；本轮显式geom阈值1e-7/1e-5/3e-6/1e-4/5e-5，非单靠TightOpt标签，最终必须核native回显实际阈值与梯度。SCC设置不凭猜测更改；若只能确认几何tight，将明确不是已证实SCC加严。模型气相无外加参与物、温压未知，不扰动/冻结/删负频，不预承诺零虚频或Gold。
用户最新提出「tight优化一下怎么样。那个fail的值得警惕，比一下虚频方向。」据此仅恢复一轮有辨别力的GFN2-xTB定向复查，不恢复全面搜索或解析呈现试验：IB9-E1从822自身原料侧端点做一次更紧的无约束最低点Opt/Freq，核两软虚频是否真正消失及结构身份；IA8先对790原生完整负模与TS附近796的两向IRC切线、目标C–O成键/键级变化方向做定量比较，不先认定误拒。若确需更紧TS优化，只能原owner原durable ts_0001中合理修订、同方法同电子占据；任何干预额度/工具阻塞照实报告，不新run或手动TS/IRC绕过。保留原始模式/几何和既有fail，比较时处理向量正负任意性、质量加权和刚体运动，不删watch或放宽strict。上述为本轮启动方案；现两项已完成，结果见本节顶端和[IB9报告](gold_compute/queue_20261018/results/IB9/REPORT.md)、[IA8报告](gold_compute/queue_20261018/results/IA8/REPORT.md)。仍无新增pass/Gold，不再追加。

## 当前方法与讨论边界（协调，2026-10-18补充）
用户再次明确当前是 **普通GFN2-xTB**，不是B3LYP；本轮B3LYP文献短评只作适用性讨论，不构成更换方法或新增计算授权。旧IB9-E1的B3LYP 14.74不能支持或回填xTB势垒。相对探索排序仅保留IB9-E1在前、IA8-E1备选，不预承诺可信Gold；两边已有真实xTB TS频率/双向IRC，不能写成尚未实算。IB9的[完整strict记录](gold_compute/queue_20261018/results/IB9/independent_endpoints/STRICT_FULL_RECORD.json)仍inconclusive，原料侧822两软虚频；IA8的[strict记录](gold_compute/queue_20261018/results/IA8/strict790_796_fail.json)仍fail，[径向模式分析](gold_compute/queue_20261018/results/IA8/mode790_analysis.json)只是疑似启发式误拒证据，非pass。其余7条反应边保留逐边原因，不以新探索排序重启重复工作，现仍0 strict pass/0新增可信目标垒，详见[覆盖总表](gold_compute/queue_20261018/EDGE_STATUS.md)。

researcher已核[官方Spin-polarization说明](https://xtb-docs.readthedocs.io/en/latest/spgfn.html)的General description：普通GFN1/2能量表达spin-independent，但occupation-dependent；可优化高自旋几何不代表可可靠计算真实单三态排序/交换分裂。`--uhf`只设未成对电子数/占据，不是自旋极化项；`--spinpol --tblite`属于另外的spGFN扩展，不能追认为既有计算或默认换用。故IC3/IF3不把普通GFN2的S–T数值作可信目标参考；IA7目标开壳单重态接口限制不外推DFT无能力或反应物理不可达。已停止的计算、输出/解析呈现试验不因本讨论自动恢复。

## IA7 — Bergman 成环
已真实GFN2-xTB两端Opt/NumFreq，771/772正常收敛零虚频；R末C2–C3–C4–C5二面角-0.00°证实Z。P是平面p-benzyne骨架，但m1不证明目标开壳单重态。durable ts_0006选映射候选0后guess被electronic_state_backend_unsupported阻塞，call_id tc_226d941588154d73：GFN-xTB --uhf0无法表达开壳单重态。无TS/IRC，无可信目标垒/反应能；不是物理不可达。[原生证据及报告](gold_compute/queue_20261018/results/IA7/REPORT.md)。


## 最新取舍：不勉强填数，科学可信性优先（协调，2026-10-18）
用户最新明确「算不出来不需要勉强，只需要算那些显然能算的边，因为有些边算出来本身也会是错误的」。据此停止重复QM、verbosity及文件呈现试验；此前strict pass要求仍有效，但它只是必要验收，不是物理准确性的充分条件。仅保留目标路径、立体与电子态正确且模型适用的参考；收敛数值、错误竞争通道、高风险方法内候选或未pass均不填Gold/目标能垒。

当前结果分流：IA5真实IRC为顺旋，不是指定反旋；IB10-E1真实IRC为O–N成环，不是指定脱氮，排除这两个候选的目标回填。IA1虽已有目标模式/双向IRC/双零虚频端点，但−4610.8cm⁻¹的异常大虚频和方形静态关联风险独立存在，不能将GFN2自洽链当可信物理Gold。IB9-E1是相对常规的环加成候选，但原料复合物仍两软虚频且strict未通过，亦不填。IA8 strict fail与电子态适用性保留，IA7/IA9及两第二步的具体能力/搜索限制照实记录。当前没有一条新增目标能垒可负责任回填，不能据此说反应物理不可达。

IA1最后一次原字节共定位试验已结束：[manifest](gold_compute/queue_20261018/results/IA1/strict_native_bundle/manifest.json)中12文件source/destination SHA全部一致、原源未改，完整[严格返回](gold_compute/queue_20261018/results/IA1/strict_bundle_result.json) tc_0790a535075c4cbf仍inconclusive missing TS geometry。只作为解析复现证据，停止文件名排列、输出组合或重复QM；不把包valid误写成科学pass。

## 用户强制验收与已执行链（下列过程记录保留）
用户明确「用xtb也行……irc也要做」「必须要过了ts_guess才算验证完成」：当前主线改为GFN2-xTB完成频率→目标模式→双向IRC→各自IRC外帧无约束Opt/Freq→`ts_guess(mode="verify", strict=true)`且`verification_status="pass"`后才回填对应边和能垒。guess生成成功、candidate、OptTS正常结束、单独一虚频、接口或独立最低点计算都不算验收。ts_guess strict通过也不豁免目标反应模式与零虚频端点身份审查。

**状态已发生变化：旧done→Freq未接续阻塞已由系统消化，不能再作为当前无频率/IRC的结论。** 目前IA1（793/797）、IA5（792/799）、IA8（790/796）、IB9-E1（794/798）、IB10-E1（795/802）均已实际执行TS数值频率和双向IRC。源日志详见各题REPORT，未通过strict仍不回填势垒。

当前需分开的事实：
- **端点几何一致性**：五题至少R侧Opt/Freq已正常收敛/零虚频，durable却报三份几何不匹配、停candidate_only。env[文件审计](gold_compute/queue_20261018/ENV_ENDPOINT_GEOMETRY_AUDIT.md)核原子序一致，原生最终XYZ四舍五入6位逐值等于保存几何、保存→频率输入差全0，最大原始坐标差约5×10⁻⁷Å。不支持保存了Opt初始帧假说；尚未证明校验器具体阈值/内部参考，因此不能直接宣布pass，不再反复seed/Opt试错。IA1正确映射R=B/P=F后817优化、820频率仍同错，报告见[方向与待验参数](gold_compute/queue_20261018/results/IA1/irc_direction_and_strict_pending.json)。
- **IA8模式**：正式790一虚频−950.34cm⁻¹，796两向外帧连接CH2OO/三元环；`ts_guess strict`显式C–O watch返回fail，完整[参数/返回](gold_compute/queue_20261018/results/IA8/strict790_796_fail.json)保留。原生模式[独立分析](gold_compute/queue_20261018/results/IA8/mode790_analysis.json)显示C1–O3径向−0.349093，主导H–H相对norm1.258783却径向−0.000269（主要横向），是可复核疑似启发式误拒，不能删watch/改阈值求pass。
- **路径身份**：IB10-E1的795/802实证O–N五元环旁路，非目标脱N2→卡宾；即使精度修好也不能填目标垒。IA5已完成[逐帧旋向审查](gold_compute/queue_20261018/results/IA5/ROTATION_AUDIT.md)：同一共同观察轴下两CH2附H同号旋转（F四氢增量+22.13/+33.00/+22.16/+33.02°，B均负），固定附氢身份、刚体变换不变，现有756/792/799是顺旋竞争路径而非目标反旋；不能填IA5目标垒。IB9-E1模式aligned、798两向为吡唑啉/分离原料，但独立B侧822仍两软虚频，尚无全链合格参考。
- **IA9仍未IRC**：791有一目标候选虚频，但IRC numeric配置需改auto；用户经ask_user明确授权仅增加1次必要干预（2→3）。原owner尝试后端tc_dcc2d25237554e5e仍拒`input revision cannot raise authorized limits`，无新IRC。授权事实不等额度已接入，需平台受权预算恢复，不能改状态/新run绕过。

独立端点实算已完成：IB9从798自身F/B外帧各一次普通Opt+NumFreq（821/822），F收敛零虚频，B收敛但有−36.41/−8.99cm⁻¹软虚频，不当合格RC。IA1从797自身B/F外帧各一次[823](gold_compute/queue_20261018/results/IA1/independent_endpoints/R_B/.cloudra/calc-823.out.log)/[824](gold_compute/queue_20261018/results/IA1/independent_endpoints/P_F/.cloudra/calc-824.out.log)普通Opt+NumFreq均正常/优化收敛/零虚频，固定map下矩形键长正确互换。正式TS/Freq/IRC仍来自durable，未手动TS/IRC或改run状态。

**目前最接近的一条IA1仍未通过工具**：`ts_guess strict` tc_8b6d2b548ee34c9a能读取793恰一虚频−4610.8、四个watch aligned、797双向各11点收敛及两独立优化外端，但返回`inconclusive: missing TS geometry`，完整[原始参数/返回](gold_compute/queue_20261018/results/IA1/strict_original_paths.json)。协调已log_parser亲核793/797/823/824正常与两端0虚频；未以该科学链完整冒称严格pass或报垒。IB9同类strict tc_aa51e9efa8f64325，另有B软虚频独立缺口。

env[strict解析审计](gold_compute/queue_20261018/STRICT_PARSER_AUDIT.md)核频率原生.hess含TS中心、原生日志无Cartesian表且无frequency.xyz；合同没有明示.hess中心fallback或复制改名bundle规则，不手造geometry/追加日志骗过parser。researcher已核[官方ORCA输出说明](gold_compute/queue_20261018/ORCA_OUTPUT_NOTE.md)。同run显式`%output Print[P_Cartesian] 1 end`的825已实际完成，自动826 IRC也完成；新日志仍无Cartesian中心，使用825/826及823/824、相同四watch的[严格复验](gold_compute/queue_20261018/results/IA1/strict_output_trial.json) tc_a5f8e226558142c0仍inconclusive missing TS geometry。该打印开关实测未修复，不再循环verbosity。另已授权一个产物目标不同的同run原生`XYZFILE`输出试验：只加频率输出keyword，检查引擎能否真实产生frequency.xyz并供strict消费，不手造/改名坐标、不改变Hamiltonian或阈值；该XYZFILE试验829已真实完成并生成原生frequency.xyz（与optimized.xyz逐坐标差0、原子序同），自动830 IRC双向收敛；但原样[829/830严格复验](gold_compute/queue_20261018/results/IA1/strict_xyzfile.json) tc_be36a5dc25504c13仍inconclusive missing TS geometry。当前中心资料已原生产生，不能再归咎为没有TS几何。停止全部输出关键词/重复QM。

后续仅一个不改科学证据的文件呈现辨别试验：在新验收包将829/830原stdout以NAME对应的frequency.out/irc.out明确别名和同job原名sidecars共定位，source/destination全SHA必须相等、原源不动、不手造/改名任何几何、四watch和阈值不变。首次整文件read隐式截断导致1042行stdout草稿仅63行，SHA闸门立即拦截并标无效，未运行strict；现仅授权完整分页read→write草稿后逐源SHA核对。只有复制字节完全相同才可作为原字节包试验；不相同不得作证据。此为解析邻接性区分，不等于验收或durable状态修复。当前0 strict pass、不回填目标垒；重复Opt不能治解析问题。

## 上一轮实算收口与未完成边（历史快照，2026-10-18）
全部9条反应边已有实际计算尝试；本轮无继续提交的后台作业，**完整TS目标模式—双向IRC—身份正确零虚频外端闭合为0/9**。六个正式OptTS优化正常且收敛（IA1/IA5/IA8/IA9/IB9-E1/IB10-E1），但均尚无对应同几何最终频率，工程卡在done→frequency接续。它们是驻点候选，不是六个已验TS；当前不能报参考能垒或声称全部可计算边已算完整。IA7另受目标开壳单重态接口不支持；IB10-E2为未定位中间极小且路径/扫描不收敛；IB9-E2针对性IDPP后的789未收敛，另有失败结果未消化的状态缺口。不得把这些类别混写“设计不可达”。

新终态已亲核：IB9 [789原生OptTS](ts/ts_0009/jobs/declaration_0003/ts_opt/.cloudra/calc-789.out.log)经log_parser tc_ae5e031211524dce为normal_termination=true但opt_converged=false（最大步数）；末能仅失败轨迹，不作势垒。IB10 [乙烯酮786](gold_compute/queue_20261018/results/IB10/ketene/.cloudra/calc-786.out.log)正常收敛、0虚频，N2可复用[同项目748](gold_compute/queue_20261018/results/IB9/calc/frag_n2/.cloudra/calc-748.out.log)同版本/方法/环境0虚频组件；787解析失败不代表N2科学不可算。完整产物[788](gold_compute/queue_20261018/results/IB10/P_clean/.cloudra/calc-788.out.log)为SCC250次未收敛fatal，不作已验证复合物。具体逐边证据与缺口统一见[EDGE_STATUS](gold_compute/queue_20261018/EDGE_STATUS.md)，不更改registry/accessible，不生成带虚构垒的标答图。
用户最新要求「只要把所有能算的边算好就行，算不出来的都是设计」：不强求每道设计难题填数，但未实际尝试不等于算不出来。反应边范围为 IA1/IA5/IA7/IA8/IA9 各一步、IB9/IB10 各两步；性质/态序题不混作反应边。本阶段已由新增IA7与IB10 owner补齐实际尝试，IB9原owner完成逆向恢复和第二步针对性跟进，IA8唯一owner完成PM7端点，env完成共同durable阻塞诊断；当前均已收口不再等待旧作业。可计算边须把TS模式、IRC与身份正确零虚频端点闭合；方法局限、搜索未成功和工程阻塞分列，不以失败填零垒或强行改Gold。

**已计算而非承诺**：IA8公开同步job768真实打通PySCF scanner→ASE→MOPAC PM7；[脚本](gold_compute/queue_20261018/results/IA8/pm7_bridge/smoke.py)及[原生PM7输出](gold_compute/queue_20261018/results/IA8/pm7_bridge/CH2OO.out)可查。后续普通job769作有限差分核验，见[原始结构与梯度比较](gold_compute/queue_20261018/results/IA8/pm7_validate/fd_results.json)；随后job776已完成两PM7模型内极小值与自定义全Cartesian梯度差分频率，两步长均9个正振动；[原始wrapper日志](gold_compute/queue_20261018/results/IA8/pm7_validate/.cloudra/calc-776.out.log)、[脚本](gold_compute/queue_20261018/results/IA8/pm7_validate/refine_minima.py)及[原生SP索引](gold_compute/queue_20261018/results/IA8/pm7_validate/refined_results.json)可审计。ΔHf_model(P−R)=−21.867740 kcal/mol，不是严格物理0K电子能或能垒，仍无PM7 TS/IRC完整反应边。

**能量口径更新**：研究者核[官方Hf公式](https://openmopac.net/Manual/SCF_calc_hof.html)：Hf=E_elect+E_nuc−E_isol+E_atom+E_bits，bits含post-SCF氢键/色散；同组成同参数只消原子参考常数，不能省略bits。ASE本次实测energy=final_hof、total_energy另存，原始首版文件不改。另据[官方Hf与total区别](https://openmopac.net/Manual/HoF%20versus%20total%20energies.html)，参数拟合隐含标准态ZPE/内能效应；故PM7结果称参数化Hf/模型势能差、未另加显式ZPE/热校正，不冒称严格物理0K电子能。IA9既有−54.107944 kcal/mol据此限定。 IA9最新必要修复：用户明确授权仅增加1次干预继续IRC，但ts_resume tc_dcc2d25237554e5e仍拒“input revision cannot raise authorized limits”（改source的tc_cf5a83fc2e3d4a77另被拒）；无新作业。需维护者将用户授权接入后端额度，再允许同run把IRC/两侧opt改auto（freq仍numeric）；不手改状态。详见[IA9报告](gold_compute/queue_20261018/results/IA9/REPORT.md)。IA8小型有限差分已支持含bits的Hf与解析梯度一致（12项check最大误差4.3623783×10⁻⁶ Eh/Bohr），继而普通端点与自定义全频已完成，不仅换字段。PM7正式TS/IRC仍无durable后端。

## 用户澄清与当前主线
用户澄清「在pyscf里调pm7我说」：目标仍为 **PM7 + xTB**，新增要求是核实能否在 PySCF 中调用 PM7，并非授权改为 CASSCF/HF/DFT。先前将「试pyscf」理解为更换Hamiltonian是协调者误读，CASSCF替代分派已撤回，不作为本轮答案。env接口核查已完成；已真实验证PySCF通用scanner经ASE调用MOPAC PM7，严格区别于PySCF原生PM7 Hamiltonian，见[接口审计](gold_compute/queue_20261018/ENV_PYSCF_PM7_AUDIT.md)及[IA8实算报告](gold_compute/queue_20261018/results/IA8/REPORT.md)。所有PM7/xTB原生结果继续保留；正式TS/IRC依然只用durable，接口缺口不得绕过。

## 目标和口径
用户要求检查 impossible 难度 benchmark 是否有现行方法可实际计算的边，并尝试以 PM7、xTB 求可复核标答。输入定义见 [十二题交接](gold_compute/queue_20261018/IMPOSSIBLE.txt) 和 [TaskSpec 目录](ideapool/tasks/impossible/)；不照抄旧 Gold。当前 MethodPolicy 未激活；仅将本轮 PM7/xTB 结果当作相应方法内候选，不将 B3LYP 旧数字跨方法挪用。

## 假说与辨别试验（待计算）
优先尝试闭壳、原子守恒且几何连接可核查的边 [IA1](ideapool/tasks/impossible/IA1.json)、[IA5](ideapool/tasks/impossible/IA5.json)、[IA8](ideapool/tasks/impossible/IA8.json)、[IA9](ideapool/tasks/impossible/IA9.json)、[IB9](ideapool/tasks/impossible/IB9.json)。这只是适用性假说，并非势能面已有一阶鞍点的证据。IA1 两端需映射键交替；IA5 反旋不可由顺旋替代；IA9 的双自由基区和 IB9 弱结合体/中间体需要独立核查。
先确认优化端点、频率与电子态；TS 必须有目标成/断键虚频模式，并通过 IRC 两向外端再优化至身份匹配的零虚频极小值。未证实的扫描峰不是能垒；能量使用同方法同级的纯电子能差与原生日志。

## PySCF 调用 PM7 的可行接口（已实算验通，范围见下文）
[PySCF-PM7接口核查](gold_compute/queue_20261018/ENV_PYSCF_PM7_AUDIT.md) 已实测 PySCF 2.14.0 无已安装PM7原生模块；官方semiempirical插件公开清单为AM1/MINDO3，没有PM7模块。但公开 `pyscf.geomopt.as_pyscf_method(mol, scan_function)` 接受返回 `(e_tot, grad)` 的自定义回调。可构造 **PySCF gradient scanner → 自定义回调 → ASE/MOPAC PM7**，准确标明外接后端；不是PySCF自己实现PM7。IA8唯一owner已用普通SP/gradient smoke及后续普通最低点/自定义数值频率实测此链，具体原生证据见下文。
普通shell提交发现范围差异：IA5/IA8/IA1多个异步任务attempt_count=0并报Unsupported job_type shell；但IA9同步 `is_async=false, cpus=1, memory_mb=2048` 的job765/766确有原生PM7结果，不可泛称所有shell失败。后续IA8普通实测已使用成功的公开同步组合，未用Bash绕过拒绝；正式TS/IRC仍无已验PM7/PySCF durable后端。

## 环境核验与当前共同障碍
**新增复现（协调亲核）**：IB9逆向E1的778已自动选峰并完成OptTS780；[原生780](ts/ts_0005/jobs/declaration_0006/ts_opt/.cloudra/calc-780.out.log)经log_parser tc_4e64633f34c24f49核正常/优化收敛、E=−15.181114290730 Eh，ts_inspect tc_94e46a7e28e94289仍waiting/refine无后继频率。IB10 E1的[OptTS785](ts/ts_0007/jobs/declaration_0003/ts_opt/.cloudra/calc-785.out.log)经tc_637d68ec31ac44d6核正常/优化收敛、E=−15.107146400190 Eh，inspect tc_1796a8d81de740a1同样无待补输入却未Freq。至此六个OptTS候选收敛、零个严格边；两者仍无模式/IRC，不能从能量相减报垒。IB9 E2的[782扫描](ts/ts_0009/jobs/declaration_0002/scan/.cloudra/calc-782.out.log)仅拉双CN为单调上升且末帧CC未成环，不能把边界高点作TS或据此认无垒；原owner随后已完成同run映射IDPP同时CC收缩的唯一针对性跟进；正式789达到最大步数未收敛，已据原生失败收口，不继续空等待。
**已收口工程诊断**：[durable阻塞报告](gold_compute/queue_20261018/ENV_DURABLE_BLOCKERS.md)逐run保存权威inspect、原生日志收敛/正常结束行号与摘要。四run均无待补输入，TS方法契约匹配、后继frequency actual=null；当前公开工具没有已核合法reconcile/advance动作。需要受权后端核终态事件接纳/阶段结果认可并幂等接续频率；external-MLIP解析fallback只是待定位假说。已决定不重复无关resume、不手改状态/预算、不手动TS/IRC；在修复前将这四条归工程阻塞，不作设计不可达或化学失败。
[环境审计](gold_compute/queue_20261018/ENV_PM7_XTB_AUDIT.md) 已核 ORCA 6.1.1 / xTB 6.7.1 和本轮安装的 MOPAC 23.2.5。PM7 的 ORCA 关键字拒绝只证明此引擎不支持，MOPAC 原生日志即使未被原 scorer 读入仍是科学尝试；不能伪装日志格式。
协调者复核 ts_inspect：IA8 ts_0001 的 job739、IA9 ts_0003 的 job751、IA5 ts_0004 的 job756 已结束；log_parser 的 external-MLIP fallback 报正常终止与优化收敛，却无自动后继频率、stage=refine/status=waiting/next=wait_for_system。这是可复现的流程推进障碍，并非反应物理不可达。TS/Freq/IRC 只能按 durable 流程，若仍不推进应报告具体修复缺口，不绕过或改原生证据。

## 已直接观察的事实与安排
[十二题交接](gold_compute/queue_20261018/IMPOSSIBLE.txt) 逐题说明旧方法局限、目标反应及不能照抄的数值。本轮已并行分派 IA1、IA5、IA8、IA9、IB9 实算，另有环境能力检查和独立方法筛选；已有端点与接口计算结果，尚无TS/IRC/端点完整闭合的反应边；最新数值以下方owner章节和原生日志为准。
初始计算队列空闲（2026-10-18 query_compute_queue），不意味着 PM7/TS/IRC 可用。专家分别在 gold_compute/queue_20261018/results/<ID>/ 保存输入、原生输出和报告；若流程阻塞则明确记录工具/方法障碍，不把失败写成零势垒。

## 方法可行性筛选（researcher，2026-10-18；修订，替代早先过强判断）

**口径纠正**：文献多参考风险不是accessible=false的充分依据；取代吡唑啉实验Ea不能确定本题RDS；某级别CCSD误差不能预测xTB误差。旧版相反断言撤回。

### 引擎边界
本机ORCA6.1.1直接`! PM7`被拒，见[原日志](gold_compute/queue_20261018/results/IB9/probe_pm7/t_pm7.out)。这仅是该调用的事实；Gaussian对PM7支持未知，不能称“PM7只能MOPAC”。MOPAC是已探索的实现途径，科学结果与TaskSpec的ORCA/Gaussian格式限制分列。GFN2-xTB优化/NumFreq已有[原生证据](gold_compute/queue_20261018/results/IA1/.cloudra/calc-731.out.log)，不等于TS/IRC完成；最新结果以下方owner章节为准。

### 实用排序（待检验假说，可被实算修正）
| 顺序 | Spec/必要边 | 待检验风险与核验重点 |
|---|---|---|
| 1 | [IB9](ideapool/tasks/impossible/IB9.json) E1 | RC重氮甲烷+乙烯→1-吡唑啉，成1–5/3–4；闭壳环加成相对适合先试，但弱结合软模和环翻转需核。E2脱氮成环另算，**RDS未定**。 |
| 2 | [IA1](ideapool/tasks/impossible/IA1.json) E1 | 矩形→方形候选→键交替互换的矩形；同SMILES不够，需映射。方形多组态风险高，但是否一阶仅由实际Hessian决定。 |
| 3 | [IA5](ideapool/tasks/impossible/IA5.json) E1 | 反旋开环，断3–4并重排π键；以虚频完整向量和IRC末端CH2旋向判别，不能仅用a'/a''标签、产物身份或旧顺旋35.17。 |
| 4 | [IA9](ideapool/tasks/impossible/IA9.json) E1 | 断O3–O4/C1–C2→两甲醛；双自由基阶段/多步可能待实算，不强迫concerted；单态IRC不验证发光非绝热机制。 |
| 5 | [IA8](ideapool/tasks/impossible/IA8.json) E1 | CH2OO→二氧杂环甲烷，成1–3、降1–2，另需isomerization_energy；旧不可达标签不否定本轮方法内极小，见owner端点证据。 |
| 6 | [IA7](ideapool/tasks/impossible/IA7.json) E1 | Z-烯二炔成1–6→p-苯炔，另需reaction_energy；开壳单重态电子占据需核，不能凭成环键断言假苯环。 |
| 7 | [IB10](ideapool/tasks/impossible/IB10.json) E1/E2 | 脱N2→单重态甲酰卡宾→乙烯酮；H6必须C4→C3。卡宾态与复合物软模增加成本，但闭合能力待测；撤回PM7无色散、IRC不可能闭合的断言。 |

### 方法内已验证边与真实物理高精度标答
- **方法内已验证边**：指定PM7/GFN-xTB版本及占据方案，收敛TS有且仅有一个目标虚频，双向IRC与身份正确的零虚频外端闭合；同模型同方法纯电子能差可作为明确限定的方法内参考垒。文献风险不一概排除这类能量，也不自动改accessible。
- **物理高精度**：上述自洽不是精度保证。强静态关联、态交叉仍需电子态跟踪与独立高精度验证。GFN-xTB自旋数/分数占据不等于自旋纯开壳单重态或多态耦合；单态IRC不证明跨态动力学。PM7的UHF/CI能力需核具体实现，m1收敛不证明目标态。诊断缺口不是无垒/物理不可达。

### 文献与适用边界
- IA1：[MR-AQCC2006](https://doi.org/10.1063/1.2222366)含ZPE6.3；[MR BWCC2000](https://doi.org/10.1063/1.481494)；[1988研究](https://doi.org/10.1063/1.454956)特定级别CCSD19.9与双参考GVB-CISD9.0；[2022参考能](https://doi.org/10.1021/acs.jpca.2c02480)。仅说明方法敏感，**不推出xTB/PM7误差方向、倍数或15–25范围**；含ZPE不能直接对标电子垒。
- IA5：[Chem Sci2025](https://doi.org/10.1039/d4sc08748h)、[ChemRxiv预印本](https://doi.org/10.26434/chemrxiv-2023-grc74)是检查Hessian/路径的动机，不证明本体系反旋TS必为二阶。
- IA7/IA8/IA9原始线索：[题源A7–A9](ideapool/reaction_candidates/impossible.md)，包括Kraka & Cremer1994 JACS116,4929；Li/Carter/Bowman/Dawes/Xie/Guo2014 JPCL5,2364；[De Vico2007](https://doi.org/10.1021/jp074063g)。CH2OO文献T1=0.043不是本轮诊断，更不证明xTB无极小。
- IB9：[1974取代物实验](https://doi.org/10.1139/v74-602)Ea39.8只提示脱氮可能重要，**不是本题母体纯电子垒，不能确定E2为RDS**；待本体系同模型两步计算及动力学口径核验。
- 检索限制：OpenAlex仅取得元数据/摘要；web search/browser因deepseek_api_key缺失失败，未完成全部原文/SI核查，因此不作超出这些材料的精确数值背书。

下一步：按端点→TS→NumFreq→双向IRC→外端Opt/Freq核验，IA1特别核Hessian和映射键交替、IA5核反旋。扫描峰、搜索失败、解析/流程阻塞不作势垒，不自动改accessible。

## 后续
本轮日志与作业状态已返回并经协调复核，未有完整反应边可报垒。六个收敛候选首先需要受权durable后端修复done→Freq接续，随后仍须核目标模式、IRC方向和正确外端；不能以候选能差代替这一步。已计算证据与尚未验收分列见总表。后续编辑前读最新文件，避免覆盖彼此内容。


## IA8：CH2OO → 二氧杂环甲烷（small_mol）
**模型与假说**：题设气相热单分子，q=0/m=1；无水、酸碱、对离子，温度未指定。本轮用孤立 CH2O2、闭壳单重态 GFN2-xTB 表示该近似，未计算多参考/开壳 singlet；电子能差不混热校正。映射 1=C、2=近端O、3=末端O、4/5=H；目标 C1–O3 成键、C1=O2 降阶，O2–O3 保留。成环须耦合 C–O 伸长/弯曲与碳平面外运动。
**直接观测**：ORCA 6.1.1 GFN2-xTB 的 [CH2OO Opt+NumFreq](gold_compute/queue_20261018/results/IA8/explore/.cloudra/calc-729.out.log) 与 [dioxirane Opt+NumFreq](gold_compute/queue_20261018/results/IA8/explore/.cloudra/calc-730.out.log) 均正常结束、优化收敛、0虚频；E 分别 -11.128183799630 / -11.177883683330 Eh，方法内 ΔE=-31.1871 kcal/mol。独立端点尚非 IRC 外端验证。
[1D约束扫描](gold_compute/queue_20261018/results/IA8/explore/.cloudra/calc-721.out.log) 发生大跳变，峰不能作能垒。durable [ts_0001](ts/ts_0001/process.json) 的 xTB path 100轮未收敛；改 IDPP 后 [OptTS 739](ts/ts_0001/jobs/declaration_0003/ts_opt/.cloudra/calc-739.out.log) 优化收敛至 E=-11.083861872140 Eh，仍仅候选。流程停留 waiting/refine（739 已 done、频率目录空），changes={} 也不能推进；暂无一虚频/IRC，故不声明势垒。
**PM7 / PySCF 澄清**：MOPAC 23.2.5 已安装；普通端点脚本 [run_opt.sh](gold_compute/queue_20261018/results/IA8/pm7/run_opt.sh) 曾经公开 submit_compute_job(job_type=shell) 接受为 job763，但最新终态为 failed，attempt_count=0，last_error="Unsupported job_type: shell"，无分子输出。这是提交后端拒绝，不是PM7科学失败；未转Bash绕过。用户要求在PySCF调用PM7，未授权CASSCF/HF/DFT替代；IA8未提交任何该类作业。env核已装PySCF无PM7接口；ASE→MOPAC是外部程序接口，不得标成PySCF PM7。xTB durable仍缺频率/IRC。


### PySCF 外接 PM7 最小实测（job768）
已实际打通 **PySCF 2.14.0 通用 as_pyscf_method scanner → 自定义回调 → ASE 3.29.0 → MOPAC 23.2.5 PM7**，不是PySCF原生Hamiltonian。仅沿用xTB零虚频两端几何作普通单点+梯度；气相q0/singlet、原子序C/O/O/H/H不变。PySCF Mole仅坐标/状态容器，无轨道基组；日志空basis警告并非做了HF/DFT。单核/2048MB、显式限制OMP/BLAS。公开同步shell提交job768，call_id tc_bfbbf076f522497d，state=done；此前异步job763失败不能推广至同步通道。
脚本 [smoke.py](gold_compute/queue_20261018/results/IA8/pm7_bridge/smoke.py)，[wrapper日志](gold_compute/queue_20261018/results/IA8/pm7_bridge/.cloudra/calc-768.out.log)，[结构/力/梯度与ASE字段](gold_compute/queue_20261018/results/IA8/pm7_bridge/results.json)。原生 [R.out](gold_compute/queue_20261018/results/IA8/pm7_bridge/CH2OO.out) / [P.out](gold_compute/queue_20261018/results/IA8/pm7_bridge/dioxirane.out) 均PM7、RHF九个双占轨道、SCF FIELD WAS ACHIEVED、JOB ENDED NORMALLY；同目录各自.mop/.arc保留。关键词PM7 1SCF GRADIENTS SINGLET PRECISE DISP RELSCF=0.0001；ASE中charge=0（中性在原生输入省略CHARGE）。
**能量口径警告**：ASE get_potential_energy实测取final_hof，不是total_energy。回调返回R/P=0.05065501211154344/0.01691429443161306 Eh，分别对应Hf=31.78650/10.61388 kcal/mol，不能称纯电子总能。原生TOTAL ENERGY（电子+核排斥、另列dispersion）为−735.40815/−736.32705 eV；原生日志对Hf的dispersion修正另列，不混这两口径。坐标Å；回调grad=−forces×Bohr/Hartree，单位Eh/Bohr；梯度范数R=0.0836382638、P=0.1119499284，明显非PM7驻点。首个碳x梯度R为+0.026277664 Eh/Bohr，与原生+31.160607 kcal/mol/Å方向一致。未做有限差分复核，未优化/频率/TS/IRC，不形成PM7绝热反应能或标答边；本次只证明真实接口可调用。


### PM7端点延伸校验：已得模型内极小值，仍非严格反应边
[有限差分脚本](gold_compute/queue_20261018/results/IA8/pm7_validate/fd.py) 与 [结果](gold_compute/queue_20261018/results/IA8/pm7_validate/fd_results.json)，job769（tc_aeb1d2b84ffd4da4）：两端各C1x/O2x/O3z、h=0.001/0.002Å的12项中心差分，Hf对返回解析梯度最大误差4.3623783×10⁻⁶ Eh/Bohr，支持采用含bits的Hf gauge；并非全坐标严格误差界。单位/负号沿用首版。
[首次BFGS普通优化770日志](gold_compute/queue_20261018/results/IA8/pm7_validate/.cloudra/calc-770.out.log) 两端precision loss，残差4.3855×10⁻⁵/5.0718×10⁻⁵ Eh/Bohr，未达事先2×10⁻⁵阈值，未跑频率。能量输出量化限制线搜索只是解释假说，不是已排他确证原因；失败保留。
经一次授权的[梯度修正脚本](gold_compute/queue_20261018/results/IA8/pm7_validate/refine_minima.py)以当前近极小几何普通least_squares梯度残差修正，无TS搜索。job776（tc_8c85d07237cc4d58）[原始wrapper日志](gold_compute/queue_20261018/results/IA8/pm7_validate/.cloudra/calc-776.out.log) / [全部原生作业索引、残差和频率](gold_compute/queue_20261018/results/IA8/pm7_validate/refined_results.json)：R/P max梯度=1.6022654×10⁻⁸/8.4329756×10⁻¹⁰ Eh/Bohr。所有MOPAC回调均检查SCF FIELD WAS ACHIEVED/JOB ENDED NORMALLY；自定义优化的收敛证据是残差及后续Hessian，不是MOPAC原生Opt声明。
完整15×15 Cartesian梯度中心差分Hessian，h=.003/.005Å；按ASE原子质量质量加权，以质心坐标构建3平移+3转动刚体向量，通过null_space投影至9维振动子空间。两步长各9频全正，R最低527.8813/527.8587、P889.8246/889.8303 cm⁻¹；全谱最大步长差约0.023cm⁻¹。Hessian反对称最大R9.67×10⁻⁶/2.91×10⁻⁵、P6.40×10⁻⁶/1.76×10⁻⁵ Eh/Bohr²，先报告反对称量后对称化。**这是自定义全数值频率，不是PySCF或MOPAC原生频率日志；原生SP输入/.out/.arc逐次保留，脚本和.npy矩阵可重建分析。**
[最终R几何](gold_compute/queue_20261018/results/IA8/pm7_validate/CH2OO_refined/final.xyz)保持无环CH2OO：C1-O2=1.291、O2-O3=1.245、C1-O3=2.186Å；[最终P几何](gold_compute/queue_20261018/results/IA8/pm7_validate/dioxirane_refined/final.xyz)为C1-O2-O3三元环：C-O各1.399、O-O1.459Å，C/O/O/H/H原子序不变。R短O-O被通用单键阈值标compressed，P角偏差为三元环预期几何，不掩盖这些观察。
PM7参数化Hf/模型势能R/P=0.047150682549204584/0.012302220637635744 Eh；Δ(P−R)=-21.867740 kcal/mol。**同组成差消原子参考常数但保留氢键/色散bits；PM7 Hf拟合298.15K标准态，参数含隐含ZPE/热贡献，故不称严格物理0K无ZPE裸电子能。**未额外加显式ZPE/热修正。官方定义：https://openmopac.net/Manual/SCF_calc_hof.html 与 https://openmopac.net/Manual/HoF%20versus%20total%20energies.html 。尚无TS模式/双向IRC，不能将两独立极小值冒充已验证反应边，也不混xTB能量。最新ts_inspect tc_c28373f16f034af2仍waiting/refine、wait_for_system，无可编辑必填；未手动绕过。


### xTB恢复历史与当前进展
**最新直接观察覆盖下述旧阻塞**：durable已完成同几何NumFreq790（[原日志](ts/ts_0001/jobs/declaration_0005/frequency/.cloudra/calc-790.out.log)），正常终止、唯一虚频−950.34cm⁻¹；双向IRC796已实际running，尚非完成。模式启发式称H4-H5相对位移1.259大于C1-O3/.351、C1-O2/.368；因轻H位移放大与坐标耦合，保留IRC继续以实际双向连接检验，暂不认定反应模式合格；完整模式parser未返回。最终仍须IRC外端Opt/Freq及ts_guess strict pass。


**后续796/804及区分试验**：IRC796原日志解析双向14/11点且两向收敛，端能−11.128163/−11.177871Eh；800 opt正常收敛−11.12818380306Eh，804零虚频最低503.54cm⁻¹，但durable判opt/source/freq几何不一致，candidate_only。工具导出[800末帧](gold_compute/queue_20261018/results/IA8/reactant_opt_800_last.xyz)身份无环CH2OO（C1-O2 1.253、C1-O3 2.222、O-O1.292Å）。ts_guess strict显式重原子watch call tc_a26dfc66d325477d返回fail（模式相对位移阈值），不能声称pass；实际IRC与启发式是否矛盾待查。区分试验：同run ts_resume tc_b8c0c4d4ba784e5a将reactant seed绑定800日志真实末帧，保留739/790/796，重建opt/freq以排查来源不一致；已实际提交816，未完成，不替换为独立旧端点、不报垒。


**819后当前结论/模式区分试验**：816优化正常收敛、819正常零虚频（最低503.65cm⁻¹），但仍相同三几何mismatch；一次显式seed不能消错，停止重复Opt。env直接文件对照证decl6原生final xyz与saved差最大4.829626e-7Å且四舍五入6位逐值相等，具体validator阈值未确认。原生[frequency.hess](ts/ts_0001/jobs/declaration_0005/frequency/frequency.hess) mode6全位移投影见[mode790_analysis.json](gold_compute/queue_20261018/results/IA8/mode790_analysis.json)：C1-O3键向−0.349093、C1-O2+0.056110、O-O+.093505；H-H相对norm1.258783但键向仅−.000269，主要横向，不能由norm主导推为H-H伸缩。碳相对O2沿CHH瞬时平面法向−.312209（不是完整面距导数）。[IRC B外帧](ts/ts_0001/jobs/declaration_0005/irc/irc_IRC_B.xyz)无环CH2OO（C-O1.254/2.217Å）；[IRC F外帧](ts/ts_0001/jobs/declaration_0005/irc/irc_IRC_F.xyz)三元环（C-O各1.360Å）。这些支持耦合成环假说，仍保留ts_guess显式watch strict fail；未删watch/改阈值，未宣称验收通过。需工具处理可复核模式反例及几何量化一致性，产品外端验证尚未生成。

以下为修复前历史（不再代表当前作业状态）：
按最新要求同run执行一次科学相关恢复：xtb2irc的frequency_mode由numeric纠正auto（IRC非频率任务），加TightSCF保障SCC梯度；NumFreq已为TightSCF numeric，端点opt auto/freq numeric保留。ts_resume **tc_f4837158d0b94d28**返回tool_exception、effect_state=unknown；后ts_inspect **tc_5e586421a75c45f3**确认声明改动已生效，但revision24仍waiting/refine，next=wait_for_system、required_inputs=[]、editable_groups=[]，TS frequency/IRC actual均null，仅原733/739作业。完整错误及inspect返回见[当前恢复证据JSON](gold_compute/queue_20261018/results/IA8/current_recovery_evidence.json)。
由于没有频率日志/IRC，不能执行成功strict验证；为明确缺证据，用现有OptTS739调用ts_guess(mode=verify,strict=true) **tc_d6051b973a124d6d**返回is_success=false、Failed to parse vibrational frequencies，verification_status为空。完整请求/返回见[ts_guess当前strict诊断](gold_compute/queue_20261018/results/IA8/ts_guess_strict_current.json)。这不是目标模式或IRC科学失败，更不是pass；未伪造IRC路径。**本次实际frequency/IRC提交数为0**，目标虚频、双向IRC和各自外帧Opt/Freq证据都无法在当前durable状态生成。不回填能垒或已验证图；已将精确call与缺口交协调者工程处理，不开新run、不shell绕过、不无限轮询。


### 定向tight复查过程（历史，已完成）
已用原生790 .hess完整带符号mode6及796近TS F/B前三帧作无新QM方向复查：[可重现脚本](gold_compute/queue_20261018/results/IA8/tight_mode_review/direction.py)、[来源SHA与数表](gold_compute/queue_20261018/results/IA8/tight_mode_review/direction_results.json)。原子序C/O/O/H/H不变；ORCA Cartesian位移转sqrt(m)质量加权，IRC先质量加权Kabsch对齐，双方同一metric投影6刚体方向并各自单位归一。首帧cos F≈+1/B≈−1，但首帧为算法初始化，非独立证明；第二/第三有限弦abs cos F=.93785/.92531、B=.96654/.96168。F首帧C1-O3缩.03843Å，B伸.03844Å，模式径向导数C-O3−.349093/C-O2+.056110/O-O+.093505；H-H径向−.000269而横向相对位移大，支持反应耦合弯曲而不是单纯H-H伸缩。保留strict fail及物理适用性风险，方向一致不替代验收。
原默认739输入未TightOpt；本轮一次同方法/同占据TightOpt TightSCF已通过同run ts_resume完整配置替换，call tc_6f97ad51b6ca4aaa，正式OptTS834已ready（[输入](ts/ts_0001/jobs/declaration_0007/ts_opt/refine.inp)）。先前引用stage直接patch被输入诊断拒绝tc_e985851ae46e4ca3，不是科学失败；[更正后完整回执](gold_compute/queue_20261018/results/IA8/tight_mode_review/tight_resume_corrected.json)。未改watch/阈值/预算，旧790/796/fail完整保留为历史；待新频率/IRC实际结果比较，不预承诺Gold。


### Tight定向复查结果（已完成，无新增Gold）
原739末次内部收敛表RMS/MAX gradient=.0000527295/.0001700857，容差.0001/.0003；834 TightOpt对应.0000265566/.0000785153，容差.00003/.0001。最终外部梯度norm由.000159187584降至.000076331097 Eh/bohr。实际两者xTB调用仍--acc .2、SCC能量2e-7Eh、wf2e-5e、电子温300K、unpaired0；**几何阈值确实收紧，但TightSCF未使已观察后端精度改变**。原生来源739末表约4500行、834末表约4900行，及各自末尾xTB SETUP/SUMMARY。
835最终.hess的vibrational_frequencies索引6为唯一负值−950.47（旧790−950.34），normal_modes同列6；atoms为相应最终TS中心、Bohr坐标，IRC同序C/O/O/H/H。新模式与新836轨迹比较见[完整带SHA数表](gold_compute/queue_20261018/results/IA8/tight_mode_review/direction_tight_results.json)及[脚本](gold_compute/queue_20261018/results/IA8/tight_mode_review/direction_tight.py)。质量参与率C/O/O/H/H=21.65/23.86/21.91/20.57/12.01%，重原子67.42%；全体系质量Kabsch对齐后截取重原子单独归一，F2/3 cos=.96841/.96622，B2/3=−.98733/−.98987（此重原子指标不再单独拟合刚体，避免三原子过拟合）。因此全方向相合不是仅H运动主导的假象；首帧是初始化，2/3为有限弦不是严格局部切线。C-O3导数−.349138、C-O2+.056113、O-O+.093503、H-H−.000258；支持C-O成环伴随CH弯曲的耦合方向，未证明物理高精度。
Tight后仍[ts_guess strict fail完整返回](gold_compute/queue_20261018/results/IA8/tight_mode_review/strict_tight.json)，call tc_5c084717219e41c9；watch与阈值未变。836 IRC已完成，838反应物频率后仍三几何mismatch/candidate_only，产品外端未启动。tight未消除两个验证问题，不反复优化，不称strict误报已确证，不回填Gold/目标垒；本轮定向复查完成。

**IA8最终状态**：无后台，不追加QM。原790/新835各唯一负频均列6；同质量metric/坐标旋转/刚体投影后负模直接abs cos full=.9999999934/heavy=.9999999990，见[mode_overlap](gold_compute/queue_20261018/results/IA8/tight_mode_review/mode_overlap.json)。方向证据较强、tight前后稳健，但实际SCC精度同前，strict call tc_5c084717219e41c9仍fail、端点几何验证仍未过，不回填物理Gold；不是把fail预定为误报。


### 真正端点参考strict定向核查（当前）
**来源纠正改变测试**：837来自旧796 B→800显式seed，不满足836-own；协调已撤回不重复R限制，授权从836 B一次新普通Opt/Freq。P840从836 F已正常优化收敛/零虚频（最低1020.46），不重复P；尚未做跨轮837+P strict。配齐本轮两侧各自优化末帧才做唯一规范strict，消除来源混淆，不是调参循环。
此前strict_tight_request用explore独立端点，不应称endpoint-relaxed strict。当前inspect tc_30a98d826c994eab证P opt actual=null，R三几何校验阻止自动接续。R837/838是显式800末帧seed谱系（800来自旧796 B），不是836 B直接新种子；复用其正常Opt/零虚频但明确跨tight轮来源，不重复R。公开ts_guess verify合同未暴露endpoint优先开关或单独endpoint-match接口。为补真实缺口，已从[836 F原生外帧](ts/ts_0001/jobs/declaration_0007/irc/irc_IRC_F.xyz)合法普通Opt+NumFreq提交840，GFN2-xTB/q0m1/TightSCF，非手动TS/IRC，也不替代durable验收；[输入](gold_compute/queue_20261018/results/IA8/endpoint_strict_review/product_optfreq.inp)。待P正常/零虚频后，仅一次835/836+原watch+两侧原生优化末帧strict，来源限制如实保留，不预承诺pass。

**836-own端点检验最终结果**：新R841来自836 B、新P840来自836 F，均普通Opt正常收敛且0虚频，最低503.56/1020.46cm⁻¹；原子序身份映射不变。真实外端→新final质量对齐RMSD .00463465/.00190746Å，来源SHA与数值见[配对表](gold_compute/queue_20261018/results/IA8/endpoint_strict_review/endpoint_comparison.json)。仅一次835/836+新pair+原watch strict call tc_8b3a7df380064bda仍fail，checks止于负模misalignment、无端点匹配返回；[完整参数/返回](gold_compute/queue_20261018/results/IA8/endpoint_strict_review/strict_own_endpoints.json)。故此前独立端点strict不代表本检验；此次实际也未兑现端点一致优先通过行为，不能宣称端点比较已fail或永久算法规则。公开合同无其他endpoint优先开关，不猜参数。两同源极小值现已具备但未pass，不回填Gold；无后台、不再QM。

## IA1 实算（small_mol）
- 模型：孤立气相 C4H4、q=0/m=1；无酸碱/离子/溶剂参与者。题设低温基质具体材料与温度未知，本模型不含基质、隧穿或动力学，仅考察电子PES。预期四个环C保持身份，1–2/3–4键级降低、1–4/2–3升高，需耦合键长交替而非断环。
- 已观察：[矩形原生Opt+NumFreq日志](gold_compute/queue_20261018/results/IA1/.cloudra/calc-731.out.log)给E=-10.444857273820 Eh、零虚频（最低振动507.5 cm⁻¹），ORCA6.1.1调用xtb6.7.1的GFN2-xTB。闭壳种子声明不等于自旋纯多参考单重态证明。
- [PM7原生失败](gold_compute/queue_20261018/results/IA1/.cloudra/calc-719.out.log)为ORCA不识别PM7；本机PATH无Gaussian/MOPAC，不以PM3/AM1/xTB冒称PM7。
- [扫描737](gold_compute/queue_20261018/results/IA1/.cloudra/calc-737.out.log)只到1.46Å为单调；[延伸749](gold_compute/queue_20261018/results/IA1/.cloudra/calc-749.out.log)在更长键长发生另两键收缩/跳支，内部峰仅提供初猜，未报势垒。扫描解析watch_pairs的索引/元素显示不一致，后续以durable实际结构表复核，不靠该表认定路径。
- durable `ts_0002` 已选择显式列出的完整映射候选0（产物具体绑定1,4,3,2并保持附H），TS优化job752达到最大优化步数未收敛，不能称为TS；见 [失败原生日志](ts/ts_0002/jobs/declaration_0005/ts_opt/.cloudra/calc-752.out.log)。同run改为相邻短键伸长/长键缩短的耦合扫描job755，17点未发现可用内部峰，现已阻塞（[扫描日志](ts/ts_0002/jobs/declaration_0006/scan/.cloudra/calc-755.out.log)）。这两种尝试不证明TS不存在；后续可从对称方形约束优化/全Hessian生成更合适种子，仍须durable正式优化与IRC。当前无作业在跑，不能产出严格合格边，无ΔE‡或ΔErxn可交付；详见[IA1报告](gold_compute/queue_20261018/results/IA1/REPORT.md)。


## IA5 — 反旋开环实算（负责章节）
**最新科学结论：756/792/799实为顺旋竞争开环，不是IA5目标反旋。** [完整旋向审计](gold_compute/queue_20261018/results/IA5/ROTATION_AUDIT.md)固定C/H身份，以共同观察轴跟踪两CH2，F四氢增量(+22.13,+33.00,+22.16,+33.02)°、B(−18.59,−26.64,−18.62,−26.66)°；两端同向且跨端配对一致，非单碳扭角或H主导启发式推断。目标反旋未定位，无目标垒；停止为该顺旋候选重复端点/strict修复，本轮不新TS。下文身份未定为历史。
最新恢复：NumFreq792恰一虚频−769.34cm⁻¹；[IRC799](ts/ts_0004/jobs/declaration_0006/irc/.cloudra/calc-799.out.log)已双向实际完成，F环r34=1.551Å、B开链2.789Å/末端双键1.327Å。自动R807/809因log/source/freq几何不一致失败；显式以原生IRC F/B seed重算[815](ts/ts_0004/jobs/declaration_0007/reactant_opt/.cloudra/calc-815.out.log)/[818](ts/ts_0004/jobs/declaration_0007/reactant_frequency/.cloudra/calc-818.out.log)仍同错，已交env核验，不再重复seed。B骨架扭41.9°仅提示可能顺旋，须完整CH2旋向证明，尚无反旋验收或strict pass。下文旧“未Freq/IRC”仅历史。
最新PM7补算：普通端点shell761/762虽入队ready，终态均failed/attempt_count=0，`Unsupported job_type: shell`，无MOPAC原生输出，不能称已算/在跑；输入留[pm7目录](gold_compute/queue_20261018/results/IA5/pm7/)，未Bash绕过。PySCF调PM7适配与后端缺口由env核，不改Hamiltonian。
气相热单分子C4H6，q0/m1，无水/酸碱/对离子，温度未指定；孤立GFN2-xTB闭壳PES仅方法内检验，不描述多参考或激发态。C3–C4断裂必须耦合两末端CH2反向旋转，丁二烯身份本身不能判方向。
[RC日志](gold_compute/queue_20261018/results/IA5/work/rc_xtb.log)收敛0虚频E=-11.557969661030 Eh；[独立s-trans产物](gold_compute/queue_20261018/results/IA5/work/prod_strans.out)收敛0虚频E=-11.552702001440 Eh，均非IRC端点证明。[PM7探测](gold_compute/queue_20261018/results/IA5/_engine_test/pm7_sp.stdout)为ORCA6.1.1关键字拒绝，不是科学搜索失败。
[durable ts_0004](ts/ts_0004/process.json)已核无氢迁移映射候选0；[扫描753](ts/ts_0004/jobs/declaration_0003/scan/.cloudra/calc-753.out.log)固定平面碳骨架探索C3–C4有内部峰，仅种子。修复frequency_mode输入冲突后job756已done且协调log_parser确认正常结束/优化收敛；ts_inspect仍waiting/refine、next=wait_for_system，频率未启动。一次明确numeric频率声明的ts_resume报内部失败（无backend call_id），不再改无关字段唤醒。待Hessian指数、模式、IRC及外端验证，尚无反旋势垒；详见[IA5审计报告](gold_compute/queue_20261018/results/IA5/REPORT.md)。旧顺旋35.17不填本题。

## IA9 — GFN2-xTB 实算（负责章节）
已核q0/m1气相热解与映射：断C1-C2/O3-O4，C1-O4/C2-O3升双键；温度未知，孤立基态模型不能覆盖发光激发态动力学。详见 [IA9报告](gold_compute/queue_20261018/results/IA9/REPORT.md)。[R727](gold_compute/queue_20261018/results/IA9/orca/.cloudra/calc-727.out.log) 与 [CH2O728](gold_compute/queue_20261018/results/IA9/orca/.cloudra/calc-728.out.log) 是GFN2-xTB（ORCA6.1.1/xtb6.7.1）同级收敛0虚频极小值；分离组分ΔE约-11.82 kcal/mol不是IRC端点证明。PM7原生[724](gold_compute/queue_20261018/results/IA9/orca/.cloudra/calc-724.out.log) ORCA关键字拒绝；当时PATH无Gaussian/MOPAC，后续同事已安装隔离MOPAC23.2.5，公开shell通道已实际成功：普通PM7 Opt765和FORCE766，原生[结果](gold_compute/queue_20261018/results/IA9/pm7/R_force.out)与[甲醛](gold_compute/queue_20261018/results/IA9/pm7/CH2O_force.out)均正常、振动全正，最低202.69/1099.59 cm⁻¹；Hf差-54.10795 kcal/mol不冒充已核电子反应能。durable/scorer仍不支持MOPAC，不能产严格PM7边。O-O及耦合扫描有跳谷，均不报势垒。durable ts_0003已选择保持C-O映射候选0，修正输入频率模式后TS job751正常/优化收敛 E=-14.236925919280 Eh，但ts_inspect tc_c53147947c6549da仍waiting/refine、next wait_for_system；必要endpoint-opt模式修订ts_resume tc_87c3e5e99c96434b被intervention limit exhausted拒绝。待流程修复、反应模式、频率、IRC与外端验证，当前无合格边，不改登记科学标签。

## IB9 — 实算进展
**只读解析/软模补审**：完整实际strict请求与未删减返回已保存gold_compute/queue_20261018/results/IB9/independent_endpoints/STRICT_FULL_RECORD.json（复现call tc_aa51e9efa8f64325仍inconclusive），含提取strict_verify/irc_end_a.xyz及irc_end_b.xyz路径。794的.cloudra日志父目录有frequency.hess/inp/optimized.xyz、没有frequency.xyz；798父目录有原生F/B终帧与轨迹，未移动/改写。822两软模中−36.41重原子非质量加权位移份额0.00211（H11/H10主导），−8.99份额0.11118（H6–H9主导）；仅能说H主导，未证纯刚体相对摆动、不能排除内模/称数值噪声。B原生optfreq.xyz组分间反应距3.379/3.251Å，组分内CC1.317、CN1.252、NN1.129Å。parser缺口与B非零虚频独立，不新增任务；env获原路径核解析条件。
**独立端点与strict已实际完成，未通过**：F821同日志Opt+NumFreq正常/优化收敛/零虚频最低95.30，E−15.28200646346 Eh，NAME原生optfreq.xyz为吡唑啉；B822正常/优化收敛但软虚频−36.41/−8.99，E−15.19012144179 Eh，正确两组分、反应距3.379/3.251Å，尚非验证RC极小值。ts_guess strict `tc_1764b3279cb64414`已用794/798原日志、两侧NAME最终XYZ、ORCA watch_pairs[[0,4],[1,2]]执行：verification_status=inconclusive，missing TS geometry；确认n_imag=1、mode aligned，F IRC收敛/B未收敛，外帧已提取。缺口是B非零虚频与TS几何提取不可用，独立验证不绕过这些事实。参数/紧凑返回见gold_compute/queue_20261018/results/IB9/independent_endpoints/STRICT_RECORD.json（非原生证据）；原日志F/.cloudra/calc-821.out.log、B/.cloudra/calc-822.out.log在同目录。各侧一次授权已用尽，不再提交、不报正向或逆向垒，不声称durable validator已通过。
**授权独立端点科学验证已提交**：从798自身原生IRC_F/B外帧，非SMILES重建，分别普通无约束Opt+NumFreq同一日志job821/822（ready）；输入gold_compute/queue_20261018/results/IB9/independent_endpoints/{F,B}/optfreq.inp已预注smiles，GFN2-XTB气相q0m1/4核4GB、constraints=[]。各侧仅一次；不改durable/原证据/阈值，无手动TS/IRC。完成后核同日志收敛/零虚频、NAME原生最终XYZ/身份，并以794/798原样和正确watch_pairs作ts_guess strict；仅明确pass后建议正向能垒，不冒称durable validator通过。
**明确IRC seed重试后仍几何mismatch（当前阻塞）**：813优化正常且收敛（parser tc_6e7aa21ad4c24b9e，E−15.28200646346 Eh），814频率正常/零虚频最低95.30（tc_cfeae326eeba4838，E−15.28200646310），但rev74再次candidate_only：optimization log / saved frequency source / frequency log geometry mismatch。不是零虚频失败，也尚无证据说连错物种。已向env提供declaration_0007原生813/814及optimized.xyz/input与旧803/806供只读精度/NAME来源诊断，不再盲目重交相同seed；另一端尚未自动验证。794/798已有真实Freq/双向IRC，旧no-submit障碍仅历史；当前无strict pass、无垒可报，待一致性检验修复再续。
**E1频率/IRC已实算，端点来源修复中**：794恰一虚频−367.39 cm⁻¹，durable模式aligned（1–5/2–3相对位移0.924/0.848）；798双向IRC F16/B20点正常结束，未两向本征收敛。原生F外帧为五元环1–5/2–3=1.544/1.452Å，B外帧为两组分2.704/2.595Å。803正常优化收敛、806零虚频最低95.30，但rev63 candidate_only因优化日志/频率来源/日志几何不匹配，不能算验证通过。实际两xyz均五元环，身份未见错，几何一致性问题原因未定；按verdict提示通过ts_resume `tc_925ad591186b4cbe`明确绑定798自身IRC_F/IRC_B为声明物种端点seed，保留780/794/798，重交reactant_opt813（inputrev7）后自动Opt/Freq两端链。不改方法/预算，不用独立极小值替代IRC。strict尚未执行/通过，仍无可回填正向垒。
**终态事件恢复后最新状态（覆盖历史阻塞判断）**：ts_inspect `tc_defd1d8aa0474aba` 已显示E1 ts_0005的正式frequency job794 running，说明780后继频率已自动提交，现不再是“无法提交Freq”。等待真实频率结果核目标模式，再双向IRC/外帧OptFreq/ts_guess strict验收；无垒可报。E2 `tc_b5a545d813f7408c` rev21已正确blocked，failed_attempt记录789 nonconvergence与原生日志SHA23ce2e54a55dec682ca173b2cebe7c775edc43e833c0f69f8c5233af8ff84437，失败结果未消化障碍已解除，但科学不收敛仍成立；依最新指令不新增E2搜索。
**用户要求IRC与ts_guess严格验收后的本轮复核**：重新读取当前ts_resume/ts_guess合同；ts_inspect `tc_5e905e2abde34e0e`仍rev45 waiting/refine，780 state=done但message仍等待终态，required_inputs/editable_groups=[]。已核verification声明完整正确：GFN2-XTB/basis空、TSopt/IRC/两侧外端optimization均auto，TS/外端frequency均numeric；没有真正缺失或错误可合法修复。Freq/IRC actual均null，公开工具无独立advance/正式frequency提交动作，故本轮未提交新作业，不以无关修订唤醒。需工程消化780终态并派发NumFreq；之后目标模式→双向IRC→IRC自身外帧Opt/Freq→ts_guess(mode=verify,strict=true)通过才回填正向垒。目前freq_log/irc_log不存在，未伪造严格验收参数/返回、不将780当频率日志传入。气相q0m1/方法/预算/状态不变，E2不新增搜索，不无限空等；本轮具体阻塞已发协调者。
**本轮最终收口（覆盖全部等待措辞）**：789已终态失败，不再等待或新增搜索。[789原生日志](ts/ts_0009/jobs/declaration_0003/ts_opt/.cloudra/calc-789.out.log)经log_parser亲核normal_termination=true但opt_converged=false（达最大步数），末能−15.114739751 Eh仅未收敛点，非TS能量/势垒。[最终原生结构](ts/ts_0009/jobs/declaration_0003/ts_opt/refine.xyz)测C2–N3=1.731、N4–C5=2.785、目标C2–C5=2.028、NN=1.143Å，无环，显示不对称反应区但不能证明分步机制。ts_inspect tc_63031b7abc624dc2仍rev18 waiting/refine、blocked/failed_attempt=null且editable空：失败结果未消化是独立工程缺口。E1 780正常且优化收敛但缺同几何频率/目标模式/双向IRC/零虚频正确外端；E2 782单调不闭环、789优化未收敛，无合格TS/Freq/IRC。两边均已真实尝试但未验证，不能宣称无垒、物理不可达或全题RDS。当前无后台计算，不修改原生日志/状态/预算，不手动补TS/Freq/IRC。
**唯一针对性跟进已提交789**：依据782真实帧显示CN-only不闭环，经协调授权同ts_0009使用已核candidate0两端15-image IDPP，非重复CN扫描/工程唤醒。durable接受input revision3并提交[OptTS789输入]( ts/ts_0009/jobs/declaration_0003/ts_opt/refine.inp )；工具生成provided.xyz测两CN2.302/2.446、目标CC2.152Å（原起点CC2.385Å），明确同时脱氮/收环且允许不对称，不是最低点或已验TS。GFN2-XTB/q0m1/4核4GB不变，无增预算、无新run。等待789真实终态/自动推进，780公共缺频率仍保留；下方“无运行作业”为789提交前的历史时点。
**最新终态覆盖提交状态**：778完成自动送OptTS780；[780日志](ts/ts_0005/jobs/declaration_0006/ts_opt/.cloudra/calc-780.out.log)正常/优化收敛E=−15.18111429073 Eh，[原生几何](ts/ts_0005/jobs/declaration_0006/ts_opt/refine.xyz)两反应距离2.375/2.262Å，尚无同几何频率/模式/IRC。ts_0005 rev45 waiting/refine、Freq actual=null且required/editable空，为公共推进第5复现，不手补频率或IRC。[782扫描](ts/ts_0009/jobs/declaration_0002/scan/.cloudra/calc-782.out.log)24点单调无内部峰，真实[末帧](ts/ts_0009/jobs/declaration_0002/scan/scan.024.xyz)两CN3.300、NN1.101、CC2.561Å且无环；本次脱氮坐标未驱动成环，不能以边界点作TS或推反应不可能。下一辨别试验应耦合CC收缩/映射IDPP；ts_0009 rev11仍waiting/guess、evidence=null、editable空，需先消化终态结果。当前无运行作业、无合格边/能垒。
气相热解q0/m1，温压未知，无额外水/溶剂。RC map1–5对应文件行1,2,3,6,7；首步成1–7/3–6，降1–2/6–7键级。GFN2-xTB（ORCA6.1.1，xtb6.7.1）job732 RC −16.01软虚频，734吡唑啉零虚频，735产物复合物三软虚频；742/745/747/748分量零虚频，原日志见[calc](gold_compute/queue_20261018/results/IB9/calc/)。无合格TS边。durable [ts_0005](ts/ts_0005/process.json)候选2及中心已显式选择；path754达8次上限，无可用guess，不把峰作能垒。 后续双成键耦合扫描757也因优化未收敛失败（[原日志](ts/ts_0005/jobs/declaration_0004/scan/.cloudra/calc-757.out.log)），旧尝试未启动TS/IRC。本轮已实际恢复：734重新核优化收敛/零虚频，采用原生[pyr_opt.xyz](gold_compute/queue_20261018/results/IB9/calc/pyr_opt/pyr_opt.xyz)且坐标工具核五元环、无异常；同ts_0005逆向声明，candidate2断具体C1–C5/C2–N3，双距离1.541/1.452→3.5Å/20步，[扫描778输入](ts/ts_0005/jobs/declaration_0006/scan/scan.inp)已提交。另首次启动第二步[ts_0009](ts/ts_0009/process.json)，candidate0断C2–N3/N4–C5、成C2–C5及NN升阶，两CN1.452→3.3Å/24步、CC/NN自由松弛，[扫描782输入](ts/ts_0009/jobs/declaration_0002/scan/scan.inp)已提交。这是协同脱氮假说试验，不预断真实机制；两run均优化auto/频率numeric分离，不改预算、不手跑TS/IRC。尚无结果/合格能垒，必须核目标一虚频、双向IRC及零虚频身份正确外端；首步成功也不等于全题RDS。详见[报告](gold_compute/queue_20261018/results/IB9/REPORT.md)。PM7 ORCA被拒，但隔离MOPAC23.2.5已实算RHF单重态吡唑啉优化，见[原输出](gold_compute/queue_20261018/results/IB9/probe_pm7/IB9_pyr_pm7.out)；既有Opt及独立FORCE系历史Bash直调，无compute job ID，来源已在报告披露；FORCE全频率尚未审完，不以首频称全面零虚频。非scorer接受格式且durable无MOPAC引擎，不能冒充严格PM7边；不重复IA8唯一PySCF外接PM7验证。

### IA1 方形Hessian补试
由矩形Z矩阵通过internal_coordinates工具生成四边1.44Å/CH夹角135°的方形种子。[约束优化758](gold_compute/queue_20261018/results/IA1/.cloudra/calc-758.out.log)正常、约束优化收敛；另行移除全部约束做[完整NumFreq759](gold_compute/queue_20261018/results/IA1/.cloudra/calc-759.out.log)，正常且恰一虚频−4535.22 cm⁻¹、E=−10.4087086777 Eh。固定边长不证明自由驻点，parser未返回模式向量，故尚不认定TS或报势垒。已同durable ts_0002新种子恢复正式无约束OptTS job760；待结果及频率/IRC推进。MOPAC现已由IB9安装并成功PM7优化，之前PATH缺失为当时环境，不应解释为PM7永远不可用；durable/scorer兼容仍是独立缺口。

### IA1 PySCF新增（用户改向）
语义纠正：用户要在PySCF调用PM7，并未授权替换Hamiltonian。协调分派期间已提交的job767为CASSCF(4,4)/cc-pVDZ单点遗留，非PM7且不作为当前任务目标证据；不再新增此方法计算。以下仅记录已提交来源：[脚本](gold_compute/queue_20261018/results/IA1/pyscf/casscf_sp.py)将现有气相xTB矩形/约束方形作SP与解析梯度，按环面法向碳pz投影选择2占据+2虚轨道，输出活性轨道权重、自然占据、<S²>及收敛。job767已公开shell提交4核/4096MB，等待结果，不将SP差作能垒。env核PySCF2.14.0/Python3.11，缺geometric/berny和CASSCF解析Hessian；正式TS/IRC无PySCF durable后端，不能shell绕过。xTB job760已done而ts_inspect仍waiting/refine（频率未启动），为推进缺口不认验收。

### 最新接口/提交审计（纠正待运行措辞）
用户所指为PySCF里调用PM7，不授权CASSCF替换。env核当前PySCF2.14.0无已装PM7/semiempirical/mopac接口；ASE/MOPAC是另一真实接口，不能称PySCF PM7。异步shell提交虽返回准入，但query证实PM7普通Opt job764与改向误解期间CASSCF脚本job767均failed、attempt_count=0、last_error为 Unsupported job_type: shell，故二者均未实际计算，不存在可报告能量；不绕过Bash执行。协调者后续核IA9同步shell普通PM7确有原生输出，故故障结论仅限本题异步通道，不能一概声称shell不可；待指定单题同步PySCF外接PM7验证，不重复批量提交。输入run_rect_pm7.sh、rect_pm7.mop与pyscf/casscf_sp.py只作提交审计，后者非当前目标证据。xTB正式job760已done，但ts_0002仍waiting/refine、频率未启动；当前无运行作业，无合格边。

### IA1 最终候选审计
最新只读ts_inspect `tc_19fe716fe9fd466a`：ts_0002 waiting/refine，next=wait_for_system，required_inputs/editable_groups均空，blocked=null。原生[正式OptTS760](ts/ts_0002/jobs/declaration_0007/ts_opt/.cloudra/calc-760.out.log)经log_parser `tc_4bb238dd377f4229`确认正常终止、优化收敛，E=−10.408998801830 Eh；但没有后继频率或IRC，故只为收敛驻点候选，不是已验一阶TS。先前方形759的一虚频不能转移到760不同几何，且其模式向量parser未返回。必要的端点optimization auto/frequency numeric分离修复已尝试一次ts_resume，工具内部失败且未提供backend call_id；未重复干预/改预算，不把修复当已解锁。原始日志不改写，未改变registry/accessibility。当前没有合格ΔE‡/ΔErxn、无运行作业；需工程修复durable推进后核同几何目标虚频、双向IRC与身份一致的零虚频两端。


## IB10 — 逐步Wolff（owner）
气相热解q0/m1，温度/压强未指定，无外加水酸碱或对离子；孤立GFN2-xTB闭壳PES不证明最低自旋纯单重态。假说为先N2脱离，再题设H6由C4到C3，不能拿协同旁路替代。RC [773](gold_compute/queue_20261018/results/IB10/R/.cloudra/calc-773.out.log)正常收敛零虚频E=-15.118382145640 Eh。独立卡宾种子 [775](gold_compute/queue_20261018/results/IB10/carbene/.cloudra/calc-775.out.log)正常收敛零虚频，但internal_coordinates核真实输出C1同时连H4/H5且C1=C2=O3：实际成乙烯酮，**不是已核卡宾极小值**。这一次塌陷不证明卡宾不存在。
E1 durable [ts_0007](ts/ts_0007/process.json) path779达20轮上限无可用TS猜测；E2 [ts_0008](ts/ts_0008/process.json)已补真实结构中心4–7断/3–7成/3–4升阶（H7对应题设H6），path781达20轮上限失败；后续E2耦合扫描784达到优化上限未收敛（[原日志](ts/ts_0008/jobs/declaration_0003/scan/.cloudra/calc-784.out.log)）。E1扫描783有两峰，实际核第9峰O–N旁路成键不选；第4峰C–N1.648Å/N–N1.114Å且醛H仍原位，已通过ts_resume tc_3b019b053295484e送正式OptTS785（[输入](ts/ts_0007/jobs/declaration_0003/ts_opt/refine.inp)），785原生正常且优化收敛E=-15.10714640019Eh；refine.xyz核C–N回缩1.289Å/N–N1.136Å，醛H仍原位，只有未定指数驻点候选。ts_inspect tc_89c54b75a04b4f4f为waiting/refine，next=wait_for_system且无required_inputs/editable_groups，Freq未启动，共同工程阻塞；不据done认TS。合法另目录修复普通产物：ketene786、N2 787、完整复合物788已提交Opt/NumFreq，等待终态通知。多组分卡宾普通writer被unsupported_spin拒绝仅属结构装配能力；P774/777为原生输入解析失败，旧证据完整保留，尚无P优化。日志导出xyz工具失败，已改用原生opt.xyz核身份。没有任何可报势垒；下一步依据路径与坐标重新选有物理依据扫描，正式TS/IRC仍只durable。


IB10最新收口：786 ketene正常/收敛/零虚频E=-9.318187047870Eh；787 N2输入解析失败、788完整P fatal single-point失败，均非极小证据。785未推进Freq的共同工程阻塞仍在；E2指定H6路径/扫描失败，未找到经验证卡宾极小但不证明不存在。无新势垒/Gold，当前无后台。具体call_id、输入/原日志与各边缺口见[IB10报告](gold_compute/queue_20261018/results/IB10/REPORT.md)收口审计。

IB10组件补核：IB9 [N2 job748](gold_compute/queue_20261018/results/IB9/calc/frag_n2/.cloudra/calc-748.out.log)与ketene786同ORCA6.1.1/GFN2-xTB6.7.1、气相q0/m1、Opt/NumFreq；正常收敛零虚频，可复用分离N2组件。787解析失败不代表N2不可算；复用不等于完整P/IRC验证，不新增垒或Gold。

### IA1 强制继续轮：实际recovery证据
本轮读取现行合同后，inspect tc_4b0c78964fd842e9显示两端optimization实际planned已auto（修订曾内部失败不能简单视为未提交），但IRC仍numeric。仅针对非Freq的IRC独立改auto一次ts_resume，完整返回内部执行失败且无backend call_id暴露。后inspect tc_4aa77b495b0d4a06证实IRC planned已auto、TS/端点频率仍numeric，然而仍waiting/refine,next wait_for_system,required_inputs/editable_groups=[]，frequency/IRC actual=null。没有同几何NumFreq或双向IRC被提交，不能假做ts_guess严格通过。参数、完整inspect、原始错误和缺失验证链已保存[recovery_round_latest.json](gold_compute/queue_20261018/results/IA1/recovery_round_latest.json)。这是本轮真实推进尝试/工具阻塞，不是化学失败；不新run绕过、不手动TS/IRC、不改状态预算，等待实际durable恢复能力。


### IB10推进后修订（当前）
先前waiting工程阻塞后来由系统推进：795恰一虚频−247.87，802双向各20点，808优化及810零虚频完成；但实际IRC后向成O–N五元环（1.640Å），808进一步O–N1.369Å且C–N仍1.355Å，**不是目标脱N2连接**。因此不以独立RC seed替换掩盖错连接、不宣告E1。ts_0007现ended/candidate_only，另报端点频率几何一致性失败；诊断与错物种分列。见[最新报告续审](gold_compute/queue_20261018/results/IB10/REPORT.md)、[IRC原日志](ts/ts_0007/jobs/declaration_0003/irc/.cloudra/calc-802.out.log)、[808原生几何](ts/ts_0007/jobs/declaration_0003/reactant_opt/reactant_opt.xyz)。E2不变，无目标垒，当前无后台、不新增旁路计算。

### IA1 IRC实际推进及物种方向修复
旧no-submit已失效：原生793为760同几何NumFreq，一虚频−4610.8；797双向IRC各11点收敛。internal_coordinates核797原生B端C12/C34=1.327Å、C23/C14=1.551Å符合R，F端相反符合P；各附H和环保持。默认A作为R后的801/805收敛零虚频但几何一致性validator拒绝；显式801最终xyz重试811/812仍拒绝，且实际属P，不能凭同SMILES算R。现依据真实映射方向以B/F分别明确R/P seed，ts_resume tc_d92b43f2a4184978提交817 R Opt（同run、保留760/793/797），等待后续真实通知；不再重复不具物理理由的opt。模式parser null且缺严格ts_guess证明，目前仍不填能垒。
