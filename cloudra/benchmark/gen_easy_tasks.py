"""Generate benchmark task JSONs from ideapool/reaction_candidates/easy.md.

Reads the curated easy-tier markdown and emits one TaskSpec JSON per task into
ideapool/tasks/easy/<task_id>.json. The markdown is the human-curated source
of truth; this generator is deterministic and re-runnable.

Usage:  python -m cloudra.benchmark.gen_easy_tasks [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from cloudra.benchmark.schema import (
    BarrierType,
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
DEFAULT_SRC = REPO_ROOT / "ideapool" / "reaction_candidates" / "easy.md"
DEFAULT_OUT = REPO_ROOT / "ideapool" / "tasks" / "easy"

ROW_RE = re.compile(r"^\|\s*([A-Z]\d+)\s*\|")
# SMILES cell like `C=CC=C.C=C>>C1CC=CCC1`，0/1  (backticks optional).
# charge may use the Unicode minus '−'; SMILES may carry a trailing note
# like `O=NO>>O=NO`（cis/trans），0/1 before the q/mult separator.
SMILES_RE = re.compile(r"`([^`]+)`(?:（[^）]*）)?\s*[，,]\s*([+−\-]?\d+)\s*/\s*(\d+)")
# barrier anchor: number possibly with range/±, and a verification tag
BARRIER_NUM_RE = re.compile(r"([ΔE]?[a-zA-Z‡]?)?\s*[≈~]?\s*(\d+(?:\.\d+)?)")
VERIFY_RE = re.compile(r"\[(已核实存在|已核实|部分核实|未核实)\]")
ELEMENTS_RE = re.compile(r"^([A-Z][a-z]?(?:,[A-Z][a-z]?)*)")
HEAVY_RE = re.compile(r"(\d+)\s*重原子")

_VERIFY_MAP = {
    "已核实": VerificationStatus.VERIFIED,
    "已核实存在": VerificationStatus.VERIFIED,
    "部分核实": VerificationStatus.PARTIAL,
    "未核实": VerificationStatus.UNVERIFIED,
}

_BARRIER_TYPE_MAP = {
    "ΔH‡": BarrierType.DH,
    "ΔE‡": BarrierType.DE,
    "ΔG‡": BarrierType.DG,
    "Ea": BarrierType.EA,
}


def _split_cells(line: str) -> list[str]:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def _parse_smiles_cell(cell: str) -> tuple[list[str], list[str], int, int] | None:
    m = SMILES_RE.search(cell)
    if not m:
        return None
    rxn, q_raw, mult = m.group(1), m.group(2), int(m.group(3))
    q = int(q_raw.replace("−", "-"))
    if ">>" in rxn:
        reactants, products = rxn.split(">>", 1)
    elif ">" in rxn:
        reactants, products = rxn.split(">", 1)
    else:
        reactants, products = rxn, ""
    r = [s for s in reactants.split(".") if s]
    p = [s for s in products.split(".") if s]
    return r, p, q, mult


def _parse_barrier(cell: str) -> tuple[float | None, BarrierType, VerificationStatus, str]:
    """Return (barrier_kcal, barrier_type, verification, doi)."""
    vtag = VERIFY_RE.search(cell)
    verification = _VERIFY_MAP.get(vtag.group(1), VerificationStatus.UNVERIFIED) if vtag else VerificationStatus.UNVERIFIED
    doi_m = re.search(r"DOI\s+([0-9.]+/[^\s，。）)]+)", cell)
    doi = doi_m.group(1).rstrip("）)") if doi_m else ""

    btype = BarrierType.EA
    for k, v in _BARRIER_TYPE_MAP.items():
        if k in cell:
            btype = v
            break

    # take the first numeric anchor (lower bound if a range like 14.9–16.6);
    # skip DOI-like numeric runs by only looking before any "DOI" token.
    barrier = None
    head = cell.split("DOI")[0]
    nums_head = re.findall(r"(\d+(?:\.\d+)?)", head)
    if nums_head:
        barrier = float(nums_head[0])
    return barrier, btype, verification, doi


def _parse_comfort(cell: str) -> tuple[list[str], int | None]:
    elem_m = ELEMENTS_RE.match(cell)
    elements = elem_m.group(1).split(",") if elem_m else []
    heavy_m = HEAVY_RE.search(cell)
    heavy = int(heavy_m.group(1)) if heavy_m else None
    return elements, heavy


def _build_graph(task_id: str, reactants: list[str], products: list[str], mechanism_summary: str) -> GoldMechanismGraph:
    """Build a minimal single-step mechanism graph (reactant -> TS -> product).

    Easy-tier tasks are all single-step; degenerate processes (product ==
    reactant) still get distinct R/P node ids but identical SMILES.
    """
    r_node = MechanismNode(id=f"{task_id}_R", role=NodeRole.REACTANT, smiles=reactants, label="reactant")
    p_node = MechanismNode(
        id=f"{task_id}_P",
        role=NodeRole.PRODUCT,
        smiles=products if products else reactants,
        label="product",
    )
    ts_node = MechanismNode(
        id=f"{task_id}_TS", role=NodeRole.TRANSITION_STATE, smiles=[], label="TS"
    )
    edge = MechanismEdge(
        id=f"{task_id}_E1",
        **{"from": r_node.id, "to": p_node.id},
        via=ts_node.id,
        step_type=mechanism_summary,
    )
    return GoldMechanismGraph(nodes=[r_node, ts_node, p_node], edges=[edge])


def _query(task_id: str, name: str, reactants: list[str], products: list[str], q: int, mult: int, conditions: str) -> str:
    rs = ".".join(reactants)
    ps = ".".join(products) if products else rs
    return (
        f"请推导以下反应/过程的机理（Easy 档）：{name}。"
        f"反应物 SMILES：{rs}；产物 SMILES：{ps}；总电荷 {q}，多重度 {mult}；条件：{conditions}。"
        "要求：定位过渡态（TS），用 IRC 连通反应物与产物端点，做频率验证（TS 有且仅有一个虚频），"
        "并给出活化能垒（kcal/mol）。"
        "**必须在沙箱根目录维护 `mechanism_graph.json`**，记录机理图的节点（reactant/product/transition_state，"
        "含 SMILES）与基元步边（含 via 指向的 TS 节点 id），评分器将读取该文件取证，缺失或不可解析将严重影响得分。"
        "允许的量化方法仅限 MACE-OMol25 与 xTB；不要尝试更高级别的泛函/基组，超出白名单的调用会被拦截。"
    )


def parse_easy_md(src: Path) -> list[TaskSpec]:
    tasks: list[TaskSpec] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        cells = _split_cells(line)
        # expect: [#, name, smiles_cell, conditions, mechanism, barrier, comfort, reference]
        if len(cells) < 8:
            continue
        task_id, name = cells[0], cells[1]
        smiles_cell, conditions, mechanism, barrier_cell, comfort_cell, _ref_cell = (
            cells[2], cells[3], cells[4], cells[5], cells[6], cells[7],
        )
        parsed = _parse_smiles_cell(smiles_cell)
        if parsed is None:
            continue
        reactants, products, q, mult = parsed
        barrier, btype, verification, doi = _parse_barrier(barrier_cell)
        elements, heavy = _parse_comfort(comfort_cell)

        graph = _build_graph(task_id, reactants, products, mechanism)
        spec = TaskSpec(
            task_id=task_id,
            tier=Tier.EASY,
            family=task_id[0],
            name=name,
            prompt=PromptSpec(query=_query(task_id, name, reactants, products, q, mult, conditions)),
            system=SystemSpec(
                reactants=reactants,
                products=products,
                charge=q,
                multiplicity=mult,
                conditions=conditions,
                elements=elements,
                max_heavy_atoms=heavy,
                closed_shell=True,
                single_step=True,
            ),
            gold=GoldSpec(
                mechanism_graph=graph,
                reference_computation=ReferenceComputation(
                    level_of_theory="literature anchor (see reference_doi)",
                    barrier_kcal_mol=barrier,
                    barrier_type=btype,
                    verification=verification,
                    reference_doi=doi,
                    computed_by_us=False,
                ),
            ),
            rubric=RubricSpec(),
        )
        tasks.append(spec)
    return tasks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    tasks = parse_easy_md(args.src)
    args.out.mkdir(parents=True, exist_ok=True)
    for t in tasks:
        out = args.out / f"{t.task_id}.json"
        out.write_text(
            json.dumps(t.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(f"wrote {len(tasks)} tasks to {args.out}")
    assert len(tasks) == 30, f"expected 30 tasks, got {len(tasks)}"


if __name__ == "__main__":
    main()
