# IA8 PM7 / GFN2-xTB 实算探索

## 判断
尚不能产出严格验收的反应边：没有完成目标反应模式的一虚频及双向 IRC/外端极小值验证。不回填正式 registry，不提供能垒。当前是可审计预备候选，不是物理不可达结论。

## 映射与模型
CH2OO C=[O+][O-] → C1OO1；C1、近端O2、末端O3、H4/H5。C1=O2 降阶（break [1,2]），C1–O3 成键（form [1,3]），O2–O3 保留。产品两O对称；durable mapping candidate 0 保持具体原子顺序。孤立气相、q0/m1、闭壳单重态；没有水/酸碱/对离子，温度未指定；xTB部分仅讨论电子PES，PM7部分采用下文参数化Hf/模型势能限定。尚未检验开壳单重态或多参考特征。

## 原生计算（均未修改日志）
程序 ORCA 6.1.1 RELEASE，方法 GFN2-xTB，无显式轨道基组、无溶剂；优化及数值频率，2 CPU/2GB。日志标识 GFN2-xTB。外部路径引擎 xtb 6.7.1 (edcfbbe)，仅用于猜测。

|job|输入|原生日志|结论|
|---|---|---|---|
|721|explore/scan_CO.inp|explore/.cloudra/calc-721.out.log|C1–O3 约束扫描；剧烈跳变，非势垒|
|722|explore/pm7_probe.inp|explore/.cloudra/calc-722.out.log|ORCA 拒绝 PM7 关键字，退出码4|
|729|explore/opt_CH2OO.inp|explore/.cloudra/calc-729.out.log|优化收敛、正常结束、零虚频，E=-11.128183799630 Eh|
|730|explore/opt_dioxirane.inp|explore/.cloudra/calc-730.out.log|优化收敛、正常结束、零虚频，E=-11.177883683330 Eh|

独立两端方法内异构化电子能：(-11.177883683330 + 11.128183799630) × 627.509474 = **-31.18715 kcal/mol**。这是独立优化端点能差，未取得 IRC 关联验证，不是严格反应边的验收值。最低正频率 R=503.63、P=1020.54 cm^-1。

## durable 路径
项目根 ts/ts_0001/process.json。路径733经100轮仍不收敛，保留在 ts/ts_0001/jobs/declaration_0002/path/xtb_path_runs/queued_path_0001。随后同 run IDPP 插值并由 durable 提交 OptTS 739：ts/ts_0001/jobs/declaration_0003/ts_opt/refine.inp；原生日志 ts/ts_0001/jobs/declaration_0003/ts_opt/.cloudra/calc-739.out.log。优化收敛、正常结束，E=-11.083861872140 Eh，但无频率，不能称已验证TS、更不能作能垒。
协调复核后尝试将引用的 calculations.xtb2freq 增加 TightSCF（数值 Hessian 的 SCC 收敛要求），ts_resume 返回内部异常且未提供 call_id；随后 ts_inspect（tc_e93ecf16487f4912）仍为同样等待状态，未提交频率。
当前工具卡在 waiting/refine：739已done、frequency目录空、队列空，ts_resume(changes={}) 返回 no input change or failed attempt to retry。没有手动绕过。需修复自动推进后继续 NumFreq、模式检查、双向IRC及外端Opt/Freq。

## PM7 / PySCF 接口与提交边界
MOPAC 23.2.5 已安装；普通端点脚本 [run_opt.sh](gold_compute/queue_20261018/results/IA8/pm7/run_opt.sh) 曾经公开 submit_compute_job(job_type=shell) 接受为 job763，但最新终态为 failed，attempt_count=0，last_error="Unsupported job_type: shell"，无分子输出。这是提交后端拒绝，不是PM7科学失败；未转Bash绕过。用户要求在PySCF调用PM7，未授权CASSCF/HF/DFT替代；IA8未提交任何该类作业。env核已装PySCF无原生PM7模块，但已真实打通PySCF通用scanner→ASE/MOPAC PM7（见下文job768）；这是外接调用，不是PySCF原生PM7 Hamiltonian。xTB durable仍缺频率/IRC。


### PySCF 外接 PM7 最小实测（job768）
已实际打通 **PySCF 2.14.0 通用 as_pyscf_method scanner → 自定义回调 → ASE 3.29.0 → MOPAC 23.2.5 PM7**，不是PySCF原生Hamiltonian。仅沿用xTB零虚频两端几何作普通单点+梯度；气相q0/singlet、原子序C/O/O/H/H不变。PySCF Mole仅坐标/状态容器，无轨道基组；日志空basis警告并非做了HF/DFT。单核/2048MB、显式限制OMP/BLAS。公开同步shell提交job768，call_id tc_bfbbf076f522497d，state=done；此前异步job763失败不能推广至同步通道。
脚本 [smoke.py](gold_compute/queue_20261018/results/IA8/pm7_bridge/smoke.py)，[wrapper日志](gold_compute/queue_20261018/results/IA8/pm7_bridge/.cloudra/calc-768.out.log)，[结构/力/梯度与ASE字段](gold_compute/queue_20261018/results/IA8/pm7_bridge/results.json)。原生 [R.out](gold_compute/queue_20261018/results/IA8/pm7_bridge/CH2OO.out) / [P.out](gold_compute/queue_20261018/results/IA8/pm7_bridge/dioxirane.out) 均PM7、RHF九个双占轨道、SCF FIELD WAS ACHIEVED、JOB ENDED NORMALLY；同目录各自.mop/.arc保留。关键词PM7 1SCF GRADIENTS SINGLET PRECISE DISP RELSCF=0.0001；ASE中charge=0（中性在原生输入省略CHARGE）。
**能量口径警告**：ASE get_potential_energy实测取final_hof，不是total_energy。回调返回R/P=0.05065501211154344/0.01691429443161306 Eh，分别对应Hf=31.78650/10.61388 kcal/mol，不能称纯电子总能。原生TOTAL ENERGY（电子+核排斥、另列dispersion）为−735.40815/−736.32705 eV；原生日志对Hf的dispersion修正另列，不混这两口径。坐标Å；回调grad=−forces×Bohr/Hartree，单位Eh/Bohr；梯度范数R=0.0836382638、P=0.1119499284，明显非PM7驻点。首个碳x梯度R为+0.026277664 Eh/Bohr，与原生+31.160607 kcal/mol/Å方向一致。job768当时未做有限差分复核、优化/频率/TS/IRC，仅证明接口可调用；后续普通端点与差分校验见下文，仍不形成已闭合反应边。


### PM7端点延伸校验：已得模型内极小值，仍非严格反应边
[有限差分脚本](gold_compute/queue_20261018/results/IA8/pm7_validate/fd.py) 与 [结果](gold_compute/queue_20261018/results/IA8/pm7_validate/fd_results.json)，job769（tc_aeb1d2b84ffd4da4）：两端各C1x/O2x/O3z、h=0.001/0.002Å的12项中心差分，Hf对返回解析梯度最大误差4.3623783×10⁻⁶ Eh/Bohr，支持采用含bits的Hf gauge；并非全坐标严格误差界。单位/负号沿用首版。
[首次BFGS普通优化770日志](gold_compute/queue_20261018/results/IA8/pm7_validate/.cloudra/calc-770.out.log) 两端precision loss，残差4.3855×10⁻⁵/5.0718×10⁻⁵ Eh/Bohr，未达事先2×10⁻⁵阈值，未跑频率。能量输出量化限制线搜索只是解释假说，不是已排他确证原因；失败保留。
经一次授权的[梯度修正脚本](gold_compute/queue_20261018/results/IA8/pm7_validate/refine_minima.py)以当前近极小几何普通least_squares梯度残差修正，无TS搜索。job776（tc_8c85d07237cc4d58）[原始wrapper日志](gold_compute/queue_20261018/results/IA8/pm7_validate/.cloudra/calc-776.out.log) / [全部原生作业索引、残差和频率](gold_compute/queue_20261018/results/IA8/pm7_validate/refined_results.json)：R/P max梯度=1.6022654×10⁻⁸/8.4329756×10⁻¹⁰ Eh/Bohr。所有MOPAC回调均检查SCF FIELD WAS ACHIEVED/JOB ENDED NORMALLY；自定义优化的收敛证据是残差及后续Hessian，不是MOPAC原生Opt声明。
完整15×15 Cartesian梯度中心差分Hessian，h=.003/.005Å；按ASE原子质量质量加权，以质心坐标构建3平移+3转动刚体向量，通过null_space投影至9维振动子空间。两步长各9频全正，R最低527.8813/527.8587、P889.8246/889.8303 cm⁻¹；全谱最大步长差约0.023cm⁻¹。Hessian反对称最大R9.67×10⁻⁶/2.91×10⁻⁵、P6.40×10⁻⁶/1.76×10⁻⁵ Eh/Bohr²，先报告反对称量后对称化。**这是自定义全数值频率，不是PySCF或MOPAC原生频率日志；原生SP输入/.out/.arc逐次保留，脚本和.npy矩阵可重建分析。**
[最终R几何](gold_compute/queue_20261018/results/IA8/pm7_validate/CH2OO_refined/final.xyz)保持无环CH2OO：C1-O2=1.291、O2-O3=1.245、C1-O3=2.186Å；[最终P几何](gold_compute/queue_20261018/results/IA8/pm7_validate/dioxirane_refined/final.xyz)为C1-O2-O3三元环：C-O各1.399、O-O1.459Å，C/O/O/H/H原子序不变。R短O-O被通用单键阈值标compressed，P角偏差为三元环预期几何，不掩盖这些观察。
PM7参数化Hf/模型势能R/P=0.047150682549204584/0.012302220637635744 Eh；Δ(P−R)=-21.867740 kcal/mol。**同组成差消原子参考常数但保留氢键/色散bits；PM7 Hf拟合298.15K标准态，参数含隐含ZPE/热贡献，故不称严格物理0K无ZPE裸电子能。**未额外加显式ZPE/热修正。官方定义：https://openmopac.net/Manual/SCF_calc_hof.html 与 https://openmopac.net/Manual/HoF%20versus%20total%20energies.html 。尚无TS模式/双向IRC，不能将两独立极小值冒充已验证反应边，也不混xTB能量。最新ts_inspect tc_c28373f16f034af2仍waiting/refine、wait_for_system，无可编辑必填；未手动绕过。

## 最新xTB恢复与strict缺证据诊断
本轮按新要求已实际尝试同run恢复：IRC profile numeric→auto并TightSCF，ts_resume tc_f4837158d0b94d28返回tool_exception、effect_state unknown。后inspect tc_5e586421a75c45f3确认声明变更已写入，但waiting/refine，frequency/IRC actual=null，未提交任何新频率/IRC作业。完整返回：[current_recovery_evidence.json](current_recovery_evidence.json)。
现有739仅OptTS无频率；ts_guess strict诊断tc_d6051b973a124d6d返回is_success=false、Failed to parse vibrational frequencies、verification_status空，完整请求/返回：[ts_guess_strict_current.json](ts_guess_strict_current.json)。不是pass，不是IRC科学失败。无法生成TS模式、双向IRC和IRC外端Opt/Freq，不回填边；当前精确工程阻塞已交协调者，不新run/shell绕过，不无限等待。


**819后当前结论/模式区分试验**：816优化正常收敛、819正常零虚频（最低503.65cm⁻¹），但仍相同三几何mismatch；一次显式seed不能消错，停止重复Opt。env直接文件对照证decl6原生final xyz与saved差最大4.829626e-7Å且四舍五入6位逐值相等，具体validator阈值未确认。原生[frequency.hess](ts/ts_0001/jobs/declaration_0005/frequency/frequency.hess) mode6全位移投影见[mode790_analysis.json](gold_compute/queue_20261018/results/IA8/mode790_analysis.json)：C1-O3键向−0.349093、C1-O2+0.056110、O-O+.093505；H-H相对norm1.258783但键向仅−.000269，主要横向，不能由norm主导推为H-H伸缩。碳相对O2沿CHH瞬时平面法向−.312209（不是完整面距导数）。[IRC B外帧](ts/ts_0001/jobs/declaration_0005/irc/irc_IRC_B.xyz)无环CH2OO（C-O1.254/2.217Å）；[IRC F外帧](ts/ts_0001/jobs/declaration_0005/irc/irc_IRC_F.xyz)三元环（C-O各1.360Å）。这些支持耦合成环假说，仍保留ts_guess显式watch strict fail；未删watch/改阈值，未宣称验收通过。需工具处理可复核模式反例及几何量化一致性，产品外端验证尚未生成。


### 定向tight复查过程（历史，已由下节完成结果覆盖）
已用原生790 .hess完整带符号mode6及796近TS F/B前三帧作无新QM方向复查：[可重现脚本](gold_compute/queue_20261018/results/IA8/tight_mode_review/direction.py)、[来源SHA与数表](gold_compute/queue_20261018/results/IA8/tight_mode_review/direction_results.json)。原子序C/O/O/H/H不变；ORCA Cartesian位移转sqrt(m)质量加权，IRC先质量加权Kabsch对齐，双方同一metric投影6刚体方向并各自单位归一。首帧cos F≈+1/B≈−1，但首帧为算法初始化，非独立证明；第二/第三有限弦abs cos F=.93785/.92531、B=.96654/.96168。F首帧C1-O3缩.03843Å，B伸.03844Å，模式径向导数C-O3−.349093/C-O2+.056110/O-O+.093505；H-H径向−.000269而横向相对位移大，支持反应耦合弯曲而不是单纯H-H伸缩。保留strict fail及物理适用性风险，方向一致不替代验收。
原默认739输入未TightOpt；本轮一次同方法/同占据TightOpt TightSCF已通过同run ts_resume完整配置替换，call tc_6f97ad51b6ca4aaa，正式OptTS834已ready（[输入](ts/ts_0001/jobs/declaration_0007/ts_opt/refine.inp)）。先前引用stage直接patch被输入诊断拒绝tc_e985851ae46e4ca3，不是科学失败；[更正后完整回执](gold_compute/queue_20261018/results/IA8/tight_mode_review/tight_resume_corrected.json)。未改watch/阈值/预算，旧790/796/fail完整保留为历史；待新频率/IRC实际结果比较，不预承诺Gold。


### Tight定向复查结果（已完成，无新增Gold）
原739末次内部收敛表RMS/MAX gradient=.0000527295/.0001700857，容差.0001/.0003；834 TightOpt对应.0000265566/.0000785153，容差.00003/.0001。最终外部梯度norm由.000159187584降至.000076331097 Eh/bohr。实际两者xTB调用仍--acc .2、SCC能量2e-7Eh、wf2e-5e、电子温300K、unpaired0；**几何阈值确实收紧，但TightSCF未使已观察后端精度改变**。原生来源739末表约4500行、834末表约4900行，及各自末尾xTB SETUP/SUMMARY。
835最终.hess的vibrational_frequencies索引6为唯一负值−950.47（旧790−950.34），normal_modes同列6；atoms为相应最终TS中心、Bohr坐标，IRC同序C/O/O/H/H。新模式与新836轨迹比较见[完整带SHA数表](gold_compute/queue_20261018/results/IA8/tight_mode_review/direction_tight_results.json)及[脚本](gold_compute/queue_20261018/results/IA8/tight_mode_review/direction_tight.py)。质量参与率C/O/O/H/H=21.65/23.86/21.91/20.57/12.01%，重原子67.42%；全体系质量Kabsch对齐后截取重原子单独归一，F2/3 cos=.96841/.96622，B2/3=−.98733/−.98987（此重原子指标不再单独拟合刚体，避免三原子过拟合）。因此全方向相合不是仅H运动主导的假象；首帧是初始化，2/3为有限弦不是严格局部切线。C-O3导数−.349138、C-O2+.056113、O-O+.093503、H-H−.000258；支持C-O成环伴随CH弯曲的耦合方向，未证明物理高精度。
Tight后仍[ts_guess strict fail完整返回](gold_compute/queue_20261018/results/IA8/tight_mode_review/strict_tight.json)，call tc_5c084717219e41c9；watch与阈值未变。836 IRC已完成，838反应物频率后仍三几何mismatch/candidate_only，产品外端未启动。tight未消除两个验证问题，不反复优化，不称strict误报已确证，不回填Gold/目标垒；本轮定向复查完成。


## 最新836自身外帧优化配对与正式strict结果（覆盖旧端点调用结论）
旧strict_tight使用explore独立端点，不能等同本轮endpoint-relaxed检验；837/838又为旧796→800谱系。本次已针对性配齐**836 B→841 R、836 F→840 P**，均普通无约束GFN2-xTB Opt+NumFreq、q0/m1、TightSCF，无TS/IRC重算，也未冒充durable verified。原子序C/O/O/H/H身份映射保持[1,2,3,4,5]，未交换等价O/H。
原生输入/最终XYZ/日志： [R输入](endpoint_strict_review/reactant_optfreq.inp)、[R最终](endpoint_strict_review/reactant_optfreq.xyz)、[R841日志](endpoint_strict_review/.cloudra/calc-841.out.log)；[P输入](endpoint_strict_review/product_optfreq.inp)、[P最终](endpoint_strict_review/product_optfreq.xyz)、[P840日志](endpoint_strict_review/.cloudra/calc-840.out.log)。两端正常终止、优化收敛、9个正振动，最低R503.56/P1020.46 cm⁻¹，身份分别无环CH2OO与C-O-O三元环。
[同源配对数值及SHA](endpoint_strict_review/endpoint_comparison.json)与[脚本](endpoint_strict_review/compare.py)：原生IRC外端至对应优化末帧，质量Kabsch RMSD R=.00463465/P=.00190746Å，最大原子位移.0184874/.0092449Å。R C1-O3 2.21720→2.22210Å，P C-O约1.3595→1.3602Å；这是独立分析量，不是工具验收阈值或pass。
唯一规范strict调用 **tc_8b3a7df380064bda**：835频率/836 IRC原日志，reactant/product为上述两新原生final XYZ，engine=orca、strict=true、原watch[[0,2],[0,1]]；[完整args/results](endpoint_strict_review/strict_own_endpoints.json)。返回verification_status=fail，checks仅唯一负频−950.47与mode misalignment，irc_end_a/b为空，没有端点匹配数值/通过判断。本次实际工具未兑现用户所述‘端点一致优先通过’行为；不从此次返回推断永久算法机制，也不将未执行的端点比较说成fail。公开合同没有另一个endpoint-priority开关或单独endpoint-match验收入口。
**当前**：两侧真正同轮IRC-own优化零虚频链已具备，strict仍未pass；方向科学证据较强但电子态/方法精度风险仍在。不删watch、不改阈值、不重试/追加QM，不回填Gold。无后台作业。

## 上轮tight收口结论（历史，端点缺口由上节补齐）
一次TightOpt定向复查完成，无后台作业。当前已实际有834 TS优化、835唯一负频、836双向IRC与837/838反应物外端Opt/Freq；仍因几何校验和strict模式fail未通过，产品外端链未完成，不追加QM。
直接前后负模比较：[mode_overlap.json](tight_mode_review/mode_overlap.json)、[脚本](tight_mode_review/overlap.py)。两原生.hess各自唯一负频均为normal_modes列6；质量加权Kabsch旋转后，在同一旧TS刚体补空间投影、单位化并取±无关绝对cos：full=0.9999999934，heavy=0.9999999990；几何质量RMSD=0.0000526945Å。故本模型内模式对几何tight稳健，并非仅频率数值相似。
原生旧[790 Hessian](../../../../ts/ts_0001/jobs/declaration_0005/frequency/frequency.hess)、新[835 Hessian](../../../../ts/ts_0001/jobs/declaration_0007/frequency/frequency.hess)；新[834优化日志](../../../../ts/ts_0001/jobs/declaration_0007/ts_opt/.cloudra/calc-834.out.log)、[835频率日志](../../../../ts/ts_0001/jobs/declaration_0007/frequency/.cloudra/calc-835.out.log)、[836 IRC日志](../../../../ts/ts_0001/jobs/declaration_0007/irc/.cloudra/calc-836.out.log)。派生[旧方向表](tight_mode_review/direction_results.json)、[新方向表](tight_mode_review/direction_tight_results.json)、[strict完整fail返回](tight_mode_review/strict_tight.json)均保留。
判断分开：反应方向证据较强且tight前后稳健；实际后端电子精度前后相同（acc .2/SCC2e-7Eh），不是更高精度电子态验证；strict仍fail/未pass，几何来源校验仍拒绝，不能宣布误报已确证或回填Gold。CH2OO电子态/多参考与普通GFN2适用性风险未解除。
