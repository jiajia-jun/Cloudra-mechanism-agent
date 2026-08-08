from __future__ import annotations

import os
import re
from io import StringIO
from typing import TYPE_CHECKING, Any, Literal, Optional

from pydantic import Field

if TYPE_CHECKING:
    # 仅用于类型注解；运行时在使用点惰性导入。
    import pandas as pd

from cloudra.fs_utils import atomic_write_text
from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

try:
    import chemcoord as cc
    _CHEMCOORD_AVAILABLE = True
except Exception:
    cc = None
    _CHEMCOORD_AVAILABLE = False

_COVALENT_RADII = {
    'H': 0.31, 'He': 0.28,
    'Li': 1.28, 'Be': 0.96, 'B': 0.84, 'C': 0.76, 'N': 0.71, 'O': 0.66, 'F': 0.57, 'Ne': 0.58,
    'Na': 1.66, 'Mg': 1.41, 'Al': 1.21, 'Si': 1.11, 'P': 1.07, 'S': 1.05, 'Cl': 1.02, 'Ar': 1.06,
    'K': 2.03, 'Ca': 1.76, 'Sc': 1.70, 'Ti': 1.60, 'V': 1.53, 'Cr': 1.39, 'Mn': 1.39,
    'Fe': 1.32, 'Co': 1.26, 'Ni': 1.24, 'Cu': 1.32, 'Zn': 1.22, 'Ga': 1.22, 'Ge': 1.20,
    'As': 1.19, 'Se': 1.20, 'Br': 1.20, 'Kr': 1.16,
    'Rb': 2.20, 'Sr': 1.95, 'Y': 1.90, 'Zr': 1.75, 'Nb': 1.64, 'Mo': 1.54, 'Tc': 1.47,
    'Ru': 1.46, 'Rh': 1.42, 'Pd': 1.39, 'Ag': 1.45, 'Cd': 1.44, 'In': 1.42, 'Sn': 1.39,
    'Sb': 1.39, 'Te': 1.38, 'I': 1.39, 'Xe': 1.40,
}

description = (
    "在笛卡尔坐标（xyz/mol/pdb/ase 等）与内坐标（Z-matrix）之间相互转换，"
    "并自动检测异常键长（过长/过短/缺失），以大模型易于理解的格式输出。"
    "适用：过渡态搜索、结构扫描等任务中识别关键反应坐标、检查结构合理性。"
    "不适用：单纯的文件格式转换（用 format_converter）、提取能量与性质（用 log_parser）。"
)


class InternalCoordinates_input_schema(input_schema):
    mode: Literal["cartesian_to_zmatrix", "zmatrix_to_cartesian"] = Field(
        description="转换模式。cartesian_to_zmatrix：从文件/文本提取笛卡尔坐标并生成 Z-matrix；"
                    "zmatrix_to_cartesian：从 Z-matrix 文本生成笛卡尔坐标文件。"
    )
    input_path: Optional[str] = Field(
        default=None,
        description="输入文件路径（xyz/mol/pdb/sdf/cif 等，ASE 可读）。mode=cartesian_to_zmatrix 时使用。"
    )
    input_text: Optional[str] = Field(
        default=None,
        description="直接传入坐标文本。若提供 input_path 则优先读取文件。"
    )
    input_format: Literal["auto", "xyz", "mol", "pdb", "sdf", "cif"] = Field(
        default="auto",
        description="笛卡尔坐标输入格式。auto 时由 ASE 根据文件扩展名推断。"
    )
    zmatrix_text: Optional[str] = Field(
        default=None,
        description="mode=zmatrix_to_cartesian 时使用的 Z-matrix 文本。"
    )
    output_path: Optional[str] = Field(
        default=None,
        description="输出文件路径。cartesian_to_zmatrix 时保存 Z-matrix 文本；"
                    "zmatrix_to_cartesian 时保存 xyz 文件。"
    )
    anomaly_threshold_low: float = Field(
        default=0.4,
        description="键长异常下限系数。若某键长 < 该系数 * 标准共价半径和，则标记为过短。默认 0.4，避免正常化学键（如 C-H ~1.09 Å）被误标。"
    )
    anomaly_threshold_high: float = Field(
        default=2.0,
        description="键长异常上限系数。若某键长 > 该系数 * 标准共价半径和，则标记为过长/可疑。默认 2.0，用于捕捉过渡态中正在断裂或形成的键。"
    )
    highlight_breaking_forming: bool = Field(
        default=True,
        description="是否在输出中突出显示可疑键长（过渡态中正在断裂或形成的键）。"
    )


class InternalCoordinates_output_schema(output_schema):
    is_success: bool = Field(description="转换是否成功")
    zmatrix_text: str = Field(default="", description="mode=cartesian_to_zmatrix 时返回的 Z-matrix 文本")
    xyz_text: str = Field(default="", description="mode=zmatrix_to_cartesian 时返回的 xyz 文本")
    output_path: str = Field(default="", description="若写入了文件，返回文件路径")
    anomalies: list[dict] = Field(default_factory=list, description="检测到的异常键长列表")
    message: str = Field(default="", description="状态或错误信息")


class InternalCoordinates(Tool):
    tool_id: str = 't-31'
    tool_name: str = 'internal_coordinates'
    tool_description: str = description
    input_schema: Any = InternalCoordinates_input_schema
    output_schema: Any = InternalCoordinates_output_schema

    def is_write(self) -> bool:
        return True

    @classmethod
    def _covalent_radius(cls, symbol: str) -> float:
        return _COVALENT_RADII.get(symbol, 1.2)

    @classmethod
    def _expected_bond_length(cls, sym_i: str, sym_j: str) -> float:
        """两个原子间的经验共价键长上限（Cordero 共价半径和）。"""
        return cls._covalent_radius(sym_i) + cls._covalent_radius(sym_j)

    @staticmethod
    def _van_der_waals_sum(sym_i: str, sym_j: str) -> float:
        """两个原子的范德华半径和，用于判断非键距离。来源：Bondi, J. Phys. Chem. 1964，单位 Å。"""
        vdw = {
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
        return vdw.get(sym_i, 1.7) + vdw.get(sym_j, 1.7)

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

        raise ValueError("必须提供 input_path 或 input_text")

    @classmethod
    def _build_connectivity(cls, atoms,
                            threshold_low: float = 0.6,
                            threshold_high: float = 2.0) -> list[tuple[int, int, float, float, str]]:
        """
        基于共价半径和简单距离判据构建连接表。
        返回 [(i, j, distance, expected_bond_length, status), ...]
        其中 status 为 'normal' / 'too_short' / 'too_long' / 'missing'
        """
        import numpy as np

        positions = atoms.get_positions()
        symbols = atoms.get_chemical_symbols()
        n = len(atoms)
        bonds = []

        for i in range(n):
            for j in range(i + 1, n):
                r = np.linalg.norm(positions[i] - positions[j])
                expected_bond = cls._expected_bond_length(symbols[i], symbols[j])
                vdw_sum = cls._van_der_waals_sum(symbols[i], symbols[j])

                if r < threshold_low * expected_bond:
                    status = "too_short"
                elif r > threshold_high * expected_bond:
                    status = "missing"
                elif r > 1.3 * expected_bond:
                    status = "too_long"
                else:
                    status = "normal"

                # 保留真正可能成键/相互作用的对：
                # 1. 预期单键范围内；2. 弱相互作用候选；3. 过渡态可疑长键
                if (r <= 1.3 * expected_bond
                        or r <= 0.55 * vdw_sum
                        or (status == "too_long" and r <= threshold_high * expected_bond)):
                    bonds.append((i, j, float(r), float(expected_bond), status))

        return bonds

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
    def _build_zmat_dataframe(cart: "cc.Cartesian", c_table: pd.DataFrame) -> pd.DataFrame:
        """
        绕开 chemcoord 2.1.2 与新版 pandas/string-dtype 的兼容 bug：
        _build_zmat 用 np.empty(..., dtype=str) 创建列，无法接受 mixed int/str 的 construction table。
        这里显式用 object dtype 构造 Zmat DataFrame。
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
        zmat_frame.loc[:, ['b', 'a', 'd']] = c_table.astype(str)

        values = cart._calculate_zmat_values(c_table)
        zmat_frame.loc[:, ['bond', 'angle', 'dihedral']] = values
        return zmat_frame

    @classmethod
    def _render_zmatrix(cls, zmat_frame: pd.DataFrame,
                        atoms,
                        bonds: list[tuple[int, int, float, float, str]]) -> str:
        """渲染成大模型友好的 Z-matrix 文本，并标注异常键长。父原子用原子名（如 C2）表示，便于反向解析。"""
        import pandas as pd

        bond_status_by_pair = {}
        for i, j, _, _, status in bonds:
            bond_status_by_pair[(i, j)] = status
            bond_status_by_pair[(j, i)] = status

        # index (1-based) -> atom name
        idx_to_name = {idx: f"{row['atom']}{idx}" for idx, row in zmat_frame.iterrows()}
        name_to_index = {name: idx - 1 for idx, name in idx_to_name.items()}

        def format_parent(x):
            s = str(x) if pd.notna(x) else ''
            if s in ('origin', 'e_x', 'e_y', 'e_z', 'None', ''):
                return s
            # x may be a 1-based index string like '2'
            try:
                return idx_to_name.get(int(s), s)
            except ValueError:
                return s

        lines = [
            "# Z-matrix (internal coordinates)",
            "# Units: bond length in Å, angle/dihedral in degrees",
            "# Anomaly markers: [!] too_long/suspicious, [!!] too_short, [?] missing/fragmented",
            "# Format: index symbol name | parent1 r=... | parent2 a=... | parent3 d=...",
            "",
        ]

        for idx, row in zmat_frame.iterrows():
            name = idx_to_name[idx]
            parts = [f"{idx:3d}  {name:<5}"]

            p1_name = format_parent(row['b'])
            if p1_name in ('origin', ''):
                parts.append("| (root)")
            else:
                p1_idx = name_to_index.get(p1_name, -1)
                status = bond_status_by_pair.get((idx - 1, p1_idx), "normal")
                marker = ""
                if status == "too_long":
                    marker = " [!]"
                elif status == "too_short":
                    marker = " [!!]"
                elif status == "missing":
                    marker = " [?]"
                parts.append(f"| {p1_name:<6}  r={float(row['bond']):.4f}{marker}")

            p2_name = format_parent(row['a'])
            if p2_name and p2_name not in ('origin', 'e_x', 'e_y', 'e_z'):
                parts.append(f"| {p2_name:<6}  a={float(row['angle']):.2f}")

            p3_name = format_parent(row['d'])
            if p3_name and p3_name not in ('origin', 'e_x', 'e_y', 'e_z'):
                parts.append(f"| {p3_name:<6}  d={float(row['dihedral']):.2f}")

            lines.append("  ".join(parts))

        anomalies = [b for b in bonds if b[4] != "normal"]
        if anomalies:
            lines.append("")
            lines.append("# --- Anomaly summary ---")
            for i, j, r, expected, status in anomalies:
                si = atoms.symbols[i]
                sj = atoms.symbols[j]
                marker = "!" if status == "too_long" else ("!!" if status == "too_short" else "?")
                lines.append(
                    f"# {marker} {si}{i + 1}-{sj}{j + 1}: r={r:.4f} Å, "
                    f"expected ~{expected:.4f} Å ({status})"
                )

        return "\n".join(lines) + "\n"

    @staticmethod
    def _extract_anomalies(bonds: list[tuple[int, int, float, float, str]], atoms) -> list[dict]:
        return [
            {
                "atom_i": i + 1,
                "atom_j": j + 1,
                "symbol_i": atoms.symbols[i],
                "symbol_j": atoms.symbols[j],
                "distance_angstrom": round(r, 4),
                "expected_angstrom": round(expected, 4),
                "status": status,
                "note": (
                    "suspicious bond length (possibly forming/breaking in TS)"
                    if status == "too_long" else
                    "abnormally short bond (possible atomic overlap)"
                    if status == "too_short" else
                    "no bond detected (fragmented or very long distance)"
                ),
            }
            for i, j, r, expected, status in bonds if status != "normal"
        ]

    def _cartesian_to_zmatrix(self, user_input: InternalCoordinates_input_schema) -> InternalCoordinates_output_schema:
        try:
            atoms = self._load_atoms_from_path_or_text(
                user_input.input_path,
                user_input.input_text,
                user_input.input_format,
            )
        except Exception as e:
            return InternalCoordinates_output_schema(
                is_success=False,
                message=f"读取输入结构失败: {str(e)}"
            )

        try:
            bonds = self._build_connectivity(
                atoms,
                threshold_low=user_input.anomaly_threshold_low,
                threshold_high=user_input.anomaly_threshold_high,
            )

            cart = self._ase_to_chemcoord_cart(atoms)
            c_table = cart.get_construction_table()
            zmat_frame = self._build_zmat_dataframe(cart, c_table)
            zmatrix_text = self._render_zmatrix(zmat_frame, atoms, bonds)
            anomalies = self._extract_anomalies(bonds, atoms)

            output_path = ""
            if user_input.output_path:
                os.makedirs(os.path.dirname(user_input.output_path) or ".", exist_ok=True)
                atomic_write_text(user_input.output_path, zmatrix_text)
                output_path = user_input.output_path

            return InternalCoordinates_output_schema(
                is_success=True,
                zmatrix_text=zmatrix_text,
                output_path=output_path,
                anomalies=anomalies,
                message=(
                    f"成功生成 Z-matrix，检测到 {len(anomalies)} 处异常键长。\n"
                    "【注意】：被标记为过长（too_long）的键，其物理意义仅仅是『两个原子的空间距离超出了标准共价键，"
                    "但依然在雷达监测阈值（默认2.0倍）之内』。这通常包含大量分子骨架中正常的非键靠近（例如 1-3 相互作用、弱相互作用等），"
                    "并不代表它们一定是过渡态中正在断裂或形成的反应键。请务必结合真实的反应机理与化学直觉进行甄别，切勿过度解读。"
                )
            )
        except Exception as e:
            import traceback
            return InternalCoordinates_output_schema(
                is_success=False,
                message=f"生成 Z-matrix 失败: {str(e)}\n{traceback.format_exc()}"
            )

    @staticmethod
    def _parse_zmatrix_text(zmatrix_text: str) -> pd.DataFrame:
        """
        解析本工具输出的 Z-matrix 文本，返回 chemcoord 风格的 DataFrame。
        列：atom(str), b(str), bond(float), a(str), angle(float), d(str), dihedral(float)
        行索引：1-based 原子序号（Z-matrix 顺序）。
        """
        import numpy as np
        import pandas as pd

        lines = [ln for ln in zmatrix_text.splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]

        records = []
        name_to_index: dict[str, int] = {}

        # 第一遍：收集序号和名字
        for line in lines:
            tokens = [t.strip() for t in line.split("|")]
            head = tokens[0].split()
            if len(head) < 2:
                raise ValueError(f"无法解析 Z-matrix 行: {line}")
            idx = int(head[0])
            name = head[1]
            symbol = re.sub(r"\d+", "", name)
            name_to_index[name] = idx
            records.append({
                'index': idx, 'name': name, 'symbol': symbol, 'tokens': tokens
            })

        # 第二遍：解析父原子与几何参数
        def resolve(name: str) -> str:
            if name in name_to_index:
                return str(name_to_index[name])
            m = re.search(r"\d+", name)
            if m:
                return str(int(m.group()))
            raise ValueError(f"无法解析父原子名: {name}")

        rows = []
        for rec in records:
            tokens = rec['tokens']
            p1 = p2 = p3 = None
            r = a = d = None

            if len(tokens) > 1 and "root" not in tokens[1]:
                m = re.search(r"([A-Za-z]+\d+)\s+r=([\d.+-]+)", tokens[1])
                if m:
                    p1 = resolve(m.group(1))
                    r = float(m.group(2))
            if len(tokens) > 2:
                m = re.search(r"([A-Za-z]+\d+)\s+a=([\d.+-]+)", tokens[2])
                if m:
                    p2 = resolve(m.group(1))
                    a = float(m.group(2))
            if len(tokens) > 3:
                m = re.search(r"([A-Za-z]+\d+)\s+d=([\d.+-]+)", tokens[3])
                if m:
                    p3 = resolve(m.group(1))
                    d = float(m.group(2))

            rows.append({
                'atom': rec['symbol'],
                'b': p1 if p1 is not None else np.nan,
                'bond': 0.0 if r is None else r,
                'a': p2 if p2 is not None else np.nan,
                'angle': 0.0 if a is None else a,
                'd': p3 if p3 is not None else np.nan,
                'dihedral': 0.0 if d is None else d,
            })

        df = pd.DataFrame(rows)
        df.index = [r['index'] for r in records]
        # 确保 b/a/d 为 object dtype，允许字符串与 NaN 混合
        for col in ['atom', 'b', 'a', 'd']:
            df[col] = df[col].astype(object)
        return df

    @staticmethod
    def _zmat_dataframe_to_xyz(zmat_frame: pd.DataFrame) -> str:
        """
        绕开 chemcoord Zmat.get_cartesian 的只读数组 bug，直接用底层 transformation.get_X
        从 Z-matrix 重建 Cartesian，返回 xyz 文本。
        """
        import chemcoord.constants as constants
        import chemcoord.internal_coordinates._zmat_transformation as tr
        import numpy as np
        import pandas as pd
        from chemcoord.utilities._temporary_deprecation_workarounds import replace_without_warn

        c_table = zmat_frame.loc[:, ['b', 'a', 'd']].copy()

        # 补全缺失的绝对参考：
        # 第 0 行：b=origin, a=e_z, d=e_x
        # 第 1 行：a=e_z, d=e_x
        # 第 2 行：d=e_x
        defaults = [
            ['origin', 'e_z', 'e_x'],
            [np.nan, 'e_z', 'e_x'],
            [np.nan, np.nan, 'e_x'],
        ]
        for i, (def_b, def_a, def_d) in enumerate(defaults):
            if i >= len(c_table):
                break
            if pd.isna(c_table.iloc[i, 0]):
                c_table.iloc[i, 0] = def_b
            if pd.isna(c_table.iloc[i, 1]):
                c_table.iloc[i, 1] = def_a
            if pd.isna(c_table.iloc[i, 2]):
                c_table.iloc[i, 2] = def_d

        # 把父原子名/序号替换为 chemcoord 内部 magic label，再映射到 0-based 列索引
        int_label = constants.int_label
        magic = {'origin', 'e_x', 'e_y', 'e_z'}
        name_to_col = {idx: col for col, idx in enumerate(zmat_frame.index)}

        def convert_cell(x):
            s = str(x) if pd.notna(x) else 'origin'
            if s in magic:
                return s
            return name_to_col.get(int(s), -1)

        c_table_conv = c_table.map(convert_cell)
        c_table_conv = (replace_without_warn(c_table_conv, int_label)
                        .astype('i8')
                        .values
                        .T)

        values = zmat_frame.loc[:, ['bond', 'angle', 'dihedral']].to_numpy(dtype=float).T.copy()
        values[[1, 2], :] = np.radians(values[[1, 2], :])

        err, row, X = tr.get_X(values, c_table_conv)
        if err != 0:
            raise ValueError(f"Z-matrix 第 {row + 1} 行参考原子无效，无法重建坐标")

        positions = X.T  # shape (n, 3)，顺序与 zmat_frame.index 一致

        # 按原始原子序号（index）排序输出 xyz
        ordered = sorted(zip(zmat_frame.index, zmat_frame['atom'], positions), key=lambda x: x[0])

        xyz_lines = [str(len(zmat_frame)), "Generated from Z-matrix"]
        for idx, sym, pos in ordered:
            xyz_lines.append(f"{str(sym):<4} {pos[0]:>14.8f} {pos[1]:>14.8f} {pos[2]:>14.8f}")

        return "\n".join(xyz_lines) + "\n"

    def _zmatrix_to_cartesian(self, user_input: InternalCoordinates_input_schema) -> InternalCoordinates_output_schema:
        if not user_input.zmatrix_text:
            return InternalCoordinates_output_schema(
                is_success=False,
                message="mode=zmatrix_to_cartesian 时必须提供 zmatrix_text"
            )

        try:
            zmat_frame = self._parse_zmatrix_text(user_input.zmatrix_text)
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
                message="成功从 Z-matrix 生成笛卡尔坐标。"
            )
        except Exception as e:
            import traceback
            return InternalCoordinates_output_schema(
                is_success=False,
                message=f"Z-matrix 转坐标失败: {str(e)}\n{traceback.format_exc()}"
            )

    async def tool_call(self, user_input: InternalCoordinates_input_schema, session: Session) -> InternalCoordinates_output_schema:
        if not _CHEMCOORD_AVAILABLE:
            return InternalCoordinates_output_schema(
                is_success=False,
                message="环境未安装 chemcoord 库。请执行: pip install 'cloudra[chem]'"
            )
        if user_input.mode == "cartesian_to_zmatrix":
            return self._cartesian_to_zmatrix(user_input)
        return self._zmatrix_to_cartesian(user_input)


def get_class():
    return InternalCoordinates
