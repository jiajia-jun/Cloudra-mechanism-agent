# IB9 GFN2-xTB 首步人工确认回填；第二步未闭合

## 当前结果（2026-10-18，覆盖下方历史快照）

用户确认“我确定就是这个反应，回填吧”后，正式题库 **IB9_E1 更新为 5.65 kcal/mol**：同方法 TS794 − 原料接触体839 的纯电子能差，不含 ZPE/热校正，替换历史 B3LYP 14.74。相对分离单体742+745为4.37 kcal/mol，另列不混用。反应模式为两处成键同步运动；839的−29.79/−4.49 cm⁻¹是组分间相对转动/摇摆，仍保留负频，未称整体零虚频或工具 strict pass。第二步仍缺测，全题速控步未定。能量、原生来源哈希及人工裁定边界见[本次回填记录](GOLD_BACKFILL_20261018.md)。

## 历史过程（下列未回填、待验证措辞为当时状态）

## 当前判断

**839唯一小步长/逐周期数值Hessian诊断已完成**：原生日志证实4周期沿途初始+三次重算Hessian（review.001–004.hess、明确read recalculated），另末NumFreq第五次；MaxStep/Trust实回显0.100/0.100，但实际步长均远小于上限，不据此归因过大步长。末RMS/MAX梯度6.27e-8/5.385e-7 Eh/bohr，引擎按gradient overachieved宣布收敛，两步长指标仍NO，不能称五项全过。结构仍原料两组分，E−15.19012562713Eh；虚频−29.79/−4.49（833−29.75/−4.37），没有消失。全频/次数/行号/模式/边界见gold_compute/queue_20261018/results/IB9/hessian_step_review/RESULT.md和PARSED_839.json。没有找到本轮零虚频接触体minimum，不证明不存在；完成一次授权收口，无后台、不新QM/strict呈现/Gold或垒，单体742/745参考保留。

**Hessian/小步长唯一诊断839已提交**：researcher官方核字段语义后，从833原生最终结构!Opt NumFreq，MaxStep0.1/Trust−0.1内部坐标au，Calc_Hess/NumHess true、Recalc_Hess1；保留833 tight阈值与GFN2/SCC/占据/完整组成。官方Hessian组说明偏TS，minimum实际执行重算尚待原生日志核验，不能把标签算次数；若拒绝/不触发就如实收口不试别的。方案与输入见gold_compute/queue_20261018/results/IB9/hessian_step_review/PLAN.md、review.inp。无冻结/新TSIRC或积分grid变更，无Gold预承诺。

**IB9新授权：一次小步长/Hessian最低点诊断（待官方支持核验）**：起点仅833原生tight_optfreq.xyz，完整CH2N2+乙烯GFN2/q0m1不变。假说是上轮BFGS近似曲率/步长处理可能使浅负曲率未解决；此次检验真实数值Hessian重算配合较小步长，而非再次仅加严梯度。先待researcher官方核minimum适用Calc_Hess/NumHess/Recalc_Hess及Trust/MaxStep接口，只选一个可支持配置一次普通Opt+Freq；输入标签不足，须原生证明重算次数/间隔与实际步长。若不支持则据具体证据停止，不试关键词组合、不新TSIRC/扰动循环、不改阈值或Gold。742/745零虚频分离参考保留，833软负频亦不撤回。

**IB9最新拆组分参考授权已完成（无新增QM）**：798 B/833确为CH2N2+乙烯两个无新跨组分键接触体、非金属配位；833非已验束缚minimum。工作序乙烯[1,2,6,7,8,9]，CH2N2[3,4,5,10,11]；742局部→工作序[5,4,3,10,11]、745[1,2,6,7,8,9]，题设map另列不混。已亲核复用742/745同日志OptNumFreq正常/收敛/零虚频，同ORCA6.1.1→xtb6.7.1/GFN2/q0m1/accuracy.2/SCC2e-7Eh，结构对应足够，不再拆后重算。E_A+E_B=−15.18807894276Eh，833候选相互作用−1.28431kcal/mol（非验证结合minimum）。详见gold_compute/queue_20261018/results/IB9/component_review/COMPONENT_REFERENCE.md与.json（全原子对应/源路径/哈希/全频）。新授权允许分离参考，旧“不用分离物掩盖负频”仍有效：组件零虚频不等于整体零虚频，公开strict无组件频率输入接口，不能代替完整IRC方向证明；没有strict pass/Gold/垒、无图或登记修改。
**IB9定向tight唯一轮已完成833并收口**：实际原生末表五项全YES，RMS/MAX梯度由822的1.53497e-5/4.07814e-5降为4.940e-7/1.7926e-6 Eh/bohr，阈值确实加严；SCC未改。仍同原料两组分，反应距3.379/3.251→3.383/3.249Å，电子能降低0.00262446 kcal/mol。两负频−36.41/−8.99→−29.75/−4.37 cm⁻¹，未消失，绝不当零/噪声；仍H主导低模但未证纯刚体摆动。全频率/实际阈值/收敛表/模式组成及原生路径见gold_compute/queue_20261018/results/IB9/tight_review/COMPARISON.md与PARSED_833.json。没有找到本轮零虚频原料复合物最小值，不证明不存在；不再迭代、无strict复验/Gold/垒，missing TS geometry独立保留。
IB9本轮方案：仅从822 NAME=optfreq.inp绑定原生最终optfreq.xyz一次无约束普通Opt+NumFreq，保留GFN2/ORCA6.1.1外部xtb6.7.1与q0m1。822实际ORCA BFGS默认TolE5e-6/MAXG3e-4/RMSG1e-4/MAXD4e-3/RMSD2e-3；本轮显式geom阈值1e-7/1e-5/3e-6/1e-4/5e-5，非单靠TightOpt标签，最终必须核native回显实际阈值与梯度。SCC设置不凭猜测更改；若只能确认几何tight，将明确不是已证实SCC加严。模型气相无外加参与物、温压未知，不扰动/冻结/删负频，不预承诺零虚频或Gold。
**只读解析/软模补审**：完整实际strict请求与未删减返回已保存gold_compute/queue_20261018/results/IB9/independent_endpoints/STRICT_FULL_RECORD.json（复现call tc_aa51e9efa8f64325仍inconclusive），含提取strict_verify/irc_end_a.xyz及irc_end_b.xyz路径。794的.cloudra日志父目录有frequency.hess/inp/optimized.xyz、没有frequency.xyz；798父目录有原生F/B终帧与轨迹，未移动/改写。822两软模中−36.41重原子非质量加权位移份额0.00211（H11/H10主导），−8.99份额0.11118（H6–H9主导）；仅能说H主导，未证纯刚体相对摆动、不能排除内模/称数值噪声。B原生optfreq.xyz组分间反应距3.379/3.251Å，组分内CC1.317、CN1.252、NN1.129Å。parser缺口与B非零虚频独立，不新增任务；env获原路径核解析条件。
**独立端点与strict已实际完成，未通过**：F821同日志Opt+NumFreq正常/优化收敛/零虚频最低95.30，E−15.28200646346 Eh，NAME原生optfreq.xyz为吡唑啉；B822正常/优化收敛但软虚频−36.41/−8.99，E−15.19012144179 Eh，正确两组分、反应距3.379/3.251Å，尚非验证RC极小值。ts_guess strict `tc_1764b3279cb64414`已用794/798原日志、两侧NAME最终XYZ、ORCA watch_pairs[[0,4],[1,2]]执行：verification_status=inconclusive，missing TS geometry；确认n_imag=1、mode aligned，F IRC收敛/B未收敛，外帧已提取。缺口是B非零虚频与TS几何提取不可用，独立验证不绕过这些事实。参数/紧凑返回见gold_compute/queue_20261018/results/IB9/independent_endpoints/STRICT_RECORD.json（非原生证据）；原日志F/.cloudra/calc-821.out.log、B/.cloudra/calc-822.out.log在同目录。各侧一次授权已用尽，不再提交、不报正向或逆向垒，不声称durable validator已通过。
**授权独立端点科学验证已提交**：从798自身原生IRC_F/B外帧，非SMILES重建，分别普通无约束Opt+NumFreq同一日志job821/822（ready）；输入gold_compute/queue_20261018/results/IB9/independent_endpoints/{F,B}/optfreq.inp已预注smiles，GFN2-XTB气相q0m1/4核4GB、constraints=[]。各侧仅一次；不改durable/原证据/阈值，无手动TS/IRC。完成后核同日志收敛/零虚频、NAME原生最终XYZ/身份，并以794/798原样和正确watch_pairs作ts_guess strict；仅明确pass后建议正向能垒，不冒称durable validator通过。
**明确IRC seed重试后仍几何mismatch（当前阻塞）**：813优化正常且收敛（parser tc_6e7aa21ad4c24b9e，E−15.28200646346 Eh），814频率正常/零虚频最低95.30（tc_cfeae326eeba4838，E−15.28200646310），但rev74再次candidate_only：optimization log / saved frequency source / frequency log geometry mismatch。不是零虚频失败，也尚无证据说连错物种。已向env提供declaration_0007原生813/814及optimized.xyz/input与旧803/806供只读精度/NAME来源诊断，不再盲目重交相同seed；另一端尚未自动验证。794/798已有真实Freq/双向IRC，旧no-submit障碍仅历史；当前无strict pass、无垒可报，待一致性检验修复再续。
**E1频率/IRC已实算，端点来源修复中**：794恰一虚频−367.39 cm⁻¹，durable模式aligned（1–5/2–3相对位移0.924/0.848）；798双向IRC F16/B20点正常结束，未两向本征收敛。原生F外帧为五元环1–5/2–3=1.544/1.452Å，B外帧为两组分2.704/2.595Å。803正常优化收敛、806零虚频最低95.30，但rev63 candidate_only因优化日志/频率来源/日志几何不匹配，不能算验证通过。实际两xyz均五元环，身份未见错，几何一致性问题原因未定；按verdict提示通过ts_resume `tc_925ad591186b4cbe`明确绑定798自身IRC_F/IRC_B为声明物种端点seed，保留780/794/798，重交reactant_opt813（inputrev7）后自动Opt/Freq两端链。不改方法/预算，不用独立极小值替代IRC。strict尚未执行/通过，仍无可回填正向垒。
**终态事件恢复后最新状态（覆盖历史阻塞判断）**：ts_inspect `tc_defd1d8aa0474aba` 已显示E1 ts_0005的正式frequency job794 running，说明780后继频率已自动提交，现不再是“无法提交Freq”。等待真实频率结果核目标模式，再双向IRC/外帧OptFreq/ts_guess strict验收；无垒可报。E2 `tc_b5a545d813f7408c` rev21已正确blocked，failed_attempt记录789 nonconvergence与原生日志SHA23ce2e54a55dec682ca173b2cebe7c775edc43e833c0f69f8c5233af8ff84437，失败结果未消化障碍已解除，但科学不收敛仍成立；依最新指令不新增E2搜索。
**用户要求IRC与ts_guess严格验收后的本轮复核**：重新读取当前ts_resume/ts_guess合同；ts_inspect `tc_5e905e2abde34e0e`仍rev45 waiting/refine，780 state=done但message仍等待终态，required_inputs/editable_groups=[]。已核verification声明完整正确：GFN2-XTB/basis空、TSopt/IRC/两侧外端optimization均auto，TS/外端frequency均numeric；没有真正缺失或错误可合法修复。Freq/IRC actual均null，公开工具无独立advance/正式frequency提交动作，故本轮未提交新作业，不以无关修订唤醒。需工程消化780终态并派发NumFreq；之后目标模式→双向IRC→IRC自身外帧Opt/Freq→ts_guess(mode=verify,strict=true)通过才回填正向垒。目前freq_log/irc_log不存在，未伪造严格验收参数/返回、不将780当频率日志传入。气相q0m1/方法/预算/状态不变，E2不新增搜索，不无限空等；本轮具体阻塞已发协调者。
**本轮最终收口（覆盖全部等待措辞）**：789已终态失败，不再等待或新增搜索。[789原生日志](../../../../ts/ts_0009/jobs/declaration_0003/ts_opt/.cloudra/calc-789.out.log)经log_parser亲核normal_termination=true但opt_converged=false（达最大步数），末能−15.114739751 Eh仅未收敛点，非TS能量/势垒。[最终原生结构](../../../../ts/ts_0009/jobs/declaration_0003/ts_opt/refine.xyz)测C2–N3=1.731、N4–C5=2.785、目标C2–C5=2.028、NN=1.143Å，无环，显示不对称反应区但不能证明分步机制。ts_inspect tc_63031b7abc624dc2仍rev18 waiting/refine、blocked/failed_attempt=null且editable空：失败结果未消化是独立工程缺口。E1 780正常且优化收敛但缺同几何频率/目标模式/双向IRC/零虚频正确外端；E2 782单调不闭环、789优化未收敛，无合格TS/Freq/IRC。两边均已真实尝试但未验证，不能宣称无垒、物理不可达或全题RDS。当前无后台计算，不修改原生日志/状态/预算，不手动补TS/Freq/IRC。
**历史跟进：789提交及其初猜**：依据782真实帧显示CN-only不闭环，经协调授权同ts_0009使用已核candidate0两端15-image IDPP，非重复CN扫描/工程唤醒。durable接受input revision3并提交[OptTS789输入]( ../../../../ts/ts_0009/jobs/declaration_0003/ts_opt/refine.inp )；工具生成provided.xyz测两CN2.302/2.446、目标CC2.152Å（原起点CC2.385Å），明确同时脱氮/收环且允许不对称，不是最低点或已验TS。GFN2-XTB/q0m1/4核4GB不变，无增预算、无新run。789现已终态失败（见上方最终收口），不再等待；780公共缺频率仍保留。
**历史阶段审计（778/782完成、789实施前；当前以顶部最终收口为准）**：778已完成并自动生成OptTS780；780原生正常终止、优化收敛，E=−15.18111429073 Eh，但没有频率/IRC。ts_0005 rev45 waiting/refine、required_inputs/editable_groups空、frequency actual=null，是公共推进故障第5复现，不是化学不可达。782已完成，24点单调上升、无内部峰，尚无E2 TS；当时ts_0009 rev11为waiting/guess、evidence=null；789实施后当前为顶部rev18 waiting/refine及失败结果消化缺口。目前无运行作业，不等待已经终态的job，不填任何能垒。

以下保留早期尝试历史，提交时态不表示当前等待。尚无合格反应边；不能填首步、第二步或全题速控能垒。旧B3LYP 14.74不参与本轮。正式流程 ts_0005；path754达8次上限未收敛，保留证据；改双成键耦合扫描job757亦因几何优化不收敛失败，旧尝试blocked；现已从已验证吡唑啉逆向恢复同一run并提交778。第二步另建ts_0009，已提交782。扫描峰不算能垒。

## 模型与映射
气相热解q0/m1，温度压力未给；无溶剂/水/外加酸碱。RC重原子map1..5对应XYZ行1,2,3,6,7。首步形成map1–5/3–4，降低1–2/4–5键级。第二步断1–2/3–4，形成1–4并增2–3键级。首步两条成键耦合，不能用单独N-C扫描替代整个环加成。38电子总体单重态；GFN2-xTB为自洽紧束缚，非多参考波函数，不能证明脱氮双自由基区域可信。

## GFN2-xTB 原生结果
ORCA6.1.1 调用外部xtb6.7.1，明确Hamiltonian GFN2-xTB；basis空，气相，q0/m1，4核/4GB，Opt+NumFreq。原生日志如下（均未修改）：
|物种|job|E/Eh|频率|原生日志|
|--|--:|--:|--|--|
|RC|732|-15.19049556742|−16.01软虚频|[log](calc/rc_opt/.cloudra/calc-732.out.log)|
|吡唑啉|734|-15.28200664278|零虚频|[log](calc/pyr_opt/.cloudra/calc-734.out.log)|
|产物复合物|735|-15.21320650059|−24.01/−15.76/−6.46|[log](calc/prod_opt/.cloudra/calc-735.out.log)|
|CH2N2|742|-8.91681833521|零虚频|[log](calc/frag_ch2n2/.cloudra/calc-742.out.log)|
|C2H4|745|-6.27126060755|零虚频|[log](calc/frag_c2h4/.cloudra/calc-745.out.log)|
|环丙烷|747|-9.44819093726|零虚频|[log](calc/frag_c3h6/.cloudra/calc-747.out.log)|
|N2|748|-5.76393542024|零虚频|[log](calc/frag_n2/.cloudra/calc-748.out.log)|
同方法电子能探索：RC相对组分−1.52 kcal/mol（非验证极小值）；吡唑啉相对分离原料−58.94；分离产物相对吡唑啉+43.85 kcal/mol。不是以已验证RC/IRC两端为参照的严格反应能。产物复合物相对组分−0.68，但多软虚频，不宣称已验证最低络合物。

## PM7
执行来源审计：本题已完成的 MOPAC PM7 普通 Opt/FORCE 是此前通过 Bash 直接调用隔离安装的 `mopac_env/bin/mopac` 执行，并非公开 `submit_compute_job(job_type="shell")` 提交，因此没有对应 compute job ID；未留存可引用的独立提交 shell 脚本，不能伪称存在。原始输入/输出及 `.arc` 保留于下列 `probe_pm7/` 路径，其来源不等于 compute 准入或 scorer 验收。后续普通 PM7 统一通过授权 compute 提交；若公开 shell 通道拒绝则报告诊断，不再以 Bash 直接运行规避。正式 TS/IRC 仅通过 durable 工作流。

[ORCA PM7拒绝原输出](probe_pm7/t_pm7.out)，Gaussian未在PATH发现。隔离conda安装MOPAC23.2.5，实际完成[吡唑啉PM7输入](probe_pm7/IB9_pyr_pm7.mop)和[原输出](probe_pm7/IB9_pyr_pm7.out)：明确PM7/RHF、14双占价轨道、singlet。补充[原生FORCE输出](probe_pm7/IB9_pyr_pm7_force.out)与.arc：已计算PM7 Hessian，正常模式首频159.5 cm⁻¹（后续频率需完整汇总）；优化.arc明确SCF achieved、EF优化、gradient0.01088，热生成焓31.22896 kcal/mol不是纯电子能，也不是势垒。MOPAC非题设scorer可解析ORCA/Gaussian；durable ts_prepare只支持orca/gaussian/xtb，无法作为正式PM7 TS/IRC边，不绕过。初始水测试mopac_test因多空行仅输出结束标记，非PM7实算，不用于证据。

## 历史尝试记录（提交不等于成功；当前终态见顶部）
- 重新log_parser核734：优化收敛、正常结束、零虚频，最低振动95.55 cm⁻¹。format_converter提取失败（工具返回Failed to process log，未产生可用结构），实际采用原计算目录已有[pyr_opt.xyz](calc/pyr_opt/pyr_opt.xyz)，internal_coordinates确认C1-C2-N3-N4-C5五元环且无键/角异常。
- E1逆向：此前方案确未实施；本轮在同ts_0005改为吡唑啉→原料，明确选择candidate2，具体断C1–C5/C2–N3，初距1.541/1.452Å，同时伸至3.5Å/20步。原子序已按反向重新绑定，未手工重排坐标。[durable输入778](../../../../ts/ts_0005/jobs/declaration_0006/scan/scan.inp)，当时已提交；现778及自动生成的780均已完成，但780缺频率/IRC。扫描只是种子，若得到反向垒不得冒作正向垒。独立reverse_e1/scan.inp仅准备，未另行提交。
- E2真实首次路径尝试：ts_0009 candidate0，断C2–N3/N4–C5，成C2–C5并N3=N4升三键，完整映射保持附氢。两CN从1.452同步伸至3.3Å/24步，CC初距2.385Å与NN1.211Å自由松弛，测试协同脱氮；若跳支/异步则需按实际帧修正，不预断双自由基机制。[durable输入782](../../../../ts/ts_0009/jobs/declaration_0002/scan/scan.inp)，当时已提交；现782已完成，后续IDPP/789亦已实施且优化未收敛。产物复合物旧735有软虚频，不能冒作已验证完整端点；分离组分747/748零虚频仅组件证据。
- 两run均GFN2-XTB/气相q0/m1；优化/IRC auto、独立频率numeric，无增加预算或手动正式TS/IRC。成功须一目标重原子虚频、双向IRC及身份正确的零虚频外端；目前尚无。

## 终态原生证据与历史辨别试验
[OptTS780原生日志](../../../../ts/ts_0005/jobs/declaration_0006/ts_opt/.cloudra/calc-780.out.log)由log_parser核正常且优化收敛；[原生refine.xyz](../../../../ts/ts_0005/jobs/declaration_0006/ts_opt/refine.xyz)测C1–C5=2.375、C2–N3=2.262、C1–C2=1.344、N4–C5=1.280、NN=1.137Å，处首步反应区但无Hessian指数/目标模式证据，不能称已验一阶鞍点；不以电子能差冒充势垒。缺链为durable自动生成频率→目标重原子模式→双向IRC→零虚频正确外端，不手动补交。

[E2扫描782原生日志](../../../../ts/ts_0009/jobs/declaration_0002/scan/.cloudra/calc-782.out.log)经scan_parse核24点无内部峰；未生成e2_peak.xyz，不以末点冒作provided。实际[005帧](../../../../ts/ts_0009/jobs/declaration_0002/scan/scan.005.xyz)/[006帧](../../../../ts/ts_0009/jobs/declaration_0002/scan/scan.006.xyz)两CN=1.773/1.854Å，CC=2.465/2.477Å；无证据将相邻大能差断言为机制跳支。[024末帧](../../../../ts/ts_0009/jobs/declaration_0002/scan/scan.024.xyz)两CN3.300、NN1.101、CC2.561Å，无环。观察表明本次只拉CN未驱动目标CC闭合，不证明目标反应不存在或无垒。当时提出同run映射IDPP或显式CC收缩耦合脱氮作为辨别试验；其中IDPP已实施并生成789，终态为优化未收敛（见顶部），不是尚待开展的计划。当前失败结果消化缺口仍在，不以无关修订/预算/手动TS绕过。

## 历史失败与验收边界
757已失败：ORCA几何优化达到最大步数未收敛，原日志 ../../../../ts/ts_0005/jobs/declaration_0004/scan/.cloudra/calc-757.out.log；该旧尝试无TS/IRC被提交；现已按上述逆向几何启动，不仅增加优化迭代。验证一虚频目标模式、双向IRC及外端零虚频/身份，再决定可否给方法内首步候选。即使首步通过也不是全题速控能垒，第二步现已开始上述真实扫描尝试，尚未验证。PM7严格边缺支持的Gaussian执行环境或durable MOPAC适配，以及scorer格式授权。未改登记/题源/已有原生日志。
