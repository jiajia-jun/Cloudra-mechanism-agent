# Cloudra Overleaf 交付

更新日期：2026年11月2日。

本轮本地同步：正式分数接入 target-correspondence Accuracy overlay（整体均分 0.7176；Impossible Brief 0.6029 / Guided 0.5051 / Record 0.2925）；中英文结果与讨论、SI 详细结果与 matcher 节已对齐；bench 图件已拷入 Overleaf 工程；交付 ZIP 已重建。本机无 XeLaTeX，PDF 预览未重编译；在线 Overleaf 另传。核对见 output/Cloudra_Overleaf/local_sync_20261102.json。

更新日期：2026年11月1日。

本地当前版已同步 STACKED 架构图：中英文均使用矢量 PDF 并保留可编辑 SVG，图4及对应图注匹配；英文23页（图4在第4页），中文19页（图4在第3页）。两版均保留最新正文、最终评分、杨程驿的第一及通讯作者身份和学校邮箱。四份现有同名／“P2更新”源码ZIP同步各自39个正式源文件；桌面PDF与arXiv准备包也已更新。本次仅本地同步，在线Overleaf和其他远端不变；下方线上同步记录描述此前版本。

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

本轮版式修订已在 Overleaf 编译并检查：英文 23 页，中文 19 页。正文采用自然双栏和跨栏浮动图，去除手工锁页、锁列造成的空白；完整 50 题矩阵占一页。原第三章内容连续衔接，图1–24均完整保留。线上下载的源项目各37个文件，逐文件与本地一致。两版均有44条实际引用，科学方法及直接用于分析的软件均在对应位置引用；不以 nocite 填充参考文献。

仓库内可编辑主稿及维护说明见 [paper/overleaf](../../paper/overleaf/README.md)。

图4、12、15、17已于2026年10月30日更新为分层卡片与矢量框体图，文字边界及论文中的实际显示已检查。源图见 [框体图目录](../../paper/figures/box_diagrams_20261030/README.md)。

原第三章 3.2 与 3.3 保留，3.4“工作流引导、局限与展望”随 P2 结果更新。

首页摘要已按仓库humanizer修订，保留科学内容及全部定量结果，中英文同步；摘要源文件为各项目的 `sections/00_abstract.tex`。

作者信息已于2026年10月31日接入两版首页；完整SI初稿及配套数据见 [SI交付目录](../Cloudra_SI/README.md)。

本轮审稿修订标题为“Cloudra: Geometric Reasoning and Scientific Validation for Autonomous Reaction Mechanism Exploration”。主干模型明确为DeepSeek-v4.1-flash（1017），调用别名单独记录；新增反例轨迹分析与条件性匹配敏感性，正式分数未改。[审稿回复与本轮核查](../Cloudra_Revision_20261031/Response_to_Reviewers_EN.md)。

2026年11月1日：已落实Astra提出的三处小修，统一Mean S列头、相对位移表述及B_axis总分符号；中英文正文与SI已同步Overleaf并重新导出，页数保持23/19/31。公式、阈值、正式分数和数据包未改。审阅和arXiv准备清单见 [发布准备目录](../Cloudra_arXiv_20261101/arXiv发布准备.md)。

2026年11月1日数据公开更新：中英文正文和SI第S7节已加入[研究数据公开目录](https://drive.google.com/drive/folders/1yZo3eJuCUuAgedQztgCtLyJcc8MZipf7)，并同步Overleaf。新版PDF为23/19/31页；正式评分与SI数据ZIP保持不变。各包获取方式见[数据交付说明](../../docs/benchmarks/P2_DELIVERY.md)。

2026年11月1日核心表述修订：摘要与贡献明确化学意图、分子身份、几何操作和计算证据的持续对应；基准开篇明确所衡量的研究能力，局部实验明确语义对应如何影响判断与动作。实验事实、评分定义和原有限定保留。中文版此前遗漏的最终分数、F4相关解释及七张共用基准图已与英文定稿同步。两版已同步到现有Overleaf项目并重新编译，均为0个编译错误，英文23页、中文19页；下载回存的两版PDF及四份同名/“P2更新”项目ZIP已更新。每版37个源文件均经下载逐字节核对；英文项目另保留一份上传的源包备份。核对记录见[同步记录](overleaf_sync_20261101.json)。SI未改。
