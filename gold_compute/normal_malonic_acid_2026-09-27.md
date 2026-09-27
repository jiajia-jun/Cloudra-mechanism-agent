# Normal 补题试算：丙二酸热脱羧

状态：2026-09-27 自算脱羧步验证完成；作为 NB1 加入默认 normal 题库。

## 已批准范围

- 净反应：`O=C(O)CC(=O)O >> CC(=O)O.O=C=O`，中性单重态，气相热反应。
- 候选两步：丙二酸脱羧形成乙酸烯醇式 `C=C(O)O` 与 CO₂，再互变成乙酸。
- 脱羧步沿用气相 ORCA B3LYP-D3(BJ)/def2-SVP（def2/J、RIJCOSX）口径；参考量为相对该步反应物极小值的纯电子 ΔE‡，不含 ZPE/热修正。
- 脱羧步须验证极小值、收敛一阶鞍点及振动方向、双向 IRC 路径与端点身份；不预先假定任何文献能垒能在本方法重现。
- 后续互变按既定 PT 规则保留图边，不强求参考垒，不为此增加大规模扫描。
- 实际计算若不支持候选拆步，先报告，不强迫匹配预设机理。CO₂ 与烯醇的弱结合端点如有软模，明确证据范围，不把分离组分偷换成复合物能量。
- 试算通过后才分配新题号、写入题源/registry 并重跑生成器，恢复 normal 为 10 题；不复用已迁入 IMP 的 NR4 身份。

## 选入依据与边界

单个底物 C₃H₄O₄ 共 11 原子、7 重原子；中性单分子，避免金属对离子配位。保留脱羧与中间体识别的多步判别价值，作为 normal 偏简单的候选。原始实验与计算研究提供路径依据，不代替本项目自算 gold。

- Staikova 等，Overtone-induced decarboxylation: a potential sink for atmospheric diacids：https://pubmed.ncbi.nlm.nih.gov/16833384/ ，六元环脱羧 TS 的计算依据；本题不研究光激发动力学。
- Mardyukov 等，1,1-Ethenediol: The Long Elusive Enol of Acetic Acid：https://doi.org/10.1002/anie.201915646 ，丙二酸热解获得烯醇中间体的光谱证据。

## 结果与溯源

已核对三组 SMILES 的总组成为 C₃H₄O₄、净电荷 0、总原子数 11，元素与电荷守恒。远端报告与原始作业给出：

| 结构/路径 | 作业 | 结果 |
|---|---:|---|
| 丙二酸反应物极小值 | 515 | E = −417.158657746617 Ha，零虚频 |
| 协同脱羧 TS | 527 | E = −417.114137914676 Ha，恰一虚频 −408.61 cm⁻¹；振动耦合 C2–C4 断裂及 O3–H8 向 O6 转移 |
| 双向 IRC | 529 | 一侧回到反应物，另一侧到烯醇 + CO₂ 产物侧；产物方向在 MaxIter 40 停止，后续端点无约束优化确认身份 |
| IRC 反应物侧优化/频率 | 531 | E = −417.158662031331 Ha，零虚频 |
| IRC 产物侧优化/频率 | 532 | E = −417.131021836728 Ha，零虚频；1,1-乙烯二醇 + CO₂ |

第一步参考垒以独立反应物作业 515 为零点：纯电子 ΔE‡ = **27.94 kcal/mol**。作业 531 的能量差别为构象/优化微差，不替换已声明零点。第一步反应能约 +17.34 kcal/mol。方法为 ORCA 5.0.2 气相 B3LYP-D3(BJ)/def2-SVP、def2/J、RIJCOSX；不含 ZPE 或热修正。第二步互变按既定 PT 规则保留图边，参考垒为 null。IRC 的产物方向未达到 IRC 自身收敛标记，证据由末端几何与后续无约束优化及频率共同支持，不能写成 IRC 完全收敛。

远端原始报告：`/public/home/yyywaa/cloudra_workspace/normal_malonic_20260927/REPORT.md`。

## 远端启动记录

- Cloudra 项目：`prj_ebb0e688c4784e93`（normal-v4-gold-20260925）。
- Agent：`as_3bc965fbc0bc4e34`，名称 `gold-normal-malonic-decarboxylation`。
- Run：`run_1117cb11b4ee4bf9`，启动响应 `accepted=true`、`state=running`。
- 工作目录：`/public/home/yyywaa/cloudra_workspace/normal_malonic_20260927`。
- 此状态表示计算 agent 已启动，不表示 QM 已完成；等待其报告和原始证据。
