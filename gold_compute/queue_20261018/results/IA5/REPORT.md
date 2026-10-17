# IA5 环丁烯反旋开环：计算审计

## 最终旋向结论（覆盖旧候选身份未定措辞）
**756/792/799是顺旋竞争开环，不是指定反旋边。** [旋向审计](ROTATION_AUDIT.md)与两个完整逐帧JSON给出固定C/H身份、同一共同观察轴的两CH2转角。共同轴F增量四氢均正、B均负且两端对应列差小于0.05°；两局部轴点积+0.84758，已排除反向轴符号伪影。Rodrigues代数校准及整体刚体不变性见审计。不能把一虚频/连通正确丁二烯转化为反旋身份；原watch未改，strict未pass，模式向量独立投影未完审。
目标反旋尚未定位，无目标势垒。停止为此顺旋候选重复端点/parser修复；不授权新搜索、不改原生证据。

## 最新恢复进展（覆盖此前等待措辞）
运行时已接续真实NumFreq792：正常结束、恰一虚频−769.34 cm⁻¹，E=−11.487579110350 Eh；原生路径`ts/ts_0004/jobs/declaration_0006/frequency/.cloudra/calc-792.out.log`。双向IRC799已实际启动，非仅计划。alignment提示H7/H8主导而C3/C4相对位移0.394；CH2旋转本可氢主导，故保留IRC待方向检验，不能直接当伪模或直接认反旋。尚无IRC外端/strict pass，仍不交付势垒。

## 当前结论
**尚未取得可验收的PM7或GFN2-xTB反旋一阶TS势垒；不交付数值ΔE‡。** 已有实际GFN2-xTB端点优化/频率、约束扫描及durable无约束OptTS。缺候选频率、反旋模式证明、双向IRC及IRC外端零虚频验证，不能把扫描峰或OptTS收敛本身当标答。

## 模型与识别
气相热单分子C4H6，电荷0、多重度1；温度未指定，无溶剂/水/酸碱/对离子。孤立闭壳方法内PES不代表多参考精度。按题映射C1=C2–C3–C4环：C3–C4断裂，C1=C2降阶，C1–C4/C2–C3升阶。反旋要求两个末端CH2在一致观察坐标中的相反旋转；需跟踪附氢及两个局部轴的取向，不能仅比较两个任意符号二面角，更不能凭产物丁二烯身份判断。旧L1的35.17 kcal/mol为顺旋，完全不采用。当前扫描固定碳骨架平面只为探索，不足以强制反旋。

## 已有原生证据
- [RC输入](work/rc_xtb.inp)、[原生日志](work/rc_xtb.log)：ORCA 6.1.1，GFN2-xTB，Opt+NumFreq，优化收敛/正常结束，0虚频，E=-11.557969661030 Eh，最低振动318.49 cm⁻¹；log_parser已确认。
- [独立s-trans产物输入](work/prod_strans.inp)、[原生日志](work/prod_strans.out)：收敛/正常结束，0虚频，E=-11.552702001440 Eh，最低振动144.47 cm⁻¹。这不是IRC外端，且结构顺序与环端点不同，不可直接套二面角诊断。
- [PM7探测输入](_engine_test/pm7_sp.inp)、[原生拒绝日志](_engine_test/pm7_sp.stdout)：ORCA6.1.1不识别PM7关键字。本机未找到Gaussian；MOPAC可用性由环境同事另核，且其日志不满足原题ORCA/Gaussian解析限制。此为软件/输入能力限制，不是PM7反旋势能面不存在的证据。
- [durable记录](../../../../ts/ts_0004/process.json)；原始扫描日志：`ts/ts_0004/jobs/declaration_0003/scan/.cloudra/calc-753.out.log`；原始OptTS：`ts/ts_0004/jobs/declaration_0004/ts_opt/.cloudra/calc-756.out.log`。不可改写/重命名原证据。

## 流程诊断与下一步
扫描753内部峰进入无约束OptTS756，协调者log_parser确认756正常结束及优化收敛；仍仅候选。ts_inspect显示waiting/refine、753/756均done、next=wait_for_system，频率没有启动。scan frequency_mode须auto，TS/IRC非频率阶段也须auto，已分别修复；独立频率保持numeric。尝试ts_resume明确numeric频率并添加TightSCF触发推进，工具报内部执行失败（未返回backend call_id），已通知AgentHub。不得手工绕过TS/IRC或修改状态。
下一步先修复durable推进/ORCA原生xTB几何解析，然后同run核全Hessian指数、模式附氢旋转方向；若一虚频并准确反旋，再双向IRC、两外端同级无约束Opt+Freq及映射方向验证。若为顺旋或多阶鞍点，如实保留，改语义约束/预组织种子而非将其认作反旋。当前失败不证明真正反旋一阶TS不存在。

## PM7普通端点补算：异步后端失败（最新）
MOPAC23.2.5已安装；从本题既有工具生成XYZ逐行转换保留[RC优化输入](pm7/rc_opt.mop)、[产物优化输入](pm7/p_opt.mop)与种子FORCE输入rc.mop/p.mop。公开submit_compute_job接受shell并返回761/762 ready，但终态均failed、attempt_count=0、last_error=`Unsupported job_type: shell`。诊断query调用id为`tc_aef594236f9e473e`/`tc_1449473d64d8421a`。**两项均未实际执行，无MOPAC .out/.arc、无PM7能量或频率，不能称在跑/已算。** 不转Bash绕过。后续协调者发现IA9同步shell成功（is_async=false），因此这里只证明本题异步shell路径失败，不能泛称全部shell不可；不批量重试，待协调者选定最小PySCF外接PM7测试。
用户后续明确要求在PySCF里调PM7；env已核当前PySCF2.14无已装PM7接口，ASE→MOPAC属于外接，不是PySCF原生PM7。是否可经公开回调适配与compute后端可执行是两个独立缺口，不替换为HF/DFT/CASSCF。

## 审计备注
早期端点与引擎探测通过直接普通引擎执行而非队列，已告知协调者；后续TS均durable队列。未修改其他题或完成的原生日志。format_converter对原生xTB日志的末帧导出失败，不能把导出失败说成优化失败；log_parser文本fallback能读能量、收敛与频率。
