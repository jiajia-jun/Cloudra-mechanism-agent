# P2 Benchmark 图件与复现

更新日期：2026年11月1日。

本目录保存接入中英文论文的 7 组 P2 图件。主比较为 Guided 与同一 Backbone（数据字段 `standard`）；Record 和 Brief（`brief-errors`）为消融比较。每组提供矢量 PDF、SVG、320 dpi PNG，以及对应的 `.data.json` 和 `.caption.txt`。

两版主稿沿用既定版式，图件作为矢量 PDF 接入现有图注、编号与交叉引用体系。配色和面板标签沿用 [论文统一图件样式](../../../scripts/model_semantics/figure_style.py)，最小图中文字为 7.4 pt。

## 正文七组图索引

| 图件 | 内容 | 源脚本 |
| --- | --- | --- |
| [bench_overview.pdf](bench_overview.pdf) | Guided–Backbone 整体与分层得分、50 题配对结果及区间 | [plot_benchmark_results.py](../../../scripts/benchmark_p2/plot_benchmark_results.py) |
| [bench_components.pdf](bench_components.pdf) | 四臂图结构、自洽性、准确度，以及主比较增益的分项来源 | [plot_benchmark_results.py](../../../scripts/benchmark_p2/plot_benchmark_results.py) |
| [bench_delivery.pdf](bench_delivery.pdf) | 运行期机理图与离线组织、40 道非 Impossible 题的完整 SC 分布、7 个离线组织结果 | [plot_speed_delivery.py](../../../scripts/benchmark_p2/plot_speed_delivery.py) |
| [bench_speed.pdf](bench_speed.pdf) | P1b 批次耗时；P2 共同 15 题的计算投入、作业终态及投入–得分配对；紧凑为 180 × 120 mm | [plot_speed_delivery.py](../../../scripts/benchmark_p2/plot_speed_delivery.py) |
| [bench_tasks_all.pdf](bench_tasks_all.pdf) | 全部 50 题、四配置、四评分层的完整全页矩阵；180 × 225 mm，共 800 格 | [plot_benchmark_results.py](../../../scripts/benchmark_p2/plot_benchmark_results.py) |
| [bench_cases.pdf](bench_cases.pdf) | HA8 能量参照、HH1 证据闭合、NU6 能差与路径归属 | [plot_benchmark_results.py](../../../scripts/benchmark_p2/plot_benchmark_results.py) |
| [bench_imp.pdf](bench_imp.pdf) | Impossible 10 题逐题表现及 Brief–Guided 的分项比较；紧凑为 180 × 120 mm | [plot_imp.py](../../../scripts/benchmark_p2/plot_imp.py) |

按上方图索引读取各组矢量 PDF，可核对本版最终结果。

逐题结果由原两张矩阵合为一张全页矩阵，按 Easy 20、Normal 10、Hard 10、Impossible 10 题分组；200 次运行的综合分与三个分项共 800 个数值全部保留，最小图中文字仍为 7.4 pt。原 [Easy/Normal 分图](bench_tasks.pdf) 与 [Hard/Impossible 分图](bench_tasks_hi.pdf) 及其 SVG、PNG、数据和图注保留为来源档案，不再单独进入正文。速度图与 IMP 图收紧内部间距至 180 × 120 mm，交付图与案例图为 180 × 105 mm；点、数字、标签和科学信息保持不变。

## 完整分项与数据来源

[publication_scores_per_run.csv](source_data/publication_scores_per_run.csv) 是出版用数据：四臂 × 50 题，共 200 个唯一运行，包含完整的 200 × 3 个图结构、自洽性和准确度分项，字段分别为 `graph_publication`、`selfc_all_publication` 和 `accuracy_publication`；`score` 为该运行已发布的综合分数。

分项来自原有离线评分表、原始评分记录及离线机理图组织的评分记录。[component_provenance.json](source_data/component_provenance.json) 保留逐条来源和行号，相关记录位于 [source_data](source_data/)。按 0.1、0.3、0.6 加权得到的结果与最终综合分的四位小数舍入一致。200 条最终记录均已完成字段及加权核对；固定评分器、最终参考定义和逐条评分来源见 [evaluation_manifest.json](../../overleaf/Cloudra_SI/companion_data/evaluation_manifest.json)。

将运行已有的对话、报告、计算日志和结构组织为统一机理图，是正式离线评测方法的一部分。`bench_delivery` 分别展示运行期生成的机理图与离线组织的机理图，分项评分采用整理后的完整记录。SC 分布按数值分为 1、0–1 之间和 0 三类；路径证据比较使用 40 道非 Impossible 题。

### 耗时与投入的单位

- **P1b：批次墙钟时间，单位 h。** 每批 4 题、并发 2；每臂 3 个批次，总计 12 个批次、48 次任务运行。数据来自 `benchmark.db` 的批次开始和结束时间。
- **P2：累计 QM job-hours。** 对每个运行的量化作业逐一累加进程耗时。图中使用四臂均有投入记录的共同 15 题，共 60 次任务运行。Backbone/M1 的投入按原有记录以原生日志 CPU time ÷ 4 整理。

两种单位分别表示批次完成时间与计算投入；图中的 P2 job-hours 不作单次研究运行墙钟时间解释。详细数据与复算脚本见 [speed_delivery](source_data/speed_delivery/)。

## 主要结果

| 臂 | 50 题平均综合分 |
| --- | ---: |
| Guided | 0.792954 |
| Backbone | 0.581390 |
| Record | 0.691798 |
| Brief | 0.754138 |

- Guided–Backbone 的逐题平均增益为 0.211564；50 题中 36 题较高、7 题较低、7 题持平。
- 增益的加权分项来源为图结构 0.010776、自洽性 0.117875、准确度 0.082916。Hard 组的平均综合分分别为 Guided 0.95765、Backbone 0.68875。
- 40 道非 Impossible 题中，SC = 1 的运行数为 Guided 24、Backbone 7、Record 16、Brief 20。Backbone 其余为 29 个中间分和 4 个零分。
- 共同 15 题的平均计算投入为 Guided 11.079、Backbone 7.555、Record 7.877、Brief 15.590 job-hours；对应平均综合分为 0.81241、0.64948、0.73595、0.72733。

## 复现

在仓库根目录执行：

```bash
uv run python scripts/benchmark_p2/prepare_publication_data.py
uv run python scripts/benchmark_p2/plot_benchmark_results.py
uv run python scripts/benchmark_p2/plot_speed_delivery.py
uv run python scripts/benchmark_p2/plot_imp.py
```

第一步从本目录保留的来源记录生成完整出版分项及聚合表，后三步生成 7 组正文图件、绘图数据与图注，并保留两张原逐题分图的来源档案。P1b 批次时间和 P2 投入的独立整理脚本也保存在 `source_data/speed_delivery/`，各图的 JSON 记录绘图数据及来源。

## 论文与数据入口

稿件源码在本机留存；预印本见 [arXiv:2611.02909](https://arxiv.org/abs/2611.02909)。[研究数据说明](../../../docs/RESEARCH_DATA_CN.md)列出配套实验数据和下载方式。
