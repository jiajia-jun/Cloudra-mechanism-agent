# HANDOFF — HG2 选择性配对纠正（方案 A，gold 回填第 2 步）

状态：完成。pytest tests/test_benchmark.py = 136 passed；tests/test_benchmark_impossible.py = 22 passed。
其它 hard 题 JSON 重生成后逐字节不变（仅 HG2.json 变化）。

## 改动（3 个文件）
1. cloudra/benchmark/hard_registry/fgk.py — G2 段：
   - steps[0]（E1，→syn 产物）：channel 'boat_ts'、favored=False、node_label 'minor product'、barrier 29.67；
     step_type 改为 boat TS -> syn (minor channel)。
   - competing[0]（EM1，→anti 产物）：channel 'chair_ts'、favored=True、node_label 'major product'、barrier 26.39；
     step_type 改为 chair TS -> anti (major channel)。
   - selectivity：favored_channel='chair_ts'（新增条目顶层键）；minor_channel_en='boat TS -> syn-2,3-dimethylpent-4-enal'。
   - 顶部 docstring + G2 注释相应纠正（chair→anti 优势、boat→syn 次）。
2. cloudra/benchmark/gen_hard_tasks.py — 向后兼容扩展：
   - 新增 _step_favored(step, main)：条目 'favored' 显式优先，否则缺省（主线 True / competing False，无 channel → None）。
   - 主线/副通道节点 label 允许条目 'node_label' 覆盖（缺省与原字面量一致）。
   - anchor='selectivity'：favored_channel = entry.get('favored_channel') or 主线 channel。
   - 缺省路径逐字节保持历史行为。
3. ideapool/reaction_candidates/hard.md — G2 行 ΔΔG‡ 锚点 '≈ 2–3 kcal/mol' → '≈ 3.28 kcal/mol'（生成器 _parse_barrier 取括号前首数）。

## HG2.json 关键字段（重生成后）
- HG2_E1 : channel=boat_ts  favored=False  barrier=29.67
- HG2_EM1: channel=chair_ts favored=True   barrier=26.39
- selectivity: spread=3.28, favored_channel='chair_ts', minor='boat TS -> syn-2,3-dimethylpent-4-enal'
- nodes: HG2_P label='minor product'; HG2_M1 label='major product'
- 不变量（test_hard_selectivity_qualitative_contract）：favored 边 channel == favored_channel → 成立。

## 复现
uv run python -m cloudra.benchmark.gen_hard_tasks
uv run pytest tests/test_benchmark.py -q

## 收尾（Coordinator 指示，已完成）
hard.md G2 行「gold 机理概要」中文散文已改写，与纠正后一致：
before: 椅式 TS 强烈占优（双甲基假赤道），(E,E) → syn 主产物。竞争：船式 TS → anti（副产物 SMILES `C=C[C@H](C)[C@@H](C)C=O`）
after : (E,E)-巴豆基丙烯基醚 Claisen：[3,3]-σ 重排；chair TS（两甲基 pseudo-equatorial）→ anti(1,2-trans) 为优势通道（较低垒），boat TS → syn(1,2-cis) 为次通道；ΔΔE‡≈3.28 kcal/mol 有利 anti。
只改散文列（cells[4]）+ ΔΔ 数值列（cells[5]，2→3.28）；未动反应/产物 SMILES 单元格、未动生成器。
该列生成器不解析，HG2.json 哈希未变（cd0d40db…）。pytest tests/test_benchmark.py = 136 passed。
