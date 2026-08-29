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
    BarrierReference,
    BarrierType,
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
DEFAULT_SRC = REPO_ROOT / "ideapool" / "reaction_candidates" / "easy.md"
DEFAULT_OUT = REPO_ROOT / "ideapool" / "tasks" / "easy"

ROW_RE = re.compile(r"^\|\s*([A-Z]\d+)\s*\|")
# SMILES cell like `C=CC=C.C=C>>C1CC=CCC1`，0/1  (backticks optional).
# charge may use the Unicode minus '−'; SMILES may carry a trailing note
# like `O=NO>>O=NO`（cis/trans），0/1 before the q/mult separator.
SMILES_RE = re.compile(r"`([^`]+)`(?:（[^）]*）)?\s*[，,]\s*([+−\-]?\d+)\s*/\s*(\d+)")
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

# 能垒口径（barrier_reference）统一为 CENTRAL（central_complex：TS 相对反应物
# 络合物/预反应络合物——双分子离子-分子反应即离子-偶极络合物；单分子与分子内
# 过程的反应物阱本身就是"反应物络合物"）。easy 档不采用相对分离反应物渐近线
# 的口径；个别题若日后确需 reactants 口径，在此按 task_id 显式登记覆盖。能垒
# 缺测时 barrier_reference 记 None。
_BARRIER_REFERENCE: dict[str, BarrierReference] = {}

# 口径核对登记：下列题的文献锚点明确是相对分离反应物渐近线的数值，且无络合物
# 口径的文献值可替换——数值原样保留（中性预反应络合物的 vdW 阱深一般只有
# ~1-3 kcal/mol，锚点在 accuracy 层高斯容差内仍有参考意义），verification
# 一律降为 unverified 待核，绝不按新口径编造数值。其余题的反应物阱即络合物
# 口径（单分子/分子内题）或出处本来就是中央能垒（C1/E1），直接挂 CENTRAL。
_BARRIER_FRAME_UNVERIFIED = {
    "D1", "D3", "D4",   # 双分子 DA：实验 Ea / 理论 ΔE‡ 均为分离反应物口径
    "C2", "C3", "F1",   # 题源单元格明确写"TS 相对反应物渐近线"
    "F3", "T1",         # 微溶剂化：文献能垒相对分离单体（"能垒降 ~30%"的口径）
    "G1", "G2", "G3",   # 双分子协同：文献值相对分离反应物（G3 题源本就未核实）
}

# 条件列中译英（按原字符串映射；新增条件必须在此登记，否则生成直接报错）。
# M 组表第 4 列是过程类型而非条件，Easy 档统一定义为气相可算，故 M 题
# conditions 一律 "gas phase"，过程类型并入 step_type 英译。
_CONDITIONS_EN = {
    "气相": "gas phase",
    "气相 487–648 °C 动力学": "gas phase, 487-648 degC kinetics",
    "气相/液相室温慢": "gas/liquid phase, slow at room temperature",
    "气相/烃溶剂加热": "gas phase or hydrocarbon solvent, heated",
    "气相 ~250 °C": "gas phase, ~250 degC",
    "气相/溶液室温即快": "gas phase or solution, fast at room temperature",
    "气相 ~200 °C": "gas phase, ~200 degC",
    "气相 403–448 K": "gas phase, 403-448 K",
    "气相 390–434 K": "gas phase, 390-434 K",
    "气相 ~350 °C": "gas phase, ~350 degC",
    "气相/溶液": "gas phase or solution",
    "气相/水溶液": "gas phase or aqueous solution",
    "气相微溶剂化": "gas phase, microsolvated",
    "气相/星际": "gas phase / interstellar",
    "气相高温": "gas phase, high temperature",
}

# 题名英译，按 task_id 映射；新增题目必须登记（漏译 KeyError 直接报错）。
_NAME_EN = {
    "D1": "butadiene + ethylene Diels-Alder (parent DA)",
    "D3": "cyclopentadiene dimerization (endo, self DA)",
    "D4": "cyclopentadiene + acrolein DA (heteroatom dienophile)",
    "P1": "1,5-hexadiene Cope rearrangement ([3,3], degenerate)",
    "P2": "cyclopentadiene [1,5]-H shift (degenerate)",
    "P3": "allyl vinyl ether Claisen rearrangement ([3,3])",
    "L1": "cyclobutene -> butadiene conrotatory ring opening",
    "L2": "hexatriene -> cyclohexadiene disrotatory ring closure",
    "X1": "beta-propiolactone -> ethylene + CO2 (decarboxylative extrusion)",
    "C1": "F- + CH3Cl -> CH3F + Cl-",
    "C2": "CN- + CH3Cl -> CH3CN + Cl-",
    "C3": "F- + CH3Cl double inversion (retention pathway)",
    "E1": "F- + CH3CH2Cl anti-E2 -> ethylene + HF + Cl-",
    "F1": "BH4- + formaldehyde -> methoxide + BH3",
    "F2": "CN- + formaldehyde -> cyanohydrin alkoxide",
    "F3": "formaldehyde + 2 H2O -> methanediol + H2O (water-assisted hydration)",
    "T1": "acetaldehyde + H2O -> vinyl alcohol + H2O (water-assisted tautomerization)",
    "T3": "HNC -> HCN (1,2-H shift)",
    "G1": "BH3 + ethylene hydroboration (concerted syn)",
    "G2": "diimide N2H2 cis reduction of ethylene (double H transfer)",
    "G3": "propylene + ethylene ene reaction (Alder-ene)",
    "M1": "2,2'-dimethylbiphenyl atropisomer rotation",
    "M3": "NH3 umbrella inversion",
    "M6": "ethane rotation (staggered<->eclipsed)",
    "M8": "cyclohexane chair flip",
    "M10": "acetaldehyde methyl rotation",
    "M12": "H5O2+ Zundel proton transfer",
    "M14": "acrolein s-trans <-> s-cis rotation",
    "M15": "HONO cis-trans isomerization",
    "M16": "formic acid dehydrogenation HCOOH -> CO2 + H2",
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
    "C3": "double inversion (retention): proton-abstraction-induced inversion to a [FH...CH2Cl]- intermediate, then a second inversion; gold models the rate-determining Cs-symmetric TS as a single step",
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

# ---------------------------------------------------------------------------
# 原子映射反应物 SMILES（query 专用）与 gold 边键变化，按 task_id 登记；
# 新增题目两处都必须登记（漏登 KeyError 直接报错）。
#
# 索引约定：query 向 agent 展示 _MAPPED_REACTANTS 的原子映射反应物 SMILES
# （RDKit 可读的 1-based atom-map 编号；参与键变化的 H 以显式 [H:n] 给出，
# 其余 H 保持隐式计数），gold 与 agent 交付边的 bond_changes [i, j] 对都引用
# 这套映射号，两侧因此共用同一套原子编号。system.reactants/products 与 gold
# 节点 SMILES 保持无映射（工具链与完整性取证用无映射形式）。
# 键变化口径：break = 该基元步内键级下降（含断至 0），form = 键级上升（含自
# 0 新建）；周环反应的 π 迁移据此记为旧 π 键 break + 新 π 键 form，双键变
# 单键（如羰基受亲核进攻）记 break。纯构象/翻转步（M1/M3/M6/M8/M10/M14/
# M15，扭转或伞形翻转，无键级变化）两个列表皆空。
# 注意：RDKit 默认 MolFromSmiles 会移除显式 H，核对映射 H 需 removeHs=False。
# ---------------------------------------------------------------------------
_MAPPED_REACTANTS = {
    "D1": "[CH2:1]=[CH:2][CH:3]=[CH2:4].[CH2:5]=[CH2:6]",
    "D3": "[CH:1]1=[CH:2][CH2:3][CH:4]=[CH:5]1.[CH:6]1=[CH:7][CH2:8][CH:9]=[CH:10]1",
    "D4": "[CH:1]1=[CH:2][CH2:3][CH:4]=[CH:5]1.[CH2:6]=[CH:7][CH:8]=[O:9]",
    "P1": "[CH2:1]=[CH:2][CH2:3][CH2:4][CH:5]=[CH2:6]",
    "P2": "[CH:1]1=[CH:2][CH:3]([H:6])[CH:4]=[CH:5]1",
    "P3": "[CH2:1]=[CH:2][CH2:3][O:4][CH:5]=[CH2:6]",
    "L1": "[CH:1]1=[CH:2][CH2:3][CH2:4]1",
    "L2": "[CH2:1]=[CH:2][CH:3]=[CH:4][CH:5]=[CH2:6]",
    "X1": "[O:1]=[C:2]1[O:3][CH2:4][CH2:5]1",
    "C1": "[F-:1].[CH3:2][Cl:3]",
    "C2": "[C-:1]#[N:2].[CH3:3][Cl:4]",
    "C3": "[F-:1].[CH3:2][Cl:3]",
    "E1": "[F-:1].[CH2:2]([H:4])[CH2:3][Cl:5]",
    "F1": "[BH3-:1][H:2].[CH2:3]=[O:4]",
    "F2": "[C-:1]#[N:2].[CH2:3]=[O:4]",
    "F3": "[CH2:1]=[O:2].[OH:3]([H:4]).[OH:5]([H:6])",
    "T1": "[CH2:1]([H:5])[CH:2]=[O:3].[OH:4]([H:6])",
    "T3": "[C-:1]#[N+:2][H:3]",
    "G1": "[BH2:1][H:3].[CH2:4]=[CH2:5]",
    "G2": "[N:1]([H:3])=[N:2]([H:4]).[CH2:5]=[CH2:6]",
    "G3": "[CH2:1]=[CH:2][CH2:3]([H:6]).[CH2:4]=[CH2:5]",
    "M1": "[CH3:1][c:2]1[cH:3][cH:4][cH:5][cH:6][c:7]1[c:8]1[c:9]([CH3:10])[cH:11][cH:12][cH:13][cH:14]1",
    "M3": "[NH3:1]",
    "M6": "[CH3:1][CH3:2]",
    "M8": "[CH2:1]1[CH2:2][CH2:3][CH2:4][CH2:5][CH2:6]1",
    "M10": "[CH3:1][CH:2]=[O:3]",
    "M12": "[OH2+:1][H:3].[OH2:2]",
    "M14": "[CH2:1]=[CH:2][CH:3]=[O:4]",
    "M15": "[O:1]=[N:2][OH:3]",
    "M16": "[O:1]([H:4])[C:2]([H:5])=[O:3]",
}

# (break, form)；每个 [i, j] 对引用上方同一 task 的映射号。逐题化学依据：
# - D/P/L/X 周环：断旧 π/σ、成新 π/σ（DA 成两个新 σ + 一个 π；电环化开/闭环
#   断/成一个 σ 并整体移 π；X1 断 C-C 与 C-O、成 C=O 第二键与 C=C）。
# - C1/C3 SN2（含双反转净结果）：断 C-Cl、成 C-F；C2 断 C-Cl、成 C-C（C 端）。
# - E1：断 β-C-H 与 C-Cl，成 H-F 与 C=C π。
# - F1 断 B-H 与 C=O π、成 C-H；F2 成 C-C、断 C=O π；F3 六元环 TS：C=O π 断、
#   两个 O-H 断/成各一次（水梭）、成新 C-O。
# - T1 水梭互变：断 α-C-H 与水 O-H，成两个 O-H 与 C=C π、断 C=O π；T3 断
#   N-H、成 C-H；M12 断 O-H、成另一 O-H（Zundel 质子转移）。
# - G1 断 B-H 与 C=C π，成 C-B 与 C-H；G2 双 H 转移：断两个 N-H 与 C=C π，
#   成两个 C-H 与 N≡N 第三键；G3 ene：断烯丙基 C-H、ene π 与 enophile π，
#   成新 C-H、新 C-C σ 与迁移 π。
# - M16 脱氢：断 O-H 与 C-H，成 H-H 与 C-O 第二键（CO2）。
# - M1/M3/M6/M8/M10/M14/M15：扭转/翻转无键级变化，([] , [])。
_BOND_CHANGES: dict[str, tuple[list[list[int]], list[list[int]]]] = {
    "D1": ([[1, 2], [3, 4], [5, 6]], [[1, 6], [2, 3], [4, 5]]),
    "D3": ([[1, 2], [4, 5], [6, 7]], [[1, 5], [2, 6], [4, 7]]),
    "D4": ([[1, 2], [4, 5], [6, 7]], [[1, 5], [2, 6], [4, 7]]),
    "P1": ([[1, 2], [3, 4], [5, 6]], [[1, 6], [2, 3], [4, 5]]),
    "P2": ([[1, 2], [3, 6], [4, 5]], [[1, 5], [2, 3], [4, 6]]),
    "P3": ([[1, 2], [3, 4], [5, 6]], [[1, 6], [2, 3], [4, 5]]),
    "L1": ([[1, 2], [3, 4]], [[1, 4], [2, 3]]),
    "L2": ([[1, 2], [3, 4], [5, 6]], [[1, 6], [2, 3], [4, 5]]),
    "X1": ([[2, 5], [3, 4]], [[2, 3], [4, 5]]),
    "C1": ([[2, 3]], [[1, 2]]),
    "C2": ([[3, 4]], [[1, 3]]),
    "C3": ([[2, 3]], [[1, 2]]),
    "E1": ([[2, 4], [3, 5]], [[1, 4], [2, 3]]),
    "F1": ([[1, 2], [3, 4]], [[2, 3]]),
    "F2": ([[3, 4]], [[1, 3]]),
    "F3": ([[1, 2], [3, 4], [5, 6]], [[1, 3], [2, 6], [4, 5]]),
    "T1": ([[1, 5], [2, 3], [4, 6]], [[1, 2], [3, 6], [4, 5]]),
    "T3": ([[2, 3]], [[1, 3]]),
    "G1": ([[1, 3], [4, 5]], [[1, 4], [3, 5]]),
    "G2": ([[1, 3], [2, 4], [5, 6]], [[1, 2], [3, 5], [4, 6]]),
    "G3": ([[1, 2], [3, 6], [4, 5]], [[1, 5], [2, 3], [4, 6]]),
    "M1": ([], []),
    "M3": ([], []),
    "M6": ([], []),
    "M8": ([], []),
    "M10": ([], []),
    "M12": ([[1, 3]], [[2, 3]]),
    "M14": ([], []),
    "M15": ([], []),
    "M16": ([[1, 4], [2, 5]], [[1, 2], [4, 5]]),
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


def _parse_barrier(cell: str) -> tuple[float | None, BarrierType | None, VerificationStatus, str]:
    """Return (barrier_kcal, barrier_type, verification, doi).

    能垒锚点只取引用括号之前的文本——括号里是文献出处（年份、卷页、DOI），
    从整格抓第一个数字会把年份（2023）或键长（2.4 Å）当成能垒。百分数
    （"能垒降 ~30%"）跳过。找不到锚点数字时返回 None（诚实缺测），并拒绝
    >200 kcal/mol 的离谱值（fail-loud 防回归）。类型只认单元格里显式写的
    Ea/ΔH‡/ΔE‡/ΔG‡ 记号；没写就是 None，不默认贴 Ea 标签。"""
    vtag = VERIFY_RE.search(cell)
    verification = _VERIFY_MAP.get(vtag.group(1), VerificationStatus.UNVERIFIED) if vtag else VerificationStatus.UNVERIFIED
    doi_m = re.search(r"DOI\s+([0-9.]+/\S*?)(?=[\s，。；）]|$)", cell)
    doi = doi_m.group(1).rstrip("）") if doi_m else ""
    # DOI 可以合法含括号（如 10.1016/s0009-2614(96)01253-5）：只剥不平衡的尾部 ")"
    while doi.endswith(")") and doi.count(")") > doi.count("("):
        doi = doi[:-1]

    btype: BarrierType | None = None
    for k, v in _BARRIER_TYPE_MAP.items():
        if k in cell:
            btype = v
            break

    # 引用信息从第一个括号开始；锚点在括号之前。范围取第一个数（下界）。
    head = re.split(r"[（(]", cell, maxsplit=1)[0]
    barrier = None
    for num_m in re.finditer(r"(\d+(?:\.\d+)?)(%?)", head):
        if num_m.group(2) == "%":
            continue  # "能垒降 ~30%" 是降幅不是锚点
        barrier = float(num_m.group(1))
        break
    if barrier is not None and not (0.0 <= barrier <= 200.0):
        raise ValueError(f"implausible barrier {barrier} parsed from cell: {cell!r}")
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
    # gold 边必须携带键变化（未登记 KeyError）：索引引用 query 展示的映射号，
    # 否则"agent 勤勉填了键变化"反而会因对称差被扣分（评分倒挂）
    breaks, forms = _BOND_CHANGES[task_id]
    edge = MechanismEdge(
        id=f"{task_id}_E1",
        **{"from": r_node.id, "to": p_node.id},
        via=ts_node.id,
        step_type=step_type,
        bond_changes=BondChangeSet(**{"break": breaks}, form=forms),
    )
    return GoldMechanismGraph(nodes=[r_node, ts_node, p_node], edges=[edge])


def _query(task_id: str, name: str, reactants: list[str], products: list[str], q: int, mult: int, conditions: str) -> str:
    rs = ".".join(reactants)
    ps = ".".join(products) if products else rs
    mapped = _MAPPED_REACTANTS[task_id]  # 原子映射反应物 SMILES；未登记 KeyError
    kind = "process" if task_id.startswith("M") else "reaction"
    # 只给任务与交付协议，不教练式地点名 TS/IRC/频率——"determine the
    # mechanism" 对合格的 agent 已隐含这些要求。证据文件的 smiles 注释是
    # 交付协议的一部分（评分器据此把图元素绑定到具体计算产物）。映射 SMILES
    # 只定义 bond_changes 的原子编号口径；节点与证据注释仍用无映射 SMILES。
    return (
        f"Determine the mechanism of the following {kind}: {name}. "
        f"Reactant SMILES: {rs}; product SMILES: {ps}; total charge {q}, multiplicity {mult}; "
        f"conditions: {conditions}. "
        f"Atom-mapped reactant SMILES: {mapped}. "
        "The 1-based map numbers in it are the indexing convention for `bond_changes` "
        "(keep using the plain SMILES above for graph nodes and evidence annotations). "
        "You must maintain `mechanism_graph.json` in the sandbox root recording the mechanism graph: "
        "nodes (reactant/product/transition_state, with SMILES) and elementary-step edges "
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
        task_id = cells[0]
        name = _NAME_EN[task_id]  # 题名英译；未登记直接 KeyError
        smiles_cell, conditions_cell, _mechanism_cell, barrier_cell, comfort_cell, _ref_cell = (
            cells[2], cells[3], cells[4], cells[5], cells[6], cells[7],
        )
        parsed = _parse_smiles_cell(smiles_cell)
        if parsed is None:
            continue
        reactants, products, q, mult = parsed
        barrier, btype, verification, doi = _parse_barrier(barrier_cell)
        # 口径统一 CENTRAL（见 _BARRIER_REFERENCE 注释）；锚点属渐近线口径的题
        # 按 _BARRIER_FRAME_UNVERIFIED 登记降为 unverified，数值保留不编造
        barrier_ref = _BARRIER_REFERENCE.get(task_id, BarrierReference.CENTRAL) if barrier is not None else None
        if task_id in _BARRIER_FRAME_UNVERIFIED:
            verification = VerificationStatus.UNVERIFIED
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
                    level_of_theory=(
                        "literature anchor (see reference_doi)"
                        if doi
                        else "literature anchor (curated in easy.md; no DOI on record)"
                    ),
                    barrier_kcal_mol=barrier,
                    barrier_type=btype,
                    barrier_reference=barrier_ref,
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
    # 先断言数量再落盘：计数回归时不会留下已写出的不一致产物
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
