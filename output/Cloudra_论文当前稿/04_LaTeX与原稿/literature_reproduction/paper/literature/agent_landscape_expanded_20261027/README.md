# 化学 AI Agent 系统文献样本与配图：2026-10-27

保留此前70项，新增15项，共 **85个分别描述的化学 AI Agent 系统**。本轮41条检索日志与此前54条日志均保留；日志条数不是独立检索实验次数。统计是持续扩充、有逐项证据的文献样本，不声称已穷尽所有Agent，也不估计全领域占比。

| 实际展示的研究对象 | 化学 AI Agent 系统数 | 样本占比 |
|---|---:|---:|
| 材料、晶体与表面 | 39 | 45.9% |
| 有限分子与配合物 | 23 | 27.1% |
| 分子液体、软物质与生物分子 | 12 | 14.1% |
| 实际展示多个对象类别 | 11 | 12.9% |
| 合计 | 85 | 100% |

各项只计一次。周期性边界条件不等于晶体材料；蛋白、液体和聚合物周期盒仍按其实际对象分类。跨类依据实际展示，而非后端支持清单。第一套DynaMate的跨类依据包含MOF结构构建，不代表已完成MOF物理模拟。

## 查漏范围

三路分别查找分子量子化学/反应机理、材料/表面/催化、动力学/软物质/生物分子，追踪原文参考文献、作者项目、数据归档及2026年9–10月新工作。此前无法核读的CatGo、ChatMat和另一套DynaMate已有原始算例依据；新增近期系统包括PULSES、GBClaw、Agent-E2MD等。

本轮对照 [Dral等人的49系统综述](https://arxiv.org/html/2608.18508v1) 逐项查漏：44项已纳入，ArIA、Q-planner、ISAAC仍待关键原始材料；AutoSolvateWeb与约化模型的tensor-network agent因边界差异单列。[49项对应表](coverage_crosswalk_49.csv)提供逐项结果。当前85项中另有41项不在该综述的49项名单中。综述采用“已实现能力也可编码”的规则，本样本要求核读到实际工作流/算例证据，未复制其任务标记。

ChemCrow、Coscientist、CACTUS、ChemToolAgent及Tang等的ChemAgent也已在本轮筛选表中明确登记。它们是相关化学Agent，但问答、预测、化学信息学或湿实验任务不能直接加入本轮物理模拟分母。两个不同团队的ChemAgent不能混为一项。

仍未闭合的线索包括ArIA、Q-planner、ISAAC、LARA-HPC、PRAXIS-MD、MatBrain和若干官方项目。具体缺口、已查来源及访问限制见筛选表；待定不等于没有相关能力。

## 计数与任务编码

LLM须在实际执行的分子、原子或分子粗粒化物理计算中参与规划、工具调用、输入/代码修改或计算反馈决策；允许人参与和算法改进工作流。单纯预测、生成、检索、问答、湿实验编排和非LLM确定性自动化不单独构成纳入依据。

单位是分别描述的系统/架构/工作流，预印本、期刊、修订版与别名合并。QAOS与Haiqu AgenticOS是同一项；Gráfico和NAMD-Agent新版本更新证据但不增加系统数。DynaMate、DynaMate2以及两代材料MDAgent有分别描述的架构，主分析单列，另按家族合并。Mendible-Barreto等的DynaMate与Guilbert等的同名系统不同；此前发现线索中的“de Gillis”归属已纠正。

| 代码 | 核读到的正面证据 | 化学 AI Agent 系统数 |
|---|---|---:|
| T | 结构构建/编辑 | 61 |
| E | 单独展示的静态能量、电子结构或材料性质 | 61 |
| O | 几何优化/弛豫 | 53 |
| F | 振动、频率及相关热化学；粗粒化正常模单独注明 | 22 |
| R | 显式路径/TS搜索，含固体结构NEB | 11 |
| D | 分子/量子动力学；MD得到的PMF等归在这里 | 37 |

任务可重叠。空心圆表示未编码，不表示没有能力。任务覆盖不代表成功率、难度、完整交付或科学验收。R的11项不能写成11个有机机理发现Agent；当前编码没有单独给出“有机机理探索”的数量。反应轨迹、自由能图、固定扫描、MD能量和普通代码参数优化不自动计为R、F、E或分子几何优化。

## 证据与敏感性

全部条目均有来源、位置、概述和限制；部分原始论文通过作者归档、论文镜像或原文索引读取，访问限制逐项说明。Protomia、Chelatron、matmcp依赖官方项目演示，不能当作独立论文评测。QAOS有人执行计算；MLP Copilot包含人审规划/验证辅助，不能表述为自主提交全部计算。

| 统计口径 | N | 材料 | 分子 | 软物质 | 跨类 |
|---|---:|---:|---:|---:|---:|
| 分别描述的系统/工作流 | 85 | 39 | 23 | 12 | 11 |
| 合并El Agente、两代MDAgent、MatAgent/ChatMat、DynaMate/DynaMate2家族 | 75 | 37 | 17 | 11 | 10 |
| 去掉3项仅官方演示的系统 | 82 | 38 | 21 | 12 | 11 |
| 再去掉MLP Copilot | 81 | 37 | 21 | 12 | 11 |

TSBench的benchmark内置Agent仍在外围单列。日期是本轮定位到的公开日期，部分不是确定的最早首发；不据此画精确增长曲线。各敏感性口径用于展示边界影响，不选择性报告某个比例。

## 图件与使用

图件目录：`../../figures/agent_landscape_acid_20261027/`。共18张中英文面板，每张有可编辑SVG、矢量PDF及400dpi PNG。每张宽86mm，最小字号7.5pt，矩阵每面板至多14行；完整矩阵覆盖85项，每种语言各出现一次。Cloudra不计入文献样本分母。

采用深绿、橄榄绿及柠檬黄，细线点图代替粗横条。颜色与结构总览中的绿黄体系衔接；灰度下仍可通过文字、位置及实心/空心区分。设计依据及输出说明见 [visual_style.md](visual_style.md)。

配图描述已筛选研究版图。Cloudra的定位与性能证据分开：几何算子和证据DAG是设计重点，改进幅度、机理正确性及难度比较仍须由对应benchmark支持。新发现的近邻见 [near_neighbours_zh.md](near_neighbours_zh.md)；这些阅读笔记不修改用户已定稿的中文表述。

## 文件与重现

- [逐项清单](catalogue_zh.md)、[来源表](source_index.csv)、[结构化记录](systems.json)、[计数](counts.json)。
- [本轮筛选](screening.json)、[检索日志](search_log.json)、[版本/家族修订](amendments.json)。此前筛选历史保留在上一版目录。
- `research/`保存三路原始记录，`build_dataset.py`合并数据，`plot_figures.py`直接从系统记录计算所有图中计数。

在仓库根目录执行：

```sh
.venv/bin/python paper/literature/agent_landscape_expanded_20261027/build_dataset.py
MPLCONFIGDIR=/private/tmp/cloudra-landscape-mpl .venv/bin/python paper/literature/agent_landscape_expanded_20261027/plot_figures.py
```

独立复核已检查新增15项与基线的重名/别名、任务证据索引、家族合并及关键近邻原文；发现的两处家族标签已统一。没有启动或修改Cloudra计算与benchmark。
