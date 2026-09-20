# reaction_eval 子任务调研笔记：MLP 反应能垒与过渡态精度的独立第三方评测

## 总述

本子任务收集了 **10 篇**对机器学习势（MLP/MLIP）在反应能垒高度与过渡态（TS）搜索精度上的独立评测或系统横评文献（2020–2026），其中 8 篇拿到开放获取全文 PDF，2 篇为 ACS 付费墙（仅摘要级结论）。核心发现可以概括为一句话：**通用 MLP 在其训练域内的近平衡与反应路径区可以做到接近化学精度（1 kcal/mol 量级），但"能垒 MAE 小"不等于"TS 搜索可靠"，且一旦跨出元素域、电荷域、自旋域或相态域，误差会跳升一个数量级甚至完全失败**。具体地：(1) 预训练基础模型不经微调几乎都无法在反应 PES 上定位 TS——Zhao et al. (Adv. Sci. 2025) 的七模型横评中无一超过 GFN2-xTB；(2) 训练数据决定成败——OMol25 数据训练的 MACE-OMol25 在有机体系 TS 搜索成功率达 96.6%（Marks et al. 2026），而 AIMNet2 只有 82.8%；(3) 失败模式有明确的化学空间归属：带电物种（AIQM1 的 PA/G21EA 误差 8–14 kcal/mol）、开壳自由基（AIMNet2-NSE 明言多数 MLIP 不区分自旋态）、金属体系（UMA-M 尚可但需 DFT 终验）、真空气相断键（ANI-1xnr 官方不建议）。这些结论直接支撑本项目的选测策略：**把测试反应严格限制在指定金标准 MLP 的训练域覆盖范围内，用反应距离预组织过滤 + 应用域距离判据做预筛**。

**两点检索说明（诚实记录）**：
1. Coordinator 关键词线索中的 "RDB7/Grambow (Nat Commun 2021)" 未能在 Crossref / Europe PMC / arXiv 中找到对应的 Grambow Nat Commun 2021 论文；RDB7 数据集的实际原始出处是 **Grambow, Pattanaik & Green, Sci Data 7, 137 (2020)**。Nat Commun 2021 时段内与本主题最匹配的论文是 AIQM1（Zheng et al., Nat Commun 12, 7022），已收录以补位。
2. "RPC reaction path completion 数据集"线索：arXiv API 精确短语 `"reaction path completion"` 返回 0 条结果，DuckDuckGo 与 OpenAlex 亦未检到同名公开数据集论文。该线索可能指向 T1x/RGD1/OA-ReactDiff 谱系中的某个内部称呼；建议 Coordinator 如需此数据集，提供更多上下文（作者或会议）再行追查。

## 对比表：方法 × 精度 × 域 × 成本

| # | 文献（年份） | 被评 MLP/模型 | 能垒精度（MAE） | TS 几何质量 | 域（舒适区）与失败模式 | 成本 | 来源 |
|---|---|---|---|---|---|---|---|
| 1 | Transition1x, Schreiner et al., Sci Data 2022 | PaiNN 等（T1x/QM9x/ANI1x 交叉训练） | NEB 复算 TS 能量 vs GSM：MAE 0.16 eV（≈3.7 kcal/mol）；未给出单一能垒 MAE | TS RMSD 平均 0.11 Å（NEB vs GSM） | 近平衡数据（QM9 类）训练 → 学不到过渡态区特征；≤7 重原子 CHNO 气相 | — | [1] Abstract & Technical Validation |
| 2 | RDB7 数据集, Grambow et al., Sci Data 2020 | （数据集本身；ωB97X-D3 为参考级） | ωB97X-D3 能垒 vs 参考 RMSD 2.28 kcal/mol（参考级的可信度标尺） | 全部 TS 经单虚频+虚频方向质检（\|ν\|≥100 cm⁻¹） | ≤7 重原子 CHNO、单分子反应物气相反应；能垒最高 ~200 kcal/mol | — | [2] Data Records & Tech. Validation |
| 3 | AIQM1, Zheng et al., Nat Commun 2021 | AIQM1（Δ-NN+ODM2*+D4） | （无专门能垒基准）能量 MAD 0.8 kcal/mol vs CCSD(T)*/CBS；生成热 CHNO 0.9 | 几何键长 MAD ~0.004–0.007 Å | 舒适区=中性闭壳层 H/C/N/O；带电物种 PA 10.5、G21IP 8.8、G21EA 14.0 kcal/mol；H2 误差 −2.9 kcal/mol（训练欠采样即失效） | SQM 速度（C60 优化 14 s 单核） | [3] Fig 3–5 |
| 4 | ANI-1xnr, Zhang et al., Nat Chem 2024 | ANI-1xnr（nanoreactor AL 训练） | C–H BDE 116.6 vs DFT 110.0 vs 实验 103.3 kcal/mol（偏差 +13.3 vs 实验）；甲烷燃烧速率偏快 ~40× | —（MD 反应网络层面验证） | 舒适区=凝聚相 CHNO、密度 0.5–2.5 g/cc、singlet；in vacuo 断键不可靠（官方明示）；对 T1x 气相反应不确定度整体超标；不显含电荷/自旋 | ~50k 梯度/s（Titan V） | [4] Methods & Ext. Data Fig 4/5 |
| 5 | 七模型 TS 横评, Zhao et al., Adv Sci 2025 | ANI-1x, CHGNet, LEFTNet, MatterSim, MACE-OFF23, DPA-2, Orb-v2 + GFN2-xTB + React-OT | 微调后优化 TS 能垒 MAE：LEFTNet 1.83（最佳）；ANI-1x 11.07 kcal/mol（最差，逊于 xTB）；E/F MAE 好 ≠ TS 成功（直接力方案 Hessian MAE 144–1215 kcal/mol/Å²） | 微调后平均 TS RMSD：LEFTNet 0.10 Å ~ ANI-1x 0.15 Å | 预训练基础模型（含 MACE-OFF23 仅 51 intended TS、Orb-v2 ~2%）无一胜过 GFN2-xTB；T1x 域内微调后 intended 率饱和于 ~68% | — | [5] Figs 2–3 |
| 6 | NNP 加速 TS 搜索, Li et al., JCIM 2025 | NequIP 等 NNP × 多种 TS 算法 | （付费墙内未核实数值）摘要级：NequIP+EW-CI-NEB 显著优于半经验方法 | 同左 | 任务专用小域训练可超 xTB | 远快于 DFT | [6] Abstract |
| 7 | G2A 可迁移性, Vadaddi et al., JPCA 2024 | 图→活化能直推模型（RGD1） | RGD1 留出测试 MAE ≈4 kcal/mol；外部测试集显著变差 | — | 机制类型/分子性/尺寸分布一变即失效（OOD 性能差是共性） | — | [7] Abstract |
| 8 | MLIP TS 搜索横评, Marks et al., arXiv 2026 | MACE-OMol25, UMA-S/M, eSEN-S, AIMNet2, GFN2-xTB（58 反应，ωB97X-V/def2-TZVP 参考） | （成功率导向）替代鞍点案例：乙烷脱氢高 ~8 kcal/mol、Claisen 高 43 kcal/mol | FSM 88–90% vs CI-NEB 63–71% 成功率；MLIP 曲率/Hessian 误差是主要失效源 | OMol25 系总体 91.8% vs 非 OMol25 84.5%；UMA-M 可迁移到 MOBH35/铑催化 OOD，但自旋/电荷重组难，终验需 DFT | MACE-OMol25 有机 96.6% 成功、3.8 次 DFT 梯度/反应（省 94–96%）；AIMNet2 82.8%、10.7 次 | [8] Sec 3–4 |
| 9 | DeePEST-OS, Ren et al., Nat Commun 2026 | DeePEST-OS（MACE+GFN2-xTB Δ-learning）vs 纯 MACE/PaiNN/GFN2-xTB | DORTS-1K：0.60 kcal/mol（MACE 0.93；PaiNN 5.28）；Zatosetron Gibbs 能垒 1.18 vs xTB 10.00 kcal/mol | 平均 RMSD 0.12 Å（MACE 0.19；PaiNN 0.50；xTB 0.31 Å） | 十种主族元素（CHONPSFClBrI）；OOD(T1x)：MAE 3.80 kcal/mol；**应用域判据：嵌入空间最近邻距离>0.7 即超 1 kcal/mol** | TS 优化提速 4 个量级 | [9] Fig 5/7 & Table 2 |
| 10 | AIMNet2-NSE, Kalita et al., Angew 2026 | AIMNet2-NSE（自旋-电荷平衡化） | 近 DFT 精度（自由基测试集/BASChem19/RP） | — | **"多数现有 MLIP 不区分自旋态→不适合开壳反应化学"**；基座 AIMNet2 只覆盖中性+带电闭壳层（CHNOSFClBrIPSiBAsSe） | 线性标度 | [10] Abstract |

### 对本项目（四级机理基准 + 单一金标准 MLP）的直接推论

1. **舒适区判据模板**（可直接写进基准规范）：元素 ∈ 训练集元素表；闭壳层中性为主（开壳/双自由基除非金标准势显式支持自旋，否则归入 Impossible 档）；无金属（金属体系即使 UMA-M 也需 DFT 终验 [8][9]）；气相分子反应需确认势的训练数据含反应路径采样而非仅近平衡构型 [1][4]。
2. **量化警戒线**：应用域最近邻距离类指标 >0.7（DeePEST-OS 512 维嵌入）对应能垒 MAE 突破化学精度 [9]；E/F MAE 达标不代表 TS 搜索成功，Hessian/曲率质量必须单独考察 [5][8]。
3. **预期误差档位**：域内能垒 MAE ~0.6–2 kcal/mol 可期 [5][8][9]；OOD 或域边界处 3.8–14 kcal/mol [3][7][9]；这正好支撑 Easy/Normal/Hard/Impossible 四档的难度分级依据。

## 引用文献（标题 + DOI/URL）

1. Transition1x - a dataset for building generalizable reactive machine learning potentials. Schreiner, M.; Bhowmik, A.; Vegge, T.; Busk, J.; Winther, O. *Scientific Data* **9**, 779 (2022). https://doi.org/10.1038/s41597-022-01870-w
2. Reactants, products, and transition states of elementary chemical reactions based on quantum chemistry. Grambow, C. A.; Pattanaik, L.; Green, W. H. *Scientific Data* **7**, 137 (2020). https://doi.org/10.1038/s41597-020-0460-4
3. Artificial intelligence-enhanced quantum chemical method with broad applicability. Zheng, P.; Zubatyuk, R.; Wu, W.; Isayev, O.; Dral, P. O. *Nature Communications* **12**, 7022 (2021). https://doi.org/10.1038/s41467-021-27340-2
4. Exploring the frontiers of condensed-phase chemistry with a general reactive machine learning potential. Zhang, S.; Makoś, M. Z.; Jadrich, R. B.; et al. *Nature Chemistry* **16**, 727–734 (2024). https://doi.org/10.1038/s41557-023-01427-3
5. Harnessing Machine Learning to Enhance Transition State Search with Interatomic Potentials and Generative Models. Zhao, Q.; Han, Y.; Zhang, D.; Wang, J.; Zhong, P.; Cui, T.; Yin, B.; Cao, Y.; Jia, H.; Duan, C. *Advanced Science* **12**(34), e06240 (2025). https://doi.org/10.1002/advs.202506240
6. Transition State Searching Accelerated by Neural Network Potential. Li, B.; Xiao, J.; Gao, Y.; Zhang, J. Z. H.; Zhu, T. *J. Chem. Inf. Model.* **65**(5), 2297–2303 (2025). https://doi.org/10.1021/acs.jcim.4c01714 （付费墙）
7. Graph to Activation Energy Models Easily Reach Irreducible Errors but Show Limited Transferability. Vadaddi, S. M.; Zhao, Q.; Savoie, B. M. *J. Phys. Chem. A* **128**(13), 2543–2555 (2024). https://doi.org/10.1021/acs.jpca.3c07240 （付费墙）
8. Reliable and Efficient Automated Transition-State Searches with Machine-Learned Interatomic Potentials. Marks, J.; Vandezande, J.; Gomes, J. arXiv:2604.00405 (2026). https://doi.org/10.48550/arXiv.2604.00405 （预印本）
9. Reactive machine learning potential for accelerating transition state search in organic synthesis. Ren, K.; Tang, K.; Zhao, Y.; Zhang, L.; Du, J.; Meng, Q.; Liu, Q. *Nature Communications* **17**, 6253 (2026). https://doi.org/10.1038/s41467-026-72945-0
10. AIMNet2-NSE: A Transferable Reactive Neural Network Potential for Open-Shell Chemistry. Kalita, B.; Zubatyuk, R.; Anstine, D. M.; Bergeler, M.; Settels, V.; Stork, C.; Spicher, S.; Isayev, O. *Angew. Chem. Int. Ed.* **65**(5), e16763 (2026). https://doi.org/10.1002/anie.202516763

---
*文件清单：`metadata.json`（10 条，含逐字摘要）、8 个 OA PDF（`YYYY_firstauthor_topic.pdf`）、本 README。`_notes/` 目录存放两篇核心基准论文的 pdf2md 提取文本备查。*
