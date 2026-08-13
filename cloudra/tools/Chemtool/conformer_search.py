import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Literal, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdDetermineBonds, rdMolAlign
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    AllChem = None
    rdDetermineBonds = None
    rdMolAlign = None
    _RDKIT_AVAILABLE = False

# k_B，单位 kcal/(mol·K)，用于 Boltzmann 布居
_KB_KCAL = 0.0019872041
# 1 Hartree = 627.5095 kcal/mol（CREST 输出为 Eh）
_EH_TO_KCAL = 627.5095


def _select_energy_window_candidates(
    candidate_ids: list[int],
    rel_energies: dict[int, float],
    passes_filters: dict[int, bool],
    energy_window_kcal: float,
    preserve_reactive: bool,
) -> list[int]:
    """Apply the ordinary energy window without losing the best reactive candidate.

    The rescued conformer keeps its global relative energy; this function does not
    reset the reactive subset's zero or otherwise hide its conformational penalty.
    """
    selected = {
        cid for cid in candidate_ids
        if rel_energies[cid] <= energy_window_kcal
    }
    if preserve_reactive:
        reactive = [cid for cid in candidate_ids if passes_filters.get(cid, False)]
        if reactive:
            selected.add(min(reactive, key=lambda cid: (rel_energies[cid], cid)))
    return sorted(selected, key=lambda cid: (rel_energies[cid], cid))


def _select_cluster_representatives(
    clusters: list[list[int]],
    rel_energies: dict[int, float],
    passes_filters: dict[int, bool],
    preserve_reactive: bool,
) -> list[int]:
    """Keep the normal minimum-energy representative and, when needed, one reactive member."""
    selected: set[int] = set()
    for cluster in clusters:
        if not cluster:
            continue
        representative = min(cluster, key=lambda cid: (rel_energies[cid], cid))
        selected.add(representative)
        if preserve_reactive and not passes_filters.get(representative, False):
            reactive = [cid for cid in cluster if passes_filters.get(cid, False)]
            if reactive:
                selected.add(min(reactive, key=lambda cid: (rel_energies[cid], cid)))
    return sorted(selected, key=lambda cid: (rel_energies[cid], cid))

description = (
    "Conformer-ensemble search: from SMILES or xyz/sdf, generate an ensemble and an energy/Boltzmann-population table, "
    "with optional reaction-distance filters (distance_filters) to keep reactive conformers whose bonding-atom distances fall in a preorganization window. "
    "All coordinates go to ensemble files (confs.sdf / confs.xyz); context only gets the numeric table. "
    "Use for: locating reactive conformers before organic-mechanism calculations, assessing conformational energy contributions, picking a starting geometry for a TS guess. "
    "Do not use for: high-accuracy single points (use submit_compute_job) or format conversion (use format_converter)."
)


class ConformerSearch_input_schema(input_schema):
    smiles: Optional[str] = Field(
        default=None,
        description="Input molecule SMILES. One of smiles/input_path/input_text; smiles is preferred."
    )
    input_path: Optional[str] = Field(
        default=None,
        description="Input structure file path (xyz/sdf/mol). xyz input infers bond orders via rdDetermineBonds."
    )
    input_text: Optional[str] = Field(
        default=None,
        description="Structure text (xyz or mol block). If input_path is set, the file is read instead."
    )
    charge: int = Field(default=0, description="Total molecular charge. Used when inferring bond orders from xyz.")
    backend: Literal["rdkit", "crest"] = Field(
        default="rdkit",
        description="Search backend. rdkit: ETKDGv3 sampling + MMFF/UFF optimization; crest: external CREST (GFN2-xTB, --quick)."
    )
    num_confs: int = Field(default=50, description="Initial conformer count for the RDKit backend.")
    energy_window_kcal: float = Field(
        default=6.0,
        description="Relative energy window (kcal/mol). With distance_filters, the lowest-energy reactive conformer is kept even if it is outside the window, "
                    "and its energy penalty vs the global minimum is retained."
    )
    rmsd_threshold: float = Field(
        default=0.5,
        description="Heavy-atom RMSD clustering threshold (Å). Usually keeps the lowest-energy member of each cluster; if that member fails the distance filter, "
                    "also keeps the lowest-energy reactive conformer in the cluster."
    )
    temperature: float = Field(default=298.15, description="Temperature for Boltzmann populations (K).")
    random_seed: int = Field(default=42, description="RDKit conformer-sampling random seed for reproducibility.")
    distance_filters: list[dict] = Field(
        default_factory=list,
        description="Reaction-distance filters; each item like {\"atoms\": [i, j], \"min_ang\": 1.8, \"max_ang\": 2.6}, "
                    "1-based atom indices. Keeps conformers whose key atom-pair distances fall in the preorganization window (reactive conformers)."
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Ensemble output directory. Default: <stem>_confs/ next to input_path, else ./confs_output/."
    )
    timeout: int = Field(default=600, description="CREST backend subprocess timeout (seconds).")


class ConformerSearch_output_schema(output_schema):
    is_success: bool = Field(description="Whether the search succeeded")
    table: str = Field(default="", description="Energy/population text table (at most 10 rows, no coordinates)")
    conformers: list[dict] = Field(
        default_factory=list,
        description="Numeric summary of clustered conformers: conf_id/rel_energy_kcal/boltzmann_pct/rmsd_to_conf0/passes_filters"
    )
    counts: dict = Field(
        default_factory=dict,
        description="Counts: generated/optimized/within_window/clusters/retained/passing_filters/reactive_rescued"
    )
    ensemble_path: str = Field(default="", description="Conformer-ensemble file path (confs.sdf or confs.xyz)")
    message: str = Field(default="", description="Status or error message")


def _kabsch_rmsd(pos_a, pos_b) -> float:
    """两个坐标集（已按质心对齐前）的 Kabsch 最优 RMSD，用于无键级信息时的构象比较。"""
    import numpy as np

    a = np.asarray(pos_a, dtype=float)
    b = np.asarray(pos_b, dtype=float)
    a = a - a.mean(axis=0)
    b = b - b.mean(axis=0)
    cov = a.T @ b
    v, _, wt = np.linalg.svd(cov)
    d = np.sign(np.linalg.det(v @ wt))
    diag = np.diag([1.0, 1.0, d])
    rot = v @ diag @ wt
    diff = a @ rot - b
    return float(np.sqrt((diff ** 2).sum() / len(a)))


class ConformerSearch(Tool):
    tool_id: str = 't-43'
    tool_name: str = 'conformer_search'
    tool_description: str = description
    input_schema: Any = ConformerSearch_input_schema
    output_schema: Any = ConformerSearch_output_schema

    def is_write(self) -> bool:
        return True

    # ---------- 输入解析 ----------

    @staticmethod
    def _read_input_text(user_input: ConformerSearch_input_schema) -> tuple[str, str]:
        """返回 (结构文本, 来源后缀)。来源后缀为 'xyz' 或 'sdf'。"""
        if user_input.input_path:
            if not os.path.isfile(user_input.input_path):
                raise ValueError(f"输入文件不存在: {user_input.input_path}")
            with open(user_input.input_path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            ext = os.path.splitext(user_input.input_path)[1].lower()
            fmt = "sdf" if ext in (".sdf", ".mol", ".sd") else "xyz"
            return text, fmt
        if user_input.input_text:
            text = user_input.input_text
            first = text.strip().splitlines()[0].strip() if text.strip() else ""
            fmt = "sdf" if ("V2000" in text or "V3000" in text or "$$$$" in text) else "xyz"
            if first.isdigit() and fmt == "sdf":
                fmt = "xyz"
            return text, fmt
        raise ValueError("必须提供 smiles、input_path 或 input_text 之一")

    def _load_mol(self, user_input: ConformerSearch_input_schema):
        """构建带键级信息的 RDKit Mol（未加氢优化前）。"""
        if user_input.smiles:
            mol = Chem.MolFromSmiles(user_input.smiles)
            if mol is None:
                raise ValueError(f"无效的 SMILES 字符串: {user_input.smiles}")
            return mol

        text, fmt = self._read_input_text(user_input)
        if fmt == "sdf":
            mol = Chem.MolFromMolBlock(text, removeHs=False)
            if mol is None:
                raise ValueError("无法解析输入的 sdf/mol 文本")
            return mol

        mol = Chem.MolFromXYZBlock(text)
        if mol is None:
            raise ValueError("无法解析输入的 xyz 文本")
        try:
            rdDetermineBonds.DetermineBonds(mol, charge=user_input.charge)
        except Exception as e:
            raise ValueError(
                f"xyz 输入的键级推断（rdDetermineBonds）失败: {e}。"
                "MMFF 优化依赖键级感知，请检查电荷设置或改用 sdf/mol 输入。"
            ) from e
        if mol.GetNumBonds() == 0 and mol.GetNumAtoms() > 1:
            raise ValueError("xyz 输入未能推断出任何化学键，无法进行 MMFF 优化。")
        return mol

    # ---------- 通用输出 ----------

    @staticmethod
    def _resolve_output_dir(user_input: ConformerSearch_input_schema) -> str:
        if user_input.output_dir:
            return user_input.output_dir
        if user_input.input_path:
            base = os.path.dirname(os.path.abspath(user_input.input_path))
            stem = os.path.splitext(os.path.basename(user_input.input_path))[0]
            return os.path.join(base, f"{stem}_confs")
        return os.path.abspath("confs_output")

    @staticmethod
    def _check_filters(user_input: ConformerSearch_input_schema, natoms: int):
        for flt in user_input.distance_filters:
            atoms = flt.get("atoms", [])
            if len(atoms) != 2:
                raise ValueError(f"distance_filters 每项的 atoms 必须含 2 个原子序号: {flt}")
            i, j = int(atoms[0]), int(atoms[1])
            if not (1 <= i <= natoms and 1 <= j <= natoms):
                raise ValueError(f"distance_filters 原子序号越界（共 {natoms} 个原子）: {flt}")

    @staticmethod
    def _filter_pass(positions, filters) -> bool:
        import numpy as np

        for flt in filters:
            i, j = int(flt["atoms"][0]) - 1, int(flt["atoms"][1]) - 1
            d = float(np.linalg.norm(positions[i] - positions[j]))
            if not (float(flt["min_ang"]) <= d <= float(flt["max_ang"])):
                return False
        return True

    @staticmethod
    def _boltzmann(rel_energies_kcal: list[float], temperature: float) -> list[float]:
        import numpy as np

        e = np.asarray(rel_energies_kcal, dtype=float)
        w = np.exp(-e / (_KB_KCAL * temperature))
        w = w / w.sum()
        return [float(x * 100.0) for x in w]

    @staticmethod
    def _render_table(rows: list[dict], has_filters: bool) -> str:
        head = f"{'conf_id':>7} {'rel E (kcal/mol)':>16} {'Boltzmann %':>11} {'RMSD to conf0 (Å)':>18}"
        if has_filters:
            head += f" {'pass_filters':>12}"
        lines = [head, "-" * len(head)]
        for r in rows[:10]:
            line = (f"{r['conf_id']:>7} {r['rel_energy_kcal']:>16.3f} "
                    f"{r['boltzmann_pct']:>11.1f} {r['rmsd_to_conf0']:>18.3f}")
            if has_filters:
                line += f" {str(r['passes_filters']):>12}"
            lines.append(line)
        return "\n".join(lines)

    def _finalize(self, user_input: ConformerSearch_input_schema,
                  kept: list[dict], counts: dict, ensemble_path: str,
                  extra_message: str = "") -> ConformerSearch_output_schema:
        """kept：聚类后按能量排序的构象 dict（含 rel_energy_kcal/rmsd/passes_filters）。计算布居并渲染输出。"""
        pops = self._boltzmann([k["rel_energy_kcal"] for k in kept], user_input.temperature)
        for k, p in zip(kept, pops):
            k["boltzmann_pct"] = round(p, 1)

        n_pass = sum(1 for k in kept if k["passes_filters"])
        counts.setdefault("clusters", len(kept))
        counts["retained"] = len(kept)
        counts["passing_filters"] = n_pass

        conformers = [
            {
                "conf_id": k["conf_id"],
                "rel_energy_kcal": round(k["rel_energy_kcal"], 3),
                "boltzmann_pct": k["boltzmann_pct"],
                "rmsd_to_conf0": round(k["rmsd_to_conf0"], 3),
                "passes_filters": k["passes_filters"],
            }
            for k in kept
        ]
        table = self._render_table(conformers, bool(user_input.distance_filters))

        message = (
            f"构象搜索完成：聚类后保留 {len(kept)} 个构象，系综已写入 {ensemble_path}。"
            "坐标不在上下文中，请用 ensemble_path 指向的文件做后续计算。"
        )
        if user_input.distance_filters:
            message += (
                f"\n通过距离过滤的构象共 {n_pass} 个，即为 reactive conformer 候选，"
                "建议对这些构象做后续 TS 初猜。"
            )
        if extra_message:
            message += f"\n{extra_message}"

        return ConformerSearch_output_schema(
            is_success=True,
            table=table,
            conformers=conformers,
            counts=counts,
            ensemble_path=ensemble_path,
            message=message,
        )

    # ---------- RDKit 后端 ----------

    def _run_rdkit(self, user_input: ConformerSearch_input_schema) -> ConformerSearch_output_schema:
        try:
            mol = self._load_mol(user_input)
            mol = Chem.AddHs(mol, addCoords=True)
            natoms = mol.GetNumAtoms()
            self._check_filters(user_input, natoms)

            params = AllChem.ETKDGv3()
            params.randomSeed = user_input.random_seed
            params.pruneRmsThresh = -1.0
            cids = list(AllChem.EmbedMultipleConfs(mol, numConfs=user_input.num_confs, params=params))
            if not cids:
                return ConformerSearch_output_schema(is_success=False, message="RDKit 构象生成失败（未嵌入任何构象）。")
            counts = {"generated": len(cids)}

            # MMFF 优化；力场参数缺失时回退 UFF
            ff_name = "MMFF"
            if AllChem.MMFFHasAllMoleculeParams(mol):
                opt_results = AllChem.MMFFOptimizeMoleculeConfs(mol)
            else:
                ff_name = "UFF"
                opt_results = AllChem.UFFOptimizeMoleculeConfs(mol)
            energies = {cid: float(e) for cid, (_, e) in zip(cids, opt_results)}
            counts["optimized"] = len(energies)

            e_min = min(energies.values())
            rel = {cid: (e - e_min) for cid, e in energies.items()}
            has_filters = bool(user_input.distance_filters)
            passes_by_cid = {
                cid: (self._filter_pass(mol.GetConformer(cid).GetPositions(), user_input.distance_filters)
                      if has_filters else True)
                for cid in cids
            }
            within_window = [cid for cid in cids if rel[cid] <= user_input.energy_window_kcal]
            counts["within_window"] = len(within_window)
            candidate_cids = _select_energy_window_candidates(
                cids, rel, passes_by_cid, user_input.energy_window_kcal, has_filters,
            )
            counts["reactive_rescued"] = sum(
                1 for cid in candidate_cids
                if passes_by_cid[cid] and rel[cid] > user_input.energy_window_kcal
            )
            if not candidate_cids:
                return ConformerSearch_output_schema(is_success=False, message="能量窗口内没有构象，异常终止。")

            # 重原子 RMSD 聚类去重（按能量升序贪心）
            mol_h = Chem.RemoveHs(mol)
            heavy_ids = {c.GetId() for c in mol_h.GetConformers()}
            ordered = sorted(candidate_cids, key=lambda c: rel[c])
            clusters: list[list[int]] = []
            for cid in ordered:
                if cid not in heavy_ids:
                    # RemoveHs 未保留该构象 id（理论上不发生），按新聚类处理
                    clusters.append([cid])
                    continue
                placed = False
                for cluster in clusters:
                    rep = cluster[0]
                    if rep in heavy_ids:
                        rmsd = rdMolAlign.GetBestRMS(mol_h, mol_h, prbId=cid, refId=rep)
                    else:
                        rmsd = _kabsch_rmsd(mol.GetConformer(cid).GetPositions(),
                                            mol.GetConformer(rep).GetPositions())
                    if rmsd <= user_input.rmsd_threshold:
                        cluster.append(cid)
                        placed = True
                        break
                if not placed:
                    clusters.append([cid])

            counts["clusters"] = len(clusters)
            selected_cids = _select_cluster_representatives(
                clusters, rel, passes_by_cid, has_filters,
            )
            counts["reactive_cluster_representatives"] = len(selected_cids) - len(clusters)

            kept = []
            for new_id, cid in enumerate(selected_cids):
                positions = mol.GetConformer(cid).GetPositions()
                kept.append({
                    "conf_id": new_id,
                    "orig_cid": cid,
                    "rel_energy_kcal": rel[cid],
                    "abs_energy": energies[cid],
                    "positions": positions,
                    "passes_filters": passes_by_cid[cid],
                    "boltzmann_pct": 0.0,
                    "rmsd_to_conf0": 0.0,
                })

            ref_pos = kept[0]["positions"]
            for k in kept:
                k["rmsd_to_conf0"] = _kabsch_rmsd(k["positions"], ref_pos)

            # 先算 Boltzmann 布居，再一次性落盘（sdf 属性需要 pct）
            pops = self._boltzmann([k["rel_energy_kcal"] for k in kept], user_input.temperature)
            for k, p in zip(kept, pops):
                k["boltzmann_pct"] = round(p, 1)

            out_dir = self._resolve_output_dir(user_input)
            os.makedirs(out_dir, exist_ok=True)
            sdf_path = os.path.join(out_dir, "confs.sdf")
            xyz_path = os.path.join(out_dir, "confs.xyz")

            sdf_chunks = []
            xyz_chunks = []
            for k in kept:
                block = Chem.MolToMolBlock(mol, confId=k["orig_cid"])
                props = (
                    f">  <conf_id>\n{k['conf_id']}\n\n"
                    f">  <energy>\n{k['abs_energy']:.6f}\n\n"
                    f">  <rel_energy_kcal>\n{k['rel_energy_kcal']:.6f}\n\n"
                    f">  <boltzmann_pct>\n{k['boltzmann_pct']:.2f}\n\n"
                )
                sdf_chunks.append(block + props + "$$$$\n")

                lines = [str(natoms),
                         f"conf_id={k['conf_id']} rel_energy_kcal={k['rel_energy_kcal']:.4f}"]
                for a_idx, atom in enumerate(mol.GetAtoms()):
                    p = k["positions"][a_idx]
                    lines.append(f"{atom.GetSymbol():<3} {p[0]:>14.6f} {p[1]:>14.6f} {p[2]:>14.6f}")
                xyz_chunks.append("\n".join(lines) + "\n")

            atomic_write_text(sdf_path, "".join(sdf_chunks))
            atomic_write_text(xyz_path, "".join(xyz_chunks))

            extra = f"力场：{ff_name}（能量单位 kcal/mol）。"
            if counts["reactive_rescued"]:
                extra += (
                    f"为避免预筛选漏掉反应构象，额外保留了 {counts['reactive_rescued']} 个能量窗外的"
                    "最低能 reactive conformer；其相对能仍以全局最低能构象为零点。"
                )
            return self._finalize(user_input, kept, counts, sdf_path, extra_message=extra)

        except Exception as e:
            return ConformerSearch_output_schema(is_success=False, message=f"构象搜索失败: {e}")

    # ---------- CREST 后端 ----------

    @staticmethod
    def _parse_crest_xyz(path: str) -> list[dict]:
        """解析 crest_conformers.xyz：每帧注释行含 Eh 能量。返回 [{'energy_eh':..., 'positions':...}]。"""
        frames = []
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        lines = [ln for ln in content.splitlines()]
        idx = 0
        while idx < len(lines):
            if not lines[idx].strip():
                idx += 1
                continue
            try:
                natoms = int(lines[idx].strip())
            except ValueError:
                idx += 1
                continue
            comment = lines[idx + 1] if idx + 1 < len(lines) else ""
            m = re.search(r"-?\d+\.\d+", comment)
            if m is None:
                raise ValueError(f"crest 输出帧缺少能量注释: {comment!r}")
            energy_eh = float(m.group(0))
            coords = []
            for ln in lines[idx + 2: idx + 2 + natoms]:
                parts = ln.split()
                if len(parts) >= 4:
                    coords.append([float(parts[1]), float(parts[2]), float(parts[3])])
            if len(coords) != natoms:
                raise ValueError("crest 输出帧原子数不完整")
            frames.append({"energy_eh": energy_eh, "positions": coords, "comment": comment})
            idx += 2 + natoms
        if not frames:
            raise ValueError("crest_conformers.xyz 中未解析到任何构象帧")
        return frames

    def _run_crest(self, user_input: ConformerSearch_input_schema) -> ConformerSearch_output_schema:
        if shutil.which("crest") is None:
            return ConformerSearch_output_schema(
                is_success=False,
                message="未找到 crest 可执行程序。请安装 CREST（https://crest-lab.github.io/crest-docs/）"
                        "并确保其在 PATH 中，或改用 backend='rdkit'。"
            )

        try:
            # 组装输入 xyz：优先复用已有结构文本；smiles 先用 RDKit 生成一个 3D 结构
            if user_input.smiles:
                if not _RDKIT_AVAILABLE:
                    return ConformerSearch_output_schema(
                        is_success=False,
                        message="smiles 输入需要 RDKit 生成初始 3D 结构。请执行: pip install 'cloudra[chem]'"
                    )
                mol = Chem.AddHs(Chem.MolFromSmiles(user_input.smiles))
                if AllChem.EmbedMolecule(mol, AllChem.ETKDGv3()) == -1:
                    return ConformerSearch_output_schema(is_success=False, message="SMILES 初始 3D 结构生成失败。")
                AllChem.MMFFOptimizeMolecule(mol)
                xyz_text = Chem.MolToXYZBlock(mol)
            else:
                text, fmt = self._read_input_text(user_input)
                if fmt == "sdf":
                    if not _RDKIT_AVAILABLE:
                        return ConformerSearch_output_schema(
                            is_success=False,
                            message="sdf 输入需要 RDKit 转换坐标。请执行: pip install 'cloudra[chem]'"
                        )
                    mol = Chem.MolFromMolBlock(text, removeHs=False)
                    if mol is None:
                        return ConformerSearch_output_schema(is_success=False, message="无法解析输入的 sdf/mol 文本")
                    xyz_text = Chem.MolToXYZBlock(mol)
                else:
                    xyz_text = text

            out_dir = self._resolve_output_dir(user_input)
            os.makedirs(out_dir, exist_ok=True)

            with tempfile.TemporaryDirectory(prefix="crest_", dir=out_dir) as workdir:
                input_xyz = os.path.join(workdir, "input.xyz")
                atomic_write_text(input_xyz, xyz_text)
                proc = subprocess.run(
                    ["crest", "input.xyz", "-gfn2", "--quick", "--chrg", str(user_input.charge)],
                    cwd=workdir, capture_output=True, text=True, timeout=user_input.timeout,
                )
                crest_xyz = os.path.join(workdir, "crest_conformers.xyz")
                if not os.path.isfile(crest_xyz):
                    tail = (proc.stdout or "")[-2000:]
                    err_tail = (proc.stderr or "")[-1000:]
                    return ConformerSearch_output_schema(
                        is_success=False,
                        message=f"CREST 未生成 crest_conformers.xyz（returncode={proc.returncode}）。\n"
                                f"stdout 尾部:\n{tail}\nstderr 尾部:\n{err_tail}"
                    )
                try:
                    frames = self._parse_crest_xyz(crest_xyz)
                except Exception as e:
                    tail = (proc.stdout or "")[-2000:]
                    return ConformerSearch_output_schema(
                        is_success=False,
                        message=f"解析 crest_conformers.xyz 失败: {e}\nstdout 尾部:\n{tail}"
                    )

            natoms = len(frames[0]["positions"])
            self._check_filters(user_input, natoms)

            e_min = min(f["energy_eh"] for f in frames)
            counts = {
                "generated": len(frames),
                "optimized": len(frames),
            }
            frame_rows = []
            for frame_id, f in enumerate(frames):
                rel_kcal = (f["energy_eh"] - e_min) * _EH_TO_KCAL
                import numpy as np
                pos = np.asarray(f["positions"], dtype=float)
                frame_rows.append({
                    "frame_id": frame_id,
                    "rel_energy_kcal": rel_kcal,
                    "positions": pos,
                    "passes_filters": (self._filter_pass(pos, user_input.distance_filters)
                                       if user_input.distance_filters else True),
                    "boltzmann_pct": 0.0,
                    "rmsd_to_conf0": 0.0,
                })
            rel_by_id = {row["frame_id"]: row["rel_energy_kcal"] for row in frame_rows}
            passes_by_id = {row["frame_id"]: row["passes_filters"] for row in frame_rows}
            within_window = [
                row["frame_id"] for row in frame_rows
                if row["rel_energy_kcal"] <= user_input.energy_window_kcal
            ]
            counts["within_window"] = len(within_window)
            selected_ids = _select_energy_window_candidates(
                [row["frame_id"] for row in frame_rows],
                rel_by_id,
                passes_by_id,
                user_input.energy_window_kcal,
                bool(user_input.distance_filters),
            )
            selected_set = set(selected_ids)
            kept = [row for row in frame_rows if row["frame_id"] in selected_set]
            kept.sort(key=lambda k: k["rel_energy_kcal"])
            for new_id, k in enumerate(kept):
                k["conf_id"] = new_id
            counts["clusters"] = len(kept)
            counts["reactive_rescued"] = sum(
                1 for row in kept
                if row["passes_filters"] and row["rel_energy_kcal"] > user_input.energy_window_kcal
            )
            if not kept:
                return ConformerSearch_output_schema(is_success=False, message="能量窗口内没有构象，异常终止。")

            ref_pos = kept[0]["positions"]
            for k in kept:
                k["rmsd_to_conf0"] = _kabsch_rmsd(k["positions"], ref_pos)

            # 拷贝系综到 output_dir（多帧 xyz，注释行带 kcal/mol 相对能量）
            symbols = [ln.split()[0] for ln in xyz_text.splitlines()[2: 2 + natoms]]
            xyz_path = os.path.join(out_dir, "confs.xyz")
            chunks = []
            for k in kept:
                lines = [str(natoms), f"conf_id={k['conf_id']} rel_energy_kcal={k['rel_energy_kcal']:.4f}"]
                for sym, p in zip(symbols, k["positions"]):
                    lines.append(f"{sym:<3} {p[0]:>14.6f} {p[1]:>14.6f} {p[2]:>14.6f}")
                chunks.append("\n".join(lines) + "\n")
            atomic_write_text(xyz_path, "".join(chunks))

            extra = "后端：CREST (GFN2-xTB, --quick)。系综已由 CREST 去重，未再做 RMSD 聚类。"
            if counts["reactive_rescued"]:
                extra += (
                    f"为避免预筛选漏掉反应构象，额外保留了 {counts['reactive_rescued']} 个能量窗外的"
                    "最低能 reactive conformer；其相对能仍以全局最低能构象为零点。"
                )
            return self._finalize(user_input, kept, counts, xyz_path, extra_message=extra)

        except subprocess.TimeoutExpired:
            return ConformerSearch_output_schema(
                is_success=False,
                message=f"CREST 运行超时（>{user_input.timeout}s）。可调大 timeout 或改用 backend='rdkit'。"
            )
        except Exception as e:
            return ConformerSearch_output_schema(is_success=False, message=f"CREST 后端失败: {e}")

    async def tool_call(self, user_input: ConformerSearch_input_schema, session: Session) -> ConformerSearch_output_schema:
        import asyncio

        # CREST / RDKit 都是同步 CPU/子进程；必须离开 UI 事件循环，否则 TUI 假死。
        if user_input.backend == "crest":
            return await asyncio.to_thread(self._run_crest, user_input)

        if not _RDKIT_AVAILABLE:
            return ConformerSearch_output_schema(
                is_success=False,
                message="环境未安装 RDKit 库。请执行: pip install 'cloudra[chem]'"
            )
        return await asyncio.to_thread(self._run_rdkit, user_input)


def get_class():
    return ConformerSearch
