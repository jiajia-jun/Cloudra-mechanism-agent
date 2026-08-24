# 基准测试集候选文献池（INDEX）

> 建立日期：2026-08-24；用途：为四级难度基准测试集（Easy 30 / Normal 30 / Hard 20 / Impossible 20，共 100 个反应体系，见 `ideapool/cloudra_novelty_and_validation_plan.md` 步骤 2）收集候选反应来源文献，供人工筛选。
> 收录原则：文献须包含可用量子化学计算的反应体系（明确反应物/产物、已报道机理或能垒数据）；仅下载开放获取 PDF，付费墙文献只保留元数据+摘要。

## 数据完备度总览

| 梯队 | 入库文献 | 已下载 OA PDF | 仅元数据+摘要 | 标注候选反应数 | 目标题量 |
|---|---|---|---|---|---|
| Easy | 12 | 5 | 7 | 49 | 30 |
| Normal | 12 | 7 | 5 | 25 | 30 |
| Hard | 16 | 5 | 11 | 24 | 20 |
| Impossible | 12 | 9 | 3 | 26 | 20 |
| **合计** | **52** | **26** | **26** | **124** | 100 |

- 所有 metadata.json 均通过 JSON 合法性校验；所有摘要非空（>50 字符）；所有 PDF 通过 `file` 校验为有效 PDF 文档。
- 每个梯队文件夹内：`metadata.json`（结构化条目：标题/作者/年份/期刊/DOI/URL/OA 状态/摘要/推荐理由/候选反应清单）+ `README.md`（人类可读索引）+ OA PDF。
- **人工筛选清单（推荐）：[selection.html](selection.html)** —— 交互式打标台：全部 52 条的摘要全文 + 推荐系数，每条下方「收录/待定/排除」按钮，标记自动存浏览器、可导出 JSON / 复制入选编号清单；支持按梯队与状态筛选、全文搜索。生成脚本见 [_gen_selection_html.py](_gen_selection_html.py)。
- 纯文本版：[SELECTION.md](SELECTION.md) —— 同源同值的静态清单（生成脚本 [_gen_selection.py](_gen_selection.py)）。

## 各梯队覆盖情况

### `easy/` — 单步基元反应（重原子 ≤7，xTB 全流程可算）
- 周环反应标准基准集（Guner 2003 周环反应集、高精度 CCSDT(Q)/CBS 能垒基准）
- SN2/E2 竞争与亲核性统一框架（Vermeeren 2020、甲基取代/离去基效应 2023）
- [3+2] 环加成量子化学反应剖面数据集（Sci Data 2023）
- 酮-烯醇互变异构（环尺寸与溶剂效应，ACS Omega 2018）
- 能垒基准数据库（HAT/NS/UA 2005、Minnesota 泛函评测 2016、GMTKN55 2017、autodE 2021）

### `normal/` — 多步机理 / 竞争路径（中等分子，xTB 可完整计算）
- 经典争议机理：Morita-Baylis-Hillman（JACS 2007）、Wittig 反应机理剖析与氧磷杂环丁烷形成（JOC 2019/2020）、NHC 苯偶姻缩合自由基通道（JOC 2018）
- 竞争过渡态：椅式(周环) vs 船式(赝周环) CASSCF 研究（JOC 2018）
- Diels-Alder 与极性/ene 反应竞争系列（Domingo 组 MEDT 研究 2018/2024/2025）
- Diels-Alder 反应动力学模拟（Rivero 2019/2020）
- 自动化反应网络探索（metadynamics nanoreactor，JCTC 2023）

### `hard/` — 立体化学 / 微观几何感知（endo/exo、torquoselectivity、轴手性、对映选择性）
- endo 规则起源（JCC 2014、EJOC 2005、JOC 2018 环丙烯酮类、Sci Rep 2016 反常 exo 选择性）
- 空腔限域与氢键催化调控 endo/exo（Nat Commun 2023、Chem Eur J 2021、ACS Omega 2025）
- Torquoselectivity：环丁烯开环顺旋/对旋竞争（2015/2016）、σ-受体 inward torquoselectivity（JACS 2003）
- 轴手性：阻转异构酰肼旋转能垒（Molecules 2023）
- 不对称催化对映选择性起源：手性磷酸催化氧杂环丁烷去对称化（JACS 2016）、环氧转硫杂环（ACIE 2022）、CBS 硼烷还原（J Mol Model 2020）
- Ireland-Claisen 船式/椅式过渡态竞争（JOC 2010）、硝酮 [3+2] 环加成选择性（2022）

### `impossible/` — 多参考态 / 开壳层体系（考察合理拒答）
- 环丁二烯：自动异构化参考能量（JPCA 2022）、单三态能隙 CIPSI-CC(P;Q)（JPCA 2025）
- 四亚甲基乙烷 FCIQMC 基准与多参考 CC（JCTC 2018）
- 双自由基/并苯单三态能隙 AFQMC（JCTC 2019）、卡宾自旋能隙范围（MRCI 2020）
- Criegee 中间体 H 转移 QMC 研究（2021）
- 乙烯扭转激发态特异性 CASSCF（2024）、Cope 重排双自由基oid（JACS 1999）
- 多参考诊断方法：S-diagnostic（JPCA 2023）、CC(P;Q) 双自由基基准（JCP 2022）、XDW-CASPT2（JCTC 2020）、CASPT2 综述（2023）

## 与已持有方法学文献的关系

以下基准方法学文献已在 `docs/benchmark_survey/pdfs/` 持有，本池不重复收录：rdb7、grambow2020、transition1x、bh9、gmtkn55（注：easy 梯队元数据中保留了相关条目但标注不重复下载）、mr_detection_duan2020、abstentionbench、simpleqa 等。

## 筛选建议（供人工筛选时参考）

1. 优先从已下载 PDF 的文献中提取反应（全文可查能垒数值与计算级别）；仅元数据条目多为付费墙文献，如需使用建议通过图书馆渠道获取。
2. Easy 目标 30 题：周环标准集 + SN2/E2 系列 + [3+2] 数据集已标注 49 个候选反应，余量充足。
3. Impossible 梯队注意区分两类用途：(a) 具体多参考反应体系（环丁二烯、Criegee、Cope 重排等）直接出题；(b) 诊断方法论文（S-diagnostic、CASPT2 综述）用于建立判据共识流程。
4. 防泄漏核查：筛选定题后需核对反应是否出现在常用训练语料的高频教材中（评分基于在线计算物理量，见计划文档原则 4）。
