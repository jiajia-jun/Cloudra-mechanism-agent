# Cloudra 双语稿引文核查（2026-10-31）

两版 references.bib 已统一为 43 条，Introduction 和 Discussion 已接入实际引文。Methods 已由主编辑接入，两版全部39条均已沿 main.tex 的实际 input 链关联到正文，39条实引、0条遗漏、0条无用key、0条nocite；实际链核查见 actual_input_chain_check.json。精确锚点保存在 methods_citation_anchors.json。未更改科学参数、评分和分析结论；未通过 nocite 增加引用量。

已补入 NumPy、cclib、NetworkX 与图5所用 scikit-learn 的4条引用，见 [依赖引用补核](依赖引用补核.md)。43条均有正文或图注实际落点，无未使用条目、缺失key和 nocite。

## 新增的实际方法来源

| 正文对象 | key | 原始来源 / 官方核实入口 |
|---|---|---|
| GFN2-xTB | gfn2xtb2019 | https://doi.org/10.1021/acs.jctc.8b01176 ；作者官方软件引用表 https://github.com/grimme-lab/xtb |
| PM7 | pm72013 | https://doi.org/10.1007/s00894-012-1667-x ；打印卷期为2013，2012为在线发表年份 |
| B3LYP：杂化交换 / LYP相关 / 三参数组合 | becke1993, lyp1988, stephens1994 | https://doi.org/10.1063/1.464913 ；https://doi.org/10.1103/PhysRevB.37.785 ；https://doi.org/10.1021/j100096a001 |
| D3 与 BJ 阻尼 | d32010, d3bj2011 | https://doi.org/10.1063/1.3382344 ；https://doi.org/10.1002/jcc.21759 |
| def2-SVP | def22005 | https://pubs.rsc.org/en/Content/ArticleLanding/2005/CP/B508541A |
| ORCA 6 | orca2025 | https://doi.org/10.1002/wcms.70019 ；官方引用要求 https://www.faccts.de/docs/orca/6.1/manual/contents/preface/howtocite.html |
| Gaussian 16 | gaussian16 | https://gaussian.com/citation/ ；Gold NY3、HL1、NR1、HI1 运行档案明确 Gaussian 16，未臆定小版本。官方页面本次返回502；条目使用标准软件题名、作者、发行方和发行年。 |
| 开源MOPAC | mopac2026 | https://doi.org/10.21105/joss.08025 ；作者官方仓库 https://github.com/openmopac/mopac 明确要求引用2026年JOSS文献；Gold IA9归档记录MOPAC23.2.5 PM7实际计算。 |
| MMFF94 | mmff941996 | https://onlinelibrary.wiley.com/doi/abs/10.1002/%28SICI%291096-987X%28199604%2917%3A5/6%3C490%3A%3AAID-JCC1%3E3.0.CO%3B2-P ；使用完整SICI DOI，未使用无效短DOI。 |
| ETKDGv3 | etkdg2020 | https://doi.org/10.1021/acs.jcim.0c00025 ；RDKit官方Cookbook确认为ETKDGv3来源。保留2015年ETKDG原文ref12。 |
| Improved-tangent NEB | neb2000 | https://doi.org/10.1063/1.1323224 |
| ASE / MDMin | ase2017 | https://doi.org/10.1088/1361-648X/aa680e |
| Adam | adam2015 | https://arxiv.org/abs/1412.6980 |
| BGE-M3 | bgem32024 | https://aclanthology.org/2024.findings-acl.137/ ；使用ACL2024正式发表题名、作者和页码2318–2335。 |
| DeepSeek V4 | deepseekv42026 | https://fe-static.deepseek.com/chat/transparency/deepseek-V4-model-card-EN.pdf ；保持运行记录的API模型名，不从当前别名反推历史服务快照。 |

## 已在 Discussion 实引的语言模型研究

- valmeekam2023planning：外部规划、状态关系与检验反馈；https://arxiv.org/abs/2305.15771 ，NeurIPS 2023。
- huang2024selfcorrect：外部反馈与推理修正；https://arxiv.org/abs/2310.01798 ，ICLR 2024。
- turpin2023unfaithful：生成解释对既有选择的合理化及解释忠实性；https://arxiv.org/abs/2305.04388 ，NeurIPS 2023。作为相关研究背景，未将这篇选择题实验写成Cloudra内部机制的直接证明。
- ref18（CRITIC）保留并接入外部工具反馈讨论；https://arxiv.org/abs/2305.11738 。

## 原有条目与落点修正

- Kabsch ref07、ORCA手册 ref11、Cloudra源代码 ref14 原先主要由nocite进入文献表；改为实际方法句尾引用。
- ref11补ORCA6.1官方手册年份2025及访问日期；ref13补在线文档访问日期和2026检索年；ref14补源码提交日期2026-10-26。
- ARCHE ref05作者表补全为原文13人；Estructural、ARCHE、Gráfico的arXiv题名和作者列表均已对照原始页面。
- IDPP ref08、IRC ref09/ref10、RDKit ref13、PAL ref15、activation patching ref16、Talk like a Graph ref17、CRITIC ref18有各自实际正文落点，保留。
- 引言第一段物理路径验证原理处补Fukui与Maeda的IRC文献，没有新增比较或限制段落。

## 元数据依据

publisher_deposited_metadata.json 保存13项DOI查询的出版社存入Crossref的数据。MMFF94的猜测短DOI返回404，随后改用Wiley原文提供的完整SICI DOI；其余12项成功取得题名、作者、卷期与页码。D3和ORCA文章号、def2终页由出版社原文或官方引用页补齐。在线与卷期年份不混用。
