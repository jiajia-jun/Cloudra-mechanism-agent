"""反应复合物组装：刚性放置采样 + 反应中心引导 + 约束预优化（Task 2 组装方案）。

**本模块的所有数值都是用户批准的具体值**（2026-09-11 计划 Task 2「组装方案（待批准后实施）」
的门禁，由用户选定方案 A）：

======================================  =========  ==================================================
参数                                     批准值     依据
======================================  =========  ==================================================
相对取向采样数                            32         Fibonacci 球面方向，确定性可复现
片间碰撞判据（最小原子间距）              1.0 Å      沿用仓库既有的碎片叠放判据（issue #19 修复引入）
片间解离判据（vdW 接触倍数）              1.5        最近片间原子对距离 > 1.5×两原子 vdW 半径和即
                                                    判为已解离（不是复合物），丢弃不交付
反应中心引导保留的放置数                  8          经反应中心距离打分后取最优（仅反应模式）
反应中心距离窗口                          1.8–2.6 Å  反应物/产物映射得到的反应中心对的预组织窗口
能量窗                                    6.0 kcal/mol 沿用 conformer_search 的既有默认值
重原子 RMSD 聚类阈值                      0.5 Å      沿用 conformer_search 的既有默认值
======================================  =========  ==================================================

两套模式（计划原文：「反应模式使用反应物/产物映射得到的反应中心引导组装，普通复合物模式
不凭空指定成键中心」）：

- **反应模式**：调用方给出 ``reaction_center``（反应物/产物映射得到的原子对，用**输入原子序号**）。
  放置按反应中心距离与窗口的偏离打分取前 8；随后用 MMFF94 在**反应中心距离约束**下预优化，
  仅当全部反应中心距离落入窗口后才**释放约束**做最后一次无约束弛豫。
- **普通复合物模式**：没有反应中心，因此**不设任何凭空指定的成键中心**；只做刚性放置采样 +
  碰撞剔除 + 无约束 MMFF94 弛豫，再按能量窗与 RMSD 聚类筛选。

「仅平移拉开距离」不算组装：平移只用来满足碰撞判据，候选由**旋转采样 + 弛豫后的能量/RMSD**
决定；弛豫后碎片塌回重叠的放置一律丢弃，弛豫后碎片间最近原子对超出
``max_interfragment_vdw_factor`` 倍 vdW 接触距离的放置同样作为**已解离**丢弃——两者都绝不
作为复合物候选交付。反应模式下约束未释放的候选，其能量是无约束单点重估（约束惩罚项不进
能量排序）。
"""

from __future__ import annotations

import os
from typing import Literal, Optional

from pydantic import BaseModel, Field

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.geometry import (
    fibonacci_sphere_directions,
    kabsch_rmsd,
    min_distance,
    rotate_about_axis,
    rotate_about_centroid,
    rotation_matrix_between,
)
from cloudra.tools.core.structure_artifacts import (
    TrajectoryArtifact,
    TrajectoryWriter,
    trajectory_artifact,
    write_trajectory_manifest,
)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    _RDKIT_AVAILABLE = True
except Exception:  # pragma: no cover - 仅在缺 chem 额外依赖时触发
    Chem = None
    AllChem = None
    _RDKIT_AVAILABLE = False

COMPLEX_XYZ_NAME = "complex_candidate_{index:03d}.xyz"
COMPLEX_MOL_NAME = "complex_candidate_{index:03d}.mol"
ASSEMBLY_JSON_NAME = "assembly.json"

MMFF_ENGINE = "MMFF94"
#: RDKit 自身的 MMFF 距离约束力常数默认值（``AllChem.MMFFAddDistanceConstraint``）。
MMFF_CONSTRAINT_FORCE_CONSTANT = 100.0

AssemblyStatus = Literal[
    "ok",              # 至少产出一个通过全部筛选的复合物候选
    "no_candidate",    # 采样过但没有任何放置通过碰撞/弛豫/能量窗筛选
    "not_applicable",  # 单组分输入（没有片间关系可组装）
    "unsupported",     # 力场缺参数/自旋不支持等，无法弛豫
]


class AssemblyParameters(BaseModel):
    """用户批准的组装参数。改动这些值等于改动科学决策，必须重新获批。"""

    orientations: int = Field(default=32, description="每个组分对的相对取向采样数（Fibonacci 球面）")
    min_interfragment_distance: float = Field(
        default=1.0, description="片间碰撞判据：任意两碎片原子间距必须 ≥ 此值（Å）"
    )
    max_interfragment_vdw_factor: float = Field(
        default=1.5,
        description="片间解离判据：弛豫后最近片间原子对的距离超过其 vdW 接触距离（两原子 "
                    "vdW 半径之和）的此倍数，即判为已解离——碎片只是被推开而没有相互作用，"
                    "丢弃不交付",
    )
    reaction_center_candidates: int = Field(
        default=8, description="反应模式下按反应中心距离打分后保留的放置数"
    )
    reaction_center_window: tuple[float, float] = Field(
        default=(1.8, 2.6), description="反应中心距离的预组织窗口（Å）：约束目标与释放条件"
    )
    energy_window_kcal: float = Field(default=6.0, description="候选保留的相对能量窗（kcal/mol）")
    rmsd_threshold: float = Field(default=0.5, description="重原子 RMSD 聚类阈值（Å）")
    relaxation_steps: int = Field(
        default=2000,
        description="单个放置每个弛豫阶段的迭代上限（**实现预算**，不是化学阈值）。"
                    "组装要跑 orientations 个放置 × 最多 2 个阶段，因此这里用 RDKit 的整块 "
                    "Minimize(maxIts=relaxation_steps) 而非逐迭代步进；逐迭代帧的完整轨迹由"
                    "每个**组分**的构建记录（见 structure_artifacts）",
    )


class AssemblyCandidate(BaseModel):
    """一个通过筛选的复合物候选。"""

    candidate_id: int
    placement_index: int = Field(description="来自第几个取向采样的刚性放置")
    energy_kcal: float = Field(description=f"{MMFF_ENGINE} 能量（kcal/mol）")
    rel_energy_kcal: float
    min_interfragment_distance: float = Field(description="弛豫后的最小片间原子距（Å）")
    reaction_center_distances: dict[str, float] = Field(
        default_factory=dict, description="反应模式下各反应中心对的距离（键 \"i-j\" → Å）"
    )
    reaction_center_in_window: Optional[bool] = Field(
        default=None, description="反应模式下全部反应中心对是否都落在批准窗口内"
    )
    constraint_released: bool = Field(description="反应模式下约束是否已释放并完成无约束弛豫")
    cluster_id: int = Field(description="重原子 RMSD 聚类编号（按能量升序贪心）")
    xyz_path: str
    mol_path: str
    trajectory_id: str


class AssemblyResult(BaseModel):
    """组装结果。"""

    status: AssemblyStatus
    message: str = ""
    parameters: AssemblyParameters = Field(default_factory=AssemblyParameters)
    mode: Literal["reaction", "complex"] = "complex"
    components: int = 0
    sampled_placements: int = 0
    collision_rejected: int = 0
    collapsed_after_relaxation: int = 0
    dissociated_after_relaxation: int = 0
    unconverged_after_relaxation: int = 0
    optimized_placements: int = 0
    candidates: list[AssemblyCandidate] = Field(default_factory=list)
    candidate_paths: list[str] = Field(default_factory=list, description="按能量升序的候选结构文件")
    trajectory_ids: list[str] = Field(default_factory=list)
    trajectory_manifest_path: str = ""
    artifact_path: str = ""
    diagnostics: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 组合分子（把逐组分结构拼成一个带坐标的 mol，供力场弛豫）
# ---------------------------------------------------------------------------


def combine_components(components) -> "Chem.Mol":
    """把已构建的组分拼成一个 RDKit Mol（保留原子顺序、电荷、立体化学与坐标）。

    ``components`` 为 ``(mol, conf_id)`` 序列。原子顺序即各组分依次拼接，和
    ``PreparedStructure.symbols`` 的顺序一致，因此输入原子序号映射（identity 表）继续成立。
    """
    combined = Chem.RWMol()
    offsets: list[int] = []
    offset = 0
    for mol, _conf_id in components:
        offsets.append(offset)
        for atom in mol.GetAtoms():
            new_atom = Chem.Atom(atom.GetAtomicNum())
            new_atom.SetFormalCharge(atom.GetFormalCharge())
            new_atom.SetChiralTag(atom.GetChiralTag())
            new_atom.SetNumExplicitHs(atom.GetNumExplicitHs())
            new_atom.SetNoImplicit(atom.GetNoImplicit())
            combined.AddAtom(new_atom)
        offset += mol.GetNumAtoms()
    stereo_to_set: list[tuple[int, int, object, int, int]] = []
    for (mol, _conf_id), base in zip(components, offsets):
        for bond in mol.GetBonds():
            begin = base + bond.GetBeginAtomIdx()
            end = base + bond.GetEndAtomIdx()
            combined.AddBond(begin, end, bond.GetBondType())
            new_bond = combined.GetBondBetweenAtoms(begin, end)
            new_bond.SetBondDir(bond.GetBondDir())
            if bond.GetStereo() == Chem.BondStereo.STEREONONE:
                continue
            stereo = list(bond.GetStereoAtoms())
            if len(stereo) != 2:
                raise ValueError(
                    f"bond {bond.GetBeginAtomIdx()}-{bond.GetEndAtomIdx()} carries stereo "
                    f"{bond.GetStereo()} but {len(stereo)} stereo atoms; refusing to guess the "
                    "reference atoms"
                )
            stereo_to_set.append(
                (begin, end, bond.GetStereo(), base + stereo[0], base + stereo[1])
            )

    # 两趟：先建齐全部键，再设立体化学。``SetStereoAtoms`` 会校验两个参考原子分别与本键的
    # begin/end 相连，而 sp2 立体的参考原子是远端取代基——若在通向它的那根单键还没加进来时
    # 就设，RDKit 直接抛 "endIdx not connected to end atom of bond"（多组分 + 立体标记的输入
    # 曾因此整条组装路径崩溃，见 GH #37；structure_builder 的同款重建早已按两趟写）。
    for begin, end, stereo, stereo_begin, stereo_end in stereo_to_set:
        new_bond = combined.GetBondBetweenAtoms(begin, end)
        new_bond.SetStereo(stereo)
        new_bond.SetStereoAtoms(stereo_begin, stereo_end)

    mol = combined.GetMol()
    Chem.SanitizeMol(mol)

    positions: list[list[float]] = []
    for component_mol, conf_id in components:
        conf = component_mol.GetConformer(conf_id)
        positions.extend([float(v) for v in conf.GetAtomPosition(i)]
                         for i in range(component_mol.GetNumAtoms()))
    conf = Chem.Conformer(mol.GetNumAtoms())
    for index, (x, y, z) in enumerate(positions):
        conf.SetAtomPosition(index, (x, y, z))
    mol.RemoveAllConformers()
    mol.AddConformer(conf, assignId=True)
    return mol


# ---------------------------------------------------------------------------
# 刚性放置采样
# ---------------------------------------------------------------------------


def _component_atom_groups(components) -> list[list[int]]:
    groups: list[list[int]] = []
    offset = 0
    for mol, _conf_id in components:
        groups.append(list(range(offset, offset + mol.GetNumAtoms())))
        offset += mol.GetNumAtoms()
    return groups


def _separate_along_axis(positions, groups, required_gap: float):
    """仅用平移把片间最小距离抬到 ``required_gap`` 之上。

    平移方向是**最近片间原子对的连线方向**（把当前碎片沿它推离最近碎片），不是固定坐标轴；
    完全重叠（方向退化）时才确定性地落到 +x。平移**只用于满足碰撞判据**，它本身不是组装：
    候选由旋转采样与弛豫后的能量/RMSD 决定。
    """
    import numpy as np

    positions = np.asarray(positions, dtype=float).copy()
    placed: list[list[int]] = []
    for group in groups:
        placed.append(list(group))
        if len(placed) < 2:
            continue
        for _ in range(200):
            worst = float("inf")
            worst_vec = None
            for earlier in placed[:-1]:
                a = positions[earlier]
                b = positions[group]
                diff = b[None, :, :] - a[:, None, :]
                dist = np.sqrt((diff ** 2).sum(axis=2))
                index = np.unravel_index(int(np.argmin(dist)), dist.shape)
                if float(dist[index]) < worst:
                    worst = float(dist[index])
                    worst_vec = diff[index]
            if worst >= required_gap:
                break
            norm = float(np.linalg.norm(worst_vec))
            step = (worst_vec / norm) if norm > 1e-12 else np.array([1.0, 0.0, 0.0])
            positions[group] = positions[group] + step * required_gap
    return positions


def _sample_placements(mol, groups, parameters: AssemblyParameters):
    """枚举刚性放置：对每个非首碎片按 Fibonacci 方向做刚体旋转 + 确定性绕轴扭转，再平移满足碰撞判据。

    方向索引就是 ``sample % len(directions)``——不与 sample 做乘法，避免 gcd 退化（例如
    ``(sample*7 + group*3) % 7`` 会把全部采样压到同一方向）。扭转角随 sample 在 0..2π 均匀
    取值，完全确定性。片内几何全程冻结（只做刚体旋转 + 整体平移）。返回 ``[(placement_index, positions)]``。
    """
    import numpy as np

    base = np.asarray(mol.GetConformer().GetPositions(), dtype=float)
    directions = fibonacci_sphere_directions(parameters.orientations)
    placements = []
    for sample in range(parameters.orientations):
        positions = base.copy()
        direction = directions[sample % len(directions)]
        rotation = rotation_matrix_between((0.0, 0.0, 1.0), direction)
        twist_degrees = 360.0 * sample / parameters.orientations
        for group_index in range(1, len(groups)):
            positions = rotate_about_centroid(positions, groups[group_index], rotation)
            centroid = positions[groups[group_index]].mean(axis=0)
            positions = rotate_about_axis(
                positions, groups[group_index],
                centroid, centroid + np.asarray(direction, dtype=float), twist_degrees,
            )
        positions = _separate_along_axis(positions, groups, parameters.min_interfragment_distance)
        placements.append((sample, positions))
    return placements


def _set_positions(mol, conf_id: int, positions) -> None:
    conf = mol.GetConformer(conf_id)
    for index, (x, y, z) in enumerate(positions):
        conf.SetAtomPosition(index, (float(x), float(y), float(z)))


# ---------------------------------------------------------------------------
# 弛豫（含反应中心约束的添加与释放）
# ---------------------------------------------------------------------------


def _mmff_force_field(mol, conf_id: int):
    """组装用的 MMFF94 力场。

    **必须** ``ignoreInterfragInteractions=False``：RDKit 的默认值会让各碎片独立收敛到
    各自的极小值，于是所有放置得到同一个能量、相对能量全零——这正是 issue #19 的症状，
    那样的"复合物候选"没有任何片间信息。
    """
    props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
    if props is None:
        return None
    return AllChem.MMFFGetMoleculeForceField(
        mol, props, confId=conf_id, ignoreInterfragInteractions=False,
    )


def _relax_with_trajectory(mol, conf_id: int, writer: TrajectoryWriter,
                           parameters: AssemblyParameters, constraints: list[tuple[int, int]],
                           release_when_in_window: Optional[tuple[float, float]],
                           guided_windows: Optional[list[tuple[int, int, float, float]]] = None,
                           ) -> tuple[bool, bool, str]:
    """弛豫一个放置；可选加反应中心距离约束并按批准窗口条件释放。

    返回 ``(converged, constraint_released, failure)``。

    **轨迹粒度（如实记录，不宣称逐迭代）**：组装要跑 ``orientations`` 个放置、每个最多两个
    阶段，逐迭代落帧会产生数百 MB 且耗时以分钟计，因此这里每个阶段只记录**首末两帧**
    （``Minimize(maxIts=relaxation_steps)`` 整块调用），并在轨迹 note 里写清粒度。
    逐迭代的完整轨迹由每个**组分**的构建负责（``structure_builder`` → ``TrajectoryWriter``）。
    """
    released = False
    try:
        ff = _mmff_force_field(mol, conf_id)
        if ff is None:
            return False, False, "MMFF94 could not be constructed for the assembled complex"
        windows = guided_windows if guided_windows is not None else [
            (left, right, *release_when_in_window) for left, right in constraints
        ]
        for left, right, low, high in windows:
            ff.MMFFAddDistanceConstraint(
                left, right, False,
                float(low), float(high),
                MMFF_CONSTRAINT_FORCE_CONSTANT,
            )
        ff.Initialize()
        writer.append(writer.frame_count, _positions(mol, conf_id), float(ff.CalcEnergy()), _max_grad(ff))
        code = int(ff.Minimize(maxIts=parameters.relaxation_steps))
        writer.append(writer.frame_count, _positions(mol, conf_id),
                      float(ff.CalcEnergy()), _max_grad(ff))
        if code != 0:
            return False, False, ""

        if constraints and release_when_in_window is not None and guided_windows is None:
            low, high = release_when_in_window
            distances = [_distance(mol, conf_id, a, b) for a, b in constraints]
            if not all(low <= d <= high for d in distances):
                return True, False, ""
            released = True
            ff_free = _mmff_force_field(mol, conf_id)
            if ff_free is None:
                return False, released, "MMFF94 could not be constructed for unconstrained relaxation"
            ff_free.Initialize()
            writer.append(writer.frame_count, _positions(mol, conf_id),
                          float(ff_free.CalcEnergy()), _max_grad(ff_free))
            free_code = int(ff_free.Minimize(maxIts=parameters.relaxation_steps))
            writer.append(writer.frame_count, _positions(mol, conf_id),
                          float(ff_free.CalcEnergy()), _max_grad(ff_free))
            if free_code != 0:
                return False, released, ""
        return True, released, ""
    except Exception as exc:  # noqa: BLE001 - 异常前已写入的帧保留
        return False, released, f"{type(exc).__name__}: {exc}"


def _positions(mol, conf_id: int) -> list[list[float]]:
    conf = mol.GetConformer(conf_id)
    return [[float(v) for v in conf.GetAtomPosition(i)] for i in range(mol.GetNumAtoms())]


def _max_grad(ff) -> Optional[float]:
    grad = [abs(float(g)) for g in ff.CalcGrad()]
    return max(grad) if grad else None


def _distance(mol, conf_id: int, left: int, right: int) -> float:
    import numpy as np

    conf = mol.GetConformer(conf_id)
    a = np.asarray(conf.GetAtomPosition(left), dtype=float)
    b = np.asarray(conf.GetAtomPosition(right), dtype=float)
    return float(np.linalg.norm(a - b))


def _min_interfragment_gap(positions, groups) -> tuple[float, tuple[int, int]]:
    """片间最小原子距，以及取得该值的原子对（完整结构原子序号）。"""
    import numpy as np

    positions = np.asarray(positions, dtype=float)
    best = float("inf")
    best_pair = (groups[0][0], groups[1][0])
    for left in range(len(groups)):
        for right in range(left + 1, len(groups)):
            a = positions[groups[left]]
            b = positions[groups[right]]
            diff = a[:, None, :] - b[None, :, :]
            dist = np.sqrt((diff ** 2).sum(axis=2))
            index = np.unravel_index(int(np.argmin(dist)), dist.shape)
            if float(dist[index]) < best:
                best = float(dist[index])
                best_pair = (groups[left][index[0]], groups[right][index[1]])
    return best, best_pair


def _greedy_heavy_atom_clusters(kept_positions, heavy_indices, threshold: float):
    """按能量升序贪心聚类，**只比较重原子坐标**（与 conformer_search 的 RemoveHs 口径一致）。

    羟基/甲基氢的取向噪声不该把同一个复合物拆成多簇。返回 ``(每个候选的 cluster_id, 各簇代表索引)``。
    """
    cluster_ids: list[int] = []
    representatives: list[int] = []
    for index, positions in enumerate(kept_positions):
        heavy_positions = [positions[i] for i in heavy_indices]
        target = -1
        for cluster_index, representative in enumerate(representatives):
            representative_heavy = [kept_positions[representative][i] for i in heavy_indices]
            if kabsch_rmsd(heavy_positions, representative_heavy) <= threshold:
                target = cluster_index
                break
        if target < 0:
            target = len(representatives)
            representatives.append(index)
        cluster_ids.append(target)
    return cluster_ids, representatives


# ---------------------------------------------------------------------------
# 公开入口
# ---------------------------------------------------------------------------


def assemble(*, components, output_dir: str, parameters: Optional[AssemblyParameters] = None,
             reaction_center: Optional[list[tuple[int, int]]] = None,
             guided_windows: Optional[list[tuple[int, int, float, float]]] = None,
             seed: int = 42) -> AssemblyResult:
    """组装反应复合物/普通复合物。

    ``components``：``(mol, conf_id)`` 序列（来自 ``structure_builder`` 的逐组分构建）。
    ``reaction_center``：反应物/产物映射得到的原子对（**完整结构的输出原子序号**，0-based）。
    给出即进入反应模式；不给则进入普通复合物模式（不凭空指定成键中心）。

    本函数是同步的（力场弛豫是 CPU 密集）；异步调用方须经 ``asyncio.to_thread`` 卸载。
    """
    if not _RDKIT_AVAILABLE:
        raise RuntimeError("RDKit is not installed; assembly requires it.")
    params = parameters or AssemblyParameters()
    os.makedirs(output_dir, exist_ok=True)
    if len(components) < 2:
        return _finalize(AssemblyResult(
            status="not_applicable",
            message="assembly needs at least two components; a single component has no inter-fragment geometry",
            parameters=params, components=len(components), mode="complex",
        ), output_dir)

    groups = _component_atom_groups(components)
    mol = combine_components(components)
    conf_id = mol.GetConformer().GetId()
    mode: Literal["reaction", "complex"] = "reaction" if reaction_center or guided_windows else "complex"
    diagnostics: list[str] = []
    if mode == "reaction":
        diagnostics.append(
            "reaction mode: placements are guided by the reaction center pairs derived from the "
            "reactant/product mapping; intra-fragment geometry stays rigid during placement"
        )
    else:
        diagnostics.append(
            "complex mode: no reaction center was provided, so NO bonding center is invented; "
            "placements are sampled by relative orientation only"
        )

    # 取向采样是确定性的（Fibonacci 方向），与 random_seed 无关：同一次构建的组装可复现。
    # seed 仍然进入每条轨迹的元数据（逐组分的构象嵌入确实随它变化）。
    placements = _sample_placements(mol, groups, params)
    collision_rejected = 0
    scored: list[tuple[float, int, list[list[float]]]] = []
    for placement_index, positions in placements:
        worst = min(
            min_distance(positions, groups[i], groups[j])
            for i in range(len(groups)) for j in range(i + 1, len(groups))
        )
        if worst < params.min_interfragment_distance:
            collision_rejected += 1
            continue
        if guided_windows or reaction_center:
            _set_positions(mol, conf_id, positions)
            deviations = []
            windows = guided_windows if guided_windows is not None else [
                (left, right, *params.reaction_center_window)
                for left, right in reaction_center or []
            ]
            for left, right, low, high in windows:
                distance = _distance(mol, conf_id, left, right)
                if distance < low:
                    deviations.append(low - distance)
                elif distance > high:
                    deviations.append(distance - high)
                else:
                    deviations.append(0.0)
            scored.append((max(deviations), placement_index, positions))
        else:
            scored.append((0.0, placement_index, positions))

    if guided_windows or reaction_center:
        scored.sort(key=lambda item: (item[0], item[1]))
        scored = scored[: params.reaction_center_candidates]
        diagnostics.append(
            f"kept the best {len(scored)} of {len(placements)} sampled placements by "
            f"maximum distance-window deviation; windows={windows}"
        )

    artifacts: list[TrajectoryArtifact] = []
    candidates: list[AssemblyCandidate] = []
    candidate_positions: list[list[list[float]]] = []
    collapsed = 0
    dissociated = 0
    optimized = 0
    unconverged = 0
    for _score, placement_index, positions in scored:
        _set_positions(mol, conf_id, positions)
        trajectory_id = f"placement{placement_index:03d}-{MMFF_ENGINE.lower()}-attempt1"
        writer = TrajectoryWriter(
            output_dir, trajectory_id, f"placement{placement_index:03d}", 1, MMFF_ENGINE,
            [a.GetSymbol() for a in mol.GetAtoms()], seed,
        )
        converged, released, failure = _relax_with_trajectory(
            mol, conf_id, writer, params,
            constraints=list(reaction_center or []),
            release_when_in_window=(params.reaction_center_window if reaction_center else None),
            guided_windows=guided_windows,
        )
        if failure:
            if writer.frame_count == 0:
                # 力场构造失败时一帧都没写：先补上刚性放置这一帧，失败轨迹才有内容可查
                writer.append(0, _positions(mol, conf_id), 0.0, None)
            record = writer.finish(-3, "failed", failure=failure)
            artifacts.append(trajectory_artifact(record))
            diagnostics.append(f"placement {placement_index}: relaxation raised {failure}")
            continue
        if guided_windows is not None:
            note = "guided distance constraints kept during relaxation"
        elif reaction_center:
            note = "reaction-center constraint " + (
                "released and re-relaxed unconstrained" if released else "kept"
            )
        else:
            note = "no reaction-center constraint (complex mode)"
        note += (
            f"; frames are phase boundaries only (maxIts={params.relaxation_steps} per phase), "
            "full per-iteration trajectories live in the per-component builds"
        )
        record = writer.finish(
            0 if converged else 1, "converged" if converged else "not_converged", notes=[note],
        )
        artifacts.append(trajectory_artifact(record))
        optimized += 1

        if not converged:
            unconverged += 1
            diagnostics.append(
                f"placement {placement_index}: relaxation did not converge within "
                f"{params.relaxation_steps} steps - candidate discarded, never delivered as a complex"
            )
            continue

        min_gap, closest_pair = _min_interfragment_gap(
            mol.GetConformer(conf_id).GetPositions(), groups,
        )
        if min_gap < params.min_interfragment_distance:
            collapsed += 1
            diagnostics.append(
                f"placement {placement_index}: relaxation collapsed the components to {min_gap:.3f} A "
                f"(< {params.min_interfragment_distance} A) - discarded, never delivered as a complex"
            )
            continue
        periodic_table = Chem.GetPeriodicTable()
        contact = (
            periodic_table.GetRvdw(mol.GetAtomWithIdx(closest_pair[0]).GetAtomicNum())
            + periodic_table.GetRvdw(mol.GetAtomWithIdx(closest_pair[1]).GetAtomicNum())
        )
        if min_gap > params.max_interfragment_vdw_factor * contact:
            dissociated += 1
            diagnostics.append(
                f"placement {placement_index}: relaxation left the closest inter-fragment pair "
                f"({closest_pair[0]}-{closest_pair[1]}) {min_gap:.3f} A apart, beyond "
                f"{params.max_interfragment_vdw_factor}x its vdW contact distance ({contact:.3f} A) - "
                "the fragments are dissociated, not a complex; discarded, never delivered as a complex"
            )
            continue

        if (reaction_center or guided_windows) and not released:
            # 约束未释放的候选 final_frame.energy 含约束惩罚项（k=100 的距离约束），与已释放
            # 候选的无约束能量不可直接相减比较；先用无约束力场对最终几何做单点重估再进排序。
            ff_free = _mmff_force_field(mol, conf_id)
            if ff_free is None:
                diagnostics.append(
                    f"placement {placement_index}: the constraint was not released and an "
                    "unconstrained MMFF94 single point could not be constructed, so its "
                    "constraint-penalized energy is not comparable - candidate dropped"
                )
                continue
            ff_free.Initialize()
            energy_kcal = float(ff_free.CalcEnergy())
            diagnostics.append(
                f"placement {placement_index}: the reaction-center constraint was not released, so "
                "the trajectory energy contains the constraint penalty; the reported candidate "
                "energy is an unconstrained MMFF94 single point on the final geometry instead"
            )
        else:
            energy_kcal = float(record.final_frame.energy)

        distances = {
            f"{left}-{right}": _distance(mol, conf_id, left, right)
            for left, right in (reaction_center or [])
        }
        checked_windows = guided_windows if guided_windows is not None else [
            (left, right, *params.reaction_center_window) for left, right in reaction_center or []
        ]
        candidates.append(AssemblyCandidate(
            candidate_id=len(candidates),
            placement_index=placement_index,
            energy_kcal=energy_kcal,
            rel_energy_kcal=0.0,
            min_interfragment_distance=min_gap,
            reaction_center_distances=distances,
            reaction_center_in_window=(all(
                low <= _distance(mol, conf_id, left, right) <= high
                for left, right, low, high in checked_windows
            ) if checked_windows else None),
            constraint_released=released,
            cluster_id=-1,
            xyz_path="",
            mol_path="",
            trajectory_id=record.trajectory_id,
        ))
        candidate_positions.append(_positions(mol, conf_id))

    if not candidates:
        result = AssemblyResult(
            status="no_candidate",
            message=(
                f"no usable complex candidate: {len(placements)} placements sampled, "
                f"{collision_rejected} rejected by the {params.min_interfragment_distance} A collision "
                f"criterion, {unconverged} did not converge during relaxation, "
                f"{collapsed} collapsed back to overlap during relaxation, "
                f"{dissociated} relaxed beyond the dissociation limit "
                f"({params.max_interfragment_vdw_factor}x the vdW contact distance). No structure was "
                "returned as a complex."
            ),
            parameters=params, mode=mode, components=len(components),
            sampled_placements=len(placements), collision_rejected=collision_rejected,
            unconverged_after_relaxation=unconverged,
            collapsed_after_relaxation=collapsed, dissociated_after_relaxation=dissociated,
            optimized_placements=optimized,
            trajectory_ids=[a.trajectory_id for a in artifacts],
            trajectory_manifest_path=write_trajectory_manifest(output_dir, artifacts) if artifacts else "",
            diagnostics=diagnostics,
        )
        return _finalize(result, output_dir)

    best = min(c.energy_kcal for c in candidates)
    for candidate in candidates:
        candidate.rel_energy_kcal = candidate.energy_kcal - best

    kept = [
        (candidate, positions)
        for candidate, positions in zip(candidates, candidate_positions)
        if guided_windows is not None or candidate.rel_energy_kcal <= params.energy_window_kcal
    ]
    dropped = len(candidates) - len(kept)
    if dropped:
        diagnostics.append(
            f"{dropped} candidate(s) fell outside the {params.energy_window_kcal} kcal/mol window"
        )
    kept.sort(key=lambda item: (item[0].rel_energy_kcal, item[0].placement_index))

    # 重原子 RMSD 聚类（按能量升序贪心），每簇保留最低能代表。
    # 只比较重原子坐标（与 conformer_search 的 RemoveHs 口径一致）：羟基/甲基氢的取向噪声
    # 不该把同一个复合物拆成多簇。
    heavy_indices = [
        index for index in range(mol.GetNumAtoms())
        if mol.GetAtomWithIdx(index).GetAtomicNum() > 1
    ]
    if guided_windows is not None:
        # A lower-energy heavy-atom representative may fail an H-involving
        # window while another member passes. The caller qualifies all frames
        # first and clusters only the qualified subset.
        cluster_ids = list(range(len(kept)))
        cluster_representatives = list(range(len(kept)))
    else:
        cluster_ids, cluster_representatives = _greedy_heavy_atom_clusters(
            [positions for _candidate, positions in kept], heavy_indices, params.rmsd_threshold,
        )
    for index, cluster_id in enumerate(cluster_ids):
        kept[index][0].cluster_id = cluster_id

    if guided_windows is not None:
        diagnostics.append(
            f"{len(kept)} guided placement(s) retained for strict qualification before "
            f"{params.rmsd_threshold} A heavy-atom RMSD clustering"
        )
    else:
        diagnostics.append(
            f"{len(kept)} candidate(s) after the energy window collapsed to "
            f"{len(cluster_representatives)} cluster representative(s) at {params.rmsd_threshold} A "
            "heavy-atom RMSD"
        )

    representatives = [kept[index][0] for index in cluster_representatives]
    paths: list[str] = []
    for index, candidate in enumerate(representatives):
        candidate.candidate_id = index
        _set_positions(mol, conf_id, kept[cluster_representatives[index]][1])
        xyz_path = os.path.join(output_dir, COMPLEX_XYZ_NAME.format(index=index))
        mol_path = os.path.join(output_dir, COMPLEX_MOL_NAME.format(index=index))
        atomic_write_text(xyz_path, _render_xyz(mol, conf_id, candidate))
        atomic_write_text(mol_path, Chem.MolToMolBlock(mol, confId=conf_id))
        candidate.xyz_path = xyz_path
        candidate.mol_path = mol_path
        paths.append(xyz_path)

    selection_detail = (
        "guided relaxation; strict qualification and clustering follow"
        if guided_windows is not None else
        f"the {params.energy_window_kcal} kcal/mol energy window and "
        f"{params.rmsd_threshold} A heavy-atom RMSD clustering"
    )
    result = AssemblyResult(
        status="ok",
        message=(
            f"{len(representatives)} complex candidate(s) from {len(placements)} sampled placements "
            f"({mode} mode). Candidates satisfy the {params.min_interfragment_distance} A inter-fragment "
            f"collision criterion, the dissociation limit ({params.max_interfragment_vdw_factor}x the "
            f"vdW contact distance), "
            f"{selection_detail}."
        ),
        parameters=params, mode=mode, components=len(components),
        sampled_placements=len(placements), collision_rejected=collision_rejected,
        unconverged_after_relaxation=unconverged,
        collapsed_after_relaxation=collapsed, dissociated_after_relaxation=dissociated,
        optimized_placements=optimized,
        candidates=representatives, candidate_paths=paths,
        trajectory_ids=[a.trajectory_id for a in artifacts],
        trajectory_manifest_path=write_trajectory_manifest(output_dir, artifacts) if artifacts else "",
        diagnostics=diagnostics,
    )
    return _finalize(result, output_dir)


def _render_xyz(mol, conf_id: int, candidate: AssemblyCandidate) -> str:
    conf = mol.GetConformer(conf_id)
    lines = [
        str(mol.GetNumAtoms()),
        (
            f"assembled complex candidate {candidate.candidate_id} "
            f"(placement {candidate.placement_index}) "
            f"rel_energy_kcal={candidate.rel_energy_kcal:.4f} "
            f"min_interfragment_distance={candidate.min_interfragment_distance:.4f}"
        ),
    ]
    for index in range(mol.GetNumAtoms()):
        symbol = mol.GetAtomWithIdx(index).GetSymbol()
        x, y, z = (float(v) for v in conf.GetAtomPosition(index))
        lines.append(f"{symbol:<3} {x:>16.8f} {y:>16.8f} {z:>16.8f}")
    return "\n".join(lines) + "\n"


def _finalize(result: AssemblyResult, output_dir: str) -> AssemblyResult:
    result.artifact_path = os.path.join(output_dir, ASSEMBLY_JSON_NAME)
    atomic_write_text(result.artifact_path, result.model_dump_json(indent=2) + "\n")
    return result
