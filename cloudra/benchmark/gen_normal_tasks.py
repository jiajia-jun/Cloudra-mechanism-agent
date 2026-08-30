"""Generate normal-tier benchmark task JSONs from ideapool/reaction_candidates/normal.md.

Reads the curated normal-tier markdown and emits one TaskSpec JSON per task into
ideapool/tasks/normal/N<id>.json for the finalized 30-task list (TASK_IDS; the
pool keeps 48 entries but only the finalized list is generated — 见 normal.md
"定稿圈定"段). The markdown is the human-curated source of truth for SMILES /
charges / barriers; this generator is deterministic and re-runnable.

Unlike the easy generator (single-step R->TS->P), normal tasks are multi-step
networks: gold graphs carry intermediate nodes and one edge per elementary step.
`bond_changes` are never hand-typed — they are DERIVED by diffing the per-step
atom-mapped SMILES registered in `cloudra/benchmark/normal_registry/` (per-family
modules), so the indexing convention cannot drift from the query's mapped
reactants. The registry is validated fail-loud: atom-map conservation and formal
charge conservation per step, unmapped registry SMILES must equal the pool
SMILES (reactants and final products), every step must show at least one bond
order change.

task_id 口径：normal 的族字母与 easy 有交叉（X 族两档都有），task_id 一律加
"N" 前缀（池内 A1 -> NA1），family 字段保留池内族字母。system.single_step
对 normal 题一律 false（含 O2/O4/O5/X 族等单基元步条目——该字段标记的是
"非 easy 单步原型档"，见 normal.md 使用注意）。

Usage:  python -m cloudra.benchmark.gen_normal_tasks [--out DIR] [--only A1 ...] [--check]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from cloudra.benchmark.gen_easy_tasks import (
    ELEMENTS_RE,
    HEAVY_RE,
    ROW_RE,
    SMILES_RE,
    _parse_barrier,
)
from cloudra.benchmark.normal_registry import REGISTRY
from cloudra.benchmark.schema import (
    AccuracyRubric,
    BarrierReference,
    BondChangeSet,
    GoldMechanismGraph,
    GoldSpec,
    MechanismEdge,
    MechanismNode,
    NodeRole,
    PromptSpec,
    ReferenceComputation,
    RubricSpec,
    SystemSpec,
    TaskSpec,
    Tier,
    VerificationStatus,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = REPO_ROOT / "ideapool" / "reaction_candidates" / "normal.md"
DEFAULT_OUT = REPO_ROOT / "ideapool" / "tasks" / "normal"

# normal.md "定稿圈定"段的权威名单（30 条）；池子其余 18 条留档不生成。
TASK_IDS = (
    "A1 A2 A4 A5 A7 I1 I3 Y2 Y3 O2 O3 O4 O5 X1 X2 "
    "X3 X4 R1 R2 R3 U1 U5 U6 U7 Q2 Q3 H1 H2 H3 H5"
).split()

# 口径核对登记（normal.md 文末）：锚点非 central_complex 标准口径的题，数值保留、
# verification 一律降 unverified 待核，不按新口径编造数值（easy 同款机制）。
_BARRIER_FRAME_UNVERIFIED = {
    "A7",   # 锚点来自类似底物（肉桂醛而非丙烯醛）
    "Y2",   # 数值经学位论文对比表二手转录，一级出处待补
    "O4", "O5",  # 微溶剂化团簇口径（非纯气相络合物基准）
    "U1",   # 锚点为中性水助通道，题设为 OH- 催化通道
    "Q2",   # 双分子，文献垒相对分离反应物渐近线（同 easy D1 情形）
    "X1",   # 锚点来自二级氯代物 iPrCl，按最近体系转录
    "X3",   # 溶液相自由能垒，参考态未明
    "H3",   # 学位论文二手转录，参考点为路径中间体络合物
    "H5",   # 文献垒相对分离反应物渐近线
}


# ---------------------------------------------------------------------------
# 原子映射 SMILES 解析与键变化推导（RDKit；chem extra，生成器为开发期工具）
# ---------------------------------------------------------------------------


def _rdkit():
    try:
        from rdkit import Chem
    except ImportError as e:  # pragma: no cover - 环境缺 chem extra
        raise SystemExit("gen_normal_tasks 需要 RDKit（pip install -e '.[chem]'）") from e
    return Chem


def _parse_mapped(smiles: str):
    """解析原子映射 SMILES，保留显式 [H:n]（默认 sanitize 会吸收/移除显式 H）。"""
    Chem = _rdkit()
    mols = []
    for frag in smiles.split("."):
        mol = Chem.MolFromSmiles(frag, sanitize=False)
        if mol is None:
            raise ValueError(f"RDKit 无法解析映射 SMILES 片段: {frag!r}")
        mol.UpdatePropertyCache(strict=False)
        Chem.SanitizeMol(
            mol,
            Chem.SanitizeFlags.SANITIZE_ALL
            ^ Chem.SanitizeFlags.SANITIZE_KEKULIZE
            ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES,
        )
        mols.append(mol)
    return mols


def _strip_maps(smiles: str) -> str:
    """字符串级去映射号（[CH2:3] -> [CH2]），再走标准解析拿 canonical 形式。"""
    return re.sub(r":\d+\]", "]", smiles)


def _unmap_canonical(smiles: str) -> list[str]:
    """映射 SMILES -> 无映射规范化 SMILES 片段列表（与池内无映射 SMILES 对比用）。"""
    Chem = _rdkit()
    out = []
    for frag in _strip_maps(smiles).split("."):
        mol = Chem.MolFromSmiles(frag)  # 标准解析：吸收显式 H、规范化芳香性
        if mol is None:
            raise ValueError(f"去映射后无法解析: {frag!r}（原 {smiles!r}）")
        out.append(Chem.MolToSmiles(mol))
    return out


def _map_numbers(smiles: str) -> list[int]:
    return [
        atom.GetAtomMapNum()
        for mol in _parse_mapped(smiles)
        for atom in mol.GetAtoms()
    ]


def _formal_charge(smiles: str) -> int:
    return sum(atom.GetFormalCharge() for mol in _parse_mapped(smiles) for atom in mol.GetAtoms())


def _bond_orders(smiles: str) -> dict[tuple[int, int], float]:
    orders: dict[tuple[int, int], float] = {}
    for mol in _parse_mapped(smiles):
        for bond in mol.GetBonds():
            i = bond.GetBeginAtom().GetAtomMapNum()
            j = bond.GetEndAtom().GetAtomMapNum()
            if i == 0 or j == 0:
                raise ValueError(f"映射 SMILES 存在无映射号原子: {smiles!r}")
            key = (min(i, j), max(i, j))
            orders[key] = orders.get(key, 0.0) + bond.GetBondTypeAsDouble()
    return orders


def _derive_bond_changes(step_in: str, step_out: str) -> tuple[list[list[int]], list[list[int]]]:
    """break = 键级下降（含断至 0），form = 键级上升（含自 0 新建），与 easy 口径一致。"""
    before = _bond_orders(step_in)
    after = _bond_orders(step_out)
    breaks, forms = [], []
    for i, j in sorted(set(before) | set(after)):
        delta = after.get((i, j), 0.0) - before.get((i, j), 0.0)
        if delta < -1e-6:
            breaks.append([i, j])
        elif delta > 1e-6:
            forms.append([i, j])
    return breaks, forms


# ---------------------------------------------------------------------------
# registry 校验（fail-loud；--check / --only 供分族登记时自检）
# ---------------------------------------------------------------------------


def _canonical_pool(smiles_list: list[str]) -> list[str]:
    """池内无映射 SMILES 的规范化形式（池字符串不一定是 RDKit  canonical 序）。"""
    Chem = _rdkit()
    out = []
    for smi in smiles_list:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            raise ValueError(f"池内 SMILES 无法解析: {smi!r}")
        out.append(Chem.MolToSmiles(mol))
    return out


def _validate_task(pid: str, entry: dict, pool_reactants: list[str], pool_products: list[str]) -> list[str]:
    errors: list[str] = []
    for key in ("name_en", "conditions_en", "mapped_reactants", "steps"):
        if key not in entry:
            errors.append(f"缺登记键 {key!r}")
    if errors:
        return errors
    try:
        pool_r = sorted(_canonical_pool(pool_reactants))
        pool_p = sorted(_canonical_pool(pool_products))
        # 映射反应物的无映射形式必须等于池内反应物（顺序无关）
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
        for k, step in enumerate(steps, 1):
            out = step["out"]
            if sorted(_map_numbers(prev)) != sorted(_map_numbers(out)):
                errors.append(f"第 {k} 步原子不守恒（映射号集合变化）")
            if _formal_charge(prev) != _formal_charge(out):
                errors.append(f"第 {k} 步形式电荷不守恒")
            breaks, forms = _derive_bond_changes(prev, out)
            if not breaks and not forms and not step.get("conformational"):
                errors.append(f"第 {k} 步无键级变化且未声明 conformational")
            if not step.get("type"):
                errors.append(f"第 {k} 步缺 step_type 英译")
            prev = out
        if sorted(_unmap_canonical(steps[-1]["out"])) != pool_p:
            errors.append(
                f"末步产物去映射后与池内产物不一致: "
                f"{sorted(_unmap_canonical(steps[-1]['out']))} != {pool_p}"
            )
    except ValueError as e:
        errors.append(str(e))
    return errors


# ---------------------------------------------------------------------------
# 图构建与 TaskSpec 组装
# ---------------------------------------------------------------------------


def _build_graph(pid: str, reactants: list[str], products: list[str], entry: dict) -> GoldMechanismGraph:
    tid = f"N{pid}"
    nodes = [MechanismNode(id=f"{tid}_R", role=NodeRole.REACTANT, smiles=reactants, label="reactant")]
    edges: list[MechanismEdge] = []
    prev_mapped, prev_id = entry["mapped_reactants"], nodes[0].id
    n = len(entry["steps"])
    for k, step in enumerate(entry["steps"], 1):
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
    return GoldMechanismGraph(nodes=nodes, edges=edges)


def _query(pid: str, name: str, reactants: list[str], products: list[str], q: int, mult: int, conditions: str, mapped: str) -> str:
    rs = ".".join(reactants)
    ps = ".".join(products)
    # 与 easy 同一套交付协议措辞；normal 增量：机理可能是多步网络——要求中间体
    # 节点与逐步边，但不点名步数（不泄题）。
    return (
        f"Determine the mechanism of the following reaction: {name}. "
        f"Reactant SMILES: {rs}; product SMILES: {ps}; total charge {q}, multiplicity {mult}; "
        f"conditions: {conditions}. "
        f"Atom-mapped reactant SMILES: {mapped}. "
        "The 1-based map numbers in it are the indexing convention for `bond_changes` "
        "(keep using the plain SMILES above for graph nodes and evidence annotations). "
        "The reaction may proceed through a multi-step network: represent each intermediate "
        "you identify as a node and each elementary step as an edge; competing pathways you "
        "investigate deserve their own edges. "
        "You must maintain `mechanism_graph.json` in the sandbox root recording the mechanism graph: "
        "nodes (reactant/intermediate/product/transition_state, with SMILES) and elementary-step edges "
        "(with `via` pointing to the TS node id). Start the graph at the reactant complex "
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
        "In your final summary you must report the computed barrier in kcal/mol for the "
        "rate-determining step, relative to the reactant complex (the pre-reaction complex, "
        "e.g. the ion-dipole complex of a bimolecular reaction; for a unimolecular process "
        "this is simply the reactant minimum). "
        "Run the computations with ORCA or Gaussian: the scorer parses only these two "
        "programs' log formats, so output from any other program cannot count as evidence. "
        "Allowed computational methods are limited to MACE-OMol25 and xTB; "
        "calls beyond the whitelist are intercepted."
    )


def parse_normal_md(src: Path, only: set[str] | None = None) -> list[TaskSpec]:
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
        barrier, btype, verification, doi = _parse_barrier(cells[5])
        if pid in _BARRIER_FRAME_UNVERIFIED:
            verification = VerificationStatus.UNVERIFIED
        barrier_ref = BarrierReference.CENTRAL if barrier is not None else None
        elem_m = ELEMENTS_RE.match(cells[6])
        elements = elem_m.group(1).split(",") if elem_m else []
        heavy_m = HEAVY_RE.search(cells[6])
        heavy = int(heavy_m.group(1)) if heavy_m else None

        entry = REGISTRY.get(pid)
        if entry is None:
            all_errors[pid] = ["未在 normal_registry 登记"]
            continue
        errors = _validate_task(pid, entry, reactants, products)
        if errors:
            all_errors[pid] = errors
            continue

        graph = _build_graph(pid, reactants, products, entry)
        name = entry["name_en"]
        conditions = entry["conditions_en"]
        tasks.append(
            TaskSpec(
                task_id=f"N{pid}",
                tier=Tier.NORMAL,
                family=pid[0],
                name=name,
                prompt=PromptSpec(query=_query(pid, name, reactants, products, q, mult, conditions, entry["mapped_reactants"])),
                system=SystemSpec(
                    reactants=reactants,
                    products=products,
                    charge=q,
                    multiplicity=mult,
                    conditions=conditions,
                    elements=elements,
                    max_heavy_atoms=heavy,
                    closed_shell=True,
                    single_step=False,
                ),
                gold=GoldSpec(
                    mechanism_graph=graph,
                    reference_computation=ReferenceComputation(
                        level_of_theory=(
                            "literature anchor (see reference_doi)"
                            if doi
                            else "literature anchor (curated in normal.md; no DOI on record)"
                        ),
                        barrier_kcal_mol=barrier,
                        barrier_type=btype,
                        barrier_reference=barrier_ref,
                        verification=verification,
                        reference_doi=doi,
                        computed_by_us=False,
                    ),
                ),
                # normal 档 accuracy 层高斯容差 σ=2.0（plan 2026-08-29 定稿）；
                # 无锚点题只评自洽性（enabled=false）
                rubric=RubricSpec(accuracy=AccuracyRubric(enabled=barrier is not None, sigma_kcal_mol=2.0)),
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

    tasks = parse_normal_md(args.src, only=set(args.only) if args.only else None)
    if args.check:
        for t in tasks:
            n_edges = len(t.gold.mechanism_graph.edges)
            print(f"OK {t.task_id}: {len(t.gold.mechanism_graph.nodes)} nodes, {n_edges} steps")
        print(f"check passed: {len(tasks)} tasks")
        return
    assert len(tasks) == 30, f"expected 30 tasks, got {len(tasks)}"
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
