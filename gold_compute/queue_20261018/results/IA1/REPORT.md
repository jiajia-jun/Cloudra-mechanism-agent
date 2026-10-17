# IA1 PM7 / GFN2-xTB 实算进展

## 当前判决
尚无满足一虚频TS + 双向IRC + 两端零虚频身份一致的严格方法内参考边；不报势垒或反应能，不更改原任务/registry科学标签。

## 模型与映射
气相孤立C4H4，电荷0，多重度1，闭壳种子。低温/基质材料和温度未给；未模拟基质、隧穿、热动力学。映射 [CH:1]1=[CH:2][CH:3]=[CH:4]1 → [CH:1]1[CH:2]=[CH:3][CH:4]=1；四环骨架与各C附H不变。短键1–2/3–4变长，长键1–4/2–3变短。单重态占据参数不是多参考/自旋纯验证。

## 已有原生尝试
- PM7：job719，[输入](test_pm7_sp.inp)，[原生日志](.cloudra/calc-719.out.log)。ORCA6.1.1不识别PM7简单关键字。PATH中无Gaussian、MOPAC/mndo。PM3/AM1/MNDO可运行但不是PM7，不替代目标。需真正支持PM7的引擎；若用MOPAC，还需解决题设仅ORCA/Gaussian格式的证据验收，不能伪装日志。
- GFN2-xTB：ORCA6.1.1外调xtb6.7.1 (edcfbbe)，无轨道基组、无溶剂；日志显式Hamiltonian GFN2-xTB、-c 0 -u 0。GFN2-XTB、XTB2、XTB探针job723/725/726实际相同GFN2。
- [矩形Opt+NumFreq输入](rect_optfreq.inp)，[job731原生日志](.cloudra/calc-731.out.log)，[原生几何](rect_optfreq.xyz)。电子能 -10.444857273820 Eh，零虚频；最低非平移转动507.5 cm⁻¹，C–C约1.326/1.552Å。此为已验证的端点，不是TS。
- [扫描737](.cloudra/calc-737.out.log)单调到1.46Å；[延伸749](.cloudra/calc-749.out.log)在约1.50Å区域跳到另一个键交替支，内部峰仅初猜，任何扫描最高点都不是本报告势垒。解析器watch pair显示曾出现索引/元素异常，认定身份须复核实际原生结构。
- durable运行 `ts_0002`：完整映射候选0，产物绑定具体C顺序1,4,3,2及附H。初次OptTS job752达到最大优化步数未收敛，[原生日志](../../../../ts/ts_0002/jobs/declaration_0005/ts_opt/.cloudra/calc-752.out.log)。正常终止字样不代表优化收敛；无合格TS。

## 在跑与下一步
同一durable运行的相邻短键伸长/长键缩短耦合扫描（17点）job755已完成，但未有可用内部峰，流程阻塞，无后台作业。原生日志位于项目根 ts/ts_0002/jobs/declaration_0006/scan/.cloudra/calc-755.out.log。后续建议对称方形约束优化/全Hessian种子，再经同一durable正式TS/IRC；本轮未完成这些证据。原先只拉两短键的跳支提示需要显式耦合，而非证明无TS。TS优化声明auto频率模式并以%geom Calc_Hess true NumHess true end请求初Hessian，后续频率numeric；优化阶段frequency_mode=numeric会被writer拒绝（无Freq任务），已修正。后续须核查真正键交替模式与两向端点；不能从同SMILES认定自动异构化成功。

### IA1 方形Hessian补试
由矩形Z矩阵通过internal_coordinates工具生成四边1.44Å/CH夹角135°的方形种子。[约束优化758](.cloudra/calc-758.out.log)正常、约束优化收敛；另行移除全部约束做[完整NumFreq759](.cloudra/calc-759.out.log)，正常且恰一虚频−4535.22 cm⁻¹、E=−10.4087086777 Eh。固定边长不证明自由驻点，parser未返回模式向量，故尚不认定TS或报势垒。已同durable ts_0002新种子恢复正式无约束OptTS job760；待结果及频率/IRC推进。MOPAC现已由IB9安装并成功PM7优化，之前PATH缺失为当时环境，不应解释为PM7永远不可用；durable/scorer兼容仍是独立缺口。

### 最新接口/提交审计（纠正待运行措辞）
用户所指为PySCF里调用PM7，不授权CASSCF替换。env核当前PySCF2.14.0无已装PM7/semiempirical/mopac接口；ASE/MOPAC是另一真实接口，不能称PySCF PM7。异步shell提交虽返回准入，但query证实PM7普通Opt job764与改向误解期间CASSCF脚本job767均failed、attempt_count=0、last_error为 Unsupported job_type: shell，故二者均未实际计算，不存在可报告能量；不绕过Bash执行。协调者后续核IA9同步shell普通PM7确有原生输出，故故障结论仅限本题异步通道，不能一概声称shell不可；待指定单题同步PySCF外接PM7验证，不重复批量提交。输入run_rect_pm7.sh、rect_pm7.mop与pyscf/casscf_sp.py只作提交审计，后者非当前目标证据。xTB正式job760已done，但ts_0002仍waiting/refine、频率未启动；当前无运行作业，无合格边。

### IA1 最终候选审计
最新只读ts_inspect `tc_19fe716fe9fd466a`：ts_0002 waiting/refine，next=wait_for_system，required_inputs/editable_groups均空，blocked=null。原生[正式OptTS760](../../../../ts/ts_0002/jobs/declaration_0007/ts_opt/.cloudra/calc-760.out.log)经log_parser `tc_4bb238dd377f4229`确认正常终止、优化收敛，E=−10.408998801830 Eh；但没有后继频率或IRC，故只为收敛驻点候选，不是已验一阶TS。先前方形759的一虚频不能转移到760不同几何，且其模式向量parser未返回。必要的端点optimization auto/frequency numeric分离修复已尝试一次ts_resume，工具内部失败且未提供backend call_id；未重复干预/改预算，不把修复当已解锁。原始日志不改写，未改变registry/accessibility。当前没有合格ΔE‡/ΔErxn、无运行作业；需工程修复durable推进后核同几何目标虚频、双向IRC与身份一致的零虚频两端。

### IA1 强制继续轮：实际recovery证据
本轮读取现行合同后，inspect tc_4b0c78964fd842e9显示两端optimization实际planned已auto（修订曾内部失败不能简单视为未提交），但IRC仍numeric。仅针对非Freq的IRC独立改auto一次ts_resume，完整返回内部执行失败且无backend call_id暴露。后inspect tc_4aa77b495b0d4a06证实IRC planned已auto、TS/端点频率仍numeric，然而仍waiting/refine,next wait_for_system,required_inputs/editable_groups=[]，frequency/IRC actual=null。没有同几何NumFreq或双向IRC被提交，不能假做ts_guess严格通过。参数、完整inspect、原始错误和缺失验证链已保存[recovery_round_latest.json](recovery_round_latest.json)。这是本轮真实推进尝试/工具阻塞，不是化学失败；不新run绕过、不手动TS/IRC、不改状态预算，等待实际durable恢复能力。

### IA1 IRC实际推进及物种方向修复
旧no-submit已失效：原生793为760同几何NumFreq，一虚频−4610.8；797双向IRC各11点收敛。internal_coordinates核797原生B端C12/C34=1.327Å、C23/C14=1.551Å符合R，F端相反符合P；各附H和环保持。默认A作为R后的801/805收敛零虚频但几何一致性validator拒绝；显式801最终xyz重试811/812仍拒绝，且实际属P，不能凭同SMILES算R。现依据真实映射方向以B/F分别明确R/P seed，ts_resume tc_d92b43f2a4184978提交817 R Opt（同run、保留760/793/797），等待后续真实通知；不再重复不具物理理由的opt。模式parser null且缺严格ts_guess证明，目前仍不填能垒。

### IA1 当前端点匹配阻塞（覆盖在途817措辞）
817/820已完成：R正确B方向优化收敛E=−10.44485755468 Eh，频率零虚频E=−10.44485755463 Eh，但仍候选判三份几何不匹配。直接read显示原生reactant_opt.xyz14位坐标与频率reactant_source.xyz6位仅四舍五入（C1 x −0.41797978874827→−0.417980），已交env集中核验，不再重复Opt。P端尚未提交，不能从R或同SMILES替代。IRC F/B身份、频率来源及待执行strict参数保存在本题 `irc_direction_and_strict_pending.json`；product参考仍null，故未虚构strict通过。已真实计算双向IRC，不再沿用旧no-submit结论；仍无已验势垒。

## 独立IRC外端一次性Opt+NumFreq与strict实测
授权独立普通计算823/824均正常、同日志优化收敛且零虚频，E_R=E_P=−10.444857554680 Eh。原生[823](independent_endpoints/R_B/.cloudra/calc-823.out.log)、[824](independent_endpoints/P_F/.cloudra/calc-824.out.log)，NAME绑定optfreq.xyz；来源直接797 B/F，不重建SMILES。固定完整map C1-4/H5-8保持，R_B的C12/C23/C34/C14=1.326/1.552/1.326/1.552Å，P_F=1.552/1.326/1.552/1.326Å，是真正矩形键交替。
使用原793频率、797 IRC与这两端原生最终XYZ实际ts_guess strict（tc_8b6d2b548ee34c9a），返回n_imag=1（−4610.8）、imag_mode_aligned=true、四watch相对位移0.704均超阈0.498、两IRC方向收敛；但verification_status=inconclusive，原因missing TS geometry（频率/IRC日志未读出可用TS坐标）。全参数及全返回见[strict_original_paths.json](strict_original_paths.json)。不重复Freq/IRC，不修改日志，不伪造TS xyz。尚未strict pass，故不填参考势垒/registry；独立端点成功也不宣称durable几何validator通过。

## 官方输出开关一次性试验终态
原ts_0002经tc_221f5608b139451a只给verification.frequency加入官方%output Print[P_Cartesian] 1（ORCA6.1 §2.4），新NumFreq825和自动IRC826/R端827/828已完成。825原生日志无CARTESIAN COORDINATES表；本external-xTB调用下该开关未解决中心消费。新825/826搭配823/824与同四watch实际strict tc_a5f8e226558142c0仍inconclusive missing TS geometry，一虚频−4610.8、模式aligned=true、双IRC收敛。全参数/全返回见[strict_output_trial.json](strict_output_trial.json)。durable R匹配仍candidate_only；不再verbosity循环、不改完成证据、不重复QM。维护者需受信.hess中心解析，未pass仍不填barrier/registry。

## XYZFILE受控产物试验终态
同run仅frequency keywords加XYZFILE，829/830及自动R端831/832完成；引擎真实生成declaration_0013/frequency/frequency.xyz，sha256=756fe3487dd4a168cd923ec9d7c692bac1cc3d8e64a6b74ffa4380adf3795a69，与同目录optimized.xyz元素序及逐坐标完全一致（最大差0）。产物未手造/复制改名。用新829/830及823/824同四watch strict tc_be36a5dc25504c13仍inconclusive missing TS geometry，一虚频/模式对齐/双IRC收敛均通过局部检查；全返回[strict_xyzfile.json](strict_xyzfile.json)。原生中心XYZ现已存在但工具不消费；停止所有输出组合/重复QM，交维护者解析适配。durable仍R几何mismatch candidate_only，未strict pass、不填能垒或registry。

## 原字节共定位单次试验
授权将829stdout别名frequency.out与原名inp/xyz/hess、830stdout别名irc.out与同job原名inp/hess/两端/轨迹共定位到strict_native_bundle。初始整文件read截断导致草稿SHA失败，已用≤100行分页完整拼接校正；最终12文件源/目标SHA全部相等，manifest valid=true含绝对路径，原源未动、几何未改名。真实包内strict tc_0790a535075c4cbf仍inconclusive missing TS geometry，模式对齐/一虚频/双IRC收敛局部检查不变。全返回[strict_bundle_result.json](strict_bundle_result.json)，字节审计[manifest](strict_native_bundle/manifest.json)。因此不支持简单共定位即可解决的假说，停止文件名排列及重复QM；仍未批准，不填barrier/registry。
