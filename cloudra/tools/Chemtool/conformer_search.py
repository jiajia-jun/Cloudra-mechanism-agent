import os
from typing import Any, Literal, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core.crest_runner import CrestRunRequest, run_crest
from cloudra.tools.core.geometry import kabsch_rmsd as _kabsch_rmsd
from cloudra.tools.core.structure_builder import (
    BUILD_DIR_NAME,
    BuildStrategy,
    PreparationRequest,
    PreparedStructure,
    StructureInput,
    prepare_structure,
)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdMolAlign
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    AllChem = None
    rdMolAlign = None
    _RDKIT_AVAILABLE = False

# k_B，单位 kcal/(mol·K)，用于 Boltzmann 布居
_KB_KCAL = 0.0019872041
# 1 Hartree = 627.5095 kcal/mol（CREST 输出为 Eh）
_EH_TO_KCAL = 627.5095
# 构建产物目录名（相对 output_dir）——与另外两个入口共用同一个常量，不要各写一份
_BUILD_DIR_NAME = BUILD_DIR_NAME


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


def _sniff_structure_text(text: str) -> Literal["mol_block", "xyz_text"]:
    """Sniff mol block vs xyz by structure, not by substring.

    A mol block is identified by its counts line (line 4: ``<atoms> <bonds> ... V2000/V3000``);
    xyz requires an atom count on line 1 and ``<symbol> <x> <y> <z>`` on every coordinate line.
    Neither match is an explicit failure — the format is never guessed from loose substrings
    (an xyz comment containing "V2000", or a mol block whose molecule name starts with a digit).
    """
    lines = text.strip().splitlines()
    if len(lines) >= 4:
        counts_parts = lines[3].split()
        if (
            len(counts_parts) >= 2
            and counts_parts[0].isdigit()
            and counts_parts[1].isdigit()
            and ("V2000" in counts_parts or "V3000" in counts_parts)
        ):
            return "mol_block"
    if lines:
        try:
            count = int(lines[0].strip())
        except ValueError:
            count = -1
        if count >= 1 and len(lines) >= 2 + count:
            coordinate_lines = lines[2: 2 + count]
            if all(
                len(parts) >= 4 and parts[0].isalpha() and _all_float(parts[1:4])
                for parts in (line.split() for line in coordinate_lines)
            ):
                return "xyz_text"
    raise ValueError(
        "input_text is neither a mol block (line 4 must be a counts line: '<atoms> <bonds> ... "
        "V2000/V3000') nor xyz text (atom count, comment, then '<symbol> <x> <y> <z>' lines); "
        "the format was not guessed"
    )


def _all_float(tokens: list[str]) -> bool:
    try:
        for token in tokens:
            float(token)
    except ValueError:
        return False
    return True


description = (
    "Conformer-ensemble search: from SMILES or xyz/sdf, generate an ensemble and an energy/Boltzmann-population table, "
    "with optional reaction-distance filters (distance_filters) to keep reactive conformers whose bonding-atom distances fall in a preorganization window. "
    "All coordinates go to ensemble files (confs.sdf / confs.xyz); context only gets the numeric table. "
    "The input structure is resolved by the shared structure builder. For a multi-component input (SMILES "
    "with dots) the ensemble IS the approved complex assembly (rigid placement sampling + collision "
    "rejection + force-field relaxation): candidates are assembled complexes, never overlapping or "
    "translated-apart fragment coordinates. "
    "The 'mode' parameter selects the CREST run type (CREST backend only): "
    "'conformers' (default) is the ordinary conformer search for a single molecule; "
    "'nci' samples NON-COVALENT complexes/aggregates under an ellipsoid wall potential — use it for "
    "hydrogen-bond networks and preorganized reactant complexes between fragments; "
    "'qcg' grows an explicit solvent shell around the solute (quantum cluster growth, needs solvent_smiles "
    "and nsolv, and the external xtb-IFF program) — the standard way to build a micro-solvated cluster or a "
    "hydrogen-bond network with explicit waters (e.g. proton shuttles); "
    "'protonate'/'deprotonate'/'tautomerize' enumerate protomers/tautomers. "
    "WARNING for protonate/deprotonate/tautomerize: the output is an automated screening ensemble that MAY "
    "contain chemically unreasonable pseudo-structures; review EVERY structure chemically before using it. "
    "Use for: locating reactive conformers before organic-mechanism calculations, building hydrogen-bonded/"
    "solvated starting structures, assessing conformational energy contributions, picking a starting geometry for a TS guess. "
    "Do not use for: high-accuracy single points (use submit_compute_job) or format conversion (use format_converter)."
)


class ConformerSearch_input_schema(input_schema):
    smiles: Optional[str] = Field(
        default=None,
        description="Input molecule SMILES. One of smiles/input_path/input_text; smiles is preferred. "
                    "Must be a single connected component; a dot-separated multi-component input is refused."
    )
    input_path: Optional[str] = Field(
        default=None,
        description="Input structure file path (xyz/sdf/mol). xyz input infers bond orders via "
                    "rdDetermineBonds. Absolute path, or relative to the agent process's current "
                    "working directory; absolute paths are recommended."
    )
    input_text: Optional[str] = Field(
        default=None,
        description="Structure text (xyz or mol block). If input_path is set, the file is read instead."
    )
    charge: int = Field(
        default=0,
        description="Total molecular charge. Must equal the structure's formal-charge sum; used when "
                    "inferring bond orders from xyz, and passed to CREST as --chrg."
    )
    multiplicity: int = Field(
        default=1,
        description="Spin multiplicity (2S+1). CREST backend: passed to xtb as --uhf = multiplicity - 1. "
                    "The RDKit backend (MMFF/UFF force fields) is closed-shell only and rejects multiplicity > 1."
    )
    backend: Literal["rdkit", "crest"] = Field(
        default="rdkit",
        description="Search backend. rdkit: ETKDGv3 sampling + MMFF/UFF optimization; crest: external CREST (GFN2-xTB, --quick). "
                    "Any mode other than 'conformers' requires backend='crest'."
    )
    mode: Literal["conformers", "nci", "qcg", "protonate", "deprotonate", "tautomerize"] = Field(
        default="conformers",
        description="CREST run type (backend='crest' only). conformers: ordinary search. "
                    "nci: non-covalent complex/aggregate sampling under a wall potential — for hydrogen-bond "
                    "networks and preorganized reactant complexes (intended for multi-component inputs). "
                    "qcg: grow an explicit solvent shell of nsolv solvent_smiles molecules around the solute "
                    "(quantum cluster growth; requires the external xtb-IFF program). "
                    "protonate/deprotonate/tautomerize: protomer/tautomer enumeration of a SINGLE-component "
                    "input; the output may contain pseudo-structures — review every structure before use.",
    )
    solvent_smiles: Optional[str] = Field(
        default=None,
        description="mode='qcg' only: SMILES of ONE neutral solvent molecule (e.g. 'O' for water). "
                    "Its geometry is built by the shared structure builder.",
    )
    nsolv: int = Field(
        default=0,
        description="mode='qcg' only: number of solvent molecules to grow around the solute (>= 1). "
                    "2-4 waters typically suffice to bridge a proton shuttle; more for a first solvation shell.",
    )
    num_confs: int = Field(
        default=50,
        description="Initial conformer count for the RDKit backend on a **single-component** "
                    "structure. Ignored for a multi-component input, whose ensemble is the approved "
                    "complex assembly (its orientation-sampling count governs instead).",
    )
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
        description="Ensemble output directory. Default: <stem>_confs/ next to input_path, else ./confs_output/. "
                    "Relative paths resolve against the agent process's current working directory. The shared "
                    "builder writes its artifacts under <output_dir>/structure_build/."
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


class ConformerSearch(Tool):
    tool_id: str = 't-43'
    tool_name: str = 'conformer_search'
    tool_description: str = description
    input_schema: Any = ConformerSearch_input_schema
    output_schema: Any = ConformerSearch_output_schema

    def is_write(self) -> bool:
        return True

    # ---------- 输入解析（唯一实现：共享结构构建器） ----------

    @staticmethod
    def _structure_input(user_input: ConformerSearch_input_schema) -> StructureInput:
        """把三种输入归一成构建器的声明式来源；来源无法判定即 fail-loud。"""
        if user_input.smiles:
            return StructureInput(kind="smiles", value=user_input.smiles)
        if user_input.input_path:
            if not os.path.isfile(user_input.input_path):
                raise ValueError(f"Input file does not exist: {user_input.input_path}")
            with open(user_input.input_path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            ext = os.path.splitext(user_input.input_path)[1].lower()
            kind = "mol_block" if ext in (".sdf", ".mol", ".sd") else "xyz_text"
            return StructureInput(kind=kind, value=text)
        if user_input.input_text:
            return StructureInput(kind=_sniff_structure_text(user_input.input_text),
                                  value=user_input.input_text)
        raise ValueError("Must provide one of smiles, input_path, or input_text")

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
    def _build_dir(out_dir: str) -> str:
        return os.path.join(out_dir, _BUILD_DIR_NAME)

    def _prepare(self, user_input: ConformerSearch_input_schema, out_dir: str,
                 *, embed: bool, optimize: bool) -> PreparedStructure:
        """调用共享构建器解析/构建结构（本工具不再自带解析与 Embed/MMFF 快捷路径）。"""
        return prepare_structure(PreparationRequest(
            structure=self._structure_input(user_input),
            output_dir=self._build_dir(out_dir),
            total_charge=user_input.charge,
            multiplicity=user_input.multiplicity,
            random_seed=user_input.random_seed,
            strategy=BuildStrategy(name="per_component", embed=embed, optimize=optimize),
        ))

    @staticmethod
    def _build_failure(prepared: PreparedStructure) -> ConformerSearch_output_schema:
        details = " | ".join(prepared.diagnostics) if prepared.diagnostics else prepared.message
        return ConformerSearch_output_schema(
            is_success=False,
            message=(
                f"Conformer search refused by the shared structure builder "
                f"(build status: {prepared.status}). {prepared.message}"
                + (f" Diagnostics: {details}" if details and details != prepared.message else "")
                + f" Build artifacts: {prepared.artifact_path}"
            ),
        )

    @staticmethod
    def _load_built_mol(prepared: PreparedStructure):
        """从构建器的组分 MOL 文件读回单组分结构（连接表/立体化学/电荷的交换格式）。"""
        component = prepared.components[0]
        with open(component.mol_path, encoding="utf-8") as handle:
            mol = Chem.MolFromMolBlock(handle.read(), removeHs=False)
        if mol is None:
            raise ValueError(
                f"the builder's component file could not be re-read as a mol: {component.mol_path}"
            )
        return mol, component

    # ---------- 通用输出 ----------

    @staticmethod
    def _check_filters(user_input: ConformerSearch_input_schema, natoms: int):
        for flt in user_input.distance_filters:
            atoms = flt.get("atoms", [])
            if len(atoms) != 2:
                raise ValueError(f"Each distance_filters entry's atoms must contain 2 atom indices: {flt}")
            i, j = int(atoms[0]), int(atoms[1])
            if not (1 <= i <= natoms and 1 <= j <= natoms):
                raise ValueError(f"distance_filters atom indices out of range (system has {natoms} atoms): {flt}")

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
            f"Conformer search complete: {len(kept)} conformers kept after clustering; ensemble written to {ensemble_path}. "
            "Coordinates are not included in context; use the file at ensemble_path for follow-up calculations."
        )
        if user_input.distance_filters:
            message += (
                f"\n{n_pass} conformers pass the distance filters and are reactive conformer candidates; "
                "TS guesses from these conformers are recommended."
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

    @staticmethod
    def _mmff_single_point_energy(mol, cid: int, ignore_interfrag: bool) -> Optional[float]:
        """指定构象的 MMFF94 单点能量（kcal/mol）；无法构建力场时返回 None。"""
        props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
        if props is None:
            return None
        ff = AllChem.MMFFGetMoleculeForceField(
            mol, props, confId=cid, ignoreInterfragInteractions=ignore_interfrag)
        if ff is None:
            return None
        return float(ff.CalcEnergy())

    def _optimize_single(self, mol, cid: int, ignore_interfrag: bool,
                         max_iters: int = 2000) -> Optional[tuple[float, str]]:
        """优化单个构象：先试 MMFF（加大迭代次数），不收敛回退 UFF；皆败返回 None。
        UFF 仅作几何优化引擎：UFF 收敛的几何统一用 MMFF 单点重估能量（MMFF 与 UFF 零点不同，
        UFF 能量值绝不进入排序/能窗/布居）。成功返回 (MMFF 能量 kcal/mol, 力场名)。"""
        if AllChem.MMFFOptimizeMolecule(
                mol, confId=cid, maxIters=max_iters, ignoreInterfragInteractions=ignore_interfrag) == 0:
            energy = self._mmff_single_point_energy(mol, cid, ignore_interfrag)
            if energy is not None:
                return energy, "MMFF"
        if AllChem.UFFOptimizeMolecule(
                mol, confId=cid, maxIters=max_iters, ignoreInterfragInteractions=ignore_interfrag) == 0:
            energy = self._mmff_single_point_energy(mol, cid, ignore_interfrag)
            if energy is not None:
                return energy, "UFF geometry, MMFF single-point"
        return None

    def _run_complex(self, user_input: ConformerSearch_input_schema, out_dir: str) -> ConformerSearch_output_schema:
        """多组分输入：以**组装结果**作为复合物构象候选（组装参数由用户批准）。

        不再对整体做 ETKDG 系综嵌入——那会把碎片相对取向随机化，等于把"复合物"退回随机叠加。
        组装自身的能窗与 RMSD 聚类已按批准参数执行；这里只额外应用调用方显式给出的
        ``distance_filters``（作为反应中心/预组织窗口的可选筛选），并如实报告每个候选。
        """
        from cloudra.tools.core.structure_artifacts import read_xyz_atoms

        prepared = self._prepare(user_input, out_dir, embed=True, optimize=True)
        if prepared.status != "ok" or not prepared.has_coordinates or prepared.assembly is None:
            return self._build_failure(prepared)

        assembly = prepared.assembly
        if not assembly.candidates:
            return ConformerSearch_output_schema(
                is_success=False,
                message=(
                    "Assembly produced no complex candidate for this multi-component input "
                    f"(assembly status: {assembly.status}). {assembly.message}"
                ),
            )

        import numpy as np

        frames = []
        for candidate in assembly.candidates:
            atoms = read_xyz_atoms(candidate.xyz_path)
            frames.append({
                "conf_id": candidate.candidate_id,
                "rel_energy_kcal": candidate.rel_energy_kcal,
                "abs_energy": candidate.energy_kcal,
                "positions": np.asarray([position for _symbol, position in atoms], dtype=float),
                "cluster_id": candidate.cluster_id,
                "min_interfragment_distance": candidate.min_interfragment_distance,
                "trajectory_id": candidate.trajectory_id,
            })

        natoms = len(frames[0]["positions"])
        self._check_filters(user_input, natoms)
        has_filters = bool(user_input.distance_filters)
        for frame in frames:
            frame["passes_filters"] = (
                self._filter_pass(frame["positions"], user_input.distance_filters)
                if has_filters else True
            )

        pops = self._boltzmann([f["rel_energy_kcal"] for f in frames], user_input.temperature)
        for frame, population in zip(frames, pops):
            frame["boltzmann_pct"] = round(population, 1)

        ref_pos = frames[0]["positions"]
        for frame in frames:
            frame["rmsd_to_conf0"] = _kabsch_rmsd(frame["positions"], ref_pos)

        # 落盘多帧系综（与单组分路径同一文件契约）
        xyz_path = os.path.join(out_dir, "confs.xyz")
        chunks = []
        for frame in frames:
            lines = [
                str(natoms),
                f"conf_id={frame['conf_id']} rel_energy_kcal={frame['rel_energy_kcal']:.4f} "
                f"cluster_id={frame['cluster_id']} "
                f"min_interfragment_distance={frame['min_interfragment_distance']:.4f}",
            ]
            for symbol, position in zip(prepared.symbols, frame["positions"]):
                lines.append(f"{symbol:<3} {position[0]:>14.6f} {position[1]:>14.6f} {position[2]:>14.6f}")
            chunks.append("\n".join(lines) + "\n")
        atomic_write_text(xyz_path, "".join(chunks))

        counts = {
            "generated": assembly.sampled_placements,
            "optimized": assembly.optimized_placements,
            "collision_rejected": assembly.collision_rejected,
            "collapsed_after_relaxation": assembly.collapsed_after_relaxation,
            "within_window": len(assembly.candidates),
            "clusters": len({f["cluster_id"] for f in frames}),
        }
        extra = (
            f"Multi-component input: candidates come from the approved complex assembly "
            f"({assembly.mode} mode, {assembly.parameters.orientations} relative orientations, "
            f"{assembly.parameters.min_interfragment_distance} Å inter-fragment collision criterion, "
            f"{assembly.parameters.energy_window_kcal} kcal/mol window, "
            f"{assembly.parameters.rmsd_threshold} Å heavy-atom RMSD clustering). "
            f"Assembly artifacts: {assembly.artifact_path}. "
            "No whole-complex ETKDG ensemble was embedded: that would randomize the relative "
            "fragment orientations and reduce the complex to a random overlay."
        )
        return self._finalize(user_input, frames, counts, xyz_path, extra_message=extra)

    def _run_rdkit(self, user_input: ConformerSearch_input_schema, out_dir: str) -> ConformerSearch_output_schema:
        try:
            # 结构解析（含拆分自检、形式电荷自检、自旋自检）统一走共享构建器；
            # 系综嵌入由本后端的 ETKDGv3 批量采样承担，故 embed=False。
            prepared = self._prepare(user_input, out_dir, embed=False, optimize=False)
            if len(prepared.components) > 1:
                # 多组分输入的"构象系综"就是**组装**：ETKDG 对整体系综重新嵌入会把碎片相对取向
                # 随机化，得到的是无意义的叠加。因此这里改走已批准的组装方案（complex_assembly），
                # 候选即组装结果。
                return self._run_complex(user_input, out_dir)
            if prepared.status != "ok":
                return self._build_failure(prepared)

            mol, component = self._load_built_mol(prepared)
            natoms = mol.GetNumAtoms()
            self._check_filters(user_input, natoms)

            params = AllChem.ETKDGv3()
            params.randomSeed = user_input.random_seed
            params.pruneRmsThresh = -1.0
            cids = list(AllChem.EmbedMultipleConfs(mol, numConfs=user_input.num_confs, params=params))
            if not cids:
                return ConformerSearch_output_schema(is_success=False, message="RDKit conformer generation failed (no conformers embedded).")
            counts = {"generated": len(cids)}

            # 单组分体系不涉及碎片间相互作用：构建器已保证多组分输入在进入本后端之前被拒。
            ignore_interfrag = True

            # MMFF 优化；逐构象检查收敛标志，失败者加大迭代次数重试并回退 UFF，两者皆败剔除（0.0 绝不当作能量）。
            # UFF 只作几何优化引擎：MMFF 与 UFF 零点不同（可差 ~17 kcal/mol），UFF 回退构象的几何统一用
            # MMFF 单点重估能量后再入排序/能窗/Boltzmann；分子缺 MMFF 参数时无法重估，显式拒收而非输出
            # 不可比的 UFF 能量表。
            use_mmff = AllChem.MMFFHasAllMoleculeParams(mol)
            if not use_mmff:
                return ConformerSearch_output_schema(
                    is_success=False,
                    message=(
                        "MMFF94 parameters are missing for at least one atom of this molecule "
                        "(MMFFHasAllMoleculeParams=False), so UFF-optimized geometries cannot be re-evaluated "
                        "on the MMFF energy scale. UFF energies use a different zero point and must not enter "
                        "energy ranking or Boltzmann populations; aborting instead of reporting UFF energies. "
                        "Use backend='crest' for this system."
                    ),
                )
            ff_name = "MMFF"
            opt_results = AllChem.MMFFOptimizeMoleculeConfs(mol, ignoreInterfragInteractions=ignore_interfrag)
            energies = {cid: float(e) for cid, (ok, e) in zip(cids, opt_results) if ok == 0}
            failed_cids = [cid for cid in cids if cid not in energies]
            uff_rescued = 0
            for cid in failed_cids:
                res = self._optimize_single(mol, cid, ignore_interfrag)
                if res is not None:
                    energies[cid] = res[0]
                    uff_rescued += res[1].startswith("UFF")
            if uff_rescued:
                ff_name = (
                    f"MMFF ({uff_rescued} unconverged conformer(s) optimized with UFF as geometry engine only; "
                    "their energies are MMFF single-point re-evaluations on the UFF geometries, so all reported "
                    "energies share the MMFF zero point and UFF energies never enter ranking or populations)"
                )
            counts["optimized"] = len(energies)
            counts["optimization_failed"] = len(cids) - len(energies)
            if not energies:
                return ConformerSearch_output_schema(
                    is_success=False,
                    message="Force-field optimization failed for all conformers (MMFF and UFF); no valid energies, aborting.",
                )

            valid_cids = [cid for cid in cids if cid in energies]
            e_min = min(energies.values())
            rel = {cid: (e - e_min) for cid, e in energies.items()}
            has_filters = bool(user_input.distance_filters)
            passes_by_cid = {
                cid: (self._filter_pass(mol.GetConformer(cid).GetPositions(), user_input.distance_filters)
                      if has_filters else True)
                for cid in valid_cids
            }
            within_window = [cid for cid in valid_cids if rel[cid] <= user_input.energy_window_kcal]
            counts["within_window"] = len(within_window)
            candidate_cids = _select_energy_window_candidates(
                valid_cids, rel, passes_by_cid, user_input.energy_window_kcal, has_filters,
            )
            counts["reactive_rescued"] = sum(
                1 for cid in candidate_cids
                if passes_by_cid[cid] and rel[cid] > user_input.energy_window_kcal
            )
            if not candidate_cids:
                return ConformerSearch_output_schema(is_success=False, message="No conformers within the energy window; aborting.")

            # 重原子 RMSD 聚类去重（按能量升序贪心）：RemoveHs 后与 GetBestRMS 同一重原子口径，
            # 0.5 Å 阈值两条路径含义一致。RemoveHs 必须保留 conformer id，否则无法把重原子
            # RMSD 对回原构象——这是一次性断言，不成立即 fail-loud，绝不换全原子口径兜底。
            mol_h = Chem.RemoveHs(mol)
            heavy_ids = {c.GetId() for c in mol_h.GetConformers()}
            missing_ids = [cid for cid in candidate_cids if cid not in heavy_ids]
            if missing_ids:
                return ConformerSearch_output_schema(
                    is_success=False,
                    message=(
                        f"RDKit RemoveHs did not preserve conformer id(s) {missing_ids}, so the "
                        "heavy-atom RMSD clustering cannot be mapped back to the original "
                        "conformers; aborting instead of silently falling back to an all-atom "
                        "RMSD criterion under the same threshold."
                    ),
                )
            ordered = sorted(candidate_cids, key=lambda c: rel[c])
            clusters: list[list[int]] = []
            for cid in ordered:
                placed = False
                for cluster in clusters:
                    rmsd = rdMolAlign.GetBestRMS(mol_h, mol_h, prbId=cid, refId=cluster[0])
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

            extra = (
                f"Force field: {ff_name} (energies in kcal/mol). "
                f"Structure resolved by the shared builder (component {component.component_id}, "
                f"build artifacts: {prepared.artifact_path})."
            )
            if counts["reactive_rescued"]:
                extra += (
                    f"{counts['reactive_rescued']} lowest-energy reactive conformer(s) outside the energy window were "
                    "additionally kept to avoid losing reactive conformers in pre-screening; their relative energies still use the global minimum as zero."
                )
            return self._finalize(user_input, kept, counts, sdf_path, extra_message=extra)

        except Exception as e:
            return ConformerSearch_output_schema(is_success=False, message=f"Conformer search failed: {e}")

    # ---------- CREST 后端 ----------

    _SINGLE_COMPONENT_RUNTYPES = ("protonate", "deprotonate", "tautomerize")

    def _build_qcg_solvent(self, user_input: ConformerSearch_input_schema, out_dir: str) -> str:
        """QCG 的溶剂分子几何：同样走共享构建器（中性、单组分、闭壳层），产物目录用 slug 隔开。"""
        from cloudra.tools.core.structure_builder import build_artifact_dir

        solvent = prepare_structure(PreparationRequest(
            structure=StructureInput(kind="smiles", value=user_input.solvent_smiles),
            output_dir=build_artifact_dir(out_dir, "qcg_solvent"),
            total_charge=0,
            multiplicity=1,
            random_seed=user_input.random_seed,
            strategy=BuildStrategy(name="per_component", embed=True, optimize=True),
        ))
        if solvent.status != "ok" or not solvent.has_coordinates:
            details = " | ".join(solvent.diagnostics) if solvent.diagnostics else solvent.message
            raise ValueError(
                f"the QCG solvent structure could not be built (status: {solvent.status}). "
                f"{solvent.message}"
                + (f" Diagnostics: {details}" if details and details != solvent.message else "")
            )
        if len(solvent.components) > 1:
            raise ValueError(
                "the QCG solvent must be a single neutral molecule (one connected component); "
                f"solvent_smiles={user_input.solvent_smiles!r} has {len(solvent.components)} components"
            )
        solvent_path = solvent.candidate_path(".xyz")
        with open(solvent_path, encoding="utf-8") as handle:
            return handle.read()

    def _run_crest(self, user_input: ConformerSearch_input_schema, out_dir: str) -> ConformerSearch_output_schema:
        try:
            # 种子结构由共享构建器产出（embed+optimize）：多组分输入在这里就被拒，
            # 互穿几何绝不会被喂给 CREST/xTB（issue #33 的直接病因）。
            prepared = self._prepare(user_input, out_dir, embed=True, optimize=True)
            if prepared.status != "ok" or not prepared.has_coordinates:
                return self._build_failure(prepared)

            runtype = "default" if user_input.mode == "conformers" else user_input.mode
            multi_fragment = len(prepared.components) > 1
            if runtype in self._SINGLE_COMPONENT_RUNTYPES and multi_fragment:
                return ConformerSearch_output_schema(
                    is_success=False,
                    message=(
                        f"mode='{user_input.mode}' screens protonation states/tautomers of ONE "
                        f"molecule, but this input has {len(prepared.components)} components. "
                        "Run it per component, or use mode='nci'/'conformers' for the complex."
                    ),
                )

            seed_path = prepared.candidate_path(".xyz")
            with open(seed_path, encoding="utf-8") as handle:
                seed_xyz = handle.read()

            solvent_xyz = ""
            if runtype == "qcg":
                solvent_xyz = self._build_qcg_solvent(user_input, out_dir)

            # 用户批准（Task 4 门）：多碎片输入默认加 --noreftopo，只关搜索前的初始拓扑检查。
            # 单组分输入不加该选项（没有片间拓扑可变化，加了只会掩盖真实问题）。
            run = run_crest(CrestRunRequest(
                xyz_text=seed_xyz,
                output_dir=out_dir,
                charge=user_input.charge,
                multiplicity=user_input.multiplicity,
                timeout=user_input.timeout,
                run_label="crest" if runtype == "default" else f"crest_{runtype}",
                noreftopo=multi_fragment,
                runtype=runtype,
                solvent_xyz_text=solvent_xyz,
                nsolv=user_input.nsolv,
            ))
            if not run.scientific_success:
                details = " | ".join(run.diagnostics) if run.diagnostics else ""
                return ConformerSearch_output_schema(
                    is_success=False,
                    message=(
                        f"CREST backend (mode='{user_input.mode}') did not produce a usable ensemble "
                        f"(termination={run.termination_reason}, stage={run.stage}, "
                        f"returncode={run.returncode}). {run.message}"
                        + (f" Diagnostics: {details}" if details else "")
                        + " A failed or partial run never enters the conformer ranking."
                    ),
                )

            frames = run.conformers
            natoms = len(frames[0].positions)
            self._check_filters(user_input, natoms)

            e_min = min(f.energy_eh for f in frames)
            counts = {
                "generated": len(frames),
                "optimized": len(frames),
            }
            frame_rows = []
            for f in frames:
                rel_kcal = (f.energy_eh - e_min) * _EH_TO_KCAL
                import numpy as np
                pos = np.asarray(f.positions, dtype=float)
                frame_rows.append({
                    "frame_id": f.frame_index,
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
                return ConformerSearch_output_schema(is_success=False, message="No conformers within the energy window; aborting.")

            ref_pos = kept[0]["positions"]
            for k in kept:
                k["rmsd_to_conf0"] = _kabsch_rmsd(k["positions"], ref_pos)

            # 拷贝系综到 output_dir（多帧 xyz，注释行带 kcal/mol 相对能量）
            # 元素序列以产物帧为准：protonate/qcg 等模式的产物原子集合与输入不同。
            symbols = frames[0].symbols if frames[0].symbols else prepared.symbols
            xyz_path = os.path.join(out_dir, "confs.xyz")
            chunks = []
            for k in kept:
                lines = [str(natoms), f"conf_id={k['conf_id']} rel_energy_kcal={k['rel_energy_kcal']:.4f}"]
                for sym, p in zip(symbols, k["positions"]):
                    lines.append(f"{sym:<3} {p[0]:>14.6f} {p[1]:>14.6f} {p[2]:>14.6f}")
                chunks.append("\n".join(lines) + "\n")
            atomic_write_text(xyz_path, "".join(chunks))

            extra = (
                "Backend: CREST (GFN2-xTB, --quick). The ensemble was deduplicated by CREST; "
                "no further RMSD clustering was applied. "
                f"CREST run directory (persistent): {run.run_dir}"
            )
            if runtype == "nci":
                extra = (
                    "Backend: CREST --nci (GFN2-xTB, ellipsoid wall potential): the ensemble samples "
                    "NON-COVALENT arrangements of the input complex — hydrogen-bond networks and aggregate "
                    "geometries — not covalent conformers of a single molecule. "
                    f"CREST run directory (persistent): {run.run_dir}"
                )
            elif runtype == "qcg":
                extra = (
                    f"Backend: CREST --qcg (quantum cluster growth): {user_input.nsolv} explicit "
                    f"{user_input.solvent_smiles} molecule(s) were grown around the solute; the product "
                    "is the grown micro-solvated cluster geometry (solute + solvent shell), NOT a "
                    "bare-solute conformer, and its energy is the GFN-level cluster electronic energy "
                    f"from grow/qcg_energy.dat. To sample alternative shell arrangements, run "
                    f"mode='nci' on this cluster. CREST run directory (persistent): {run.run_dir}"
                )
            elif runtype in self._SINGLE_COMPONENT_RUNTYPES:
                extra = (
                    f"Backend: CREST --{runtype} (automated {'protomer' if runtype != 'tautomerize' else 'tautomer'} "
                    "screening). WARNING: the entries are DIFFERENT CHEMICAL SPECIES (protonation-site or "
                    "tautomer variants), not conformers of one connectivity, and the automated screening may "
                    "include chemically unreasonable pseudo-structures — review EVERY structure chemically "
                    "(protonation site, valence, charge) before using it for any follow-up calculation. "
                    "Relative energies are GFN2-xTB electronic energies of these distinct species. "
                    f"CREST run directory (persistent): {run.run_dir}"
                )
            if multi_fragment:
                extra += (
                    " NOTE: this input has multiple components, so --noreftopo was passed: the initial "
                    "topology check before the search was disabled (CREGEN's in-search topology checks "
                    "were NOT disabled). Any topology change is recorded in the run result's "
                    "topology_change field."
                )
            if counts["reactive_rescued"]:
                extra += (
                    f"{counts['reactive_rescued']} lowest-energy reactive conformer(s) outside the energy window were "
                    "additionally kept to avoid losing reactive conformers in pre-screening; their relative energies still use the global minimum as zero."
                )
            return self._finalize(user_input, kept, counts, xyz_path, extra_message=extra)

        except Exception as e:
            return ConformerSearch_output_schema(is_success=False, message=f"CREST backend failed: {e}")

    async def tool_call(self, user_input: ConformerSearch_input_schema, session: Session) -> ConformerSearch_output_schema:
        import asyncio

        # 前置校验：temperature<=0 会让 Boltzmann 布居除零/NaN；multiplicity<1 无物理意义。
        if user_input.temperature <= 0:
            return ConformerSearch_output_schema(
                is_success=False,
                message=(
                    f"temperature must be > 0 K for Boltzmann populations, got {user_input.temperature:g}. "
                    "Negative or zero temperature would produce NaN/non-finite populations."
                ),
            )
        if user_input.multiplicity < 1:
            return ConformerSearch_output_schema(
                is_success=False,
                message=f"multiplicity must be >= 1 (2S+1), got {user_input.multiplicity}.",
            )
        if user_input.mode != "conformers" and user_input.backend != "crest":
            return ConformerSearch_output_schema(
                is_success=False,
                message=(
                    f"mode='{user_input.mode}' is a CREST run type and requires backend='crest' "
                    f"(got backend='{user_input.backend}')."
                ),
            )
        if user_input.mode == "qcg":
            if not user_input.solvent_smiles:
                return ConformerSearch_output_schema(
                    is_success=False,
                    message="mode='qcg' requires solvent_smiles (one neutral solvent molecule, e.g. 'O').",
                )
            if user_input.nsolv < 1:
                return ConformerSearch_output_schema(
                    is_success=False,
                    message=f"mode='qcg' requires nsolv >= 1, got {user_input.nsolv}.",
                )
        elif user_input.solvent_smiles or user_input.nsolv:
            return ConformerSearch_output_schema(
                is_success=False,
                message="solvent_smiles/nsolv are only valid with mode='qcg'.",
            )

        # 路径语义收口：相对路径解析到 agent 工作目录（沙箱），绝对路径保持既有权限语义。
        out_dir = self._resolve_output_dir(user_input)
        if user_input.input_path:
            user_input.input_path = resolve_tool_path(self, user_input.input_path)
        user_input.output_dir = resolve_tool_path(self, out_dir)

        # CREST / RDKit 都是同步 CPU/子进程；必须离开 UI 事件循环，否则 TUI 假死。
        if user_input.backend == "crest":
            return await asyncio.to_thread(self._run_crest, user_input, user_input.output_dir)

        if not _RDKIT_AVAILABLE:
            return ConformerSearch_output_schema(
                is_success=False,
                message="RDKit is not installed. Install it with: pip install 'cloudra[chem]'"
            )
        return await asyncio.to_thread(self._run_rdkit, user_input, user_input.output_dir)


def get_class():
    return ConformerSearch
