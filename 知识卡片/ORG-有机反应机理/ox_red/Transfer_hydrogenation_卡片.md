---
id: org:ox_red:9
title: 转移氢化
domain: 有机反应机理与副反应
topic: Transfer hydrogenation
cards: 9
---

## 1. 反应概览
转移氢化（TH）不用高压 H2，而用有机氢源：经典 MPV 还原（Meerwein–Ponndorf–Verley：异丙醇/Al(OiPr)3，Oppenauer 为其逆反应）与 Noyori 不对称转移氢化（Ru-手性二胺 + HCO2H/Et3N）。酮→醇产率 80–98%，Noyori 体系 ee 常 >95%。优点：设备简单、氢源易得、化学选择性好（C=C 常保留）。

## 2. 主机理链：MPV 六元环 TS
铝醇盐与异丙醇交换得 Al-OiPr，酮与铝配位后经六元环过渡态把异丙醇的 C-H 作为氢负转移到羰基碳，同时异丙酮生成并被蒸除/共沸移走，推动平衡完全。机理为分子内协同氢负转移，无自由基。

## 3. 主机理链：Noyori 外层协同
Ru(II)-TsDPEN（对甲磺酰基手性二胺）在碱活化下生成 18 电子 Ru-H/N-H 物种；酮不配位金属，而是通过六元环状 TS 由 Ru-H 供氢负、N-H 供质子协同还原 C=O——「金属-配体协同外层机理」。手性来自二胺骨架与 Ru 环境的底物取向。

## 4. 主机理链：甲酸脱羧驱动
HCO2H/Et3N（常用 5:2 共沸物）作为氢源：Ru 催化甲酸脱氢/脱羧为 CO2，热力学不可逆，驱动不对称还原。pH 与水含量显著影响速率；MeOH 溶剂常用。

## 5. 关键条件与试剂选择
- MPV：Al(OiPr)3 催化（或化学计量），回流 iPrOH，除丙酮。
- Noyori：RuCl(p-cymene)Cl 二聚体 + TsDPEN + KOtBu（约 4 mol%）于 HCO2H/Et3N/MeOH，室温。
- 气氛：N2；O2 毒化 Ru。
- 变体：手性二胺的磺酰基电子效应调 ee 与速率；水/添加剂微调。

## 6. 底物范围与局限
MPV：醛快、酮慢、位阻酮需苛刻条件；C=C 不动（与催化氢化的关键差别）。Noyori：芳基烷基酮 ee 最好；二芳基酮中等；脂肪酮挑战大。局限：① 底物若含酸性质子干扰；② 碱敏底物；③ 催化剂对硫毒化敏感。

## 7. 副路径与抑制策略
- 转化不完全（位阻酮 MPV）：抑制——Noyori 体系、除丙酮、延时。
- 碱致消除/差向异构：抑制——降碱、降温、快速后处理；选无 α-H 底物位点。
- 竞争 Meerwein 类脱氢（Oppenauer 氧化误用）：氢源/受体比例错误时发生醇氧化——保持异丙醇大大过量。
- 水解 Ru 二聚体失活：无水操作与新鲜配制。

## 8. 选择性控制
chemo：C=O 优先，C=C/C≡C 保留（适合合成手性烯丙醇）。enantio：Noyori 模型预测——酮大基团/小基团与 TsDPEN 芳环的立体匹配；(R,R)-或(S,S)-配体给相反构型。MPV 变体（手性 Al/Borane）ee 有限。

## 9. 与计算化学的衔接
Noyori 外层 TS 是机理计算教科书案例：DFT 优化六元环 TS、比较 Re/Si 面 ΔΔG‡ 与实验 ee 的 Boltzmann 换算；甲酸脱羧循环的决骤步与 pH 依赖可用 pKa/自由度分析。MPV 六元环 TS 的椅式/船式构象搜索也常规。推荐：dispersion-corrected hybrid 泛函、SMD(MeOH)、标准态从 1 M 校正到实验浓度。选择性模型误差 1 kcal/mol 即对应 ~80% ee 偏差，需报告误差棒。
