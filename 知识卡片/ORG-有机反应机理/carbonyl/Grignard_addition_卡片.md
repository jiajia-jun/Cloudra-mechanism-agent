---
id: org:carbonyl:5
title: 格氏试剂对羰基的加成
domain: 有机反应机理与副反应
topic: Grignard addition to carbonyls
cards: 10
---

## 1. 反应概览与历史

格氏试剂（Grignard reagent, RMgX）对醛、酮、酯、酰氯、腈、环氧化物等的亲核加成是有机金属化学奠基反应之一。Victor Grignard 1900 年发现 RMgX 在乙醚中形成，1912 年获诺贝尔奖。RMgX 对醛得仲醇、对酮得叔醇、对酯/酰氯经两次加成得叔醇、对 CO₂ 得羧酸。典型产率：醛/酮 70–95%；酯 60–90%；位阻酮 40–70%。它是 C–C 键形成与醇合成的教科书方法，也是后续 Barbier、Reformatsky 等的参照。综述见 Grignard《Organometallic Chemistry》传统专著与 Clayden 有机金属章。

## 2. 试剂制备与结构

RMgX 由 R–X（Cl/Br/I，活性 Br>I>Cl）与 Mg 粒在无水乙醚或 THF 中氧化插入制备：Mg 插入 C–X 键，Mg 由 0 价变为 +2 价（氧化加成）。乙醚/THF 的氧孤对配位 Mg，形成 R₂Mg·MgX₂·n(solvent) Schlenk 平衡与二聚/缔合物种。反应引发：活化 Mg（I₂、1,2-二溴乙烷、RBr 预处理）、引发剂。官能团容忍差：RMgX 与 OH/NH/SH/COOH/NO₂/羰基本身反应，故底物需保护。对空气与水极端敏感，Schlenk 线/手套箱操作。

## 3. 主机理：对醛酮的加成

① RMgX（实际亲核种常为 R₂Mg 或溶剂解离的 R⁻·MgX⁺ 对）中 R（碳负离子等价物）进攻醛/酮羰基碳，四面体镁配位烷氧负离子中间体（C 由 sp²→sp³，形成 C–C 键与 C–O–Mg）。② 酸性水淬灭（NH₄Cl/H₃O⁺）质子化 O–Mg 得醇。氧化态：R 从碳负离子样到 C–C 成键无形式氧化；Mg 保持 +2。对酯/酰氯：第一当量加成-消除得酮（更活泼），酮再被第二当量 RMgX 加成得叔醇镁盐；控制 1 当量或低温可停在酮（困难）。对腈：R 加成得亚胺镁盐，水解得酮。对环氧化物：R 进攻取代较少碳开环得增加 2 碳的醇镁。

## 4. 金属交换与转移机理细节

实际物种：Schlenk 平衡 2 RMgX ⇌ R₂Mg + MgX₂；R₂Mg 通常更亲核。与卤化锂添加（LiCl，Knochel 预处理）可加速、活化 RMgX（「Turbo Grignard」类）。交叉加成中可能与底物发生卤镁交换或还原副反应（尤其α-卤代酮）。机理多为极性四中心/六中心 TS（金属配位羰基氧降低 LUMO），非自由基为主，但 SET 通道在某些芳酮/位阻体系有证据（痕量颜色、自由基钟）。立体：非螯合底物 Felkin–Anh 加成；α-烷氧基酮经螯合控制（Mg 配位两氧）得螯合产物。

## 5. 关键条件：溶剂、温度与添加物

溶剂：Et₂O（经典、易除去）、THF（溶解更好、更常用于制备）、2-MeTHF（绿色替代）；醚氧配位是 RMgX 稳定必要条件。温度：制备回流引发；加成 −78 °C 至 0 °C 控制选择性与副反应；位阻体系可升温。添加物：LiCl（1:1，Turbo）提升反应性；CeCl₃（Luche 型）促进 1,2-选择于烯酮；Cu 催化剂促 1,4（见副路径）。计量：RMgX 1.0–1.2 equiv；对酯需 2 equiv。后处理：饱和 NH₄Cl 或稀酸；Rieke Mg、Ca/Mg 混金属为变体。无水无氧与新鲜蒸馏醚是成功率关键。

## 6. 底物范围与局限

优秀底物：甲醛→伯醇；其他醛→仲醇；酮→叔醇；CO₂→酸；环氧化物→高一级醇；腈→酮。中等：位阻酮、芳酮（还原偶联竞争）。差：酰胺、叔卤代底物、游离质子性官能团。官能团保护策略：OH→TBS/TBDPS 或 THP；COOH→酯；NH→Boc；C=O→缩酮（对 Grignard 稳定）。局限：官能团耐受窄（相对 organozinc/boron）；对映选择性需手性辅基或手性配体/催化（NuKi/Fu 类进展为 frontier 但仍非默认）；大规模锂代/烷基锂有时更活泼可控。

## 7. 副路径与抑制

① enolization（酸性 α-H 底物被夺质子）：酮/醛烯醇化而非加成 — 抑制：低温、换 organolithium 或 Cerium 盐、位阻匹配。② 还原偶联（Wurtz 型）：R–R 偶联，SET 路径，芳基/卤代杂质催化 — 抑制：高纯 Mg、避免过渡金属污染、控制温度。③ 1,4-共轭加成（烯酮/烯酯）：软化或 Cu 杂质促 — 抑制：CeCl₃/LaCl₃·2LiCl 促 1,2；或故意加 CuI 做 1,4。④ 羰基过度加成/多次加成于酯 — 抑制：低温、1 当量、或换 Weinreb 酰胺停在酮。⑤ 卤代底物上 SN2/Wurtz — 抑制：避免游离仲/伯卤代共存，保护或换偶联方法。⑥ 自由基环丙烷化副产 — 抑制：避光、高纯试剂。

## 8. 选择性控制

chemo：醛>酮>酯活性序列利用；多羰基用缩酮保护选择性加成。regio：环氧化物开环取代少端。stereo：α-手性醛 Felkin–Anh 主产物；螯合底物（α-OMe、β-酮酯）金属配位翻转选择性；环己酮 equatorial/axial 加成受 A^(1,3) 与配位控制。enantio：Evans oxazolidinone + RMgX 的不对称加成；催化不对称 Grignard 加成（手性噁唑啉）是活跃领域（frontier:false 经典，但催化版 frontier:true 倾向）。

## 9. 代表性应用与变体

应用：药物中间体叔/仲醇构建；CO₂ 羧化固定；格氏-酯停酮（Weinreb 改良）；与 Barbier 一锅法（见 Barbier 卡）互补。变体： Barbier 原位；Turbo Grignard（iPrMgCl·LiCl）；Rieke Mg；In/Bi 介导；SmI₂ 还原加成。工业：布洛芬类中间体、香料醇。计算衔接见第 10 节。

## 10. 计算化学衔接

DFT 研究：① RMgX/R₂Mg 对羰基加成 TS（四/六中心，醚配位数影响）；② Felkin–Anh vs 螯合控制的相对能垒；③ SET 与极性路径的交叉（自旋密度分析）。方法：M06-2X 或 ωB97X-D/def2-SVP(TZVP) + SMD(THF)，显式 Mg–O 配位溶剂分子必须保留；Mg 软势/def2 基组即可（非过渡金属）。CeCl₃ 体系可用 YPBE/双杂化做相对趋势。能垒计算配合 Conductor-like 溶剂模型评估醚溶剂效应。相关：method:DFT、concept:过渡态、method:opt=TS。
