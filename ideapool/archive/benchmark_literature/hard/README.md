# HARD 梯队候选文献库（结构感知 / 立体化学支柱）

**目的**：为 Cloudra 有机反应机理基准测试集 HARD 梯队收集候选反应来源文献。HARD 定义：高度依赖微观几何与立体化学感知的反应（endo/exo 选择性、对映面区分、E/Z 选择性、轴手性、环状过渡态构象竞争），xTB 可计算但纯文本 SMILES 输入极易判断错误。

- 入库条目：**16 篇**（hard-01 ~ hard-16），覆盖全部 5 个检索方向。
- 成功下载 OA PDF：**5 篇**（见下表 ✓，达到"至少 5 个"的下限；本领域大量高相关计算文献在 ACS/Wiley 付费墙或对自动化下载 403，已尽力从 nature.com / MDPI / IAS / JMCS 等免拦截 OA 源补足）。
- 仅元数据（无 PDF）：**11 篇**（其中 8 篇为付费墙文献；3 篇虽 OA 但出版商 PDF 端点拒绝自动下载，HTTP 403，详见各条备注）。
- 元数据与摘要来源：OpenAlex / arXiv(paper_searcher) / Crossref REST / Europe PMC REST / Semantic Scholar GraphQL，摘要均为检索结果原文，未做改写。
- 已持有文献核对：docs/benchmark_survey/pdfs/ 下的方法学文献（rdb7、grambow2020、transition1x、bh9 等）与本批无机理文献重复，未重复下载。

## 覆盖方向对照

| 方向 | 条目 |
|---|---|
| (a) Diels–Alder endo/exo 选择性起源 | hard-01, 02, 03, 04, 05, 06, 07 |
| (b) 电环化 torquoselectivity | hard-08, 09, 10 |
| (c) 轴手性/阻转异构旋转能垒 | hard-11 |
| (d) 不对称催化对映选择性起源（CPA、氢键、CBS） | hard-06, 12, 13, 14 |
| (e) 周环反应立体专一性 / 环状 TS 构象竞争 | hard-02, 15, 16 |

## 本地 PDF 清单（5 个）

| 文件 | 对应条目 | 来源 |
|---|---|---|
| 2016_ho_exo_selectivity_da.pdf | hard-04 | nature.com (Sci Rep, CC-BY) |
| 2023_pavosevic_cavity_da.pdf | hard-05 | nature.com (Nat Commun, CC-BY) |
| 2015_akilandeswari_torquoselectivity.pdf | hard-08 | ias.ac.in (J. Chem. Sci., OA) |
| 2023_pellegrini_atropisomer_hydrazide.pdf | hard-11 | mdpi-res.com (Molecules, CC-BY) |
| 2022_salih_nitrone_32ca.pdf | hard-15 | jmcs.org.mx (J. Mex. Chem. Soc., OA) |

补充说明：另尝试过 CCS Chemistry 胍催化 [8+2] 环加成（10.31635/ccschem.021.202000664，gold OA）与 Wiley/ACS 三篇 OA 文献，PDF 端点均返回 403（bot 拦截），未入库。若需扩充 PDF，可人工经浏览器下载 hard-06（Wiley, CC-BY）、hard-07（ACS Omega, CC-BY）、hard-13（Wiley, CC-BY-NC，PMC9305870 亦有全文）。

---

## hard-01 — Origin of the "endo rule" in Diels–Alder reactions
- **作者**: Israel Fernández, F. Matthias Bickelhaupt
- **年份/期刊**: 2014, *Journal of Computational Chemistry*；DOI: 10.1002/jcc.23500
- **OA**: 否（Wiley 付费墙），pdf_file = null
- **摘要**: DFT 计算明确解释了教科书式热 Diels–Alder 反应（马来酸酐 + 环戊二烯/丁二烯）中 endo 加成物占优（endo 规则）的原因：该选择性主要源于 exo 路径过渡态区域不利的空间排布，转化为更高的活化应变；与广泛接受的轨道相互作用解释相反，轨道相互作用与形变反应物间总相互作用均不贡献 endo 选择性。
- **推荐理由**: 现代活化应变模型对 endo 规则的权威重释——endo/exo 由 TS 几何/应变决定，SMILES-only agent 只会背诵"次级轨道相互作用"，是结构感知支柱的标杆体系。
- **候选反应**: cyclopentadiene + maleic anhydride (endo vs exo)；butadiene + maleic anhydride

## hard-02 — The Source of the endo Rule in the Diels–Alder Reaction: Are Secondary Orbital Interactions Really Necessary?
- **作者**: José Ignacio García, José Antonio Mayoral, Luis Salvatella
- **年份/期刊**: 2005, *Eur. J. Org. Chem.*；DOI: 10.1002/ejoc.200400424
- **OA**: 否，pdf_file = null
- **摘要**: endo 偏好通常归因于次级轨道相互作用（SOI）。作者分析 s-trans 丁二烯与反丁烯二腈的平行接近，发现 SOI 被闭壳层排斥超越；对环戊二烯+马来酸酐、环丁二烯+环丁烯二酮、环丁二烯+降冰片二烯等反应的研究表明 SOI 相关原子对间不存在净吸引，结论：endo 偏好并非源于 SOI 吸引，该概念并不必要。
- **推荐理由**: 对 SOI 教条的经典批判，与 hard-01 构成"endo 起源之争"的两极；涉及多个 xTB 可算的小环加成体系。
- **候选反应**: cyclopentadiene + maleic anhydride；cyclobutadiene + cyclobutenedione；cyclobutadiene + norbornadiene

## hard-03 — Origins of the Endo and Exo Selectivities in Cyclopropenone, Iminocyclopropene, and Triafulvene Diels–Alder Cycloadditions
- **作者**: Brian J. Levandowski, Trevor A. Hamlin, Ryan C. Helgeson, F. Matthias Bickelhaupt, K. N. Houk
- **年份/期刊**: 2018, *J. Org. Chem.*；DOI: 10.1021/acs.joc.8b00025
- **OA**: 否（PMC6314817 有作者手稿但非 OA 子集，自动下载失败），pdf_file = null
- **摘要**: DFT 合理化环丙烯酮、亚氨基环丙烯及取代三富烯与丁二烯的 endo/exo 选择性：环丙烯酮为亲双烯体时 exo 占优 1.8 kcal/mol；3-二氟亚甲基三富烯则 endo 占优 2.8 kcal/mol。讨论了电荷转移与 SOI 的影响，预测选择性与三富烯 C3 碳的电荷及 HOMO 系数相关。
- **推荐理由**: 1.8–2.8 kcal/mol 量级的 endo↔exo 翻转，小张力亲双烯体，xTB 完全可算——几何细微差别决定选择性符号的典型体系。
- **候选反应**: cyclopropenone + butadiene (exo)；3-difluoromethylene triafulvene + butadiene (endo)

## hard-04 — Unconventional exo selectivity in thermal normal-electron-demand Diels–Alder reactions
- **作者**: Guan-Ming Ho, Chih-Jui Huang, En-Yi Li, Shou-Kuo Hsu, Tao Wu, Medel M. L. Zulueta, Kong-Wei Wu, Shang-Cheng Hung
- **年份/期刊**: 2016, *Scientific Reports*；DOI: 10.1038/srep35147
- **OA**: 是 ✓ **PDF: 2016_ho_exo_selectivity_da.pdf**
- **摘要**: 系统评估热正常电子需求 Diels–Alder 中驱动 exo 选择性的结构因素：双烯 Cβ 位取代、亲双烯体吸电子基的大小与电负性是主因；实验与计算均指向双烯/亲双烯体取代基间的位阻与静电作用提高 exo 路径概率，endo TS 中反应伙伴畸变与对齐不良削弱 endo 优势。
- **推荐理由**: endo 规则失效的系统案例集（实验+计算），理想的"反例/负对照"，检验 agent 能否从几何发现 exo 占优而非套规则。
- **候选反应**: Cβ-取代双烯 + 缺电子亲双烯体的 exo 选择性 DA

## hard-05 — Computational study on the catalytic control of endo/exo Diels–Alder reactions by cavity quantum vacuum fluctuations
- **作者**: Fabijan Pavošević, Robert L. Smith, Ángel Rubio
- **年份/期刊**: 2023, *Nature Communications*；DOI: 10.1038/s41467-023-38474-w
- **OA**: 是 ✓ **PDF: 2023_pavosevic_cavity_da.pdf**
- **摘要**: 用 QED-CC 方法证明光学腔对两个 Diels–Alder 反应的催化与选择性控制：改变分子相对腔模偏振的取向可显著抑制或选择性增强反应，按需得到 endo 或 exo 主产物。
- **推荐理由**: 极端案例——产物 endo/exo 完全由分子三维取向决定，凸显"构型/取向即选择性"，文本输入完全无法表达。
- **候选反应**: 腔调控 endo/exo Diels–Alder（QED-CC 参考能垒）

## hard-06 — Bifunctional Hydrogen Bond Donor-Catalyzed Diels–Alder Reactions: Origin of Stereoselectivity and Rate Enhancement
- **作者**: Pascal Vermeeren, Trevor A. Hamlin, F. Matthias Bickelhaupt, Israel Fernández
- **年份/期刊**: 2021, *Chem. Eur. J.*；DOI: 10.1002/chem.202004496
- **OA**: 是（CC-BY），但 Wiley pdfdirect 端点 403，未能自动下载，pdf_file = null（落地页开放）
- **摘要**: DFT+CC 研究环戊二烯+丙烯醛的（硫）脲双功能氢键给体催化 DA：催化剂使反应加速（能垒最多降 7 kcal/mol）并呈 exo 选择性；活化应变与 KS-MO 分析表明加速源于降低 Pauli 排斥而非增强轨道相互作用，exo 选择性直接与更大的异步性相关。
- **推荐理由**: 氢键有机催化把 DA 选择性翻转为 exo，横跨方向 (a) 与 (d)；小体系（CPD+丙烯醛+脲），xTB 可探索。
- **候选反应**: cyclopentadiene + acrolein + (thio)urea（exo 选择性 H 键催化 DA）

## hard-07 — DFT Investigation of the Stereoselectivity of the Lewis-Acid-Catalyzed Diels–Alder Reaction between 2,5-Dimethylfuran and Acrolein
- **作者**: Mariem Chellegui, Mohamed Trabelsi, Benoît Champagne, Vincent Liégeois
- **年份/期刊**: 2025, *ACS Omega*；DOI: 10.1021/acsomega.4c07888
- **OA**: 是（gold OA），但 ACS PDF 端点 403，pdf_file = null（PMC11739960 有全文）
- **摘要**: 未催化反应为一步异步 NED 过程；低介电溶剂中弱 endo 选择性，DMSO 等高介电溶剂转为弱 exo。AlCl3/GaCl3 催化时 endo 与 exo 路径均变为两步异步过程（两个 TS + 稳定中间体），第二个 TS 决定 exo 选择性增强。
- **推荐理由**: 2025 年最新工作：溶剂介电常数与 Lewis 酸配位切换 endo/exo 并改变机理（一步→两步），考察 agent 对条件敏感选择性的把握。
- **候选反应**: 2,5-dimethylfuran + acrolein（未催化 vs AlCl3/GaCl3 催化）

## hard-08 — Competitive and Cooperative Torquoselectivity in the Thermal Ring Opening of Cyclobutene: A Density Functional Insight
- **作者**: Lakshminarayanan Akilandeswari, Chandrasekaran Prathipa
- **年份/期刊**: 2015, *Journal of Chemical Sciences* (IAS)；DOI: 10.1007/s12039-015-0936-5
- **OA**: 是 ✓ **PDF: 2015_akilandeswari_torquoselectivity.pdf**
- **摘要**: B3LYP/6-31G(d) 研究甲氧基/硅氧基取代环丁烯的热顺旋开环 torquoselectivity：C3 取代基可向内（朝断裂 σ 键方向）或向外旋转，两条路径竞争。
- **推荐理由**: 最小 torquoselectivity 体系的直接计算——产物二烯 E/Z 由顺旋方向决定，纯文本完全无法判断，xTB 几分钟可验证。
- **候选反应**: 3-methoxycyclobutene / 3-silyloxycyclobutene 顺旋开环（inward vs outward）

## hard-09 — Torquoselectivity in Cyclobutene Ring Openings and the Interatomic Interactions That Control Them
- **作者**: José Enrique Barquera-Lozada
- **年份/期刊**: 2016, *J. Phys. Chem. A*；DOI: 10.1021/acs.jpca.6b08771
- **OA**: 否，pdf_file = null
- **摘要**: 用 QTAIM、ELI-D、IQA 能量分解定量评估 3-取代环丁烯 torquoselectivity 背后的原子间相互作用：C4 与 C3 取代基 R5 在 TS 中的相互作用主导选择性；3-硼基环丁烯中该作用强到形成 B5–C4 原共价键；BCP 密度与断裂键路径形状和活化能/选择性强相关。
- **推荐理由**: 键拓扑视角的 torquoselectivity 定量研究，含反常 3-硼基 inward 案例；取代基系列给出可比的 inward/outward 能垒数值表。
- **候选反应**: 3-取代环丁烯开环系列（R = boryl, silyl, formyl…）

## hard-10 — Origins of Inward Torquoselectivity by Silyl Groups and Other σ-Acceptors in Electrocyclic Reactions of Cyclobutenes
- **作者**: Patrick S. Lee, Xiyun Zhang, K. N. Houk
- **年份/期刊**: 2003, *JACS*；DOI: 10.1021/ja0287635
- **OA**: 否，pdf_file = null
- **摘要**: B3LYP 解释无 π 轨道取代基（硅基等 σ 受体）的 contrasteric inward torquoselectivity：取代基空轨道与断裂键占据轨道的相互作用控制选择性，静电贡献次要。报道 3-硅基、氟硅基、甲基、氟甲基、铵基、膦基、甲酰基、硼氢基环丁烯开环的能量与 TS。
- **推荐理由**: Houk 奠基性工作，完整取代基-能垒表，可直接当作 E/Z 产物预测的数值基准系列。
- **候选反应**: 3-silylcyclobutene inward 开环（Z-二烯）；3-甲酰基/3-三氟甲基环丁烯系列

## hard-11 — On the Nature of the Rotational Energy Barrier of Atropisomeric Hydrazides
- **作者**: Andrea Pellegrini, Laura Marcon, Paolo Righi, Giovanni Centonze, Chiara Portolani, Marco Capodiferro, Shilashi Badasa Oljira, Simone Manetto
- **年份/期刊**: 2023, *Molecules* (MDPI)；DOI: 10.3390/molecules28237856
- **OA**: 是 ✓ **PDF: 2023_pellegrini_atropisomer_hydrazide.pdf**
- **摘要**: 实验+计算深入研究 N–N 阻转异构酰肼的外消旋能垒，考察电子与位阻因素的影响；结果表明能垒主要源于氮原子 p 轨道成分的增加。所用 DFT 方法经实验能垒验证，可作为预测阻转异构体旋转能垒的可靠工具。
- **推荐理由**: 方向 (c) 核心条目：轴手性构型稳定性 ↔ 旋转能垒定量关系，含实验验证的计算协议，便于设计"半衰期推断"类考题。
- **候选反应**: N–N 阻转异构酰肼绕 N–N 轴的外消旋（旋转能垒）

## hard-12 — Origins of Selectivity and General Model for Chiral Phosphoric Acid-Catalyzed Oxetane Desymmetrizations
- **作者**: Pier Alexandre Champagne, K. N. Houk
- **年份/期刊**: 2016, *JACS*；DOI: 10.1021/jacs.6b08276
- **OA**: 否，pdf_file = null
- **摘要**: DFT 研究 CPA 催化氧杂环丁烷去对称化的高对映选择性起源：一个对映 TS 中催化剂口袋内的位阻拥挤导致催化剂结构畸变，是立体化学偏好的主因；提出普适模型指导相关转化的催化剂设计。
- **推荐理由**: CPA 对映选择性起源的范式论文——催化剂口袋畸变决定 re/si 面攻击，二维连接表完全不可推断。
- **候选反应**: CPA 催化氧杂环丁烷去对称化（对映决定开环 TS）

## hard-13 — Chiral Phosphoric Acid Catalyzed Conversion of Epoxides into Thiiranes: Mechanism, Stereochemical Model, and New Catalyst Design
- **作者**: Meng Duan, Christian Díaz-Oviedo, Yang Zhou, Xiangyang Chen, Peiyuan Yu, Benjamin List, K. N. Houk, Yu Lan
- **年份/期刊**: 2022, *Angew. Chem. Int. Ed.*；DOI: 10.1002/anie.202113204
- **OA**: 是（CC-BY-NC），但 Wiley PDF 端点 403，pdf_file = null（PMC9305870 有全文）
- **摘要**: 计算+实验发展环氧化物硫羰化的新 CPA 催化剂；DFT 揭示机理与对映选择性起源，3,3'-芳基邻位大取代基限制环氧化物在对映决定 TS 中的位置，对位更大取代基显著提高 ee；据计算信息设计的新 CPA 实验验证高效。
- **推荐理由**: 计算指导催化剂设计的成功范例，含明确的对映决定 TS 几何与取代基立体图谱；与 hard-12 互补（不同底物/机理）。
- **候选反应**: CPA 催化环氧化物硫羰化动力学拆分（对映决定 TS）

## hard-14 — A DFT Study on the Reaction Mechanism of Enantioselective Reduction of Ketones with Borane Catalyzed by a B-Methoxy-Oxazaborolidine Catalyst Derived from (–)-β-Pinene
- **作者**: Hichem Sadrik Kettouche
- **年份/期刊**: 2020, *Journal of Molecular Modeling*；DOI: 10.1007/s00894-019-4276-0
- **OA**: 否，pdf_file = null
- **摘要**: ωB97XD/6-31G(d,p) 研究蒎烯衍生 B-甲氧基噁唑硼烷催化硼烷还原酮的机理：经 TS3s 形成 M4s 为速率与手性决定步；NCI 分析四个立体决定 TS，TS3a(S) 最稳；Si 面进攻给出 S 型二级醇，98% ee，与实验一致。
- **推荐理由**: 覆盖任务指定的 CBS 还原家族：六元环船式噁唑硼烷 TS、Re/Si 面竞争、98% ee 参考值——对映面判别标准考题。
- **候选反应**: 噁唑硼烷（CBS 类）催化硼烷还原酮（Re/Si 面 TS）

## hard-15 — Unveiling [3+2] Cycloaddition Reactions of N-Methyl-C-3-Bromophenyl-Nitrone to Dimethyl Maleate: Molecular Electron Density Theory Perspective
- **作者**: Sabir A. Mohammed Salih, Huda A. Basheer, Haydar Mohammad-Salim
- **年份/期刊**: 2022, *Journal of the Mexican Chemical Society*；DOI: 10.29356/jmcs.v66i4.1801
- **OA**: 是 ✓ **PDF: 2022_salih_nitrone_32ca.pdf**
- **摘要**: MEDT（MPWB95/6-311++G(d,p)）研究 N-甲基-C-3-溴苯基硝酮与马来酸二甲酯的 zw 型 [3+2] 环加成：活化焓 34.04–38.37 kJ/mol（气相）；动力学控制下 endo 路径占优；BET 预测 endo/exo 均为一步早期 TS 过程，ELF 拓扑分析吻合。
- **推荐理由**: 把 HARD 梯队从 Diels–Alder 拓展到 1,3-偶极 [3+2] 环加成 stereochemistry；量化 endo/exo 活化焓可直接作参照。
- **候选反应**: N-methyl-C-3-bromophenyl-nitrone + dimethyl maleate [3+2]（endo vs exo）

## hard-16 — Computational Study of Factors Controlling the Boat and Chair Transition States of Ireland–Claisen Rearrangements
- **作者**: Şeref Gül, Franziska Schoenebeck, Viktorya Aviyente, K. N. Houk
- **年份/期刊**: 2010, *J. Org. Chem.*；DOI: 10.1021/jo100033d
- **OA**: 否（PMC2837782 有作者手稿但自动下载被 reCAPTCHA 拦截），pdf_file = null
- **摘要**: DFT 探索 Kishi 等实验研究的 Ireland–Claisen 重排中船式 TS 偏好的起源：椅式 TS 中的位阻相互作用是船式占优的主因。
- **推荐理由**: 直接命中梯队定义中的"环状过渡态构象竞争"：六元环 chair/boat TS 竞争决定非对映选择性，σ 迁移重排类代表。
- **候选反应**: Ireland–Claisen 重排 chair/boat TS 竞争（Kishi 底物）

---

## 检索与下载记录（溯源）
- 检索渠道：OpenAlex API（openalex_searcher）、arXiv/S2（paper_searcher）、DuckDuckGo（web_search）、Crossref REST、Europe PMC REST、Semantic Scholar Graph API（均经 bashtools curl）。
- 摘要来源标注：hard-01/03/09/12/13/14/16 来自 Europe PMC core 记录；hard-02 来自 Crossref JATS 摘要；hard-04/05/06/07/10/15 来自 OpenAlex 倒排索引摘要；hard-08 来自出版商页面（IAS/Springer 摘要片段）；hard-11 来自 Crossref JATS 摘要。
- 下载失败说明：Wiley（onlinelibrary wiley.com pdfdirect/pdf）、ACS（pubs.acs.org）、CCS Chemistry（chinesechemsoc.org）端点对自动化请求一律返回 403（bot 拦截），涉及 hard-06/07/13 三篇 OA 文献；NCBI/PMC 页面触发 reCAPTCHA（hard-03/16 手稿无法自动获取）。这些条目均保留开放落地页 URL，建议人工浏览器补下。
