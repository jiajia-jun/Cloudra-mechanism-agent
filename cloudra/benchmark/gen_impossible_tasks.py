"""Generate impossible-tier benchmark task JSONs from ideapool/reaction_candidates/impossible.md.

Reads the curated impossible-tier markdown (strong multireference / refusal tier)
and emits two TaskSpec JSONs per task into ideapool/tasks/impossible/:

- ``I<id>.json``  — the impossible task itself (expected_outcome=correct_refusal；
  gold 图带 accessible=False 节点，进入 rubric.impossible_case)；
- ``S<id>.json``  — the sibling control task（同反应族、单参考可解，
  expected_outcome=mechanism_found——本档信号 = 本题拒答 × 兄弟题正常作答）。

只读 impossible.md "定稿圈定"段的 v3 正选 10 个池 id（TASK_IDS；池子其余留档；
每个池 id 产 I+S 两 JSON，共 20）。
md 是人策事实源（条目化学与判分哲学），机器契约在
``cloudra/benchmark/impossible_registry/``（按族分文件）；生成器做 fail-loud
校验：登记标题与 md 头行全等、逐步原子映射号/形式电荷守恒、末步产物去映射
等于登记产物、每步有键级变化（conformational 态变化与显式 no_mapping 的
笼状键重组除外）、impossible 题至少一个不可达节点、sibling 题全部可达。

task_id 前缀纪律：impossible 正选用 "I" 前缀（池内 A1 -> IA1）。注意池内
I 族编号与此前缀撞形：池内 I2 -> II2、I8 -> II8（两个 I 连写），兄弟题
"S" 前缀同理（SI2/SI8）。判分哲学（impossible.md "定稿圈定"）：不内嵌
"合理拒答" rubric——query 只统一给"不可信时必须明确拒答"的协议句（impossible
与 sibling 同款措辞，不泄题），行为事实由 refusal.py 分类，跨档校准由
runner 的 refusal_stats 承担。

交付句按 registry 的 `deliverable_kind` 生成（见 `_deliverable_clause`）：
mechanism 类维持 RDS 边 `barrier_kcal_mol` 声明（ΔE‡ 口径，可选
`product_property_keys` 把反应能等挂在产物节点 properties）；property /
state_order 类在物种节点的 `properties` 字典上声明（键自带单位，
`state_ordering` 等描述性条目允许字符串值；无边题因此挂节点而非边）。
拒答协议句各类型共用、一字不动。

Usage:  python -m cloudra.benchmark.gen_impossible_tasks [--out DIR] [--only A1 ...] [--check]
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path

from cloudra.benchmark.gen_normal_tasks import (
    _canonical_pool,
    _derive_bond_changes,
    _formal_charge,
    _map_numbers,
    _unmap_canonical,
)
from cloudra.benchmark.impossible_registry import REGISTRY
from cloudra.benchmark.query_builder import (
    GRAPH_JSON_EXAMPLE,
    conditions_modeling_guidance,
    format_allowed_methods_clause,
)
from cloudra.benchmark.schema import (
    AccuracyRubric,
    BondChangeSet,
    ExpectedOutcome,
    GoldMechanismGraph,
    GoldSpec,
    ImpossibleCaseRubric,
    IntegrityRubric,
    MechanismEdge,
    MechanismNode,
    MethodPolicy,
    NodeRole,
    PromptSpec,
    RubricSpec,
    SystemSpec,
    TaskSpec,
    Tier,
    complex_smiles,
)
from cloudra.infra.config import get_config

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = REPO_ROOT / "ideapool" / "reaction_candidates" / "impossible.md"
DEFAULT_OUT = REPO_ROOT / "ideapool" / "tasks" / "impossible"

# impossible.md "定稿圈定"段的正选名单（v3 缩减：20 → 10 个池 id，每个产 I+S 两题；
# 池子其余 60 条留档）。v3 保留 10 对（I/S）：A1 环丁二烯 / A5 反旋开环 / A7 Bergman /
# A8 CH2OO / A9 二氧环丁烷 / C3 苯基氮烯 / D2 FOOF / E2 N2 / F3 三角烯 / G8 Cr2。
# 灰区 6 条（G7/H7/H8/I8/J6/J7）与 ¹O2/苯炔等边缘对全数剔除，避免"拒答正确性"统计污染。
TASK_IDS = (
    "A1 A5 A7 A8 A9 C3 D2 E2 F3 G8"
).split()

_HEADER_RE = re.compile(r"^### ([A-J]\d+)\.\s*(.+)$")


# ---------------------------------------------------------------------------
# md 解析（条目头行 -> 池内 id 与中文标题）
# ---------------------------------------------------------------------------


def _clean_md_name(raw: str) -> str:
    """头行标题 -> 中文题名：去掉尾部【…】定稿标记与最后一个（英文）括注。"""
    name = raw.strip()
    name = re.sub(r"【[^】]*】\s*$", "", name).strip()
    name = re.sub(r"（[^（）]*）\s*$", "", name).strip()
    return name


def parse_md_names(src: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for line in src.read_text(encoding="utf-8").splitlines():
        m = _HEADER_RE.match(line)
        if m:
            names[m.group(1)] = _clean_md_name(m.group(2))
    return names


# ---------------------------------------------------------------------------
# registry 校验（fail-loud；--check / --only 供分族登记时自检）
# ---------------------------------------------------------------------------


def _elements_of(smiles: list[str]) -> tuple[list[str], int]:
    from cloudra.benchmark.gen_normal_tasks import _parse_mapped

    chem_elements: list[str] = []
    heavy = 0
    for frag in smiles:
        for atom in _parse_mapped(frag)[0].GetAtoms():
            heavy += int(atom.GetAtomicNum() > 1)
            sym = atom.GetSymbol()
            if sym != "H" and sym not in chem_elements:
                chem_elements.append(sym)
    return sorted(chem_elements), heavy


def _validate_entry(pid: str, entry: dict, md_names: dict[str, str], *, is_sibling: bool) -> list[str]:
    errors: list[str] = []
    for key in (
        "name_zh", "name_en", "kind", "question_en", "deliverable_en",
        "deliverable_kind", "conditions_en", "charge", "multiplicity",
        "closed_shell", "reactants", "products", "steps",
    ):
        if key not in entry:
            errors.append(f"缺登记键 {key!r}")
    if errors:
        return errors
    if entry["kind"] not in ("reaction", "property"):
        errors.append(f"kind 取值非法: {entry['kind']!r}")

    # 交付物类型决定 query 交付句（mechanism 走边能垒；property/state_order 走
    # 物种节点 properties 字典）——与 kind（图协议形态）的一致性在此强制
    dk = entry["deliverable_kind"]
    if dk not in ("mechanism", "property", "state_order"):
        errors.append(f"deliverable_kind 取值非法: {dk!r}")
    elif dk == "mechanism":
        if entry["kind"] != "reaction":
            errors.append("deliverable_kind=mechanism 要求 kind=reaction")
        ppk = entry.get("product_property_keys", [])
        if not isinstance(ppk, list) or not all(isinstance(k, str) and k for k in ppk):
            errors.append("product_property_keys 必须为非空字符串列表")
        elif ppk and not entry["steps"]:
            errors.append("无步骤题不能声明 product_property_keys（没有产物节点）")
    else:
        if entry["kind"] != "property":
            errors.append(f"deliverable_kind={dk} 要求 kind=property")
        keys = entry.get("property_keys")
        if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k for k in keys):
            errors.append(f"deliverable_kind={dk} 必须登记非空 property_keys")
        else:
            if dk == "state_order" and "state_ordering" not in keys:
                errors.append("state_order 题的 property_keys 必须含 state_ordering")
        node = entry.get("property_node", "reactant")
        if node not in ("reactant", "product"):
            errors.append(f"property_node 取值非法: {node!r}")
        elif node == "product" and not entry["steps"]:
            errors.append("property_node=product 要求至少一个步骤（否则没有目标态节点）")
    gp = entry.get("gold_properties", {})
    if not isinstance(gp, dict) or not all(
        isinstance(k, str) and isinstance(v, (int, float, str)) for k, v in gp.items()
    ):
        errors.append("gold_properties 必须为 dict[str, float|str]")
    elif gp:
        # 锚点键必须是契约键的子集（防 gold 与题面口径漂移）
        declared = set(entry.get("property_keys") or []) | set(
            entry.get("product_property_keys") or []
        )
        extra = set(gp) - declared
        if extra:
            errors.append(f"gold_properties 键未在契约键中登记: {sorted(extra)}")

    # 登记标题与题源对齐（正选与 sibling 同属一个 md 条目）
    if pid in md_names:
        if entry["name_zh"] != md_names[pid]:
            errors.append(f"name_zh 与 md 头行不一致: {entry['name_zh']!r} != {md_names[pid]!r}")
        if not is_sibling and entry.get("sibling", {}).get("name_zh") not in (None, md_names[pid]):
            errors.append("sibling.name_zh 与 md 头行不一致")
    else:
        errors.append(f"md 中无此条目: {pid}")

    steps = entry["steps"]
    no_map = bool(steps) and all(s.get("no_mapping") for s in steps)
    mapped = entry.get("mapped_reactants") or (None if no_map else "")
    if steps and not no_map and not mapped:
        errors.append("有可推导键变化的步骤但缺 mapped_reactants")
    if not steps and entry.get("mapped_reactants"):
        errors.append("无步骤却登记了 mapped_reactants")

    try:
        pool_r = sorted(_canonical_pool(entry["reactants"]))
        pool_p = sorted(_canonical_pool(entry["products"]))
        if not steps and pool_r != pool_p:
            errors.append("单节点题 products 必须等于 reactants")
        if mapped:
            if sorted(_unmap_canonical(mapped)) != pool_r:
                errors.append(f"mapped_reactants 去映射后与登记反应物不一致: {sorted(_unmap_canonical(mapped))} != {pool_r}")
            maps = _map_numbers(mapped)
            if len(maps) != len(set(maps)):
                errors.append("mapped_reactants 映射号重复")
            prev = mapped
            for k, step in enumerate(steps, 1):
                stag = f"第 {k} 步"
                if step.get("no_mapping"):
                    if step.get("conformational"):
                        errors.append(f"{stag} no_mapping 与 conformational 互斥")
                    if _derive_bond_changes(prev, step["out"])[0] or _derive_bond_changes(prev, step["out"])[1]:
                        errors.append(f"{stag} 声明 no_mapping 但映射差集非空（应去掉声明）")
                else:
                    if sorted(_map_numbers(prev)) != sorted(_map_numbers(step["out"])):
                        errors.append(f"{stag} 原子不守恒（映射号集合变化）")
                    if _formal_charge(prev) != _formal_charge(step["out"]):
                        errors.append(f"{stag} 形式电荷不守恒")
                    breaks, forms = _derive_bond_changes(prev, step["out"])
                    if not breaks and not forms and not step.get("conformational"):
                        errors.append(f"{stag} 无键级变化且未声明 conformational")
                if not step.get("type"):
                    errors.append(f"{stag} 缺 step_type 英译")
                prev = step["out"]
            if steps and sorted(_unmap_canonical(steps[-1]["out"])) != pool_p:
                errors.append(
                    f"末步产物去映射后与登记产物不一致: "
                    f"{sorted(_unmap_canonical(steps[-1]['out']))} != {pool_p}"
                )
    except ValueError as e:
        errors.append(str(e))

    # 可达性纪律：sibling 全真；impossible 至少一假
    flags = [entry.get("reactant_accessible", True)]
    flags += [s.get("ts_accessible", True) for s in steps if s.get("with_ts")]
    flags += [s.get("node_accessible", True) for s in steps]
    if is_sibling:
        if entry.get("reactant_accessible") is False or any(f is False for f in flags):
            errors.append("sibling 题不得携带不可达节点")
    elif all(f is not False for f in flags):
        errors.append("impossible 题至少需要一个 accessible=False 节点")
    if not is_sibling:
        if entry.get("wrongly_solve_penalty") not in ("high", "medium"):
            errors.append("wrongly_solve_penalty 必须为 high/medium")
        if entry.get("evidence_strength") not in ("ironclad", "gray_zone"):
            errors.append("evidence_strength 必须为 ironclad/gray_zone")
    return errors


# ---------------------------------------------------------------------------
# 图构建与 TaskSpec 组装
# ---------------------------------------------------------------------------


def _build_graph(tid: str, entry: dict) -> GoldMechanismGraph:
    property_kind = entry["kind"] == "property"
    r_label = "reference state" if property_kind else "reactant"
    nodes = [
        MechanismNode(
            id=f"{tid}_R",
            role=NodeRole.REACTANT,
            smiles=complex_smiles(entry["reactants"]),
            accessible=entry.get("reactant_accessible", True),
            label=r_label,
        )
    ]
    edges: list[MechanismEdge] = []
    steps = entry["steps"]
    mapped = entry.get("mapped_reactants")
    prev_mapped, prev_id = mapped, nodes[0].id
    n = len(steps)
    for k, step in enumerate(steps, 1):
        last = k == n
        node = MechanismNode(
            id=f"{tid}_P" if last else f"{tid}_I{k}",
            role=NodeRole.PRODUCT if last else NodeRole.INTERMEDIATE,
            smiles=complex_smiles(entry["products"]) if last else _unmap_canonical(step["out"]),
            accessible=step.get("node_accessible", True),
            label=("target state" if property_kind else "product") if last
            else (f"state {k}" if property_kind else f"intermediate {k}"),
        )
        via = None
        if step.get("with_ts"):
            ts = MechanismNode(
                id=f"{tid}_TS{k}",
                role=NodeRole.TRANSITION_STATE,
                smiles=[],
                accessible=step.get("ts_accessible", True),
                label=f"TS{k}",
            )
            via = ts.id
            nodes.append(ts)
        if step.get("no_mapping") or not prev_mapped:
            breaks, forms = [], []
        else:
            breaks, forms = _derive_bond_changes(prev_mapped, step["out"])
        edges.append(
            MechanismEdge(
                id=f"{tid}_E{k}",
                **{"from": prev_id, "to": node.id},
                via=via,
                step_type=step["type"],
                bond_changes=BondChangeSet(**{"break": breaks}, form=forms),
            )
        )
        nodes.append(node)
        prev_mapped, prev_id = step["out"], node.id
    return GoldMechanismGraph(nodes=nodes, edges=edges)


def _deliverable_clause(entry: dict) -> str:
    """按交付物类型生成结构化交付契约句（拒答协议句不在此——各类型共用、不动）。"""
    dk = entry["deliverable_kind"]
    if dk == "mechanism":
        clause = (
            f"Declare {entry['deliverable_en']} on the rate-determining step's edge as "
            "`barrier_kcal_mol` in mechanism_graph.json. Barriers are electronic energy "
            "differences (ΔE‡) in kcal/mol, without ZPE or thermal corrections, each "
            "relative to that step's own starting minimum. "
        )
        extra = entry.get("product_property_keys") or []
        if extra:
            keys = ", ".join(f"`{k}`" for k in extra)
            clause += (
                f"Additionally declare {keys} in a `properties` object on the product node. "
            )
        return clause
    node_desc = (
        "the reactant species"
        if entry.get("property_node", "reactant") == "reactant"
        else "the target-state (product)"
    )
    keys = ", ".join(f"`{k}`" for k in entry["property_keys"])
    clause = (
        f"Declare {entry['deliverable_en']} as a structured `properties` object on "
        f"{node_desc} node in mechanism_graph.json, using these unit-carrying keys: "
        f"{keys}. String values are allowed for descriptive entries. "
    )
    if dk == "state_order":
        # 示例必须用占位物种名：写真实态序（如 "triplet below singlet"）会直接
        # 泄露答案——IC3/IF3 的答案就是三态在下
        clause += (
            "`state_ordering` states which state lies lower (e.g. \"<species A> "
            "below <species B>\"). "
        )
    return clause


def _query(entry: dict, allowed_methods: Sequence[str] | None = None) -> str:
    rs = ".".join(entry["reactants"])
    ps = ".".join(entry["products"])
    q, mult = entry["charge"], entry["multiplicity"]
    if entry["kind"] == "reaction":
        system_line = f"Reactant SMILES: {rs}; product SMILES: {ps}"
    else:
        system_line = f"Species SMILES: {rs}"
        if sorted(entry["products"]) != sorted(entry["reactants"]):
            system_line += f"; target SMILES: {ps}"
    system_line += (
        f"; total charge {q}, multiplicity {mult}; conditions: {entry['conditions_en']}. "
        f"{conditions_modeling_guidance(entry['conditions_en'])}"
    )

    mapped = entry.get("mapped_reactants")
    steps = entry["steps"]
    show_map = bool(mapped) and not all(s.get("no_mapping") for s in steps)
    if entry["kind"] == "reaction":
        graph_spec = (
            "You must maintain `mechanism_graph.json` in the sandbox root recording the "
            "mechanism graph: nodes (reactant/intermediate/product/transition_state, with "
            "SMILES) and elementary-step edges (with `via` pointing to the TS node id). "
            "Start the graph at the reactant complex (the pre-reaction complex), not at "
            "the separated reactants. "
            + GRAPH_JSON_EXAMPLE +
            "The scorer checks that your graph covers the "
            "reference mechanism as a subgraph: extra nodes or edges beyond the reference "
            "are never penalized, so record every step you actually investigated."
        )
    else:
        graph_spec = (
            "Model the process you investigate as a graph and maintain "
            "`mechanism_graph.json` in the sandbox root: nodes for every species or "
            "electronic state you characterize (with SMILES) and edges for the state "
            "changes or transformations between them (with `via` pointing to the TS node "
            "id when a transition state was located). "
            + GRAPH_JSON_EXAMPLE +
            "Extra nodes or edges beyond the "
            "reference are never penalized, so record every state you actually "
            "characterized."
        )
    bond_spec = (
        "Every elementary-step edge must carry `bond_changes`: `break`/`form` lists of "
        "[i, j] atom-map index pairs, where [i, j] belongs to `break` if the bond order "
        "between atoms i and j decreases over the step (including full cleavage) and to "
        "`form` if it increases (including newly formed bonds); a purely conformational "
        "or state-change step carries two empty lists. "
        if show_map
        else ""
    )
    mapped_line = (
        f"Atom-mapped reactant SMILES: {mapped}. The 1-based map numbers in it are the "
        "indexing convention for `bond_changes` (keep using the plain SMILES above for "
        "graph nodes and evidence annotations). "
        if show_map
        else ""
    )
    methods_clause = format_allowed_methods_clause(allowed_methods)
    methods_part = f" {methods_clause}" if methods_clause else ""
    return (
        f"{entry['question_en']} {system_line} "
        f"{mapped_line}"
        f"{graph_spec} {bond_spec}"
        "Every computational evidence file you produce for a species or step (QM input "
        "or log) must carry a `smiles: <SMILES>` comment line identifying the species, "
        "so the scorer can bind each graph element to concrete evidence. "
        "The scorer reads this file forensically; a missing or unparseable file "
        "severely impacts the score. "
        f"{_deliverable_clause(entry)}"
        "If you conclude that the requested quantity cannot be computed to a trustworthy "
        "accuracy with the allowed methods, deliver mechanism_graph.json containing "
        '{"refusal": {"refused": true, "reason": "<the electronic-structure reason>"}} '
        "instead of a mechanism graph. The scorer reads that structured declaration, "
        "not prose; do not declare a number you cannot stand behind. "
        "Run the computations with ORCA or Gaussian: the scorer parses only these two "
        "programs' log formats, so output from any other program cannot count as "
        f"evidence.{methods_part}"
    )


def _assemble(pid: str, entry: dict, prefix: str) -> TaskSpec:
    tid = f"{prefix}{pid}"
    impossible = prefix == "I"
    elements, heavy = _elements_of(entry["reactants"])
    graph = _build_graph(tid, entry)
    rubric = (
        RubricSpec(
            expected_outcome=ExpectedOutcome.CORRECT_REFUSAL,
            # 拒答是合法交付：不要求图/证据文件，零交付不触发 no_evidence 倒扣
            #（composite 与拒答 outcome 正交，本档主指标是跨档拒答校准矩阵）。
            integrity=IntegrityRubric(require_graph_json=False, require_evidence_files=False),
            accuracy=AccuracyRubric(enabled=False),
            impossible_case=ImpossibleCaseRubric(
                gold_inaccessible_nodes=[n.id for n in graph.nodes if not n.accessible],
                wrongly_solve_penalty=entry["wrongly_solve_penalty"],
                evidence_strength=entry["evidence_strength"],
            ),
        )
        if impossible
        # sibling：有性质锚点（gold_properties，回填后）才启用 accuracy 层
        else RubricSpec(accuracy=AccuracyRubric(enabled=bool(entry.get("gold_properties"))))
    )
    policy = MethodPolicy(
        allowed_methods=get_config().method_policy.allowed_methods_impossible
    )
    return TaskSpec(
        task_id=tid,
        tier=Tier.IMPOSSIBLE,
        family=pid[0],
        name=entry["name_en"],
        pair_id=f"{'S' if impossible else 'I'}{pid}",
        prompt=PromptSpec(query=_query(entry, allowed_methods=policy.allowed_methods)),
        method_policy=policy,
        system=SystemSpec(
            reactants=entry["reactants"],
            products=entry["products"],
            charge=entry["charge"],
            multiplicity=entry["multiplicity"],
            conditions=entry["conditions_en"],
            elements=elements,
            max_heavy_atoms=heavy,
            closed_shell=entry["closed_shell"],
            single_step=len(entry["steps"]) <= 1,
        ),
        gold=GoldSpec(
            mechanism_graph=graph,
            # 性质类参考答案：registry 的 gold_properties（缺值待文献回填，留空不编造）
            reference_properties=entry.get("gold_properties", {}),
        ),
        rubric=rubric,
    )


def parse_impossible_md(src: Path, only: set[str] | None = None) -> list[TaskSpec]:
    md_names = parse_md_names(src)
    tasks: list[TaskSpec] = []
    all_errors: dict[str, list[str]] = {}
    for pid in TASK_IDS:
        if only and pid not in only:
            continue
        entry = REGISTRY.get(pid)
        if entry is None:
            all_errors[pid] = ["未在 impossible_registry 登记"]
            continue
        errors = _validate_entry(pid, entry, md_names, is_sibling=False)
        if "sibling" not in entry:
            errors.append("缺兄弟题登记（sibling 键）")
        else:
            errors.extend(_validate_entry(pid, entry["sibling"], md_names, is_sibling=True))
        if errors:
            all_errors[pid] = errors
            continue
        tasks.append(_assemble(pid, entry, "I"))
        tasks.append(_assemble(pid, entry["sibling"], "S"))
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
    ap.add_argument("--only", nargs="*", default=None, help="只处理这些池内 id（如 A1 G7），供分族登记自检")
    ap.add_argument("--check", action="store_true", help="只校验与组装，不落盘")
    args = ap.parse_args()

    tasks = parse_impossible_md(args.src, only=set(args.only) if args.only else None)
    if args.check:
        for t in tasks:
            inacc = t.rubric.impossible_case.gold_inaccessible_nodes if t.rubric.impossible_case else []
            n_edges = len(t.gold.mechanism_graph.edges)
            print(
                f"OK {t.task_id}: {len(t.gold.mechanism_graph.nodes)} nodes, {n_edges} edges, "
                f"outcome={t.rubric.expected_outcome.value}, inaccessible={len(inacc)}"
            )
        print(f"check passed: {len(tasks)} tasks (10 impossible + 10 siblings expected)")
        return
    assert len(tasks) == 20, f"expected 20 tasks, got {len(tasks)}"
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
