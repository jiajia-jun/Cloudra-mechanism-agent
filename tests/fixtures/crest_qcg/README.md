# CREST 官方 QCG 示例输入

从 [CREST Docs QCG Examples](https://crest-lab.github.io/crest-docs/page/examples/qcg) 逐字抽出的输入坐标（`crest-lab/crest-docs` `page/examples/qcg-example_*.md` 里的 `{% capture %}` / 代码围栏），不含官网贴出的运行日志。

| 目录 | 文件 | 官网题 | 原子/格式 |
|---|---|---|---|
| `example_1/` | `bacillaene.xyz`, `water.xyz` | 杆菌素 + 100 水，grow（`--gfnff --alpb water --nofix`） | 90 + 3 |
| `example_2/` | `benzoic_acid.xyz`, `water.xyz` | 苯甲酸 + 3 水，ensemble | 15 + 3 |
| `example_3/` | `solute.xyz`, `solvent.xyz`, `.xcontrol` | Fe 配合物 + 乙腈，约束 ensemble | 23 + 6 |
| `example_4/` | `pentanol.xyz`, `benzene.coord` | 1-戊醇 + 苯，`--gsolv` | 18 + TM `$coord` |
| `example_5/` | `struc.xyz`, `directed.list` | 肽定向溶剂化 | 34 + 位点清单 |

来源：<https://github.com/crest-lab/crest-docs>（与 CREST 同属 Grimme 组文档仓）。坐标保持官网原文，含行首空格。

集成测试用 `example_2`（小、grow 口径可对原子数：15 + 3×3 = 24）。例 1 的 100 水 grow 官网日志约 35 分钟，不进默认 pytest。
