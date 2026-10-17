# IA9 PM7 / GFN2-xTB 实算探索（未获得严格合格边）

## 模型与路径
题设为气相热反应、中性单重态；温度未指定，无溶剂、水、酸碱或反离子。模型为孤立 C2H4O2，不能描述激发态化学发光动力学。起点原子顺序 C1 C2 O3 O4 H5 H6 H7 H8；断 C1-C2/O3-O4，C1-O4/C2-O3升至双键。O-O先伸长及耦合C-C/O-O路径都实际探索，未强迫协同机制。

## 直接证据
ORCA 6.1.1 调用 xtb 6.7.1，Hamiltonian GFN2-xTB，无基组/溶剂，q0/m1，xtb --uhf 0；不是经验证的开壳单重态波函数。
- [R 原生日志](orca/.cloudra/calc-727.out.log)：Opt+NumFreq 正常终止，优化收敛，0虚频，E=-14.332457737560 Eh。
- [CH2O 原生日志](orca/.cloudra/calc-728.out.log)：同级Opt+NumFreq收敛、0虚频，E=-7.175648087940 Eh。分离2CH2O相对R的电子反应能为约 -11.8214 kcal/mol；这是组分参考，不是IRC完整产物端证据。
- [PM7 probe](orca/.cloudra/calc-724.out.log)：ORCA原生 ! PM7 被拒为UNRECOGNIZED OR DUPLICATED KEYWORD，退出4。探测当时PATH无Gaussian g16/g09、MOPAC。随后env确认隔离MOPAC23.2.5/Apache-2.0/osx-arm64可执行：`../IB9/mopac_env/bin/mopac`。早期“无MOPAC/尚无经验证普通提交后端、无成功PM7能量”仅属探测时历史；此后已通过公开shell提交完成真实PM7端点（见下），当前缺正式durable PM7 TS/IRC后端及scorer格式适配，不能直接bash计算绕过计算门。未把xTB冒称PM7。
- O-O粗/细扫描 [736](orca/.cloudra/calc-736.out.log)、[741](orca/.cloudra/calc-741.out.log) 与耦合扫描 [750](orca/.cloudra/calc-750.out.log) 均在C-C裂解区跳谷；扫描峰不是势垒。细扫描8→9跳变约71 kcal/mol。
- [triplet probe](orca/.cloudra/calc-744.out.log) 使用-u2；[UHF singlet probe](orca/.cloudra/calc-746.out.log) 仍传-u0且能量与原单重态相同，不能据此称BS单重态。

## PM7 后续实际成功端点（公开shell提交）
协调者澄清公开submit_compute_job shell通道后，job765普通Opt与job766 FORCE均实际成功，未用Bash直接计算。输入坐标来自现有工具生成XYZ和MOPAC优化arc，不手打几何。MOPAC23.2.5、PM7 PRECISE CHARGE=0 SINGLET XYZ（默认闭壳填充），气相无COSMO。
- [R.out](pm7/R.out)/[R.arc](pm7/R.arc)：EF优化与SCF成功、正常结束，梯度范数0.02926；[R_force.out](pm7/R_force.out)18个振动均正，最低202.69 cm⁻¹。
- [CH2O.out](pm7/CH2O.out)/[CH2O.arc](pm7/CH2O.arc)：正常优化、SCF成功、梯度0.01578；[CH2O_force.out](pm7/CH2O_force.out)6个振动均正，最低1099.59 cm⁻¹。
原生输出给热生成焓R=3.02121、CH2O=-25.54337 kcal/mol；2Hf(CH2O)-Hf(R)=-54.10795 kcal/mol。这不是题设要求的经核纯电子总能差，不能写成严格裸0K电子reaction_energy_kcal_mol。研究者官方定义核查给出 Hf=E_elect+E_nuc−E_isol+E_atom+E_bits；同组成只消原子常数、不保证消post-SCF氢键/色散bits，PM7拟合亦隐含标准态/ZPE热贡献，因此不将Hf差冒称严格物理电子能。现有日志未打印TOTAL ENERGY等eV分项。MOPAC格式不满足题设ORCA/Gaussian scorer，且正式TS/IRC无durable MOPAC后端；端点是方法内预备证据，不是合格PM7边。

## 用户授权的一次必要修复（最新）
协调者转达用户ask_user明确授权“同意，仅增加1次必要修复并继续IRC验证”。inspect tc_c7ee025ed8c44097核blocked/无在途；按授权仅拟将max_interventions 2→3，并将IRC和两侧endpoint opt显式replace同GFN2-XTB auto，独立freq numeric、compute_actions12不变。工具tc_cf5a83fc2e3d4a77拒绝改变source；保留原source、reason记录用户授权的tc_dcc2d25237554e5e仍报“input revision cannot raise authorized limits”。修订未生效，无新IRC作业。需维护者接入本次用户授权至后端授权额度，不能Agent手改状态；不把工程拒绝当科学失败。

## durable TS 进度及障碍
ts_0003（项目根 ts/ts_0003/process.json）。明确选择映射候选0，保留C1-O4/C2-O3及附氢。初始frequency_mode错误已纠正：TS优化auto、验证频率numeric。正式TS job751已正常结束且优化收敛，E=-14.236925919280 Eh（尚未频率验证）。输入 ts/ts_0003/jobs/declaration_0003/ts_opt/refine.inp；但自动推进停滞：ts_inspect tc_c53147947c6549da 显示 waiting/refine、next=wait_for_system、editable_groups=[]，751为done且未启动频率。科学理由修订endpoint opt为auto（独立freq仍numeric）的ts_resume tc_87c3e5e99c96434b 被 intervention limit exhausted 拒绝；2次干预已用于映射及TS-opt输入修复，不能自行加授权预算。这是流程/预算障碍，不是不存在TS的证据。后续系统已推进[frequency791](../../../../ts/ts_0003/jobs/declaration_0003/frequency/.cloudra/calc-791.out.log)：正常结束、恰一虚频−1597.10 cm⁻¹，E与751一致，模式自动诊断断C-C/O-O aligned（modes向量摘要null，仍需谨慎）。现阻塞转为IRC输入的frequency_mode_without_frequency；需IRC auto及endpoint opt auto，但干预预算2/max2。当前没有经双向IRC及两端0虚频验收的边，不填barrier_kcal_mol，不改原登记accessible。

本轮收口：751已完成，仅待受权维护者修复durable后端推进，才能继续核反应虚频与IRC身份；当前无后台计算，不新增搜索。未验证不证明不存在极小值/鞍点。普通PM7端点Opt/FORCE已成功；剩余缺口是正式PM7 TS/IRC durable后端及scorer格式适配，现有MOPAC日志仍不满足题设ORCA/Gaussian解析要求。安装软件本身不消除这两个独立缺口。
