from __future__ import annotations

import asyncio
import functools
import math
import os
from collections import deque
from io import StringIO
from typing import TYPE_CHECKING, Any, Literal, Optional

from pydantic import Field

if TYPE_CHECKING:
    # 仅用于类型注解；运行时在使用点惰性导入。
    import pandas as pd

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core.geometry import rotate_about_axis, rotation_matrix_between
from cloudra.tools.core.irc_path import (
    COVALENT_RADII as _COVALENT_RADII,
)
from cloudra.tools.core.irc_path import (
    DISTANCE_CONNECTIVITY_FACTOR as DISTANCE_CONNECTIVITY_FACTOR,
)

try:
    from rdkit import Chem
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    _RDKIT_AVAILABLE = False

try:
    import chemcoord as cc
    _CHEMCOORD_AVAILABLE = True
except Exception:
    cc = None
    _CHEMCOORD_AVAILABLE = False

# 共价半径：_COVALENT_RADII（irc_path 部分表，与 ts_guess/IRC 判据同一事实源）覆盖常见
# 主族与 3d/4d/5d 前段元素；其未覆盖元素（Pt/Ir/W/镧系等）取自 ase.data.covalent_radii——
# 同一套 Cordero (2008) 数据（重叠数值一致性由 tests 守护），ASE 是项目核心依赖，不新增依赖。
# 任何真实元素都有半径可查；查不到（非元素符号）一律 fail-loud 列出符号，绝不静默回退
# 1.2 Å（旧回退会把 Ir/Pt 配位球的 2.3–2.9 Å 非键接触静默误判成键）。


@functools.lru_cache(maxsize=1)
def _covalent_radii_table() -> dict[str, float]:
    """完整 Cordero (2008) 共价半径表（Å）：irc_path 表 + ASE 全表补缺，惰性构建。"""
    from ase.data import atomic_numbers, covalent_radii

    table = dict(_COVALENT_RADII)
    for symbol, z in atomic_numbers.items():
        if z > 0 and symbol not in table:
            table[symbol] = float(covalent_radii[z])
    return table


def _covalent_radius(symbol: str) -> float:
    """Cordero 共价半径（Å）；非元素符号 fail-loud（报错中列出符号）。"""
    table = _covalent_radii_table()
    if symbol not in table:
        raise ValueError(
            f"no Cordero covalent radius for element symbol {symbol!r}; "
            "the connectivity verdict for this structure is undecidable"
        )
    return table[symbol]

# Bondi 范德华半径（J. Phys. Chem. 1964），单位 Å。
_VAN_DER_WAALS_RADII = {
    'H': 1.20, 'He': 1.40, 'Li': 1.82, 'Be': 1.53, 'B': 1.92, 'C': 1.70,
    'N': 1.55, 'O': 1.52, 'F': 1.47, 'Ne': 1.54, 'Na': 2.27, 'Mg': 1.73,
    'Al': 1.84, 'Si': 2.10, 'P': 1.80, 'S': 1.80, 'Cl': 1.75, 'Ar': 1.88,
    'K': 2.75, 'Ca': 2.31, 'Sc': 2.15, 'Ti': 2.11, 'V': 2.07, 'Cr': 2.06,
    'Mn': 2.05, 'Fe': 2.04, 'Co': 2.00, 'Ni': 1.97, 'Cu': 1.96, 'Zn': 2.01,
    'Ga': 1.87, 'Ge': 2.11, 'As': 1.85, 'Se': 1.90, 'Br': 1.85, 'Kr': 2.02,
    'Rb': 2.03, 'Sr': 2.19, 'Y': 2.12, 'Zr': 2.03, 'Nb': 1.98, 'Mo': 1.90,
    'Tc': 1.83, 'Ru': 1.78, 'Rh': 1.73, 'Pd': 1.63, 'Ag': 1.72, 'Cd': 1.58,
    'In': 1.93, 'Sn': 2.17, 'Sb': 2.06, 'Te': 2.06, 'I': 1.98, 'Xe': 2.16,
}

# 常见元素对的参考键长（Å），键级键：1 / 1.5(芳香) / 2 / 3。
# 查不到的对回退到 共价半径和 × {1:1.00, 1.5:0.93, 2:0.87, 3:0.78}。
_REFERENCE_BOND_LENGTHS = {
    tuple(sorted(p)): orders for p, orders in {
        ('H', 'H'): {1: 0.74},
        ('B', 'H'): {1: 1.19}, ('C', 'H'): {1: 1.09}, ('N', 'H'): {1: 1.01},
        ('O', 'H'): {1: 0.96}, ('F', 'H'): {1: 0.92}, ('Si', 'H'): {1: 1.48},
        ('P', 'H'): {1: 1.42}, ('S', 'H'): {1: 1.34}, ('Cl', 'H'): {1: 1.27},
        ('Br', 'H'): {1: 1.41}, ('I', 'H'): {1: 1.61},
        ('B', 'B'): {1: 1.77}, ('B', 'C'): {1: 1.56}, ('B', 'N'): {1: 1.58},
        ('B', 'O'): {1: 1.48}, ('B', 'F'): {1: 1.40}, ('B', 'Cl'): {1: 1.75},
        ('C', 'C'): {1: 1.54, 1.5: 1.40, 2: 1.34, 3: 1.20},
        ('C', 'N'): {1: 1.47, 1.5: 1.34, 2: 1.28, 3: 1.16},
        ('C', 'O'): {1: 1.43, 1.5: 1.36, 2: 1.21, 3: 1.13},
        ('C', 'F'): {1: 1.35}, ('C', 'Si'): {1: 1.86},
        ('C', 'P'): {1: 1.84, 2: 1.66}, ('C', 'S'): {1: 1.82, 2: 1.60},
        ('C', 'Cl'): {1: 1.77}, ('C', 'Br'): {1: 1.94}, ('C', 'I'): {1: 2.14},
        ('N', 'N'): {1: 1.45, 1.5: 1.30, 2: 1.25, 3: 1.10},
        ('N', 'O'): {1: 1.40, 2: 1.20}, ('N', 'F'): {1: 1.36},
        ('N', 'Si'): {1: 1.75}, ('N', 'P'): {1: 1.71}, ('N', 'S'): {1: 1.68},
        ('N', 'Cl'): {1: 1.75},
        ('O', 'O'): {1: 1.48, 2: 1.21}, ('O', 'F'): {1: 1.42},
        ('O', 'Si'): {1: 1.63}, ('O', 'P'): {1: 1.60, 2: 1.48},
        ('O', 'S'): {1: 1.58, 2: 1.43}, ('O', 'Cl'): {1: 1.70},
        ('Si', 'Si'): {1: 2.33}, ('Si', 'S'): {2.0: 2.15, 1: 2.15},
        ('Si', 'Cl'): {1: 2.05},
        ('P', 'P'): {1: 2.22}, ('P', 'S'): {1: 2.10}, ('P', 'Cl'): {1: 2.04},
        ('S', 'S'): {1: 2.05}, ('S', 'Cl'): {1: 2.07},
        ('Cl', 'Cl'): {1: 1.99}, ('Br', 'Br'): {1: 2.28}, ('I', 'I'): {1: 2.67},
    }.items()
}

_BOND_ORDER_FALLBACK_FACTOR = {1.0: 1.00, 1.5: 0.93, 2.0: 0.87, 3.0: 0.78}

_MAGIC_REFS = ('origin', 'e_x', 'e_y', 'e_z')

description = (
    "Molecular-structure perception: from Cartesian coordinates (xyz/mol/pdb/sdf/cif), infer bond orders, stereochemistry, rings, and rotatable dihedrals; "
    "detect anomalous bond lengths (compressed/elongated/breaking_suspect/forming/atomic overlap) and anomalous angles; "
    "and write a Z-matrix internal-coordinate file along a spanning tree of the molecular graph. Can also convert a Z-matrix back to Cartesian. "
    "mode=transform applies rigid internal-coordinate edits to the Cartesian coordinates — rotate a group about an axis/bond, "
    "stretch or compress a bond by translating one fragment, invert a chiral center by swapping two branches — "
    "or edits the covalent topology by replacing a substituent with a new group given as SMILES, "
    "then re-validates the edited geometry (bond/angle anomaly detection) and returns the transformed xyz. "
    "Gives the model accurate structural facts without looking at a picture. "
    "REQUIRED before ts_guess scan_prepare/interpolate or any TS/scan work: scan/watch atom indices and reaction coordinates must come from this "
    "analyze report (forming/breaking bonds, dihedrals, clashes) — never from guessing XYZ indices or reading a picture. "
    "Also required to verify dihedral/angle preorganization that distance_filters cannot express. "
    "Use for: TS inspection (locating breaking/forming bonds), conformational analysis, stereo confirmation, geometry sanity checks, Z-matrix edits. "
    "Do not use for: plain format conversion (use format_converter) or generating a structure from SMILES (use smiles_to_mol)."
)


class InternalCoordinates_input_schema(input_schema):
    mode: Literal["analyze", "zmatrix_to_cartesian", "transform"] = Field(
        default="analyze",
        description="analyze: structure-perception analysis and write a Z-matrix file (default); "
                    "zmatrix_to_cartesian: restore Cartesian coordinates from Z-matrix text/file; "
                    "transform: apply rigid internal-coordinate operations (see 'operations') to the Cartesian "
                    "coordinates, validate the edited geometry, and return the transformed xyz."
    )
    input_path: Optional[str] = Field(
        default=None,
        description="Input file path (xyz/mol/pdb/sdf/cif, etc., ASE-readable). Used when mode=analyze or transform."
    )
    input_text: Optional[str] = Field(
        default=None,
        description="Coordinate text. If input_path is set, the file is read instead."
    )
    input_format: Literal["auto", "xyz", "mol", "pdb", "sdf", "cif"] = Field(
        default="auto",
        description="Cartesian input format. auto lets ASE infer from the file extension (input_text defaults to xyz)."
    )
    charge: int = Field(
        default=0,
        description="Total charge, used for RDKit bond-order perception (rdDetermineBonds.DetermineBonds). Default 0."
    )
    reactive_atoms: Optional[list[int]] = Field(
        default=None,
        description="Optional reaction-center atom indices (1-based). When set, the report includes bonded-neighbor distances and key angles for these atoms."
    )
    watch_pairs: Optional[list[list[int]]] = Field(
        default=None,
        description="Optional atom pairs to monitor explicitly (1-based). The report gives distances and a bonded/forming (distance heuristic)/undecidable/far verdict; crowded H...H contacts are never reported as forming."
    )
    bond_tolerance: float = Field(
        default=0.15,
        description="Bond-length deviation threshold as a fraction. measured/reference ≤ 1-threshold → compressed; ≥ 1+threshold → elongated (≥1.5 → breaking_suspect)."
    )
    angle_tolerance: float = Field(
        default=12.0,
        description="Bond-angle deviation threshold (degrees). Reported only when the deviation from the hybridization-expected angle exceeds this. Default 12°."
    )
    zmat_path: Optional[str] = Field(
        default=None,
        description="Z-matrix output path when mode=analyze. Default: <stem>.zmat next to input_path; "
                    "./structure.zmat for text-only input."
    )
    zmatrix_path: Optional[str] = Field(
        default=None,
        description="Z-matrix file path when mode=zmatrix_to_cartesian (preferred over zmatrix_text)."
    )
    zmatrix_text: Optional[str] = Field(
        default=None,
        description="Z-matrix text when mode=zmatrix_to_cartesian."
    )
    output_path: Optional[str] = Field(
        default=None,
        description="xyz output path when mode=zmatrix_to_cartesian or transform."
    )
    operations: Optional[list[dict]] = Field(
        default=None,
        description="Transform operations, required when mode=transform (rejected in other modes). Applied in order "
                    "on a copy of the coordinates; all atom indices are 1-based, matching the analyze report; "
                    "fragment selection uses the connectivity perceived from the input structure. "
                    "Four operation types: "
                    "(1) rotate — 'axis_atoms': [i, j] defines the rotation axis, 'degrees': angle in degrees, plus "
                    "exactly one group selector: 'atoms': [...] (explicit 1-based atom list) or 'side_of_bond': [a, b] "
                    "(rotate the fragment on the b side of bond a-b; fails when a-b is on a ring). "
                    "Example: {\"type\": \"rotate\", \"axis_atoms\": [3, 7], \"side_of_bond\": [3, 7], \"degrees\": 120}. "
                    "(2) stretch — 'atoms': [i, j] (must be a bonded pair), plus exactly one of 'delta': d (relative "
                    "change) or 'new_length': L (absolute target), both in Angstrom; the fragment on the j side of "
                    "bond i-j is translated along the i->j direction. "
                    "Example: {\"type\": \"stretch\", \"atoms\": [3, 7], \"new_length\": 2.10}. "
                    "(3) invert_chirality — 'center': c, 'swap': [n1, n2] (n1/n2 must both be bonded neighbors of c); "
                    "the two branches are rigidly swapped, inverting the stereocenter. "
                    "Example: {\"type\": \"invert_chirality\", \"center\": 5, \"swap\": [6, 9]}. "
                    "(4) replace_group — topology edit: 'bond': [a, b] (1-based bonded pair, not on a ring) cuts bond "
                    "a-b, removes the whole fragment on the b side, and attaches a new substituent to atom a; "
                    "'smiles': the new group with exactly one [*] dummy atom marking the attachment point "
                    "(e.g. '[*]C(=O)O' for -COOH, '[*]c1ccccc1' for phenyl, '[*]F' for -F). The substituent's 3D "
                    "geometry is embedded and force-field optimized, then docked along the old a->b direction at the "
                    "reference bond length; the new bond order comes from the [*] bond in the SMILES (default single). "
                    "Surviving atoms keep their order and the new atoms are appended; operations listed after a "
                    "replace_group use the NEW atom numbering. "
                    "Example: {\"type\": \"replace_group\", \"bond\": [3, 7], \"smiles\": \"[*]C(=O)O\"}."
    )


class InternalCoordinates_output_schema(output_schema):
    is_success: bool = Field(description="Whether the operation succeeded")
    report: str = Field(default="", description="Structured analysis report when mode=analyze (sectioned text)")
    anomalies: list[dict] = Field(
        default_factory=list,
        description="Machine-readable list of bond/angle anomalies; each item has type/atoms/value/reference/status. "
                    "When mode=transform, these are measured on the transformed coordinates."
    )
    operations_applied: list[dict] = Field(
        default_factory=list,
        description="Per-operation summaries when mode=transform: type, target atoms, parameters, and the "
                    "1-based list/count of atoms moved"
    )
    anomalies_before: list[dict] = Field(
        default_factory=list,
        description="Bond/angle anomalies of the input structure before the transform (mode=transform)"
    )
    zmat_path: str = Field(default="", description="Z-matrix file path written when mode=analyze")
    zmat_lines: int = Field(default=0, description="Line count of the Z-matrix file when mode=analyze")
    zmat_status: Literal["written", "failed", "not_requested"] = Field(
        default="not_requested",
        description="Z-matrix export status, reported separately from the geometry analysis: "
                    "'written' = file produced; 'failed' = export failed while the analysis "
                    "succeeded (see zmat_error); 'not_requested' = other mode.",
    )
    zmat_error: str = Field(
        default="",
        description="Why the Z-matrix export failed (only set when zmat_status='failed'). A failed "
                    "export never hides the completed distance/angle measurements.",
    )
    xyz_text: str = Field(default="", description="xyz text returned when mode=zmatrix_to_cartesian or transform")
    output_path: str = Field(default="", description="xyz file path written when mode=zmatrix_to_cartesian or transform")
    message: str = Field(default="", description="Status or error message")


def _expected_bond_length(sym_i: str, sym_j: str) -> float:
    """两个原子间的经验共价键长上限（Cordero 共价半径和）。"""
    return _covalent_radius(sym_i) + _covalent_radius(sym_j)


#: 距离判据的默认容差系数：r ≤ factor × 共价半径和 判为成键。
#: 唯一来源在 cloudra.tools.core.irc_path（顶部导入）——拓扑变更报告
#: （crest_runner）、电子结构分析（electronic_analysis）与 TS 弱接触分级
#: 共用同一阈值，不再各写一份。


def distance_connectivity(symbols, positions,
                          factor: float = DISTANCE_CONNECTIVITY_FACTOR) -> dict[tuple[int, int], float]:
    """距离判据连接表：``r ≤ factor × 共价半径和`` 判为单键。

    返回 ``{(i, j): 1.0}``，``i < j``。纯函数，供几何分析与拓扑对比共用。
    """
    import numpy as np

    n = len(symbols)
    bond_orders: dict[tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            r = float(np.linalg.norm(np.asarray(positions[i], dtype=float)
                                     - np.asarray(positions[j], dtype=float)))
            if r <= factor * _expected_bond_length(symbols[i], symbols[j]):
                bond_orders[(i, j)] = 1.0
    return bond_orders


def _angle_deg(p0, p1, p2) -> float:
    """p1 处的键角（度）。"""
    import numpy as np

    v1 = np.asarray(p0) - np.asarray(p1)
    v2 = np.asarray(p2) - np.asarray(p1)
    cos = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
    return float(np.degrees(np.arccos(float(np.clip(cos, -1.0, 1.0)))))


def _dihedral_deg(p0, p1, p2, p3) -> float:
    """p0-p1-p2-p3 二面角（度，-180..180）。"""
    import numpy as np

    b0 = -(np.asarray(p1) - np.asarray(p0))
    b1 = np.asarray(p2) - np.asarray(p1)
    b2 = np.asarray(p3) - np.asarray(p2)
    b1 = b1 / np.linalg.norm(b1)
    v = b0 - np.dot(b0, b1) * b1
    w = b2 - np.dot(b2, b1) * b1
    x = np.dot(v, w)
    y = np.dot(np.cross(b1, v), w)
    return float(np.degrees(np.arctan2(y, x)))


def _cremer_pople(coords) -> tuple[float, float, float]:
    """6 元环 Cremer–Pople 参数 (Q, θ, φ)，θ 单位度，φ 单位度。coords 须按环序排列。"""
    import numpy as np

    r = np.asarray(coords, dtype=float) - np.mean(coords, axis=0)
    _, _, vt = np.linalg.svd(r)
    z = r @ vt[2]
    n = len(z)
    q2c = math.sqrt(2.0 / n) * sum(z[j] * math.cos(2 * math.pi * 2 * j / n) for j in range(n))
    q2s = -math.sqrt(2.0 / n) * sum(z[j] * math.sin(2 * math.pi * 2 * j / n) for j in range(n))
    q3 = math.sqrt(2.0 / n) * sum(z[j] * math.cos(math.pi * j) for j in range(n))
    q2 = math.hypot(q2c, q2s)
    big_q = float(np.sqrt((z ** 2).sum()))
    theta = math.degrees(math.atan2(q2, q3))
    phi = math.degrees(math.atan2(q2s, q2c)) % 360.0
    return big_q, theta, phi


class InternalCoordinates(Tool):
    tool_id: str = 't-31'
    tool_name: str = 'internal_coordinates'
    tool_description: str = description
    input_schema: Any = InternalCoordinates_input_schema
    output_schema: Any = InternalCoordinates_output_schema

    def is_write(self) -> bool:
        return True

    # ---------- 基础几何/半径 ----------

    @classmethod
    def _covalent_radius(cls, symbol: str) -> float:
        return _covalent_radius(symbol)

    @classmethod
    def _expected_bond_length(cls, sym_i: str, sym_j: str) -> float:
        """两个原子间的经验共价键长上限（Cordero 共价半径和）。"""
        return cls._covalent_radius(sym_i) + cls._covalent_radius(sym_j)

    @classmethod
    def _van_der_waals_sum(cls, sym_i: str, sym_j: str) -> float:
        return _VAN_DER_WAALS_RADII.get(sym_i, 1.7) + _VAN_DER_WAALS_RADII.get(sym_j, 1.7)

    @classmethod
    def _reference_bond_length(cls, sym_i: str, sym_j: str, order: float) -> float:
        """元素对+键级的参考键长；查不到回退 共价半径和 × 键级系数。"""
        orders = _REFERENCE_BOND_LENGTHS.get(tuple(sorted((sym_i, sym_j))))
        if orders:
            key = order if order in orders else min(orders, key=lambda o: abs(o - order))
            if order in orders or abs(key - order) < 0.6:
                return orders[key]
        factor = _BOND_ORDER_FALLBACK_FACTOR.get(order, 1.0)
        return cls._expected_bond_length(sym_i, sym_j) * factor

    # ---------- 输入读取 ----------

    @staticmethod
    def _load_atoms_from_path_or_text(input_path: Optional[str],
                                      input_text: Optional[str],
                                      input_format: str):
        import ase.io

        if input_path and os.path.isfile(input_path):
            fmt = None if input_format == "auto" else input_format
            return ase.io.read(input_path, format=fmt)

        if input_text:
            fmt = "xyz" if input_format == "auto" else input_format
            return ase.io.read(StringIO(input_text), format=fmt)

        raise ValueError("Must provide input_path or input_text")

    @staticmethod
    def _atoms_to_xyz_block(atoms) -> str:
        pos = atoms.get_positions()
        syms = atoms.get_chemical_symbols()
        lines = [str(len(syms)), ""]
        for s, p in zip(syms, pos):
            lines.append(f"{s:<4} {p[0]:>14.8f} {p[1]:>14.8f} {p[2]:>14.8f}")
        return "\n".join(lines) + "\n"

    # ---------- 连接表 / 键级 ----------

    @classmethod
    def _perceive_bonds_rdkit(cls, xyz_block: str, charge: int):
        """RDKit 键级感知。成功返回 (mol, bond_orders)；失败抛异常由调用方回退。"""
        from rdkit import Chem
        from rdkit.Chem import rdDetermineBonds

        mol = Chem.MolFromXYZBlock(xyz_block)
        if mol is None:
            raise ValueError("RDKit could not parse the XYZ block")
        rdDetermineBonds.DetermineConnectivity(mol)
        rdDetermineBonds.DetermineBonds(mol, charge=charge)
        bond_orders: dict[tuple[int, int], float] = {}
        for bond in mol.GetBonds():
            i = min(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
            j = max(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
            order = 1.5 if bond.GetIsAromatic() else float(bond.GetBondTypeAsDouble())
            bond_orders[(i, j)] = order
        return mol, bond_orders

    @classmethod
    def _distance_connectivity(cls, symbols, positions) -> dict[tuple[int, int], float]:
        """距离判据回退连接表（实现见模块级 ``distance_connectivity``）。"""
        return distance_connectivity(symbols, positions)

    @staticmethod
    def _build_adjacency(n: int, bond_orders: dict[tuple[int, int], float]):
        adj: list[list[int]] = [[] for _ in range(n)]
        for (i, j) in bond_orders:
            adj[i].append(j)
            adj[j].append(i)
        for lst in adj:
            lst.sort()
        return adj

    # ---------- 立体化学 ----------

    @staticmethod
    def _stereochemistry_report(mol) -> tuple[list[str], list[str]]:
        """返回 (手性中心描述行, 双键 E/Z 描述行)。"""
        from rdkit import Chem

        chiral_lines: list[str] = []
        ez_lines: list[str] = []
        try:
            Chem.AssignStereochemistryFrom3D(mol)
            centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True, useLegacyImplementation=False)
            for idx, label in centers:
                sym = mol.GetAtomWithIdx(idx).GetSymbol()
                text = label if label != '?' else 'unassigned(?)'
                chiral_lines.append(f"  {sym}{idx + 1}: {text}")
            for bond in mol.GetBonds():
                stereo = bond.GetStereo()
                if stereo == Chem.BondStereo.STEREOE:
                    tag = 'E'
                elif stereo == Chem.BondStereo.STEREOZ:
                    tag = 'Z'
                else:
                    continue
                i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
                si = mol.GetAtomWithIdx(i).GetSymbol()
                sj = mol.GetAtomWithIdx(j).GetSymbol()
                ez_lines.append(f"  {si}{i + 1}={sj}{j + 1}: {tag}")
        except Exception:
            pass
        return chiral_lines, ez_lines

    # ---------- 环 ----------

    @staticmethod
    def _order_ring(ring_atoms: set[int], adj: list[list[int]]) -> list[int]:
        """把环原子集合按连接顺序排列。"""
        start = min(ring_atoms)
        order = [start]
        prev, cur = None, start
        while True:
            nxt = [a for a in adj[cur] if a in ring_atoms and a != prev]
            if not nxt:
                break
            nxt_atom = nxt[0]
            if nxt_atom == start:
                break
            if nxt_atom in order:
                break
            order.append(nxt_atom)
            prev, cur = cur, nxt_atom
        return order

    @classmethod
    def _rings_report(cls, mol, adj, symbols, positions,
                      bond_orders) -> tuple[list[str], list[set[int]]]:
        """返回 (报告行, 环原子集合列表)。6 元环附 Cremer–Pople 参数。"""
        ring_sets: list[set[int]] = []
        if mol is not None:
            from rdkit import Chem

            try:
                for ring in Chem.GetSymmSSSR(mol):
                    ring_sets.append(set(ring))
            except Exception:
                ring_sets = []
        elif adj is not None:
            try:
                import networkx as nx

                g = nx.Graph()
                g.add_nodes_from(range(len(symbols)))
                g.add_edges_from(bond_orders.keys())
                for cyc in nx.cycle_basis(g):
                    ring_sets.append(set(cyc))
            except Exception:
                ring_sets = []

        lines: list[str] = []
        for ring in ring_sets:
            ordered = cls._order_ring(ring, adj)
            labels = "-".join(f"{symbols[a]}{a + 1}" for a in ordered)
            line = f"  {len(ring)}-membered ring: {labels}"
            if len(ring) == 6 and len(ordered) == 6:
                try:
                    coords = [positions[a] for a in ordered]
                    big_q, theta, phi = _cremer_pople(coords)
                    if big_q < 0.05:
                        # Q≈0（如平面芳香环/苯）：Cremer–Pople 振幅为零，θ 无几何意义——
                        # 必须标 planar，不得按 θ 数值误判 chair/boat（θ=0 且 Q≈0 常发生）。
                        hint = "planar (Q≈0)"
                    elif theta < 15 or theta > 165:
                        hint = "near-chair (chair)"
                    elif 75 <= theta <= 105:
                        hint = "boat/twist-boat"
                    else:
                        hint = "intermediate conformation"
                    line += f"  [CP: Q={big_q:.3f} θ={theta:.1f}° φ={phi:.1f}° → {hint}]"
                except Exception:
                    pass
            lines.append(line)
        return lines, ring_sets

    # ---------- 可旋转二面角 ----------

    @classmethod
    def _rotatable_dihedrals(cls, mol, adj, symbols, positions,
                             bond_orders, ring_sets) -> list[str]:
        """SMARTS 匹配可旋转键，对每条取代表性四元组算扭转角并分类。"""
        pairs: list[tuple[int, int]] = []
        if mol is not None:
            from rdkit import Chem

            try:
                patt = Chem.MolFromSmarts('[!$(*#*)&!D1]-&!@[!$(*#*)&!D1]')
                for m in mol.GetSubstructMatches(patt, uniquify=True):
                    pairs.append((m[0], m[1]))
            except Exception:
                pairs = []
        else:
            in_ring: set[tuple[int, int]] = set()
            for ring in ring_sets:
                rl = sorted(ring)
                for x in rl:
                    for y in rl:
                        if x < y and (x, y) in bond_orders:
                            in_ring.add((x, y))
            for (i, j), order in bond_orders.items():
                if order != 1.0 or (i, j) in in_ring:
                    continue
                if len(adj[i]) >= 2 and len(adj[j]) >= 2:
                    pairs.append((i, j))

        def pick_neighbor(center: int, exclude: int) -> Optional[int]:
            cands = [a for a in adj[center] if a != exclude]
            if not cands:
                return None
            # 优先重原子，其次原子序号小者
            return sorted(cands, key=lambda a: (symbols[a] == 'H', a))[0]

        def classify(tau: float) -> str:
            t = abs(tau)
            if t <= 30.0:
                return "synperiplanar (cis-like)"
            if t <= 90.0:
                return "gauche/synclinal"
            if t <= 150.0:
                return "anticlinal"
            return "antiperiplanar (anti)"

        lines: list[str] = []
        for i, j in pairs:
            a = pick_neighbor(i, j)
            d = pick_neighbor(j, i)
            if a is None or d is None:
                continue
            tau = _dihedral_deg(positions[a], positions[i], positions[j], positions[d])
            quad = "-".join(f"{symbols[x]}{x + 1}" for x in (a, i, j, d))
            lines.append(f"  {quad}  τ={tau:.1f}°  [{classify(tau)}]")
        return lines

    # ---------- 异常键 ----------

    @classmethod
    def _abnormal_bonds(cls, symbols, positions, adj,
                        bond_orders, bond_tolerance: float) -> tuple[list[dict], list[str]]:
        """
        返回 (anomalies, report_lines)。
        分级：ratio ≤ 1-tol → compressed；≥ 1+tol → elongated；≥ 1.5 → breaking_suspect。
        非键对：r < 0.75×vdW 和 且 r > 单键参考 → forming_candidate；r < 单键参考但未成键 → clash。
        非键判定是纯距离启发式（输出带 basis='distance_heuristic' 标注）：两端都是 H 的
        接触不作成键候选（拥挤 H···H 没有成键含义，纯距离判据必然假阳性）；任一端元素
        缺 Bondi 范德华半径时 vdW 阈值不可信，标 undecidable 而不是给 forming。
        """
        import numpy as np

        n = len(symbols)
        anomalies: list[dict] = []
        bonded_keys = set(bond_orders.keys())

        # 1-3 关联（图上距离 ≤ 2）的非键对不报，避免淹没在正常键角几何中
        within_two: set[tuple[int, int]] = set()
        for i in range(n):
            seen = {i}
            for j in adj[i]:
                seen.add(j)
                for k in adj[j]:
                    seen.add(k)
            for j in seen:
                if i < j:
                    within_two.add((i, j))

        def dist(i, j):
            return float(np.linalg.norm(positions[i] - positions[j]))

        for (i, j), order in sorted(bond_orders.items()):
            r = dist(i, j)
            ref = cls._reference_bond_length(symbols[i], symbols[j], order)
            ratio = r / ref
            if ratio >= 1.5:
                status = 'breaking_suspect'
            elif ratio >= 1.0 + bond_tolerance:
                status = 'elongated'
            elif ratio <= 1.0 - bond_tolerance:
                status = 'compressed'
            else:
                continue
            anomalies.append({
                'type': 'bond',
                'atoms': [f"{symbols[i]}{i + 1}", f"{symbols[j]}{j + 1}"],
                'value': round(r, 3),
                'reference': round(ref, 3),
                'ratio': round(ratio, 3),
                'bond_order': order,
                'status': status,
            })

        for i in range(n):
            for j in range(i + 1, n):
                if (i, j) in bonded_keys or (i, j) in within_two:
                    continue
                r = dist(i, j)
                ref_single = cls._reference_bond_length(symbols[i], symbols[j], 1.0)
                vdw_sum = cls._van_der_waals_sum(symbols[i], symbols[j])
                if r < ref_single:
                    status = 'clash'
                elif symbols[i] == 'H' and symbols[j] == 'H':
                    # 拥挤 H···H 接触：纯距离判据对 H-H 没有成键含义，不成候选
                    continue
                elif r < 0.75 * vdw_sum:
                    if symbols[i] not in _VAN_DER_WAALS_RADII or symbols[j] not in _VAN_DER_WAALS_RADII:
                        status = 'undecidable'
                    else:
                        status = 'forming_candidate'
                else:
                    continue
                anomalies.append({
                    'type': 'bond',
                    'atoms': [f"{symbols[i]}{i + 1}", f"{symbols[j]}{j + 1}"],
                    'value': round(r, 3),
                    'reference': round(ref_single, 3),
                    'vdw_sum': round(vdw_sum, 3),
                    'bond_order': 0.0,
                    'status': status,
                    'basis': 'distance_heuristic',
                })

        status_label = {
            'compressed': 'compressed',
            'elongated': 'elongated',
            'breaking_suspect': 'breaking_suspect',
            'forming_candidate': 'forming_candidate (distance heuristic)',
            'clash': 'clash',
            'undecidable': 'undecidable (no Bondi vdW radius for at least one element)',
        }
        lines: list[str] = []
        for a in anomalies:
            pair = "-".join(a['atoms'])
            if a['bond_order'] > 0:
                lines.append(
                    f"  {pair}  r={a['value']:.3f} Å  ref={a['reference']:.3f} (bond order {a['bond_order']:g})  "
                    f"ratio={a['ratio']:.3f}  [{status_label[a['status']]}]"
                )
            else:
                lines.append(
                    f"  {pair}  r={a['value']:.3f} Å  single-bond ref={a['reference']:.3f}  vdW={a['vdw_sum']:.3f}  "
                    f"[{status_label[a['status']]}]"
                )
        return anomalies, lines

    # ---------- 异常键角 ----------

    @classmethod
    def _abnormal_angles(cls, symbols, positions, adj,
                         bond_orders, angle_tolerance: float) -> tuple[list[dict], list[str]]:
        """中心原子杂化估计期望角（sp 180 / sp2 120 / sp3 109.5），|Δ|>tolerance 才报。

        亚砜/砜/磺酰胺/磷酸酯的 S/P：配位数 ≥3 且带双键，是四面体中心而非 sp2/sp，
        期望角取 109.5°——只看键级会把它们推成 120°/180°，稳定产出假 angle_deviation。
        """

        def expected_angle(center: int) -> float:
            orders = [bond_orders[(min(center, x), max(center, x))] for x in adj[center]]
            if (symbols[center] in ('S', 'P') and len(orders) >= 3
                    and any(o == 2.0 for o in orders)):
                return 109.5
            if any(o >= 3.0 for o in orders) or sum(1 for o in orders if o == 2.0) >= 2:
                return 180.0
            if any(o in (1.5, 2.0) for o in orders):
                return 120.0
            return 109.5

        records: list[dict] = []
        for center in range(len(symbols)):
            nbrs = adj[center]
            if len(nbrs) < 2:
                continue
            ref = expected_angle(center)
            for x in range(len(nbrs)):
                for y in range(x + 1, len(nbrs)):
                    i, k = nbrs[x], nbrs[y]
                    actual = _angle_deg(positions[i], positions[center], positions[k])
                    delta = actual - ref
                    if abs(delta) > angle_tolerance:
                        records.append({
                            'type': 'angle',
                            'atoms': [f"{symbols[i]}{i + 1}", f"{symbols[center]}{center + 1}",
                                      f"{symbols[k]}{k + 1}"],
                            'value': round(actual, 1),
                            'reference': round(ref, 1),
                            'delta': round(delta, 1),
                            'status': 'angle_deviation',
                        })
        records.sort(key=lambda a: -abs(a['delta']))
        lines = [
            f"  {'-'.join(a['atoms'])}  ∠={a['value']:.1f}°  expected={a['reference']:.1f}°  Δ={a['delta']:+.1f}°"
            for a in records[:20]
        ]
        return records[:20], lines

    # ---------- 反应中心 ----------

    @classmethod
    def _reactive_center_report(cls, symbols, positions, adj, bond_orders,
                                reactive_atoms: Optional[list[int]],
                                watch_pairs: Optional[list[list[int]]]) -> list[str]:
        import numpy as np

        n = len(symbols)
        lines: list[str] = []

        def dist(i, j):
            return float(np.linalg.norm(positions[i] - positions[j]))

        def label(i):
            return f"{symbols[i]}{i + 1}"

        if watch_pairs:
            lines.append("  [Watched atom pairs]")
            for pair in watch_pairs:
                if len(pair) != 2:
                    continue
                i, j = pair[0] - 1, pair[1] - 1
                if not (0 <= i < n and 0 <= j < n):
                    lines.append(f"  {pair}: atom index out of range, skipped")
                    continue
                r = dist(i, j)
                ref_single = cls._reference_bond_length(symbols[i], symbols[j], 1.0)
                vdw_sum = cls._van_der_waals_sum(symbols[i], symbols[j])
                key = (min(i, j), max(i, j))
                if key in bond_orders:
                    order = bond_orders[key]
                    ref = cls._reference_bond_length(symbols[i], symbols[j], order)
                    verdict = f"bonded (bond order {order:g}, ref {ref:.3f})"
                elif symbols[i] == 'H' and symbols[j] == 'H':
                    verdict = "crowded H...H contact: not a bond-forming candidate"
                elif r < 0.75 * vdw_sum:
                    if symbols[i] not in _VAN_DER_WAALS_RADII or symbols[j] not in _VAN_DER_WAALS_RADII:
                        missing = sorted({symbols[i], symbols[j]} - set(_VAN_DER_WAALS_RADII))
                        verdict = (
                            f"undecidable: no Bondi vdW radius for {'/'.join(missing)}; "
                            "the distance-only forming criterion is not applicable"
                        )
                    else:
                        verdict = f"forming (distance heuristic): < vdW {vdw_sum:.3f}"
                        if r > ref_single:
                            verdict += f", > {symbols[i]}-{symbols[j]} single-bond ref {ref_single:.3f}"
                else:
                    verdict = f"far: > 0.75×vdW {0.75 * vdw_sum:.3f}"
                lines.append(f"  r({label(i)}-{label(j)})={r:.3f} Å  [{verdict}]")

        if reactive_atoms:
            lines.append("  [Reactive-center atoms]")
            for idx in reactive_atoms:
                i = idx - 1
                if not (0 <= i < n):
                    lines.append(f"  Atom {idx}: index out of range, skipped")
                    continue
                if not adj[i]:
                    lines.append(f"  {label(i)}: no bonded neighbors")
                    continue
                bonds_desc = []
                for j in adj[i]:
                    order = bond_orders[(min(i, j), max(i, j))]
                    ref = cls._reference_bond_length(symbols[i], symbols[j], order)
                    bonds_desc.append(f"{label(j)}={dist(i, j):.3f}(ref {ref:.3f})")
                lines.append(f"  {label(i)} neighbors: " + ", ".join(bonds_desc))
                nbrs = adj[i]
                angle_desc = []
                for x in range(len(nbrs)):
                    for y in range(x + 1, len(nbrs)):
                        a, b = nbrs[x], nbrs[y]
                        ang = _angle_deg(positions[a], positions[i], positions[b])
                        angle_desc.append(f"∠{label(a)}-{label(i)}-{label(b)}={ang:.1f}°")
                if angle_desc:
                    lines.append("    Angles: " + ", ".join(angle_desc[:8]))
        return lines

    # ---------- 等价原子 ----------

    @staticmethod
    def _equivalent_atoms_report(mol, symbols) -> list[str]:
        from rdkit import Chem

        try:
            ranks = Chem.CanonicalRankAtoms(mol, breakTies=False)
        except Exception:
            return []
        groups: dict[int, list[int]] = {}
        for idx, rank in enumerate(ranks):
            groups.setdefault(int(rank), []).append(idx)
        lines = []
        for members in groups.values():
            if len(members) > 1:
                lines.append("  {" + ", ".join(f"{symbols[i]}{i + 1}" for i in sorted(members)) + "}")
        return lines

    # ---------- Z-matrix 构造表 ----------

    @staticmethod
    def _build_construction_table(adj: list[list[int]]) -> list[tuple[int, Any, Any, Any]]:
        """
        沿分子图生成树（从度数最大的原子 BFS）构造 construction table。
        返回按放置顺序排列的 [(atom_idx, b, a, d), ...]，其中 b/a/d 为 0-based 原子序号
        或 chemcoord magic 参考（origin/e_z/e_x）。多碎片时每个碎片根回退 origin/e_z/e_x。
        """
        n = len(adj)
        seen: set[int] = set()
        order: list[tuple[int, Any, Any, Any]] = []

        starts = sorted(range(n), key=lambda i: (-len(adj[i]), i))
        for start in starts:
            if start in seen:
                continue
            # BFS，记录父原子
            parent: dict[int, Optional[int]] = {start: None}
            queue: deque[int] = deque([start])
            seen.add(start)
            while queue:
                node = queue.popleft()
                placed = {entry[0] for entry in order}
                par = parent[node]
                if par is None or par not in placed:
                    # 碎片根：绝对参考
                    order.append((node, 'origin', 'e_z', 'e_x'))
                else:
                    b = par
                    a: Any = next((x for x in adj[b] if x in placed and x != node), 'e_z')
                    if isinstance(a, int):
                        d: Any = next((x for x in adj[a] if x in placed and x not in (b, node)), 'e_x')
                    else:
                        d = 'e_x'
                    order.append((node, b, a, d))
                for nxt in adj[node]:
                    if nxt not in seen:
                        seen.add(nxt)
                        parent[nxt] = node
                        queue.append(nxt)
        return order

    @staticmethod
    def _ase_to_chemcoord_cart(atoms) -> "cc.Cartesian":
        """把 ASE Atoms 转成 chemcoord.Cartesian（1-based index）。"""
        import chemcoord as cc
        import pandas as pd

        pos = atoms.get_positions()
        syms = atoms.get_chemical_symbols()
        df = pd.DataFrame({
            'atom': syms,
            'x': pos[:, 0], 'y': pos[:, 1], 'z': pos[:, 2],
        })
        df.index = range(1, len(syms) + 1)
        return cc.Cartesian(df)

    @staticmethod
    def _fix_collinear_dihedral_refs(cart: "cc.Cartesian", c_table: pd.DataFrame) -> pd.DataFrame:
        """
        chemcoord get_X 要求每行的 d-a-b 不共线，否则二面角未定义、重建报错。
        逐行检查，共线时把 d 换成第一个与 a-b 不共线的 magic 参考（e_x/e_y/e_z），
        此时绕 a-b 轴的旋转任意，换参考不影响重建几何。
        """
        import numpy as np

        dummy = {
            'origin': np.zeros(3), 'e_x': np.array([1.0, 0.0, 0.0]),
            'e_y': np.array([0.0, 1.0, 0.0]), 'e_z': np.array([0.0, 0.0, 1.0]),
        }
        pos = {
            idx: cart.loc[idx, ['x', 'y', 'z']].to_numpy(dtype=float)
            for idx in c_table.index
        }

        def ref(x):
            s = str(x)
            if s in dummy:
                return dummy[s]
            return pos[int(float(s))]

        c_table = c_table.copy()
        d_col = c_table.columns.get_loc('d')
        for i in range(len(c_table)):
            pb, pa = ref(c_table.iloc[i]['b']), ref(c_table.iloc[i]['a'])
            u = pa - pb
            if np.linalg.norm(u) < 1e-12:
                continue
            pd_ = ref(c_table.iloc[i]['d'])
            if np.linalg.norm(np.cross(u, pd_ - pb)) > 1e-9:
                continue
            for cand in ('e_x', 'e_y', 'e_z'):
                if np.linalg.norm(np.cross(u, dummy[cand] - pb)) > 1e-9:
                    c_table.iloc[i, d_col] = cand
                    break
        return c_table

    @staticmethod
    def _calculate_zmat_values_local(cart: "cc.Cartesian", c_table: pd.DataFrame):
        """
        本地计算 Z-matrix 数值（bond/angle/dihedral），与 chemcoord get_X 的
        绝对参考语义一致（origin=(0,0,0), e_x/e_y/e_z 为单位向量，二面角取
        d-a-b-p 扭转角的相反数）。避免 chemcoord _calculate_zmat_values 在
        首原子恰位于 origin 等退化情况下静默返回 None。
        """
        import numpy as np

        dummy = {
            'origin': np.zeros(3), 'e_x': np.array([1.0, 0.0, 0.0]),
            'e_y': np.array([0.0, 1.0, 0.0]), 'e_z': np.array([0.0, 0.0, 1.0]),
        }
        pos = {
            idx: cart.loc[idx, ['x', 'y', 'z']].to_numpy(dtype=float)
            for idx in c_table.index
        }

        def ref(x):
            s = str(x)
            if s in dummy:
                return dummy[s]
            return pos[int(float(s))]

        values = np.zeros((len(c_table), 3))
        for row, (idx, r) in enumerate(c_table.iterrows()):
            p = pos[idx]
            pb, pa, pd_ = ref(r['b']), ref(r['a']), ref(r['d'])
            bond = float(np.linalg.norm(p - pb))
            v1, v2 = pa - pb, p - pb
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 < 1e-12 or n2 < 1e-12:
                angle = 0.0
            else:
                cos = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
                angle = float(np.degrees(np.arccos(cos)))
            try:
                dihedral = -_dihedral_deg(pd_, pa, pb, p)
            except Exception:
                dihedral = 0.0
            if not np.isfinite(dihedral):
                dihedral = 0.0
            values[row] = (bond, angle, dihedral)
        return values

    @staticmethod
    def _build_zmat_dataframe(cart: "cc.Cartesian", c_table: pd.DataFrame) -> pd.DataFrame:
        """
        绕开 chemcoord 2.1.2 与新版 pandas/string-dtype 的兼容 bug：
        _build_zmat 用 np.empty(..., dtype=str) 创建列，无法接受 mixed int/str 的 construction table。
        这里显式用 object dtype 构造 Zmat DataFrame，数值由 _calculate_zmat_values_local 给出。
        """
        import numpy as np
        import pandas as pd

        n = len(c_table)
        dtypes = [
            ('atom', 'O'), ('b', 'O'), ('bond', float),
            ('a', 'O'), ('angle', float), ('d', 'O'), ('dihedral', float)
        ]
        zmat_frame = pd.DataFrame(np.empty(n, dtype=dtypes), index=c_table.index)
        zmat_frame.loc[:, 'atom'] = cart.loc[c_table.index, 'atom'].astype(str)
        c_table = InternalCoordinates._fix_collinear_dihedral_refs(cart, c_table)
        zmat_frame.loc[:, ['b', 'a', 'd']] = c_table.astype(str)

        values = InternalCoordinates._calculate_zmat_values_local(cart, c_table)
        zmat_frame.loc[:, ['bond', 'angle', 'dihedral']] = values
        return zmat_frame

    @classmethod
    def _render_zmatrix(cls, zmat_frame: pd.DataFrame) -> str:
        """
        渲染 annotated Z-matrix 文本。父原子以原子标签（如 C2）或 magic 参考（origin/e_z/e_x）表示，
        保持能被 _parse_zmatrix_text 解析回去。
        """
        import pandas as pd

        idx_to_name = {idx: f"{row['atom']}{idx}" for idx, row in zmat_frame.iterrows()}

        def format_parent(x) -> str:
            s = str(x) if pd.notna(x) else ''
            if s in _MAGIC_REFS or s in ('None', ''):
                return s or 'origin'
            try:
                return idx_to_name.get(int(s), s)
            except (ValueError, TypeError):
                return s

        lines = [
            "# Z-matrix (internal coordinates), generated along molecular-graph spanning tree",
            "# Units: bond length in Å, angle/dihedral in degrees",
            "# Format: index name | parent r=... | parent a=... | parent d=...",
            "# Parent is an atom label (e.g. C2) or absolute reference (origin/e_z/e_x)",
            "",
        ]

        for idx, row in zmat_frame.iterrows():
            name = idx_to_name[idx]
            parts = [f"{idx:3d}  {name:<5}"]
            parts.append(f"| {format_parent(row['b']):<7} r={float(row['bond']):.4f}")
            parts.append(f"| {format_parent(row['a']):<7} a={float(row['angle']):.2f}")
            parts.append(f"| {format_parent(row['d']):<7} d={float(row['dihedral']):.2f}")
            lines.append("  ".join(parts))

        return "\n".join(lines) + "\n"

    # ---------- analyze 主流程 ----------

    def _analyze(self, user_input: InternalCoordinates_input_schema) -> InternalCoordinates_output_schema:
        import numpy as np

        try:
            atoms = self._load_atoms_from_path_or_text(
                user_input.input_path, user_input.input_text, user_input.input_format,
            )
        except Exception as e:
            return InternalCoordinates_output_schema(is_success=False, message=f"Failed to read input structure: {e}")

        symbols = atoms.get_chemical_symbols()
        positions = np.asarray(atoms.get_positions(), dtype=float)
        n = len(symbols)
        notes: list[str] = []

        # 1. 键级感知（RDKit 优先，距离判据回退）
        mol = None
        if _RDKIT_AVAILABLE:
            try:
                mol, bond_orders = self._perceive_bonds_rdkit(
                    self._atoms_to_xyz_block(atoms), user_input.charge,
                )
            except Exception as e:
                bond_orders = self._distance_connectivity(symbols, positions)
                notes.append(f"RDKit bond perception failed ({e}); bond orders were not perceived — bond info below is distance-inferred (all treated as single bonds).")
        else:
            bond_orders = self._distance_connectivity(symbols, positions)
            notes.append("RDKit is not installed; bond orders were not perceived — bond info below is distance-inferred (all treated as single bonds).")

        adj = self._build_adjacency(n, bond_orders)
        n_frag = 0
        seen: set[int] = set()
        for i in range(n):
            if i in seen:
                continue
            n_frag += 1
            stack = [i]
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                stack.extend(adj[x])

        # 2. 各分析块
        chiral_lines: list[str] = []
        ez_lines: list[str] = []
        if mol is not None:
            chiral_lines, ez_lines = self._stereochemistry_report(mol)
        elif _RDKIT_AVAILABLE:
            notes.append("Bond orders were not perceived; stereochemistry analysis skipped.")

        ring_lines, ring_sets = self._rings_report(mol, adj, symbols, positions, bond_orders)
        rot_lines = self._rotatable_dihedrals(mol, adj, symbols, positions, bond_orders, ring_sets)
        bond_anomalies, bond_lines = self._abnormal_bonds(
            symbols, positions, adj, bond_orders, user_input.bond_tolerance,
        )
        angle_anomalies, angle_lines = self._abnormal_angles(
            symbols, positions, adj, bond_orders, user_input.angle_tolerance,
        )
        reactive_lines = []
        if user_input.reactive_atoms or user_input.watch_pairs:
            reactive_lines = self._reactive_center_report(
                symbols, positions, adj, bond_orders,
                user_input.reactive_atoms, user_input.watch_pairs,
            )
        equiv_lines: list[str] = []
        if mol is not None:
            equiv_lines = self._equivalent_atoms_report(mol, symbols)

        # 3. 组装报告（约 80 行以内）
        hill: dict[str, int] = {}
        for s in symbols:
            hill[s] = hill.get(s, 0) + 1
        if 'C' in hill:
            formula_keys = ['C', 'H'] + sorted(k for k in hill if k not in ('C', 'H'))
        else:
            formula_keys = sorted(hill)
        formula = "".join(f"{k}{hill[k] if hill[k] > 1 else ''}" for k in formula_keys if k in hill)

        report: list[str] = ["== Summary =="]
        report.append(f"  Formula: {formula}  Atoms: {n}  Bonds: {len(bond_orders)}  "
                      f"Fragments: {n_frag}  Total charge: {user_input.charge}")
        report.append(f"  Bond orders: {'RDKit (perceived)' if mol is not None else 'distance-inferred (all single)'}")
        report.append(f"  Bond anomalies: {len(bond_anomalies)}  Angle anomalies: {len(angle_anomalies)}")

        report.append("== Stereochemistry ==")
        if chiral_lines or ez_lines:
            if chiral_lines:
                report.append("  Chiral centers:")
                report.extend(chiral_lines)
            if ez_lines:
                report.append("  Double-bond configurations:")
                report.extend(ez_lines)
        else:
            report.append("  No chiral centers / no E-Z double bonds (or not perceived)")

        report.append("== Rings ==")
        report.extend(ring_lines if ring_lines else ["  No rings"])

        report.append("== Rotatable Dihedrals ==")
        if rot_lines:
            report.extend(rot_lines[:15])
            if len(rot_lines) > 15:
                report.append(f"  ... {len(rot_lines) - 15} more omitted")
        else:
            report.append("  No rotatable bonds")

        report.append("== Abnormal Bonds ==")
        report.extend(bond_lines if bond_lines else ["  No abnormal bond lengths (normal bonds are not listed)"])

        report.append("== Abnormal Angles ==")
        report.extend(angle_lines if angle_lines else [f"  No bond angles deviating by more than {user_input.angle_tolerance:.1f}°"])

        if user_input.reactive_atoms or user_input.watch_pairs:
            report.append("== Reactive Center ==")
            report.extend(reactive_lines if reactive_lines else ["  (no valid input)"])

        report.append("== Equivalent Atoms ==")
        if equiv_lines:
            report.extend(equiv_lines[:10])
        else:
            report.append("  No symmetry-equivalent atom groups (or not perceived)")

        report.append("== Notes ==")
        notes.append("Numeric format: bond lengths 3 decimals (Å), angles 1 decimal (°); van der Waals radii from Bondi (1964).")
        notes.append("forming_candidate/breaking_suspect are geometric-criteria hints only; interpret them against the reaction mechanism.")
        report.extend(f"  - {t}" for t in notes)

        # 4. Z-matrix 文件。导出与几何报告**分别给状态**：Z-matrix 失败（chemcoord 缺失、
        #    构造表退化等）绝不能让已完成的键长/键角/异常测量变得不可用。
        zmat_path = user_input.zmat_path
        if not zmat_path:
            if user_input.input_path:
                stem = os.path.splitext(user_input.input_path)[0]
                zmat_path = stem + ".zmat"
            else:
                zmat_path = resolve_tool_path(self, "./structure.zmat")

        zmat_status: Literal["written", "failed"] = "written"
        zmat_error = ""
        zmat_lines = 0
        try:
            cart = self._ase_to_chemcoord_cart(atoms)
            order = self._build_construction_table(adj)
            import pandas as pd

            c_table = pd.DataFrame(
                {
                    'b': [e[1] if isinstance(e[1], str) else e[1] + 1 for e in order],
                    'a': [e[2] if isinstance(e[2], str) else e[2] + 1 for e in order],
                    'd': [e[3] if isinstance(e[3], str) else e[3] + 1 for e in order],
                },
                index=[e[0] + 1 for e in order],
            )
            zmat_frame = self._build_zmat_dataframe(cart, c_table)
            zmatrix_text = self._render_zmatrix(zmat_frame)
            os.makedirs(os.path.dirname(zmat_path) or ".", exist_ok=True)
            atomic_write_text(zmat_path, zmatrix_text)
            zmat_lines = zmatrix_text.count("\n")
        except Exception as e:  # noqa: BLE001 - 导出失败只降级导出，不丢几何报告
            zmat_status = "failed"
            zmat_error = f"{type(e).__name__}: {e}"
            report.append(
                f"  - Z-matrix export failed ({zmat_error}); the distance/angle measurements above "
                "are unaffected and remain valid."
            )

        anomalies = bond_anomalies + angle_anomalies
        if zmat_status == "written":
            message = (
                f"Structure analysis complete: {len(bond_anomalies)} bond anomalies, "
                f"{len(angle_anomalies)} angle anomalies. "
                f"Z-matrix written to {zmat_path} ({zmat_lines} lines); its content is not included "
                "in context — restore coordinates with mode=zmatrix_to_cartesian."
            )
        else:
            message = (
                f"Structure analysis complete: {len(bond_anomalies)} bond anomalies, "
                f"{len(angle_anomalies)} angle anomalies. "
                f"Z-matrix export FAILED ({zmat_error}); request a Z-matrix from a different structure "
                "or install the chemcoord extra, then retry."
            )
        return InternalCoordinates_output_schema(
            is_success=True,
            report="\n".join(report),
            anomalies=anomalies,
            zmat_path=zmat_path if zmat_status == "written" else "",
            zmat_lines=zmat_lines,
            zmat_status=zmat_status,
            zmat_error=zmat_error,
            message=message,
        )

    # ---------- transform ----------

    @staticmethod
    def _transform_atom_index(value, n: int, context: str) -> int:
        """transform op 的 1-based 原子索引校验，非法一律 fail-loud。"""
        if not isinstance(value, int) or isinstance(value, bool) or not (1 <= value <= n):
            raise ValueError(f"{context}: atom index {value!r} is not a valid 1-based index (1..{n})")
        return value - 1

    @staticmethod
    def _bfs_group(adj: dict[int, set[int]], start: int) -> set[int]:
        seen = {start}
        stack = [start]
        while stack:
            x = stack.pop()
            for y in adj.get(x, ()):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        return seen

    @staticmethod
    def _adjacency_without_edge(adj: dict[int, set[int]], i: int, j: int) -> dict[int, set[int]]:
        cut = {k: set(v) for k, v in adj.items()}
        cut[i].discard(j)
        cut[j].discard(i)
        return cut

    @staticmethod
    def _op_finite_number(value, context: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"{context} must be a finite number, got {value!r}")
        return float(value)

    @classmethod
    def _op_rotate(cls, op: dict, positions, adj: dict[int, set[int]], n: int) -> dict:
        axis_raw = op.get("axis_atoms")
        if not (isinstance(axis_raw, list) and len(axis_raw) == 2):
            raise ValueError("rotate requires axis_atoms: [i, j] (1-based indices of the two axis atoms)")
        ia = cls._transform_atom_index(axis_raw[0], n, "rotate axis_atoms")
        ib = cls._transform_atom_index(axis_raw[1], n, "rotate axis_atoms")
        if ia == ib:
            raise ValueError("rotate axis_atoms must be two distinct atoms")
        degrees = cls._op_finite_number(op.get("degrees"), "rotate 'degrees'")

        has_atoms = op.get("atoms") is not None
        has_side = op.get("side_of_bond") is not None
        if has_atoms == has_side:
            raise ValueError(
                "rotate requires exactly one of 'atoms' (explicit group) or 'side_of_bond' "
                "([a, b]: rotate the fragment on the b side of bond a-b)"
            )
        if has_atoms:
            if not isinstance(op["atoms"], list) or not op["atoms"]:
                raise ValueError("rotate 'atoms' must be a non-empty list of 1-based atom indices")
            group = {cls._transform_atom_index(x, n, "rotate atoms") for x in op["atoms"]}
            selection = f"explicit atoms {sorted(x + 1 for x in group)}"
        else:
            side_raw = op["side_of_bond"]
            if not (isinstance(side_raw, list) and len(side_raw) == 2):
                raise ValueError("rotate 'side_of_bond' must be [a, b] (1-based bonded pair)")
            a = cls._transform_atom_index(side_raw[0], n, "rotate side_of_bond")
            b = cls._transform_atom_index(side_raw[1], n, "rotate side_of_bond")
            if b not in adj.get(a, set()):
                raise ValueError(f"rotate side_of_bond: atoms {a + 1} and {b + 1} are not bonded")
            group = cls._bfs_group(cls._adjacency_without_edge(adj, a, b), b)
            if a in group:
                raise ValueError(
                    f"rotate side_of_bond: bond {a + 1}-{b + 1} lies on a ring (the graph stays "
                    "connected after cutting it); cannot select a side — pass explicit 'atoms' instead"
                )
            selection = f"side of bond {a + 1}-{b + 1} from atom {b + 1}"
        positions[:] = rotate_about_axis(positions, sorted(group), positions[ia], positions[ib], degrees)
        moved = sorted(x + 1 for x in group if x not in (ia, ib))
        return {
            "type": "rotate",
            "axis_atoms": [ia + 1, ib + 1],
            "degrees": degrees,
            "selection": selection,
            "moved_atoms": moved,
            "n_moved": len(moved),
        }

    @classmethod
    def _op_stretch(cls, op: dict, positions, adj: dict[int, set[int]], n: int) -> dict:
        import numpy as np

        atoms_raw = op.get("atoms")
        if not (isinstance(atoms_raw, list) and len(atoms_raw) == 2):
            raise ValueError("stretch requires atoms: [i, j] (1-based indices of a bonded pair)")
        i = cls._transform_atom_index(atoms_raw[0], n, "stretch atoms")
        j = cls._transform_atom_index(atoms_raw[1], n, "stretch atoms")
        if i == j:
            raise ValueError("stretch atoms must be two distinct atoms")
        if j not in adj.get(i, set()):
            raise ValueError(f"stretch: atoms {i + 1} and {j + 1} are not bonded")
        delta, new_length = op.get("delta"), op.get("new_length")
        if (delta is None) == (new_length is None):
            raise ValueError("stretch requires exactly one of 'delta' or 'new_length' (Angstrom)")
        vec = positions[j] - positions[i]
        current = float(np.linalg.norm(vec))
        if current < 1e-9:
            raise ValueError(f"stretch: atoms {i + 1} and {j + 1} coincide; the direction is undefined")
        target = current + cls._op_finite_number(delta, "stretch 'delta'") if delta is not None \
            else cls._op_finite_number(new_length, "stretch 'new_length'")
        if target <= 0.0:
            raise ValueError(f"stretch: target bond length must be > 0 Angstrom, got {target:.3f}")
        group = cls._bfs_group(cls._adjacency_without_edge(adj, i, j), j)
        if i in group:
            raise ValueError(
                f"stretch: bond {i + 1}-{j + 1} lies on a ring (the graph stays connected after "
                "cutting it); stretching it is not a rigid-fragment operation"
            )
        idx = sorted(group)
        positions[idx] = positions[idx] + (target - current) * vec / current
        return {
            "type": "stretch",
            "atoms": [i + 1, j + 1],
            "old_length": round(current, 4),
            "new_length": round(target, 4),
            "moved_atoms": [x + 1 for x in idx],
            "n_moved": len(idx),
        }

    @classmethod
    def _op_invert_chirality(cls, op: dict, positions, adj: dict[int, set[int]], n: int) -> dict:
        if "center" not in op:
            raise ValueError("invert_chirality requires 'center' (1-based index of the stereocenter)")
        c = cls._transform_atom_index(op["center"], n, "invert_chirality center")
        swap_raw = op.get("swap")
        if not (isinstance(swap_raw, list) and len(swap_raw) == 2):
            raise ValueError("invert_chirality requires swap: [n1, n2] (two bonded neighbors of the center, 1-based)")
        n1 = cls._transform_atom_index(swap_raw[0], n, "invert_chirality swap")
        n2 = cls._transform_atom_index(swap_raw[1], n, "invert_chirality swap")
        if n1 == n2:
            raise ValueError("invert_chirality swap atoms must be distinct")
        neighbors = adj.get(c, set())
        if n1 not in neighbors or n2 not in neighbors:
            raise ValueError(
                f"invert_chirality: swap atoms {n1 + 1} and {n2 + 1} must both be bonded neighbors "
                f"of the center atom {c + 1}"
            )
        cut = {k: (set(v) - {c}) for k, v in adj.items()}
        cut[c] = set()
        branch1 = cls._bfs_group(cut, n1)
        branch2 = cls._bfs_group(cut, n2)
        if branch1 & branch2:
            raise ValueError(
                "invert_chirality: the two swap branches stay connected without the center (ring); "
                "cannot swap them rigidly"
            )
        rotation = rotation_matrix_between(positions[n1] - positions[c], positions[n2] - positions[c])
        center_pos = positions[c]
        idx1, idx2 = sorted(branch1), sorted(branch2)
        positions[idx1] = (positions[idx1] - center_pos) @ rotation.T + center_pos
        positions[idx2] = (positions[idx2] - center_pos) @ rotation + center_pos
        moved = [x + 1 for x in sorted(branch1 | branch2)]
        return {
            "type": "invert_chirality",
            "center": c + 1,
            "swap": [n1 + 1, n2 + 1],
            "moved_atoms": moved,
            "n_moved": len(moved),
        }

    @staticmethod
    def _embed_substituent_3d(smiles: str):
        """取代基 SMILES（恰好一个 ``[*]`` 假原子标记连接点）→ 力场优化过的 3D 片段。

        返回 ``(symbols, coords, attach_idx, bond_order, out_dir)``：
        ``symbols``/``coords`` 不含假原子和"连接氢"；``attach_idx`` 是连接原子在返回数组中的
        局部索引；``out_dir`` 是连接原子指向被删连接氢的单位向量——即片段朝"核心一侧"的方向，
        对接时对齐到旧键方向的反向。所有失败一律 fail-loud。
        """
        import numpy as np
        from rdkit import Chem
        from rdkit.Chem import AllChem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"replace_group: invalid substituent SMILES {smiles!r}")
        dummies = [at.GetIdx() for at in mol.GetAtoms() if at.GetAtomicNum() == 0]
        if len(dummies) != 1:
            raise ValueError(
                f"replace_group: substituent SMILES must contain exactly one [*] dummy atom "
                f"marking the attachment point, got {len(dummies)}"
            )
        dummy_neighbors = mol.GetAtomWithIdx(dummies[0]).GetNeighbors()
        if len(dummy_neighbors) != 1:
            raise ValueError("replace_group: the [*] dummy atom must have exactly one bond (the attachment)")
        attach_heavy = dummy_neighbors[0].GetIdx()
        bond_order = float(mol.GetBondBetweenAtoms(dummies[0], attach_heavy).GetBondTypeAsDouble())

        rw = Chem.RWMol(mol)
        rw.RemoveAtom(dummies[0])
        frag = rw.GetMol()
        attach_local = attach_heavy - 1 if attach_heavy > dummies[0] else attach_heavy
        # RemoveAtom 后必须重算隐式氢（去掉假原子空出的价态才会被 AddHs 补成氢），
        # 并重建 RingInfo（UpdatePropertyCache 不负责，后续嵌入/力场会用到）。
        frag.UpdatePropertyCache(strict=False)
        Chem.FastFindRings(frag)
        frag = Chem.AddHs(frag)
        # 连接原子因去掉假原子空出的价态由 AddHs 补氢；这些氢彼此等价，任取其一标记
        # "朝核心一侧"的方向即可（替掉哪个氢化学上是同一个分子）。连接原子无氢可替说明
        # 价态本已饱和，无从对接，fail-loud。
        h_neighbors = [nb.GetIdx() for nb in frag.GetAtomWithIdx(attach_local).GetNeighbors()
                       if nb.GetAtomicNum() == 1]
        if not h_neighbors:
            raise ValueError(
                "replace_group: the attachment atom has no hydrogen to vacate after removing [*] "
                "(its valence is saturated by other substituents)"
            )
        marker_h = h_neighbors[0]

        params = AllChem.ETKDGv3()
        params.randomSeed = 20260914
        if AllChem.EmbedMolecule(frag, params) != 0:
            raise ValueError(f"replace_group: 3D embedding failed for substituent {smiles!r}")
        if AllChem.MMFFHasAllMoleculeParams(frag):
            AllChem.MMFFOptimizeMolecule(frag)
        elif AllChem.UFFHasAllMoleculeParams(frag):
            AllChem.UFFOptimizeMolecule(frag)
        else:
            raise ValueError(f"replace_group: no MMFF/UFF force-field parameters for substituent {smiles!r}")

        coords = np.asarray(frag.GetConformer().GetPositions(), dtype=float)
        out_vec = coords[marker_h] - coords[attach_local]
        norm = float(np.linalg.norm(out_vec))
        if norm < 1e-9:
            raise ValueError("replace_group: degenerate substituent geometry (attachment hydrogen coincides with the attachment atom)")
        out_dir = out_vec / norm

        keep = [i for i in range(frag.GetNumAtoms()) if i != marker_h]
        symbols = [frag.GetAtomWithIdx(i).GetSymbol() for i in keep]
        attach_idx = keep.index(attach_local)
        return symbols, coords[keep], attach_idx, bond_order, out_dir

    @classmethod
    def _op_replace_group(cls, op: dict, symbols: list[str], positions, adj: dict[int, set[int]], n: int):
        """拓扑编辑 op：切断 bond a-b、移除 b 侧片段、把 SMILES 新基团对接到 a 上。

        与刚性 op 不同，它不改坐标数组而是返回 ``(summary, new_symbols, new_positions)``；
        新结构的原子顺序 = 存活者原序 + 新基团追加，调用方负责重建邻接表。
        """
        import numpy as np

        bond_raw = op.get("bond")
        if not (isinstance(bond_raw, list) and len(bond_raw) == 2):
            raise ValueError(
                "replace_group requires bond: [a, b] (1-based bonded pair; the fragment on the "
                "b side is removed and the new group attaches to a)"
            )
        a = cls._transform_atom_index(bond_raw[0], n, "replace_group bond")
        b = cls._transform_atom_index(bond_raw[1], n, "replace_group bond")
        if a == b:
            raise ValueError("replace_group bond atoms must be distinct")
        if b not in adj.get(a, set()):
            raise ValueError(f"replace_group: atoms {a + 1} and {b + 1} are not bonded")
        removed = cls._bfs_group(cls._adjacency_without_edge(adj, a, b), b)
        if a in removed:
            raise ValueError(
                f"replace_group: bond {a + 1}-{b + 1} lies on a ring (the graph stays connected "
                "after cutting it); cannot cut it for substitution"
            )

        smiles = op.get("smiles")
        if not isinstance(smiles, str) or not smiles.strip():
            raise ValueError(
                "replace_group requires 'smiles': the new substituent with exactly one [*] dummy "
                "atom marking the attachment point (e.g. '[*]C(=O)O')"
            )
        frag_symbols, frag_coords, attach_idx, bond_order, out_dir = cls._embed_substituent_3d(smiles.strip())

        vec = positions[b] - positions[a]
        old_len = float(np.linalg.norm(vec))
        if old_len < 1e-9:
            raise ValueError(
                f"replace_group: atoms {a + 1} and {b + 1} coincide; the attachment direction is undefined"
            )
        v_hat = vec / old_len
        new_len = cls._reference_bond_length(symbols[a], frag_symbols[attach_idx], bond_order)

        # out_dir 在片段内是 b′→核心方向；目标构型中它必须指向 a，即 -v_hat。
        rot = rotation_matrix_between(out_dir, -v_hat)
        frag_placed = frag_coords @ rot.T
        frag_placed = frag_placed - frag_placed[attach_idx] + positions[a] + new_len * v_hat

        survivors = [i for i in range(n) if i not in removed]
        new_symbols = [symbols[i] for i in survivors] + list(frag_symbols)
        new_positions = np.vstack([positions[survivors], frag_placed])
        n_after = len(new_symbols)
        first_new = n_after - len(frag_symbols)  # 0-based
        summary = {
            "type": "replace_group",
            "bond": [a + 1, b + 1],
            "smiles": smiles.strip(),
            "bond_order": bond_order,
            "attachment_atoms": [a + 1, first_new + attach_idx + 1],
            "removed_atoms": sorted(x + 1 for x in removed),
            "n_removed": len(removed),
            "n_added": len(frag_symbols),
            "n_atoms_before": n,
            "n_atoms_after": n_after,
        }
        return summary, new_symbols, new_positions

    @classmethod
    def _apply_transform_op(cls, op, positions, adj: dict[int, set[int]], n: int) -> dict:
        """在 positions（调用方持有的 numpy 副本）上原地应用一个 op，返回该 op 的摘要。"""
        if not isinstance(op, dict):
            raise ValueError(f"each transform operation must be an object, got {type(op).__name__}")
        op_type = op.get("type")
        if op_type == "rotate":
            return cls._op_rotate(op, positions, adj, n)
        if op_type == "stretch":
            return cls._op_stretch(op, positions, adj, n)
        if op_type == "invert_chirality":
            return cls._op_invert_chirality(op, positions, adj, n)
        raise ValueError(
            f"unknown transform operation type {op_type!r}; supported types: "
            "'rotate', 'stretch', 'invert_chirality', 'replace_group'"
        )

    @staticmethod
    def _transform_summary_line(k: int, s: dict) -> str:
        if s["type"] == "rotate":
            return (f"{k}. rotate {s['degrees']:g}° about axis atoms "
                    f"{s['axis_atoms'][0]}-{s['axis_atoms'][1]} ({s['selection']}): "
                    f"moved {s['n_moved']} atoms")
        if s["type"] == "stretch":
            return (f"{k}. stretch bond {s['atoms'][0]}-{s['atoms'][1]} "
                    f"{s['old_length']:.3f} -> {s['new_length']:.3f} Å: moved {s['n_moved']} atoms")
        if s["type"] == "replace_group":
            return (f"{k}. replace_group on bond {s['bond'][0]}-{s['bond'][1]}: removed "
                    f"{s['n_removed']} atoms, attached {s['smiles']} ({s['n_added']} atoms, "
                    f"bond order {s['bond_order']:g}, new bond {s['attachment_atoms'][0]}-"
                    f"{s['attachment_atoms'][1]}); atoms {s['n_atoms_before']} -> {s['n_atoms_after']}")
        return (f"{k}. invert_chirality at center {s['center']} "
                f"(swap {s['swap'][0]}/{s['swap'][1]}): moved {s['n_moved']} atoms")

    def _transform(self, user_input: InternalCoordinates_input_schema) -> InternalCoordinates_output_schema:
        import numpy as np

        if not user_input.operations:
            return InternalCoordinates_output_schema(
                is_success=False,
                message=(
                    "mode=transform requires 'operations': a non-empty list of transform operations "
                    "({'type': 'rotate'|'stretch'|'invert_chirality'|'replace_group', ...})"
                ),
            )
        try:
            atoms = self._load_atoms_from_path_or_text(
                user_input.input_path, user_input.input_text, user_input.input_format,
            )
        except Exception as e:
            return InternalCoordinates_output_schema(is_success=False, message=f"Failed to read input structure: {e}")

        symbols = atoms.get_chemical_symbols()
        positions = np.asarray(atoms.get_positions(), dtype=float)
        n = len(symbols)
        notes: list[str] = []

        if _RDKIT_AVAILABLE:
            try:
                _, bond_orders = self._perceive_bonds_rdkit(
                    self._atoms_to_xyz_block(atoms), user_input.charge,
                )
            except Exception as e:
                bond_orders = self._distance_connectivity(symbols, positions)
                notes.append(f"RDKit bond perception failed ({e}); bond orders were not perceived — bonds are distance-inferred (all treated as single bonds).")
        else:
            bond_orders = self._distance_connectivity(symbols, positions)
            notes.append("RDKit is not installed; bond orders were not perceived — bonds are distance-inferred (all treated as single bonds).")

        adj = self._build_adjacency(n, bond_orders)
        before_bonds, _ = self._abnormal_bonds(
            symbols, positions, adj, bond_orders, user_input.bond_tolerance,
        )
        before_angles, _ = self._abnormal_angles(
            symbols, positions, adj, bond_orders, user_input.angle_tolerance,
        )
        anomalies_before = before_bonds + before_angles

        # 图划分与校验都用初始键感知拓扑：刚性 transform op（rotate/stretch/invert_chirality）
        # 共价拓扑不变；对新坐标重新感知会把被拉断的键/新接触静默改写成分子身份的一部分，校验失去意义。
        # replace_group 是有意的拓扑编辑：它之后的 op 与最终校验改用替换后重新感知的拓扑。
        from ase import Atoms

        work = positions.copy()
        cur_symbols = list(symbols)
        cur_n = n
        cur_bond_orders = bond_orders
        cur_adj = adj
        adj_sets = {i: set(adj[i]) for i in range(n)}
        summaries: list[dict] = []
        try:
            for op in user_input.operations:
                if isinstance(op, dict) and op.get("type") == "replace_group":
                    summary, cur_symbols, work = self._op_replace_group(
                        op, cur_symbols, work, adj_sets, cur_n,
                    )
                    cur_n = len(cur_symbols)
                    if _RDKIT_AVAILABLE:
                        try:
                            _, cur_bond_orders = self._perceive_bonds_rdkit(
                                self._atoms_to_xyz_block(Atoms(symbols=cur_symbols, positions=work)),
                                user_input.charge,
                            )
                        except Exception as e:
                            cur_bond_orders = self._distance_connectivity(cur_symbols, work)
                            notes.append(f"RDKit bond perception failed on the substituted structure ({e}); bonds after the replacement are distance-inferred (all treated as single bonds).")
                    else:
                        cur_bond_orders = self._distance_connectivity(cur_symbols, work)
                    cur_adj = self._build_adjacency(cur_n, cur_bond_orders)
                    adj_sets = {i: set(cur_adj[i]) for i in range(cur_n)}
                    summaries.append(summary)
                else:
                    summaries.append(self._apply_transform_op(op, work, adj_sets, cur_n))
        except ValueError as e:
            return InternalCoordinates_output_schema(is_success=False, message=f"Invalid transform operation: {e}")

        after_bonds, after_bond_lines = self._abnormal_bonds(
            cur_symbols, work, cur_adj, cur_bond_orders, user_input.bond_tolerance,
        )
        after_angles, after_angle_lines = self._abnormal_angles(
            cur_symbols, work, cur_adj, cur_bond_orders, user_input.angle_tolerance,
        )
        anomalies_after = after_bonds + after_angles
        reactive_lines: list[str] = []
        if user_input.reactive_atoms or user_input.watch_pairs:
            reactive_lines = self._reactive_center_report(
                cur_symbols, work, cur_adj, cur_bond_orders,
                user_input.reactive_atoms, user_input.watch_pairs,
            )

        report: list[str] = ["== Operations Applied =="]
        for k, s in enumerate(summaries, start=1):
            report.append("  " + self._transform_summary_line(k, s))
        report.append("== Validation After Transform ==")
        report.append(f"  Bond anomalies: {len(after_bonds)}  Angle anomalies: {len(after_angles)}")
        report.append("  [Abnormal Bonds]")
        report.extend(after_bond_lines if after_bond_lines
                      else ["  No abnormal bond lengths (normal bonds are not listed)"])
        report.append("  [Abnormal Angles]")
        report.extend(after_angle_lines if after_angle_lines
                      else [f"  No bond angles deviating by more than {user_input.angle_tolerance:.1f}°"])
        if user_input.reactive_atoms or user_input.watch_pairs:
            report.append("  [Reactive Center]")
            report.extend(reactive_lines if reactive_lines else ["  (no valid input)"])
        before_keys = {(a["type"], tuple(a["atoms"]), a["status"]) for a in anomalies_before}
        after_keys = {(a["type"], tuple(a["atoms"]), a["status"]) for a in anomalies_after}
        new_count = len(after_keys - before_keys)
        resolved_count = len(before_keys - after_keys)
        report.append("== Transform Comparison ==")
        report.append(f"  Anomalies before transform: {len(anomalies_before)}  after: {len(anomalies_after)}")
        report.append(f"  New anomalies introduced: {new_count}  anomalies resolved: {resolved_count}")
        if notes:
            report.append("== Notes ==")
            report.extend(f"  - {t}" for t in notes)

        xyz_text = self._atoms_to_xyz_block(Atoms(symbols=cur_symbols, positions=work))
        output_path = ""
        if user_input.output_path:
            os.makedirs(os.path.dirname(user_input.output_path) or ".", exist_ok=True)
            atomic_write_text(user_input.output_path, xyz_text)
            output_path = user_input.output_path

        message = (
            f"Applied {len(summaries)} transform operation(s). Validation after transform: "
            f"{len(after_bonds)} bond anomalies, {len(after_angles)} angle anomalies "
            f"(before: {len(before_bonds)} bond, {len(before_angles)} angle); "
            f"{new_count} new, {resolved_count} resolved."
        )
        if output_path:
            message += f" Transformed coordinates written to {output_path}."
        return InternalCoordinates_output_schema(
            is_success=True,
            report="\n".join(report),
            anomalies=anomalies_after,
            operations_applied=summaries,
            anomalies_before=anomalies_before,
            xyz_text=xyz_text,
            output_path=output_path,
            message=message,
        )

    # ---------- Z-matrix -> Cartesian ----------

    @staticmethod
    def _zmat_symbol_from_label(label: str) -> str:
        """从原子标签取元素符号（``C12`` → ``C``，``Cl3`` → ``Cl``）。

        只剥尾部的十进制数字，不做任何模式匹配；剥完不是纯字母即拒绝——标签必须真的以
        元素符号开头，否则后续按元素算键长/半径时会静默用错元素。
        """
        end = len(label)
        while end > 0 and label[end - 1].isdigit():
            end -= 1
        symbol = label[:end]
        if not symbol or not symbol.isalpha():
            raise ValueError(
                f"Z-matrix atom label {label!r} does not start with an element symbol"
            )
        return symbol

    @staticmethod
    def _zmat_number(token: str, context: str) -> float:
        """逐 token 数值校验：必须可解析为**有限**浮点数，NaN/Inf 一律拒绝。"""
        try:
            value = float(token)
        except ValueError as exc:
            raise ValueError(f"{context}: {token!r} is not a number") from exc
        if not math.isfinite(value):
            raise ValueError(f"{context}: {token!r} is not a finite number")
        return value

    @staticmethod
    def _parse_zmatrix_text(zmatrix_text: str) -> pd.DataFrame:
        """结构化解析 Z-matrix 文本（逐 token 校验，本模块不含正则）。

        接受的格式与 ``_render_zmatrix`` 的输出一致::

            1  C1     | origin  r=0.0000  | e_z     a=0.00  | e_x     d=-0.00

        校验规则（全部 fail-loud，绝不静默补零/猜测）：

        - 数据行形如 ``<序号> <标签>`` 后跟最多三段 ``| <父原子> <key>=<数值>``；
          ``key`` 必须是 ``r``/``a``/``d`` 且与所在段位置一致。
        - 序号是**原始原子序号**（不要求 1..N 连续，生成器按构造顺序打印），但必须为正且唯一；
          标签内部编号必须与序号一致（生成器如此打印，手写输入也照此校验）。
        - 父原子只能是 magic 绝对参考（origin/e_x/e_y/e_z）、**前面已声明**行的标签、或该行的序号。
          未知引用、引用自身或引用后面的行一律拒绝。
        - 数值必须有限。
        - **合法绝对参考规则**：只允许文件前三个数据行按位置省略参考——
          第 1 行可省 b/a/d（补 origin/e_z/e_x），第 2 行可省 a/d（补 e_z/e_x），
          第 3 行可省 d（补 e_x）。第 4 行起缺任何一个父原子或数值都是**非法缺字段**，直接报错。

        行索引：1-based 原子序号（Z-matrix 顺序），经 chemcoord 的 ``index`` 语义。
        """
        import pandas as pd

        data_lines = [
            line.strip() for line in zmatrix_text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not data_lines:
            raise ValueError("the Z-matrix text contains no data lines")

        #: 按行位置允许省略的绝对参考（唯一合法的省略位置）
        absolute_defaults = {
            1: {"r": "origin", "a": "e_z", "d": "e_x"},
            2: {"a": "e_z", "d": "e_x"},
            3: {"d": "e_x"},
        }

        records: list[dict] = []
        label_to_index: dict[str, int] = {}
        seen_indices: set[int] = set()

        for position, line in enumerate(data_lines, start=1):
            segments = [segment.strip() for segment in line.split("|")]
            head = segments[0].split()
            if len(head) != 2:
                raise ValueError(
                    f"Z-matrix data line {position} ({line!r}): expected '<index> <label>' "
                    "before the first '|'"
                )
            try:
                atom_index = int(head[0])
            except ValueError as exc:
                raise ValueError(
                    f"Z-matrix data line {position}: {head[0]!r} is not an integer atom index"
                ) from exc
            if atom_index < 1:
                raise ValueError(
                    f"Z-matrix data line {position}: atom index must be >= 1, got {atom_index}"
                )
            if atom_index in seen_indices:
                raise ValueError(
                    f"Z-matrix data line {position}: duplicate atom index {atom_index}"
                )
            label = head[1]
            if label in label_to_index:
                raise ValueError(f"Z-matrix data line {position}: duplicate atom label {label!r}")
            symbol = InternalCoordinates._zmat_symbol_from_label(label)
            if label[len(symbol):] and int(label[len(symbol):]) != atom_index:
                raise ValueError(
                    f"Z-matrix data line {position}: label {label!r} disagrees with the row index "
                    f"{atom_index}; the label must be <element><row index>"
                )

            allowed_defaults = absolute_defaults.get(position, {})
            parents: dict[str, str] = {}
            values: dict[str, float] = {}

            for key_position, key in enumerate(("r", "a", "d")):
                segment = segments[key_position + 1] if key_position + 1 < len(segments) else ""
                tokens = segment.split()
                if len(tokens) > 2:
                    raise ValueError(
                        f"Z-matrix data line {position}: segment {segment!r} has more than a "
                        "parent atom and one '<key>=<value>' pair"
                    )
                parent = ""
                value_token = ""
                if len(tokens) == 2:
                    parent, value_token = tokens
                elif len(tokens) == 1:
                    if "=" in tokens[0]:
                        value_token = tokens[0]
                    else:
                        parent = tokens[0]

                if value_token:
                    prefix, separator, raw_value = value_token.partition("=")
                    if separator != "=" or prefix != key:
                        raise ValueError(
                            f"Z-matrix data line {position}: segment {key_position + 1} must be "
                            f"'{key}=<number>', got {value_token!r}"
                        )
                    values[key] = InternalCoordinates._zmat_number(
                        raw_value, f"Z-matrix data line {position} '{key}=' value",
                    )
                elif key in allowed_defaults:
                    values[key] = 0.0
                else:
                    raise ValueError(
                        f"Z-matrix data line {position} (atom {atom_index}) is missing '{key}='; "
                        "only the first three data lines may omit absolute references"
                    )

                if parent:
                    parents[key] = parent
                elif key in allowed_defaults:
                    parents[key] = allowed_defaults[key]
                else:
                    raise ValueError(
                        f"Z-matrix data line {position} (atom {atom_index}) is missing the parent "
                        f"atom for '{key}='; only the first three data lines may omit it"
                    )

            resolved: dict[str, str] = {}
            for key in ("r", "a", "d"):
                parent = parents[key]
                if parent in _MAGIC_REFS:
                    resolved[key] = parent
                    continue
                if parent in label_to_index:
                    resolved[key] = str(label_to_index[parent])
                    continue
                if parent.isdigit() and int(parent) in seen_indices:
                    resolved[key] = str(int(parent))
                    continue
                raise ValueError(
                    f"Z-matrix data line {position} (atom {atom_index}): parent reference "
                    f"{parent!r} for '{key}=' is unknown — it is not a magic reference "
                    f"({', '.join(_MAGIC_REFS)}), not a label declared on an earlier line, and not "
                    "an earlier row index"
                )

            records.append({
                "index": atom_index,
                "atom": symbol,
                "b": resolved["r"],
                "bond": values["r"],
                "a": resolved["a"],
                "angle": values["a"],
                "d": resolved["d"],
                "dihedral": values["d"],
            })
            label_to_index[label] = atom_index
            seen_indices.add(atom_index)

        frame = pd.DataFrame(records).set_index("index")
        for column in ("atom", "b", "a", "d"):
            frame[column] = frame[column].astype(object)
        return frame

    @staticmethod
    def _zmat_dataframe_to_xyz(zmat_frame: pd.DataFrame) -> str:
        """
        从 Z-matrix DataFrame 逐行重建笛卡尔坐标（与 chemcoord get_X 同一套
        变换语义，但不走其只读数组路径）。d 参考与 a-b 轴共线时二面角数学上
        未定义——此时绕 a-b 轴旋转任意，换成第一个非共线的 magic 参考
        （e_x/e_y/e_z）继续重建，与 analyze 方向的 _fix_collinear_dihedral_refs
        处理一致；只有 b 与 a 位置重合才是真正无效的参考。
        """
        import numpy as np
        import pandas as pd

        dummy = {
            'origin': np.zeros(3), 'e_x': np.array([1.0, 0.0, 0.0]),
            'e_y': np.array([0.0, 1.0, 0.0]), 'e_z': np.array([0.0, 0.0, 1.0]),
        }

        # 父原子与数值由 _parse_zmatrix_text 逐 token 校验后保证齐全（合法的绝对参考
        # 省略已在解析阶段按位置补成 origin/e_z/e_x），因此这里**不做**任何默认填充：
        # 出现 NaN 说明上游解析被绕过，必须报错而不是静默当 origin。
        c_table = zmat_frame.loc[:, ['b', 'a', 'd']].copy()

        name_to_col = {idx: col for col, idx in enumerate(zmat_frame.index)}

        def to_ref(x):
            if not pd.notna(x):
                raise ValueError(
                    "Z-matrix reference atom is missing (NaN); the parser must resolve every "
                    "parent reference before coordinates are rebuilt"
                )
            text = str(x)
            if text in dummy:
                return text
            try:
                col = name_to_col.get(int(text), -1)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Could not parse reference atom: {text}") from exc
            if col < 0:
                raise ValueError(f"Could not parse reference atom: {text}")
            return col

        n = len(zmat_frame)
        positions = np.zeros((n, 3))
        values = zmat_frame.loc[:, ['bond', 'angle', 'dihedral']].to_numpy(dtype=float)

        for j in range(n):
            b_ref = to_ref(c_table.iloc[j]['b'])
            a_ref = to_ref(c_table.iloc[j]['a'])
            d_ref = to_ref(c_table.iloc[j]['d'])

            def pos(ref):
                return dummy[ref] if isinstance(ref, str) else positions[ref]

            pb, pa = pos(b_ref), pos(a_ref)
            ba = pa - pb
            norm_ba = np.linalg.norm(ba)
            if norm_ba < 1e-9:
                raise ValueError(
                    f"Z-matrix row {j + 1}: bond-length and bond-angle references coincide; cannot define a coordinate frame"
                )
            normal = np.cross(pos(d_ref) - pa, ba)
            if np.linalg.norm(normal) < 1e-9:
                # d-a-b 共线：二面角未定义，换非共线的 magic 参考（旋转任意）
                for cand in ('e_x', 'e_y', 'e_z'):
                    normal = np.cross(dummy[cand] - pa, ba)
                    if np.linalg.norm(normal) >= 1e-9:
                        break
            basis = np.empty((3, 3))
            basis[:, 2] = -ba / norm_ba
            basis[:, 1] = normal / np.linalg.norm(normal)
            basis[:, 0] = np.cross(basis[:, 1], basis[:, 2])

            r, alpha, delta = values[j]
            alpha, delta = np.radians(alpha), np.radians(delta)
            if np.isclose(alpha, np.pi):
                s = np.array([0.0, 0.0, r])
            elif np.isclose(alpha, 0.0):
                s = np.array([0.0, 0.0, -r])
            else:
                s = np.array([
                    r * np.sin(alpha) * np.cos(delta),
                    -r * np.sin(alpha) * np.sin(delta),
                    -r * np.cos(alpha),
                ])
            positions[j] = basis @ s + pb

        # 按原始原子序号（index）排序输出 xyz
        ordered = sorted(zip(zmat_frame.index, zmat_frame['atom'], positions), key=lambda x: x[0])

        xyz_lines = [str(len(zmat_frame)), "Generated from Z-matrix"]
        for idx, sym, p in ordered:
            xyz_lines.append(f"{str(sym):<4} {p[0]:>14.8f} {p[1]:>14.8f} {p[2]:>14.8f}")

        return "\n".join(xyz_lines) + "\n"

    def _zmatrix_to_cartesian(self, user_input: InternalCoordinates_input_schema) -> InternalCoordinates_output_schema:
        zmatrix_text = None
        if user_input.zmatrix_path:
            # 与 analyze/format_converter/log_parser 同一套路径语义：相对路径解析到 agent 工作
            # 目录；读取失败时报出**解析后的目标**与具体错误，绝不把"文件不存在"说成"没给参数"。
            target = resolve_tool_path(self, user_input.zmatrix_path)
            try:
                with open(target, encoding="utf-8") as f:
                    zmatrix_text = f.read()
            except OSError as e:
                return InternalCoordinates_output_schema(
                    is_success=False,
                    message=(
                        f"Failed to read the Z-matrix file at the resolved path {target!r} "
                        f"(requested zmatrix_path={user_input.zmatrix_path!r}): "
                        f"{type(e).__name__}: {e}"
                    ),
                )
        elif user_input.zmatrix_text:
            zmatrix_text = user_input.zmatrix_text

        if not zmatrix_text:
            return InternalCoordinates_output_schema(
                is_success=False,
                message=(
                    "mode=zmatrix_to_cartesian requires zmatrix_path or zmatrix_text; neither was "
                    f"provided (zmatrix_path={user_input.zmatrix_path!r}, "
                    f"zmatrix_text={'set' if user_input.zmatrix_text else 'unset'})"
                )
            )

        try:
            zmat_frame = self._parse_zmatrix_text(zmatrix_text)
            xyz_text = self._zmat_dataframe_to_xyz(zmat_frame)

            output_path = ""
            if user_input.output_path:
                os.makedirs(os.path.dirname(user_input.output_path) or ".", exist_ok=True)
                atomic_write_text(user_input.output_path, xyz_text)
                output_path = user_input.output_path

            return InternalCoordinates_output_schema(
                is_success=True,
                xyz_text=xyz_text,
                output_path=output_path,
                message="Cartesian coordinates generated from Z-matrix."
            )
        except Exception as e:
            import traceback
            return InternalCoordinates_output_schema(
                is_success=False,
                message=f"Failed to convert Z-matrix to coordinates: {e}\n{traceback.format_exc()}"
            )

    async def tool_call(self, user_input: InternalCoordinates_input_schema, session: Session) -> InternalCoordinates_output_schema:
        # 路径语义收口：文件路径字段的相对路径统一解析到 agent 工作目录（沙箱）；
        # 绝对路径保持既有权限语义。zmatrix_text/input_text 是文本，不做路径解析。
        user_input = user_input.model_copy(
            update={
                field: resolve_tool_path(self, value)
                for field, value in {
                    "input_path": user_input.input_path,
                    "zmat_path": user_input.zmat_path,
                    "zmatrix_path": user_input.zmatrix_path,
                    "output_path": user_input.output_path,
                }.items()
                if value
            }
        )
        if not _CHEMCOORD_AVAILABLE:
            return InternalCoordinates_output_schema(
                is_success=False,
                message="chemcoord is not installed. Install it with: pip install 'cloudra[chem]'"
            )
        if user_input.operations and user_input.mode != "transform":
            return InternalCoordinates_output_schema(
                is_success=False,
                message="'operations' is only valid with mode=transform",
            )
        if user_input.mode == "analyze":
            # chemcoord 解析/分析是同步重活，卸载出事件循环。
            return await asyncio.to_thread(self._analyze, user_input)
        if user_input.mode == "transform":
            return await asyncio.to_thread(self._transform, user_input)
        return self._zmatrix_to_cartesian(user_input)


def get_class():
    return InternalCoordinates
