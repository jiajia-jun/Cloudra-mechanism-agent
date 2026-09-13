# gold_compute — 逐边能垒（edge-level barrier）补齐方案

> 用户口径（2026-09-13）：gold 机理图的**每一条有效边**都要有参考能垒数值；
> “有效边/比什么数据”按每个反应具体情况由我们判断（有什么数据比什么数据）；
> 数据来源：**文献优先，缺口用计算补**。hard 选择性不做数值 ΔΔ 评分，只看定性判断。

## 目标产物
每个 task 的 `gold.mechanism_graph.edges[*].barrier_kcal_mol` 都有值（含来源/类型/口径/核实），
不再只有单一 RDS。当前 `MechanismEdge.barrier_kcal_mol` 在 schema 里是“交付侧字段”，
需扩展为 gold 也承载参考值（+ 可选 type/doi/verification 字段）。

## 数据流
1. 逐边文献调研 → `gold_compute/edge_barriers/<task_id>.json`（每条边一条记录）。
2. 文献缺口 → 计算补（xTB 探索 + B3LYP/def2-SVP 校核；必要时 MACE）。
3. 合并进 registry 的 step 定义（`normal_registry/*`、`hard_registry/*`）+ easy 生成器；
   gen_* 写回 `ideapool/tasks/**/*.json` 的 gold 边。
4. 扩展 accuracy/barrier_evidence 支持逐边比对（“有什么数据比什么数据”）。

## 记录格式（edge_barriers/<task_id>.json）
{ "task_id": "...", "edges": [
  {"edge_id":"NA2_E1","barrier_kcal_mol":X|null,"barrier_type":"...","frame":"...",
   "source":"...","doi":"...","verification":"...","method":"...","note":"..."} ] }

## 进度
- [ ] 21 份逐边文献调研（normal 10 / hard 10 / easy F1）派发
- [ ] 汇总逐边表 → edge_barriers/
- [ ] 计算补缺口
- [ ] 合并进 registry/generator + 扩展 schema
- [ ] 重新生成 + 测试
