# NORMAL 梯队候选文献库（有机机理：多步 / 竞争路径）

收集日期：2026-08-24。共 12 篇候选文献（7 篇已下载 OA PDF，5 篇付费墙仅元数据）。
所有 PDF 已通过 `file` 命令校验为真实 PDF（非 HTML 错误页）。

## OA 状态说明
- 本领域经典机理论文（JACS/JOC 等）多为付费墙；MDPI《Molecules》与 arXiv 预印本提供了充足的 OA 来源，故 OA 比例（7/12）已达标（≥5）。
- 付费墙条目仅记录元数据 + 摘要 + 落地页，未尝试绕过付费墙。

---

## normal-01
- **标题**: Mechanism of the Morita-Baylis-Hillman Reaction: A Computational Investigation
- **作者**: Raphael Robiette, Varinder K. Aggarwal, Jeremy N. Harvey
- **年份/期刊**: 2007, J. Am. Chem. Soc. (129, 15513-15525)
- **DOI**: 10.1021/ja0717865
- **URL**: https://doi.org/10.1021/ja0717865
- **OA**: closed（仅元数据）
- **摘要**: Accurate calculations are presented on the mechanism of the MBH reaction, focusing on the reaction between methyl acrylate and benzaldehyde, catalyzed by a tertiary amine. We address the mechanism under protic solvent-free conditions, but also consider how the mechanism and rate-limiting step change in the presence of alcohols. DFT calibrated against G3MP2; solvent as dielectric continuum. Without protic solvent, alpha-deprotonation is rate-determining via a cyclic TS with proton transfer to a hemiacetal alkoxide (formed from a second aldehyde equivalent) — the McQuade mechanism explaining second-order kinetics in aldehyde. In methanol, a slightly lower-energy pathway has the alcohol shuttle the proton from carbon to oxygen; overall barrier 24.6 kcal/mol (B3LYP). The amine-acrylate betaine addition TS is much lower (16.0 kcal/mol), so C-C bond formation is not rate-limiting except perhaps for aliphatic aldehydes or imines.
- **推荐理由**: MBH 是机理争议的经典案例（决速步曾被长期误判）；文中比较多条质子转移通道并给出定量能垒，适合考察 Agent 提出并淘汰竞争性假设。
- **候选反应**: DABCO 催化 methyl acrylate + benzaldehyde 的 MBH 反应；MeOH 穿梭 vs 第二分子醛穿梭的质子转移竞争。

## normal-02
- **标题**: Dissection of the Mechanism of the Wittig Reaction
- **作者**: Paola Farfan, Sara Gomez, Albeiro Restrepo
- **年份/期刊**: 2019, J. Org. Chem. (84, 14644-14658)
- **DOI**: 10.1021/acs.joc.9b02224
- **URL**: https://doi.org/10.1021/acs.joc.9b02224
- **OA**: closed（仅元数据）
- **摘要**: QTAIM/NBO 等多种成键演化描述符一致表明：无盐 Wittig 反应中，无论叶立德性质、过渡态性质与取代基位置如何，oxaphosphetane 形成步过渡态处新 C-C 键的形成程度与最终烯烃立体化学紧密相关。羰基氧孤对电子向叶立德 P=C 反键轨道的远程弱相互作用（nO -> pi*(P=C)）将 P=C 与 C=O 锁定在形成 oxaphosphetane 所需的位置，解释了为何生成环状中间体而非 betaine。Wittig 反应每一步都是高度异步过程。
- **推荐理由**: Wittig 机理（betaine vs oxaphosphetane、[2+2] vs 分步）是经典争议；多步剖面完整，中等大小含磷体系 xTB 可算。
- **候选反应**: 无盐 Wittig 反应（叶立德 + 醛）；oxaphosphetane 形成 vs betaine 路径；oxaphosphetane 环消除。

## normal-03
- **标题**: A Close Look to the Oxaphosphetane Formation along the Wittig Reaction: A [2+2] Cycloaddition?
- **作者**: E. Chamorro, Mario Duque-Norena, Nestor Gutierrez-Sanchez, Elizabeth Rincon, Luis R. Domingo
- **年份/期刊**: 2020, J. Org. Chem.
- **DOI**: 10.1021/acs.joc.0c00697
- **URL**: https://doi.org/10.1021/acs.joc.0c00697
- **OA**: closed（仅元数据）
- **摘要**: 研究三苯基膦亚甲基叶立德与苯甲醛的 Wittig 反应。键合演化理论（BET）拓扑分析表明 oxaphosphetane 形成的单一动力学步骤含两个电子阶段：先在 C-C 距离 2.02 A 处形成 C-C 键（过渡态区），再在 P-O 距离 2.06 A 处由羰基氧非键区向磷供电子形成 P-O 键（路径末端）。表明 OPA 形成应理解为"两阶段一步"机理，而非传统公认的 [2+2] 环加成。
- **推荐理由**: 直接挑战教科书 [2+2] 环加成图景的机理翻案论文，与 normal-02 互补，是"协同 vs 分步"对比的理想素材。
- **候选反应**: Ph3P=CH2 + 苯甲醛的 Wittig 反应；oxaphosphetane 形成：协同 [2+2] vs 两阶段一步。

## normal-04
- **标题**: Can the Radical Channel Contribute to the Catalytic Cycle of N-Heterocyclic Carbene in Benzoin Condensation?
- **作者**: Ming-Hsiu Hsieh, Gou-Tao Huang, Jen-Shiang K. Yu
- **年份/期刊**: 2018, J. Org. Chem. (83, 15202-15209)
- **DOI**: 10.1021/acs.joc.8b02483
- **URL**: https://doi.org/10.1021/acs.joc.8b02483
- **OA**: closed（仅元数据）
- **摘要**: NHC 经 Breslow 中间体催化苯偶姻缩合；EPR 已证实自由基物种存在但催化角色不明。DFT 比较自由基路径与非自由基机理：非自由基路径（ΔG‡ = 18.7 kcal/mol）动力学上优于自由基路径（ΔG‡ = 27.6 kcal/mol，由苯甲醛从 Breslow 中间体夺氢产生自由基对引发），产物形成由非自由基路径主导。Breslow 中间体不如其酮式稳定会阻断反应，而自由基物种可能协助互变异构以促进催化循环。
- **推荐理由**: 离子 vs 自由基通道的定量能垒对比，安息香缩合（Breslow 机理）是任务点名的经典体系。
- **候选反应**: NHC 催化苯甲醛苯偶姻缩合（Breslow 机理）；自由基对通道 vs 离子通道竞争。

## normal-05
- **标题**: CASSCF Calculations Reveal Competitive Chair (Pericyclic) and Boat (Pseudopericyclic) Transition States for the [3,3] Sigmatropic Rearrangement of Allyl Esters
- **作者**: Henry W. Kreiman, Mackenzie E. Batali, C. Jamieson, Molly A. Lyon, J. A. Duncan
- **年份/期刊**: 2018, J. Org. Chem.
- **DOI**: 10.1021/acs.joc.7b02316
- **URL**: https://doi.org/10.1021/acs.joc.7b02316
- **OA**: closed（仅元数据）
- **摘要**: 在 (10,8)CASPT2/6-31G**//(10,8)CASSCF/6-31G** 与 CCSD(T)/cc-pVDZ//(10,8)-CASSCF/6-31G** 水平研究 cis-3-penten-2-yl acetate (16) -> trans-3-penten-2-yl acetate (17) 及 3-buten-2-yl acetate (21) -> trans-2-buten-1-yl acetate (22) 的 [3,3] σ迁移重排势能面。与此前 B3LYP/6-31G** 报道 16->17 经船形 TS 为协同伪周环（Birney 等, JACS 2009, 131, 528）不同，CASSCF 发现两条重排均有竞争性协同路径：一条船形、一条椅形 TS。椅/船偏好依赖方法。活性空间轨道分析确认船形 TS 为伪周环、椅形 TS 为周环。
- **推荐理由**: Cope/Claisen 类 [3,3] 重排的椅 vs 船竞争通道 + 方法依赖性争议（DFT vs CASSCF 结论相反），底物小，适合 xTB 复验。
- **候选反应**: cis-3-penten-2-yl acetate 的 [3,3] σ迁移重排；椅形（周环）vs 船形（伪周环）过渡态竞争。

## normal-06
- **标题**: A Molecular Electron Density Theory Study of the Competitiveness of Polar Diels-Alder and Polar Alder-ene Reactions
- **作者**: Luis R. Domingo, Mar Rios-Gutierrez, Patricia Perez
- **年份/期刊**: 2018, Molecules (23, 1913)
- **DOI**: 10.3390/molecules23081913
- **URL**: https://doi.org/10.3390/molecules23081913
- **OA**: oa，**PDF**: `2018_domingo_polar_da_ene.pdf`
- **摘要**: 在 MPWB1K/6-311G(d,p) 水平用 MEDT 研究 BF3 催化 2-methyl-1,3-butadiene（含烯丙位氢的二烯）与甲醛的极性 Diels-Alder (P-DA) 与极性 Alder-ene (P-AE) 竞争。BF3 配位大幅加速两个反应（活化焓 < 2.2 kcal/mol）使二者竞争；二氧六环中 P-AE 略占优（TS 极性更大）。还研究了 hexahydrophenanthrene + BF3:formaldehyde 的 Prins 反应（P-DA 因二烯骨架芳香性而能垒很高）。提出"pseudocyclic selectivity"概念。
- **推荐理由**: 同一反应物对的环加成 vs ene 双通道竞争的教科书式案例，DFT 完整能垒剖面，OA 全文可下载。
- **候选反应**: BF3 催化 2-甲基-1,3-丁二烯 + 甲醛：极性 DA vs 极性 Alder-ene；hexahydrophenanthrene 的 Prins 反应。

## normal-07
- **标题**: Unveiling the Role of the Lewis Acids in the Acceleration of Alder-Ene Reactions: A Molecular Electron Density Theory Study
- **作者**: Luis R. Domingo, Patricia Perez
- **年份/期刊**: 2025, Molecules (30, 4289)
- **DOI**: 10.3390/molecules30214289
- **URL**: https://doi.org/10.3390/molecules30214289
- **OA**: oa，**PDF**: `2025_domingo_lewis_acid_ene.pdf`
- **摘要**: 用 MEDT 研究 Lewis 酸（BH3、BF3、AlCl3，酸性递增）对 2-methylbutadiene 与甲醛 Alder-ene 反应活化能的电子效应。LA 不改变羰基电子结构但显著增强甲醛亲电性；LA 不仅加速反应还改变机理——从非协同"两阶段一步"变为"分步（two-step）"。TS 电子密度拓扑分析显示新 C-C 键已开始形成而氢迁移尚未开始。RIAE 分析定量建立 LA 电子效应；LA 增大全局电子密度转移（GEDT）稳定 TS 处 CHO 骨架。
- **推荐理由**: 展示催化剂诱导的机理切换（一步两阶段 vs 分步），三种 Lewis 酸梯度对比，OA 全文。
- **候选反应**: 2-methylbutadiene + 甲醛的 Alder-ene 反应；BH3/BF3/AlCl3 调控的一步 vs 分步机理切换。

## normal-08
- **标题**: A New Insight into the Molecular Mechanism of the Reaction between 2-Methoxyfuran and Ethyl (Z)-3-phenyl-2-nitroprop-2-enoate: An MEDT Computational Study
- **作者**: Mikolaj Sadowski, Ewa Dresler, Aneta Wroblewska, Radomir Jasinski
- **年份/期刊**: 2024, Molecules (29, 4876)
- **DOI**: 10.3390/molecules29204876
- **URL**: https://doi.org/10.3390/molecules29204876
- **OA**: oa，**PDF**: `2024_sadowski_methoxyfuran.pdf`
- **摘要**: 用 wB97XD/6-311+G(d,p) (PCM) 研究 2-methoxyfuran 与 ethyl (Z)-3-phenyl-2-nitroprop-2-enoate 的反应机理。最可能机理与此前假设根本不同：检测到反应路径上 6 种可能的两性离子中间体，其形成由局部亲核/亲电相互作用决定；exo-nitro Diels-Alder 环加合通道被完全排除；并评估了五元/六元 nitronate 作为潜在 TAC 的电子本质。
- **推荐理由**: 机理翻案 + 多中间体分步网络 + 明确排除 DA 通道，假设提出与淘汰素材丰富；OA。
- **候选反应**: 2-methoxyfuran 与硝基丙烯酸酯的反应；两性离子分步 vs 协同 DA 通道竞争。

## normal-09
- **标题**: Reactive Atomistic Simulations of Diels-Alder Reactions: the Importance of Molecular Rotations
- **作者**: Uxia Rivero, Oliver T. Unke, Markus Meuwly, Stefan Willitsch
- **年份/期刊**: 2019, J. Chem. Phys. (151, 104301)
- **DOI**: 10.1063/1.5114981（arXiv:1906.07455）
- **URL**: https://arxiv.org/abs/1906.07455
- **OA**: oa（arXiv），**PDF**: `2019_rivero_dielsalder_dynamics.pdf`
- **摘要**: 用多面绝热反应分子动力学 + PhysNet 神经网络研究 2,3-二溴-1,3-丁二烯与马来酸酐的 Diels-Alder 反应，作为探索 DA 反应协同性/同步性及促进方式的原型。最小动力学路径分析表明转动能（~65%）与碰撞能（~20%）共同驱动体系越过过渡态；与丁二烯+马来酸酐对比显示溴取代增强转动激发的重要性；高能反应事件中反应为直接且大多同步。
- **推荐理由**: 用动力学（而非静态扫描）检验 DA 协同性/同步性，体系重原子 ~17，适合 xTB 静态+动态交叉验证。
- **候选反应**: 2,3-二溴-1,3-丁二烯 + 马来酸酐 DA 反应；丁二烯 + 马来酸酐（同步性对比）。

## normal-10
- **标题**: Reactive Atomistic Simulations of Diels-Alder-type Reactions: Conformational and Dynamic Effects in the Polar Cycloaddition of 2,3-Dibromobutadiene Radical Ions with Maleic Anhydride
- **作者**: Uxia Rivero, Haydar Taylan Turan, Markus Meuwly, Stefan Willitsch
- **年份/期刊**: 2020, Molecular Physics
- **DOI**: 10.1080/00268976.2020.1825852（arXiv:2010.00464）
- **URL**: https://arxiv.org/abs/2010.00464
- **OA**: oa（arXiv），**PDF**: `2020_rivero_ionic_dielsalder.pdf`
- **摘要**: 理论研究了马来酸酐与 2,3-二溴丁二烯自由基离子的离子型 DA（极性环加成）动力学、动态学与构象特异性。发现协同与分步路径竞争，s-cis 与 s-trans 构象均有反应性（300 K 速率分别为 5.1e-14 与 3.8e-14 s^-1）。与中性体系（仅 gauche 构象经慢速、协同、大多同步路径反应）形成对照。
- **推荐理由**: 协同 vs 分步 + 构象依赖竞争的双假设检验案例，离子体系拓展了难度维度；arXiv OA。
- **候选反应**: 2,3-二溴丁二烯自由基离子 + 马来酸酐的离子型 DA；协同 vs 分步及 s-cis/s-trans 构象效应。

## normal-11
- **标题**: Insights into the Mechanism, Selectivity, and Substituent Effects in the Diels-Alder Reaction of Azatrienes with Electron-rich Dienophiles: An MEDT Study
- **作者**: Amine Rafik, Abdeljabbar Jaddi Mohammed Salah, Najia Komiha, Miguel Carvajal, Khadija Marakchi
- **年份/期刊**: 2024, J. Mol. Graph. Model. (108819)
- **DOI**: 10.1016/j.jmgm.2024.108819（arXiv:2407.11230）
- **URL**: https://arxiv.org/abs/2407.11230
- **OA**: oa（arXiv），**PDF**: `2024_rafik_azatriene_dielsalder.pdf`
- **摘要**: 用 MEDT 理论研究氮杂三烯与乙基乙烯基醚、烯丙基甲基醚的杂 Diels-Alder 反应。机理为动力学控制的极性"一步两阶段"过程；建立了周选择性/区域选择性/立体选择与机理特征的关系；讨论了弱相互作用对活化势垒与成键演化的影响；增强反向电子密度通量的取代基促进反应。
- **推荐理由**: 杂 DA 的多重选择性（peri-/regio-/stereo-）竞争通道，含氮中等底物，arXiv OA。
- **候选反应**: 氮杂三烯 + 乙基乙烯基醚杂 DA；氮杂三烯 + 烯丙基甲基醚（peri-/区域选择性竞争）。

## normal-12
- **标题**: Automated Exploration of Reaction Networks and Mechanisms Based on Metadynamics Nanoreactor Simulations
- **作者**: Yutai Zhang, Chao Xu, Zhenggang Lan
- **年份/期刊**: 2023, J. Chem. Theory Comput. (19, 8718-8731)
- **DOI**: 10.1021/acs.jctc.3c00752（arXiv:2306.14130，Green OA）
- **URL**: https://arxiv.org/abs/2306.14130
- **OA**: oa（arXiv），**PDF**: `2023_zhang_nanoreactor.pdf`
- **摘要**: 开发自动化反应网络构建与机理探索方法：nanoreactor 型分子动力学产生可能反应，metadynamics 克服能垒，半经验 GFN2-xTB 降低计算成本；基于分子连接性演化的隐马尔可夫模型从轨迹识别反应事件，为 DFT 水平过渡态搜索提供起点，最终构建含多条路径的完整反应网络。以 HCHO + NH3 双分子反应及数十个 HCN/H2O 组成的多物种体系验证可行性与效率。
- **推荐理由**: 自动化机理探索复现/构建完整反应网络（含中间体清单）方向的代表作，且直接用 GFN2-xTB——与本基准计算档位一致。
- **候选反应**: HCHO + NH3 反应网络（亚胺/羟甲胺形成路径）；HCN + H2O 多物种反应网络。

---

## 覆盖的反应类型
1. Morita-Baylis-Hillman（质子转移竞争通道、决速步重判）
2. Wittig 反应（betaine vs oxaphosphetane；[2+2] vs 两阶段一步）×2
3. 苯偶姻/安息香缩合（离子 vs 自由基通道）
4. [3,3] σ迁移重排（椅 vs 船、周环 vs 伪周环、方法依赖争议）
5. 极性 Diels-Alder vs 极性 Alder-ene 通道竞争
6. Alder-ene 的 Lewis 酸调控机理切换（一步 vs 分步）
7. 呋喃-硝基烯烃多通道（两性离子分步网络，DA 通道被排除）
8. Diels-Alder 协同性/同步性动力学检验（中性 + 离子自由基、构象效应）×2
9. 杂 Diels-Alder 多重选择性竞争
10. 自动化反应网络探索（GFN2-xTB nanoreactor，HCHO+NH3、HCN+H2O）

## 备注
- 检索中 OpenAlex 搜索接口 503 不可用，改用 Crossref REST API + Semantic Scholar API + arXiv 检索补齐元数据与摘要（所有摘要均来自检索 API 返回原文）。
- 已持有方法学文献（rdb7、grambow2020、transition1x、bh9、mr_detection_duan2020、gmtkn55 等）未重复下载；normal-12 与 grambow2020 主题相近但体系不同（有机小分子网络，GFN2-xTB），予以保留。
