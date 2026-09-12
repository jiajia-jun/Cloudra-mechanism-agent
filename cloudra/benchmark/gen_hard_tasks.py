"""Generate hard-tier benchmark task JSONs from ideapool/reaction_candidates/hard.md.

Reads the curated hard-tier markdown (stereochemistry tier) and emits one
TaskSpec JSON per task into ideapool/tasks/hard/H<id>.json for the finalized
10-task list (TASK_IDS; the pool keeps 51 entries but only the finalized list
is generated — 见 hard.md "定稿圈定"段)。v3（2026-09-09）将 20 条缩至 10 条并为
hard 开放 DFT（B3LYP-D3(BJ)/def2-SVP）白名单。The markdown is the
human-curated source of truth for SMILES / charges / anchors; this generator
is deterministic and re-runnable.

Hard-tier specifics vs normal (gen_normal_tasks):

- task_id 加 "H" 前缀（池内 A1 -> HA1），family 保留池内族字母。
- 选择性锚点（ΔΔG‡/ΔΔE‡ 竞争非对映 TS 能垒差）走 `gold.selectivity`
  （SelectivityReference），绝不塞进 reference_computation.barrier_kcal_mol；
  绝对能垒锚点（H1 消旋阻垒 ΔG‡）仍走 reference_computation 且 accuracy 层
  照常评分（σ=2.0，同 normal）。选择性锚点题的 accuracy 暂 disable
  （runner 尚不支持 spread 评分），锚点仅作记录。每题的锚点路由由登记表
  `anchor` 键声明显式给出："selectivity" / "barrier" / None。
- gold 机理图带竞争立体化学通道：主写出线照旧为主线边列，登记表
  `competing` 列出副通道（默认从反应物络合物出发到副产物/副中间体节点），
  子图打分据此要求 agent 两条 TS 都交付才算覆盖。立体专一题（副通道被
  禁阻）不带 competing 边——stereo_tier_rule="hard_stereo_costly" 下的节点
  立体匹配本身就是判别器。
- rubric.graph_similarity.stereo_tier_rule 一律 "hard_stereo_costly"
  （runner 据此把 GedConfig.stereo_free 关掉）。
- bond_changes 同 normal：由相邻步映射 SMILES 差集推导，禁止手填；映射
  SMILES 保留立体标记（@/@@、/、\\），去映射规范化对比因此自动强制立体
  化学正确（校验是立体敏感的）。

Usage:  python -m cloudra.benchmark.gen_hard_tasks [--out DIR] [--only A1 ...] [--check]
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from cloudra.benchmark.gen_easy_tasks import (
    ELEMENTS_RE,
    HEAVY_RE,
    ROW_RE,
    SMILES_RE,
    _parse_barrier,
)
from cloudra.benchmark.gen_normal_tasks import (
    _canonical_pool,
    _derive_bond_changes,
    _formal_charge,
    _map_numbers,
    _unmap_canonical,
)
from cloudra.benchmark.hard_registry import REGISTRY
from cloudra.benchmark.query_builder import GRAPH_JSON_EXAMPLE, format_allowed_methods_clause
from cloudra.benchmark.schema import (
    AccuracyRubric,
    BarrierReference,
    BondChangeSet,
    GoldMechanismGraph,
    GoldSpec,
    GraphSimilarityRubric,
    MechanismEdge,
    MechanismNode,
    MethodPolicy,
    NodeRole,
    PromptSpec,
    ReferenceComputation,
    RubricSpec,
    SelectivityReference,
    SystemSpec,
    TaskSpec,
    Tier,
    VerificationStatus,
)
from cloudra.infra.config import get_config

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = REPO_ROOT / "ideapool" / "reaction_candidates" / "hard.md"
DEFAULT_OUT = REPO_ROOT / "ideapool" / "tasks" / "hard"

# hard.md "定稿圈定"段的权威名单（v3 缩减：20 → 10；池子其余条目留档不生成）。
# v3 保留：A1 torqueselection / A6 WH×torqueselection / D2 Fürst–Plattner /
# E2 轴向进攻 / E3 CBS / F1 Henbest / G2 Claisen 椅-船 / H1 联萘消旋 /
# I1 脯氨酸 aldol / L1 肟 Beckmann（全 ≤20 重原子，开放 B3LYP-D3(BJ)/def2-SVP）。
TASK_IDS = (
    "A1 A6 D2 E2 E3 F1 G2 H1 I1 L1"
).split()

# H1 消旋阻垒是绝对能垒锚点（ΔG‡ 23.5，部分核实），挂 reference_computation 且
# accuracy 照常评分（σ=2.0 同 normal）；selectivity 题与无锚点题 accuracy disable。
_BARRIER_SIGMA = 2.0


# ---------------------------------------------------------------------------
# registry 校验（fail-loud；--check / --only 供分族登记时自检）
# ---------------------------------------------------------------------------


def _validate_step_conservation(tag: str, prev: str, step: dict) -> list[str]:
    """单步（主线或副通道）的原子/电荷守恒与键变化检查。"""
    errors: list[str] = []
    out = step["out"]
    if sorted(_map_numbers(prev)) != sorted(_map_numbers(out)):
        errors.append(f"{tag} 原子不守恒（映射号集合变化）")
    if _formal_charge(prev) != _formal_charge(out):
        errors.append(f"{tag} 形式电荷不守恒")
    breaks, forms = _derive_bond_changes(prev, out)
    if not breaks and not forms and not step.get("conformational"):
        errors.append(f"{tag} 无键级变化且未声明 conformational")
    if not step.get("type"):
        errors.append(f"{tag} 缺 step_type 英译")
    return errors


def _validate_task(pid: str, entry: dict, pool_reactants: list[str], pool_products: list[str]) -> list[str]:
    errors: list[str] = []
    for key in ("name_en", "conditions_en", "mapped_reactants", "steps", "anchor"):
        if key not in entry:
            errors.append(f"缺登记键 {key!r}")
    if errors:
        return errors
    if entry["anchor"] not in ("selectivity", "barrier", None):
        errors.append(f"anchor 取值非法: {entry['anchor']!r}")
    if entry["anchor"] == "selectivity" and not entry.get("minor_channel_en"):
        errors.append("selectivity 锚点缺 minor_channel_en")
    try:
        pool_r = sorted(_canonical_pool(pool_reactants))
        pool_p = sorted(_canonical_pool(pool_products))
        # 映射反应物的无映射形式必须等于池内反应物（顺序无关；立体敏感）
        if sorted(_unmap_canonical(entry["mapped_reactants"])) != pool_r:
            errors.append(
                f"mapped_reactants 去映射后与池内反应物不一致: "
                f"{sorted(_unmap_canonical(entry['mapped_reactants']))} != {pool_r}"
            )
        maps = _map_numbers(entry["mapped_reactants"])
        if len(maps) != len(set(maps)):
            errors.append("mapped_reactants 映射号重复")
        prev = entry["mapped_reactants"]
        steps = entry["steps"]
        main_outs: list[str] = []
        for k, step in enumerate(steps, 1):
            errors.extend(_validate_step_conservation(f"第 {k} 步", prev, step))
            prev = step["out"]
            main_outs.append(sorted(_unmap_canonical(step["out"])))
        if main_outs and sorted(_unmap_canonical(steps[-1]["out"])) != pool_p:
            errors.append(
                f"末步产物去映射后与池内产物不一致: "
                f"{sorted(_unmap_canonical(steps[-1]['out']))} != {pool_p}"
            )
        # 副通道：守恒规则相同；副产物/副中间体必须与主线节点立体/连接性可区分
        for k, step in enumerate(entry.get("competing", []), 1):
            origin = entry["mapped_reactants"] if step.get("from_step", 0) == 0 else steps[step["from_step"] - 1]["out"]
            errors.extend(_validate_step_conservation(f"副通道 {k}", origin, step))
            minor = sorted(_unmap_canonical(step["out"]))
            if minor in main_outs or minor == pool_p:
                errors.append(f"副通道 {k} 产物与主线节点不可区分（立体或连接性必须不同）")
    except ValueError as e:
        errors.append(str(e))
    return errors


# ---------------------------------------------------------------------------
# 图构建与 TaskSpec 组装
# ---------------------------------------------------------------------------


def _build_graph(pid: str, reactants: list[str], products: list[str], entry: dict) -> GoldMechanismGraph:
    tid = f"H{pid}"
    nodes = [MechanismNode(id=f"{tid}_R", role=NodeRole.REACTANT, smiles=reactants, label="reactant")]
    edges: list[MechanismEdge] = []
    prev_mapped, prev_id = entry["mapped_reactants"], nodes[0].id
    steps = entry["steps"]
    n = len(steps)
    for k, step in enumerate(steps, 1):
        last = k == n
        node = MechanismNode(
            id=f"{tid}_P" if last else f"{tid}_I{k}",
            role=NodeRole.PRODUCT if last else NodeRole.INTERMEDIATE,
            smiles=products if last else _unmap_canonical(step["out"]),
            label="product" if last else f"intermediate {k}",
        )
        ts = MechanismNode(id=f"{tid}_TS{k}", role=NodeRole.TRANSITION_STATE, smiles=[], label=f"TS{k}")
        breaks, forms = _derive_bond_changes(prev_mapped, step["out"])
        edges.append(
            MechanismEdge(
                id=f"{tid}_E{k}",
                **{"from": prev_id, "to": node.id},
                via=ts.id,
                step_type=step["type"],
                bond_changes=BondChangeSet(**{"break": breaks}, form=forms),
            )
        )
        nodes.extend([ts, node])
        prev_mapped, prev_id = step["out"], node.id
    # 竞争立体化学通道（hard 特有）：副产物节点 role=PRODUCT / 副中间体
    # role=INTERMEDIATE（step 里 is_product 声明，默认 True）
    for k, step in enumerate(entry.get("competing", []), 1):
        from_step = step.get("from_step", 0)
        origin_id = nodes[0].id if from_step == 0 else f"{tid}_I{from_step}"
        origin_mapped = entry["mapped_reactants"] if from_step == 0 else steps[from_step - 1]["out"]
        is_product = step.get("is_product", True)
        minor = MechanismNode(
            id=f"{tid}_M{k}",
            role=NodeRole.PRODUCT if is_product else NodeRole.INTERMEDIATE,
            smiles=_unmap_canonical(step["out"]),
            label=f"minor {'product' if is_product else 'intermediate'} {k}",
        )
        ts = MechanismNode(id=f"{tid}_TSM{k}", role=NodeRole.TRANSITION_STATE, smiles=[], label=f"TS minor {k}")
        breaks, forms = _derive_bond_changes(origin_mapped, step["out"])
        edges.append(
            MechanismEdge(
                id=f"{tid}_EM{k}",
                **{"from": origin_id, "to": minor.id},
                via=ts.id,
                step_type=step["type"],
                bond_changes=BondChangeSet(**{"break": breaks}, form=forms),
            )
        )
        nodes.extend([ts, minor])
    return GoldMechanismGraph(nodes=nodes, edges=edges)


def _query(
    pid: str,
    name: str,
    reactants: list[str],
    products: list[str],
    q: int,
    mult: int,
    conditions: str,
    mapped: str,
    allowed_methods: Sequence[str] | None = None,
) -> str:
    rs = ".".join(reactants)
    ps = ".".join(products)
    # 与 easy/normal 同一套交付协议措辞；hard 增量：立体化学结果是交付本体——
    # 竞争立体化学通道的两条 TS 都要查，报告能垒排序与差值（选择性锚点据此评分）。
    # 不点名具体构型/几何归属（不泄题）。
    methods_clause = format_allowed_methods_clause(allowed_methods)
    methods_part = f" {methods_clause}" if methods_clause else ""
    return (
        f"Determine the mechanism of the following reaction: {name}. "
        f"Reactant SMILES: {rs}; product SMILES: {ps}; total charge {q}, multiplicity {mult}; "
        f"conditions: {conditions}. "
        f"Atom-mapped reactant SMILES: {mapped}. "
        "The 1-based map numbers in it are the indexing convention for `bond_changes` "
        "(keep using the plain SMILES above for graph nodes and evidence annotations). "
        "This task probes stereochemistry: resolving the stereochemical outcome is part of "
        "the deliverable. Investigate the competing stereochemical channels (not only the "
        "major one), and make sure the stereochemistry of every product and intermediate "
        "node is stated in its SMILES. "
        "The reaction may proceed through a multi-step network: represent each intermediate "
        "you identify as a node and each elementary step as an edge; competing pathways you "
        "investigate deserve their own edges. "
        "You must maintain `mechanism_graph.json` in the sandbox root recording the mechanism graph: "
        "nodes (reactant/intermediate/product/transition_state, with SMILES) and elementary-step edges "
        "(with `via` pointing to the TS node id). Start the graph at the reactant complex "
        + GRAPH_JSON_EXAMPLE +
        "(the pre-reaction complex), not at the separated reactants. The scorer checks that "
        "your graph covers the reference mechanism as a subgraph: extra nodes or edges beyond "
        "the reference are never penalized, so record every step you actually investigated. "
        "Every elementary-step edge must carry "
        "`bond_changes`: `break`/`form` lists of [i, j] atom-map index pairs, where [i, j] "
        "belongs to `break` if the bond order between atoms i and j decreases over the step "
        "(including full cleavage) and to `form` if it increases (including newly formed bonds); "
        "a purely conformational or inversion step carries two empty lists. "
        "The scorer reads this file forensically; "
        "a missing or unparseable file severely impacts the score. "
        "Every computational evidence file you produce for a species or step (QM input or log) "
        "must carry a `smiles: <SMILES>` comment line identifying the species, so the scorer "
        "can bind each graph element to concrete evidence. "
        "Declare every barrier you actually compute in kcal/mol on that elementary "
        "step's edge as `barrier_kcal_mol` in mechanism_graph.json (each barrier is "
        "relative to that step's own starting minimum; for a bimolecular reaction "
        "that minimum is the reactant complex (e.g. the ion-dipole complex), and for "
        "a unimolecular process it is simply the reactant minimum). The scorer derives every declared step barrier "
        "from your log files and takes the highest as the rate-determining step; a "
        "barrier that is undeclared, has no bound ORCA/Gaussian log, or disagrees with "
        "those logs is not scorable. A transition-state evidence file must carry "
        "`smiles: <the SMILES of that step's reactant>` so the scorer can attach "
        "the saddle to the step it belongs to. For each competing stereochemical "
        "channel also "
        "state the barrier difference (minor-channel TS minus major-channel TS) in "
        "kcal/mol and which channel it favors (recorded for the report, not scored "
        "numerically). "
        "Run the computations with ORCA or Gaussian: the scorer parses only these two "
        f"programs' log formats, so output from any other program cannot count as evidence.{methods_part}"
    )


def parse_hard_md(src: Path, only: set[str] | None = None) -> list[TaskSpec]:
    tasks: list[TaskSpec] = []
    all_errors: dict[str, list[str]] = {}
    for line in src.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        pid = m.group(1)
        if pid not in TASK_IDS or (only and pid not in only):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 8:
            raise SystemExit(f"{pid}: 行解析失败（列数 {len(cells)}）")
        sm = SMILES_RE.search(cells[2])
        if not sm:
            raise SystemExit(f"{pid}: SMILES 格解析失败")
        rxn, q_raw, mult = sm.group(1), sm.group(2), int(sm.group(3))
        q = int(q_raw.replace("−", "-"))
        reactants_s, products_s = rxn.split(">>", 1)
        reactants = [s for s in reactants_s.split(".") if s]
        products = [s for s in products_s.split(".") if s]
        anchor_val, anchor_type, verification, doi = _parse_barrier(cells[5])
        elem_m = ELEMENTS_RE.match(cells[6])
        elements = elem_m.group(1).split(",") if elem_m else []
        heavy_m = HEAVY_RE.search(cells[6])
        heavy = int(heavy_m.group(1)) if heavy_m else None

        entry = REGISTRY.get(pid)
        if entry is None:
            all_errors[pid] = ["未在 hard_registry 登记"]
            continue
        errors = _validate_task(pid, entry, reactants, products)
        if errors:
            all_errors[pid] = errors
            continue

        # 锚点路由：selectivity -> gold.selectivity（accuracy 暂不评分）；
        # barrier -> reference_computation（accuracy σ=2.0）；None -> 只评自洽。
        anchor = entry["anchor"]
        if anchor in ("selectivity", "barrier") and anchor_val is None:
            all_errors[pid] = [f"登记 anchor={anchor!r} 但能垒格无数值锚点"]
            continue
        if anchor is None and anchor_val is not None:
            all_errors[pid] = [f"能垒格有数值锚点（{anchor_val}）但登记 anchor=None"]
            continue

        selectivity = None
        reference = ReferenceComputation(
            level_of_theory="",
            verification=VerificationStatus.UNVERIFIED,
        )
        accuracy = AccuracyRubric(enabled=False, sigma_kcal_mol=_BARRIER_SIGMA)
        if anchor == "selectivity":
            selectivity = SelectivityReference(
                spread_kcal_mol=anchor_val,
                spread_type=anchor_type,
                minor_channel=entry["minor_channel_en"],
                verification=verification,
                reference_doi=doi,
            )
        elif anchor == "barrier":
            reference = ReferenceComputation(
                level_of_theory=(
                    "literature anchor (see reference_doi)"
                    if doi
                    else "literature anchor (curated in hard.md; no DOI on record)"
                ),
                barrier_kcal_mol=anchor_val,
                barrier_type=anchor_type,
                # 单分子消旋：反应物阱即络合物口径（CENTRAL）
                barrier_reference=BarrierReference.CENTRAL,
                verification=verification,
                reference_doi=doi,
            )
            accuracy = AccuracyRubric(enabled=True, sigma_kcal_mol=_BARRIER_SIGMA)

        graph = _build_graph(pid, reactants, products, entry)
        # v3：hard 开放 DFT（B3LYP-D3(BJ)/def2-SVP，ORCA/Gaussian 引擎）。白名单为组合
        # 条目：基组是许可的一部分，b3lyp 配其他基组（或缺基组）一律 fail-closed 拦截。
        # 内容源是全局 config（method_policy.allowed_methods），不是这里的字面量。
        policy = MethodPolicy(allowed_methods=get_config().method_policy.allowed_methods)
        tasks.append(
            TaskSpec(
                task_id=f"H{pid}",
                tier=Tier.HARD,
                family=pid[0],
                name=entry["name_en"],
                prompt=PromptSpec(
                    query=_query(
                        pid,
                        entry["name_en"],
                        reactants,
                        products,
                        q,
                        mult,
                        entry["conditions_en"],
                        entry["mapped_reactants"],
                        allowed_methods=policy.allowed_methods,
                    )
                ),
                method_policy=policy,
                system=SystemSpec(
                    reactants=reactants,
                    products=products,
                    charge=q,
                    multiplicity=mult,
                    conditions=entry["conditions_en"],
                    elements=elements,
                    max_heavy_atoms=heavy,
                    closed_shell=True,
                    single_step=False,
                ),
                gold=GoldSpec(
                    mechanism_graph=graph,
                    reference_computation=reference,
                    selectivity=selectivity,
                ),
                rubric=RubricSpec(
                    graph_similarity=GraphSimilarityRubric(stereo_tier_rule="hard_stereo_costly"),
                    accuracy=accuracy,
                ),
            )
        )
    if all_errors:
        lines = [f"{pid}: {msg}" for pid, msgs in all_errors.items() for msg in msgs]
        raise SystemExit("registry 校验失败：\n  " + "\n  ".join(lines))
    if only is None:
        missing = [pid for pid in TASK_IDS if pid not in {t.task_id[1:] for t in tasks}]
        if missing:
            raise SystemExit(f"定稿名单中的题目未生成（未登记或未通过校验）: {missing}")
    return tasks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--only", nargs="*", default=None, help="只处理这些池内 id（如 A1 A2），供分族登记自检")
    ap.add_argument("--check", action="store_true", help="只校验与组装，不落盘")
    args = ap.parse_args()

    tasks = parse_hard_md(args.src, only=set(args.only) if args.only else None)
    if args.check:
        for t in tasks:
            n_edges = len(t.gold.mechanism_graph.edges)
            print(f"OK {t.task_id}: {len(t.gold.mechanism_graph.nodes)} nodes, {n_edges} edges")
        print(f"check passed: {len(tasks)} tasks")
        return
    assert len(tasks) == 10, f"expected 10 tasks, got {len(tasks)}"
    args.out.mkdir(parents=True, exist_ok=True)
    for t in tasks:
        out = args.out / f"{t.task_id}.json"
        out.write_text(
            json.dumps(t.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(f"wrote {len(tasks)} tasks to {args.out}")


if __name__ == "__main__":
    main()
