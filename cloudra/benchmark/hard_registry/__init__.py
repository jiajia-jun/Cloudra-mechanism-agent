"""hard 档任务登记表（按族分文件，避免并行登记冲突）。

每个子模块导出 `TASKS: dict[str, dict]`，键为池内 id（如 "A1"），值为：

- `name_en`: 题名英译（漏登记在校验阶段报错）。
- `conditions_en`: 条件列英译。
- `anchor`: 锚点路由——"selectivity"（能垒格数值为竞争 TS 能垒差 ΔΔ，
  入 gold.selectivity）/ "barrier"（绝对能垒，入 reference_computation，
  accuracy 照常评分）/ None（无数值锚点，accuracy disable）。selectivity
  必须同时给 `minor_channel_en`（副通道英文一句话）。
- `mapped_reactants`: query 展示的原子映射反应物 SMILES（1-based 映射号；
  **保留立体标记**（@/@@、/、\\）；参与键变化的 H 以显式 [H:n] 给出，其余
  H 保持隐式；去映射后必须等于池内反应物 SMILES——规范化对比是立体敏感
  的，立体标错会在这里被 fail-loud 拦住）。
- `steps`: 主写出线的基元步列表，每步 {"out": <该步产物的映射 SMILES>,
  "type": <step_type 英译>}；末步 out 去映射后必须等于池内产物。
  纯构象步（无键级变化）另加 "conformational": True。
- `competing`（可选）: 竞争立体化学副通道列表，每步 {"out": <副通道产物/
  中间体的映射 SMILES>, "type": ...}；可选键 "from_step": k（默认 0 =
  从反应物络合物出发；k≥1 = 从主线第 k 步的输出节点出发，用于立体决定步
  在多步网络中段的情形，如 I1）与 "is_product": bool（默认 True；False 时
  副通道终点为中间体节点，如 I1 的副面 aldolate）。

粒度规则：gold 边 = hard.md 机理概要中每个造成重原子骨架键变化的事件；
质子转移凡涉及显式写入 SMILES 的催化剂/水（[OH-]/[OH3+] 等）一律单独成边，
分子内质子转移并入相邻边。bond_changes 由生成器从相邻两步的映射 SMILES
差集自动推导，禁止手填。
"""

from cloudra.benchmark.hard_registry import ab, de, fgk, hi, jl

REGISTRY: dict[str, dict] = {}
for module in (ab, de, fgk, hi, jl):
    overlap = set(REGISTRY) & set(module.TASKS)
    if overlap:
        raise SystemExit(f"hard_registry 登记重复: {overlap}")
    REGISTRY.update(module.TASKS)
