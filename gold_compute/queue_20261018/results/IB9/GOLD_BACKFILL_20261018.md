# IB9 E1 Gold 回填记录（2026-10-18）

用户在振动模式复核后确认：“我确定就是这个反应，回填吧”。据此保留IB9，并将首步Gold从历史B3LYP 14.74更新为 **GFN2-xTB 5.65 kcal/mol**。本次为人工确认的方法内参考更新；未修改原生计算证据、频率数目、工具验收状态或评分规则。

## 能量参照

同级别气相GFN2-xTB，ORCA 6.1.1调用外部xTB 6.7.1，整体电荷0、单重态。以下均为原生电子能，不含ZPE/热校正。

|来源|电子能 / Eh|当前用途|
|---|---:|---|
|TS794（日志496行）|-15.181114290760|首步过渡态|
|原料接触体839（日志5211行）|-15.190125627130|沿用当前题面单一接触体参照|
|重氮甲烷742|-8.916818335210|零虚频分离单体|
|乙烯745|-6.271260607550|零虚频分离单体|
|742+745|-15.188078942760|分离原料参照，另列|

使用现有换算常数 627.5094740631 kcal/mol/Eh：

- 当前Gold：`(E_TS794 − E_contact839) × 627.5094740631` = **5.6546989461 → 5.65 kcal/mol**。
- 相对分离原料：`(E_TS794 − E_742 − E_745) × 627.5094740631` = **4.3703851136 → 4.37 kcal/mol**。
- 接触体相对分离原料低 **1.2843138326 kcal/mol**。两个能垒的差别来自参照，未跨方法混减。

当前题面从原料接触体起图，评分实现不把组分能量直接替代该完整接触体能量。本次沿用该参照，没有改变题目定义；分离单体各自零虚频不代表整体接触体零虚频。

## 反应与模式复核

780优化收敛；794恰有一个虚频 **−367.39185 cm⁻¹**。工作序成键C1–C5、C2–N3随该模式同步缩短/伸长，对应题库map成键`[[1,5],[3,4]]`，无需改图或原子映射。工作序前五重原子对应题库map `[5,4,3,2,1]`。原生Hessian模式沿两处距离的相对位移约−0.922357/−0.845353。

798已实际计算双向IRC：F方向16点收敛，B方向20点未本征收敛。F外帧优化/频率821为身份正确的1-吡唑啉，零虚频，最低95.30 cm⁻¹；B外帧经822→833→839保持重氮甲烷+乙烯两组分身份。

839仍有 **−29.78791、−4.49384 cm⁻¹** 两个软虚频。原生模式按乙烯和重氮甲烷分别作刚体运动拟合后，剩余位移平方占比分别约`1.04e-5`、`5.62e-6`；整体刚体拟合的剩余占比则约0.899、0.802。两模主要为组分间相对轴向转动和横向摇摆，内部键长/键角变化很小，与794的两处成键运动不同。保留真实负频，不把它们删除、归零或称整个体系已验证为极小值。用户已接受软模接触端点方案并确认目标反应，此处按人工裁定纳入本题参考。

## 验收边界与本次同步

实际工具返回仍为 `verification_status=inconclusive`、`missing TS geometry`，见[实际验收记录](new_verification_review/ACTUAL_VERIFICATION.json)；本次未改写为pass。可视化用文件由原生Hessian生成，仅供显示，不作为IRC证据。没有新增量化计算。

已同步机器登记、人工题源、正式`IB9.json`及既有题库再生成测试。**IB9_E2能垒仍为null，原有不可达标签不变，全题速控步未定**；E2搜索未成功不作为新的物理不可达证明。xTB方法内参考不代表高等级定量误差已经验证。

## 原生来源与SHA256

路径相对仓库根目录；哈希在本次回填时从原文件读取。未改写任何原日志或几何。

|来源|仓库内路径|SHA256|
|---|---|---|
|TS794 energy / frequency|`ts/ts_0005/jobs/declaration_0006/frequency/.cloudra/calc-794.out.log`|`dacf14b165b8cdedff3ea964a02c541bd0b636891d738f530fa4f8d27f35c2df`|
|TS794 native Hessian|`ts/ts_0005/jobs/declaration_0006/frequency/frequency.hess`|`24d7b5bc5b5345a38e6ac2ad5fb7efc7f86f86eed459e7f928e135cdbf0c8f90`|
|TS794 geometry|`ts/ts_0005/jobs/declaration_0006/frequency/optimized.xyz`|`07c1e8b757ca80fcf8fe6cc98fb83bfc9f11e33ddd709ea3a3af9ac56a0dccb1`|
|TS780 optimization|`ts/ts_0005/jobs/declaration_0006/ts_opt/.cloudra/calc-780.out.log`|`fb6690201d54c46dafa1b9f30bfc8d82ebe832d02a7b05614c651f9f9511c531`|
|IRC798|`ts/ts_0005/jobs/declaration_0006/irc/.cloudra/calc-798.out.log`|`a7d2a66bdf5fc6f3a7fbb50fe005da92d0eb4ea67d8fb7d27055697dc7318ca9`|
|IRC798 F outer frame|`ts/ts_0005/jobs/declaration_0006/irc/irc_IRC_F.xyz`|`41e6448110e0d1a626566cad0684f98c44e79fb8d6b18de0f0bf02ac17c3bc36`|
|IRC798 B outer frame|`ts/ts_0005/jobs/declaration_0006/irc/irc_IRC_B.xyz`|`d981c37f5f2c1208ab0ea0108e77954e0b0b676f1a4b339f87f818b4bb913449`|
|Product821 Opt+Freq|`gold_compute/queue_20261018/results/IB9/independent_endpoints/F/.cloudra/calc-821.out.log`|`cf2ecf8991335f29ff5aaa50778d42e0b96fd3f30b673295aa5da05eb4b0f870`|
|Product821 geometry|`gold_compute/queue_20261018/results/IB9/independent_endpoints/F/optfreq.xyz`|`a6c249290eb14ed9580f1eb756f900eda085e0ef24e5db253dc842bc3c6eb839`|
|Contact839 Opt+Freq|`gold_compute/queue_20261018/results/IB9/hessian_step_review/.cloudra/calc-839.out.log`|`cb4112b3c4354aaf932a6052fdda9349ae9fda032092401fb4b9722ecda6d204`|
|Contact839 native Hessian|`gold_compute/queue_20261018/results/IB9/hessian_step_review/review.hess`|`03614ad863ded1ce410fc227e472be63d6abc8362e57b2f5eb371700d907b20e`|
|Contact839 geometry|`gold_compute/queue_20261018/results/IB9/hessian_step_review/review.xyz`|`0441b7b47d183d0c53194ba1c13f015ee25089fa798a0c1f92cd48daace78692`|
|CH2N2 742 Opt+Freq|`gold_compute/queue_20261018/results/IB9/calc/frag_ch2n2/.cloudra/calc-742.out.log`|`b3ba81fdf3b6e059515e96d26653c942f9d1e5e5957eda62797cf30749dcff04`|
|C2H4 745 Opt+Freq|`gold_compute/queue_20261018/results/IB9/calc/frag_c2h4/.cloudra/calc-745.out.log`|`ee211f1426500477ad0cbd0ab6954f46b0e82e610b1eacefd8ef4b541629e4c3`|
