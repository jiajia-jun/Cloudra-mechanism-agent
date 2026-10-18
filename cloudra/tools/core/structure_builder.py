"""分片建模与逐步轨迹的**唯一**实现（issue #33 / #19）。

存在理由：``smiles_to_mol`` / ``qm_input_writer`` / ``conformer_search`` 过去各自复制一份
"SMILES → AddHs → EmbedMolecule → MMFFOptimizeMolecule"，于是

1. 同一缺陷要在三处分别修，且 RDKit 后端的片段叠放修复没有覆盖另外两处与 CREST 种子分支；
2. "``MMFFOptimizeMolecule`` 返回 0"被当作"坐标可用"，导致互穿几何（实测 F–C 0.1392 Å）
   被喂给 CREST/xTB，底层报 ``|grad| > 500`` 秒退（见 tests/fixtures/chemtool_issue33/）。

本模块把建模收成一条确定性流水线：

    prepare_structure(request) -> PreparedStructure

- **拆分**：按分子图连通分量拆分，保留输入原子序号映射；点号不是"可删除的盐"，
  单原子离子（如 ``[F-]``）也作为独立组分保留。
- **身份**：新增的氢按 ``(父重原子输入序号, 该父原子上的第 k 个氢)`` 登记稳定身份，
  **绝不**用 ``AddHs`` 之后的数组下标充当跨反应映射。
- **构建**：已有完整几何原样保留；无坐标时逐组分嵌入 + 力场优化，每一步迭代落一帧轨迹；
  失败与不收敛的轨迹同样保留。真实坐标可继续计算，不表示已成为力场极小值。
- **开壳层**：按声明电荷和总多重度检查电子数奇偶性/范围；自由基数仅作诊断。只生成
  未优化的 ETKDG 种子，跳过 MMFF/UFF，不把种子冒充科学确证的驻点。
  显式电子态声明优先；即使声明为闭壳层，带局域自由基标记的图仍保守地跳过力场。
- **不冒充成功**：可处理状态一律走 ``BuildStatus`` 枚举；"坐标已生成"或"优化返回 0"
  都不构成"几何可用"。

**组装**：多组分体系在本模块内交给 ``complex_assembly``（参数已由用户批准，见该模块
docstring 的参数表）产出**复合物候选**。组装需要已嵌入的组分坐标，因此 ``embed=False``
（只做结构解析）对多组分输入返回 ``assembly_failed``；组装跑不出候选时报 ``assembly_failed``
而不是把逐组分或平移拉开的坐标当成"复合物已生成"——后者正是本模块要消除的行为。
可经 ``BuildStrategy.reaction_center`` 给出反应物/产物映射得到的反应中心，进入反应模式
（反应中心引导 + 距离约束预优化 + 条件释放约束）；不给则按普通复合物模式，不凭空指定成键中心。
"""

from __future__ import annotations

import math
import os
from typing import Literal, Optional

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.complex_assembly import (
    AssemblyParameters,
    AssemblyResult,
    _min_interfragment_gap,
    assemble,
)
from cloudra.tools.core.electronic_state import electronic_state_details, electronic_state_issue
from cloudra.tools.core.molecule import Molecule, copy_conformer, renumber_atoms
from cloudra.tools.core.structure_artifacts import (
    FORCE_FIELD_ENERGY_UNIT,
    TrajectoryArtifact,
    TrajectoryRecord,
    TrajectoryWriter,
    trajectory_artifact,
    write_trajectory_manifest,
)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdDetermineBonds
    _RDKIT_AVAILABLE = True
except Exception:  # pragma: no cover - 仅在缺 chem 额外依赖时触发
    Chem = None
    AllChem = None
    rdDetermineBonds = None
    _RDKIT_AVAILABLE = False

#: 构建产物目录的**唯一**名字。三个调用入口（smiles_to_mol / qm_input_writer /
#: conformer_search）必须一致，否则同一个工作区会出现 structure_build / <stem>_build /
#: smiles_to_mol_build 三种名字，逐迭代帧又很多，目录会很快失控。
BUILD_DIR_NAME = "structure_build"


def build_artifact_dir(base_dir: str, slug: str = "") -> str:
    """构建产物目录的唯一规则：``<base_dir>/structure_build[/<slug>]``。

    ``slug`` 用于把**并存的**多个结构隔开（例如同一个目录里连续转换两个分子）：
    给它时目录是 ``structure_build/<slug>``，同一父目录下不会互相覆盖。
    工具自己的输出目录已经是 per-structure 的（如 conformer_search 的 ``<stem>_confs``）
    时不必再给 slug。
    """
    root = os.path.join(base_dir, BUILD_DIR_NAME)
    return os.path.join(root, slug) if slug else root


PREPARED_JSON_NAME = "prepared_structure.json"
PREPARED_XYZ_NAME = "prepared.xyz"
PREPARED_MOL_NAME = "prepared.mol"

#: MMFF94 与 UFF 能量的零点不同（可差 ~17 kcal/mol），因此跨力场的能量**不可比**。
#: 这里只记录引擎名，绝不把两个引擎的能量放进同一次排序。
MMFF_ENGINE = "MMFF94"
UFF_ENGINE = "UFF"

BuildStatus = Literal[
    "ok",                  # 已按请求完成：单一组分，或多组分经已批准的组装产出了复合物候选
    "assembly_failed",     # 多组分且组装未产出任何通过筛选的复合物候选
    "charge_mismatch",     # 形式电荷总和与请求的总电荷不一致
    "unsupported_spin",    # 总电子数/自旋声明不合法，或所声明电子态/图不支持力场组装
    "missing_parameters",  # 力场缺参数，无法优化该组分
    "optimization_failed", # 组分优化未收敛或抛异常
    "invalid_input",       # 输入无法解析
    "invalid_reaction_center",  # 反应中心引用了构建后结构中不存在的原子
]

EmbedStatus = Literal["embedded", "not_required", "failed"]
OptimizationStatus = Literal[
    "converged",
    "not_converged",
    "failed",
    "not_required",       # 单原子组分无需力场；未请求嵌入/优化时同样如此
    "missing_parameters",
    "skipped_electronic_state",  # 电子态声明或自由基图标记需避开力场，仅生成未优化种子
]

# 不满足力场极小值资格的优化状态；未收敛末帧仍可能是下一种方法的种子。
_NON_USABLE_OPTIMIZATION = ("failed", "not_converged")


class StructureInput(BaseModel):
    """结构来源。外部文本与内部 Mol 在这里归一。"""

    kind: Literal["smiles", "mol_block", "xyz_text", "molecule"] = Field(description="输入类型")
    value: str | Molecule = Field(description="原生 Mol 或入口结构文本")

    @field_validator("value", mode="before")
    @classmethod
    def parse_native_molecule(cls, value, info):
        if info.data.get("kind") == "molecule":
            return TypeAdapter(Molecule).validate_python(value)
        return value


class BuildStrategy(BaseModel):
    """已批准的构建策略。

    当前**只有** ``per_component`` 一种，且它明确不含任何组装采样：多组分体系只做
    逐组分构建。新的策略名必须在组装参数获批后才允许加入，禁止用默认值夹带未获批行为。
    """

    name: Literal["per_component"] = Field(
        default="per_component",
        description="构建策略标识。per_component：逐组分独立嵌入 + 力场优化，不做任何片间组装",
    )
    embed: bool = Field(
        default=True,
        description="是否嵌入 3D 坐标。False 时只做结构解析（拆分/加氢/身份表/电荷自检），"
                    "不产生坐标也不产生轨迹——供自己的集成引擎（如构象系综搜索）复用解析结果",
    )
    optimize: bool = Field(
        default=True,
        description="是否对组分做力场优化（仅在 embed=True 时生效）。开壳层声明或自由基图标记"
        "始终跳过力场，其坐标仅作为未优化种子。",
    )
    max_optimization_steps: int = Field(
        default=20000,
        description="单个组分单次优化的迭代上限；达上限未收敛记为 not_converged（绝不记为成功）。"
                    "逐迭代 Minimize 的实测迭代数是千级到万级（辛烷 11,371 步），故上限取此量级",
    )
    assembly: AssemblyParameters = Field(
        default_factory=AssemblyParameters,
        description="多组分输入的组装参数。默认值即用户批准的具体数值（见 complex_assembly 模块）",
    )
    reaction_center: list[tuple[int, int]] = Field(
        default_factory=list,
        description="反应物/产物映射得到的反应中心原子对（完整结构的输出原子序号，0-based）。"
                    "给出即按反应模式组装（反应中心引导 + 距离约束预优化 + 条件释放约束）；"
                    "不给则按普通复合物模式组装，不凭空指定成键中心",
    )
    guided_windows: list[tuple[int, int, float, float]] = Field(
        default_factory=list,
        description="内部预组织距离窗口：(0-based i, j, min Å, max Å)；为空保持原组装行为",
    )


class PreparationRequest(BaseModel):
    """``prepare_structure`` 的请求：输入、电子态信息、输出目录与已批准策略。"""

    structure: StructureInput
    output_dir: str = Field(description="本构建产物的输出目录（由本模块独占，不做二级嵌套）")
    total_charge: int = Field(default=0, description="体系总电荷，必须等于各组分形式电荷之和")
    multiplicity: int = Field(default=1, description="自旋多重度 2S+1")
    electronic_character: Literal["closed_shell", "open_shell"] | None = Field(
        default=None,
        description="显式电子态性质；open_shell 支持开壳层单重态。省略时仅依据所声明多重度和"
        "分子图自由基标记判断是否应避开闭壳层力场，不推断基态或自旋耦合。",
    )
    random_seed: int = Field(default=42, description="构象嵌入随机种子，写入轨迹元数据")
    strategy: BuildStrategy = Field(default_factory=BuildStrategy)


class AtomIdentity(BaseModel):
    """跨帧稳定原子身份。

    ``index`` 只是**本构建输出坐标数组**中的位置，会随拆分/加氢而变；真正的身份是
    ``origin`` 加相应的输入序号。跨反应原子映射必须用 ``input_atom_index`` /
    ``(parent_input_atom_index, hydrogen_ordinal)``，不得用 ``index``。
    """

    index: int = Field(description="本构建输出原子顺序中的位置（0-based，仅供本产物内部使用）")
    symbol: str
    component_id: str = Field(description="所属组分编号")
    origin: Literal["input_atom", "added_hydrogen"] = Field(
        description="input_atom：来自输入结构；added_hydrogen：由 AddHs 补的显式氢"
    )
    input_atom_index: Optional[int] = Field(
        default=None, description="origin=input_atom 时的输入原子序号（0-based，加氢前）"
    )
    parent_input_atom_index: Optional[int] = Field(
        default=None, description="origin=added_hydrogen 时该氢所连重原子的输入原子序号"
    )
    hydrogen_ordinal: Optional[int] = Field(
        default=None,
        description="origin=added_hydrogen 时该父原子上的第几个氢（按确定性顺序，从 1 起）",
    )


class BuildComponent(BaseModel):
    """一个可独立处理的组分（分子图连通分量）。"""

    component_id: str = Field(description="组分编号，如 frag0")
    mol: Molecule
    source_atom_indices: list[int] = Field(description="所属输入原子序号（加氢前，0-based，升序）")
    embed_status: EmbedStatus
    optimization_status: OptimizationStatus
    engine: str = Field(default="", description=f"实际使用的力场（{MMFF_ENGINE}/{UFF_ENGINE}）或空串")
    trajectory_id: str = Field(default="", description="该组分最后一条轨迹的编号；无轨迹时为空")
    final_energy: Optional[float] = Field(
        default=None, description=f"终态力场能量（{FORCE_FIELD_ENERGY_UNIT}）；无轨迹时为 None"
    )
    mol_path: str = Field(default="", description="该组分的 MOL 文件（连接表/立体化学；有坐标时含坐标）")
    xyz_path: str = Field(
        default="", description="该组分带坐标的 xyz（含稳定身份注释）；未嵌入坐标时为空"
    )
    diagnostics: list[str] = Field(default_factory=list)

    @property
    def symbols(self) -> list[str]:
        return [atom.GetSymbol() for atom in self.mol.GetAtoms()]

    @property
    def atom_count(self) -> int:
        return self.mol.GetNumAtoms()

    @property
    def heavy_atom_count(self) -> int:
        return self.mol.GetNumHeavyAtoms()

    @property
    def formal_charge(self) -> int:
        return Chem.GetFormalCharge(self.mol)

    @property
    def single_atom(self) -> bool:
        return self.atom_count == 1

    @property
    def isomeric_smiles(self) -> str:
        return _canonical_isomeric_smiles(Chem.RemoveHs(self.mol))


class PreparedStructure(BaseModel):
    """构建产物。Mol 托管结构，枚举记录收敛与可用性，路径指向导出文件。"""

    status: BuildStatus
    mol: Molecule | None = None
    message: str = Field(default="", description="给定状态的说明；不承载收敛判定本身")
    has_coordinates: bool = Field(
        default=False, description="是否保留或生成了可继续计算的真实坐标；不表示力场已收敛或驻点已验证"
    )
    components: list[BuildComponent] = Field(default_factory=list)
    atom_identities: list[AtomIdentity] = Field(
        default_factory=list, description="按**完整结构输出原子顺序**排列的稳定身份表"
    )
    candidate_paths: list[str] = Field(
        default_factory=list, description="可交给下游的候选结构文件；仅 status='ok' 且 has_coordinates 时非空"
    )
    component_paths: list[str] = Field(
        default_factory=list, description="逐组分结构文件；只有在组装失败时才构成完整产物"
    )
    assembly: Optional[AssemblyResult] = Field(
        default=None,
        description="多组分输入的组装结果（含每个复合物候选的能量、片间最小距离、反应中心距离、"
                    "聚类编号与轨迹）。单组分输入为 None",
    )
    trajectory_ids: list[str] = Field(default_factory=list, description="本次构建的全部轨迹编号")
    trajectory_manifest_path: str = Field(default="", description="轨迹清单路径")
    artifact_path: str = Field(default="", description="本产物 JSON 的路径")
    electronic_state: dict = Field(
        default_factory=dict,
        description="输入声明、总电子数、局域自由基数、alpha/beta 电子数与开壳层分类；"
        "局域自由基数仅作诊断，不限制所声明的自旋耦合。",
    )
    diagnostics: list[str] = Field(default_factory=list)

    @property
    def symbols(self) -> list[str]:
        return [atom.GetSymbol() for atom in self.mol.GetAtoms()] if self.mol is not None else []

    @property
    def formal_charge_sum(self) -> int:
        return Chem.GetFormalCharge(self.mol) if self.mol is not None else 0

    def atom_identity(self, index: int) -> AtomIdentity:
        """按完整结构的输出原子序号取身份表条目（越界即 fail-loud）。"""
        for identity in self.atom_identities:
            if identity.index == index:
                return identity
        raise KeyError(f"no atom identity recorded for output atom index {index}")

    def candidate_path(self, suffix: str) -> str:
        """按扩展名取候选产物路径（找不到即 fail-loud，不返回空串冒充存在）。"""
        for path in self.candidate_paths:
            if path.endswith(suffix):
                return path
        raise FileNotFoundError(
            f"prepared structure (status={self.status}) has no {suffix} candidate; "
            f"available: {self.candidate_paths}"
        )


# ---------------------------------------------------------------------------
# 输入解析
# ---------------------------------------------------------------------------


def _parse_input(structure: StructureInput, total_charge: int):
    """把入口输入解析成带键级与立体化学的 RDKit Mol；失败抛 ValueError。"""
    if structure.kind == "molecule":
        return Chem.Mol(structure.value)
    if structure.kind == "smiles":
        mol = Chem.MolFromSmiles(structure.value)
        if mol is None:
            raise ValueError(f"Invalid SMILES string: {structure.value}")
        return mol

    if structure.kind == "mol_block":
        mol = Chem.MolFromMolBlock(structure.value, removeHs=False)
        if mol is None:
            raise ValueError("Could not parse the input MOL block")
        return mol

    mol = Chem.MolFromXYZBlock(structure.value)
    if mol is None:
        raise ValueError("Could not parse the input xyz text")
    try:
        rdDetermineBonds.DetermineBonds(mol, charge=total_charge)
    except Exception as exc:  # noqa: BLE001 - 统一转成显式 ValueError
        raise ValueError(
            f"Bond-order inference (rdDetermineBonds) failed for the xyz input: {exc}"
        ) from exc
    if mol.GetNumBonds() == 0 and mol.GetNumAtoms() > 1:
        raise ValueError("No chemical bonds could be inferred from the xyz input")
    return mol


def _fragment_atom_tuples(mol) -> list[tuple[int, ...]]:
    """按分子图连通分量拆分，返回每个组分的输入原子序号（升序）。

    用 ``sanitizeFrags=False`` 的索引视图拿到**原始原子序号**，正是"保留原始索引映射"
    所需要的；子分子另由 ``_submol_by_input_indices`` 按同一序号显式构造。
    """
    frags = Chem.GetMolFrags(mol, asMols=False, sanitizeFrags=False)
    return [tuple(sorted(frag)) for frag in frags]


def _canonical_isomeric_smiles(fragment_mol) -> str:
    """组分的规范异构 SMILES；立体标记是否保留靠它核对，不靠位置猜测。"""
    try:
        return Chem.MolToSmiles(fragment_mol)
    except Exception:  # noqa: BLE001 - 取不到就明确报告，不静默给空串冒充成功
        return ""


def _submol_by_input_indices(mol, indices: list[int]):
    """按**给定的输入原子序号顺序**构造子分子，返回 ``(submol, {输入序号: 子分子下标})``。

    在分子副本上删除未选原子，再按请求顺序重排。由 RDKit 保留原子/键属性、
    构象和立体参考，避免逐字段重建时丢失化学信息；输入分子不变。
    """
    old_to_new = {old_index: new_index for new_index, old_index in enumerate(indices)}
    rw = Chem.RWMol(mol)
    for old_index in reversed(range(mol.GetNumAtoms())):
        if old_index not in old_to_new:
            rw.RemoveAtom(old_index)
    retained_order = {old_index: new_index for new_index, old_index in enumerate(sorted(indices))}
    submol = renumber_atoms(rw, [retained_order[index] for index in indices])
    Chem.SanitizeMol(submol)
    return submol, old_to_new


# ---------------------------------------------------------------------------
# 加氢与原子身份
# ---------------------------------------------------------------------------


def _add_hydrogens_with_identity(submol, component_id: str):
    """加显式氢并返回 ``(加氢后的 mol, {新氢子分子下标: (父子分子下标, 第 k 个氢)})``。

    新增氢的身份是 ``(父重原子的输入序号, 该父原子上的第 k 个氢)``——与 ``AddHs`` 之后的
    数组位置无关。落在原子上的数组下标会随拆分方式改变，不能充当跨反应映射。
    """
    n_before = submol.GetNumAtoms()
    mol_h = Chem.AddHs(submol, addCoords=bool(submol.GetNumConformers() and submol.GetConformer().Is3D()))
    hydrogen_by_index: dict[int, tuple[int, int]] = {}
    per_parent: dict[int, list[int]] = {}
    for new_index in range(n_before, mol_h.GetNumAtoms()):
        atom = mol_h.GetAtomWithIdx(new_index)
        if atom.GetAtomicNum() != 1:
            raise ValueError(
                f"component {component_id}: atom {new_index} appended by AddHs is not hydrogen "
                f"(symbol={atom.GetSymbol()})"
            )
        neighbors = [n.GetIdx() for n in atom.GetNeighbors()]
        if len(neighbors) != 1:
            raise ValueError(
                f"component {component_id}: the added hydrogen {new_index} has "
                f"{len(neighbors)} neighbours; a stable identity needs exactly one parent"
            )
        per_parent.setdefault(neighbors[0], []).append(new_index)
    for parent_index, hydrogen_indices in per_parent.items():
        for ordinal, new_index in enumerate(sorted(hydrogen_indices), start=1):
            hydrogen_by_index[new_index] = (parent_index, ordinal)
    return mol_h, hydrogen_by_index


def _identity_table(mol_h, submol_atom_to_input: dict[int, int],
                    hydrogen_by_index: dict[int, tuple[int, int]],
                    component_id: str, index_offset: int) -> list[AtomIdentity]:
    """构造组分身份表（``index`` 为完整结构中的输出原子序号）。"""
    table: list[AtomIdentity] = []
    for atom_index in range(mol_h.GetNumAtoms()):
        symbol = mol_h.GetAtomWithIdx(atom_index).GetSymbol()
        if atom_index in hydrogen_by_index:
            parent_submol_index, ordinal = hydrogen_by_index[atom_index]
            if parent_submol_index not in submol_atom_to_input:
                raise ValueError(
                    f"component {component_id}: added hydrogen {atom_index} is bonded to sub-mol "
                    f"atom {parent_submol_index}, which has no input-index mapping"
                )
            table.append(AtomIdentity(
                index=index_offset + atom_index,
                symbol=symbol,
                component_id=component_id,
                origin="added_hydrogen",
                parent_input_atom_index=submol_atom_to_input[parent_submol_index],
                hydrogen_ordinal=ordinal,
            ))
            continue
        if atom_index not in submol_atom_to_input:
            raise ValueError(
                f"component {component_id}: atom {atom_index} has no input-index mapping; refusing "
                "to let the post-AddHs array position stand in for a stable identity"
            )
        table.append(AtomIdentity(
            index=index_offset + atom_index,
            symbol=symbol,
            component_id=component_id,
            origin="input_atom",
            input_atom_index=submol_atom_to_input[atom_index],
        ))
    return table


# ---------------------------------------------------------------------------
# 力场引擎与轨迹
# ---------------------------------------------------------------------------


def _select_engine(mol) -> Optional[str]:
    """选力场引擎：优先 MMFF94，缺参数再试 UFF；两者皆不可用返回 None。"""
    try:
        if AllChem.MMFFHasAllMoleculeParams(mol):
            return MMFF_ENGINE
    except Exception:  # noqa: BLE001 - 力场不可用即视为该引擎不可选
        pass
    try:
        if AllChem.UFFHasAllMoleculeParams(mol):
            return UFF_ENGINE
    except Exception:  # noqa: BLE001
        pass
    return None


def _make_force_field(mol, conf_id: int, engine: str):
    if engine == MMFF_ENGINE:
        props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
        if props is None:
            return None
        return AllChem.MMFFGetMoleculeForceField(mol, props, confId=conf_id)
    return AllChem.UFFGetMoleculeForceField(mol, confId=conf_id)


def _positions(mol, conf_id: int) -> list[list[float]]:
    conf = mol.GetConformer(conf_id)
    return [[float(v) for v in conf.GetAtomPosition(i)] for i in range(mol.GetNumAtoms())]


def _max_gradient(ff) -> Optional[float]:
    grad = [abs(float(g)) for g in ff.CalcGrad()]
    return max(grad) if grad else None


def _optimize_component(mol, conf_id: int, engine: str, seed: int, strategy: BuildStrategy,
                        component_id: str, attempt: int, out_dir: str) -> TrajectoryRecord:
    """在**同一个** ForceField 实例上逐步优化，并把每一迭代帧流式写入轨迹文件。

    机制与其唯一性见 ``structure_artifacts`` 模块 docstring：本构建下
    ``MinimizeTrajectory`` 的 Snapshot 无 Python 绑定、``Positions()`` 只读，
    因此逐迭代 ``Minimize(maxIts=1)`` 是取到逐迭代快照的唯一手段；实测它给出与一次性
    ``Minimize(maxIts=N)`` 相同终态（dE ≤ 1e-4 kcal/mol）且能量单调下降。
    """
    trajectory_id = f"{component_id}-{engine.lower()}-attempt{attempt}"
    symbols = [a.GetSymbol() for a in mol.GetAtoms()]
    writer = TrajectoryWriter(
        out_dir, trajectory_id, component_id, attempt, engine, symbols, seed,
    )
    ff = _make_force_field(mol, conf_id, engine)
    if ff is None:
        writer.append(0, _positions(mol, conf_id), 0.0, None)
        return writer.finish(
            -2, "failed", failure=f"force field {engine} could not be constructed for this component",
        )

    ff.Initialize()
    writer.append(0, _positions(mol, conf_id), float(ff.CalcEnergy()), _max_gradient(ff))
    try:
        for step in range(1, strategy.max_optimization_steps + 1):
            code = int(ff.Minimize(maxIts=1))
            writer.append(step, _positions(mol, conf_id), float(ff.CalcEnergy()), _max_gradient(ff))
            if code == 0:
                return writer.finish(0, "converged")
    except Exception as exc:  # noqa: BLE001 - 异常前已写入的帧必须保留
        return writer.finish(-3, "failed", failure=f"{type(exc).__name__}: {exc}")

    return writer.finish(
        1, "not_converged",
        notes=[f"reached the iteration limit ({strategy.max_optimization_steps}) without converging"],
    )


def _render_xyz(mol, conf_id: int, title: str,
                identities: Optional[list[AtomIdentity]] = None) -> str:
    """渲染 xyz；给身份表时每行尾部附稳定身份注释，便于下游把坐标映射回输入原子。"""
    conf = mol.GetConformer(conf_id)
    lines = [str(mol.GetNumAtoms()), title]
    for index in range(mol.GetNumAtoms()):
        symbol = mol.GetAtomWithIdx(index).GetSymbol()
        x, y, z = (float(v) for v in conf.GetAtomPosition(index))
        suffix = ""
        if identities is not None:
            identity = identities[index]
            if identity.origin == "added_hydrogen":
                suffix = f"  in:{identity.parent_input_atom_index}#H{identity.hydrogen_ordinal}"
            else:
                suffix = f"  in:{identity.input_atom_index}"
        lines.append(f"{symbol:<3} {x:>16.8f} {y:>16.8f} {z:>16.8f}{suffix}")
    return "\n".join(lines) + "\n"


def _build_component(mol, indices: list[int], component_id: str, request: PreparationRequest,
                     out_dir: str, artifacts: list[TrajectoryArtifact],
                     index_offset: int, candidate_sink=None, *, skip_force_field: bool) -> tuple[BuildComponent, list[AtomIdentity]]:
    """构建单个组分：切分 → 加氢 → （可选）嵌入 → 力场优化（含轨迹）→ 落盘。"""
    submol, old_to_new = _submol_by_input_indices(mol, indices)
    submol_atom_to_input = {new: old for old, new in old_to_new.items()}
    diagnostics: list[str] = []

    formal_charge = sum(a.GetFormalCharge() for a in submol.GetAtoms())

    mol_h, hydrogen_by_index = _add_hydrogens_with_identity(submol, component_id)
    identities = _identity_table(
        mol_h, submol_atom_to_input, hydrogen_by_index, component_id, index_offset,
    )

    component_capture=candidate_sink.for_component(identities) if candidate_sink else None
    parent=None
    single_atom = mol_h.GetNumAtoms() == 1
    embed_status: EmbedStatus = "not_required"
    optimization_status: OptimizationStatus = "not_required"
    engine = ""
    trajectory_id = ""
    final_energy: Optional[float] = None
    xyz_path = ""
    conf_id: Optional[int] = None

    if not request.strategy.embed:
        diagnostics.append(
            "coordinate embedding was not requested (strategy.embed=False); only the structural "
            "resolution (split / AddHs / identity table / charge self-check) was performed"
        )
    elif mol_h.GetNumConformers() and mol_h.GetConformer().Is3D():
        conf_id = mol_h.GetConformer().GetId()
        diagnostics.append("Input coordinates retained; no embedding or force-field optimization was run.")
        if component_capture:
            component_capture.capture(mol_h, conf_id, generator="component_input_geometry")
    elif single_atom:
        # 单原子组分无需调用力场：位置即原点，没有可优化的内部自由度。
        conf = Chem.Conformer(1)
        conf.SetAtomPosition(0, (0.0, 0.0, 0.0))
        mol_h.RemoveAllConformers()
        conf_id = mol_h.AddConformer(conf, assignId=True)
        diagnostics.append(
            "single-atom component: no conformer embedding and no force field were run"
        )
        if skip_force_field:
            optimization_status = "skipped_electronic_state"
            diagnostics.append("single-atom seed: no force-field energy or optimization is claimed")
    else:
        params = AllChem.ETKDGv3()
        params.randomSeed = request.random_seed
        params.clearConfs = True
        params.pruneRmsThresh = -1.0
        embedded = AllChem.EmbedMolecule(mol_h, params)
        if embedded < 0:
            embed_status = "failed"
            mol_h.RemoveAllConformers()
            placeholder = Chem.Conformer(mol_h.GetNumAtoms())
            for atom_index in range(mol_h.GetNumAtoms()):
                placeholder.SetAtomPosition(atom_index, (0.0, 0.0, 0.0))
            conf_id = mol_h.AddConformer(placeholder, assignId=True)
            diagnostics.append(
                f"ETKDGv3 embedding failed for component {component_id} "
                f"(seed={request.random_seed}); the recorded coordinates are placeholders at the "
                "origin and must not be used as a starting geometry"
            )
        else:
            embed_status = "embedded"
            conf_id = embedded
            if component_capture:
                parent=component_capture.capture(mol_h,conf_id,generator="component_ETKDGv3",seed=request.random_seed)
            if not skip_force_field:
                engine = _select_engine(mol_h) or ""
            if skip_force_field:
                optimization_status = "skipped_electronic_state"
                diagnostics.append(
                    "ETKDGv3 seed coordinates are unoptimized: the electronic-state declaration or "
                    "localized radical graph markers require avoiding MMFF94/UFF. No force-field "
                    "energy or convergence is claimed; subsequent optimization must preserve the "
                    "declared electronic state."
                )
            elif not request.strategy.optimize:
                optimization_status = "not_required"
                diagnostics.append("force-field optimization disabled by the approved build strategy")
            elif not engine:
                if component_capture:
                    from cloudra.tools.core.conformer_catalog import Qualification
                    component_capture.capture(mol_h,conf_id,generator="component_force_field_unavailable",parent_id=parent.candidate_id,state="failed",qualification=Qualification(status="rejected",reasons=["missing_parameters"]))
                optimization_status = "missing_parameters"
                diagnostics.append(
                    "no force field covers every atom of this component (MMFF94 and UFF both "
                    "unavailable); coordinates are embedded but NOT optimized"
                )
            else:
                record = _optimize_component(
                    mol_h, conf_id, engine, request.random_seed, request.strategy,
                    component_id, attempt=1, out_dir=out_dir,
                )
                artifacts.append(trajectory_artifact(record))
                trajectory_id = record.trajectory_id
                final_energy = record.final_frame.energy
                optimization_status = record.status
                if component_capture:
                    from cloudra.tools.core.conformer_catalog import EnergyObservation, Qualification
                    energies=[]
                    if final_energy is not None:
                        energies=[EnergyObservation(value=final_energy,unit='kcal/mol',method_fingerprint=engine,
                            species_key=parent.species_key,charge=formal_charge,multiplicity=request.multiplicity,
                            convergence='converged' if record.status=='converged' else 'unconverged',artifact_ref=record.trajectory_id)]
                    component_capture.capture(mol_h,conf_id,generator='component_'+engine,parent_id=parent.candidate_id,
                        state='optimized' if record.status=='converged' else 'failed',energies=energies,
                        qualification=Qualification(status='unknown' if record.status=='converged' else 'rejected',
                            reasons=[] if record.status=='converged' else [record.status],evidence_refs=[record.trajectory_id]))
                if record.status == "not_converged":
                    gradient = record.final_frame.max_gradient
                    gradient_text = "n/a" if gradient is None else f"{gradient:.6g}"
                    diagnostics.append(
                        f"force-field optimization did not converge within "
                        f"{request.strategy.max_optimization_steps} iterations "
                        f"(max gradient {gradient_text})"
                    )
                elif record.status == "failed":
                    diagnostics.append(f"force-field optimization raised: {record.failure}")

    mol_path = os.path.join(out_dir, f"component_{component_id}.mol")
    atomic_write_text(
        mol_path,
        Chem.MolToMolBlock(mol_h, confId=conf_id) if conf_id is not None
        else Chem.MolToMolBlock(mol_h),
    )
    if conf_id is not None:
        xyz_path = os.path.join(out_dir, f"component_{component_id}.xyz")
        atomic_write_text(
            xyz_path,
            _render_xyz(
                mol_h, conf_id, f"component {component_id} (per-component build)", identities,
            ),
        )

    component = BuildComponent(
        component_id=component_id,
        mol=copy_conformer(mol_h, conf_id) if conf_id is not None else mol_h,
        source_atom_indices=list(indices),
        embed_status=embed_status,
        optimization_status=optimization_status,
        engine=engine,
        trajectory_id=trajectory_id,
        final_energy=final_energy,
        mol_path=mol_path,
        xyz_path=xyz_path,
        diagnostics=diagnostics,
    )
    return component, identities


# ---------------------------------------------------------------------------
# 公开入口
# ---------------------------------------------------------------------------


def _finalize(prepared: PreparedStructure, out_dir: str) -> PreparedStructure:
    """把产物落盘（含失败态）并回填路径。落盘失败一律抛出，不吞。"""
    artifact_path = os.path.join(out_dir, PREPARED_JSON_NAME)
    prepared.artifact_path = artifact_path
    atomic_write_text(artifact_path, prepared.model_dump_json(indent=2) + "\n")
    return prepared


def _empty(status: BuildStatus, message: str, out_dir: str,
           mol=None,
           diagnostics: Optional[list[str]] = None,
           electronic_state: Optional[dict] = None) -> PreparedStructure:
    return _finalize(
        PreparedStructure(
            status=status,
            message=message,
            mol=mol,
            electronic_state=dict(electronic_state or {}),
            diagnostics=list(diagnostics or []),
        ),
        out_dir,
    )


def _component_is_usable(component: BuildComponent) -> bool:
    """闭壳层力场组装的组分资格：嵌入过、且优化真的收敛。

    单原子组分无需嵌入与力场（位置即原点，是确定值），不受"嵌入过+收敛"要求的约束。
    """
    if component.single_atom:
        return True
    return (
        component.embed_status == "embedded"
        and component.optimization_status == "converged"
    )


def prepare_structure(request: PreparationRequest, *, candidate_sink=None) -> PreparedStructure:
    """把请求解析成 ``PreparedStructure``。

    所有可预期失败都返回带显式 ``status`` 的产物（不抛异常、也不返回半成品冒充成功）；
    只有"本函数无法继续"（缺 RDKit、策略名未知）才抛异常。
    """
    if not _RDKIT_AVAILABLE:
        raise RuntimeError(
            "RDKit is not installed. Install it with: pip install 'cloudra[chem]', then retry."
        )
    if request.strategy.name != "per_component":
        raise ValueError(
            f"unknown build strategy {request.strategy.name!r}; only 'per_component' has been "
            "approved (assembly sampling parameters are still awaiting user approval)"
        )
    if request.multiplicity < 1:
        raise ValueError(f"multiplicity must be >= 1 (2S+1), got {request.multiplicity}")

    out_dir = request.output_dir
    os.makedirs(out_dir, exist_ok=True)

    try:
        mol = _parse_input(request.structure, request.total_charge)
    except ValueError as exc:
        return _empty(
            "invalid_input",
            f"Could not build a structure from the request: {exc}",
            out_dir,
        )

    preserve_geometry = request.strategy.embed and bool(mol.GetNumConformers() and mol.GetConformer().Is3D())
    if preserve_geometry and not all(
        math.isfinite(float(value)) for position in mol.GetConformer().GetPositions() for value in position
    ):
        return _empty("invalid_input", "Input coordinates must be finite.", out_dir, mol)

    fragments = _fragment_atom_tuples(mol)
    if not fragments:
        return _empty(
            "invalid_input", "The input structure contains no atoms", out_dir,
        )

    state_details = electronic_state_details(
        mol, charge=request.total_charge, multiplicity=request.multiplicity,
        electronic_character=request.electronic_character,
    )
    state_issue = electronic_state_issue(
        mol, charge=request.total_charge, multiplicity=request.multiplicity,
        electronic_character=request.electronic_character,
    )
    if state_issue:
        status, message = state_issue
        return _empty(
            status, message,
            out_dir, mol,
            diagnostics=[
                f"{len(fragments)} component(s) were not built: the electronic state is unsupported"
            ],
            electronic_state=state_details,
        )

    artifacts: list[TrajectoryArtifact] = []
    components: list[BuildComponent] = []
    identities: list[AtomIdentity] = []
    component_paths: list[str] = []
    index_offset = 0

    for position, indices in enumerate(fragments):
        component_id = f"frag{position}"
        component, component_identities = _build_component(
            mol, list(indices), component_id, request, out_dir, artifacts, index_offset, candidate_sink,
            skip_force_field=state_details["requires_spin_aware_geometry"],
        )
        identity_symbols = [a.symbol for a in component_identities]
        if identity_symbols != component.symbols:
            raise ValueError(
                f"component {component_id}: identity table symbols {identity_symbols} do not match "
                f"the built element sequence {component.symbols}"
            )
        components.append(component)
        identities.extend(component_identities)
        component_paths.append(component.mol_path)
        index_offset += component.atom_count

    built_mol = Chem.Mol(components[0].mol)
    for component in components[1:]:
        built_mol = Chem.CombineMols(built_mol, component.mol)

    if preserve_geometry:
        # Splitting groups fragments together. Restore the input atom order,
        # appending only newly added hydrogens after the existing input atoms.
        order = sorted(range(len(identities)), key=lambda index: (
            identities[index].input_atom_index is None,
            identities[index].input_atom_index if identities[index].input_atom_index is not None
            else identities[index].parent_input_atom_index,
            identities[index].hydrogen_ordinal or 0,
        ))
        built_mol = renumber_atoms(built_mol, order)
        identities = [identities[index].model_copy(update={"index": new_index})
                      for new_index, index in enumerate(order)]

    trajectory_manifest = write_trajectory_manifest(out_dir, artifacts) if artifacts else ""

    atom_count = len(identities)
    invalid_pairs = [
        (left, right) for left, right in request.strategy.reaction_center
        if not (0 <= left < atom_count and 0 <= right < atom_count) or left == right
    ]
    # A reaction center is consumed by this builder only when it assembles multiple
    # embedded fragments. Single-component reaction paths check it after endpoint mapping.
    if invalid_pairs and len(components) > 1 and request.strategy.embed:
        numbering = ", ".join(f"{atom.index}={atom.symbol}" for atom in identities)
        return _finalize(
            PreparedStructure(
                status="invalid_reaction_center",
                message=(
                    f"reaction_center pair(s) {invalid_pairs} are invalid for the built structure "
                    f"with {atom_count} atoms. Indices are 0-based in the full output atom order, "
                    f"including hydrogens; valid indices are 0..{atom_count - 1}, and a pair must "
                    "name two different atoms."
                ),
                components=components,
                mol=built_mol,
                atom_identities=identities,
                component_paths=component_paths,
                trajectory_ids=[artifact.trajectory_id for artifact in artifacts],
                trajectory_manifest_path=trajectory_manifest,
                electronic_state=state_details,
                diagnostics=[f"built atoms (0-based): {numbering}"],
            ),
            out_dir,
        )

    diagnostics: list[str] = []
    assembly: Optional[AssemblyResult] = None
    assembly_paths: list[str] = []
    if preserve_geometry:
        status: BuildStatus = "ok"
        has_coordinates = True
        message = "Input geometry retained as an unverified seed; no embedding, force-field optimization or reassembly was run."
        if len(components) > 1:
            groups = [list(group) for group in Chem.GetMolFrags(built_mol)]
            gap, pair = _min_interfragment_gap(built_mol.GetConformer().GetPositions(), groups)
            if gap < request.strategy.assembly.min_interfragment_distance:
                status = "assembly_failed"
                has_coordinates = False
                message = (f"Input geometry has an interfragment collision at atoms {pair}: {gap:.4f} Å "
                           f"< {request.strategy.assembly.min_interfragment_distance} Å; coordinates were not moved.")
        diagnostics.extend(diagnostic for component in components for diagnostic in component.diagnostics)
    elif len(components) > 1 and not request.strategy.embed:
        # 组装的对象是**已嵌入的**组分坐标（刚性放置要冻结片内几何），因此 embed=False
        # 只做结构解析的调用方拿不到复合物候选；明确报出原因，不做隐式补算。
        status = "assembly_failed"
        has_coordinates = False
        message = (
            f"{len(components)} connected components detected, but the build strategy requested "
            "embed=False (structure resolution only), so no component has 3D coordinates to "
            "assemble. Request embed=True to get complex candidates."
        )
        diagnostics.append(
            "assembly needs embedded component coordinates; the strategy disabled embedding"
        )
    elif len(components) > 1 and state_details["requires_spin_aware_geometry"]:
        status = "unsupported_spin"
        has_coordinates = False
        message = (
            "Multicomponent force-field assembly cannot represent the electronic-state declaration "
            "or radical-marked graph. Component coordinates are unoptimized seeds; no complex "
            "candidate was produced. Supply an explicit MOL "
            "graph plus XYZ complex geometry through the file conformer input."
        )
        diagnostics.append("MMFF94/UFF complex assembly was not run for this state declaration or graph representation")
    elif len(components) > 1:
        # 组装前闸门：任一组分坐标不可用（嵌入失败/优化未收敛/缺参数）就不进 assemble——
        # 把占位坐标或未收敛几何拼成"复合物"等于交付无意义结构。
        unusable = [component for component in components if not _component_is_usable(component)]
        if unusable:
            details = "; ".join(
                f"{component.component_id} (embed={component.embed_status}, "
                f"optimization={component.optimization_status})"
                for component in unusable
            )
            status = "optimization_failed"
            has_coordinates = False
            message = (
                f"{len(components)} connected components detected, but component(s) "
                f"{details} have no usable coordinates, so assembly was NOT run: a complex "
                "assembled from placeholder or unconverged fragment geometries would be "
                "meaningless. Fix the component builds first."
            )
            diagnostics.append(
                f"assembly refused: {len(unusable)} of {len(components)} component(s) failed the "
                "usability gate (embedded + converged, or single-atom)"
            )
        else:
            # 组装（用户批准的方案 A）：刚性放置采样 + 碰撞剔除 + 力场弛豫；反应中心给出时按
            # 反应模式做约束预优化并条件释放约束。组装参数就是 BuildStrategy.assembly 的默认值。
            assembly = assemble(
                components=[(component.mol, component.mol.GetConformer().GetId()) for component in components],
                output_dir=os.path.join(out_dir, "assembly"),
                parameters=request.strategy.assembly,
                reaction_center=list(request.strategy.reaction_center) or None,
                guided_windows=list(request.strategy.guided_windows) or None,
                seed=request.random_seed, candidate_sink=candidate_sink,
            )
            diagnostics.extend(assembly.diagnostics)
            if assembly.status == "ok":
                status = "ok"
                has_coordinates = True
                built_mol = assembly.candidates[0].mol
                assembly_paths = list(assembly.candidate_paths)
                message = (
                    f"{len(components)} connected components assembled ({assembly.mode} mode): "
                    f"{len(assembly.candidates)} complex candidate(s). {assembly.message}"
                )
            else:
                status = "assembly_failed"
                has_coordinates = False
                message = (
                    f"{len(components)} connected components detected and assembled, but no usable complex "
                    f"candidate was produced (assembly status: {assembly.status}). {assembly.message}"
                )
    elif not request.strategy.embed:
        status = "ok"
        has_coordinates = False
        message = (
            "Structure resolved (split / AddHs / identity table / charge self-check); coordinate "
            "embedding was not requested."
        )
    else:
        only = components[0]
        if only.embed_status == "failed":
            status = "optimization_failed"
            has_coordinates = False
            message = (
                f"Conformer embedding failed for component {only.component_id}; the "
                "recorded coordinates are placeholders and must not be used as a starting geometry."
            )
        elif only.single_atom:
            status = "ok"
            has_coordinates = True
            message = "Single-atom structure; its coordinate is the origin (no force field needed)."
        elif only.optimization_status in _NON_USABLE_OPTIMIZATION:
            status = "optimization_failed"
            has_coordinates = only.optimization_status == "not_converged"
            message = (
                f"Component {only.component_id} did not converge under "
                f"{only.engine or 'any force field'} (or the optimization raised); "
                "its embedded coordinates remain an unqualified seed for a separate quantum-chemistry "
                "optimization, not a force-field minimum. See the recorded trajectory for the last state."
            )
        elif only.optimization_status == "missing_parameters":
            status = "missing_parameters"
            has_coordinates = True
            message = (
                "No force field covers every atom of this structure (MMFF94 and UFF both "
                "unavailable); coordinates were embedded but NOT optimized."
            )
        elif only.optimization_status == "skipped_electronic_state":
            status = "ok"
            has_coordinates = True
            message = (
                "Seed embedded by ETKDGv3; coordinates are unoptimized. "
                "MMFF94/UFF were skipped; subsequent optimization and scientific qualification "
                "must use the declared electronic state."
            )
            diagnostics.extend(only.diagnostics)
        elif only.optimization_status == "not_required":
            status = "ok"
            has_coordinates = True
            message = (
                "Force-field optimization was disabled by the build strategy, so the structure was "
                "embedded but not optimized."
            )
        else:
            status = "ok"
            has_coordinates = True
            message = "Single component built and optimized; coordinates are ready for downstream use."

    if has_coordinates and not all(
        math.isfinite(float(value)) for position in built_mol.GetConformer().GetPositions() for value in position
    ):
        status = "invalid_input"
        has_coordinates = False
        message = "Built coordinates are nonfinite; no usable geometry was delivered."

    prepared = PreparedStructure(
        status=status,
        message=message,
        has_coordinates=has_coordinates,
        components=components,
        mol=built_mol,
        atom_identities=identities,
        candidate_paths=[],
        component_paths=component_paths,
        trajectory_ids=[a.trajectory_id for a in artifacts],
        trajectory_manifest_path=trajectory_manifest,
        electronic_state=state_details,
        diagnostics=diagnostics,
    )

    prepared.assembly = assembly
    prepared.candidate_paths = assembly_paths

    if status == "ok" and has_coordinates and (len(components) == 1 or preserve_geometry):
        xyz_path = os.path.join(out_dir, PREPARED_XYZ_NAME)
        mol_path = os.path.join(out_dir, PREPARED_MOL_NAME)
        atomic_write_text(
            xyz_path,
            _render_xyz(
                prepared.mol, prepared.mol.GetConformer().GetId(),
                "prepared by cloudra structure_builder (per-component build)",
                identities,
            ),
        )
        atomic_write_text(mol_path, Chem.MolToMolBlock(prepared.mol))
        prepared.candidate_paths = [xyz_path, mol_path]

    return _finalize(prepared, out_dir)
