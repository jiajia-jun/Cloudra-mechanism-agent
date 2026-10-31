# 完整出版分项更新

本报告保留同一报告ID、标题、章节布局、样式和全部200个最终总分。统一采用 `source_publication_scores_per_run.csv` 的 `score`、`graph_publication`、`selfc_all_publication` 与 `accuracy_publication`。所有分项均来自实际运行记录；离线组织机理图与证据引用属于本次评分前整理方法，没有补算、改变科学结论或修改评分标准。

正式组件现在为200行×3项，所有组间比较纳入完整50题。旧39/47题组件子集、normal+hard的15/18对及据此得出的负Accuracy贡献已撤回。主对照Guided−Backbone全50题分别贡献Graph +0.009513、SC +0.117875、Accuracy +0.058916；Guided−Record的Accuracy贡献为正的+0.005099。normal+hard的Guided−Record改为20题，SC贡献62.6%，Accuracy贡献31.7%。最终总分及逐题胜负不变。

`selfc_gold`是另一个辅助报告变体，并非正式三分项。其既有比较记录单列于`provenance/d3_selfc_pairs.csv`；不将该子集当作正式组件分母，也没有为缺少该变体的记录推造数值。QM投入的共同15题来自旧投入快照覆盖范围，与正式分项完整性无关。

复算顺序（不运行实验或评分器）：

1. `python paired/analyze_paired.py`
2. `python paired/derive_findings.py`
3. `python paired/extract_baseline_comparison.py`
4. `python chemistry/reproduce.py`
5. `python provenance/analyze_provenance_effort.py`
6. `python compose_report.py`

唯一报告数据更新入口为`compose_report.py`；旧的第二轮静态覆写脚本已经移除，避免重新覆盖完整分项。原始表仍保存在`source_final_scores_per_run.csv`供过程来源核对；正式分析使用publication表。

已核对600个值、全部200个总分、50题配对分解、零组件排除、200行Pareto矩阵及稳定报告身份。页面结构与CSS未变，原split HTML和同名离线完整HTML均重建成功。本轮浏览器工具不可用，未重复声称进行了浏览器目视检查。
