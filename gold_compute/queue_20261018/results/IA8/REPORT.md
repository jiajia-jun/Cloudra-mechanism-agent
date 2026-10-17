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

## 收口与剩余缺口
本轮无后台计算，不新增搜索；待受权维护者修复同一durable run的自动推进后，先验证候选频率/模式，若不合格则依据结构改耦合坐标猜测，不追加迭代参数堆叠。正式标答仍缺TS频率、IRC两向方向和外端身份/零虚频证据。详见项目根PROCESS.md自己的IA8章节和AgentHub。
