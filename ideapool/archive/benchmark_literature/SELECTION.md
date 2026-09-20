# 四级测试集候选文献筛选清单（含摘要与推荐系数）

> 生成日期：2026-08-25｜数据来源：`ideapool/benchmark_literature/{easy,normal,hard,impossible}/metadata.json` 共 52 篇自动汇编，**摘要为原文未删节**。配套背景见 [INDEX.md](INDEX.md)。
> 用途：人工筛选正式进入四级测试集（Easy 30 / Normal 30 / Hard 20 / Impossible 20）的文献与反应体系；筛选结果反馈编号即可。

## 数据完备度

| 梯队 | 文献数 | PDF 在手 | 仅元数据 | 候选反应标注 | 目标题量 |
|---|---|---|---|---|---|
| easy | 12 | 5 | 7 | 49 | 30 |
| normal | 12 | 7 | 5 | 25 | 30 |
| hard | 16 | 5 | 11 | 24 | 20 |
| impossible | 12 | 9 | 3 | 26 | 20 |
| **合计** | **52** | **26** | **26** | **124** | 100 |

## 推荐系数说明

综合分 = 体系适配×0.30 + 参考数据×0.25 + 测试价值×0.30 + 可获取性×0.15（各分项 0–10）：
- **体系适配**：是否符合该梯队难度定义与本项目算力（xTB→DFT 流水线、重原子规模）
- **参考数据**：是否提供可用于评分的真值（实验/高精度能垒、完整能量剖面、选择性数据）
- **测试价值**：对结构感知、机理发现、假设淘汰、合理拒答四大能力的区分度
- **可获取性**：OA 状态、PDF 是否在手、数据可否经其他途径交叉验证

档位：**≥8.5 必选**（强烈建议纳入）｜**7.5–8.4 推荐**｜**<7.5 备选**。

---
## 总览（各梯队按综合分降序）

### EASY 梯队 —— 单步基元反应（重原子 ≤7，xTB 全流程可算；目标 30 题）

(12 篇｜PDF 在手 5｜候选反应标注 49 条)

| 综合分 | 档位 | ID | 年份 | 文献（短题名） | PDF |
|---|---|---|---|---|---|
| 9.8 | 必选 | easy-01 | 2003 | A Standard Set of Pericyclic Reactions of Hydrocarbons for t… | ✅ |
| 9.3 | 必选 | easy-05 | 2020 | A Unified Framework for Understanding Nucleophilicity and Pr… | ✅ |
| 9.1 | 必选 | easy-02 | 2015 | Accurate reaction barrier heights of pericyclic reactions: S… | — |
| 8.9 | 必选 | easy-12 | 2017 | A look at the density functional theory zoo with the advance… | 📚 |
| 8.8 | 必选 | easy-03 | 2019 | Highly Accurate CCSDT(Q)/CBS Reaction Barrier Heights for a … | — |
| 8.8 | 必选 | easy-07 | 2023 | Effects of Methyl Substitution and Leaving Group on E2/SN2 C… | ✅ |
| 8.7 | 必选 | easy-06 | 2023 | Reaction profiles for quantum chemistry-computed [3 + 2] cyc… | ✅ |
| 8.5 | 必选 | easy-09 | 2005 | Benchmark Database of Barrier Heights for Heavy Atom Transfe… | — |
| 7.6 | 推荐 | easy-08 | 2018 | DFT Study To Explore the Importance of Ring Size and Effect … | ✅ |
| 7.0 | 备选 | easy-04 | 2021 | Accuracy of DLPNO-CCSD(T): Effect of Basis Set and System Si… | — |
| 6.8 | 备选 | easy-11 | 2021 | autodE: Automated Calculation of Reaction Energy Profiles - … | — |
| 6.3 | 备选 | easy-10 | 2016 | How Accurate Are the Minnesota Density Functionals for Nonco… | — |

### NORMAL 梯队 —— 多步机理 / 竞争路径（中等分子；目标 30 题）

(12 篇｜PDF 在手 7｜候选反应标注 25 条)

| 综合分 | 档位 | ID | 年份 | 文献（短题名） | PDF |
|---|---|---|---|---|---|
| 8.7 | 必选 | normal-06 | 2018 | A Molecular Electron Density Theory Study of the Competitive… | ✅ |
| 8.7 | 必选 | normal-08 | 2024 | A New Insight into the Molecular Mechanism of the Reaction b… | ✅ |
| 8.2 | 推荐 | normal-07 | 2025 | Unveiling the Role of the Lewis Acids in the Acceleration of… | ✅ |
| 7.8 | 推荐 | normal-01 | 2007 | Mechanism of the Morita-Baylis-Hillman Reaction: A Computati… | — |
| 7.8 | 推荐 | normal-02 | 2019 | Dissection of the Mechanism of the Wittig Reaction | — |
| 7.8 | 推荐 | normal-04 | 2018 | Can the Radical Channel Contribute to the Catalytic Cycle of… | — |
| 7.6 | 推荐 | normal-12 | 2023 | Automated Exploration of Reaction Networks and Mechanisms Ba… | ✅ |
| 7.5 | 推荐 | normal-11 | 2024 | Insights into the Mechanism, Selectivity, and Substituent Ef… | ✅ |
| 7.3 | 备选 | normal-03 | 2020 | A Close Look to the Oxaphosphetane Formation along the Witti… | — |
| 7.2 | 备选 | normal-09 | 2019 | Reactive Atomistic Simulations of Diels-Alder Reactions: the… | ✅ |
| 7.0 | 备选 | normal-05 | 2018 | CASSCF Calculations Reveal Competitive Chair (Pericyclic) an… | — |
| 6.6 | 备选 | normal-10 | 2020 | Reactive Atomistic Simulations of Diels-Alder-type Reactions… | ✅ |

### HARD 梯队 —— 立体化学 / 微观几何感知（目标 20 题）

(16 篇｜PDF 在手 5｜候选反应标注 24 条)

| 综合分 | 档位 | ID | 年份 | 文献（短题名） | PDF |
|---|---|---|---|---|---|
| 9.6 | 必选 | hard-04 | 2016 | Unconventional exo selectivity in thermal normal-electron-de… | ✅ |
| 9.0 | 必选 | hard-08 | 2015 | Competitive and Cooperative Torquoselectivity in the thermal… | ✅ |
| 8.8 | 必选 | hard-15 | 2022 | Unveiling [3 + 2] Cycloaddition Reactions of N-Methyl-C-3-Br… | ✅ |
| 8.7 | 必选 | hard-01 | 2014 | Origin of the "endo rule" in Diels-Alder reactions | — |
| 8.4 | 推荐 | hard-10 | 2003 | Origins of Inward Torquoselectivity by Silyl Groups and Othe… | — |
| 8.3 | 推荐 | hard-07 | 2025 | DFT Investigation of the Stereoselectivity of the Lewis-Acid… | — |
| 8.1 | 推荐 | hard-02 | 2005 | The Source of the endo Rule in the Diels-Alder Reaction: Are… | — |
| 8.1 | 推荐 | hard-09 | 2016 | Torquoselectivity in Cyclobutene Ring Openings and the Inter… | — |
| 7.8 | 推荐 | hard-03 | 2018 | Origins of the Endo and Exo Selectivities in Cyclopropenone,… | — |
| 7.8 | 推荐 | hard-11 | 2023 | On the Nature of the Rotational Energy Barrier of Atropisome… | ✅ |
| 7.7 | 推荐 | hard-16 | 2010 | Computational Study of Factors Controlling the Boat and Chai… | — |
| 7.4 | 备选 | hard-06 | 2021 | Bifunctional Hydrogen Bond Donor-Catalyzed Diels-Alder React… | — |
| 7.2 | 备选 | hard-14 | 2020 | A DFT study on the reaction mechanism of enantioselective re… | — |
| 6.9 | 备选 | hard-12 | 2016 | Origins of Selectivity and General Model for Chiral Phosphor… | — |
| 6.7 | 备选 | hard-05 | 2023 | Computational study on the catalytic control of endo/exo Die… | ✅ |
| 6.6 | 备选 | hard-13 | 2022 | Chiral Phosphoric Acid Catalyzed Conversion of Epoxides into… | — |

### IMPOSSIBLE 梯队 —— 多参考态 / 开壳层（考察合理拒答；目标 20 题）

(12 篇｜PDF 在手 9｜候选反应标注 26 条)

| 综合分 | 档位 | ID | 年份 | 文献（短题名） | PDF |
|---|---|---|---|---|---|
| 9.8 | 必选 | impossible-01 | 2022 | Reference Energies for Cyclobutadiene: Automerization and Ex… | ✅ |
| 9.8 | 必选 | impossible-03 | 2018 | Full configuration interaction quantum Monte Carlo benchmark… | ✅ |
| 9.5 | 必选 | impossible-02 | 2025 | The Singlet-Triplet Gap of Cyclobutadiene: The CIPSI-Driven … | ✅ |
| 9.2 | 必选 | impossible-04 | 2019 | Singlet-Triplet Energy Gaps of Organic Biradicals and Polyac… | ✅ |
| 8.9 | 必选 | impossible-05 | 2020 | Large yet bounded: Spin gap ranges in carbenes | ✅ |
| 8.7 | 必选 | impossible-07 | 2024 | Excited state-specific CASSCF theory for the torsion of ethy… | ✅ |
| 8.4 | 推荐 | impossible-06 | 2021 | Quantum Monte Carlo Investigation of the H-transfer Reaction… | ✅ |
| 8.3 | 推荐 | impossible-09 | 2022 | Benchmarking the semi-stochastic CC(P;Q) approach for single… | — |
| 8.1 | 推荐 | impossible-08 | 1999 | Ab Initio and DFT Calculations on the Cope Rearrangement of … | — |
| 7.2 | 备选 | impossible-11 | 2020 | Extended dynamically weighted CASPT2: the best of two worlds | ✅ |
| 6.7 | 备选 | impossible-10 | 2023 | S-Diagnostic - An a Posteriori Error Assessment for Single-R… | — |
| 6.7 | 备选 | impossible-12 | 2023 | Multiconfigurational quantum chemistry: The CASPT2 method | ✅ |

> ✅ = 已下载 PDF；📚 = 本地另有存档；— = 付费墙仅元数据。

---

# EASY 梯队 —— 单步基元反应（重原子 ≤7，xTB 全流程可算；目标 30 题）

### easy-01｜综合 9.8【必选】｜2003

**A Standard Set of Pericyclic Reactions of Hydrocarbons for the Benchmarking of Computational Methods: The Performance of ab Initio, Density Functional, CASSCF, CASPT2, and CBS-QB3 Methods for the Prediction of Activation Barriers, Reaction Energetics, and Transition State Geometries**

- 作者：Vildan Guner、Kelli S. Khuong、Andrew G. Leach et al.（共 6 人）
- 出处：Journal of Physical Chemistry A, 107(51), 11445-11459
- DOI：[10.1021/jp035501w](https://doi.org/10.1021/jp035501w)
- 获取：✅ 已下载 PDF `2003_guner_pericyclic.pdf`（OA）
- 分项：体系适配 10｜参考数据 10｜测试价值 10｜可获取 9

**摘要**：Experimental and theoretical data are provided for a set of 11 pericyclic reactions of unsaturated hydrocarbons. Literature experimental data are evaluated and standardized to ΔH‡0K for comparison to theory. Hartree−Fock, MP2, CASSCF, CASPT2, density functional theory (B3LYP, BPW91, MPW1K, and KMLYP functionals), and CBS-QB3 transition-structure geometries, activation enthalpies and entropies, and reaction enthalpies and entropies for these reactions are reported and are compared to experimental results. For activation enthalpies, several density functionals rival CASPT2 and CBS-QB3 for closest agreement with experiment, while CASPT2 and CBS-QB3 provide the most accurate heats of reaction. Transition-structure geometries are reproduced well by all methods with the exception of the Cope rearrangement and cyclopentadiene dimerization transition structures.

**候选反应（7）**：
- Diels-Alder cycloaddition of butadiene + ethylene
- electrocyclic ring-opening of cyclobutene to 1,3-butadiene
- electrocyclic ring-opening of 1,3-cyclohexadiene to 1,3,5-hexatriene
- [1,5]-H sigmatropic shift in 1,3-pentadiene
- Cope rearrangement of 1,5-hexadiene
- ene reaction
- cyclopentadiene dimerization

**推荐理由**：全梯队最高优先：11 个周环反应实验活化焓已标准化到 ΔH‡0K，题目—真值链最完整，可直接出 5–8 道 Easy 题。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### easy-05｜综合 9.3【必选】｜2020

**A Unified Framework for Understanding Nucleophilicity and Protophilicity in the SN2/E2 Competition**

- 作者：Pascal Vermeeren、Thomas Hansen、Paul Jansen et al.（共 6 人）
- 出处：Chemistry - A European Journal, 26(67), 15538-15548
- DOI：[10.1002/chem.202003831](https://doi.org/10.1002/chem.202003831)
- 获取：✅ 已下载 PDF `2020_vermeerder_sn2e2.pdf`（OA）
- 分项：体系适配 10｜参考数据 9｜测试价值 9｜可获取 9

**摘要**：The concepts of nucleophilicity and protophilicity are fundamental and ubiquitous in chemistry. A case in point is bimolecular nucleophilic substitution (SN2) and base-induced elimination (E2). A Lewis base acting as a strong nucleophile is needed for SN2 reactions, whereas a protophile (i.e., base) is required for E2 reactions. A complicating factor is, however, the fact that a good nucleophile is often also a good protophile. Nevertheless, a sound, physical model that explains, in a transparent manner, when an electron-rich Lewis base acts as a nucleophile or as a protophile, which is not just phenomenological, is currently lacking in the literature. To address this question, the potential energy surfaces of SN2 and E2 reactions of X- + C2H5Y systems with X, Y = F, Cl, Br, I, At, were explored by using relativistic density functional theory at ZORA-OLYP/TZ2P. These explorations have yielded a consistent overview of reactivity trends over a wide range of reaction pathways. Activation strain analyses of these reactions reveal the factors that determine the shape of the potential energy surfaces and hence govern the propensity of the Lewis base to act as a nucleophile or protophile. The concepts of 'characteristic distortivity' and 'transition state acidity' of a reaction are introduced, which enable chemists to better understand and design synthesis.

**候选反应（4）**：
- F- + C2H5Cl SN2 backside attack
- F- + C2H5Cl E2 anti elimination
- Cl- + C2H5F SN2
- halide + ethyl halide SN2/E2 competition series (X,Y = F,Cl,Br,I)

**推荐理由**：SN2/E2 竞争教科书级体系，全势能面公开且有 PDF；卤素+乙基卤素系列可直接出题。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### easy-02｜综合 9.1【必选】｜2015

**Accurate reaction barrier heights of pericyclic reactions: Surprisingly large deviations for the CBS-QB3 composite method and their consequences in DFT benchmark studies**

- 作者：Amir Karton、Lars Goerigk（共 2 人）
- 出处：Journal of Computational Chemistry, 36(9), 622-632
- DOI：[10.1002/jcc.23837](https://doi.org/10.1002/jcc.23837)
- 获取：❌ 未下载（OA，仅元数据+摘要）
- 分项：体系适配 10｜参考数据 10｜测试价值 9｜可获取 6

**摘要**：Accurate barrier heights are obtained for the 26 pericyclic reactions in the BHPERI dataset by means of the high-level Wn-F12 thermochemical protocols. Very often, the complete basis set (CBS)-type composite methods are used in similar situations, but herein it is shown that they in fact result in surprisingly large errors with root mean square deviations (RMSDs) of about 2.5 kcal mol(-1). In comparison, other composite methods, particularly G4-type and estimated coupled cluster with singles, doubles, and quasiperturbative triple excitations [CCSD(T)/CBS] approaches, show deviations well below the chemical-accuracy threshold of 1 kcal mol(-1). With the exception of SCS-MP2 and the herein newly introduced MP3.5 approach, all other tested Møller-Plesset perturbative procedures give poor performance with RMSDs of up to 8.0 kcal mol(-1). The finding that CBS-type methods fail for barrier heights of these reactions is unexpected and it is particularly troublesome given that they are often used to obtain reference values for benchmark studies. Significant differences are identified in the interpretation and final ranking of density functional theory (DFT) methods when using the original CBS-QB3 rather than the new Wn-F12 reference values for BHPERI. In particular, it is observed that the more accurate Wn-F12 benchmark results in lower statistical errors for those methods that are generally considered to be robust and accurate. Two examples are the PW6B95-D3(BJ) hybrid-meta-general-gradient approximation and the PWPB95-D3(BJ) double-hybrid functionals, which result in the lowest RMSDs of the entire DFT study (1.3 and 1.0 kcal mol(-1), respectively). These results indicate that CBS-QB3 should be applied with caution in computational modeling and benchmark studies involving related systems.

**候选反应（4）**：
- butadiene + ethylene Diels-Alder cycloaddition
- cyclobutene ring-opening
- 1,3,5-hexatriene electrocyclization
- various [1,5]-H shifts and electrocyclic reactions in BHPERI set

**推荐理由**：BHPERI 26 能垒的 Wn-F12 真值比 Guner 2003 更新更准；虽付费墙，数值可通过本地 GMTKN55 子集交叉获取。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### easy-12｜综合 8.9【必选】｜2017

**A look at the density functional theory zoo with the advanced GMTKN55 database for general main group thermochemistry, kinetics and noncovalent interactions**

- 作者：Lars Goerigk、Andreas Hansen、Christoph Bauer et al.（共 6 人）
- 出处：Physical Chemistry Chemical Physics, 19, 32184-32215
- DOI：[10.1039/c7cp04913g](https://doi.org/10.1039/c7cp04913g)
- 获取：✅ 本地已有：`True`（未重复下载）
- 分项：体系适配 9｜参考数据 10｜测试价值 8｜可获取 9

**摘要**：We present the GMTKN55 benchmark database for general main group thermochemistry, kinetics and noncovalent interactions. Compared to its popular predecessor GMTKN30, it allows assessment across a larger variety of chemical problems - with 13 new benchmark sets being presented for the first time - and it also provides reference values of significantly higher quality for most sets. GMTKN55 comprises 1505 relative energies based on 2462 single-point calculations and it is accessible to the user community via a dedicated website. Herein, we demonstrate the importance of better reference values, and we re-emphasise the need for London-dispersion corrections in density functional theory (DFT) treatments of thermochemical problems, including Minnesota methods. We assessed 217 variations of dispersion-corrected and -uncorrected density functional approximations, and carried out a detailed analysis of 83 of them to identify robust and reliable approaches.

**候选反应（3）**：
- BHPERI pericyclic reactions subset
- BH76 barrier heights (H/ heavy-atom transfer)
- RC21 reaction energies of small organic reactions

**推荐理由**：GMTKN55 一站式汇总 BHPERI/BH76/RC21 等子集真值，本地已有 PDF；作为 Easy 梯队总真值库保留。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### easy-03｜综合 8.8【必选】｜2019

**Highly Accurate CCSDT(Q)/CBS Reaction Barrier Heights for a Diverse Set of Transition Structures: Basis Set Convergence and Cost-Effective Approaches for Estimating Post-CCSD(T) Contributions**

- 作者：Amir Karton（共 1 人）
- 出处：Journal of Physical Chemistry A, 123(31), 6720-6732
- DOI：[10.1021/acs.jpca.9b04611](https://doi.org/10.1021/acs.jpca.9b04611)
- 获取：❌ 未下载（OA，仅元数据+摘要）
- 分项：体系适配 10｜参考数据 10｜测试价值 8｜可获取 6

**摘要**：The ability to accurately calculate reaction barrier heights is of central importance to many areas of chemistry. We report an extensive study examining the basis set convergence of post-CCSD(T) contributions (up to CCSDT(Q)) for a diverse set of 28 reaction barrier heights. In contrast to previous studies, we focus here on larger transition structures (TSs) involving 4-7 non-hydrogen atoms. The set of reaction barrier heights includes pericyclic, bipolar cycloaddition, cycloreversion, and multiple-proton transfer reactions. We find that in most cases post-CCSD(T) contributions converge rapidly toward the basis set limit, such that even double-zeta and truncated double-zeta basis sets provide useful estimates of the T-(T) and (Q) contributions, respectively. In addition, we find that due to the tendency of these small basis sets to systematically underestimate the T-(T) and (Q) components, scaling is an effective approach for improving performance. For example, scaling the T-(T)/cc-pVDZ contribution by 1.25 results in an RMSD of merely 0.4 kJ mol-1 relative to basis set limit reference values from W3lite-F12 theory. Similarly, calculating the (Q) contribution with a cc-pVDZ basis set without d functions and scaling by 1.6 results in an RMSD of 0.5 kJ mol-1. We also examine the magnitude of post-CCSD(T) contributions for a wide range of TSs. We find that for pericyclic, bipolar cycloaddition, and multiple-proton transfer reactions there is an effective cancellation between the T-(T) and (Q) components (i.e., they have opposite signs and are of similar magnitude), such that overall post-CCSD(T) contributions to the reaction barrier heights are below ~1 kJ mol-1 (in absolute value). However, for the barrier heights of cycloreversion reactions, the T-(T) and (Q) components are both negative and large and consequentially post-CCSD(T) contributions reduce the reaction barrier heights by significant amounts ranging between 4.1 and 6.7 kJ mol-1.

**候选反应（4）**：
- pericyclic reactions with 4-7 non-hydrogen atom TSs
- 1,3-dipolar (bipolar) cycloadditions
- cycloreversion reactions
- multiple proton-transfer reactions

**推荐理由**：28 个 CCSDT(Q)/CBS 能垒且刻意限定 4–7 个非氢原子过渡态，与 Easy 定义逐字吻合，适合作高精度参考值层。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### easy-07｜综合 8.8【必选】｜2023

**Effects of Methyl Substitution and Leaving Group on E2/SN2 Competition for Reactions of F- with RY (R = CH3, C2H5, iC3H7, tC4H9; Y = Cl, I)**

- 作者：Wenqing Zhen、Siwei Zhao、Gang Fu et al.（共 7 人）
- 出处：Molecules, 28(17), 6269
- DOI：[10.3390/molecules28176269](https://doi.org/10.3390/molecules28176269)
- 获取：✅ 已下载 PDF `2023_zhen_e2sn2.pdf`（OA）
- 分项：体系适配 10｜参考数据 8｜测试价值 8｜可获取 9

**摘要**：The competition between bimolecular nucleophilic substitution (SN2) and elimination (E2) is a classic topic in physical organic chemistry. In this work, the E2/SN2 competition for the gas-phase reactions of F- with RY (R = CH3, C2H5, iC3H7, tC4H9; Y = Cl, I) is systematically investigated by quantum chemical calculations and ab initio molecular dynamics simulations, focusing on the effects of methyl substitution and the leaving group. (Abstract abridged from the MDPI landing page; see PDF for full text.)

**候选反应（4）**：
- F- + CH3Cl SN2 (methyl fluoride formation)
- F- + CH3I SN2
- F- + C2H5Cl E2 vs SN2 competition
- F- + iC3H7Cl E2 vs SN2 competition

**推荐理由**：最小体系 F−+CH3Cl 仅 3 重原子，金色 OA 数据完整；与 easy-05 组成甲基取代/离去基效应梯度。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### easy-06｜综合 8.7【必选】｜2023

**Reaction profiles for quantum chemistry-computed [3 + 2] cycloaddition reactions**

- 作者：Thijs Stuyver、Kjell Jorner、Connor W. Coley（共 3 人）
- 出处：Scientific Data, 10, 66
- DOI：[10.1038/s41597-023-01977-8](https://doi.org/10.1038/s41597-023-01977-8)
- 获取：✅ 已下载 PDF `2023_stuyver_32cycloaddition.pdf`（OA）
- 分项：体系适配 9｜参考数据 9｜测试价值 8｜可获取 9

**摘要**：Bio-orthogonal click chemistry based on [3 + 2] dipolar cycloadditions has had a profound impact on the field of biochemistry and significant effort has been devoted to identify promising new candidate reactions for this purpose. To gauge whether a prospective reaction could be a suitable bio-orthogonal reaction, information about both on- and off-target activation and reaction energies is highly valuable. Here, we use an automated workflow, based on the autodE program, to compute over 5000 reaction profiles for [3 + 2] cycloadditions involving both synthetic dipolarophiles and a set of biologically-inspired structural motifs. Based on a succinct benchmarking study, the B3LYP-D3(BJ)/def2-TZVP//B3LYP-D3(BJ)/def2-SVP level of theory was selected for the DFT calculations, and standard conditions and an (aqueous) SMD model were imposed to mimic physiological conditions. We believe that this data, as well as the presented workflow for high-throughput reaction profile computation, will be useful to screen for new bio-orthogonal reactions, as well as for the development of novel machine learning models for the prediction of chemical reactivity more broadly.

**候选反应（4）**：
- ozone + ethylene [3+2] cycloaddition (primary ozonide formation)
- nitrone + ethylene cycloaddition
- azide + ethylene cycloaddition
- small dipole + ethylene prototype cycloadditions

**推荐理由**：5000+ 自动化 [3+2] 剖面数据库（Sci Data），小型原型子集即取即用，还可与本项目自动剖面流程对标。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### easy-09｜综合 8.5【必选】｜2005

**Benchmark Database of Barrier Heights for Heavy Atom Transfer, Nucleophilic Substitution, Association, and Unimolecular Reactions and Its Use to Test Theoretical Methods**

- 作者：Yan Zhao、Nuria Gonzalez-Garcia、Donald G. Truhlar（共 3 人）
- 出处：Journal of Physical Chemistry A, 109(9), 2012-2018
- DOI：[10.1021/jp045141s](https://doi.org/10.1021/jp045141s)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 9｜参考数据 10｜测试价值 8｜可获取 6

**摘要**：A benchmark database of forward and reverse barrier heights for 19 non-hydrogen-transfer reactions has been developed by using Weizmann 1 calculations, and 29 DFT methods and 6 ab initio wave-function theory (WFT) methods have been tested against the new database as well as against an older database for hydrogen atom transfer reactions. Among the hybrid DFT methods without kinetic energy density, MPW1K is the most accurate model for calculating barrier heights. Among the meta methods, BB1K and MPWB1K are the two best models. Overall, the results show that BB1K is the best DFT model for calculating barrier heights, followed in order by MPW1K, MPWKCIS1K, B1B95, MPW1B95, BH&HLYP, B97-2, mPW1PW91, and B98. The popular B3LYP method has a mean unsigned error four times larger than BB1K. Of the methods tested, QCISD(T) is the best WFT model for barrier height calculations, and QCISD is second best, but both are outperformed by the BB1K, MPWB1K, and MPW1K methods.

**候选反应（6）**：
- H + N2O -> OH + N2 (heavy atom transfer)
- CH3 + FCl -> CH3F + Cl (atom transfer)
- F- + CH3F identity SN2
- Cl- + CH3Cl identity SN2
- HNC -> HCN unimolecular isomerization
- cyclopropyl radical ring-opening type unimolecular reactions

**推荐理由**：NHTBH38/04 是原子转移/SN2 类经典真值库；付费墙但全部数值收录于 GMTKN55（本地已有）。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### easy-08｜综合 7.6【推荐】｜2018

**DFT Study To Explore the Importance of Ring Size and Effect of Solvents on the Keto-Enol Tautomerization Process of α- and β-Cyclodiones**

- 作者：Kalyanashis Jana、Bishwajit Ganguly（共 2 人）
- 出处：ACS Omega, 3(10), 13095-13103
- DOI：[10.1021/acsomega.8b01008](https://doi.org/10.1021/acsomega.8b01008)
- 获取：✅ 已下载 PDF `2018_jana_ketoenol.pdf`（OA）
- 分项：体系适配 8｜参考数据 7｜测试价值 7｜可获取 9

**摘要**：We have explored the effect of ring size on the keto-enol tautomerization of α- and β-cyclodiones using M062X-SMD(aq)/6-31+G(d,p)//M062X/6-31+G(d,p) level of theory. The calculated results show that the activation free energy barrier for the keto-enol process of α-cyclopropanedione (1) is 54.9 kcal/mol, which is lower compared to other cyclic diketo systems studied here. The four-membered β-cyclobutanedione (2) does not favor keto-enol tautomerization unlike 1 because of the ring strain developed in the transition-state geometries and their corresponding products. Water-assisted tautomerization with one water molecule reveals that the barriers reduce to almost half of those of the uncatalyzed systems. The two-water-assisted process is more favorable as the barriers are lowered by ~10 kcal/mol than the one-water-assisted process. The ion-pair formation seems to govern the barrier lowering with two water molecules during the process, however, it also overcomes the aromatization driving force of the three-membered ring system. (Abridged from the ACS Omega abstract.)

**候选反应（3）**：
- alpha-cyclopropanedione keto-enol tautomerization (gas phase)
- water-assisted keto-enol tautomerization of cyclopropanedione (1H2O, 2H2O)
- beta-cyclobutanedione keto-enol tautomerization

**推荐理由**：小环二酮 keto-enol 含水催化通道，机理略超'单步'定义但仍属 Easy；互变异构类补充。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### easy-04｜综合 7.0【备选】｜2021

**Accuracy of DLPNO-CCSD(T): Effect of Basis Set and System Size**

- 作者：Isolde Sandler、Junbo Chen、Mackenzie Taylor et al.（共 5 人）
- 出处：Journal of Physical Chemistry A, 125(7), 1553-1563
- DOI：[10.1021/acs.jpca.0c11270](https://doi.org/10.1021/acs.jpca.0c11270)
- 获取：❌ 未下载（OA，仅元数据+摘要）
- 分项：体系适配 8｜参考数据 8｜测试价值 6｜可获取 5

**摘要**：The DLPNO-CCSD(T) method is designed to study large molecular systems at significantly reduced cost relative to its canonical counterpart. However, the error in this approach is also size-extensive and relies on cancellation of errors for the calculation of relative energies. This work provides a direct comparison of canonical CCSD(T) and TightPNO DLPNO-CCSD(T) calculations of reaction energies and barriers of a broad range of chemical reactions. The dataset includes acidities, anion binding affinities, enolization, Diels-Alder, nucleophilic substitution, and atom transfer reactions and complements existing theoretical datasets in terms of system size as well as new reaction types (e.g., anion binding affinities and chlorine atom transfer reactions). The performance of DLPNO-CCSD(T) was further examined with respect to systematic variation of basis set and system size and amounts of nonbonded interaction present in the system. The errors in the DLPNO-CCSD(T) were found to be relatively insensitive to the choice of basis set for small systems but increase monotonically with system size. Additionally, calculations of barriers appear to be more challenging than reaction energies with errors exceeding 5 kJ mol-1 for many Diels-Alder reactions. Further tests on three realistic organic reactions reveal the impact of the DLPNO approximation in calculating absolute and relative barriers that are important for predictions such as stereoselectivity.

**候选反应（4）**：
- enolization (keto-enol) reactions
- small Diels-Alder reactions
- gas-phase nucleophilic substitution (SN2)
- chlorine/hydrogen atom transfer reactions

**推荐理由**：方法学论文，数据集可反查但反应条目零散；仅作参考能垒补充源。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### easy-11｜综合 6.8【备选】｜2021

**autodE: Automated Calculation of Reaction Energy Profiles - Application to Organic and Organometallic Reactions**

- 作者：Tom A. Young、Joseph J. Silcock、Alistair J. Sterling et al.（共 4 人）
- 出处：Angewandte Chemie International Edition, 60(8), 4266-4274
- DOI：[10.1002/anie.202011941](https://doi.org/10.1002/anie.202011941)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 7｜参考数据 6｜测试价值 7｜可获取 7

**摘要**：Calculating reaction energy profiles to aid in mechanistic elucidation has long been the domain of the expert computational chemist. Here, we introduce autodE (https://github.com/duartegroup/autodE), an open-source Python package capable of locating transition states (TSs) and minima and delivering a full reaction profile from 1D or 2D chemical representations. autodE is broadly applicable to the study of organic and organometallic reaction classes, including addition, substitution, elimination, migratory insertion, oxidative addition, and reductive elimination; it accounts for conformational sampling of both TSs and minima and is compatible with many electronic structure packages. The general applicability of autodE is demonstrated with complex multi-step reactions, including cobalt- and rhodium-catalyzed hydroformylation and the Ireland-Claisen rearrangement.

**候选反应（3）**：
- small-molecule addition reactions (e.g., HX addition to alkenes)
- substitution reactions
- elimination reactions

**推荐理由**：autodE 工具论文——与基准 Agent 的自动剖面流程直接同构，方法学对照价值大于选题价值。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### easy-10｜综合 6.3【备选】｜2016

**How Accurate Are the Minnesota Density Functionals for Noncovalent Interactions, Isomerization Energies, Thermochemistry, and Barrier Heights Involving Molecules Composed of Main-Group Elements?**

- 作者：Narbe Mardirossian、Martin Head-Gordon（共 2 人）
- 出处：Journal of Chemical Theory and Computation, 12(9), 4303-4325
- DOI：[10.1021/acs.jctc.6b00637](https://doi.org/10.1021/acs.jctc.6b00637)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 7｜参考数据 8｜测试价值 5｜可获取 5

**摘要**：The 14 Minnesota density functionals published between the years 2005 and early 2016 are benchmarked on a comprehensive database of 4986 data points (84 data sets) involving molecules composed of main-group elements. The database includes noncovalent interactions, isomerization energies, thermochemistry, and barrier heights, as well as equilibrium bond lengths and equilibrium binding energies of noncovalent dimers. Additionally, the sensitivity of the Minnesota density functionals to the choice of basis set and integration grid is explored for both noncovalent interactions and thermochemistry. Overall, the main strength of the hybrid Minnesota density functionals is that the best ones provide very good performance for thermochemistry (e.g., M06-2X), barrier heights (e.g., M08-HX, M08-SO, MN15), and systems heavily characterized by self-interaction error (e.g., M06-2X, M08-HX, M08-SO, MN15), while the main weakness is that none of them are state-of-the-art for the full spectrum of noncovalent interactions and isomerization energies (although M06-2X is recommended from the 10 hybrid Minnesota functionals). Similarly, the main strength of the local Minnesota density functionals is that the best ones provide very good performance for thermochemistry (e.g., MN15-L), barrier heights (e.g., MN12-L), and systems heavily characterized by self-interaction error (e.g., MN12-L and MN15-L), while the main weakness is that none of them are state-of-the-art for the full spectrum of noncovalent interactions and isomerization energies (although M06-L is clearly the best from the four local Minnesota functionals). As an overall guide, M06-2X and MN15 are perhaps the most broadly useful hybrid Minnesota functionals, while M06-L and MN15-L are perhaps the most broadly useful local Minnesota functionals, although each has different strengths and weaknesses.

**候选反应（3）**：
- HTBH38 hydrogen transfer reactions (e.g., H + CH4, H + C2H6)
- NHTBH38 non-hydrogen transfer small reactions
- BHPERI pericyclic reactions subset

**推荐理由**：大型泛函评测元基准，自身不提供新反应体系；仅在需要更多参考点时反查。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

# NORMAL 梯队 —— 多步机理 / 竞争路径（中等分子；目标 30 题）

### normal-06｜综合 8.7【必选】｜2018

**A Molecular Electron Density Theory Study of the Competitiveness of Polar Diels-Alder and Polar Alder-ene Reactions**

- 作者：Luis R. Domingo、Mar Rios-Gutierrez、Patricia Perez（共 3 人）
- 出处：Molecules
- DOI：[10.3390/molecules23081913](https://doi.org/10.3390/molecules23081913)
- 获取：✅ 已下载 PDF `2018_domingo_polar_da_ene.pdf`（OA）
- 分项：体系适配 9｜参考数据 9｜测试价值 8｜可获取 9

**摘要**：The competitiveness of the BF3 Lewis acid (LA) catalyzed polar Diels-Alder (P-DA) and polar Alder-ene (P-AE) reactions of 2-methyl-1,3-butadiene, a diene possessing an allylic hydrogen, with formaldehyde has been studied within the Molecular Electron Density Theory (MEDT) at the MPWB1K/6-311G(d,p) computational level. Coordination of BF3 LA to the oxygen of formaldehyde drastically accelerates both reactions given the high electrophilic character of the BF3:formaldehyde complex. As a consequence, these reactions present a very low activation enthalpy - less than 2.2 kcal/mol - thus becoming competitive. In dioxane, the P-AE reaction is slightly favored because of the larger polar character of the corresponding transition state structure (TS). In addition, the Prins reaction between hexahydrophenanthrene and the BF3:formaldehyde complex has also been studied as a computational model of an experimental P-AE reaction. For this LA-catalyzed reaction, the P-DA reaction presents very high activation energy because of the aromatic character of the dienic framework. The present MEDT study allows establishing the similarity of the TSs associated with the formation of the C-C single bond in both reactions, as well as the competitiveness between P-AE and P-DA reactions when the diene substrate possesses at least one allylic hydrogen, thus making it necessary to be considered by experimentalists in highly polar processes. In this work, the term 'pseudocyclic selectivity' is suggested to connote the selective formation of structural isomers through stereoisomeric pseudocyclic TSs.

**候选反应（2）**：
- BF3-catalyzed reaction of 2-methyl-1,3-butadiene with formaldehyde: polar Diels-Alder vs polar Alder-ene
- Prins reaction of hexahydrophenanthrene with BF3:formaldehyde complex

**推荐理由**：同一反应对两条通道（极性 DA vs 极性 ene）完整能量剖面，OA 有 PDF，竞争路径题的标准配置。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### normal-08｜综合 8.7【必选】｜2024

**A New Insight into the Molecular Mechanism of the Reaction between 2-Methoxyfuran and Ethyl (Z)-3-phenyl-2-nitroprop-2-enoate: A Molecular Electron Density Theory (MEDT) Computational Study**

- 作者：Mikolaj Sadowski、Ewa Dresler、Aneta Wroblewska et al.（共 4 人）
- 出处：Molecules
- DOI：[10.3390/molecules29204876](https://doi.org/10.3390/molecules29204876)
- 获取：✅ 已下载 PDF `2024_sadowski_methoxyfuran.pdf`（OA）
- 分项：体系适配 9｜参考数据 8｜测试价值 9｜可获取 9

**摘要**：The molecular mechanism of the reaction between 2-methoxyfuran and ethyl (Z)-3-phenyl-2-nitroprop-2-enoate was investigated using wB97XD/6-311+G(d,p) (PCM) quantum chemical calculations. It was found that the most probable reaction mechanism is fundamentally different from what was previously postulated. In particular, six possible zwitterionic intermediates were detected on the reaction pathway. Their formation is determined by the nature of local nucleophile/electrophile interactions. Additionally, the channel involving the formation of the exo-nitro Diels-Alder cycloadduct was completely ruled out. Finally, the electronic nature of the five- and six-membered nitronates as potential TACs was evaluated.

**候选反应（2）**：
- reaction of 2-methoxyfuran with ethyl (Z)-3-phenyl-2-nitroprop-2-enoate
- zwitterionic stepwise vs concerted Diels-Alder channels in furan-nitroalkene cycloaddition

**推荐理由**：已发表机理被推翻+显式排除 DA 通道，假设淘汰素材最丰富的一篇；中等尺寸呋喃-硝基烯烃体系对 xTB/DFT 流水线友好，OA。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### normal-07｜综合 8.2【推荐】｜2025

**Unveiling the Role of the Lewis Acids in the Acceleration of Alder-Ene Reactions: A Molecular Electron Density Theory Study**

- 作者：Luis R. Domingo、Patricia Perez（共 2 人）
- 出处：Molecules
- DOI：[10.3390/molecules30214289](https://doi.org/10.3390/molecules30214289)
- 获取：✅ 已下载 PDF `2025_domingo_lewis_acid_ene.pdf`（OA）
- 分项：体系适配 8｜参考数据 8｜测试价值 8｜可获取 9

**摘要**：The electronic effects of Lewis acids (LAs) in reducing the activation energies of Alder-ene (AE) reactions have been studied within the Molecular Electron Density Theory (MEDT). To this end, the AE reactions of 2-methylbutadiene (2MBD) with formaldehyde (CHO) in the presence of three LAs with increasing acidic character, BH3, BF3, and AlCl3, have been studied. Topological analysis of the electron density and the evaluation of the DFT-based reactivity indices indicate that LAs do not modify the electronic structure of the carbonyl group but markedly increase the electrophilic character of CHO. LAs not only strongly accelerate the AE reactions, but also modify the molecular mechanisms, changing them from a non-concerted two-stage one-step mechanism to a two-step one. Topological analyses of the electron density at the transition state structures (TSs) indicate that while the formation of the new C-C single bond has begun, the departure of the hydrogen has not yet started. A Relative Interacting Atomic Energy (RIAE) analysis of the activation energies allows the establishment of the electronic effects of LAs on the AE reactions. LAs increase the global electron density transfer (GEDT) occurring in polar AE reactions; this phenomenon markedly stabilizes the CHO framework at the TSs, decreasing the RIAE relative energies.

**候选反应（2）**：
- Alder-ene reaction of 2-methylbutadiene with formaldehyde
- Lewis acid (BH3/BF3/AlCl3) modulated one-step vs two-step Alder-ene mechanism

**推荐理由**：三种 Lewis 酸引起机理切换（两阶段一步 vs 分步），催化剂调制变量设计良好，OA。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### normal-01｜综合 7.8【推荐】｜2007

**Mechanism of the Morita-Baylis-Hillman Reaction: A Computational Investigation**

- 作者：Raphael Robiette、Varinder K. Aggarwal、Jeremy N. Harvey（共 3 人）
- 出处：Journal of the American Chemical Society
- DOI：[10.1021/ja0717865](https://doi.org/10.1021/ja0717865)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 8｜参考数据 8｜测试价值 9｜可获取 5

**摘要**：Accurate calculations are presented on the mechanism of the MBH reaction, focusing on the reaction between methyl acrylate and benzaldehyde, catalyzed by a tertiary amine. We address the mechanism under protic solvent-free conditions, but also consider how the mechanism and rate-limiting step change in the presence of alcohols. We have carefully calibrated the DFT method used in the calculations by carrying out high-level G3MP2 calculations on a model system. All of our calculations also treat the effect of solvent, described as a dielectric continuum. In the absence of protic solvent, we predict that deprotonation of the alpha-position is the rate-determining step and occurs through a cyclic transition state, with proton transfer to a hemiacetal alkoxide formed by addition of a second equivalent of aldehyde to the intermediate alkoxide. As first suggested by McQuade, this mechanism explains the observed second-order kinetics with respect to aldehyde concentration in the absence of protic solvent. In contrast, in the presence of methanol, we find a slightly lower energy pathway, in which the alcohol serves as a shuttle to transfer the proton from carbon to oxygen. Overall, the barrier to reaction for the latter mechanism is of 24.6 kcal/mol with respect to reactants at the B3LYP level of theory. The relative energy of the transition state for addition of the amine-acrylate betaine adduct to the aldehyde is much lower, at 16.0 kcal/mol relative to reactants, so C-C bond formation should not be rate-limiting, except perhaps for some aliphatic aldehydes or imines. We discuss implications for the design of asymmetric versions of the MBH reaction, given the overwhelming importance of the proton-transfer step.

**候选反应（2）**：
- DABCO-catalyzed Morita-Baylis-Hillman reaction of methyl acrylate with benzaldehyde
- MeOH-shuttled vs second-aldehyde-shuttled proton transfer in MBH

**推荐理由**：MBH 三步机理+两类质子转移通道竞争，假设淘汰型考题的经典素材；体系中等偏大但 DFT 可算。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### normal-02｜综合 7.8【推荐】｜2019

**Dissection of the Mechanism of the Wittig Reaction**

- 作者：Paola Farfan、Sara Gomez、Albeiro Restrepo（共 3 人）
- 出处：The Journal of Organic Chemistry
- DOI：[10.1021/acs.joc.9b02224](https://doi.org/10.1021/acs.joc.9b02224)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 8｜参考数据 8｜测试价值 9｜可获取 5

**摘要**：A wide variety of descriptors of the evolution of bonding, rooted in the formalism of quantum mechanics, but otherwise conceptually and methodologically independent of each other (QTAIM, NBO, based), consistently indicate that in the mechanism of the salt-free Wittig reaction, regardless of the nature of the ylide, regardless of the nature of the transition state, and regardless of the positioning of the substituents around the reactive center, the degree of advance in the formation of the emerging C-C bond as early as at the transition state for the oxaphosphetane formation step is firmly tied to the stereochemistry of the final alkene. In addition to the fast evolution of the emerging C-C bond, very early in the reaction, a long range, weak interaction between a lone pair in the oxygen atom of the carbonyl group and an empty p orbital in the phosphorous atom, resulting from the polarization of the P=C bond in the ylide (nO -> pi*(P=C)), clamps the P=C and C=O bonds to the positions required for the subsequent formation of oxaphosphetanes, thus explaining the formation of the cyclic intermediates rather than betaines. Each step of the Wittig reaction is a highly asynchronous process.

**候选反应（3）**：
- salt-free Wittig reaction of a phosphorus ylide with an aldehyde
- oxaphosphetane formation vs betaine pathway in Wittig reaction
- oxaphosphetane cycloreversion to alkene + phosphine oxide

**推荐理由**：Wittig 机理剖析权威文献，加成/氧磷杂环丁烷/环消除三段式结构清晰，适合多步路径排序题。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### normal-04｜综合 7.8【推荐】｜2018

**Can the Radical Channel Contribute to the Catalytic Cycle of N-Heterocyclic Carbene in Benzoin Condensation?**

- 作者：Ming-Hsiu Hsieh、Gou-Tao Huang、Jen-Shiang K. Yu（共 3 人）
- 出处：The Journal of Organic Chemistry
- DOI：[10.1021/acs.joc.8b02483](https://doi.org/10.1021/acs.joc.8b02483)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 8｜参考数据 8｜测试价值 9｜可获取 5

**摘要**：NHC can catalyze benzoin condensation via the key Breslow intermediate. EPR spectroscopy recently confirmed the existence of the radical species, but its catalytic role is still unclear. Herein, we use density functional approaches to study the radical-associated pathway in comparison with the nonradical mechanism reported previously. Theoretical investigations show that the nonradical path (Delta G = 18.7 kcal/mol) is more kinetically favorable than the radical route (Delta G = 27.6 kcal/mol), which is initialized by the hydrogen abstraction from the Breslow intermediate by benzaldehyde, leading to a radical pair. The product formation is thus dominated by the nonradical pathway. In addition, the Breslow intermediate is less stable than its keto form, which blocks the benzoin condensation, and the radical species could play an important role in assisting the tautomerization and promoting the catalytic reaction.

**候选反应（2）**：
- NHC-catalyzed benzoin condensation of benzaldehyde (Breslow mechanism)
- radical-pair channel vs ionic channel in benzoin condensation

**推荐理由**：离子 vs 自由基通道定量能垒对比（18.7 vs 27.6 kcal/mol），标准假设淘汰题模板。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### normal-12｜综合 7.6【推荐】｜2023

**Automated Exploration of Reaction Networks and Mechanisms Based on Metadynamics Nanoreactor Simulations**

- 作者：Yutai Zhang、Chao Xu、Zhenggang Lan（共 3 人）
- 出处：Journal of Chemical Theory and Computation
- DOI：[10.1021/acs.jctc.3c00752](https://doi.org/10.1021/acs.jctc.3c00752)
- 获取：✅ 已下载 PDF `2023_zhang_nanoreactor.pdf`（OA）
- 分项：体系适配 7｜参考数据 7｜测试价值 8｜可获取 9

**摘要**：We developed an automated approach to construct a complex reaction network and explore the reaction mechanisms for numerous reactant molecules by integrating several theoretical approaches. Nanoreactor-type molecular dynamics was used to generate possible chemical reactions, in which the metadynamics was used to overcome the reaction barriers, and the semiempirical GFN2-xTB method was used to reduce the computational cost. Reaction events were identified from trajectories using the hidden Markov model based on the evolution of the molecular connectivity. This provided the starting points for further transition-state searches at the electronic structure levels of density functional theory to obtain the reaction mechanism. Finally, the entire reaction network containing multiple pathways was built. The feasibility and efficiency of the automated construction of the reaction network were investigated using the HCHO and NH3 bimolecular reaction and the reaction network for a multispecies system comprising dozens of HCN and H2O molecules. The results indicated that the proposed approach provides a valuable and effective tool for the automated exploration of the reaction networks.

**候选反应（2）**：
- HCHO + NH3 bimolecular reaction network (imine/hydroxymethanamine formation pathways)
- HCN + H2O multispecies reaction network exploration

**推荐理由**：自动反应网络探索的对照组文献，HCHO+NH3 网络小而全，可作'网络级'扩展题型试点。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### normal-11｜综合 7.5【推荐】｜2024

**Insights into the Mechanism, Selectivity, and Substituent Effects in the Diels-Alder Reaction of Azatrienes with Electron-rich Dienophiles: An MEDT Study**

- 作者：Amine Rafik、Abdeljabbar Jaddi Mohammed Salah、Najia Komiha et al.（共 5 人）
- 出处：Journal of Molecular Graphics and Modelling
- DOI：[10.1016/j.jmgm.2024.108819](https://doi.org/10.1016/j.jmgm.2024.108819)
- 获取：✅ 已下载 PDF `2024_rafik_azatriene_dielsalder.pdf`（OA）
- 分项：体系适配 8｜参考数据 7｜测试价值 7｜可获取 8

**摘要**：The reactivity and mechanistic intricacies of azatrienes in Diels-Alder reactions have been relatively unexplored despite their intriguing potential applications. In this study, we employ Molecular Electron Density Theory to theoretically investigate the hetero-Diels-Alder reaction involving azatrienes with ethyl vinyl ether and allenyl methyl ether. Analysis of Conceptual Density Functional Theory, energetic profiles, and the topological characteristics is conducted to elucidate the reactions. The revealed mechanism manifests as a polar one-step two-stages process under kinetic control. We establish a clear relationship of between the periselectivity, regioselectivity, and stereoselectivity on one hand and the characteristics of the reactions mechanism on the other hand. The influence of weak interactions on reaction activation barriers and bonding evolution are discussed in detail. We demonstrate that substituents enhancing the reverse electron density flux facilitate the feasibility of the reactions. The results lay ground for a meticulous control of the reaction of azatriene in similar synthetic scenarios.

**候选反应（2）**：
- hetero-Diels-Alder reaction of azatrienes with ethyl vinyl ether
- hetero-Diels-Alder reaction of azatrienes with allenyl methyl ether (peri-/regioselectivity competition)

**推荐理由**：氮杂双烯体 HDA 的 peri/区域/立体三重选择性竞争，arXiv 版可得，异原子体系扩展的好素材。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### normal-03｜综合 7.3【备选】｜2020

**A Close Look to the Oxaphosphetane Formation along the Wittig Reaction: A [2+2] Cycloaddition?**

- 作者：E. Chamorro、Mario Duque-Norena、Nestor Gutierrez-Sanchez et al.（共 5 人）
- 出处：The Journal of Organic Chemistry
- DOI：[10.1021/acs.joc.0c00697](https://doi.org/10.1021/acs.joc.0c00697)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 8｜参考数据 7｜测试价值 8｜可获取 5

**摘要**：The Wittig reaction between triphenylphosphine methylide and benzaldehyde has been studied both from conceptual and computational approaches. The supernucleophilic character of ylide accounts for the feasibly of the initial nucleophilic attack. The nature of bonding driving the formation of the first oxaphosphetane (OPA) intermediate in such a domino reaction, is examined within a topological-based bonding evolution theory perspective. The sequence of the electronic flow associated to the changes in electron density support a rationalization via two main electronic stages characterizing the single kinetic step: first, the C-C bond formation, which takes place via donation of electron density of the ylide carbon to the carbonyl carbon of benzaldehyde at a C-C distance of 2.02 A, is formally associated to the transition state region; then, the P-O bond formation via the donation of electron density of the non-bonding region of the carbonyl oxygen to phosphorus at a P-O distance of 2.06 A, is located at the end of the reaction path. The detailed picture of bonding patterns suggests that the OPA formation in the Wittig mechanism can be better understood in terms of a two-stage one-step mechanism beyond molecular orbital considerations behind the traditionally accepted [2+2] cycloaddition proposal.

**候选反应（2）**：
- Wittig reaction of triphenylphosphine methylide with benzaldehyde
- oxaphosphetane formation: concerted [2+2] vs two-stage one-step pathway

**推荐理由**：与 normal-02 配套的'[2+2] 还是两阶段一步'争议点，单独成题价值稍低，建议合并使用。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### normal-09｜综合 7.2【备选】｜2019

**Reactive Atomistic Simulations of Diels-Alder Reactions: the Importance of Molecular Rotations**

- 作者：Uxia Rivero、Oliver T. Unke、Markus Meuwly et al.（共 4 人）
- 出处：The Journal of Chemical Physics
- DOI：[10.1063/1.5114981](https://doi.org/10.1063/1.5114981)
- 获取：✅ 已下载 PDF `2019_rivero_dielsalder_dynamics.pdf`（OA）
- 分项：体系适配 7｜参考数据 7｜测试价值 7｜可获取 8

**摘要**：The Diels-Alder reaction between 2,3-dibromo-1,3-butadiene and maleic anhydride has been studied by means of multisurface adiabatic reactive molecular dynamics and the PhysNet neural network architecture. This system is used as a prototype to explore the concertedness, synchronicity and possible ways of promotion of Diels-Alder reactions. Analysis of the minimum dynamic path indicates that rotational energy is crucial (~65%) to drive the system towards the transition state in addition to collision energy (~20%). Comparison with the reaction of butadiene and maleic anhydride shows that the presence of bromine substituents in the diene accentuates the importance of rotational excitation to promote the reaction. At the high total energies at which reactive events are recorded, the reaction is found to be direct and mostly synchronous.

**候选反应（2）**：
- Diels-Alder reaction of 2,3-dibromo-1,3-butadiene with maleic anhydride
- Diels-Alder reaction of butadiene with maleic anhydride (synchronicity comparison)

**推荐理由**：动力学模拟视角考察同步性；静态基准只取其能垒数据，动态结论本项目暂不考核。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### normal-05｜综合 7.0【备选】｜2018

**CASSCF Calculations Reveal Competitive Chair (Pericyclic) and Boat (Pseudopericyclic) Transition States for the [3,3] Sigmatropic Rearrangement of Allyl Esters**

- 作者：Henry W. Kreiman、Mackenzie E. Batali、C. Jamieson et al.（共 5 人）
- 出处：The Journal of Organic Chemistry
- DOI：[10.1021/acs.joc.7b02316](https://doi.org/10.1021/acs.joc.7b02316)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 7｜参考数据 7｜测试价值 8｜可获取 5

**摘要**：(10,8)CASPT2/6-31G**//(10,8)CASSCF/6-31G** and CCSD(T)/cc-pVDZ//(10,8)-CASSCF/6-31G** calculations have been performed on the potential surface for the [3,3] sigmatropic allyl ester rearrangements of cis-3-penten-2-yl acetate (16) to trans-3-penten-2-yl acetate (17) and 3-buten-2-yl acetate (21) to trans-2-buten-1-yl acetate (22). The results are compared to the DFT (B3LYP/6-31G**) calculations on the known 16 -> 17 rearrangement that reported it to be concerted and pseudopericyclic through a boat-shaped transition structure (Birney, D. M. et al. J. Am. Chem. Soc. 2009, 131, 528-537). The CASSCF calculations, on the other hand, uncovered competitive concerted pathways for both the 16 -> 17 and 21 -> 22 rearrangements, though it was necessary to apply certain approximations in the former case. While one CASSCF pathway in each case involves a boat-shaped structure, similar to that located through DFT calculations, the other involves a chair-shaped structure. Preference for the chair or boat is shown to be method dependent. Moreover, examination of the active-space CASSCF orbitals clearly confirms that the boat-shaped transition structures are pseudopericyclic, but significantly also established that the chair-shaped transition structures are pericyclic. Conclusions based on these results, regarding our understanding of pericyclic vs pseudopericyclic reactions, are proffered.

**候选反应（2）**：
- [3,3] sigmatropic rearrangement of cis-3-penten-2-yl acetate
- chair (pericyclic) vs boat (pseudopericyclic) transition states in allyl ester rearrangement

**推荐理由**：结论依赖 CASSCF，单参考流程可能无法复现判据——更适合挪入 Impossible 作方法依赖性讨论，故降为备选。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### normal-10｜综合 6.6【备选】｜2020

**Reactive Atomistic Simulations of Diels-Alder-type Reactions: Conformational and Dynamic Effects in the Polar Cycloaddition of 2,3-Dibromobutadiene Radical Ions with Maleic Anhydride**

- 作者：Uxia Rivero、Haydar Taylan Turan、Markus Meuwly et al.（共 4 人）
- 出处：Molecular Physics
- DOI：[10.1080/00268976.2020.1825852](https://doi.org/10.1080/00268976.2020.1825852)
- 获取：✅ 已下载 PDF `2020_rivero_ionic_dielsalder.pdf`（OA）
- 分项：体系适配 6｜参考数据 6｜测试价值 7｜可获取 8

**摘要**：The kinetics, dynamics and conformational specificities for the ionic Diels-Alder reaction (polar cycloaddition) of maleic anhydride with 2,3-dibromobutadiene radical ions have been studied theoretically using multisurface adiabatic reactive molecular dynamics. A competition of concerted and stepwise reaction pathways was found and both the s-cis and s-trans conformers of the diene are reactive. The analysis of the minimum dynamic path of the reaction indicates that both, rotations and vibrations of the reactant molecules are important for driving the system towards the transition state. The rates were computed as k = 5.1 x 10^-14 s^-1 for the s-cis and k = 3.8 x 10^-14 s^-1 for the s-trans conformer of 2,3-dibromobutadiene at an internal temperature of 300 K. The present results are to be contrasted with the neutral variant of the title system in which only the gauche conformer of the diene was found to undergo a considerably slower, concerted and mostly synchronous reaction driven by the excitation of rotations. The results presented here inform detailed experimental studies of the dynamics of polar cycloadditions under single-collision conditions in the gas phase.

**候选反应（2）**：
- ionic Diels-Alder reaction of 2,3-dibromobutadiene radical ion with maleic anhydride
- concerted vs stepwise pathways and s-cis/s-trans conformer effects in polar cycloaddition

**推荐理由**：自由基离子开壳层体系，常规闭壳层流水线处理困难，边界属性强于 Normal 梯队定位。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

# HARD 梯队 —— 立体化学 / 微观几何感知（目标 20 题）

### hard-04｜综合 9.6【必选】｜2016

**Unconventional exo selectivity in thermal normal-electron-demand Diels-Alder reactions**

- 作者：Guan-Ming Ho、Chih-Jui Huang、En-Yi Li et al.（共 8 人）
- 出处：Scientific Reports
- DOI：[10.1038/srep35147](https://doi.org/10.1038/srep35147)
- 获取：✅ 已下载 PDF `2016_ho_exo_selectivity_da.pdf`（OA）
- 分项：体系适配 10｜参考数据 9｜测试价值 10｜可获取 9

**摘要**：The Diels-Alder reaction is a useful tool for generating functionalized chiral molecules through the concerted cycloaddition of dienes and dienophiles leading to six-membered rings. Traditionally, the selective predictions of the products rely heavily on consideration of the secondary orbital interactions that stabilize the endo pathway. However, there remain some basic examples defying this notion and produce the exo-isomer as major product. Here we systematically evaluated of the structural features driving exo selectivity in thermal normal-electron-demand Diels-Alder reactions. Substitution at the Cβ position and the size and electronegativity of the electron-withdrawing group of the dienophile are contributing factors. Experimental and computational studies both point toward the steric and electrostatic forces between the substituents in both the diene and the dienophile that increase the likelihood of the exo pathway. For these substrates, the dominance of the endo pathway is reduced by transition state distortions and poor structural alignments of the reacting partners. We also noted the tilt of the dienophile with respect to the diene causing steric strain on the functionalities at the more advanced bond forming carbon-carbon position of the endo transition state. Insights into such factors may benefit synthetic planning and asserting control over this important named reaction.

**候选反应（2）**：
- Cβ-substituted diene + electron-poor dienophile exo-selective Diels-Alder
- thermal normal-electron-demand DA with tilted endo TS

**推荐理由**：教科书规则失效的反例集（反常 exo 选择性），阴性对照考题最佳来源，且有 PDF。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-08｜综合 9.0【必选】｜2015

**Competitive and Cooperative Torquoselectivity in the thermal ring opening of cyclobutene: A density functional insight**

- 作者：Lakshminarayanan Akilandeswari、Chandrasekaran Prathipa（共 2 人）
- 出处：Journal of Chemical Sciences
- DOI：[10.1007/s12039-015-0936-5](https://doi.org/10.1007/s12039-015-0936-5)
- 获取：✅ 已下载 PDF `2015_akilandeswari_torquoselectivity.pdf`（OA）
- 分项：体系适配 10｜参考数据 8｜测试价值 9｜可获取 9

**摘要**：Torquoselective preference for methoxy and silyloxy substituted cyclobutene during thermal conrotatory electrocyclic ring opening is substantiated through computational study at B3LYP/6-31G(d) level. When cyclobutenes are substituted at C3 carbon there are two possible pathways of thermal ring opening viz either rotation of 3-substituent inward (in the direction of cleaving sigma bond) or rotation of 3-substituent outward.

**候选反应（2）**：
- 3-methoxycyclobutene conrotatory ring opening (inward vs outward)
- 3-silyloxycyclobutene torquoselective ring opening

**推荐理由**：3-取代环丁烯顺旋开环内外选择性的最小体系，有 PDF，torquoselectivity 类题首选。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-15｜综合 8.8【必选】｜2022

**Unveiling [3 + 2] Cycloaddition Reactions of N-Methyl-C-3-Bromophenyl-Nitrone to Dimethyl Maleate: Molecular Electron Density Theory Perspective**

- 作者：Sabir A. Mohammed Salih、Huda A. Basheer、Haydar Mohammad-Salim（共 3 人）
- 出处：Journal of the Mexican Chemical Society
- DOI：[10.29356/jmcs.v66i4.1801](https://doi.org/10.29356/jmcs.v66i4.1801)
- 获取：✅ 已下载 PDF `2022_salih_nitrone_32ca.pdf`（OA）
- 分项：体系适配 10｜参考数据 8｜测试价值 8｜可获取 9

**摘要**：The zwitterionic-type (zw-type) [3+2] cycloaddition (32CA) reactions of N-methyl-C-3-bromophenyl-nitrone 1 with dimethyl maleate 2 with increased electrophilicity were investigated using the Molecular Electron Density Theory (MEDT) at the MPWB95/6-311++G(d,p) computational level. Both reactivity and selectivity are rationalized in relation to the polarity of the reaction. The associated zw-type 32CA reactions are accelerated due to the high nucleophilic character of N-methyl-C-3-bromophenyl-nitrone 1 and the strong electrophilic character of dimethyl maleate 2, which also play a critical part in the mechanism of the reaction, influencing the stereoselectivity, with activation enthalpies in between 34.04 and 38.37 kJ/mol in the gas phase. The CDFT indices are used to anticipate global electron density flux from the nucleophilic N-methyl-C-3-bromophenyl-nitrone 1 to the electrophilic dimethyl maleate 2. These exergonic 32CA reactions have negative Gibbs free energy along the endo and exo stereochemical pathways. The endo stereochemical process is preferred over the exo stereochemical pathway in this kinetically controlled 32CA reaction. The predictions of bonding evolution theory (BET) for the endo and exo pathways indicate a one-step process with early transition states, which is compatible with the ELF topological examination of transition states.

**候选反应（1）**：
- N-methyl-C-3-bromophenyl-nitrone + dimethyl maleate [3+2] cycloaddition (endo vs exo)

**推荐理由**：硝酮 [3+2] 的 endo/exo 定量能垒+ELF/BET 分析；小分子硝酮+顺丁烯二酸二甲酯体系完全在算力舒适区，有 PDF，把 Hard 梯队从 DA 扩展到偶极环加成。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-01｜综合 8.7【必选】｜2014

**Origin of the "endo rule" in Diels-Alder reactions**

- 作者：Israel Fernández、F. Matthias Bickelhaupt（共 2 人）
- 出处：Journal of Computational Chemistry
- DOI：[10.1002/jcc.23500](https://doi.org/10.1002/jcc.23500)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 9｜参考数据 9｜测试价值 10｜可获取 5

**摘要**：Detailed density functional theory calculations definitively rationalize the preference for the endo cycloadduct (also known as endo rule) in text-book thermal Diels-Alder reactions involving maleic anhydride and cyclopentadiene or butadiene. This selectivity is mainly caused by an unfavorable steric arrangement in the transition-state region of the exo pathway which translates into a more destabilizing activation strain. In contrast with the widely accepted, orbital-interaction-based explanation for the endo rule, it is found that neither the orbital interactions nor the total interaction between the deformed reactants contributes to the endo selectivity.

**候选反应（2）**：
- cyclopentadiene + maleic anhydride Diels-Alder (endo vs exo)
- cyclopentadiene/butadiene + maleic anhydride endo/exo selectivity

**推荐理由**：endo 规则的现代活化应变解释，几何感知考题的核心锚点文献。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-10｜综合 8.4【推荐】｜2003

**Origins of Inward Torquoselectivity by Silyl Groups and Other σ-Acceptors in Electrocyclic Reactions of Cyclobutenes**

- 作者：Patrick S. Lee、Xiyun Zhang、K. N. Houk（共 3 人）
- 出处：Journal of the American Chemical Society
- DOI：[10.1021/ja0287635](https://doi.org/10.1021/ja0287635)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 10｜参考数据 9｜测试价值 8｜可获取 5

**摘要**：Recent reports of inward torquoselectivities in thermal electrocyclic ring-opening reactions of 3-silylcyclobutenes have revealed that saturated silyl substituents, just like the extensively studied pi-acceptors, can exert contrasteric effects. The origins of torquoselectivity for substituents lacking pi orbitals have been explained using B3LYP density functional calculations. Orbital interactions involving the substituent vacant orbitals and the occupied orbitals associated with the breaking bonds are found to control these contrasteric torquoselectivities, with minor contributions from electrostatic effects. Reaction energetics and transition states for electrocyclic ring-opening reactions of 3-silyl, fluorosilyl, difluorosilyl, trifluorosilyl, methylsilyl, methyl, fluoromethyl, difluoromethyl, trifluoromethyl, ammonio, phosphonio, formyl, and borohydrido cyclobutenes are reported to complement previous extensive studies of unsaturated substituents. Inward stereoselectivities are predicted for various silyl and phosphonium substituents, along with potent pi-acceptors studied earlier. Cope and Diels-Alder reactions involving silyl substituents are also computed.

**候选反应（2）**：
- 3-silylcyclobutene inward ring opening (Z-diene)
- 3-formyl/3-trifluoromethyl cyclobutene torquoselectivity series

**推荐理由**：Houk 内旋 torquoselectivity 奠基作，取代基逐一能垒表可直接转成系列考题。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-07｜综合 8.3【推荐】｜2025

**DFT Investigation of the Stereoselectivity of the Lewis-Acid-Catalyzed Diels-Alder Reaction between 2,5-Dimethylfuran and Acrolein**

- 作者：Mariem Chellegui、Mohamed Trabelsi、Benoît Champagne et al.（共 4 人）
- 出处：ACS Omega
- DOI：[10.1021/acsomega.4c07888](https://doi.org/10.1021/acsomega.4c07888)
- 获取：❌ 未下载（OA，仅元数据+摘要）
- 分项：体系适配 9｜参考数据 8｜测试价值 8｜可获取 8

**摘要**：Density functional theory (DFT) has been enacted to study the Diels-Alder reaction between 2,5-dimethylfuran (2,5-DMF), a direct product of biomass transformation, and acrolein and to analyze its thermodynamics, kinetics, and mechanism when catalyzed by a Lewis acid (LA), in comparison to the uncatalyzed reaction. The uncatalyzed reaction occurs via a typical one-step asynchronous process, corresponding to a normal electron demand (NED) mechanism, where acrolein is an electrophile whereas 2,5-DMF is a nucleophile. The small endo selectivity in solvents of low dielectric constants is replaced by a small exo selectivity in solvents with larger dielectric constants, such as DMSO. In the catalyzed process, the LA interacts with acrolein, forming a O-LA coordinating bond, that enhances its electron-acceptor character, further favoring the NED mechanism and reducing the activation energy. When AlCl3 and GaCl3 catalyze the reaction, the bond formations of both the endo and exo pathways occur via a two-step asynchronous process. Thus, these processes involve the formation of two transition states and a stable intermediate. The second transition state is the critical one and it dictates the increase of the exo selectivity, in comparison to the uncatalyzed reaction.

**候选反应（1）**：
- 2,5-dimethylfuran + acrolein Diels-Alder (uncatalyzed vs AlCl3/GaCl3-catalyzed endo/exo)

**推荐理由**：溶剂介电+Lewis 酸结合切换 endo/exo 并变分步机理，金色 OA，小杂芳体系可算性好。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-02｜综合 8.1【推荐】｜2005

**The Source of the endo Rule in the Diels-Alder Reaction: Are Secondary Orbital Interactions Really Necessary?**

- 作者：José Ignacio García、José Antonio Mayoral、Luis Salvatella（共 3 人）
- 出处：European Journal of Organic Chemistry
- DOI：[10.1002/ejoc.200400424](https://doi.org/10.1002/ejoc.200400424)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 9｜参考数据 8｜测试价值 9｜可获取 5

**摘要**：The endo preference in Diels-Alder reactions is usually attributed to the occurrence of attractive Secondary Orbital Interactions (SOI), whereas other interaction mechanisms (primary interactions, closed-shell repulsions, electrostatics) are assumed to be identical for both endo and exo approaches. However, analysis of the parallel approximation between s-trans butadiene and fumaronitrile shows that SOI is overcome by closed-shell repulsions. Furthermore, the study of several reactions (cyclopentadiene + maleic anhydride, cyclobutadiene + cyclobutenedione, cyclobutadiene + norbornadiene) indicates the absence of a net attraction for the atom pairs involved in SOI. As a conclusion, the endo preference is not due to the occurrence of an attractive interaction between the atom pairs involved in SOI and so this concept is unnecessary.

**候选反应（3）**：
- cyclopentadiene + maleic anhydride endo/exo
- cyclobutadiene + cyclobutenedione Diels-Alder
- cyclobutadiene + norbornadiene Diels-Alder

**推荐理由**：与 hard-01 构成正反方辩论（次级轨道相互作用是否必要），配对出题价值高。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-09｜综合 8.1【推荐】｜2016

**Torquoselectivity in Cyclobutene Ring Openings and the Interatomic Interactions That Control Them**

- 作者：José Enrique Barquera-Lozada（共 1 人）
- 出处：The Journal of Physical Chemistry A
- DOI：[10.1021/acs.jpca.6b08771](https://doi.org/10.1021/acs.jpca.6b08771)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 9｜参考数据 9｜测试价值 8｜可获取 5

**摘要**：Torquoselectivity has explained diasteromeric preferences of a number electrocyclic ring openings. The quantum theory of atoms in molecules (QTAIM), the electron localizability indicator (ELI-D), and the interacting quantum atoms (IQA) energy partition method are used to evaluate qualitatively and quantitatively the atomic interactions behind the torquoselectivity of a series of 3-substituted cyclobutenes. ELI-D topology and IQA energies show that the interaction between the distal terminus carbon atom of cyclobutene (C4) with the substituent at C3 (R5) in the transition state governs torquoselectivities. In the case of 3-borylcyclobutene, this interaction is so strong that a protocovalent bond is actually formed between B5 and C4. The evaluation of the interatomic energies allowed us to identify an additional interaction that contribute to a minor extent to the stabilization of the TS. Despite the fact that C4,R5 interaction is the main cause of the torquoselectivity, a bonding path (BP) between these two atoms was not observed. However, the lack of a BP between C4 and R5 does not mean that the topology of the electron density was not affected by the interaction of these two atoms. Surprisingly, we found a strong correlation between the density at the bond critical point (BCP) and the BP shape of C3-C4 breaking bond with the observed activation energies and torquoselectivities.

**候选反应（1）**：
- 3-substituted cyclobutene ring opening series (R = boryl, silyl, formyl, etc.)

**推荐理由**：取代基系列（含 3-boryl 内旋特例）QTAIM/IQA 定量能垒表；付费墙但表格数值是现成评分基准。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-03｜综合 7.8【推荐】｜2018

**Origins of the Endo and Exo Selectivities in Cyclopropenone, Iminocyclopropene, and Triafulvene Diels-Alder Cycloadditions**

- 作者：Brian J. Levandowski、Trevor A. Hamlin、Ryan C. Helgeson et al.（共 5 人）
- 出处：The Journal of Organic Chemistry
- DOI：[10.1021/acs.joc.8b00025](https://doi.org/10.1021/acs.joc.8b00025)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 9｜参考数据 8｜测试价值 8｜可获取 5

**摘要**：The endo and exo stereoselectivities of Diels-Alder reactions of cyclopropenone, iminocyclopropene, and substituted triafulvenes with butadiene were rationalized using density functional theory calculations. When cyclopropenone is the dienophile, there is a 1.8 kcal/mol preference for the exo cycloaddition with butadiene, while the reaction of 3-difluoromethylene triafulvene with butadiene favors the endo cycloaddition by 2.8 kcal/mol. The influence of charge transfer and secondary orbital interactions on the stereoselectivity of Diels-Alder reactions involving triafulvenes and heteroanalogs is discussed. The predicted stereoselectivity correlates with both the charge and highest occupied molecular orbital (HOMO) coefficient at the C3 carbon of the triafulvene motif.

**候选反应（3）**：
- cyclopropenone + butadiene (exo-selective DA)
- 3-difluoromethylene triafulvene + butadiene (endo-selective DA)
- iminocyclopropene + butadiene DA

**推荐理由**：小张力双烯亲合物导致 endo/exo 偏好翻转（1.8–2.8 kcal/mol），量化翻转幅度适合写进评分细则。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-11｜综合 7.8【推荐】｜2023

**On the Nature of the Rotational Energy Barrier of Atropisomeric Hydrazides**

- 作者：Andrea Pellegrini、Laura Marcon、Paolo Righi et al.（共 8 人）
- 出处：Molecules
- DOI：[10.3390/molecules28237856](https://doi.org/10.3390/molecules28237856)
- 获取：✅ 已下载 PDF `2023_pellegrini_atropisomer_hydrazide.pdf`（OA）
- 分项：体系适配 8｜参考数据 8｜测试价值 7｜可获取 9

**摘要**：N-N atropisomers represent a useful class of compounds that has recently received important attention from many research groups. This article presents an in-depth analysis of the energy barrier needed for the racemization process of atropoisomeric hydrazides, combining an experimental and computational approach. The focus is on examining how electronic and steric factors impact the racemization process. The results obtained indicate that the barrier observed during the racemization process mainly arises from an increase in the p-orbital character of the nitrogen atoms.

**候选反应（1）**：
- N-N atropisomeric hydrazide racemization (rotation about the N-N axis)

**推荐理由**：N-N 阻转异构体消旋化能垒，实验+计算互证协议完整，轴手性分支代表作，有 PDF。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-16｜综合 7.7【推荐】｜2010

**Computational Study of Factors Controlling the Boat and Chair Transition States of Ireland-Claisen Rearrangements**

- 作者：Şeref Gül、Franziska Schoenebeck、Viktorya Aviyente et al.（共 4 人）
- 出处：The Journal of Organic Chemistry
- DOI：[10.1021/jo100033d](https://doi.org/10.1021/jo100033d)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 8｜参考数据 8｜测试价值 8｜可获取 6

**摘要**：The origins of the boat transition state preference in the Ireland-Claisen rearrangements studied experimentally by Kishi and co-workers have been explored computationally with Density Functional Theory. Steric interactions in the chair transition states were identified as the principal reason for the boat transition state preference.

**候选反应（1）**：
- Ireland-Claisen rearrangement via competing chair/boat TSs (Kishi substrates)

**推荐理由**：Ireland-Claisen 船式/椅式 TS 竞争决定非对映选择性；PMC 有全文（此前自动下载失败，可手动补）。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-06｜综合 7.4【备选】｜2021

**Bifunctional Hydrogen Bond Donor-Catalyzed Diels-Alder Reactions: Origin of Stereoselectivity and Rate Enhancement**

- 作者：Pascal Vermeeren、Trevor A. Hamlin、F. Matthias Bickelhaupt et al.（共 4 人）
- 出处：Chemistry - A European Journal
- DOI：[10.1002/chem.202004496](https://doi.org/10.1002/chem.202004496)
- 获取：❌ 未下载（OA，仅元数据+摘要）
- 分项：体系适配 7｜参考数据 8｜测试价值 8｜可获取 6

**摘要**：The selectivity and rate enhancement of bifunctional hydrogen bond donor-catalyzed Diels-Alder reactions between cyclopentadiene and acrolein were quantum chemically studied using density functional theory in combination with coupled-cluster theory. (Thio)ureas render the studied Diels-Alder cycloaddition reactions exo selective and induce a significant acceleration of this process by lowering the reaction barrier by up to 7 kcal/mol. Our activation strain and Kohn-Sham molecular orbital analyses uncover that these organocatalysts enhance the Diels-Alder reactivity by reducing the Pauli repulsion between the closed-shell filled pi-orbitals of the diene and dienophile, by polarizing the pi-orbitals away from the reactive center and not by making the orbital interactions between the reactants stronger. In addition, we establish that the unprecedented exo selectivity of the hydrogen bond donor-catalyzed Diels-Alder reactions is directly related to the larger degree of asynchronicity along this reaction pathway, which is manifested in a relief of destabilizing activation strain and Pauli repulsion.

**候选反应（1）**：
- cyclopentadiene + acrolein + (thio)urea catalyst (exo-selective H-bond-catalyzed DA)

**推荐理由**：氢键供体催化使 DA 反转为 exo 选择性；催化剂底物复合物偏大且出版社 PDF 被 403 拦截。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-14｜综合 7.2【备选】｜2020

**A DFT study on the reaction mechanism of enantioselective reduction of ketones with borane catalyzed by a B-methoxy-oxazaborolidine catalyst derived from (-)-β-pinene**

- 作者：Hichem Sadrik Kettouche（共 1 人）
- 出处：Journal of Molecular Modeling
- DOI：[10.1007/s00894-019-4276-0](https://doi.org/10.1007/s00894-019-4276-0)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 7｜参考数据 8｜测试价值 8｜可获取 5

**摘要**：Theoretical studies on enantioselective reduction of ketone with borane catalyzed by a B-methoxy-oxazaborolidine catalyst derived from pinene have been performed by means of the density functional theory (DFT) method. All the structures were optimized completely using wB97XD/6-31G(d,p) level and the mechanism of the enantioselective reduction is studied. The formation of the M4s complexes via transition state TS3s was the rate-determining step and the chirality-limiting step for this enantioselective reduction; the dominant reaction is the attack of proton from the Si surface of M3a, which provides the corresponding secondary alcohols in 98% ee. NCI analysis of the four computed transition states associated with stereoselectivity-determining step discloses that TS3a(S) is the stable conformation with respect to TS3a(R), TS3b(S), and TS3b(R). The produced reaction pathway takes place through: M1 -> M2a -> M3a -> M4a(S) -> M5a(S) -> M6a(S) -> M7a(S). The chirality of the reduced product is of S type, which is in agreement with the experiment.

**候选反应（1）**：
- oxazaborolidine (CBS-type) catalyzed borane reduction of ketones (Re/Si face TS)

**推荐理由**：CBS 硼烷还原 Re/Si 面竞争，六元船式 TS 几何感知典型；工作量中等。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-12｜综合 6.9【备选】｜2016

**Origins of Selectivity and General Model for Chiral Phosphoric Acid-Catalyzed Oxetane Desymmetrizations**

- 作者：Pier Alexandre Champagne、K. N. Houk（共 2 人）
- 出处：Journal of the American Chemical Society
- DOI：[10.1021/jacs.6b08276](https://doi.org/10.1021/jacs.6b08276)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 6｜参考数据 8｜测试价值 8｜可获取 5

**摘要**：The origins of the high enantioselectivity of chiral phosphoric acid-catalyzed oxetane desymmetrizations were investigated by density functional theory (DFT) calculations. Distortion of the catalyst structure, caused by steric crowding in the catalyst pocket of one enantiomeric transition state, is the main cause for stereochemical preference. A general model was developed to assist in the rational design of new catalysts for related transformations.

**候选反应（1）**：
- CPA-catalyzed oxetane desymmetrization (enantiodetermining ring-opening TS)

**推荐理由**：CPA 对映选择性起源经典，但催化剂空腔体系重原子数 >50，计算成本超出常规预算。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-05｜综合 6.7【备选】｜2023

**Computational study on the catalytic control of endo/exo Diels-Alder reactions by cavity quantum vacuum fluctuations**

- 作者：Fabijan Pavošević、Robert L. Smith、Ángel Rubio（共 3 人）
- 出处：Nature Communications
- DOI：[10.1038/s41467-023-38474-w](https://doi.org/10.1038/s41467-023-38474-w)
- 获取：✅ 已下载 PDF `2023_pavosevic_cavity_da.pdf`（OA）
- 分项：体系适配 4｜参考数据 8｜测试价值 7｜可获取 9

**摘要**：Achieving control over chemical reaction's rate and stereoselectivity realizes one of the Holy Grails in chemistry that can revolutionize chemical and pharmaceutical industries. Strong light-matter interaction in optical or nanoplasmonic cavities might provide the knob to reach such control. In this work, we demonstrate the catalytic and selectivity control of an optical cavity for two selected Diels-Alder cycloaddition reactions using the quantum electrodynamics coupled cluster (QED-CC) method. Herein, we find that by changing the molecular orientation with respect to the polarization of the cavity mode the reactions can be significantly inhibited or selectively enhanced to produce major endo or exo products on demand. This work highlights the potential of utilizing quantum vacuum fluctuations of an optical cavity to modulate the rate of Diels-Alder cycloaddition reactions and to achieve stereoselectivity in a practical and non-intrusive way. We expect that the present findings will be applicable to a larger set of relevant reactions, including the click chemical reactions.

**候选反应（1）**：
- cavity-controlled endo/exo Diels-Alder cycloadditions (QED-CC reference barriers)

**推荐理由**：腔量子电动力学控制选择性——概念震撼但 QED-CC 无法在本项目流程复现，仅作概念拓展阅读。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### hard-13｜综合 6.6【备选】｜2022

**Chiral Phosphoric Acid Catalyzed Conversion of Epoxides into Thiiranes: Mechanism, Stereochemical Model, and New Catalyst Design**

- 作者：Meng Duan、Christian Díaz-Oviedo、Yang Zhou et al.（共 8 人）
- 出处：Angewandte Chemie International Edition
- DOI：[10.1002/anie.202113204](https://doi.org/10.1002/anie.202113204)
- 获取：❌ 未下载（OA，仅元数据+摘要）
- 分项：体系适配 6｜参考数据 7｜测试价值 7｜可获取 6

**摘要**：Computations and experiments leading to new chiral phosphoric acids (CPAs) for epoxide thionations are reported. Density functional theory calculations reveal the mechanism and origin of the enantioselectivity of such CPA-catalyzed epoxide thionations. The calculated mechanistic information was used to design new efficient CPAs that were tested experimentally and found to be highly effective. Bulky ortho-substituents on the 3,3'-aryl groups of the CPA are important to restrict the position of the epoxide in the key transition states for the enantioselectivity-determining step. Larger para-substituents significantly improve the enantioselectivity of the reaction.

**候选反应（1）**：
- CPA-catalyzed epoxide thionation kinetic resolution (enantiodetermining TS)

**推荐理由**：同为 CPA 大体系且 PDF 被 403 拦截；除非手性催化分支扩容再考虑。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

# IMPOSSIBLE 梯队 —— 多参考态 / 开壳层（考察合理拒答；目标 20 题）

### impossible-01｜综合 9.8【必选】｜2022

**Reference Energies for Cyclobutadiene: Automerization and Excited States**

- 作者：Enzo Monino、Martial Boggio-Pasqua、Anthony Scemama et al.（共 5 人）
- 出处：Journal of Physical Chemistry A 126, 4664
- DOI：[10.1021/acs.jpca.2c02480](https://doi.org/10.1021/acs.jpca.2c02480)
- 获取：✅ 已下载 PDF `2022_Monino_cyclobutadiene.pdf`（OA）
- 分项：体系适配 10｜参考数据 10｜测试价值 10｜可获取 9

**摘要**：Cyclobutadiene is a well-known playground for theoretical chemists and is particularly suitable to test ground- and excited-state methods. Indeed, due to its high spatial symmetry, especially at the D4h square geometry but also in the D2h rectangular arrangement, the ground and excited states of cyclobutadiene exhibit multi-configurational characters and single-reference methods, such as adiabatic time-dependent density-functional theory (TD-DFT) or equation-of-motion coupled cluster (EOM-CC), are notoriously known to struggle in such situations. In this work, using a large panel of methods and basis sets, we provide an extensive computational study of the automerization barrier (defined as the difference between the square and rectangular ground-state energies) and the vertical excitation energies at D2h and D4h equilibrium structures. In particular, selected configuration interaction (SCI), multi-reference perturbation theory (CASSCF, CASPT2, and NEVPT2), and coupled-cluster (CCSD, CC3, CCSDT, CC4, and CCSDTQ) calculations are performed. The spin-flip formalism, which is known to provide a qualitatively correct description of these diradical states, is also tested within TD-DFT (combined with numerous exchange-correlation functionals) and the algebraic diagrammatic construction [ADC(2)-s, ADC(2)-x, and ADC(3)] schemes. A theoretical best estimate is defined for the automerization barrier and for each vertical transition energy.

**候选反应（2）**：
- cyclobutadiene automerization (rectangular D2h minimum via square D4h transition state)
- cyclobutadiene singlet-triplet gap at D4h geometry

**推荐理由**：多参考态识别的金标准体系：D4h 方形过渡构型基态双组态简并，CCSDTQ 级真值齐备，拒答判定题首选。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### impossible-03｜综合 9.8【必选】｜2018

**Full configuration interaction quantum Monte Carlo benchmark and multireference coupled cluster studies of tetramethyleneethane diradical**

- 作者：Libor Veis、Andrej Antalik、Ors Legeza et al.（共 5 人）
- 出处：Journal of Chemical Theory and Computation 14, 2439-2445
- DOI：[10.1021/acs.jctc.8b00022](https://doi.org/10.1021/acs.jctc.8b00022)
- 获取：✅ 已下载 PDF `2018_Veis_tetramethyleneethane.pdf`（OA）
- 分项：体系适配 10｜参考数据 10｜测试价值 10｜可获取 9

**摘要**：We have performed a FCI-quality benchmark calculation for the tetramethyleneethane molecule in cc-pVTZ basis set employing a subset of CASPT2(6,6) natural orbitals for the FCIQMC calculation. The results are in an excellent agreement with the previous large scale diffusion Monte Carlo calculations by Pozun et al. and available experimental results. Our computations verified that there is a maximum on PES of the ground singlet state (1A) 45 deg torsional angle and the corresponding vertical singlet-triplet energy gap is 0.01 eV. We have employed this benchmark for assessment of the accuracy of MkCCSDT and DMRG-tailored CCSD (TCCSD) methods. MR MkCCSDT with CAS(2,2) model space, though giving good values for the singlet-triplet energy gap, is not able to properly describe the shape of the multireference singlet PES. Similarly, DMRG(24,25) is not able to correctly capture the shape of the singlet surface, due to the missing dynamic correlation. On the other hand, the DMRG-tailored CCSD method describes the shape of the ground singlet state with an excellent accuracy, but for the correct ordering requires computation of the zero-spin-projection component of the triplet state (3B1).

**候选反应（2）**：
- tetramethyleneethane torsional potential energy surface (singlet vs triplet)
- tetramethyleneethane ring-closing to bicyclobutane-type products (see Pozun et al. DMC refs)

**推荐理由**：连 DMRG(24,25) 与 CAS(2,2)-MkCCSDT 都难以正确描述的单线态扭转面——检验 Agent 方法边界意识的极端案例。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### impossible-02｜综合 9.5【必选】｜2025

**The Singlet-Triplet Gap of Cyclobutadiene: The CIPSI-Driven CC(P;Q) Study**

- 作者：Swati S. Priyadarsini、Karthik Gururangan、Jun Shen et al.（共 4 人）
- 出处：Journal of Physical Chemistry A 129, 11749
- DOI：[10.1021/acs.jpca.5c07572](https://doi.org/10.1021/acs.jpca.5c07572)
- 获取：✅ 已下载 PDF `2025_Priyadarsini_cyclobutadiene_stgap.pdf`（OA）
- 分项：体系适配 10｜参考数据 10｜测试价值 9｜可获取 9

**摘要**：An accurate determination of singlet-triplet gaps in biradicals, including cyclobutadiene in the automerization barrier region where one has to balance the substantial nondynamical many-electron correlation effects characterizing the singlet ground state with the predominantly dynamical correlations of the lowest-energy triplet, remains a challenge for many quantum chemistry methods. High-level coupled-cluster (CC) approaches, such as the CC method with a full treatment of singly, doubly, and triply excited clusters (CCSDT), are often capable of providing reliable results, but the routine application of such methods is hindered by their high computational costs. We have recently proposed a practical alternative to converging the CCSDT energetics at small fractions of the computational effort, even when electron correlations become stronger and connected triply excited clusters are larger and nonperturbative, by merging the CC(P;Q) moment expansions with the selected configuration interaction methodology abbreviated as CIPSI. We demonstrate that one can accurately approximate the highly accurate CCSDT potential surfaces characterizing the lowest singlet and triplet states of cyclobutadiene along the automerization coordinate and the gap between them using tiny fractions of triply excited cluster amplitudes identified with the help of relatively inexpensive CIPSI Hamiltonian diagonalizations.

**候选反应（2）**：
- cyclobutadiene automerization singlet PES
- cyclobutadiene triplet surface along automerization coordinate

**推荐理由**：沿自动异构化坐标给出单/三线态双势能面，与 impossible-01 配对构成完整考题组。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### impossible-04｜综合 9.2【必选】｜2019

**Singlet-Triplet Energy Gaps of Organic Biradicals and Polyacenes with Auxiliary-Field Quantum Monte Carlo**

- 作者：James Shee、Evan J. Arthur、Shiwei Zhang et al.（共 5 人）
- 出处：Journal of Chemical Theory and Computation (DOI 10.1021/acs.jctc.9b00534)
- DOI：[10.1021/acs.jctc.9b00534](https://doi.org/10.1021/acs.jctc.9b00534)
- 获取：✅ 已下载 PDF `2019_Shee_benzyne_afqmc.pdf`（OA）
- 分项：体系适配 9｜参考数据 10｜测试价值 9｜可获取 9

**摘要**：The energy gap between the lowest-lying singlet and triplet states is an important quantity in chemical photocatalysis, with relevant applications ranging from triplet fusion in optical upconversion to the design of organic light-emitting devices. The ab initio prediction of singlet-triplet (ST) gaps is challenging due to the potentially biradical nature of the involved states, combined with the potentially large size of relevant molecules. In this work, we show that phaseless auxiliary-field quantum Monte Carlo (ph-AFQMC) can accurately predict ST gaps for chemical systems with singlet states of highly biradical nature, including a set of 13 small molecules and the ortho-, meta-, and para-isomers of benzyne. With respect to gas-phase experiments, ph-AFQMC using CASSCF trial wavefunctions achieves a mean averaged error of ~1 kcal/mol. Furthermore, we find that in the context of a spin-projection technique, ph-AFQMC using unrestricted single-determinant trial wavefunctions, which can be readily obtained for even very large systems, produces equivalently high accuracy. We proceed to show that this scalable methodology is capable of yielding accurate ST gaps for all linear polyacenes for which experimental measurements exist, i.e. naphthalene, anthracene, tetracene, and pentacene. Our results suggest a protocol for selecting either unrestricted Hartree-Fock or Kohn-Sham orbitals for the single-determinant trial wavefunction, based on the extent of spin-contamination.

**候选反应（3）**：
- ortho-/meta-/para-benzyne singlet-triplet gap ordering
- benzyne biradical reactivity (Bergman-type cyclization energetics presuppose correct ST ordering)
- polyacene (naphthalene-pentacene) singlet-triplet gaps

**推荐理由**：13 个强双自由基单三态能隙+基于自旋污染选参考的判据，一次入库一整族考题。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### impossible-05｜综合 8.9【必选】｜2020

**Large yet bounded: Spin gap ranges in carbenes**

- 作者：Max Schwilk、Diana N. Tahchieva、O. Anatole von Lilienfeld（共 3 人）
- 出处：arXiv:2004.10600 (preprint)
- DOI：—
- 获取：✅ 已下载 PDF `2020_Schwilk_carbenes_mrci.pdf`（OA）
- 分项：体系适配 9｜参考数据 10｜测试价值 8｜可获取 9

**摘要**：Despite its relevance for chemistry, the electronic structure of free carbenes throughout chemical space has not yet been studied in a systematic manner. We explore a large and systematic carbene chemical space consisting of eight thousand diverse and common carbene scaffolds in their singlet and triplet state computed at controlled accuracy (higher order multireference level of theory) and with verified carbene character in the electronic structure. Originating in strong electron correlation, a hard upper limit for the singlet-triplet gap is found to emerge at around 30 kcal/mol for all the carbene classes in this chemical space. We also observe large vertical and adiabatic spin gap ranges within many carbene classes (>100 and >60 kcal/mol, respectively), and we report novel relationships between compositional, structural, and electronic degrees of freedom. Our QMspin data base includes numerical results for ~13000 MRCI calculations on randomly selected carbene scaffolds.

**候选反应（2）**：
- singlet vs triplet carbene ground-state assignment across 8000 scaffolds
- spin-state-dependent carbene reactivity (singlet concerted insertion vs triplet stepwise abstraction)

**推荐理由**：约 13000 条 MRCI 卡宾自旋能隙数据库；自旋态指认错误即机理判断错误的典型案例库。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### impossible-07｜综合 8.7【必选】｜2024

**Excited state-specific CASSCF theory for the torsion of ethylene**

- 作者：Sandra Saade、Hugh G. A. Burton（共 2 人）
- 出处：arXiv:2402.13046 (preprint)
- DOI：—
- 获取：✅ 已下载 PDF `2024_Saade_ethylene_torsion.pdf`（OA）
- 分项：体系适配 9｜参考数据 8｜测试价值 9｜可获取 9

**摘要**：State-specific complete active space self-consistent field (SS-CASSCF) theory has emerged as a promising route to accurately predict electronically excited energy surfaces away from molecular equilibria. However, its accuracy and practicality for chemical systems of photochemical interest has yet to be fully determined. We investigate the performance of SS-CASSCF theory for the low-lying ground and excited states in the double bond rotation of ethylene. We show that state-specific approximations with a minimal (2e, 2o) active space provide comparable accuracy to state-averaged calculations with much larger active spaces, while optimising the orbitals for each excited state significantly improves the spatial diffusivity of the wave function. However, the unbalanced post-CASSCF dynamic correlation in valence and Rydberg excitations, or the use of a non-diffuse basis set, causes excited state solutions to coalesce and disappear, creating unphysical discontinuities in the potential energy surface. Our findings highlight the theoretical challenges that must be overcome to realise practical applications of state-specific electronic structure theory for computational photochemistry.

**候选反应（2）**：
- ethylene cis-trans double-bond torsion (pi-bond breaking biradical at 90 deg)
- ethylene ground- and excited-state torsional surfaces

**推荐理由**：π 键扭转双自由基的原型考题（90° 扭转处单参考完全失效），还展示 CASSCF 自身的陷阱，深化'多参考方法也有坑'的认知。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### impossible-06｜综合 8.4【推荐】｜2021

**Quantum Monte Carlo Investigation of the H-transfer Reaction of Criegee Intermediate CH3CHOO: A Benchmark Calculation**

- 作者：Zhiping Wang、Yuxiang Bu（共 2 人）
- 出处：arXiv:2106.11822 (preprint)
- DOI：—
- 获取：✅ 已下载 PDF `2021_Wang_criegee_qmc.pdf`（OA）
- 分项：体系适配 8｜参考数据 9｜测试价值 8｜可获取 9

**摘要**：We perform the fixed-node diffuse Monte Carlo (FN DMC) calculations to determine the barrier height and reaction energy of a critical reaction, the H-transfer reaction from syn-CH3CHOO to vinyl hydroperoxide. The FN DMC barrier height is found to be 16.60+/-0.35 kcal/mol which agrees well with the experimental measurement within a few tenths of kcal, justifying the reliability of the FN DMC method for predicting barrier height of the rapid unimolecular reaction of Criegee intermediates. By comparing the predictions from the CCSD(t), G3 (MCG3), DFT and MP2 methods with respect to the FN DMC results and available experiment measurement, we found that the CCSD(t) barrier heights agree with the FN DMC counterpart within statistical errors, and is within a closer agreement with experiment and FN DMC prediction than the G3(MCG3) models. Barrier heights predicted from the relatively more economic DFT methods are within a few tenths kcal of the FN DMC prediction. MP2 method severely underestimates the barrier height. FN DMC prediction for the reaction energy is -17.25+/-0.31 kcal/mol, setting an upper limit for the reaction energies predicted by the post Hartree-Fock methods and a lower limit for the DFT reaction energies. We provide FN DMC input for clarifying the energetic uncertainties in the critical H-transfer reaction of syn-CH3CHOO.

**候选反应（2）**：
- syn-CH3CHOO -> vinyl hydroperoxide unimolecular H-transfer
- Criegee intermediate ozonolysis channel energetics

**推荐理由**：有用的边界反例：DFT/CCSD(T) 尚可而 MP2 失效，训练 Agent 区分弱关联失效与多参考失效。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### impossible-09｜综合 8.3【推荐】｜2022

**Benchmarking the semi-stochastic CC(P;Q) approach for singlet-triplet gaps in biradicals**

- 作者：Arnab Chakraborty、Stephen H. Yuwono、J. Emiliano Deustua et al.（共 5 人）
- 出处：Journal of Chemical Physics 157, 134101
- DOI：[10.1063/5.0100165](https://doi.org/10.1063/5.0100165)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 9｜参考数据 10｜测试价值 8｜可获取 5

**摘要**：We recently proposed a semi-stochastic approach to converging high-level coupled-cluster (CC) energetics, such as those obtained in the CC calculations with singles, doubles, and triples (CCSDT), in which the deterministic CC(P;Q) framework is merged with the stochastic configuration interaction Quantum Monte Carlo propagations [J. E. Deustua, J. Shen, and P. Piecuch, Phys. Rev. Lett. 119, 223003 (2017)]. In this work, we investigate the ability of the semi-stochastic CC(P;Q) methodology to recover the CCSDT energies of the lowest singlet and triplet states and the corresponding singlet-triplet gaps of biradical systems using methylene, (HFH)-, cyclobutadiene, cyclopentadienyl cation, and trimethylenemethane as examples.

**候选反应（4）**：
- methylene (CH2) singlet-triplet gap
- trimethylenemethane (TMM) singlet-triplet gap and planar vs twisted conformers
- cyclopentadienyl cation singlet-triplet gap (antiaromatic 4pi ground state)
- cyclobutadiene singlet-triplet gap

**推荐理由**：一篇同时给 5 个经典多参考体系的 CCSDT 级单三态能隙，性价比极高的真值库。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### impossible-08｜综合 8.1【推荐】｜1999

**Ab Initio and DFT Calculations on the Cope Rearrangement of 1,2,6-Heptatriene**

- 作者：David A. Hrovat、Weston Thatcher Borden（共 2 人）
- 出处：Journal of the American Chemical Society
- DOI：[10.1021/ja983032j](https://doi.org/10.1021/ja983032j)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 9｜参考数据 8｜测试价值 9｜可获取 5

**摘要**：(8/8)CASSCF, CASPT2, and B3LYP calculations have been performed on the potential surface for the Cope rearrangement of 1,2,6-heptatriene (1) to 3-methylene-1,5-hexadiene (3). Although an allylic diradical intermediate (2) has been located, the transition states connecting it to 1 and 3 show little allylic delocalization. The first of these transition states is higher in energy than the second. [Abstract excerpt retrieved from the ACS landing page via web search.]

**候选反应（2）**：
- Cope rearrangement of 1,2,6-heptatriene to 3-methylene-1,5-hexadiene via allylic diradical intermediate
- parent 1,5-hexadiene Cope rearrangement (concerted vs stepwise diradicaloid)

**推荐理由**：双自由基oid Cope 重排的 CASSCF/CASPT2 vs B3LYP 对照标杆；付费墙但结论被综述广泛引用。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### impossible-11｜综合 7.2【备选】｜2020

**Extended dynamically weighted CASPT2: the best of two worlds**

- 作者：Stefano Battaglia、Roland Lindh（共 2 人）
- 出处：Journal of Chemical Theory and Computation (DOI 10.1021/acs.jctc.9b01129)
- DOI：[10.1021/acs.jctc.9b01129](https://doi.org/10.1021/acs.jctc.9b01129)
- 获取：✅ 已下载 PDF `2020_Battaglia_xdwcaspt2.pdf`（OA）
- 分项：体系适配 6｜参考数据 8｜测试价值 7｜可获取 9

**摘要**：We introduce a new variant of the complete active space second-order perturbation theory (CASPT2) method that performs similarly to multistate CASPT2 (MS-CASPT2) in regions of the potential energy surface where the electronic states are energetically well separated and is akin to extended MS-CASPT2 (XMS-CASPT2) in case the underlying zeroth-order references are near-degenerate. Our approach follows a recipe analogous to XMS-CASPT2 to ensure approximate invariance under unitary transformations of the model states and a dynamical weighting scheme to smoothly interpolate the Fock operator between a state-specific and a state-average regime. The resulting extended dynamically weighted CASPT2 (XDW-CASPT2) methodology possesses the most desirable features of both MS-CASPT2 and XMS-CASPT2, i.e. the ability to provide accurate transition energies and correctly describe avoided crossings and conical intersections. The reliability of XDW-CASPT2 is assessed on a number of molecular systems. First, we consider the dissociation of lithium fluoride, highlighting the distinctive characteristics of the new approach. Second, the invariance of the theory is investigated by studying the conical intersection of the distorted allene molecule. Finally, the relative accuracy in the calculation of vertical excitation energies is benchmarked on a set of 26 organic compounds.

**候选反应（3）**：
- LiF dissociation curve (ionic-covalent avoided crossing)
- distorted allene conical intersection topology
- 26-organic-molecule excitation benchmark (method calibration)

**推荐理由**：LiF 解离避免交叉等强关联案例，方法学色彩浓于反应体系色彩。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### impossible-10｜综合 6.7【备选】｜2023

**S-Diagnostic - An a Posteriori Error Assessment for Single-Reference Coupled-Cluster Methods**

- 作者：Fabian M. Faulstich、Hakon E. Kristiansen、Mihaly A. Csirik et al.（共 6 人）
- 出处：Journal of Physical Chemistry A
- DOI：[10.1021/acs.jpca.3c01575](https://doi.org/10.1021/acs.jpca.3c01575)
- 获取：❌ 未下载（付费墙，仅元数据+摘要）
- 分项：体系适配 6｜参考数据 7｜测试价值 8｜可获取 5

**摘要**：We propose a novel a posteriori error assessment for the single-reference coupled-cluster (SRCC) method called the S-diagnostic. We provide a derivation of the S-diagnostic that is rooted in the mathematical analysis of different SRCC variants. We numerically scrutinized the S-diagnostic, testing its performance for (1) geometry optimizations, (2) electronic correlation simulations of systems with varying numerical difficulty, and (3) the square-planar copper complexes [CuCl4]2-, [Cu(NH3)4]2+, and [Cu(H2O)4]2+. Throughout the numerical investigations, the S-diagnostic is compared to other SRCC diagnostic procedures, that is, the T1, D1, and D2 diagnostics as well as different indices of multi-determinantal and multi-reference character in coupled-cluster theory. Our numerical investigations show that the S-diagnostic outperforms the T1, D1, and D2 diagnostics and is comparable to the indices of multi-determinantal and multi-reference character in coupled-cluster theory in their individual fields of applicability.

**候选反应（1）**：
- n/a - diagnostic methodology paper; provides criteria (T1/D1/D2/S-diagnostic) for judging when single-reference CC/DFT conclusions should be rejected

**推荐理由**：单参考诊断方法学论文（T1/D1/D2/S-diagnostic），作为'何时应怀疑单参考结果'的判据引用而非选题来源。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

### impossible-12｜综合 6.7【备选】｜2023

**Multiconfigurational quantum chemistry: The CASPT2 method**

- 作者：Stefano Battaglia、Ignacio Fdez. Galvan、Roland Lindh（共 3 人）
- 出处：In Theoretical and Computational Photochemistry; Elsevier, pp 135-162
- DOI：[10.1016/B978-0-323-91738-4.00016-6](https://doi.org/10.1016/B978-0-323-91738-4.00016-6)
- 获取：✅ 已下载 PDF `2023_Battaglia_caspt2_chapter.pdf`（OA）
- 分项：体系适配 5｜参考数据 7｜测试价值 7｜可获取 9

**摘要**：This chapter presents the theory behind the CASPT2 method and its adaptation to a multi-state formalism. The chapter starts with an introduction of the theory of the CASPT2 method - an application of Rayleigh-Schrodinger perturbation theory applied to multiconfigurational reference function - as it was originally presented. In particular, we discuss the nature of the reference Hamiltonian and the first-order interacting space. This is followed by some detailed discussion with respect to the intruder state problem and various shift techniques to address this problem. Afterwards a longer review on alternative reference Hamiltonians, which to some degree or completely remove the intruder state problem, is put forward. Subsequently the presently proposed multi-state versions of the CASPT2 method are discussed in some detail. The chapter is concluded with a review of different benchmark assessments of the accuracy of the method and a qualified suggestion on the future development potentials of the approach.

**候选反应（1）**：
- n/a - methodology reference chapter supporting CASPT2/NEVPT2-level treatment decisions for multireference reactions

**推荐理由**：CASPT2 权威综述章节，作方法学锚点文档保留，不用于直接出题。

`筛选标记`：☐ 入选　☐ 待定　☐ 排除

---
## 筛选建议

- **Easy**：必选 8 篇（easy-01/02/03/05/06/07/09/12）已足以覆盖 30 题，easy-08 视互变异构类需求增补。
- **Normal**：必选 2 篇打底（normal-06/08），从推荐档（01/02/04/07/11/12）按机理类型均衡挑 5–6 篇；normal-05 建议改投 Impossible 作方法依赖性案例。
- **Hard**：必选 4 篇（hard-01/04/08/15）覆盖 endo/exo、torquoselectivity、偶极环加成三大主题，推荐档按轴手性/不对称催化需求补 3–4 篇。
- **Impossible**：必选 6 篇（imp-01/02/03/04/05/07）即够 20 题；impossible-06 作为'边界反例'强烈建议保留。
- 每篇可出 1–3 题，注意跨文献的重复体系（如 BHPERI 同时见于 easy-01/02/12，环丁二烯同时见于 imp-01/02/09）。

> 筛选完成后请回复入选编号清单（如 `easy-01, easy-05, normal-06, …`），将据此生成正式反应清单与自动化评测脚本。
