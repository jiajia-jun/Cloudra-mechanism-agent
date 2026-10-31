# Cloudra Overleaf 交付

更新日期：2026年10月31日。

两版论文已迁移为完整 LaTeX 项目。后续正文、公式、图表和参考文献以项目中的 TeX 与 BibTeX 文件为准，旧 Word 保留为迁移前审阅快照。

| 版本 | 可导入项目包 | 排版预览 |
| --- | --- | --- |
| 英文 | [Cloudra_Manuscript_EN.zip](Cloudra_Manuscript_EN.zip) | [英文 PDF](Cloudra_Manuscript_EN.pdf) |
| 中文 | [Cloudra_Manuscript_ZH.zip](Cloudra_Manuscript_ZH.zip) | [中文 PDF](Cloudra_Manuscript_ZH.pdf) |

在线项目：[Cloudra_Manuscript_EN](https://www.overleaf.com/project/6ae36f82f45648027f73ed76) · [Cloudra_Manuscript_ZH](https://www.overleaf.com/project/6ae37adfaf331ac2323b4c3f)。

自行导入时，在 Overleaf 新建项目并上传对应 ZIP，以 `main.tex` 为主文件，选择 **XeLaTeX、TeX Live 2026**，然后编译。每个项目包均包含完整正文、参考文献和图件。

后续直接编辑 `sections/` 中的正文，文献在 `references.bib` 中维护，图件放在 `figures/`。方法 2.6 包含 Benchmark 设计；结果 3.1 纳入 P1b 的 48 次重复运行，以及 P2 的四臂 × 50 题完整 200 次结果。Guided 与同一 Backbone 为主比较，Record 和 Brief 为消融比较。

P2 逐运行的图结构、自洽性和准确度共 600 个分项均已对应其原有评分记录，200 个综合分数保持不变。将既有对话、报告、计算日志及结构整理成统一机理图，是正式离线评测方法的一部分；整理过程不新增量化计算，也不补造原运行没有的科学结论或证据。

正文使用 7 组矢量图，覆盖整体与分层得分、三个评分分项、图交付与离线组织、速度与计算投入、全部 50 题、科学归属案例及 Brief/Impossible 表现。两张逐题分图合为一张完整全页矩阵，800 个数值保持不变。可先查看 [P2 图册](P2更新审阅/Cloudra_P2_图件.pdf)，共 7 页；[历史图册入口](P2更新审阅/Cloudra_P2_八组图.pdf) 保留原文件名，内容同为 7 页。各图的 PDF、SVG、PNG、数据及图注见 [P2 图件目录](../../paper/figures/benchmark_p2_20261031/)。[自包含复算记录](P2更新审阅/publication_replay_validation.json)确认 600 个分项与 200 个总分逐项重现。

本轮版式修订已在 Overleaf 编译并检查：英文 22 页，中文 19 页。正文采用自然双栏和跨栏浮动图，去除手工锁页、锁列造成的空白；完整 50 题矩阵占一页。原第三章内容连续衔接，图1–24均完整保留。线上下载的源项目各35个文件，逐文件与本地一致。两版均有43条实际引用，科学方法及直接用于分析的软件均在对应位置引用；不以 nocite 填充参考文献。

仓库内可编辑主稿及维护说明见 [paper/overleaf](../../paper/overleaf/README.md)。

图4、12、15、17已于2026年10月30日更新为分层卡片与矢量框体图，文字边界及论文中的实际显示已检查。源图见 [框体图目录](../../paper/figures/box_diagrams_20261030/README.md)。

原第三章 3.2 与 3.3 保留，3.4“工作流引导、局限与展望”随 P2 结果更新。
