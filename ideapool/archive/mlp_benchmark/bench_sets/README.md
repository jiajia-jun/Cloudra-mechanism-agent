# bench_sets — MLP 常用基准集定义文献与统计（GMTKN55 / BH9 / QM9 / rMD17 / ISO17 / SPICE）

## 总述

本子任务整理了机器学习势（MLP）领域 6 个最常用基准集的定义文献与关键统计，外加 2 篇直接给出"MLP×基准集"公开成绩的模型论文（NequIP、AIMNet2），共 8 个 metadata 条目；另在交叉引用表中补充 MACE-OFF 的公开数字（其 PDF 亦已入库）。核心发现有三点。**第一**，六个基准集覆盖三种不同的考察维度：QM9 与 GMTKN55 的 48/55 子集、BH9 的反应能部分衡量**热化学**；GMTKN55 的 7 个势垒子集与 BH9 的势垒高度部分衡量**动力学**；rMD17、ISO17、SPICE 衡量**势能面/力场保真度**（MD 轨迹能量与力），不涉及反应势垒。**第二**，开源 MLP 中只有 AIMNet2（Chem. Sci. 2025）在正文把 GMTKN55 纳入评测并按类别给出 WTMAD2——其"势垒高度"类成绩（≈8 kcal/mol，读图值）与作为其训练参考的 B97-3c 自身（≈8.2）相当，这是"指定 MLP 金标准"可期望的势垒精度上界参照。**第三**，对项目约束（无 DFT 预算、xTB 仅做采样预筛）的文献支持：GFN2-xTB 在 GMTKN55 全集上 WTMAD2 ≈20 kcal/mol、构象搜索成功率仅 45.2%（676 例），显著劣于 AIMNet2 的 77%——xTB 定位为预筛而非最终能量来源是合理的。

**两处必须更正的引用误记**（已用 Crossref/OpenAlex 核实）：
1. 任务描述中的 "GMTKN55 (Acc. Chem. Res. 2021)" 不存在：Crossref 按 Acc. Chem. Res.（ISSN 0009-2665）检索 "GMTKN55" 命中 **0** 条（api.crossref.org 查询记录），OpenAlex 标题/全文检索亦无 2021 年 Acc. Chem. Res. 的 GMTKN55 文章。GMTKN55 的正典定义文献是 **Goerigk et al., PCCP 2017, 19, 32184**（DOI 10.1039/c7cp04913g，被引 1964）。
2. 任务描述称 BH9 出自 "Grimme 组"：实际作者是 **Prasad, Pei, Edelmann, Otero-de-la-Roza, DiLabio**（UBC Okanagan + Oviedo，Crossref 作者字段核实），正式发表于 **JCTC 2021**（DOI 10.1021/acs.jctc.1c00694），与 Grimme 组无关（Grimme 组相关工作是其评测对象 r²SCAN-3c 等引用了 BH9）。

**PDF 获取情况**：8 个 PDF 全部落盘且均 >100 KB（`ls -la` 验证）。GMTKN55 主文（RSC，CC-BY-NC）与 BH9 主文（ACS，付费墙）的 PDF 被 Cloudflare/反爬拦截（HTTP 403；Wayback 429 限流），如实记录为无主文 PDF——GMTKN55 以双源核对的逐字摘要 + DOI 交付，BH9 交付本地已有的 JCTC 支撑信息（SI）真 PDF（228 KB）。ISO17 与 rMD17 因 AIP 403，改用同工作的 arXiv 版 PDF。

## 一、六个基准集：定义文献、规模与"衡量什么"

| 基准集 | 定义文献（DOI） | 规模 / 参考能级 | 衡量维度 | 与四级机理基准的映射 |
|---|---|---|---|---|
| **GMTKN55** | Goerigk et al., PCCP 2017, 10.1039/c7cp04913g | 55 子集 / 1505 个相对能量 / 2462 单点；高精度 WFT 参考 | **热化学**（基础性质 18 + 大体系反应/异构化能 9 + 分子间 NCI 12 + 分子内 NCI 9）+ **动力学**（势垒子集 7） | 热化学子集→Easy/Normal 的反应能校验；7 个势垒子集→Hard 层的势垒精度标尺 |
| **BH9** | Prasad et al., JCTC 2021, 10.1021/acs.jctc.1c00694 | 449 个反应 × 9 类有机/生化反应类型；DLPNO-CCSD(T)/CBS | **热化学 + 动力学**（每反应同时给反应能与正/逆势垒） | 与 Cloudra 反应机理基准最同构：反应能+势垒成对出现，可作 Hard/Impossible 分层的模板 |
| **QM9** | Ramakrishnan et al., Sci. Data 2014, 10.1038/sdata.2014.22 | 133,885 个 CHONF 分子（≤9 重原子）；B3LYP/6-31G(2df,p)，C7H10O2 的 6,095 异构体另给 G4MP2 | **热化学**（原子化能/焓/自由能等，仅平衡几何，无过渡态） | Easy 层"单点性质/同分异构能量排序"的题源风格参照 |
| **rMD17** | Christensen et al., JCP 2020, 10.1063/1.5126701（随文发布） | 8 分子 × 100,000 帧；PBE/def2-SVP、very tight SCF + 极密网格重算 | **势能面/力**（MD 构型能量+力，无反应事件） | 不直接用于机理分级，但是指定 MLP"力面保真"的入门体检 |
| **ISO17** | Schütt et al., JCP 2018, 10.1063/1.5019779（首次提出于 arXiv:1706.08566） | 129 个 C7O2H10 异构体 × 5,000 帧 = 645,000 样本 | **跨异构体泛化**（化学空间+构型空间双重变化，无势垒） | Normal/Hard 层"异构化能量排序、跨骨架泛化"的先例 |
| **SPICE** | Eastman et al., Sci. Data 2023, 10.1038/s41597-022-01882-6 | >110 万构象；15 元素；带电+中性；ωB97M-D3(BJ)/def2-TZVPPD | **训练域定义**（小分子/二聚体/二肽/溶剂化氨基酸，≤50 原子） | 定义"指定 MLP 舒适区"的元素/电荷/尺寸边界的直接依据 |

要点：
- **热化学 vs 动力学的精确划分**（来源：GMTKN55 摘要 + AIMNet2 p.10233 沿用的分类）：55 = 18 基础性质 + 9 大体系反应/异构化能 + **7 势垒** + 12 分子间 NCI + 9 分子内 NCI。即 GMTKN55 中只有 7/55 直接考动力学。
- **MLP 文献的"动力学替代品"**：主流 MLP 论文极少直接评测过渡态势垒，常用扭转势垒代替——MACE-OFF 用 TorsionNet-500 与双芳基扭转（78 分子，CCSD(T) 参考），AIMNet2 用 torsion rotation profiles。真正的"TS 几何+势垒"联合基准在 MLP 社区仍是空白，这正是 Cloudra 四级机理基准的差异化机会。
- **ISO17 规模勘误**：常被误记为"17 个异构体"，实际定义是 **129 个异构体**（ISO17 之名并非异构体数目），共 645,000 样本（arXiv:1706.08566 §5.3 原文）。

## 二、方法 × 精度 × 域 × 成本对比表（MLP 公开成绩交叉引用）

| 方法（论文） | 精度（公开数字，均注明出处） | 域（元素/电荷/尺寸） | 成本 | 在哪些基准集上有公开成绩 |
|---|---|---|---|---|
| **NequIP (l=3)**（Nat. Commun. 2022, 10.1038/s41467-022-29939-5, Table 1/2） | rMD17（1000 训练构型，E MAE / F MAE）：苯 0.04 meV / 0.3 meV/Å；乙醇 0.4 / 2.8；甲苯 0.3 / 1.6；阿司匹林 2.3 / 8.2；原 MD17 乙醇 2.2 / 3.1；数据效率比既有模型高最多 3 个数量级（摘要） | 训练集所含分子体系（小分子）；按数据集特训 | 未在正文给统一速度数字 | rMD17、MD17、液态水/冰、Cu 表面甲酸分解 |
| **FCHL19**（JCP 2020, 10.1063/1.5126701 摘要；NequIP Table 2） | rMD17 乙醇 0.9 meV / 6.2 meV/Å（1000 训练构型）；预测耗时"每原子几毫秒"（摘要） | 小分子+凝聚相水簇 | 每原子毫秒级（摘要） | QM7b、QM9、水簇、MD17/rMD17 |
| **SchNet**（arXiv:1706.08566 Table 3） | ISO17 能量 MAE：已知分子 0.36 kcal/mol（能量+力训练）、未知分子 2.40 kcal/mol；均值基线 14.89/15.54 | QM9 类有机分子 | — | QM9、MD17、ISO17 |
| **AIMNet2**（Chem. Sci. 2025, 10.1039/d4sc08572h, Fig. 5a + p.10233） | GMTKN55 WTMAD2（读图近似）：All ≈12 kcal/mol（B97-3c 版）/ ≈11.8（ωB97M-D3 版），对比 GFN2-xTB ≈20、B97-3c DFT ≈9.8、OrbNet Denali ≈9.3；分类别：Basic properties ≈4.0（ωB97M-D3 版，优于 B97-3c DFT 的 ≈9.5）、**Barrier heights ≈8.1（≈B97-3c 自身 8.2；最优 DFT ωB97X-D3 ≈4.6）**；构象搜索成功率 77%（B97-3c 75%、GFN2-xTB 45.2%） | **≤14 种元素、中性+带电**（摘要）；训练数据 2×10⁷ 杂化 DFT 计算 | 半经验级速度（论文定位） | **GMTKN55**、NCI Atlas、构象搜索、扭转剖面、几何优化 |
| **MACE-OFF23**（arXiv:2312.15211 / JACS 2025, 10.1021/jacs.4c07099） | SPICE 留出测试（L 模型）：E ≈0.5–1.0 meV/atom、F ≈15–20 meV/Å（化学精度=1 kcal/mol≈43 meV）；双芳基扭转垒 MAE 0.3/0.4/0.5 kcal/mol（L/M/S，DFT 自身 vs CC 为 0.2；优于 ANI-1ccx 与 GFN2-xTB）；TorsionNet-500 ≈0.25 kcal/mol（M/L）；分子晶体升华焓 MAE 1.8 kcal/mol（ANI-2x 为 4.9） | **10 元素 H,C,N,O,F,P,S,Cl,Br,I、仅中性闭壳层**；训练域=SPICE v1 的 85% + QMugs 50–90 原子分子 + 水簇 | LAMMPS/OpenMM 可跑纳秒级蛋白模拟（crambin 18,000 原子演示） | SPICE 留出集、TorsionNet-500、双芳基扭转、分子晶体、液体性质；**未评 GMTKN55**（正文无该词） |
| **GFN2-xTB**（对照，AIMNet2 p.10233 + Fig. 5a） | GMTKN55 All WTMAD2 ≈20 kcal/mol；构象搜索成功率 45.2%（676 例） | 全周期表大部分（Z≤86） | 最快（秒级/构象系综） | GMTKN55、NCI Atlas、CREST 系综采样 |

**读表结论（供 Coordinator 汇总"单一指定 MLP + 舒适区判据"）**：
1. **精度预期分层**（均有公开出处）：平衡态力/能（rMD17）可达 meV 级；扭转/构象能差可达 0.25–0.5 kcal/mol；GMTKN55 式广谱热化学 WTMAD2 ≈4–12 kcal/mol（分类别差异大）；**反应势垒类 ≈8 kcal/mol**（AIMNet2 vs B97-3c，读图）——即当前开源 MLP 在"真势垒"上的公开成绩距化学精度（1 kcal/mol）尚远，四级基准中 Hard 层的容差设计应以此为锚。
2. **舒适区判据的文献依据**：元素域取 SPICE 的 15 元素或 MACE-OFF 的 10 元素（若指定 MLP 为 MACE-OFF 系）；电荷域：AIMNet2 支持带电，MACE-OFF **仅中性闭壳层**——开壳层/自由基反应（BH9 与 GMTKN55 势垒子集中大量存在）可能落在 MACE-OFF 舒适区外，选型时须核对指定势的自旋处理能力；尺寸域：SPICE ≤50 原子、QM9 ≤9 重原子、MACE-OFF 演示到 18,000 原子（外推演示而非精度保证）。
3. **xTB 角色的佐证**：GFN2-xTB 热化学误差（≈20 kcal/mol）与构象成功率（45.2%）都支持项目约束——xTB 只承担构象系综生成/预组织过滤，最终能量数字交给指定 MLP。
4. **基准组合建议**：热化学用 GMTKN55 子集抽样 + BH9 反应能；动力学用 BH9 势垒 + GMTKN55 的 7 个势垒子集；力面体检用 rMD17；跨骨架泛化用 ISO17 协议；训练域边界用 SPICE 子集构成定义。

## 三、检索与获取过程记录（可复现）

- 逐字摘要来源：OpenAlex API（works/doi 端点，abstract_inverted_index 还原）、Europe PMC REST（resultType=core 的 abstractText）、Crossref。GMTKN55 摘要经 OpenAlex 与 Europe PMC 双源逐字核对一致。
- PDF 通道：Nature/PMC 直下成功（QM9、SPICE、NequIP、AIMNet2 经 europepmc.org/articles/PMC12057637?pdf=render）；arXiv 直下成功（rMD17=FCHL19 1909.01946、ISO17=SchNet 1706.08566、MACE-OFF 2312.15211）；RSC pubs（GMTKN55、AIMNet2 主站）、AIP（SchNet JCP、FCHL19 JCP）、ChemRxiv（BH9 预印本）均 403 反爬；web.archive.org 两次 429 限流。
- 本地复用：`docs/benchmark_survey/pdfs/` 下 gmtkn55.pdf（5.8 KB）与 bh9.pdf（6.8 KB）经 `file` 检查为 Cloudflare "Just a moment..." HTML 假 PDF（非 PDF 文档），未采用；bh9_si.pdf（228 KB）为真 PDF，已复制为 `2021_prasad_bh9_si.pdf`。
- 中间产物（各论文 markdown 抽取文本）归档于 `_work/` 子目录，便于复核引文页码。

## 四、引用列表（标题 + DOI/URL）

**metadata.json 中的 8 条：**
1. Goerigk L., Hansen A., Bauer C., Ehrlich S., Najibi A., Grimme S., *A look at the density functional theory zoo with the advanced GMTKN55 database for general main group thermochemistry, kinetics and noncovalent interactions*, Phys. Chem. Chem. Phys. 2017, 19, 32184–32215. DOI: [10.1039/c7cp04913g](https://doi.org/10.1039/c7cp04913g)
2. Prasad V.K., Pei Z., Edelmann S., Otero-de-la-Roza A., DiLabio G.A., *BH9, a New Comprehensive Benchmark Data Set for Barrier Heights and Reaction Energies…*, J. Chem. Theory Comput. 2021. DOI: [10.1021/acs.jctc.1c00694](https://doi.org/10.1021/acs.jctc.1c00694)（更正 10.1021/acs.jctc.2c00362；预印本 10.33774/chemrxiv-2021-mdjwx）
3. Ramakrishnan R., Dral P.O., Rupp M., von Lilienfeld O.A., *Quantum chemistry structures and properties of 134 kilo molecules*, Sci. Data 2014, 1, 140022. DOI: [10.1038/sdata.2014.22](https://doi.org/10.1038/sdata.2014.22)
4. Christensen A.S., Bratholm L.A., Faber F.A., von Lilienfeld O.A., *FCHL revisited: Faster and more accurate quantum machine learning*, J. Chem. Phys. 2020, 152, 044107. DOI: [10.1063/1.5126701](https://doi.org/10.1063/1.5126701)（arXiv:1909.01946；rMD17 数据集 figshare.com/articles/dataset/12672038）
5. Schütt K.T., Kindermans P.-J., Sauceda H.E., Chmiela S., Tkatchenko A., Müller K.-R., *SchNet – A deep learning architecture for molecules and materials*, J. Chem. Phys. 2018, 148, 241722. DOI: [10.1063/1.5019779](https://doi.org/10.1063/1.5019779)（ISO17 首次提出：arXiv:1706.08566）
6. Eastman P. et al., *SPICE, A Dataset of Drug-like Molecules and Peptides for Training Machine Learning Potentials*, Sci. Data 2023, 10, 62. DOI: [10.1038/s41597-022-01882-6](https://doi.org/10.1038/s41597-022-01882-6)（arXiv:2209.10702）
7. Batzner S. et al., *E(3)-equivariant graph neural networks for data-efficient and accurate interatomic potentials*, Nat. Commun. 2022, 13, 3733. DOI: [10.1038/s41467-022-29939-5](https://doi.org/10.1038/s41467-022-29939-5)
8. Anstine D.M., Zubatyuk R., Isayev O., *AIMNet2: a neural network potential to meet your neutral, charged, organic, and elemental-organic needs*, Chem. Sci. 2025, 16, 10228–10244. DOI: [10.1039/d4sc08572h](https://doi.org/10.1039/d4sc08572h)（PMC12057637）

**README 补充引用（未单列 metadata 条目）：**
9. Kovács D.P. et al., *MACE-OFF: Short-Range Transferable Machine Learning Force Fields for Organic Molecules*, JACS 2025. DOI: [10.1021/jacs.4c07099](https://doi.org/10.1021/jacs.4c07099)（arXiv:2312.15211，本地 PDF：2024_kovacs_mace_off.pdf）
10. Christensen A.S. et al., *OrbNet Denali*, J. Chem. Phys. 2021, 155, 204103. DOI: 10.1063/5.0061990（AIMNet2 GMTKN55 评测口径的来源）
