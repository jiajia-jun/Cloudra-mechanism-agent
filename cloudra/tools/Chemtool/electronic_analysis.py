import os
import shutil
import subprocess
import tempfile
from typing import Any, Literal, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.persistence.workspace import resolve_existing_tool_path
from cloudra.tools.Chemtool.frontier_orbitals import (
    GAP_OK,
    GAP_UNDECIDABLE_SPIN_CROSSOVER,
    frontier_orbital_summary,
)
from cloudra.tools.Chemtool.internal_coordinates import (
    _COVALENT_RADII,
    DISTANCE_CONNECTIVITY_FACTOR,
)

try:
    from pyscf import gto, lo, scf
    from pyscf.lo import iao, ibo
    from pyscf.tools import molden
    _PYSCF_AVAILABLE = True
except Exception:
    gto = None
    lo = None
    scf = None
    iao = None
    ibo = None
    molden = None
    _PYSCF_AVAILABLE = False

_HARTREE_TO_EV = 27.211386245988

description = (
    "Electronic-structure analysis: single-point calculation on an xyz structure (PySCF or xTB), extracting agent-readable facts — "
    "total energy, HOMO/LUMO/gap, dipole, atomic charges (Mulliken vs meta-Löwdin), Mayer bond orders "
    "(partial bonds and forming incipient bonds at a TS), and an IBO-localized Lewis picture "
    "(lone pairs and 2c-2e bonds; an open-source NBO alternative). "
    "Open-shell supported (spin>1 automatically uses UHF/UKS): reports <S^2> spin contamination and Mulliken spin populations to locate radical centers. "
    "All output is numeric/text tables; coordinates never enter context. "
    "Use for: electronic-structure perception of reactants/intermediates/TS (including radicals) and judging how far a reaction has proceeded (partial/incipient bonds). "
    "Do not use for: geometry optimization or TS search itself (use submit_compute_job) or conformer search (use conformer_search)."
)


class ElectronicAnalysis_input_schema(input_schema):
    input_path: Optional[str] = Field(
        default=None, description="Input structure file path (xyz). Mutually exclusive with input_text; file is preferred."
    )
    input_text: Optional[str] = Field(
        default=None, description="xyz coordinate text. If input_path is set, the file is read instead."
    )
    charge: int = Field(default=0, description="Total molecular charge.")
    spin: int = Field(default=1, description="Spin multiplicity (2S+1). Closed-shell is 1.")
    backend: Literal["pyscf", "xtb"] = Field(
        default="pyscf",
        description="Compute backend. pyscf: full HF/DFT analysis; xtb: external xTB (GFN2-xTB semi-empirical; energy/gap/charges/dipole only)."
    )
    method: str = Field(
        default="b3lyp",
        description="PySCF functional (e.g. b3lyp, pbe0, wb97x). Use 'hf' for HF. spin>1 automatically switches to unrestricted (UHF/UKS)."
    )
    basis: str = Field(default="def2-svp", description="PySCF basis set (e.g. def2-svp, sto-3g, cc-pvdz).")
    density_fitting: bool = Field(
        default=True,
        description="Whether to accelerate SCF with density fitting (DF/RI). Accuracy loss on charges/bond orders is negligible; cost drops substantially. On by default."
    )
    scf_conv_tol: float = Field(
        default=1e-7, description="SCF energy convergence threshold (Eh). 1e-7 is enough for perception; tighten to 1e-9 for publication-grade energies."
    )
    reactive_atoms: list[int] = Field(
        default_factory=list,
        description="Key reactive atom indices (1-based). When set, charge/bond-order/IBO reports focus on these atoms and their bonded neighbors."
    )
    output_dir: Optional[str] = Field(
        default=None, description="Output directory. When set, writes a molden orbital file and a calculation log and returns their paths."
    )
    timeout: int = Field(default=1200, description="xTB backend subprocess timeout (seconds).")


class ElectronicAnalysis_output_schema(output_schema):
    is_success: bool = Field(description="Whether the analysis succeeded")
    report: str = Field(default="", description="Electronic-structure text report (Summary/Frontier Orbitals/Charges/Bond Orders/IBO Lewis Picture/Notes)")
    summary: dict = Field(
        default_factory=dict,
        description="Numeric summary: total_energy_eh/homo_eh/lumo_eh/gap_ev/dipole_debye, etc."
    )
    molden_path: str = Field(default="", description="molden orbital file path (when output_dir is set)")
    log_path: str = Field(default="", description="Calculation log path (when output_dir is set)")
    message: str = Field(default="", description="Status or error message")


def _load_xyz_text(tool, user_input: ElectronicAnalysis_input_schema) -> str:
    if user_input.input_path:
        input_path = resolve_existing_tool_path(tool, user_input.input_path)
        with open(input_path, encoding="utf-8", errors="replace") as f:
            return f.read()
    if user_input.input_text:
        return user_input.input_text
    raise ValueError("Must provide one of input_path or input_text")


def _parse_xyz(xyz_text: str) -> tuple[list[str], list[list[float]]]:
    """解析 xyz 文本，返回 (元素符号, 坐标)。容忍多余空行与注释行。"""
    lines = [ln for ln in xyz_text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("xyz text is empty")
    try:
        natoms = int(lines[0].split()[0])
        start = 2
    except ValueError:
        # 没有原子数头，直接按 "符号 x y z" 逐行解析
        natoms = None
        start = 0
    symbols, coords = [], []
    for ln in lines[start:]:
        parts = ln.split()
        if len(parts) < 4:
            continue
        symbols.append(parts[0])
        coords.append([float(parts[1]), float(parts[2]), float(parts[3])])
    if natoms is not None and len(symbols) != natoms:
        raise ValueError(f"xyz declares {natoms} atoms, but {len(symbols)} were parsed")
    if not symbols:
        raise ValueError("No atoms were parsed from the xyz text")
    return symbols, coords


class ElectronicAnalysis(Tool):
    tool_id: str = 't-44'
    tool_name: str = 'electronic_analysis'
    tool_description: str = description
    input_schema: Any = ElectronicAnalysis_input_schema
    output_schema: Any = ElectronicAnalysis_output_schema

    def is_write(self) -> bool:
        return True

    # ---------- 几何/连通性 ----------

    @staticmethod
    def _bond_pairs(symbols: list[str], coords) -> list[tuple[int, int, float]]:
        """共价半径距离判据的成键对：[(i, j, distance)]，0-based。

        判据系数引用 internal_coordinates 的共享常量
        DISTANCE_CONNECTIVITY_FACTOR（同一分子在两处的成键结论必须一致）。
        """
        import numpy as np

        pos = np.asarray(coords, dtype=float)
        pairs = []
        for i in range(len(symbols)):
            ri = _COVALENT_RADII.get(symbols[i], 1.2)
            for j in range(i + 1, len(symbols)):
                rj = _COVALENT_RADII.get(symbols[j], 1.2)
                d = float(np.linalg.norm(pos[i] - pos[j]))
                if d <= DISTANCE_CONNECTIVITY_FACTOR * (ri + rj):
                    pairs.append((i, j, d))
        return pairs

    @staticmethod
    def _focus_set(user_input: ElectronicAnalysis_input_schema,
                   bonds: list[tuple[int, int, float]], natoms: int) -> Optional[set[int]]:
        """reactive_atoms 及其成键邻居（0-based）。未指定 reactive_atoms 时返回 None（不聚焦）。"""
        if not user_input.reactive_atoms:
            return None
        focus = set()
        for a in user_input.reactive_atoms:
            if 1 <= a <= natoms:
                focus.add(a - 1)
        for i, j, _ in bonds:
            if i in focus or j in focus:
                focus.add(i)
                focus.add(j)
        return focus

    # ---------- PySCF 后端 ----------

    @staticmethod
    def _mayer_bond_orders(dm, ovlp, ao_slices, natoms: int, dm_spin=None):
        """Mayer 键级。闭壳层：BO(A,B) = Σ_{μ∈A}Σ_{ν∈B} (PS)_{μν}(PS)_{νμ}；
        开壳层必须叠加自旋密度项：BO(A,B) = Σ[(PS)_{μν}(PS)_{νμ} + (PsS)_{μν}(PsS)_{νμ}]，
        其中 P 为总密度矩阵、Ps = Pα−Pβ 为自旋密度矩阵。缺 Ps 项会系统性低估
        开壳层键级（O2 三重态缺项时 BO≈1.37，补全后 ≈1.85）。"""
        import numpy as np

        ps = np.asarray(dm) @ np.asarray(ovlp)
        ps_spin = np.asarray(dm_spin) @ np.asarray(ovlp) if dm_spin is not None else None
        bo = np.zeros((natoms, natoms))
        for a in range(natoms):
            pa = slice(ao_slices[a, 2], ao_slices[a, 3])
            for b in range(a + 1, natoms):
                pb = slice(ao_slices[b, 2], ao_slices[b, 3])
                block = ps[pa, pb] * ps[pb, pa].T
                if ps_spin is not None:
                    block = block + ps_spin[pa, pb] * ps_spin[pb, pa].T
                bo[a, b] = bo[b, a] = float(block.sum())
        return bo

    @staticmethod
    def _core_orbital_count(symbol: str) -> int:
        """该元素核芯空间轨道数（全电子计数；ECP 基组下定域出的轨道更少，此处仅作
        IBO 展示的核芯/孤对分类启发，不影响数值）。
        按周期表电子排布，价层 = 最高主量子数的 s/p：
        H/He 0；Li–Ne 1（1s）；Na–Ar 5（1s2s2p）；K–Kr 9（+3s3p）；
        Rb–Xe 18（+3d4s4p）；Cs–Rn 27（+4d5s5p）；Fr–Og 43（+4f5d6s6p）。"""
        z = gto.charge(symbol)
        for z_max, count in ((2, 0), (10, 1), (18, 5), (36, 9), (54, 18), (86, 27), (118, 43)):
            if z <= z_max:
                return count
        raise ValueError(f"Element beyond Og (Z=118) is not supported: {symbol}")

    @staticmethod
    def _ibo_analysis(mol, mf, ovlp, symbols: list[str], spin_channel: Optional[int] = None):
        """
        IBO 定域占据轨道 + IAO 原子投影。spin_channel=None 为闭壳层；0/1 为 UHF/UKS 的 α/β 通道。
        返回 list[dict]：每个定域轨道的 kind（core/lone_pair/bond/delocalized）、
        主导原子（1-based）与份额、Fock 期望能量（Eh）、spin 标签（"α"/"β"/""）。
        core 判定：同一原子上的单中心轨道按能量升序，前 n_core(元素) 个为核芯。
        """
        import numpy as np

        if spin_channel is None:
            mo_occ = mf.mo_coeff[:, mf.mo_occ > 0]
            fock = mf.get_fock()
            spin_tag = ""
        else:
            mo_occ = mf.mo_coeff[spin_channel][:, mf.mo_occ[spin_channel] > 0]
            fock = mf.get_fock()[spin_channel]
            spin_tag = "α" if spin_channel == 0 else "β"
        if mo_occ.shape[1] == 0:
            return []
        c_loc = ibo.ibo(mol, mo_occ, verbose=0)
        c_iao = iao.iao(mol, mo_occ)
        # iao.iao 返回的 IAO 不保证 S-正交，需 Löwdin 正交化后再做投影
        c_iao = lo.vec_lowdin(c_iao, ovlp)
        ref_mol = iao.reference_mol(mol)
        ref_slices = ref_mol.aoslice_by_atom()

        proj = c_iao.T @ ovlp @ c_loc
        weights = proj ** 2  # (n_iao, n_loc)

        results = []
        single_center = []  # (atom_idx, energy, pop, 结果索引)
        for i in range(c_loc.shape[1]):
            atom_pops = np.array([
                weights[ref_slices[a, 2]:ref_slices[a, 3], i].sum()
                for a in range(mol.natm)
            ])
            total = atom_pops.sum()
            if total > 0:
                atom_pops = atom_pops / total
            order = np.argsort(atom_pops)[::-1]
            e_orb = float(c_loc[:, i] @ fock @ c_loc[:, i])
            top1, top2 = int(order[0]), int(order[1]) if len(order) > 1 else None
            p1 = float(atom_pops[top1])
            p2 = float(atom_pops[top2]) if top2 is not None else 0.0

            if p1 >= 0.8:
                entry = {
                    "kind": "lone_pair", "atoms": [top1 + 1], "shares": [round(p1 * 100, 1)],
                    "symbols": [symbols[top1]], "energy_eh": e_orb, "spin": spin_tag,
                }
                single_center.append((top1, e_orb, len(results)))
                results.append(entry)
            elif top2 is not None and (p1 + p2) >= 0.7:
                share_sum = p1 + p2
                results.append({
                    "kind": "bond", "atoms": sorted([top1 + 1, top2 + 1]),
                    "shares": [round(p1 / share_sum * 100, 1), round(p2 / share_sum * 100, 1)],
                    "symbols": [symbols[top1], symbols[top2]], "energy_eh": e_orb, "spin": spin_tag,
                })
            else:
                top = [int(a) + 1 for a in order[:3]]
                results.append({
                    "kind": "delocalized", "atoms": top,
                    "shares": [round(float(atom_pops[a - 1]) * 100, 1) for a in top],
                    "symbols": [symbols[a - 1] for a in top], "energy_eh": e_orb, "spin": spin_tag,
                })

        # 单中心轨道按原子分组，能量最低的前 n_core 个改判为核芯轨道
        by_atom: dict[int, list[tuple[float, int]]] = {}
        for atom_idx, e_orb, res_idx in single_center:
            by_atom.setdefault(atom_idx, []).append((e_orb, res_idx))
        for atom_idx, entries in by_atom.items():
            entries.sort()
            n_core = ElectronicAnalysis._core_orbital_count(symbols[atom_idx])
            for _, res_idx in entries[:n_core]:
                results[res_idx]["kind"] = "core"

        results.sort(key=lambda r: r["energy_eh"])
        return results

    def _run_pyscf(self, user_input: ElectronicAnalysis_input_schema,
                   xyz_text: str) -> ElectronicAnalysis_output_schema:
        import numpy as np

        symbols, coords = _parse_xyz(xyz_text)
        natoms = len(symbols)
        bonds = self._bond_pairs(symbols, coords)
        focus = self._focus_set(user_input, bonds, natoms)

        atom_str = "; ".join(
            f"{sym} {c[0]:.10f} {c[1]:.10f} {c[2]:.10f}" for sym, c in zip(symbols, coords)
        )
        mol = gto.Mole()
        mol.build(atom=atom_str, basis=user_input.basis,
                  charge=user_input.charge, spin=user_input.spin - 1, verbose=0)

        open_shell = user_input.spin > 1
        is_hf = user_input.method.strip().lower() == "hf"
        if is_hf:
            mf = scf.UHF(mol) if open_shell else scf.RHF(mol)
        else:
            mf = scf.UKS(mol) if open_shell else scf.RKS(mol)
            mf.xc = user_input.method.strip().lower()
        mf.conv_tol = user_input.scf_conv_tol
        if user_input.density_fitting:
            # 密度拟合近似：对布居分析精度损失可忽略，SCF 成本显著下降
            mf = mf.density_fit()
        e_tot = float(mf.kernel())
        dm = mf.make_rdm1()
        ovlp = mf.get_ovlp()
        # 自旋分辨密度矩阵：UHF/UKS 的 make_rdm1 返回 (2, nao, nao)
        if open_shell and np.asarray(dm).ndim == 3:
            dma, dmb = dm[0], dm[1]
            dm_tot = dma + dmb
            dm_spin = dma - dmb
        else:
            dm_tot = np.asarray(dm)
            dm_spin = None

        # 前线轨道：与 log_parser 共用同一套原语（frontier_orbitals）。
        # 开壳层显式报 α/β 两套 HOMO/LUMO（SOMO 语义）；自旋交叉时 gap
        # 不可判定（None），绝不报负值。
        if dm_spin is not None:
            na, nb = mol.nelec
            frontier = frontier_orbital_summary(
                [list(mf.mo_energy[0]), list(mf.mo_energy[1])], [na, nb],
            )
        else:
            nocc = int(mol.nelectron // 2)
            frontier = frontier_orbital_summary([list(mf.mo_energy)], [nocc])
        homo_eh = frontier["homo"] if frontier["homo"] is not None else float("nan")
        lumo_eh = frontier["lumo"] if frontier["lumo"] is not None else float("nan")
        gap_ev = frontier["gap"] * _HARTREE_TO_EV if frontier["gap"] is not None else None

        # 偶极矩（Debye）
        dip_vec = mf.dip_moment(mol, dm, verbose=0)
        dip_norm = float(np.linalg.norm(dip_vec))

        # meta-Löwdin 原子电荷（基于总密度）
        _, chg = mf.mulliken_meta(mol, dm_tot, s=ovlp, verbose=0)
        chg = np.asarray(chg, dtype=float)
        # Mulliken 原子电荷（对基组敏感、大基组下不可靠，仅作对照参考）
        _, chg_mul = mf.mulliken_pop(mol, dm_tot, s=ovlp, verbose=0)
        chg_mul = np.asarray(chg_mul, dtype=float)
        # Mulliken 自旋布居（开壳层）：Σ_{μ∈A}(P_spin·S)μμ，正值为 α 自旋富集，定位自由基中心
        spin_pop = None
        if dm_spin is not None:
            ps_spin = dm_spin @ ovlp
            ao_slices_spin = mol.aoslice_by_atom()
            spin_pop = np.array([
                np.trace(ps_spin[ao_slices_spin[a, 2]:ao_slices_spin[a, 3],
                                 ao_slices_spin[a, 2]:ao_slices_spin[a, 3]])
                for a in range(natoms)
            ], dtype=float)

        # Mayer 键级：开壳层必须叠加自旋密度项（缺项会把 O2 三重态 BO 低估成 ≈1.37）
        ao_slices = mol.aoslice_by_atom()
        bo = self._mayer_bond_orders(dm_tot, ovlp, ao_slices, natoms, dm_spin=dm_spin)

        # IBO Lewis 图像（开壳层按自旋通道分别定域）
        if dm_spin is not None:
            ibo_orbitals = (self._ibo_analysis(mol, mf, ovlp, symbols, spin_channel=0)
                            + self._ibo_analysis(mol, mf, ovlp, symbols, spin_channel=1))
        else:
            ibo_orbitals = self._ibo_analysis(mol, mf, ovlp, symbols)

        # ---------- 组装报告 ----------
        atom_label = [f"{symbols[a]}{a + 1}" for a in range(natoms)]
        lines = []

        lines.append("=== Summary ===")
        shell = "U" if dm_spin is not None else "R"
        method_str = f"{shell}HF" if is_hf else f"{shell}KS/{user_input.method}"
        if user_input.density_fitting:
            method_str += " (DF/RI)"
        lines.append(f"Backend        : PySCF ({method_str})")
        lines.append(f"Basis          : {user_input.basis}")
        lines.append(f"Charge / Spin  : {user_input.charge} / {user_input.spin}")
        lines.append(f"Total energy   : {e_tot:.8f} Eh")
        lines.append(f"SCF converged  : {bool(mf.converged)}")
        s2_val = None
        if dm_spin is not None:
            s2_val, mult_est = mf.spin_square()
            s2_ideal = (user_input.spin - 1) / 2 * ((user_input.spin - 1) / 2 + 1)
            lines.append(f"<S^2>          : {float(s2_val):.4f} (ideal {s2_ideal:.4f}; deviation >0.1 suggests spin contamination)")
        lines.append(f"Dipole moment  : {dip_norm:.4f} Debye  (vector: {dip_vec[0]:.3f}, {dip_vec[1]:.3f}, {dip_vec[2]:.3f})")
        lines.append("")

        lines.append("=== Frontier Orbitals ===")
        if frontier["open_shell"]:
            for tag, channel in (("α", frontier["alpha"]), ("β", frontier["beta"])):
                ch_homo = channel["homo"]
                ch_lumo = channel["lumo"]
                homo_str = (
                    f"{ch_homo:.6f} Eh  ({ch_homo * _HARTREE_TO_EV:.3f} eV)"
                    if ch_homo is not None else "undecidable (no occupied orbital)"
                )
                lumo_str = (
                    f"{ch_lumo:.6f} Eh  ({ch_lumo * _HARTREE_TO_EV:.3f} eV)"
                    if ch_lumo is not None else "undecidable (no virtual orbital)"
                )
                lines.append(f"{tag}-HOMO (SOMO) : {homo_str}")
                lines.append(f"{tag}-LUMO       : {lumo_str}")
            lines.append(
                f"Overall HOMO/LUMO: {homo_eh:.6f} / {lumo_eh:.6f} Eh "
                "(max of α/β HOMO, min of α/β LUMO)"
            )
        else:
            lines.append(f"HOMO           : {homo_eh:.6f} Eh  ({homo_eh * _HARTREE_TO_EV:.3f} eV)")
            lines.append(f"LUMO           : {lumo_eh:.6f} Eh  ({lumo_eh * _HARTREE_TO_EV:.3f} eV)")
        if frontier["gap_status"] == GAP_OK:
            lines.append(f"HOMO-LUMO gap  : {gap_ev:.3f} eV")
        elif frontier["gap_status"] == GAP_UNDECIDABLE_SPIN_CROSSOVER:
            lines.append(
                "HOMO-LUMO gap  : undecidable — spin crossover (the lowest virtual orbital lies "
                "below the highest occupied one; a single-determinant gap is not well-defined)"
            )
        else:
            lines.append("HOMO-LUMO gap  : undecidable (frontier orbitals missing)")
        lines.append("")

        lines.append("=== Charges (Mulliken / meta-Löwdin) ===")
        if spin_pop is not None:
            lines.append("(spin column = Mulliken spin population: large |value| marks the radical/unpaired-electron center)")

        def _charge_row(a: int) -> str:
            row = f"{atom_label[a]:>6} {chg_mul[a]:>10.4f} {chg[a]:>12.4f}"
            if spin_pop is not None:
                row += f" {spin_pop[a]:>10.4f}"
            return row

        if natoms <= 30:
            header = f"{'atom':>6} {'Mulliken':>10} {'meta-Lowdin':>12}"
            if spin_pop is not None:
                header += f" {'spin':>10}"
            lines.append(header)
            for a in range(natoms):
                lines.append(_charge_row(a))
        else:
            order = np.argsort(chg)
            lines.append("Most negative 5 (by meta-Löwdin):")
            for a in order[:5]:
                lines.append("  " + _charge_row(a))
            lines.append("Most positive 5 (by meta-Löwdin):")
            for a in order[-5:][::-1]:
                lines.append("  " + _charge_row(a))
        if focus is not None:
            lines.append("Reactive atoms and bonded neighbors:")
            for a in sorted(focus):
                lines.append("  " + _charge_row(a))
        if spin_pop is not None:
            radical_order = np.argsort(-np.abs(spin_pop))[:3]
            top = ", ".join(f"{atom_label[a]} ({spin_pop[a]:+.3f})" for a in radical_order)
            lines.append(f"Spin population top-3 (radical center): {top}")
        lines.append("")

        lines.append("=== Bond Orders (Mayer) ===")
        partial_notes = []
        lines.append("Bonded pairs (covalent-radius connectivity):")
        for i, j, d in bonds:
            if focus is not None and i not in focus and j not in focus:
                continue
            bo_ij = bo[i, j]
            tag = ""
            if 0.3 < bo_ij < 1.7 and abs(bo_ij - 1.0) > 0.3:
                tag = "  <- partial bond (TS-like)"
                partial_notes.append(f"{atom_label[i]}-{atom_label[j]}")
            lines.append(f"  {atom_label[i]:>6}-{atom_label[j]:<6} r={d:.3f} Å  BO={bo_ij:.3f}{tag}")
        bonded_set = {(i, j) for i, j, _ in bonds}
        incipient = []
        for i in range(natoms):
            for j in range(i + 1, natoms):
                if (i, j) in bonded_set:
                    continue
                if focus is not None and i not in focus and j not in focus:
                    continue
                if bo[i, j] > 0.3:
                    d = float(np.linalg.norm(np.asarray(coords[i]) - np.asarray(coords[j])))
                    incipient.append((i, j, d, bo[i, j]))
        if incipient:
            lines.append("Non-bonded pairs with BO > 0.3 (incipient bond, forming):")
            for i, j, d, b in incipient:
                lines.append(f"  {atom_label[i]:>6}-{atom_label[j]:<6} r={d:.3f} Å  BO={b:.3f}  <- incipient bond")
        lines.append("")

        lines.append("=== IBO Lewis Picture ===")
        lone_pairs = [o for o in ibo_orbitals if o["kind"] == "lone_pair"]
        cores = [o for o in ibo_orbitals if o["kind"] == "core"]
        ibo_bonds = [o for o in ibo_orbitals if o["kind"] == "bond"]
        deloc = [o for o in ibo_orbitals if o["kind"] == "delocalized"]

        def _spin_prefix(o: dict) -> str:
            return f"({o['spin']}) " if o.get("spin") else " "

        if lone_pairs:
            lines.append("Lone pairs:")
            for o in lone_pairs:
                lines.append(f"  LP{_spin_prefix(o)}on {atom_label[o['atoms'][0] - 1]}  ({o['shares'][0]:.0f}%, E={o['energy_eh']:.3f} Eh)")
        if cores:
            lines.append("Core orbitals:")
            for o in cores:
                lines.append(f"  core{_spin_prefix(o)}on {atom_label[o['atoms'][0] - 1]}  (E={o['energy_eh']:.3f} Eh)")
        if ibo_bonds:
            lines.append("2c-2e bonds:")
            for o in ibo_bonds:
                a1, a2 = o["atoms"][0] - 1, o["atoms"][1] - 1
                if focus is not None and a1 not in focus and a2 not in focus:
                    continue
                s1, s2 = o["shares"]
                lines.append(f"  {atom_label[a1]}-{atom_label[a2]}{_spin_prefix(o)} ({s1:.0f}% / {s2:.0f}%, E={o['energy_eh']:.3f} Eh)")
        if deloc:
            lines.append("Delocalized orbitals (not assigned to the classical Lewis picture):")
            for o in deloc:
                share_str = "/".join(f"{s:.0f}%" for s in o["shares"])
                labels = "-".join(atom_label[a - 1] for a in o["atoms"])
                lines.append(f"  {labels}{_spin_prefix(o)} ({share_str})")
        lines.append("")

        lines.append("=== Notes ===")
        lines.append("Charges follow meta-Löwdin: Mulliken charges are basis-set sensitive (may distort with large "
                     "basis sets) and are shown only for comparison; on sign conflicts, trust meta-Löwdin.")
        lines.append("Partial bonds (0.3 < BO and deviating from an integer bond order by > 0.3) and incipient "
                     "bonds signal an ongoing reaction: bonds breaking/forming near a TS usually show non-integer bond orders.")
        if partial_notes:
            lines.append(f"Partial bond (TS-like) detected: {', '.join(partial_notes)}.")
        if incipient:
            lines.append(f"Detected {len(incipient)} incipient bond pair(s) (non-bonded but BO>0.3), suggesting bond formation in progress.")
        if spin_pop is not None:
            lines.append("Open-shell system: the spin population (the spin column of the Charges table) locates the radical center; "
                         "an α-channel-only single-center IBO roughly corresponds to a singly occupied orbital (SOMO). "
                         "UHF/UKS carries spin-contamination risk — interpret energies and bond orders with care when the <S^2> deviation is large.")
        if not mf.converged:
            lines.append("[Warning] SCF did not converge; the values above are not trustworthy. Check geometry/charge/spin settings.")
        lines.append("Coordinates are not included in context; use the returned molden_path for orbital visualization.")

        report = "\n".join(lines)
        summary = {
            "total_energy_eh": round(e_tot, 8),
            "homo_eh": round(homo_eh, 6),
            "lumo_eh": round(lumo_eh, 6),
            "homo_ev": round(homo_eh * _HARTREE_TO_EV, 3),
            "lumo_ev": round(lumo_eh * _HARTREE_TO_EV, 3),
            "gap_ev": round(gap_ev, 3) if gap_ev is not None else None,
            "gap_status": frontier["gap_status"],
            "dipole_debye": round(dip_norm, 4),
            "scf_converged": bool(mf.converged),
            "partial_bonds": partial_notes,
            "incipient_bond_count": len(incipient),
        }
        if frontier["open_shell"]:
            for prefix, channel in (("alpha", frontier["alpha"]), ("beta", frontier["beta"])):
                summary[f"{prefix}_homo_eh"] = (
                    round(channel["homo"], 6) if channel["homo"] is not None else None
                )
                summary[f"{prefix}_lumo_eh"] = (
                    round(channel["lumo"], 6) if channel["lumo"] is not None else None
                )
        if s2_val is not None:
            summary["spin_squared"] = round(float(s2_val), 4)
            summary["spin_population"] = {atom_label[a]: round(float(spin_pop[a]), 4) for a in range(natoms)}

        molden_path = ""
        log_path = ""
        if user_input.output_dir:
            os.makedirs(user_input.output_dir, exist_ok=True)
            try:
                molden_path = os.path.join(user_input.output_dir, "orbitals.molden")
                with open(molden_path, "w", encoding="utf-8") as f:
                    molden.header(mol, f)
                    if dm_spin is not None:
                        # molden 单文件只写一套轨道，开壳层写 α 通道
                        molden.orbital_coeff(mol, f, mf.mo_coeff[0], ene=mf.mo_energy[0], occ=mf.mo_occ[0])
                    else:
                        molden.orbital_coeff(mol, f, mf.mo_coeff, ene=mf.mo_energy, occ=mf.mo_occ)
            except Exception as e:
                molden_path = ""
                lines_note = f" (failed to write molden orbital file: {e})"
            else:
                lines_note = ""
            log_path = os.path.join(user_input.output_dir, "electronic_analysis.log")
            atomic_write_text(log_path, report + ("\n" + lines_note if lines_note else "") + "\n")

        return ElectronicAnalysis_output_schema(
            is_success=True,
            report=report,
            summary=summary,
            molden_path=molden_path,
            log_path=log_path,
            message="Electronic structure analysis complete (PySCF). The report contains no coordinates; see the returned paths for the molden file and log.",
        )

    # ---------- xTB 后端 ----------

    @staticmethod
    def _parse_xtb_stdout(stdout: str) -> dict:
        # 能量/gap/偶极的文本判据与 guard、log_parser 共用公共层
        # tools.core.xtb_frames（GH #26），此处只做键名映射。
        from cloudra.tools.core import xtb_frames

        data = {}
        energy = xtb_frames.final_energy_hartree(stdout)
        if energy is not None:
            data["total_energy_eh"] = energy
        gap = xtb_frames.homo_lumo_gap_ev(stdout)
        if gap is not None:
            data["gap_ev"] = gap
        dipole = xtb_frames.dipole_debye(stdout)
        if dipole is not None:
            data["dipole_debye"] = dipole
        return data

    def _run_xtb(self, user_input: ElectronicAnalysis_input_schema,
                 xyz_text: str) -> ElectronicAnalysis_output_schema:
        if shutil.which("xtb") is None:
            return ElectronicAnalysis_output_schema(
                is_success=False,
                message="xtb executable not found. Install xTB (https://xtb-docs.readthedocs.io/) "
                        "and ensure it is on PATH, or use backend='pyscf'."
            )

        symbols, _ = _parse_xyz(xyz_text)
        natoms = len(symbols)

        with tempfile.TemporaryDirectory(prefix="xtb_") as workdir:
            input_xyz = os.path.join(workdir, "input.xyz")
            atomic_write_text(input_xyz, xyz_text)
            try:
                proc = subprocess.run(
                    ["xtb", "input.xyz", "--sp",
                     "--chrg", str(user_input.charge),
                     "--uhf", str(user_input.spin - 1)],
                    cwd=workdir, capture_output=True, text=True, timeout=user_input.timeout,
                )
            except subprocess.TimeoutExpired:
                return ElectronicAnalysis_output_schema(
                    is_success=False,
                    message=f"xTB run timed out (>{user_input.timeout}s)."
                )

            stdout = proc.stdout or ""
            data = self._parse_xtb_stdout(stdout)
            if "total_energy_eh" not in data:
                tail = stdout[-2000:]
                err_tail = (proc.stderr or "")[-1000:]
                return ElectronicAnalysis_output_schema(
                    is_success=False,
                    message=f"Failed to parse the total energy from xTB output (returncode={proc.returncode}).\n"
                            f"stdout tail:\n{tail}\nstderr tail:\n{err_tail}"
                )

            # Mulliken 电荷（charges 文件：每行一个电荷值）
            charges = []
            charges_file = os.path.join(workdir, "charges")
            if os.path.isfile(charges_file):
                with open(charges_file, encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        ln = ln.strip()
                        if ln:
                            try:
                                charges.append(float(ln.split()[0]))
                            except ValueError:
                                pass
            if len(charges) != natoms:
                charges = []

            if user_input.output_dir:
                os.makedirs(user_input.output_dir, exist_ok=True)
                log_path = os.path.join(user_input.output_dir, "xtb_stdout.log")
                atomic_write_text(log_path, stdout)
            else:
                log_path = ""

        atom_label = [f"{symbols[a]}{a + 1}" for a in range(natoms)]
        lines = ["=== Summary ===",
                 "Backend        : xTB (GFN2-xTB, --sp)",
                 f"Charge / Spin  : {user_input.charge} / {user_input.spin}",
                 f"Total energy   : {data['total_energy_eh']:.8f} Eh"]
        if "dipole_debye" in data:
            lines.append(f"Dipole moment  : {data['dipole_debye']:.4f} Debye")
        lines.append("")
        lines.append("=== Frontier Orbitals ===")
        if "gap_ev" in data:
            lines.append(f"HOMO-LUMO gap  : {data['gap_ev']:.3f} eV")
        else:
            lines.append("HOMO-LUMO gap  : not parsed from output")
        lines.append("")
        if charges:
            lines.append("=== Charges (Mulliken, xTB) ===")
            lines.append(f"{'atom':>6} {'charge':>10}")
            for a in range(natoms):
                lines.append(f"{atom_label[a]:>6} {charges[a]:>10.4f}")
            lines.append("")
        lines.append("=== Notes ===")
        lines.append("The xTB backend is semi-empirical GFN2-xTB and only provides energy/gap/charges/dipole; "
                     "use backend='pyscf' for Mayer bond orders and the IBO Lewis picture.")
        report = "\n".join(lines)

        summary = dict(data)
        summary["scf_converged"] = proc.returncode == 0
        return ElectronicAnalysis_output_schema(
            is_success=True,
            report=report,
            summary=summary,
            log_path=log_path,
            message="Electronic structure analysis complete (xTB/GFN2-xTB). The report contains no coordinates.",
        )

    async def tool_call(self, user_input: ElectronicAnalysis_input_schema, session: Session) -> ElectronicAnalysis_output_schema:
        import asyncio

        try:
            xyz_text = _load_xyz_text(self, user_input)
        except Exception as e:
            return ElectronicAnalysis_output_schema(is_success=False, message=f"Failed to read input structure: {e}")

        # xTB / PySCF 为同步子进程或重 CPU；移出事件循环，避免 TUI 与 Coordinator 同 loop 假死。
        if user_input.backend == "xtb":
            try:
                return await asyncio.to_thread(self._run_xtb, user_input, xyz_text)
            except Exception as e:
                return ElectronicAnalysis_output_schema(is_success=False, message=f"xTB backend failed: {e}")

        if not _PYSCF_AVAILABLE:
            return ElectronicAnalysis_output_schema(
                is_success=False,
                message="PySCF is not installed. Install it with: pip install pyscf or pip install 'cloudra[chem]'"
            )
        try:
            return await asyncio.to_thread(self._run_pyscf, user_input, xyz_text)
        except Exception as e:
            return ElectronicAnalysis_output_schema(is_success=False, message=f"PySCF backend failed: {e}")
