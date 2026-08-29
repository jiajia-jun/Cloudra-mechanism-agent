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

# 条件列中译英（按原字符串映射；新增条件必须在此登记，否则生成直接报错）。
# M 组表第 4 列是过程类型而非条件，Easy 档统一定义为气相可算，故 M 题
# conditions 一律 "gas phase"，过程类型并入 step_type 英译。
_CONDITIONS_EN = {
    "气相": "gas phase",
    "气相 487–648 °C 动力学": "gas phase, 487–648 °C kinetics",
    "气相/液相室温慢": "gas/liquid phase, slow at room temperature",
    "气相/烃溶剂加热": "gas phase or hydrocarbon solvent, heated",
    "气相 ~250 °C": "gas phase, ~250 °C",
    "气相/溶液室温即快": "gas phase or solution, fast at room temperature",
    "气相 ~200 °C": "gas phase, ~200 °C",
    "气相 403–448 K": "gas phase, 403–448 K",
    "气相 390–434 K": "gas phase, 390–434 K",
    "气相 ~350 °C": "gas phase, ~350 °C",
    "气相/溶液": "gas phase or solution",
    "气相/水溶液": "gas phase or aqueous solution",
    "气相微溶剂化": "gas phase, microsolvated",
    "气相/星际": "gas phase / interstellar",
    "气相高温": "gas phase, high temperature",
}

# gold 机理概要（step_type）英译，按 task_id 映射；新增题目必须登记。
_STEP_TYPE_EN = {
    "D1": "concerted [4+2] cycloaddition, single step via symmetric TS",
    "D3": "concerted [4+2], bispericyclic TS; one molecule as diene, one as dienophile",
    "D4": "concerted [4+2], endo/exo selectivity, aldehyde dienophile",
    "P1": "[3,3]-sigmatropic shift, chair TS, degenerate rearrangement",
    "P2": "[1,5]-sigmatropic H shift, suprafacially allowed, unimolecular",
    "P3": "[3,3]-sigmatropic shift, chair TS, Claisen (O-containing complement to all-carbon Cope P1) -> pent-4-enal",
    "L1": "4pi electrocyclic ring opening, conrotatory, single step",
    "L2": "6pi electrocyclic ring closure, disrotatory, single step",
    "X1": "concerted asynchronous C-C/C-O cleavage, CO2 extrusion",
    "C1": "backside attack, single step, exothermic",
    "C2": "backside attack, single step (C-end attack of ambident nucleophile)",
    "C3": "proton-abstraction-induced inversion followed by second inversion, Cs-symmetric double-inversion TS, net retention",
    "E1": "anti-periplanar concerted elimination, single step (competes with SN2)",
    "F1": "hydride transfer, single step via asynchronous TS",
    "F2": "anion nucleophilic addition to carbonyl, single step (Burgi-Dunitz trajectory ~107 deg)",
    "F3": "extra water as proton shuttle, six-center cyclic TS, single step",
    "T1": "water as proton shuttle, six-center cyclic TS, single step",
    "T3": "intramolecular 1,2-H shift; anomalous IRC - separate C-H cleavage and N-H formation transition regions with an all-real-frequency quasi-state between",
    "G1": "four-center cyclic TS, concerted C-B and C-H formation with B-H cleavage, syn addition; nearly barrierless in gas phase, TST failure (kinetic anomaly)",
    "G2": "concerted [sigma2s+sigma2s+pi2s] double H transfer, syn stereospecific, N2 release",
    "G3": "concerted [sigma2s+pi2s+pi2s], allylic H shift + C-C formation + pi shift",
    "M1": "atropisomerism: ortho-methyl hindered rotation, Ra<->Sa via near-planar TS",
    "M3": "N inversion: double-well inversion via planar D3h TS, tunneling splitting",
    "M6": "conformational rotation: C-C torsion, threefold-symmetric TS",
    "M8": "conformational inversion: chair-chair interconversion via half-chair TS",
    "M10": "methyl rotation: threefold methyl torsion, focal-point benchmark",
    "M12": "proton cluster transfer: shared proton between two waters; O-O distance decides single/double well",
    "M14": "conformational rotation: C(sp2)-C(sp2) single-bond torsion, trans more stable",
    "M15": "conformational isomerization: N-O torsion, trans ground state, cis ~0.5-0.6 kcal/mol higher",
    "M16": "dehydrogenation: concerted H2 elimination to CO2 (competes with dehydration to CO+H2O)",
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


def _build_graph(task_id: str, reactants: list[str], products: list[str], step_type: str) -> GoldMechanismGraph:
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
        step_type=step_type,
    )
    return GoldMechanismGraph(nodes=[r_node, ts_node, p_node], edges=[edge])


def _query(task_id: str, name: str, reactants: list[str], products: list[str], q: int, mult: int, conditions: str) -> str:
    rs = ".".join(reactants)
    ps = ".".join(products) if products else rs
    kind = "process" if task_id.startswith("M") else "reaction"
    # 只给任务与交付协议，不教练式地点名 TS/IRC/频率——"determine the
    # mechanism" 对合格的 agent 已隐含这些要求。
    return (
        f"Determine the mechanism of the following {kind} (easy tier): {name}. "
        f"Reactant SMILES: {rs}; product SMILES: {ps}; total charge {q}, multiplicity {mult}; "
        f"conditions: {conditions}. "
        "You must maintain `mechanism_graph.json` in the sandbox root recording the mechanism graph: "
        "nodes (reactant/product/transition_state, with SMILES) and elementary-step edges "
        "(with `via` pointing to the TS node id). The scorer reads this file forensically; "
        "a missing or unparseable file severely impacts the score. "
        "Allowed computational methods are limited to MACE-OMol25 and xTB; "
        "calls beyond the whitelist are intercepted."
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
        smiles_cell, conditions_cell, _mechanism_cell, barrier_cell, comfort_cell, _ref_cell = (
            cells[2], cells[3], cells[4], cells[5], cells[6], cells[7],
        )
        parsed = _parse_smiles_cell(smiles_cell)
        if parsed is None:
            continue
        reactants, products, q, mult = parsed
        barrier, btype, verification, doi = _parse_barrier(barrier_cell)
        elements, heavy = _parse_comfort(comfort_cell)
        # M 组第 4 列是过程类型而非条件（类型已并入 step_type 英译）；
        # 映射表未收录的条件/概要直接 KeyError 报错，防止静默漏译。
        if task_id.startswith("M"):
            conditions = "gas phase"
        else:
            conditions = _CONDITIONS_EN[conditions_cell]
        step_type = _STEP_TYPE_EN[task_id]

        graph = _build_graph(task_id, reactants, products, step_type)
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
