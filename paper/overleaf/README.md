# Cloudra 双语 LaTeX 主稿

2026年11月2日同行审稿后修订：SI 的 L2 最终表、26/19-edge误差统计、manifest 与独立复现源树已同步；Impossible 使用“在当前允许方法下的物理不可达”表述。Tectonic/XeTeX 本地重编英文24页、中文20页、SI32页，上传源无未解析引用或 Overfull。200条正式评分不变，未增加计算。

以下保留此前各轮记录；当前构建核对见 `output/Cloudra_Overleaf/local_sync_20261102_peer_review.json`。

更新日期：2026年11月2日。

本轮本地同步：正式分数接入 target-correspondence Accuracy overlay（整体均分 0.7176；Impossible Brief 0.6029 / Guided 0.5051 / Record 0.2925）；中英文结果与讨论、SI 详细结果与 matcher 节已对齐；bench 图件已拷入 Overleaf 工程；交付 ZIP 已重建。本机无 XeLaTeX，PDF 预览未重编译；在线 Overleaf 另传。核对见 output/Cloudra_Overleaf/local_sync_20261102.json。

更新日期：2026年11月1日。

本地当前版已同步 STACKED 架构图：中英文均使用矢量 PDF 并保留可编辑 SVG，图4及对应图注匹配；英文23页（图4在第4页），中文19页（图4在第3页）。两版均保留最新正文、最终评分、杨程驿的第一及通讯作者身份和学校邮箱。四份现有同名／“P2更新”源码ZIP同步各自39个正式源文件；桌面PDF与arXiv准备包也已更新。本次仅本地同步，在线Overleaf和其他远端不变；下方线上同步记录描述此前版本。

两版正式排版源文件分别位于 [Cloudra_EN](Cloudra_EN/) 和 [Cloudra_ZH](Cloudra_ZH/)。各项目独立完整，在 Overleaf 中以 `main.tex` 为主文件，使用 **XeLaTeX、TeX Live 2026** 编译。

- `main.tex`：全文入口、版式和文末参考文献。
- `sections/00_abstract.tex`：首页摘要，英文原文与中文对应译文。
- `sections/`：引言、方法、结果与讨论的正文，后续直接编辑这些 TeX 文件。
- `references.bib`：参考文献条目，正文通过引用键关联来源。
- `figures/`：独立图件 PDF，图号、图注和正文引用由 LaTeX 管理。

方法 2.6 已包含 CloudraBench 设计与 50 题分布图。结果 3.1 已接入 P1b 的 48 次重复运行和 P2 四臂 × 50 题的完整 200 次结果，讨论 3.4 已随 P2 结果更新；原有 3.2 与 3.3 保留。Guided 与同一 Backbone 为主比较，Record 和 Brief 为消融比较。

两版主稿沿用既定版式。新增 7 组矢量图覆盖整体与分层得分、完整 600 个评分分项、速度与计算投入、机理图组织、全部 50 题和科学归属案例。将既有研究产物离线组织为统一机理图属于正式评测方法，整理后的 200 个综合分数保持不变。图件索引、数据来源和复现命令见 [P2 图件说明](../figures/benchmark_p2_20261031/README.md)。

英文新增正文为 [结果 3.1](Cloudra_EN/sections/03_benchmark_results.tex) 和 [讨论 3.4](Cloudra_EN/sections/03_benchmark_discussion.tex)；中文对应 [结果 3.1](Cloudra_ZH/sections/03_benchmark_results.tex) 和 [讨论 3.4](Cloudra_ZH/sections/03_benchmark_discussion.tex)。两版均通过各自的 `sections/03_results.tex` 接入。`sections/03_figures.tex` 集中声明跨栏浮动图，正文保持自然双栏流动，不用手工换页或锁列。

`build_sections.py` 记录首次从 Markdown 迁移到 LaTeX 的转换过程；后续不运行它覆盖正式 TeX。旧 Word 文件保留为迁移前的审阅快照。

可直接导入的项目包及 PDF 预览见 [Overleaf 交付目录](../../output/Cloudra_Overleaf/README.md)。

在线项目：[英文](https://www.overleaf.com/project/6ae36f82f45648027f73ed76) · [中文](https://www.overleaf.com/project/6ae37adfaf331ac2323b4c3f)。

图4、12、15、17已于2026年10月30日更新为分层卡片与矢量框体图，文字边界及论文中的实际显示已检查。源图见 [框体图目录](../figures/box_diagrams_20261030/README.md)。

英文SI独立项目为 [Cloudra_SI](Cloudra_SI/README.md)，含完整长表与证据分析；编译PDF、源项目和数据包见 [SI交付目录](../../output/Cloudra_SI/README.md)。两版正文与SI按现有顺序列出作者，不标注共同作者身份。

2026年11月1日：两版主稿已同步强化核心对应关系、基准能力定义及局部语义实验的作用，保留实验事实和原有限定；中文旧分数、F4相关解释与共用图件同步最终英文定稿。两版已同步现有Overleaf项目并重新编译，英文23页、中文19页，均无编译错误；每版37个源文件经下载逐字节核对与本地一致。最新在线编译PDF、项目包与同步记录见交付目录。
