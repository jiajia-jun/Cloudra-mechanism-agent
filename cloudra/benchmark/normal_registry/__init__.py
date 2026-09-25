"""normal 档任务登记表（按族分文件，避免并行登记冲突）。

每个子模块导出 `TASKS: dict[str, dict]`，键为池内 id（如 "A1"），值为：

- `name_en`: 题名英译（漏登记在校验阶段报错）。
- `conditions_en`: 条件列英译。
- `mapped_reactants`: query 展示的原子映射反应物 SMILES（1-based 映射号；
  参与键变化的 H 以显式 [H:n] 给出，其余 H 保持隐式；去映射后必须等于池内
  反应物 SMILES）。
- `steps`: 主写出线的基元步列表，每步 {"out": <该步产物的映射 SMILES>,
  "type": <step_type 英译>}；末步 out 去映射后必须等于池内产物。
  纯构象步（无键级变化）另加 "conformational": True。可选键 "barrier"
  （该步参考答案能垒 kcal/mol，逐边承载；缺省 None = 无参考值、不评分）与
  "weight"（该边 accuracy 加权平均的权重，缺省 1.0；越难算准的边越小）。

粒度规则：gold 边 = normal.md 机理概要中每个造成重原子骨架键变化的事件；
质子转移凡涉及显式写入 SMILES 的催化剂/水（[OH-]/[OH3+]/CNC/CN- 等）一律
单独成边，分子内质子转移并入相邻边。2026-09-25 PT 边规则补充：分子内
互变异构（如 Q5 烯醇→醛）可单独成边保留在图里，但该边不挂参考垒（构建期
诚实缺测，gold 战役不花算力）。bond_changes 由生成器从相邻两步的映射
SMILES 差集自动推导，禁止手填。
"""

from cloudra.benchmark.normal_registry import ai, qh, ru, x, yo

REGISTRY: dict[str, dict] = {}
for module in (ai, yo, x, ru, qh):
    overlap = set(REGISTRY) & set(module.TASKS)
    if overlap:
        raise SystemExit(f"normal_registry 登记重复: {overlap}")
    REGISTRY.update(module.TASKS)
