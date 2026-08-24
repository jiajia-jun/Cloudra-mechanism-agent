# EASY 梯队候选反应来源文献（benchmark_literature/easy）

**梯队定义**：单步基元反应、重原子数 ≤7、机理明确无争议、xTB 全流程可顺畅计算（参考 RDB7 分子量区间）。用于考察 Agent 的基础闭环能力。
**收集日期**：2026-08-24 · **入库**：12 篇（5 篇已存 PDF，7 篇仅元数据）

## 检索策略
- 主源：OpenAlex API（`api.openalex.org`，含 works 端点按 DOI 精查 OA 状态与 green OA 仓库位置）；openalex_searcher 工具在高峰期 503/429 限流，改用 web_fetcher 直连 API + `mailto` 礼貌池。
- 补充：paper_searcher（arXiv 命中质量差，多返回核物理/ML 噪声，未采用）、web_search（duckduckgo；bing 后端返回无关结果，弃用）。
- OA PDF 下载渠道：期刊官网直链（Nature/MDPI 被 Cloudflare 拦）→ Europe PMC `?pdf=render`（成功率高）→ 机构库（UNSW/UWA/Minerva 均被 Incapsula/Cloudflare 或 TLS 拦截，多次失败后放弃，记 pdf_file=null）。
- 关键词：pericyclic benchmark、SN2/E2 competition、keto-enol tautomerization barrier、barrier heights database (NHTBH38/BHPERI/HTBH38)、DLPNO-CCSD(T) dataset、autodE reaction profiles。

## 索引

### easy-01 ✅ PDF
- **Guner, Khuong, Leach, Lee, Bartberger, Houk (2003)**, *J. Phys. Chem. A* 107, 11445. DOI: 10.1021/jp035501w
- 摘要：提供 11 个不饱和烃周环反应的实验与理论数据，实验数据标准化至 ΔH‡(0K)；对比 HF、MP2、CASSCF、CASPT2、DFT（B3LYP/BPW91/MPW1K/KMLYP）与 CBS-QB3 的 TS 几何、活化焓/熵与反应焓/熵。若干 DFT 在活化焓上媲美 CASPT2/CBS-QB3。
- 推荐理由：Houk 组周环基准基石文献，小分子、机理无争议、有实验真值。
- 候选反应：butadiene+ethylene Diels-Alder；cyclobutene 电环化开环；1,3-cyclohexadiene 开环；[1,5]-H 迁移（1,3-戊二烯）；1,5-己二烯 Cope 重排；ene 反应；环戊二烯二聚。
- 本地文件：`2003_guner_pericyclic.pdf`（作者自存档版，home.sandiego.edu）

### easy-02 （OA 元数据，PDF 未能获取）
- **Karton & Goerigk (2015)**, *J. Comput. Chem.* 36, 622. DOI: 10.1002/jcc.23837
- 摘要：用 Wn-F12 高精度方案获得 BHPERI 数据集 26 个周环反应的准确能垒；证明 CBS-QB3 有 ~2.5 kcal/mol RMSD 的意外大误差，G4 型与估计 CCSD(T)/CBS 误差低于 1 kcal/mol 化学精度阈值；更换参考值后 DFT 排名显著变化（PW6B95-D3(BJ)、PWPB95-D3(BJ) 最优）。
- 推荐理由：BHPERI 的现行高精度参考值来源，周环小分子反应能垒真值。
- 候选反应：butadiene+ethylene DA；cyclobutene 开环；1,3,5-hexatriene 电环化；BHPERI 各 [1,5]-H 迁移/电环化反应。
- OA 说明：green OA（墨尔本大学 Minerva Access, hdl.handle.net/11343/58563），落地页被 Incapsula 拦截，未取得 PDF。

### easy-03 （OA 元数据，PDF 未能获取）
- **Karton (2019)**, *J. Phys. Chem. A* 123, 6720. DOI: 10.1021/acs.jpca.9b04611
- 摘要：考察 28 个反应能垒的 post-CCSD(T) 贡献（至 CCSDT(Q)）的基组收敛，聚焦 4–7 个非氢原子的较大 TS；集合含周环、双极环加成、环反转与多质子转移反应；T−(T)/(Q) 贡献在双 ζ 基组即可用且可缩放校正；环反转反应的 post-CCSD(T) 贡献使能垒降低 4.1–6.7 kJ/mol。
- 推荐理由：明确以"4–7 非氢原子 TS"为对象，与 EASY 定义完全对齐，提供极限精度参考。
- 候选反应：4–7 非氢原子 TS 的周环反应；1,3-偶极环加成；环反转；多质子转移。
- OA 说明：green OA（UWA repository），被 Cloudflare 拦截，未取得 PDF。

### easy-04 （OA 元数据，PDF 未能获取）
- **Sandler, Chen, Taylor, Sharma, Ho (2021)**, *J. Phys. Chem. A* 125, 1553. DOI: 10.1021/acs.jpca.0c11270
- 摘要：直接比较正则 CCSD(T) 与 TightPNO DLPNO-CCSD(T) 在多类反应上的反应能与能垒；数据集含酸度、阴离子结合能、enolization、Diels-Alder、亲核取代与原子转移反应；DLPNO 误差对小体系不敏感但随体系增大单调上升，Diels-Alder 能垒误差可超 5 kJ/mol。
- 推荐理由：数据集显式覆盖 enolization/DA/SN2/原子转移小分子反应，附 CCSD(T) 参考。
- 候选反应：keto-enol enolization；小型 DA；气相 SN2；Cl/H 原子转移。
- OA 说明：green OA（UNSW unsworks 直链），本机 TLS 握手持续失败（3 种客户端均失败），未取得 PDF。

### easy-05 ✅ PDF
- **Vermeeren, Hansen, Jansen, Swart, Hamlin, Bickelhaupt (2020)**, *Chem. Eur. J.* 26, 15538. DOI: 10.1002/chem.202003831
- 摘要：以 ZORA-OLYP/TZ2P 相对论 DFT 系统探索 X− + C2H5Y（X,Y = F,Cl,Br,I,At）的 SN2/E2 势能面；提出"特征畸变度"与"过渡态酸度"概念，用活化应变分析统一解释 Lewis 碱作亲核试剂还是碱的趋势。
- 推荐理由：E2/SN2 竞争的统一框架，最小体系 3 重原子，机理教科书级明确。
- 候选反应：F−+C2H5Cl SN2 背面进攻；F−+C2H5Cl E2 反式消除；Cl−+C2H5F SN2；卤素全系列竞争。
- 本地文件：`2020_vermeerder_sn2e2.pdf`（Europe PMC, PMC7756690）

### easy-06 ✅ PDF
- **Stuyver, Jorner, Coley (2023)**, *Scientific Data* 10, 66. DOI: 10.1038/s41597-023-01977-8
- 摘要：基于 autodE 自动工作流计算 5000+ 条 [3+2] 偶极环加成反应剖面（合成亲偶极体+生物启发结构）；经基准研究选定 B3LYP-D3(BJ)/def2-TZVP//def2-SVP，SMD 水模型模拟生理条件。
- 推荐理由：大规模反应剖面数据集；小型偶极子+乙烯原型反应（O3、甲亚胺叶立德、叠氮+乙烯）重原子数 ≤7。
- 候选反应：O3+ethylene 生成初级臭氧化物；nitrone+ethylene；azide+ethylene；其他小偶极子原型。
- 本地文件：`2023_stuyver_32cycloaddition.pdf`（Nature 金色 OA）

### easy-07 ✅ PDF
- **Zhen, Zhao, Fu, Wang, Sun, Yang, Zhang (2023)**, *Molecules* 28, 6269. DOI: 10.3390/molecules28176269
- 摘要：以量子化学计算与从头算分子动力学系统研究气相 F− + RY（R = CH3, C2H5, iC3H7, tC4H9; Y = Cl, I）的 E2/SN2 竞争，聚焦甲基取代与离去基团效应。
- 推荐理由：MDPI 金色 OA；F−+CH3Cl 仅 3 重原子；与 easy-05 互补（静态能垒 vs 动力学）。
- 候选反应：F−+CH3Cl SN2；F−+CH3I SN2；F−+C2H5Cl E2/SN2；F−+iC3H7Cl E2/SN2。
- 本地文件：`2023_zhen_e2sn2.pdf`（Europe PMC, PMC10490392）

### easy-08 ✅ PDF
- **Jana & Ganguly (2018)**, *ACS Omega* 3, 13095. DOI: 10.1021/acsomega.8b01008
- 摘要：M062X-SMD(aq)/6-31+G(d,p)//M062X/6-31+G(d,p) 研究 α-/β-环二酮环尺寸对 keto-enol 互变异构的影响；α-环丙二酮气相活化自由能垒 54.9 kcal/mol；一分子水协助能垒近乎减半，两分子水再降 ~10 kcal/mol；β-环丁二酮因 TS 环张力不利于互变异构。
- 推荐理由：小环（3–6 重原子）互变异构+水协助质子转移双主题，能垒数值明确。
- 候选反应：α-环丙二酮 keto-enol（气相/1H2O/2H2O 协助）；β-环丁二酮 keto-enol。
- 本地文件：`2018_jana_ketoenol.pdf`（Europe PMC, PMC6644555）

### easy-09 （付费墙，仅元数据）
- **Zhao, González-García, Truhlar (2005)**, *J. Phys. Chem. A* 109, 2012. DOI: 10.1021/jp045141s
- 摘要：用 W1 计算建立 19 个非氢转移反应的正反向能垒基准库（NHTBH38/04），并连同氢转移库测试 29 个 DFT 与 6 个 WFT 方法；BB1K 最佳，B3LYP 平均无符号误差为其 4 倍。
- 推荐理由：原子转移/恒等 SN2/单分子异构（HNC→HCN 等）的经典 W1 真值，体系极小。
- 候选反应：H+N2O→OH+N2；CH3+FCl→CH3F+Cl；F−+CH3F 恒等 SN2；Cl−+CH3Cl 恒等 SN2；HNC→HCN。

### easy-10 （付费墙，仅元数据）
- **Mardirossian & Head-Gordon (2016)**, *J. Chem. Theory Comput.* 12, 4303. DOI: 10.1021/acs.jctc.6b00637
- 摘要：在 4986 数据点（84 个子集）上基准测试 14 个 Minnesota 泛函，涵盖非共价作用、异构化能、热化学与能垒；杂化泛函中 M06-2X/M08-HX/M08-SO/MN15 能垒表现好，推荐 M06-2X 与 MN15 为通用选择。
- 推荐理由：汇总含 HTBH38/NHTBH38/BHPERI 的小反应能垒基准数据库，方向 (c)。
- 候选反应：HTBH38 氢转移（H+CH4、H+C2H6 等）；NHTBH38 非氢转移；BHPERI 周环子集。

### easy-11 （付费墙，仅元数据）
- **Young, Silcock, Sterling, Duarte (2021)**, *Angew. Chem. Int. Ed.* 60, 4266. DOI: 10.1002/anie.202011941
- 摘要：开源 Python 包 autodE 可从 1D/2D 表示自动定位 TS 与极小点、输出完整反应剖面，涵盖加成、取代、消除、迁移插入、氧化加成、还原消除等反应类别，含构象采样并兼容多电子结构软件；以 Co/Rh 催化氢甲酰化与 Ireland-Claisen 重排示范。
- 推荐理由：自动剖面工具对标 Agent 闭环；easy-06 数据集即由 autodE 生成。
- 候选反应：HX 对烯烃加成；小分子取代/消除。

### easy-12 （already_held，仅元数据）
- **Goerigk et al. (2017)**, *Phys. Chem. Chem. Phys.* 19, 32184. DOI: 10.1039/c7cp04913g
- 摘要：GMTKN55 基准数据库：1505 个相对能量、2462 个单点，13 个新子集，更高质量参考值；强调色散校正必要性；双杂化泛函（DSD-BLYP-D3(BJ) 等）热化学/非共价最可靠。
- 推荐理由：含 BHPERI、BH76、RC21 小反应能垒子集，真值汇总出处。本地已存 `docs/benchmark_survey/pdfs/gmtkn55.pdf`，**already_held: true**，不重复下载。
- 候选反应：BHPERI 周环子集；BH76（H/重原子转移）；RC21 小有机反应能量。

## 覆盖反应类型
周环（DA/电环化开环/σ迁移/Cope/ene）、SN2、E2/SN2 竞争、[3+2] 偶极环加成、keto-enol 互变异构（含小环二酮与水协助）、原子转移（H/Cl）、单分子异构（HNC→HCN）、自动剖面方法学。

## 已知限制
- 机构库（UNSW/UWA/Minerva/KAUST）均被反爬/TLS 拦截，easy-02/03/04 的 OA PDF 未能获取，建议有校园网/代理环境时按 OA URL 补下。
- arXiv 后端检索化学关键词返回大量无关结果；Bing 后端返回垃圾结果；均已弃用并在上文注明。
