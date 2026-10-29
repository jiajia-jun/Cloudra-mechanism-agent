# Cloudra 双语 LaTeX 主稿

更新日期：2026年10月30日。

两版正式排版源文件分别位于 [Cloudra_EN](Cloudra_EN/) 和 [Cloudra_ZH](Cloudra_ZH/)。各项目独立完整，在 Overleaf 中以 `main.tex` 为主文件，使用 **XeLaTeX、TeX Live 2026** 编译。

- `main.tex`：全文入口、版式和文末参考文献。
- `sections/`：引言、方法、结果与讨论的正文，后续直接编辑这些 TeX 文件。
- `references.bib`：参考文献条目，正文通过引用键关联来源。
- `figures/`：独立图件 PDF，图号、图注和正文引用由 LaTeX 管理。

方法 2.6 已包含 CloudraBench 设计与 50 题分布图。结果 3.1 先介绍 48 组重复实验，再介绍 200 个消融沙箱，保留讨论小节和写作空间，随后进入机制分析。

`build_sections.py` 记录首次从 Markdown 迁移到 LaTeX 的转换过程；后续不运行它覆盖正式 TeX。旧 Word 文件保留为迁移前的审阅快照。

可直接导入的项目包及 PDF 预览见 [Overleaf 交付目录](../../output/Cloudra_Overleaf/README.md)。

在线项目：[英文](https://www.overleaf.com/project/6ae36f82f45648027f73ed76) · [中文](https://www.overleaf.com/project/6ae37adfaf331ac2323b4c3f)。

图4、12、15、17已于2026年10月30日更新为分层卡片与矢量框体图，文字边界及论文中的实际显示已检查。源图见 [框体图目录](../figures/box_diagrams_20261030/README.md)。
