# 新增近邻阅读笔记

本文件是修改论文前的阅读依据，不替换用户已经修改的中文版。所有数据定位、访问限制与任务细分见同目录 `systems.json`。

| 系统 | 本轮核实的相似之处 | 比较时保留的界限 |
|---|---|---|
| [CatGo](https://www.researchgate.net/publication/410982627_CatGo_Bridging_CLI_coding_agents_with_interactive_structure_and_workflow_management_for_computational_chemistry) | 共享可编辑DAG、结构操作、依赖和结果关联；有表面及分子计算报告 | 科学选择由人控制；本轮未完整获取SI数值表。不能将DAG载体本身写成Cloudra独有 |
| [PULSES](https://arxiv.org/abs/2610.32392) | 专家确认研究边界后，领域Agent与科学校验Agent配对检查阶段产物 | 重点是激发态模型构建和动力学；不能把反应轨迹当作TS/IRC证据，也不能泛称前人没有科学护栏 |
| [QAOS / AgenticOS](https://arxiv.org/html/2610.05304v1) | 固定科学设置、保留依赖和校验约束，研究Zundel阳离子质子转移 | 人执行计算，采用规定的一维扫描；不是完整有机反应机理自主探索 |
| [El Agente Potente](https://arxiv.org/html/2609.14840v1) | 分子构象、动力学、频率与表面NEB展示扩大了El Agente家族的覆盖面 | 部分计算依赖Gráfico和MLIP；覆盖面不能代替机理正确性及难度对照 |

原有近邻也需继续保留：ARCHE、Quntur、Estructural、Aitomia、Gráfico、TSAgent及Evolving TS workflows。Gráfico v2的二苯二硫醚研究确有机理讨论与物种优化/热化学；原始记录明确缺少裂解TS，本轮没有增加R标记。

文献矩阵不为Cloudra赋予能力或科学验收标记。若要进一步表述区别，应围绕有机机理任务范围、几何操作的具体深度、物种/步骤的原生证据绑定及同条件计算评测展开；这些属于后续与用户讨论的措辞，未擅自改入正文。
