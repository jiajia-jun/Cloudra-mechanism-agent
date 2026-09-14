# 逐边能垒重构 spec（用户 2026 指令）

## 目标
能垒只在「边」上有意义。彻底移除整题 barrier 锚点机制，改为 gold 机理图逐边承载参考答案能垒，accuracy 层逐边评分（加权平均）。用户明确：已不存在「计算依据（provenance）」概念——不再保留 level_of_theory / DOI / verification / barrier_type / frame。题级只保留必要字段：参考答案、query、方法白名单、反应信息。

## 1. schema (cloudra/benchmark/schema.py)
- MechanismEdge：
  - barrier_kcal_mol: Optional[float] —— gold 侧=参考答案能垒；交付侧=agent 声明值（语义与现在一致，只是 gold 侧现在真的会被填）。
  - 新增 weight: float = 1.0（gold 侧有效：越难算准的边权重越小；交付侧忽略）。
  - 保留 channel / favored。不要新增 barrier_type/frame/doi/verification 字段。
- GoldSpec：
  - 删除 reference_computation 字段与 ReferenceComputation 模型。
  - mechanism_graph 保留（边承载逐边参考答案）。
  - selectivity 保留（仅 qualitative：favored_channel；spread 数值不评分）。
  - 若 impossible 需要 properties 锚点：新增 reference_properties: dict[str, float|str] = {}（属"参考答案"）。
  - BarrierType / BarrierReference 若删除后无引用则一并移除（先全仓 grep 确认）。
- 白名单（MethodPolicy）不改。
- rubric.accuracy.enabled 语义：由"整题锚点非空"改为"gold 机理图存在任一带参考值的边"。

## 2. 生成器 (gen_easy/normal/hard/impossible_tasks.py + *_registry/)
- easy：单步题参考答案 = 该唯一边的 barrier_kcal_mol（源自题源 md 单元格）。
- normal/hard：从 registry step dict / 题源 md 为每条边提供 barrier_kcal_mol 与可选 weight（registry step 新增可选 'barrier'/'weight' 键）。
- hard_registry 原 anchor=="barrier" 路由（写 reference_computation）删除，改逐边。
- impossible：properties 锚点迁移到 GoldSpec.reference_properties；不再产出 reference_computation。
- 不产出任何 DOI/level_of_theory/verification 字段。

## 3. 评分 (accuracy.py / barrier_evidence.py / runner.py)
- barrier_evidence：保留逐边推导（edge_id -> derived barrier）。rds() 只保留作报告，不再作为唯一比较对象。
- score_accuracy 改为逐边：
  - 对每条「gold 带参考值」的边：在交付 evidence 中按 edge_id 找对应步；要求 (a) 交付图声明了该边 barrier_kcal_mol、(b) 声明值与日志推导值一致（容差 rubric.sigma_kcal_mol）。缺声明或不一致 -> 该边 0 分（fail-loud）。
  - 该边高斯分：gaussian_barrier_score(derived, gold_edge_value, _effective_sigma(...))。
  - 汇总 = 加权平均（权重 = 该 gold 边 weight）。
  - 若不存在任何带参考值的 gold 边 -> accuracy not scored（final_score=1.0），沿用旧 null 行为。
  - 删除 verification 门禁。
- runner.py:322 传 task.gold（或 gold.mechanism_graph）替代 task.gold.reference_computation。
- hard 定性选择性评分不变。

## 4. 测试 (tests/test_benchmark.py 等)
- 更新/删除所有引用 reference_computation、barrier anchors、verification 门禁的测试。
- 新增逐边评分单测：加权平均正确、缺边记 0、声明/日志不一致 fail-loud、无参考边 -> not scored。
- test_{easy,normal,hard,impossible}_tasks_regenerate_identically 守卫必须保持绿：所有 gold 改动经生成器重跑，禁止手改 JSON。

## 5. 数据回填
- 已有 26 条逐边文献值（见 gold_compute/edge_barriers/*.json 与 gold_compute/edge_gap_summary.md）接入 gold 边；easy 单步题用其整题值。
- weight 初值建议：可核实/同底物 = 1.0；analogue/部分核实/质子转移等难算准边 = 0.5（可逐边覆盖）。
- 关键边仍缺值（normal NA2；hard HA1/HA6/HE3/HG2）-> 该边无参考值，暂不评分。

## 6. 守卫与验收
- 重跑 gen_easy/gen_normal/gen_hard/gen_impossible -> ideapool/tasks/**/*.json。
- uv run pytest -q tests/test_benchmark.py 全绿；uv run ruff check cloudra 通过。
- 不 git commit/push（等用户指令）。

## 7. 交付报告
- 改动文件清单；测试与 ruff 结果；每题逐边参考值覆盖表（哪些边有值/权重/哪些缺）。
