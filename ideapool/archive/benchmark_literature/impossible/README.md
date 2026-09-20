# IMPOSSIBLE 梯队候选文献库（多参考态 / 复杂开壳层反应体系）

定义：具有显著多参考态特征或复杂开壳层电子态的有机/小分子反应体系（需 CASSCF/NEVPT2/MRCI 级别方可可靠描述，单参考 DFT 会给出错误结论）。用于考察 Agent 能否识别方法边界并合理拒答——合理拒答得分、盲目论断扣分。

- 入库：**12 篇**（metadata.json，id 前缀 `impossible-`）
- 成功下载 OA PDF：**9 个**（均经 `file` 验证为真实 PDF）
- 仅元数据（付费墙）：**3 篇**（impossible-08 / 09 / 10）
- 注：Kulik 课题组多参考态诊断论文（Duan et al. 2020）**已持有**于 `docs/benchmark_survey/pdfs/mr_detection_duan2020.pdf`，未重复入库；impossible-10（S-diagnostic）为其互补。
- 检索记录：OpenAlex 匿名检索全程 503 不可用（搜索集群过载），改用 arXiv（paper_searcher）+ DuckDuckGo（web_search）+ CrossRef API 完成。Bing 后端返回噪声结果，弃用。

## 覆盖的反应类型（方向 a–d 对照）

| 方向 | 覆盖体系 | 来源 |
|---|---|---|
| (a) 经典多参考态反应 | 环丁二烯自动异构化 | impossible-01, 02 |
| | 四亚甲基乙烷（TME）扭转 PES | impossible-03 |
| | o/m/p-苯炔（脱氢苯）单三态能隙 | impossible-04 |
| | 单线态/三线态卡宾（8000 骨架 MRCI 库） | impossible-05 |
| | 臭氧化 / Criegee 中间体 H 转移 | impossible-06 |
| | π 键断裂（乙烯扭转双自由基） | impossible-07 |
| | Cope 重排双自由基oid 过渡态 | impossible-08 |
| | TMM、环戊二烯基正离子、CH2 能隙 | impossible-09 |
| | LiF 键解离、丙二烯锥形交叉 | impossible-11 |
| (b) CASSCF/NEVPT2 机理研究 | 01, 02, 03, 07, 08, 11 | 文中均明示单参考失效 |
| (c) 多参考态诊断 | S-diagnostic vs T1/D1/D2 | impossible-10（+已持有 Duan 2020） |
| (d) 自旋污染/破缺自旋 | UHF/UKS 参考选择判据（AFQMC 协议） | impossible-04 |

未充分覆盖（可后续补充）：N2H2 顺反异构、过氧化物 O–O 断裂、单线态氮宾反应——arXiv 上未检索到合适的近年 OA 文献。

---

## impossible-01
- **Reference Energies for Cyclobutadiene: Automerization and Excited States**
- Monino, Boggio-Pasqua, Scemama, Jacquemin, Loos — 2022, *J. Phys. Chem. A* 126, 4664. DOI: 10.1021/acs.jpca.2c02480
- OA（arXiv:2204.05098）｜本地 PDF：`2022_Monino_cyclobutadiene.pdf`
- 摘要：环丁二烯在 D4h 方形与 D2h 矩形几何下基态与激发态均呈多组态特征，单参考 TD-DFT/EOM-CC 已知失效。本文以 SCI、CASSCF/CASPT2/NEVPT2、CCSD→CCSDTQ 及 spin-flip 方法系统计算自动异构化势垒（方形与矩形基态能量差）与各几何下垂直激发能，给出理论最优估计（TBE）。
- 推荐理由：最经典的"单参考必然出错"反应坐标，含权威真值表，可直接做 impossible 题库真值来源。
- 候选反应：cyclobutadiene automerization (D2h → D4h TS)；D4h 几何单三态能隙。

## impossible-02
- **The Singlet-Triplet Gap of Cyclobutadiene: The CIPSI-Driven CC(P;Q) Study**
- Priyadarsini, Gururangan, Shen, Piecuch — 2025, *J. Phys. Chem. A* 129, 11749. DOI: 10.1021/acs.jpca.5c07572
- OA（arXiv:2405.15864）｜本地 PDF：`2025_Priyadarsini_cyclobutadiene_stgap.pdf`
- 摘要：双自由基单三态能隙的准确测定需平衡单线态基态的强非动态关联与三线态的动态关联。本文以 CIPSI 驱动的 CC(P;Q) 矩展开近似收敛 CCSDT 能量，给出环丁二烯沿自动异构化坐标的最低单/三线态势能面及能隙。
- 推荐理由：提供沿反应坐标全程的 CCSDT 级别势能面剖面，可检验 Agent 是否会错误地用 CCSD(T) 断言自动异构化势垒。
- 候选反应：cyclobutadiene automerization singlet/triplet PES。

## impossible-03
- **Full configuration interaction quantum Monte Carlo benchmark and multireference coupled cluster studies of tetramethyleneethane diradical**
- Veis, Antalík, Legeza, Alavi, Pittner — 2018, *J. Chem. Theory Comput.* 14, 2439–2445. DOI: 10.1021/acs.jctc.8b00022
- OA（arXiv:1801.01057）｜本地 PDF：`2018_Veis_tetramethyleneethane.pdf`
- 摘要：对 TME 在 cc-pVTZ 基组下做 FCI 质量基准计算（CASPT2(6,6) 自然轨道子空间 FCIQMC），证实单线态基态 PES 在 45° 扭转角取极大、垂直单三态能隙 0.01 eV。CAS(2,2)-MkCCSDT 能隙尚可但 PES 形状错误；DMRG(24,25) 缺动态关联同样失败；DMRG-TCCSD 形状准确但需计算 Ms=0 三线态分量才能正确排序。
- 推荐理由：教科书级双自由基 TME；连"多参考"方法家族内部都有半数失败，是 impossible 梯队判定标准的最强支撑。
- 候选反应：TME 扭转单线态/三线态 PES；TME 关环反应（见 Pozun et al. DMC 引文）。

## impossible-04
- **Singlet-Triplet Energy Gaps of Organic Biradicals and Polyacenes with Auxiliary-Field Quantum Monte Carlo**
- Shee, Arthur, Zhang, Reichman, Friesner — 2019, *J. Chem. Theory Comput.* DOI: 10.1021/acs.jctc.9b00534
- OA（arXiv:1905.13316）｜本地 PDF：`2019_Shee_benzyne_afqmc.pdf`
- 摘要：ph-AFQMC 以 CASSCF 试探波函数对 13 个强双自由基小分子及 o/m/p-苯炔的单三态能隙达到相对实验 ~1 kcal/mol 平均误差；自旋投影技术下单行列式参考亦可达到同等精度；并给出基于自旋污染程度选择 UHF/UKS 参考的协议。
- 推荐理由：覆盖苯炔三异构体（脱氢苯方向）；自旋污染驱动的参考选择协议直接对应方向 (d)。
- 候选反应：o/m/p-benzyne 单三态能隙排序；polyacene 单三态能隙；Bergman 环化能量学前提。

## impossible-05
- **Large yet bounded: Spin gap ranges in carbenes**
- Schwilk, Tahchieva, von Lilienfeld — 2020, arXiv:2004.10600（预印本）
- OA｜本地 PDF：`2020_Schwilk_carbenes_mrci.pdf`
- 摘要：对 8000 种卡宾骨架在受控精度的高阶多参考级别计算单/三线态，发现强电子关联导致所有卡宾类单三态能隙存在 ~30 kcal/mol 硬上限；QMspin 数据库含约 13000 条 MRCI 计算。
- 推荐理由：单线态卡宾强关联 → 基态自旋态指认与协同插入 vs 分步夺取机理判断都必须用多参考方法，DFT 自旋态排序常错。
- 候选反应：卡宾单/三线态基态指认（8000 骨架）；自旋态依赖的卡宾反应性。

## impossible-06
- **Quantum Monte Carlo Investigation of the H-transfer Reaction of Criegee Intermediate CH3CHOO: A Benchmark Calculation**
- Wang, Bu — 2021, arXiv:2106.11822（预印本）
- OA｜本地 PDF：`2021_Wang_criegee_qmc.pdf`
- 摘要：FN-DMC 给出 syn-CH3CHOO → 乙烯基氢过氧化物 H 转移势垒 16.60±0.35 kcal/mol（与实验吻合）；CCSD(T) 与 DFT 势垒接近 DMC，MP2 严重低估；反应能 -17.25±0.31 kcal/mol。
- 推荐理由：臭氧化/Criegee 方向代表；同时是"边界反例"——并非所有 Criegee 反应都必须多参考，训练 Agent 区分多参考失效与 MP2 类失效。
- 候选反应：syn-CH3CHOO 单分子 H 转移；Criegee 中间体臭氧化通道能量学。

## impossible-07
- **Excited state-specific CASSCF theory for the torsion of ethylene**
- Saade, Burton — 2024, arXiv:2402.13046（预印本）
- OA｜本地 PDF：`2024_Saade_ethylene_torsion.pdf`
- 摘要：以乙烯双键扭转的低激发态检验 SS-CASSCF；最小 (2e,2o) 活性空间的态特定近似可与大活性空间态平均相当；但价态/里德伯激发动态关联不平衡或非弥散基组会导致激发态解塌缩、PES 出现非物理不连续。
- 推荐理由：π 键断裂双自由基原型（90° 扭转单参考完全失效）；并揭示即使 CASSCF 方法本身也有陷阱，深化拒答教育意义。
- 候选反应：乙烯顺反扭转（π 键断裂）；乙烯基态/激发态扭转势能面。

## impossible-08（仅元数据，付费墙）
- **Ab Initio and DFT Calculations on the Cope Rearrangement of 1,2,6-Heptatriene**
- Hrovat, Borden — 1999, *J. Am. Chem. Soc.* DOI: 10.1021/ja983032j
- 落地页：https://pubs.acs.org/doi/full/10.1021/ja983032j ｜ PDF：null
- 摘要（ACS 落地页节选）：(8/8)CASSCF、CASPT2 与 B3LYP 计算 1,2,6-庚三烯 (1) → 3-亚甲基-1,5-己二烯 (3) Cope 重排势能面；定位到烯丙基双自由基中间体 (2)，但连接 1/3 的两个过渡态烯丙基离域很小，第一个过渡态能量高于第二个。
- 推荐理由：Cope 重排双自由基oid 机理的 CASSCF/CASPT2 经典文献；B3LYP 与多参考结果的对照是识别双自由基过渡态方法边界的标杆。
- 候选反应：1,2,6-heptatriene Cope 重排（双自由基中间体）；母体 1,5-hexadiene Cope 重排（协同 vs 分步）。

## impossible-09（仅元数据，付费墙）
- **Benchmarking the semi-stochastic CC(P;Q) approach for singlet-triplet gaps in biradicals**
- Chakraborty, Yuwono, Deustua, Shen, Piecuch — 2022, *J. Chem. Phys.* 157, 134101. DOI: 10.1063/5.0100165
- 落地页：https://pubs.aip.org/jcp/article/157/13/134101/2841819 ｜ PDF：null
- 摘要：半随机 CC(P;Q)（确定性矩展开 + 随机 CIQMC 传播）逼近 CCSDT 能量，以亚甲基、(HFH)⁻、环丁二烯、环戊二烯基正离子、三亚甲基甲烷为例恢复双自由基最低单/三线态能量及能隙。
- 推荐理由：一篇覆盖 5 个经典多参考态体系的 CCSDT 级真值库（含 TMM、反芳香环戊二烯基正离子——任务书点名的方向）。
- 候选反应：CH2 单三态能隙；TMM 单三态能隙与构象；环戊二烯基正离子能隙；环丁二烯能隙。

## impossible-10（仅元数据，付费墙）
- **S-Diagnostic — An a Posteriori Error Assessment for Single-Reference Coupled-Cluster Methods**
- Faulstich, Kristiansen, Csirik, Kvaal, Pedersen, Laestadius — 2023, *J. Phys. Chem. A*. DOI: 10.1021/acs.jpca.3c01575
- 落地页：https://pubs.acs.org/doi/10.1021/acs.jpca.3c01575 ｜ PDF：null
- 摘要：提出基于 SRCC 变体数学分析的新型后验误差评估 S-diagnostic；在几何优化、不同数值难度关联能模拟及方形平面铜配合物上测试，与 T1/D1/D2 及多行列式/多参考指标系统对比，S-diagnostic 优于 T1/D1/D2，并能纠正 T1/D1 对铜配合物的已知误诊。
- 推荐理由：方向 (c) 诊断方法最新代表，给 Agent 提供"何时应怀疑单参考结论"的量化判据；与已持有的 Duan 2020（mr_detection_duan2020.pdf）互补。
- 候选反应：n/a（诊断方法论文，支撑拒答判据）。

## impossible-11
- **Extended dynamically weighted CASPT2: the best of two worlds**
- Battaglia, Lindh — 2020, *J. Chem. Theory Comput.* DOI: 10.1021/acs.jctc.9b01129
- OA（arXiv:1911.04996）｜本地 PDF：`2020_Battaglia_xdwcaspt2.pdf`
- 摘要：XDW-CASPT2 在态分离好时近似 MS-CASPT2、近简并时近似 XMS-CASPT2；以 LiF 解离、扭曲丙二烯锥形交叉、26 个有机分子垂直激发能基准验证。
- 推荐理由：LiF 离子键解离（离子-共价避免交叉）与锥形交叉是单参考必败的键断裂原型；近简并下 CASPT2 变体选择影响定性结论。
- 候选反应：LiF 解离曲线；扭曲丙二烯锥形交叉；26 分子激发能基准（方法校准）。

## impossible-12
- **Multiconfigurational quantum chemistry: The CASPT2 method**
- Battaglia, Galván, Lindh — 2023, in *Theoretical and Computational Photochemistry* (Elsevier), pp 135–162. DOI: 10.1016/B978-0-323-91738-4.00016-6
- OA（arXiv:2305.06678，作者自存档）｜本地 PDF：`2023_Battaglia_caspt2_chapter.pdf`
- 摘要：CASPT2 理论综述章节：参考哈密顿量、一级相互作用空间、侵入态问题与 shift 技术、替代参考哈密顿量、多态 CASPT2 版本及精度基准评估。
- 推荐理由：impossible 梯队的"正确做法"方法学锚点——Agent 应据此判断何时必须升级至 MS-CASPT2/NEVPT2 而非用 DFT 强答。
- 候选反应：n/a（方法学参考章节）。
