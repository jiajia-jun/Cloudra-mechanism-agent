---
id: org:carbonyl:8
title: Henry 反应（硝基醛醇反应）
domain: 有机反应机理与副反应
topic: Henry reaction (nitroaldol)
cards: 9
---

## 1. 反应概览与历史

Henry 反应（nitroaldol reaction）是硝基烷烃（α-H 酸性，pKa≈10）在碱性条件下生成硝基烯醇负离子，对醛/酮亲核加成得 β-硝基醇的反应。1895 年 Louis Henry 报道。β-硝基醇可脱水成硝基烯（Henry condensation）、还原成 1,2-氨基醇、或经 Nef 反应转羰基，是多官能团合成枢纽。典型产率：芳醛 70–95%；脂肪醛 50–85%；酮 30–60%。综述见 Henry 原始文献与含硝基化学综述（如 Ballini 等方向）。

## 2. 主机理

① 碱夺取硝基烷 α-H（酸性强，弱碱如胺/碱金属醇盐/氟化物即可），生成硝基烯醇负离子（负电荷离域在 C 与 N⁺–O⁻，nitronate）。② nitronate C 进攻醛/酮羰基碳，生成 β-硝基醇盐（C–C 键形成；sp²→sp³）。③ 水/酸淬灭得 β-硝基醇。酸催化路径：硝基烷互变异构为 nitronic acid 后加成质子化羰基（少用）。脱水：β-硝基醇在酸/碱/脱水剂（Ac₂O、MsCl/碱）下 E1cb 消除得 β-硝基烯（共轭稳定）。氧化态：硝基 N 保持 +3；碳无氧化还原。可逆性：nitroaldol 可逆（retro-nitroaldol），平衡常数中等。

## 3. 关键条件：碱与溶剂

碱：弱到中强即可——NaOH/KOH（水/醇，催化量）、Et₃N/DBU、TBAF（氟离子催化，对碱敏底物）、负载碱（Mg/Al 水滑石、Amberlite IRA-400 有机碱树脂）、手性胺（不对称 Henry）。溶剂：MeOH/EtOH/H₂O、THF、DCM；水相绿色条件可用。计量：催化碱即可（产物 nitroaldol 不像 aldol 那样强扣碱）；强碱过量促脱水/聚合。温度：0 °C 至 rt 控选择性；加热促脱水。不对称：手性 Cu/BOX、胍、金鸡纳碱衍生物催化，er 90–99%（frontier:true 不对称 nitroaldol 仍活跃）。无特殊无水要求（水相可用），但脱水步骤需除水。

## 4. 底物范围与局限

硝基甲烷（得 β-硝基伯醇单元）、硝基乙烷、2-硝基丙烷（叔碳产物位阻大）。醛：芳醛优秀、脂醛中等、α,β-不饱和醛可 1,2（Henry）或 1,4（Michael-nitro）竞争。酮：活性低，需活化酮或 Lewis 酸催化。局限：硝基烷自身聚合；多硝基底物过酸易爆炸风险（工艺安全）；脂肪硝基化合物分离纯化有时困难。产物转化价值高：β-硝基醇 → 脱水硝基烯 → Michael/环加成；还原 → 1,2-氨基醇（鞘氨醇类）。

## 5. 副路径与抑制

① 脱水成硝基烯（Henry condensation）：酸/热/脱水剂 — 若需 β-硝基醇：低温、中性后处理、避免加热；若需硝基烯：故意加脱水剂。② 逆 nitroaldol：碱性可逆 — 抑制：短时、温和碱、及时衍生化。③ Michael 加成竞争（烯醛）：nitronate 对 C=C 1,4 — 抑制：低温、硬 Lewis 酸促进 1,2、选饱和醛。④ 聚合/多聚：碱性下醛/nitronate 多聚 — 抑制：稀溶液、慢加醛、弱碱催化。⑤ Nef 副反应/氧化：强碱长时间 — 控制时间与碱当量。⑥ nitroalkane 自缩合：控制硝基烷过量或当量匹配。

## 6. 选择性控制

chemo：多羰基底物醛选择性；与 aldol 共存时 nitroalkane 更易去质子（pKa 低）可化学选择 Henry。regio：硝基烷不对称 α 位需动力学控制（单 α-H 硝基烷无问题）。stereo：β-硝基醇 1,2-立体；手性催化 Cu/BOX 或有机催化剂高 er。不对称 Henry 是构建 β-氨基醇/硝基烯前体的核心方法之一。脱水硝基烯几何：E-常为主（热力学）。

## 7. 代表性应用

鞘氨醇/植物鞘氨醇（1,2-氨基醇）；β-内酰胺前体；硝基烯作为多米诺/Michael 受体构建复杂骨架；糖化学硝基 C-糖苷。工业：胺类中间体。与 Mannich/硝基 Mannich 变体（aza-Henry）关联：nitronate 对亚胺加成得 β-硝基胺。

## 8. 与相关反应网络

Henry 是「硝基化学」枢纽：nitronate 也可做金属催化烯丙基化（Trost）、芳构化。aza-Henry（nitro-Mannich）：亚胺+硝基烷→β-硝基胺，机理同 Henry 但亲电体为 C=N。计算与机理卡末节见下。

## 9. 计算化学衔接

DFT 研究：① nitronate 几何（syn/anti nitronate）与醛加成 TS；② 可逆性（retro 能垒低）与脱水 E1cb 能垒；③ 手性催化剂口袋的双功能活化（胺+金属）。方法：ωB97X-D/def2-SVP+SMD(MeOH)，硝基偶极需极性溶剂模型；催化不对称体系用全催化剂模型+构象采样。相关：method:DFT、concept:过渡态、method:opt=TS。
