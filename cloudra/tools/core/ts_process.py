"""过渡态搜索 SOP 的进程核心（`docs/TS_PROCESS_SOP.md`）。

本模块是 SOP 的**状态机与目录约定**，不是 agent 可见接口。agent 只见两个函数
（`ts_prepare` / `ts_resume`，JS 侧 `tools.ts_prepare(...)`），它们包在本模块外面。

设计纪律（逐条对应规格）：

- **校验是流程自己的职责**，不是交给 agent 的决策点。校验失败 → **阻塞**（blocked），
  阻塞信息**点名到原子**，agent 据此改声明再 `resume`。
- **只推两类事件**：阻塞与终态。阶段推进不推（避免污染上下文）。
- **四态终态**：``verified`` / ``candidate_only`` / ``search_failed`` / ``invalid_input``，
  且搜索失败 ≠ 反应不可能。
- **有界推进**：预算来自声明；干预次数耗尽即落终态，不无限续。
- **目录约定**：``ts/<run_id>/``，逐迭代帧只允许出现在 ``build/trajectories/``。
- **不新增存储**：状态是每个运行目录里的一个 ``process.json``；干预记进 runtime 事件
  （由调用方注入 ``event_sink``，本模块自己不建存储）。
- **阶段诚实**：尚未接线的阶段标 ``not_implemented`` 并**停下**，绝不假装跑过。

**本模块当前实现到哪**：declare → build → map → assemble → guess → validate →
submit → refine → verdict 已接线；两端的路径种子须另经同方法 Opt/Freq 验证为极小值，
才能作为 IRC 连通性判断的参考几何。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.geometry_inputs import DistanceWindowInput, ScanPlanInput, atom_index_base
from cloudra.tools.core.structure_builder import (
    BuildStrategy,
    PreparationRequest,
    StructureInput,
    prepare_structure,
)

#: 运行目录名（工作区下）。与 SOP §7 一致。
TS_ROOT_NAME = "ts"
PROCESS_JSON_NAME = "process.json"
DECLARE_JSON_NAME = "declare.json"
BUILD_STAGE_DIR = "build"
PATH_STAGE_DIR = "path"
JOBS_STAGE_DIR = "jobs"
VERDICT_STAGE_DIR = "verdict"
#: 逐迭代帧**只允许**出现在这一层（目录整洁的硬约束，见 SOP §7）
TRAJECTORY_DIR_NAME = "trajectories"

#: 片间最小原子距判据（与 structure_builder / complex_assembly 同一个既有值）
MIN_INTERFRAGMENT_DISTANCE = 1.0

TsStage = Literal[
    "declare", "build", "map", "assemble", "guess", "validate",
    "submit", "refine", "verdict",
]
TsTerminal = Literal["verified", "candidate_only", "search_failed", "invalid_input"]
StageStatus = Literal["pending", "done", "blocked", "waiting", "not_implemented"]
PathKind = Literal["", "xtb_path", "xtb_path_failed", "idpp_fallback", "not_attempted", "scan"]

#: 尚未接线的阶段：停下来并如实说明，绝不假装跑过
#: 尚未接线的阶段（保留机制：新增阶段若还没实现，必须标 not_implemented 并停下，不假装跑过）
_NOT_IMPLEMENTED_STAGES: dict[str, str] = {}

#: 精修输入的文件名（放在 jobs/<job_dir>/ 下，与作业现场同处）
REFINEMENT_INPUT_NAMES = {"orca": "refine.inp", "gaussian": "refine.gjf"}
#: 精修作业的申请资源。保守默认，且**必须**与写进输入文件的 %pal/%nprocshared 一致——
#: 准入会核对"申请量不得低于输入自述"，不一致会被直接拒收（这正是该检查的用处）。
REFINEMENT_CPUS = 4
REFINEMENT_MEMORY_MB = 4096


class TsBudget(BaseModel):
    """声明的预算。有界推进的上限来自这里，不来自实现里的常量的隐式假设。"""

    max_interventions: int = Field(default=8, description="允许 agent 介入（resume）的次数上限")
    path_refinement_runs: int = Field(
        default=0,
        description="路径精修的轮数上限（$path nrun）；**只是机时上限**，不是收敛判据。"
                    "0 = 声明未给出，由 runner 的默认值决定；撞上限后可用 ts_resume 抬高重跑",
    )


class ProductGeometry(BaseModel):
    """第二端点的**几何来源**声明。

    为什么需要它：``bond_changes`` 为空的题型（阻转异构、构象异构）里，两端 SMILES 是同一个
    分子——**"产物"只能由几何而不是由 SMILES 区分**。只从 SMILES 各建一次，两端会得到同一个
    构象，路径退化。这里让调用方声明"第二端 = 第一端绕这根键转这个角"，由工具生成几何，
    agent 不需要手写坐标。
    """

    kind: Literal["rotate_about_bond"] = Field(
        default="rotate_about_bond",
        description="几何生成方式。rotate_about_bond：把第一端几何绕指定键的轴刚体旋转一个角"
                    "（片内几何完全不变，只有两侧相对取向改变）——阻转异构/联芳旋转就是这种",
    )
    atoms: tuple[int, int] = Field(
        description="绕哪根键旋转（完整结构输出原子序号，Gaussian 1-based / ORCA 0-based，顺序无关）",
    )
    degrees: float = Field(description="旋转角（度）。180 = 转到对面的阻转异构体")


class PathSolvation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Literal["alpb", "gbsa"]
    solvent: str = Field(min_length=1)


class TsDeclaration(BaseModel):
    """一次 TS 搜索的声明。**这些是化学决策，由 agent/人给出，工具不猜。**"""

    model_config = ConfigDict(extra="forbid")

    reactant_smiles: str
    product_smiles: str
    charge: int = 0
    multiplicity: int = 1
    method: str = Field(
        description="方法与基组（如 'b3lyp/def2svp'）。**必填**：方法选择属科学决策，"
                    "不接受工具默认值",
    )
    engine: Literal["orca", "gaussian"] = Field(
        default="orca",
        description="精修作业的引擎。默认 orca（NEB-TS 路线只在 ORCA 上）；"
                    "要用 Gaussian 必须显式声明。引擎选择同样是声明项，不由工具临时决定",
    )
    extra_keywords: str = Field(
        default="",
        description="Explicit route keywords for TS refinement, frequency, IRC and endpoint Opt/Freq; e.g. ORCA CPCM(Water) or Gaussian scrf=(solvent=water). Scan uses scan.extra_route separately.",
    )
    path_solvation: Optional[PathSolvation] = Field(
        default=None,
        description="Explicit xTB path-guess solvation model and solvent, e.g. {'model':'alpb','solvent':'water'}. Separate from scan and refinement.",
    )
    budget: TsBudget = Field(default_factory=TsBudget)
    scan: Optional[ScanPlanInput] = Field(default=None, description="Optional exploratory scan; method is explicit, coordinates use this engine atom numbering. The process owns submission and refinement.")
    reaction_center: list[tuple[int, int]] = Field(
        default_factory=list,
        description="反应物/产物映射得到的反应中心原子对（完整结构的输出原子序号，"
                    "软件原生编号（Gaussian 1-based，ORCA 0-based），包含所有氢）；"
                    "给出即按反应模式组装",
    )
    ring_order: list[int] = Field(
        default_factory=list,
        description="拟成环原子顺序，Gaussian 1-based / ORCA 0-based 完整构建原子序号；空列表保持普通 TS 流程",
    )
    distance_filters: list[DistanceWindowInput] = Field(
        default_factory=list,
        description="原子对距离窗口，与 conformer_search 同一格式；可与 ring_order 并用",
    )
    product_geometry: Optional[ProductGeometry] = Field(
        default=None,
        description="第二端的几何来源。给了它就**不再从 product_smiles 单独建结构**，而是按声明"
                    "从第一端几何生成——两端 SMILES 相同的题型（阻转异构/外消旋）必须用这个，"
                    "否则两端会建出同一个构象、路径退化。此时原子对应关系是恒等（由构造保证），"
                    "不需要 atom_map",
    )
    irc_log: str = Field(
        default="",
        description="已跑好的 IRC 日志路径（可选）。IRC 是「已验证」的第二道闸：频率只支持一阶鞍点，"
                    "还需 IRC 双向朝向两端经 Opt/Freq 证实的极小值才算 verified。流程优先使用"
                    "自己提交的 IRC 作业；这里允许声明已有的 IRC 日志作为兜底",
    )
    atom_map: list[int] = Field(
        default_factory=list,
        description="Full atom correspondence in product order; values use Gaussian 1-based / ORCA 0-based numbering, covering EVERY atom including hydrogens "
                    "(a heavy-atom-only map is rejected). Atom numbers refer to the endpoint "
                    "XYZs built by this process (component-wise assembly order, NOT raw SMILES "
                    "order). If empty, the map stage blocks and returns the built XYZ paths "
                    "with their software-native element sequences; reaction_mapping on the built "
                    "structures can draft a candidate for you to verify",
    )


class TsBlocked(BaseModel):
    """阻塞：需要 agent 改声明才能继续。**必须点名到原子/字段**，否则等于让人猜。"""

    failure_class: str = Field(description="失败分类（复用 crest_runner 的分类名 + 校验类）")
    stage: TsStage
    message: str
    atom_details: list[str] = Field(default_factory=list, description="点名到原子的具体事实")
    needs: list[str] = Field(default_factory=list, description="需要 agent 调整的声明项")


class TsStageRecord(BaseModel):
    stage: TsStage
    status: StageStatus
    detail: str = ""
    artifacts: list[str] = Field(default_factory=list)


class TsProcessRecord(BaseModel):
    """持久运行记录（``ts/<run_id>/process.json``）。"""

    format_version: Literal[2] = 2
    run_id: str
    run_dir: str
    workspace_dir: str = Field(default="", description="工作区根（证据快照的沙箱边界）")
    owner_conversation_id: str = Field(
        default="", description="发起项目的 conversation_id（compute_jobs 归属，随记录持久化）"
    )
    owner_session_id: Optional[str] = Field(
        default=None, description="发起 agent 的 session_id（作业终态推送收件人）"
    )
    declaration: TsDeclaration
    stage: TsStage = "declare"
    stage_records: list[TsStageRecord] = Field(default_factory=list)
    terminal: Optional[TsTerminal] = None
    blocked: Optional[TsBlocked] = None
    intervention_count: int = 0
    path_kind: PathKind = "not_attempted"
    guidance_attempt: int = 0
    active_attempt_dir: str = ""
    current_seed_xyz_path: str = ""
    current_seed_mol_path: str = ""
    current_reactant_prepared_path: str = ""
    current_ts_guess_path: str = ""
    guidance_manifest_path: str = ""
    effective_reaction_center: list[tuple[int, int]] = Field(default_factory=list)
    job_id: Optional[int] = Field(
        default=None, description="提交后的 compute_jobs 作业号（精修作业）"
    )
    job_input_path: str = Field(default="", description="精修输入文件路径")
    waiting_for: str = Field(
        default="",
        description="非空表示正在等某个已提交的作业（如 'job:12'）。**等计算不是阻塞**："
                    "不推事件、不需要 agent 做决策；作业终态由既有 compute 通知路径投递",
    )
    scan_step: Optional["TsJobStep"] = None
    job_steps: list["TsJobStep"] = Field(
        default_factory=list,
        description="精修作业序列（TS Opt/Freq → IRC → 两端 Opt/Freq），每步记 job_id/输入/状态",
    )
    #: 可进入证据集的小产物。**逐迭代帧永远不在这里**（SOP §7 第 2 条）
    evidence_candidates: list[str] = Field(default_factory=list)
    revision: int = 0

    @property
    def is_terminal(self) -> bool:
        return self.terminal is not None

    def stage_record(self, stage: TsStage) -> TsStageRecord:
        for record in self.stage_records:
            if record.stage == stage:
                return record
        raise KeyError(f"no record for stage {stage!r}")


class TsStartRequest(BaseModel):
    """`ts_prepare` 的输入。"""

    declaration: TsDeclaration
    workspace_dir: str = Field(description="工作区根目录；运行目录建在 <workspace_dir>/ts/<run_id>/")
    owner_conversation_id: str = Field(
        default="", description="发起项目的 conversation_id（计算作业归属；缺失时 submit 阶段拒收）"
    )
    owner_session_id: Optional[str] = Field(
        default=None, description="发起 agent 的 session_id（作业终态推送的收件人）"
    )


class TsAdjustment(BaseModel):
    """`ts_resume` 的输入：**只接受局部覆盖**，不是重新声明整条反应。"""

    scan: Optional[ScanPlanInput] = None
    reaction_center: Optional[list[tuple[int, int]]] = None
    ring_order: Optional[list[int]] = None
    distance_filters: Optional[list[DistanceWindowInput]] = None
    atom_map: Optional[list[int]] = None
    path_refinement_runs: Optional[int] = Field(
        default=None, ge=1,
        description="抬高路径精修的轮数上限后重跑 guess（GH #39：撞上限的路径是被截断的采样，"
                    "不是收敛路径；抬高上限是让引擎自己跑到收敛判据）",
    )
    max_interventions: Optional[int] = None
    budget_override_note: str = Field(default="", description="为什么调预算（记进干预事件）")


# ---------------------------------------------------------------------------
# 目录与持久化
# ---------------------------------------------------------------------------


def _next_run_id(workspace_dir: str) -> str:
    root = os.path.join(workspace_dir, TS_ROOT_NAME)
    os.makedirs(root, exist_ok=True)
    used = set()
    for name in os.listdir(root):
        if name.startswith("ts_") and name[3:].isdigit():
            used.add(int(name[3:]))
    index = 1
    while index in used:
        index += 1
    return f"ts_{index:04d}"


def _make_stage_dirs(run_dir: str) -> None:
    for name in (BUILD_STAGE_DIR, PATH_STAGE_DIR, JOBS_STAGE_DIR, VERDICT_STAGE_DIR):
        os.makedirs(os.path.join(run_dir, name), exist_ok=True)


def save_record(record: TsProcessRecord) -> str:
    """落 ``process.json``；同时刷新 ``declare.json``（声明单独可读，便于人核对）。"""
    path = os.path.join(record.run_dir, PROCESS_JSON_NAME)
    atomic_write_text(path, record.model_dump_json(indent=2) + "\n")
    atomic_write_text(
        os.path.join(record.run_dir, DECLARE_JSON_NAME),
        record.declaration.model_dump_json(indent=2) + "\n",
    )
    return path


def load_record(workspace_dir: str, run_id: str) -> TsProcessRecord:
    path = os.path.join(workspace_dir, TS_ROOT_NAME, run_id, PROCESS_JSON_NAME)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format_version") != 2:
        raise ValueError("This TS record predates software-native atom numbering; start a new declaration.")
    return TsProcessRecord.model_validate(data)


def _record_stage(record: TsProcessRecord, stage: TsStage, status: StageStatus,
                  detail: str = "", artifacts: Optional[list[str]] = None) -> None:
    entry = TsStageRecord(stage=stage, status=status, detail=detail, artifacts=list(artifacts or []))
    record.stage_records = [r for r in record.stage_records if r.stage != stage] + [entry]
    record.stage = stage
    record.revision += 1


def _block(record: TsProcessRecord, stage: TsStage, failure_class: str, message: str,
           atom_details: Optional[list[str]] = None,
           needs: Optional[list[str]] = None) -> TsProcessRecord:
    record.blocked = TsBlocked(
        failure_class=failure_class, stage=stage, message=message,
        atom_details=list(atom_details or []), needs=list(needs or []),
    )
    _record_stage(record, stage, "blocked", message)
    return record


def _terminal(record: TsProcessRecord, stage: TsStage, terminal: TsTerminal,
              detail: str) -> TsProcessRecord:
    record.terminal = terminal
    record.blocked = None
    _record_stage(record, stage, "done", detail)
    return record


# ---------------------------------------------------------------------------
# 阶段实现
# ---------------------------------------------------------------------------


def _declare(record: TsProcessRecord) -> TsProcessRecord:
    declaration = record.declaration
    problems: list[str] = []
    if not declaration.reactant_smiles.strip():
        problems.append("reactant_smiles is empty")
    if not declaration.product_smiles.strip():
        problems.append("product_smiles is empty")
    if not declaration.method.strip():
        problems.append(
            "method is empty: the method/basis is a scientific decision and must be declared "
            "explicitly (the tool will not pick one)"
        )
    if declaration.multiplicity < 1:
        problems.append(f"multiplicity must be >= 1 (2S+1), got {declaration.multiplicity}")
    if declaration.product_geometry is not None:
        from rdkit import Chem

        reactant_graph = Chem.MolFromSmiles(declaration.reactant_smiles)
        product_graph = Chem.MolFromSmiles(declaration.product_smiles)
        if reactant_graph is None or product_graph is None:
            problems.append("product_geometry requires parseable reactant and product SMILES")
        else:
            Chem.RemoveStereochemistry(reactant_graph)
            Chem.RemoveStereochemistry(product_graph)
            if Chem.MolToSmiles(reactant_graph) != Chem.MolToSmiles(product_graph):
                problems.append(
                    "product_geometry is only a rotation, so reactant and product SMILES "
                    "must describe the same molecular graph"
                )
    if problems:
        return _terminal(record, "declare", "invalid_input", "; ".join(problems))
    _record_stage(record, "declare", "done", f"declared method={declaration.method}")
    return record


def _build(record: TsProcessRecord) -> TsProcessRecord:
    """建两端结构。多组分会被组装，因此这里要求 embed=True。"""
    from cloudra.tools.core.preorganization import search_guided

    declaration = record.declaration
    out_dir = os.path.join(record.run_dir, BUILD_STAGE_DIR)
    if (declaration.ring_order or declaration.distance_filters) and not record.active_attempt_dir:
        record.guidance_attempt += 1
        record.active_attempt_dir = os.path.join(
            out_dir, f"guided_attempt_{record.guidance_attempt:04d}",
        )
    endpoints = [("reactant", declaration.reactant_smiles)]
    if declaration.product_geometry is None:
        endpoints.append(("product", declaration.product_smiles))
    # 第二端几何由声明派生（绕键旋转）时**不单独建**：那一端就是第一端的一个刚体旋转，
    # 另外建一个构象既浪费又可能被误当成"产物"（两端 SMILES 相同的题型必然踩这个坑）
    for role, smiles in endpoints:
        if role == "reactant" and (declaration.ring_order or declaration.distance_filters):
            try:
                guided = search_guided(
                    structure=StructureInput(kind="smiles", value=smiles),
                    output_dir=os.path.join(record.active_attempt_dir, "reactant"),
                    ring_order=[i + (0 if declaration.engine == "orca" else 1) for i in declaration.ring_order],
                    index_base=0 if declaration.engine == "orca" else 1,
                    distance_filters=[dict(row.model_dump(), atoms=[i + (0 if declaration.engine == "orca" else 1) for i in row.atoms])
                                      for row in declaration.distance_filters],
                    charge=declaration.charge, multiplicity=declaration.multiplicity,
                )
            except ValueError as exc:
                return _block(
                    record, "build", "invalid_geometry_guidance", str(exc),
                    atom_details=[str(exc)], needs=["ring_order", "distance_filters"],
                )
            if guided.status != "ok" or not guided.candidates:
                return _block(
                    record, "build", "guided_preorganization_failed",
                    f"{guided.message} Guidance manifest: {guided.manifest_path}",
                    atom_details=guided.diagnostics + [
                        path for path in (guided.closest_path, guided.manifest_path) if path
                    ],
                    needs=["ring_order", "distance_filters"],
                )
            chosen = guided.candidates[0]
            record.current_seed_xyz_path = chosen.xyz_path
            record.current_seed_mol_path = chosen.mol_path
            record.current_reactant_prepared_path = guided.prepared_path
            record.guidance_manifest_path = guided.manifest_path
            record.effective_reaction_center = list(dict.fromkeys(
                tuple(sorted(pair))
                for pair in [*declaration.reaction_center, *guided.forming_pairs]
            ))
            record.evidence_candidates.extend([chosen.xyz_path, chosen.mol_path])
            continue
        target_dir = (
            os.path.join(record.active_attempt_dir, role)
            if record.active_attempt_dir else os.path.join(out_dir, role)
        )
        prepared = prepare_structure(PreparationRequest(
            structure=StructureInput(kind="smiles", value=smiles),
            output_dir=target_dir,
            total_charge=declaration.charge,
            multiplicity=declaration.multiplicity,
            strategy=BuildStrategy(
                name="per_component", embed=True, optimize=True,
                # Ring-derived pairs index the reactant graph; product atom order is
                # only established at the later map stage.
                reaction_center=list(declaration.reaction_center),
            ),
        ))
        if prepared.status == "charge_mismatch":
            return _terminal(
                record, "build", "invalid_input",
                f"{role} ({smiles}): {prepared.message}",
            )
        if prepared.status == "unsupported_spin":
            return _terminal(
                record, "build", "invalid_input",
                f"{role} ({smiles}): {prepared.message}",
            )
        if prepared.status == "invalid_reaction_center":
            return _block(
                record, "build", prepared.status,
                f"{role} ({smiles}) could not be built: {prepared.message}",
                atom_details=list(prepared.diagnostics),
                needs=["reaction_center"],
            )
        if prepared.status != "ok":
            return _block(
                record, "build", prepared.status,
                f"{role} ({smiles}) could not be built: {prepared.message}",
                atom_details=list(prepared.diagnostics),
                needs=[f"{role}_smiles"],
            )
        if role == "reactant":
            record.current_reactant_prepared_path = prepared.artifact_path
        record.evidence_candidates.extend(prepared.candidate_paths)
    detail = "both endpoints built" if len(endpoints) == 2 else (
        "first endpoint built; the second endpoint is derived from it by the declared rotation"
    )
    _record_stage(record, "build", "done", detail, record.evidence_candidates)
    return record


def _active_reaction_center(record: TsProcessRecord) -> list[tuple[int, int]]:
    return (record.effective_reaction_center if (record.declaration.ring_order or record.declaration.distance_filters)
            else record.declaration.reaction_center)


def _read_built_xyz(record: TsProcessRecord, role: str):
    """读回某端已构建的几何，返回 ``(symbols, positions, xyz_path, mol_path)``；
    找不到返回 ``None``。

    多组分输入建出来的是**组装候选**（已按能量排序，取第一个）；单组分是 ``prepared.xyz``。
    """
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    if role == "reactant" and record.current_seed_xyz_path:
        path = record.current_seed_xyz_path
        if not os.path.isfile(path):
            return None
        atoms = read_xyz_atoms(path)
        return ([symbol for symbol, _ in atoms], [position for _, position in atoms],
                path, record.current_seed_mol_path)
    base = (
        os.path.join(record.active_attempt_dir, role)
        if record.active_attempt_dir else
        os.path.join(record.run_dir, BUILD_STAGE_DIR, role)
    )
    candidates = [os.path.join(base, "prepared.xyz")]
    assembly_dir = os.path.join(base, "assembly")
    if os.path.isdir(assembly_dir):
        candidates.extend(sorted(
            os.path.join(assembly_dir, name)
            for name in os.listdir(assembly_dir)
            if name.startswith("complex_candidate_") and name.endswith(".xyz")
        ))
    for path in candidates:
        if os.path.isfile(path):
            atoms = read_xyz_atoms(path)
            mol_path = os.path.splitext(path)[0] + ".mol"
            return (
                [symbol for symbol, _ in atoms],
                [position for _, position in atoms],
                path,
                mol_path if os.path.isfile(mol_path) else "",
            )
    return None


def _derive_product_geometry(record: TsProcessRecord, built):
    """按声明的旋转从第一端几何生成第二端几何；返回 ``(错误, positions)``。

    分组用**真实键图**：读第一端构建产物的 MOL，去掉被旋转的那根键，取连通分量——
    不用距离启发式（那等于把"哪些原子属于哪一侧"交给一个阈值）。旋转的是**含 atoms[1]
    的那一侧**（绕同一根轴转，两侧等价，取一个确定的规则即可）。
    """
    from rdkit import Chem

    from cloudra.tools.core.geometry import rotate_about_axis

    declaration = record.declaration
    geometry = declaration.product_geometry
    if geometry is None:
        return "", []
    symbols, positions, _xyz_path, mol_path = built
    if not mol_path:
        return (
            "the built endpoint's MOL file is missing, so the bond to rotate about cannot be "
            "identified from the real bond graph",
            [],
        )
    mol = Chem.MolFromMolBlock(Path(mol_path).read_text(encoding="utf-8"), removeHs=False)
    if mol is None:
        return f"the built endpoint's MOL file could not be parsed: {mol_path}", []
    left, right = int(geometry.atoms[0]), int(geometry.atoms[1])
    n = len(symbols)
    if not (0 <= left < n and 0 <= right < n) or left == right:
        return (
            f"rotation axis atoms {geometry.atoms} are out of range for a {n}-atom structure",
            [],
        )
    if mol.GetBondBetweenAtoms(left, right) is None:
        return (
            f"atoms {left} and {right} are not bonded in the built structure, so there is no bond "
            "to rotate about",
            [],
        )
    editable = Chem.RWMol(mol)
    editable.RemoveBond(left, right)
    fragments = [sorted(frag) for frag in Chem.GetMolFrags(editable)]
    if len(fragments) != 2:
        return (
            f"removing the bond {left}-{right} left {len(fragments)} fragment(s) instead of 2, so "
            "the rotation would not split the molecule into two rigid sides",
            [],
        )
    side = fragments[0] if right in fragments[0] else fragments[1]
    rotated = rotate_about_axis(
        positions, side, positions[left], positions[right], geometry.degrees,
    )
    return "", [[float(v) for v in row] for row in rotated]


def _endpoint_numbering(record: TsProcessRecord) -> list[str]:
    """map 阶段自诊断负载：两端已建几何的 XYZ 路径与 1-based 元素序列。

    atom_map 的序号以**流程构建的 XYZ**为准（按连通分量拼装，H 跟在各自组分
    后面），既不是 SMILES 序也不是 RDKit AddHs 序——agent 看不见这个参照系
    就只能猜编号，所以阻塞时必须把它直接给出来。"""
    lines: list[str] = []
    for role in ("reactant", "product"):
        built = _read_built_xyz(record, role)
        if built is None:
            continue
        symbols, _, path, _mol = built
        lines.append(f"{role} built geometry: {path}")
        base = 0 if record.declaration.engine == "orca" else 1
        lines.append(
            f"{role} atoms ({base}-based): "
            + ", ".join(f"{i}={s}" for i, s in enumerate(symbols, start=base))
        )
    return lines


def _map(record: TsProcessRecord) -> TsProcessRecord:
    """原子映射：校验声明的映射能把产物重排到**与反应物同一原子序列**。

    这一步是必需的，不是形式：构建器按连通分量拼装两端，两端的原子顺序**本来就不一样**
    （实测 ``[F-].CCl`` → ``[F,C,Cl,H,H,H]``，``CF.[Cl-]`` → ``[C,F,H,H,H,Cl]``），而
    路径搜索要求两端是同一套、同序的原子。歧义与错映射必须**点名到原子**地报出来。
    """
    declaration = record.declaration
    base = 0 if declaration.engine == "orca" else 1
    if declaration.product_geometry is not None:
        # 第二端几何由第一端绕键旋转而来 -> 原子对应关系是**恒等**（构造保证），不需要 atom_map
        built = _read_built_xyz(record, "reactant")
        if built is None:
            return _block(
                record, "map", "missing_built_geometry",
                "the first endpoint has no built geometry, so the declared rotation cannot be "
                "applied",
                needs=["reactant_smiles"],
            )
        error, positions = _derive_product_geometry(record, built)
        if error:
            return _block(
                record, "map", "product_geometry_failed", error, needs=["product_geometry"],
            )
        if len(positions) != len(built[0]):
            return _block(
                record, "map", "product_geometry_failed",
                f"the derived second endpoint has {len(positions)} atoms but the first endpoint has "
                f"{len(built[0])}",
                needs=["product_geometry"],
            )
        _record_stage(
            record, "map", "done",
            "the second endpoint is the first endpoint rotated about the declared bond "
            f"({declaration.product_geometry.atoms}, {declaration.product_geometry.degrees} deg), so "
            "the atom correspondence is the identity by construction; no atom_map is needed",
        )
        return record
    if not declaration.atom_map:
        return _block(
            record, "map", "atom_map_missing",
            "no atom_map was declared: the reactant→product atom correspondence is ambiguous, and "
            "an ambiguous mapping must be declared rather than guessed (a wrong mapping produces a "
            "non-physical path no matter how good the path search is). To fix: declare the FULL "
            "software-native map (Gaussian 1-based, ORCA 0-based), in product atom order, "
            "covering EVERY atom including hydrogens (a heavy-atom-only map is rejected). Atom "
            "numbers refer to the built endpoint XYZs listed in atom_details (component-wise "
            "assembly order, NOT raw SMILES order): read them, or call reaction_mapping on the "
            "built structures for a draft and verify it element-wise before ts_resume.",
            atom_details=_endpoint_numbering(record),
            needs=["atom_map"],
        )

    reactant = _read_built_xyz(record, "reactant")
    product = _read_built_xyz(record, "product")
    if reactant is None or product is None:
        return _block(
            record, "map", "missing_built_geometry",
            "the built endpoint geometries are missing from the run directory, so the atom map "
            "could not be checked",
            needs=["reactant_smiles", "product_smiles"],
        )
    r_symbols = reactant[0]
    p_symbols = product[0]
    n = len(r_symbols)
    if len(p_symbols) != n:
        return _block(
            record, "map", "atom_count_mismatch",
            f"the reactant has {n} atoms but the product has {len(p_symbols)}; a path search needs "
            "one consistent atom set",
            atom_details=[f"reactant: {r_symbols}", f"product: {p_symbols}"],
            needs=["reactant_smiles", "product_smiles"],
        )
    if sorted(declaration.atom_map) != list(range(n)):
        got = declaration.atom_map
        diagnosis = ""
        if got and min(got) < 0:
            diagnosis = (" The map contains negative internal indices.")
        elif 0 < len(got) < n and sorted(got) == list(range(len(got))):
            heavy = sum(1 for s in p_symbols if s != "H")
            if len(got) == heavy:
                diagnosis = (f" The map has {len(got)} entries, exactly the heavy-atom count — "
                             "this is a heavy-atom map (e.g. reaction_mapping's heavy_atom_map); "
                             "atom_map must cover EVERY atom including hydrogens.")
        return _block(
            record, "map", "atom_map_not_a_permutation",
            f"atom_map must cover every atom once ({base}..{n-1+base}); got "
            f"{[i+base for i in got]}.{diagnosis} Atom numbering refers to the built endpoint XYZs listed in "
            "atom_details.",
            atom_details=_endpoint_numbering(record),
            needs=["atom_map"],
        )

    mismatches: list[str] = []
    for product_index, target in enumerate(declaration.atom_map):
        if p_symbols[product_index] != r_symbols[target]:
            mismatches.append(
                f"product atom {product_index + base} is {p_symbols[product_index]} but the map points it "
                f"at reactant atom {target + base} which is {r_symbols[target]}"
            )
    if mismatches:
        return _block(
            record, "map", "atom_map_element_mismatch",
            "the declared atom_map does not line up the two endpoints element-wise; reordering the "
            "product by it would put the wrong element on the wrong atom. The full software-native element "
            "sequences of both built endpoints are in atom_details — rebuild the whole map against "
            "them (do not patch single entries by trial and error).",
            atom_details=mismatches[:10] + _endpoint_numbering(record),
            needs=["atom_map"],
        )
    _record_stage(record, "map", "done", f"{n} atoms mapped and element-consistent")
    return record


def _assemble(record: TsProcessRecord) -> TsProcessRecord:
    """反应中心引导的组装。组装本身在 build 阶段由 structure_builder 完成，这里只核对声明。"""
    # 组装只对**多组分**体系有意义：单组分（分子内重排、阻转异构、环翻转）没有片间取向可采样，
    # 因此不要求 reaction_center——这是"反应中心"这个概念本身不适用，不是调用方漏填
    import json as _json

    prepared_path = (record.current_reactant_prepared_path or
                     os.path.join(record.run_dir, BUILD_STAGE_DIR, "reactant", "prepared_structure.json"))
    components = 1
    prepared_data: dict = {}
    if os.path.isfile(prepared_path):
        with open(prepared_path, encoding="utf-8") as handle:
            prepared_data = _json.load(handle)
        components = len(prepared_data.get("components", []))
    identities = prepared_data.get("atom_identities", [])
    active_center = _active_reaction_center(record)
    if active_center and not identities:
        return _block(
            record, "assemble", "missing_built_atom_numbering",
            "the built reactant atom identities are missing; reaction_center cannot be checked "
            "against a reliable atom order",
            needs=["reactant_smiles"],
        )
    atom_count = len(identities)
    invalid_pairs = [
        (left, right) for left, right in active_center
        if not (0 <= left < atom_count and 0 <= right < atom_count) or left == right
    ]
    if invalid_pairs and record.declaration.product_geometry is None:
        base = 0 if record.declaration.engine == "orca" else 1
        invalid_pairs = [(left + base, right + base) for left, right in invalid_pairs]
        numbering = ", ".join(f"{atom['index'] + base}={atom['symbol']}" for atom in identities)
        return _block(
            record, "assemble", "invalid_reaction_center",
            f"reaction_center pair(s) {invalid_pairs} are invalid for the built reactant with "
            f"{atom_count} atoms. Use {base}-based indices {base}..{atom_count - 1 + base} in the full output "
            "atom order, including hydrogens; each pair must name two different atoms.",
            atom_details=[f"reactant atoms ({base}-based): {numbering}"],
            needs=["reaction_center"],
        )
    if components <= 1 and record.declaration.product_geometry is not None:
        _record_stage(
            record, "assemble", "done",
            "single-component process whose second endpoint is a declared rotation of the first: "
            "there is no inter-fragment orientation to sample, so no reaction_center applies — the "
            "declared rotation is the reaction coordinate",
        )
        return record
    if components <= 1:
        _record_stage(
            record, "assemble", "done",
            "single component: nothing to assemble (no inter-fragment orientation). The reaction "
            "coordinate is whatever the path guess explores",
        )
        return record
    if not active_center:
        return _block(
            record, "assemble", "reaction_center_missing",
            "no reaction_center was declared for a MULTI-component input: complex mode would sample "
            "relative orientations without any bonding centre, which is not a reactive complex. "
            "Declare the atom pairs that form/break",
            needs=["reaction_center"],
        )
    _record_stage(
        record, "assemble", "done",
        f"{len(active_center)} reaction-centre pair(s) guide the assembly",
    )
    return record


def _guess_scan(record: TsProcessRecord) -> TsProcessRecord:
    """Advance a declared scan via the same job ledger and parser as manual scans."""
    import math

    from cloudra.services.compute_store import TERMINAL_STATES
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    declaration = record.declaration
    plan = declaration.scan
    if record.scan_step is None:
        built = _read_built_xyz(record, "reactant")
        if built is None:
            return _block(record, "guess", "missing_built_geometry", "Reactant geometry missing", needs=["reactant_smiles"])
        root = Path(record.run_dir) / PATH_STAGE_DIR
        root.mkdir(parents=True, exist_ok=True)
        folder = root / f"scan_{len(list(root.glob('scan_*'))) + 1:04d}"
        folder.mkdir()
        base = 0 if declaration.engine == "orca" else 1
        def public_rows(rows):
            return [dict(row.model_dump(), atoms=[i + base for i in row.atoms]) for row in rows]
        request = TsGuess_input_schema(
            mode="scan_prepare", input_path=built[2], engine=declaration.engine,
            method=plan.method, charge=declaration.charge, spin=declaration.multiplicity,
            extra_route=plan.extra_route,
            scans=public_rows(plan.scans), freeze=public_rows(plan.freeze),
            output_path=str(folder / ("scan.inp" if declaration.engine == "orca" else "scan.gjf")),
            nprocs=REFINEMENT_CPUS,
        )
        try:
            prepared = TsGuess()._scan_prepare(request)
        except ValueError as exc:
            return _block(record, "guess", "invalid_scan", str(exc), needs=["scan"])
        if not prepared.is_success:
            return _block(record, "guess", "invalid_scan", prepared.message, needs=["scan"])
        error, job_id = _submit_step(record, "scan", prepared.input_file_path, declaration.engine)
        if error:
            return _block(record, "guess", "compute_admission_rejected", error, needs=["scan"])
        record.scan_step = TsJobStep(purpose="scan", job_id=job_id, input_path=prepared.input_file_path, state="ready")
        record.waiting_for = f"job:{job_id}"
        _record_stage(record, "guess", "waiting", f"Scan job {job_id} submitted; wait for notification, then ts_resume.", [prepared.input_file_path])
        return record
    step = record.scan_step
    step.state = _read_job_state(record, step.job_id)
    if step.state not in TERMINAL_STATES and step.state != "missing":
        record.waiting_for = f"job:{step.job_id}"
        return record
    record.waiting_for = ""
    if step.state != "done":
        return _block(record, "guess", "scan_job_failed", f"Scan job {step.job_id}: {step.state}", needs=["scan"])
    target = str(Path(step.input_path).parent / "scan_peak.xyz")
    try:
        parsed = TsGuess()._scan_parse(TsGuess_input_schema(
            mode="scan_parse", engine=declaration.engine,
            log_path=_refinement_log_path(record, step), ts_candidate_path=target,
        ))
    except (ValueError, OSError) as exc:
        return _block(record, "guess", "scan_parse_failed", str(exc), needs=["scan"])
    if (not parsed.is_success or parsed.scan_has_internal_peak is not True
            or parsed.candidate_unavailable or not parsed.ts_candidate_path
            or not Path(parsed.ts_candidate_path).is_file()):
        return _block(record, "guess", "scan_no_candidate",
                      "Scan produced no usable internal-peak geometry. " + parsed.message,
                      atom_details=parsed.verdicts, needs=["scan"])
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    try:
        candidate_atoms = read_xyz_atoms(parsed.ts_candidate_path)
        built = _read_built_xyz(record, "reactant")
        if built is None or [symbol for symbol, _ in candidate_atoms] != built[0]:
            raise ValueError("Scan peak atom identity/order differs from the assembled reactant")
        if not all(math.isfinite(value) for _, position in candidate_atoms for value in position):
            raise ValueError("Scan peak has nonfinite coordinates")
    except (ValueError, OSError) as exc:
        return _block(record, "guess", "scan_invalid_geometry", str(exc), needs=["scan"])
    record.current_ts_guess_path = parsed.ts_candidate_path
    record.path_kind = "scan"
    record.evidence_candidates.extend([_refinement_log_path(record, step), parsed.ts_candidate_path])
    _record_stage(record, "guess", "done", "Scan internal peak extracted; unconstrained refinement still required.", [parsed.ts_candidate_path])
    return record


def _guess(record: TsProcessRecord) -> TsProcessRecord:
    """路径初猜：**先把产物按 atom_map 重排到与反应物同序**，再跑 xTB MTD 路径。

    重排是必须的：路径搜索要求两端是同一套、同序的原子，而两端是各自按连通分量拼装的
    （实测元素序列不同）。重排后的产物几何落在 ``path/product_reordered.xyz``，可复查。
    xTB 缺失时退回 IDPP 并**显式写进 path_kind**。
    """
    if record.declaration.scan is not None:
        return _guess_scan(record)

    from cloudra.persistence.fs_utils import atomic_write_text
    from cloudra.tools.core.xtb_path_runner import (
        XTB_ENGINE_STARTED_TERMINATIONS,
        XtbPathRequest,
        run_xtb_path,
    )

    out_dir = (os.path.join(record.run_dir, PATH_STAGE_DIR,
                            f"guided_attempt_{record.guidance_attempt:04d}")
               if record.active_attempt_dir else
               os.path.join(record.run_dir, PATH_STAGE_DIR))
    record.current_ts_guess_path = ""
    os.makedirs(out_dir, exist_ok=True)

    reactant = _read_built_xyz(record, "reactant")
    if reactant is None:
        return _block(
            record, "guess", "missing_built_geometry",
            "the built first endpoint geometry is missing from the run directory, so no path guess "
            "could be constructed",
            needs=["reactant_smiles"],
        )
    r_symbols, r_pos = reactant[0], reactant[1]
    if record.declaration.product_geometry is not None:
        # 第二端 = 第一端绕声明的键旋转（阻转异构等"两端同一分子"的题型走这条）
        error, reordered = _derive_product_geometry(record, reactant)
        if error:
            return _block(
                record, "guess", "product_geometry_failed", error, needs=["product_geometry"],
            )
    else:
        product = _read_built_xyz(record, "product")
        if product is None:
            return _block(
                record, "guess", "missing_built_geometry",
                "the built second endpoint geometry is missing from the run directory, so no path "
                "guess could be constructed",
                needs=["product_smiles"],
            )
        p_pos = product[1]
        atom_map = record.declaration.atom_map
        if len(atom_map) != len(r_symbols):
            return _block(
                record, "guess", "atom_map_length_mismatch",
                f"atom_map has {len(atom_map)} entries for {len(r_symbols)} atoms",
                needs=["atom_map"],
            )
        # 产物第 k 个原子 → 反应物第 atom_map[k]-1 个位置
        reordered = [None] * len(r_symbols)
        for product_index, target in enumerate(atom_map):
            reordered[target] = list(p_pos[product_index])
        if any(position is None for position in reordered):
            return _block(
                record, "guess", "atom_map_not_a_permutation",
                "the atom_map does not cover every reordered position; reordering would leave holes",
                needs=["atom_map"],
            )

    def xyz_block(symbols, positions, comment: str) -> str:
        lines = [str(len(symbols)), comment]
        for symbol, position in zip(symbols, positions):
            lines.append(
                f"{symbol:<3} {position[0]:>16.8f} {position[1]:>16.8f} {position[2]:>16.8f}"
            )
        return "\n".join(lines) + "\n"

    reactant_xyz = xyz_block(r_symbols, r_pos, "ts_process reactant (as built)")
    product_xyz = xyz_block(r_symbols, reordered, "ts_process product (reordered by atom_map)")
    reordered_path = os.path.join(out_dir, "product_reordered.xyz")
    atomic_write_text(reordered_path, product_xyz)

    request = XtbPathRequest(
        reactant_xyz=reactant_xyz,
        product_xyz=product_xyz,
        output_dir=out_dir,
        charge=record.declaration.charge,
        multiplicity=record.declaration.multiplicity,
        run_label="guess",
        extra_args=(
            [f"--{record.declaration.path_solvation.model}", record.declaration.path_solvation.solvent]
            if record.declaration.path_solvation else []
        ),
    )
    # 声明给了上限就用它（GH #39：撞上限的截断路径不是初猜，抬高上限重跑才是出路）；
    # 0 = 未声明，交给 runner 默认值。
    if record.declaration.budget.path_refinement_runs > 0:
        request.refinement_runs = record.declaration.budget.path_refinement_runs
    run = run_xtb_path(request)
    if run.termination_reason == "executable_missing":
        from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

        # 复用 ts_guess 的同一份 IDPP 实现；两端已按显式 atom_map 对齐。
        # 插值帧只是无约束 OptTS 的几何种子，不提供鞍点或能垒证据。
        try:
            fallback = TsGuess()._interpolate(TsGuess_input_schema(
                mode="interpolate",
                reactant_text=reactant_xyz,
                product_text=product_xyz,
                engine=record.declaration.engine,
                interp_method="idpp",
                output_dir=os.path.join(out_dir, "idpp_images"),
            ))
        except (ValueError, OSError) as exc:
            return _block(
                record, "guess", "idpp_fallback_failed",
                f"xtb is unavailable and IDPP interpolation failed: {exc}",
                needs=["reactant_smiles", "product_smiles", "atom_map"],
            )
        if not fallback.is_success or not fallback.ts_candidate_path or not os.path.isfile(fallback.ts_candidate_path):
            return _block(
                record, "guess", "idpp_fallback_failed",
                "xtb is unavailable and IDPP interpolation produced no candidate geometry",
                needs=["reactant_smiles", "product_smiles", "atom_map"],
            )
        record.path_kind = "idpp_fallback"
        record.current_ts_guess_path = fallback.ts_candidate_path
        record.evidence_candidates.extend([reordered_path, fallback.ts_candidate_path])
        _record_stage(
            record, "guess", "done",
            "xtb is not on PATH: the path guess fell back to IDPP interpolation "
            "(path_kind=idpp_fallback). This is a degraded geometric seed for unconstrained "
            "refinement, not a saddle point or energy peak.",
            [reordered_path, fallback.ts_candidate_path],
        )
        return record
    if not run.usable_as_guess:
        # "跑了但没出可用初猜" ≠ "根本没搜"：引擎确实启动过的终止类别单独上报，
        # not_attempted 只留给引擎没起来的失败（端点非法等）——GH #39 实测
        # incomplete_artifacts 时 run_dir 里已有 24 帧采样，报成 not_attempted
        # 会让上层误判"根本没搜"。
        record.path_kind = (
            "xtb_path_failed"
            if run.termination_reason in XTB_ENGINE_STARTED_TERMINATIONS
            else "not_attempted"
        )
        if run.termination_reason == "path_not_converged":
            # 触顶 = 路径被截断（引擎没判收敛）。实测：这种路径的最高帧落在反应物自己的盆地里
            # （离起点 21°），拿去做 OptTS 不收敛。因此**不**把它当初猜交出去。
            return _block(
                record, "guess", run.termination_reason,
                f"the xTB path refinement hit its {run.refinement_runs}-cycle ceiling before the "
                f"engine declared convergence, so the path's highest frame is a truncated sample "
                f"and must not be used as a TS guess ({run.refinement_runs} is a compute ceiling, "
                f"not a convergence criterion). Raise the ceiling via ts_resume with "
                f"adjustment.path_refinement_runs and rerun. Persistent run directory "
                f"(truncated path kept for inspection): {run.run_dir}",
                atom_details=list(run.diagnostics),
                needs=["budget"],
            )
        partial = (
            f" {len(run.partial_frames)} partial iteration frame(s) were left behind "
            f"(sampling artifacts, not a usable guess)."
            if run.partial_frames else ""
        )
        return _block(
            record, "guess", run.termination_reason,
            f"the xTB path search did not produce a usable guess ({run.termination_reason}, "
            f"returncode={run.returncode}).{partial} Persistent run directory: {run.run_dir}. "
            f"Next step: ts_resume with adjustment.scan (method, scans, optional freeze) when one "
            f"forming/breaking bond or angle is clear (take the atom indices from "
            f"internal_coordinates first); (b) ts_guess mode='interpolate' (IDPP) — only when both "
            f"endpoint geometries and the all-atom map are already trustworthy. Either way the "
            f"result is a path/guess, not a saddle: an unconstrained OptTS with frequency and IRC "
            f"is still required.",
            atom_details=list(run.diagnostics),
            needs=["scan", "reaction_center", "atom_map", "reactant_smiles", "product_smiles"],
        )
    record.path_kind = "xtb_path"
    record.current_ts_guess_path = run.ts_xyz_path
    record.evidence_candidates.extend([reordered_path, run.path_xyz_path, run.ts_xyz_path])
    _record_stage(
        record, "guess", "done",
        f"xTB MTD path search: {len(run.frames)} frames, TS candidate {run.ts_candidate_energy_eh:.6f} Eh",
        [reordered_path, run.path_xyz_path, run.ts_xyz_path],
    )
    return record


def _validate(record: TsProcessRecord) -> TsProcessRecord:
    """内部校验闸门。失败 → 阻塞并**点名到原子**（诱导 agent 改对声明，而不是拦截）。"""
    import numpy as np

    params = _active_reaction_center(record)
    guess_dir = os.path.join(record.run_dir, PATH_STAGE_DIR)
    run_dirs = sorted(
        Path(guess_dir).glob("xtb_path_runs/*")
    ) if os.path.isdir(guess_dir) else []
    if record.path_kind in ("xtb_path", "scan", "idpp_fallback") and (record.current_ts_guess_path or run_dirs):
        ts_path = (record.current_ts_guess_path if (record.active_attempt_dir or record.current_ts_guess_path or record.path_kind == "scan") else
                   os.path.join(str(run_dirs[-1]), "xtbpath_ts.xyz"))
        if os.path.isfile(ts_path):
            lines = Path(ts_path).read_text(encoding="utf-8").splitlines()
            count = int(lines[0].strip())
            positions = np.asarray(
                [[float(v) for v in line.split()[1:4]] for line in lines[2: 2 + count]],
                dtype=float,
            )
            # 反应中心距离：超出合理区间就是可执行的、点名到原子的反馈
            detail: list[str] = []
            base = 0 if record.declaration.engine == "orca" else 1
            for left, right in params:
                distance = float(np.linalg.norm(positions[left] - positions[right]))
                if distance < 0.5:
                    detail.append(
                        f"reaction-centre pair ({left + base}, {right + base}) is {distance:.3f} A apart in the "
                        "TS candidate — below 0.5 A, which is not a chemically meaningful saddle "
                        "region"
                    )
                elif distance > 4.0:
                    detail.append(
                        f"reaction-centre pair ({left + base}, {right + base}) is {distance:.3f} A apart in the "
                        "TS candidate — the path never brought them together"
                    )
            if detail:
                return _block(
                    record, "validate", "reaction_center_distance_out_of_range",
                    "the TS candidate does not place the declared reaction centre in a plausible "
                    "range; adjust the declaration and resume",
                    atom_details=detail,
                    needs=["reaction_center", "atom_map"],
                )
    _record_stage(record, "validate", "done", "internal validation passed")
    return record


def _write_refinement_input(record: TsProcessRecord, job_dir: str) -> tuple[str, str]:
    """把 TS 候选写成精修作业的引擎输入；返回 ``(错误, 输入路径)``。

    复用 `qm_input_writer` 的构建器与校验（延迟导入）而不是另写一套输入语法：同一个引擎语法
    只能有一份实现，否则同一份作业会在两条入口下写出不同的文件、走不同的校验。
    """
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
    from cloudra.tools.core.calculation_intent import (
        inspect_input,
        intent_from_writer,
        validate_writer_request,
    )
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    declaration = record.declaration
    method = declaration.method.strip()
    if "/" in method:
        head, _sep, basis = method.partition("/")
        method_name, basis_name = head.strip(), basis.strip()
    else:
        method_name, basis_name = method, ""
    if not method_name:
        return f"method {declaration.method!r} has no method part before '/'", ""

    guess_dir = os.path.join(record.run_dir, PATH_STAGE_DIR)
    source = ""
    if record.active_attempt_dir or record.current_ts_guess_path or record.path_kind == "scan":
        source = record.current_ts_guess_path
        if source and not os.path.isfile(source):
            source = ""
    else:
        run_dirs = sorted(Path(guess_dir).glob("xtb_path_runs/*")) if os.path.isdir(guess_dir) else []
        for run_dir in reversed(run_dirs):
            candidate = os.path.join(str(run_dir), "xtbpath_ts.xyz")
            if os.path.isfile(candidate):
                source = candidate
                break
    if not source:
        # 降级路线（IDPP）下没有 MTD 的 TS 候选：如实报出，不去拿别的帧冒充
        return (
            "no TS candidate was produced by the guess stage, so there is nothing to refine "
            f"(looked for xtbpath_ts.xyz under {guess_dir})",
            "",
        )

    atoms = read_xyz_atoms(source)
    coords = "\n".join(
        f"{symbol:<4} {position[0]:>14.8f} {position[1]:>14.8f} {position[2]:>14.8f}"
        for symbol, position in atoms
    )

    input_name = REFINEMENT_INPUT_NAMES[declaration.engine]
    input_path = os.path.join(job_dir, input_name)
    # 引擎各自的原生 TS 写法由项目的 skill 规定（references/orca-inputs.md /
    # gaussian-inputs.md）。ORCA 用 `! OptTS`，初始 Hessian 走原生 %geom 块；
    # **频率是后续独立作业**（skill 的"Frequency and IRC follow-ups"），因此这里只写 TS 优化，
    # 频率/IRC 归 refine 阶段。若 skill 里的配方变了，改这里一处即可。
    if declaration.engine == "orca":
        task_type: list[dict] = [{"opt": "ts"}]
        orca_blocks: Optional[str] = "%geom\n  Calc_Hess true\nend"
    else:
        task_type = [{"opt": "TS,calcfc,noeigen"}]
        orca_blocks = None
    request = QmInputWriter_input_schema(
        engine=declaration.engine,
        source_type="xyz_file",
        source_value=source,
        method=method_name,
        basis_set=basis_name,
        task_type=task_type,
        extra_keywords=declaration.extra_keywords,
        orca_blocks=orca_blocks,
        charge=declaration.charge,
        multiplicity=declaration.multiplicity,
        title=f"TS refinement: {declaration.reactant_smiles} -> {declaration.product_smiles}",
        output_dir=input_path,
    )
    # 输入冲突前置校验（与 qm_input_writer 同一份）
    conflicts = validate_writer_request(request.model_dump())
    if conflicts:
        return "refinement input refused: " + " | ".join(
            f"[{c['code']}] {c['message']}" for c in conflicts
        ), ""

    content = (
        QmInputWriter._build_orca_input(request, coords)
        if declaration.engine == "orca"
        else QmInputWriter._build_gjf(request, coords)
    )
    # 不信 writer 自述：从生成文本重新 inspect，任务集合不一致即失败（同一份纪律）
    inspected = inspect_input(content, engine=declaration.engine)
    requested = intent_from_writer(request.model_dump())
    if inspected.tasks != requested.tasks:
        return (
            "refinement input internal mismatch: the generated file encodes tasks "
            f"{sorted(inspected.tasks)} but {sorted(requested.tasks)} were requested",
            "",
        )
    atomic_write_text(input_path, content)
    return "", input_path


def _submit(record: TsProcessRecord) -> TsProcessRecord:
    """提交精修作业：写输入 → **复用**唯一一份准入校验 → 入库为 ready。

    入库用**同步** ``insert_compute_job``：本进程整体跑在工具的工作线程里（不是事件循环
    线程），项目的同步 SQLite 纪律允许在工作线程使用。关键是准入判断与
    ``submit_compute_job`` 共用 ``services/compute_admission.admit_job``——**没有第二套**，
    否则同一份作业会在两条入口下得出不同的准入结论。
    """
    declaration = record.declaration
    if not record.owner_conversation_id:
        # 归属缺失不是声明能修的：直接点名死因，别让 agent 去改 method/budget
        return _block(
            record, "submit", "owner_missing",
            "this run carries no owner identity, so its compute jobs would be undeliverable "
            "dead letters; refusing to submit. Start the run through ts_prepare so the "
            "calling project/agent is stamped.",
        )
    jobs_root = os.path.join(record.run_dir, JOBS_STAGE_DIR)
    os.makedirs(jobs_root, exist_ok=True)
    existing = [name for name in os.listdir(jobs_root) if name.startswith("job_")]
    job_dir = os.path.join(jobs_root, f"job_{len(existing) + 1:04d}")
    os.makedirs(job_dir, exist_ok=True)

    error, input_path = _write_refinement_input(record, job_dir)
    if error:
        return _block(
            record, "submit", "refinement_input_failed", error, needs=["method", "engine"]
        )

    # 精修是重活：资源按声明申请；方法与基组已写进输入，准入据此核对输入自述需求。
    # 准入 + 入库收在 _submit_step（与 refine 的频率作业走同一条路径，只有一份）。
    job_type = "orca" if declaration.engine == "orca" else "gaussian"
    error, job_id = _submit_step(record, "ts_opt", input_path, job_type)
    if error:
        return _block(
            record, "submit", "compute_admission_rejected", error,
            needs=["method", "engine", "budget"],
        )
    record.job_id = int(job_id)
    record.job_input_path = input_path
    record.job_steps = [TsJobStep(
        purpose="ts_opt", job_id=job_id, input_path=input_path, state="ready",
    )]
    _record_stage(
        record, "submit", "done",
        f"refinement job {job_id} submitted as 'ready' ({job_type}, {declaration.method}); the "
        "scheduler daemon claims it and its terminal state arrives through the existing compute "
        "notification path",
        [input_path],
    )
    return record


class TsJobStep(BaseModel):
    """精修作业序列里的一步（TS、IRC 与两端极小值验证）。"""

    purpose: Literal[
        "scan", "ts_opt", "frequency", "irc", "reactant_opt", "reactant_frequency",
        "product_opt", "product_frequency",
    ]
    job_id: Optional[int] = None
    input_path: str = ""
    state: str = Field(default="", description="compute_jobs 里的状态；终态见 TERMINAL_STATES")


def _read_job_state(record: TsProcessRecord, job_id: Optional[int]) -> str:
    """读作业当前状态；读不到返回 ``"missing"``（不猜成成功）。"""
    if job_id is None:
        return "missing"
    from cloudra.persistence.database import ComputeDB

    db = ComputeDB().init()
    with db.connect() as con:
        row = con.execute("SELECT state FROM compute_jobs WHERE id = ?", (job_id,)).fetchone()
    return str(row[0]) if row else "missing"


def _submit_step(record: TsProcessRecord, purpose: str, input_path: str,
                 job_type: str) -> tuple[str, int]:
    """准入 + 入库为 ready，并把这一步登记进作业序列。返回 ``(错误, job_id)``。

    归属与 ``submit_compute_job`` 同一纪律：conversation_id 是发起项目、
    session_id 是发起 agent——终态推送（ComputeNotifyBroker）只认这两个字段，
    缺归属的作业是投递不到的死信，宁可拒收也不入库。
    """
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_admission import admit_job
    from cloudra.services.compute_store import insert_compute_job

    if not record.owner_conversation_id:
        return (
            "this run carries no owner identity (owner_conversation_id is empty), so its "
            "compute jobs would be undeliverable dead letters; refusing to submit. Start the "
            "run through ts_prepare so the calling project/agent is stamped.",
            -1,
        )

    # charge/multiplicity 是 xtb 专属运行参数，orca/gaussian 作业必须留默认——电荷/自旋已经
    # 写在输入文件里，再传一次会被准入 fail-loud 拒收（"绝不静默丢弃"那道门）
    admission = admit_job(
        input_file=input_path,
        job_type=job_type,
        cpus=REFINEMENT_CPUS,
        memory_mb=REFINEMENT_MEMORY_MB,
        execution_backend="auto",
    )
    if not admission.ok:
        return admission.message, -1

    db = ComputeDB().init()
    job_id = int(insert_compute_job(
        db,
        conversation_id=record.owner_conversation_id,
        session_id=record.owner_session_id,
        path=input_path,
        state="ready",
        jobtype=job_type,
        node_id=admission.node_id,
        scheduler=admission.scheduler,
        scheduler_options=json.dumps(admission.scheduler_options, ensure_ascii=False),
        priority=0,
        req_cpus=REFINEMENT_CPUS,
        req_memory_mb=REFINEMENT_MEMORY_MB,
    ))
    return "", job_id


def _refinement_log_path(record: TsProcessRecord, step: TsJobStep) -> str:
    """该步作业的实测日志路径（走统一的 resolve_log_path，不猜文件名）。"""
    from cloudra.infra.compute_utils import resolve_log_path

    job_type = "orca" if record.declaration.engine == "orca" else "gaussian"
    return resolve_log_path(step.input_path, job_type=job_type, task_id=step.job_id)


def _write_frequency_input(record: TsProcessRecord, job_dir: str) -> tuple[str, str]:
    """从 TS 优化作业的**优化末帧**写频率作业输入；返回 ``(错误, 输入路径)``。

    频率是独立作业（`skills/.../orca-inputs.md` 的 "Frequency and IRC follow-ups"），
    几何必须取优化后的末帧，不是当初的 TS 候选——否则频率描述的不是收敛到的那个驻点。
    """
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
    from cloudra.tools.core import gaussian_frames, orca_frames
    from cloudra.tools.core.calculation_intent import (
        inspect_input,
        intent_from_writer,
        validate_writer_request,
    )
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    if not record.job_steps:
        return "no TS-optimisation job was submitted, so there is no optimised geometry", ""
    step = record.job_steps[-1]
    log_path = _refinement_log_path(record, step)
    if not os.path.isfile(log_path):
        return (
            f"the TS-optimisation job's log was not found at its registered location {log_path}; "
            "refusing to run frequencies on an unverified geometry",
            "",
        )
    frames_mod = orca_frames if record.declaration.engine == "orca" else gaussian_frames
    frames = frames_mod.extract_frames(log_path)
    if not frames:
        return f"no optimised frame could be extracted from {log_path}", ""

    # 优化末帧落在作业目录里（不是临时文件）：频率作业用的几何要能复查
    optimized_xyz = os.path.join(job_dir, "optimized.xyz")
    atomic_write_text(optimized_xyz, frames[-1].xyz)
    atoms = read_xyz_atoms(optimized_xyz)
    coords = "\n".join(
        f"{symbol:<4} {position[0]:>14.8f} {position[1]:>14.8f} {position[2]:>14.8f}"
        for symbol, position in atoms
    )

    declaration = record.declaration
    method = declaration.method.strip()
    head, _sep, basis = method.partition("/")
    input_path = os.path.join(job_dir, f"frequency.{'inp' if declaration.engine == 'orca' else 'gjf'}")
    request = QmInputWriter_input_schema(
        engine=declaration.engine,
        source_type="xyz_file",
        source_value=optimized_xyz,
        method=head.strip(),
        basis_set=basis.strip(),
        task_type=[{"freq": None}],
        extra_keywords=declaration.extra_keywords,
        charge=declaration.charge,
        multiplicity=declaration.multiplicity,
        title=f"frequency at the refined stationary point: {declaration.reactant_smiles}",
        output_dir=input_path,
    )
    conflicts = validate_writer_request(request.model_dump())
    if conflicts:
        return "frequency input refused: " + " | ".join(
            f"[{c['code']}] {c['message']}" for c in conflicts
        ), ""
    content = (
        QmInputWriter._build_orca_input(request, coords)
        if declaration.engine == "orca"
        else QmInputWriter._build_gjf(request, coords)
    )
    inspected = inspect_input(content, engine=declaration.engine)
    requested = intent_from_writer(request.model_dump())
    if inspected.tasks != requested.tasks:
        return (
            "frequency input internal mismatch: generated "
            f"{sorted(inspected.tasks)} but {sorted(requested.tasks)} were requested",
            "",
        )
    atomic_write_text(input_path, content)
    return "", input_path


def _write_irc_input(record: TsProcessRecord, job_dir: str) -> tuple[str, str]:
    """写 IRC 作业输入；返回 ``(错误, 输入路径)``。

    几何与频率作业**同一帧**（TS 优化末帧）——skill 要求"reuse its same-geometry frequency
    Hessian for both IRC directions"。两个引擎的原生写法照
    ``references/{orca,gaussian}-inputs.md``：

    - Gaussian：``task_type=[{"irc":"calcfc"}]``（默认双向，不加自定义步数上限）。
    - ORCA：``task_type=[{"irc": None}]`` + 原生 ``%irc`` 块。Hessian 走哪个分支由**证据**决定，
      不是偏好：频率作业真的落下了同名 ``.hess`` 就用 ``InitHess read`` + ``Hess_Filename``；
      没有就按 skill 说的 ``InitHess calc_numfreq``（数值评估），绝不默认请求解析外部 Hessian。
    """
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
    from cloudra.tools.core.calculation_intent import (
        inspect_input,
        intent_from_writer,
        validate_writer_request,
    )

    declaration = record.declaration
    frequency_step = next(
        (step for step in record.job_steps if step.purpose == "frequency"), None
    )
    if frequency_step is None:
        return "no frequency job was run, so its same-geometry Hessian cannot be reused", ""
    geometry = os.path.join(os.path.dirname(frequency_step.input_path), "optimized.xyz")
    if not os.path.isfile(geometry):
        return (
            f"the optimised geometry kept next to the frequency job ({geometry}) is missing; "
            "refusing to start IRC from an unverified geometry",
            "",
        )

    method = declaration.method.strip()
    head, _sep, basis = method.partition("/")
    input_path = os.path.join(job_dir, f"irc.{'inp' if declaration.engine == 'orca' else 'gjf'}")

    if declaration.engine == "orca":
        task_type: list[dict] = [{"irc": None}]
        hess_path = os.path.splitext(frequency_step.input_path)[0] + ".hess"
        if os.path.isfile(hess_path):
            # 频率作业真的落下了 Hessian：复用同一几何的 Hessian（skill 的首选做法）
            irca = (
                "%irc\n  Direction both\n  InitHess read\n"
                f'  Hess_Filename "{hess_path}"\nend'
            )
        else:
            irca = "%irc\n  Direction both\n  InitHess calc_numfreq\nend"
        orca_blocks: Optional[str] = irca
    else:
        task_type = [{"irc": "calcfc"}]
        orca_blocks = None

    request = QmInputWriter_input_schema(
        engine=declaration.engine,
        source_type="xyz_file",
        source_value=geometry,
        method=head.strip(),
        basis_set=basis.strip(),
        task_type=task_type,
        extra_keywords=declaration.extra_keywords,
        orca_blocks=orca_blocks,
        charge=declaration.charge,
        multiplicity=declaration.multiplicity,
        title=f"IRC both directions from the refined saddle: {declaration.reactant_smiles}",
        output_dir=input_path,
    )
    conflicts = validate_writer_request(request.model_dump())
    if conflicts:
        return "IRC input refused: " + " | ".join(
            f"[{c['code']}] {c['message']}" for c in conflicts
        ), ""
    content = (
        QmInputWriter._build_orca_input(request, _xyz_coords(geometry))
        if declaration.engine == "orca"
        else QmInputWriter._build_gjf(request, _xyz_coords(geometry))
    )
    inspected = inspect_input(content, engine=declaration.engine)
    requested = intent_from_writer(request.model_dump())
    if inspected.tasks != requested.tasks:
        return (
            f"IRC input internal mismatch: generated {sorted(inspected.tasks)} but "
            f"{sorted(requested.tasks)} were requested",
            "",
        )
    atomic_write_text(input_path, content)
    return "", input_path


def _xyz_coords(path: str) -> str:
    """把单帧 xyz 渲染成引擎坐标块（与精修/频率输入同一格式）。"""
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    return "\n".join(
        f"{symbol:<4} {position[0]:>14.8f} {position[1]:>14.8f} {position[2]:>14.8f}"
        for symbol, position in read_xyz_atoms(path)
    )


def _product_reordered_path(record: TsProcessRecord) -> str:
    return os.path.join(
        record.run_dir, PATH_STAGE_DIR,
        f"guided_attempt_{record.guidance_attempt:04d}" if record.active_attempt_dir else "",
        "product_reordered.xyz",
    )


def _endpoint_opt_frame(record: TsProcessRecord, step: TsJobStep) -> tuple[str, str]:
    """Extract the final geometry only when the endpoint optimization converged."""
    from cloudra.tools.core import gaussian_frames, orca_frames

    log_path = _refinement_log_path(record, step)
    if not os.path.isfile(log_path):
        return "", f"endpoint optimization log is missing at {log_path}"
    if record.declaration.engine == "orca":
        log_text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        converged = orca_frames.opt_converged(log_text)
        xyz = orca_frames.final_xyz_from_text(log_text)
    else:
        try:
            frames = gaussian_frames.extract_frames(log_path)
        except Exception as exc:
            return "", f"endpoint optimization geometry is unreadable: {exc}"
        converged = frames[-1].converged if frames else None
        xyz = frames[-1].xyz if frames else ""
    if converged is not True or not xyz.strip():
        return "", (
            "endpoint optimization did not prove convergence and a final geometry; "
            "normal job termination alone is insufficient"
        )
    return xyz, ""


def _write_endpoint_input(record: TsProcessRecord, job_dir: str,
                          role: Literal["reactant", "product"],
                          task: Literal["opt", "frequency"]) -> tuple[str, str]:
    """Write an unconstrained IRC-side Opt or a Freq at its converged Opt frame.

    The historic reactant/product step names are side A/B slots. Species identity is
    assigned only after both sides have optimized and passed frequency checks.
    """
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
    from cloudra.tools.core.calculation_intent import (
        inspect_input,
        intent_from_writer,
        validate_writer_request,
    )

    if task == "opt":
        irc_step = next(
            (step for step in reversed(record.job_steps) if step.purpose == "irc"), None,
        )
        if irc_step is None or irc_step.state != "done":
            return "a completed IRC job is required before optimizing its outer frames", ""
        irc_log = _refinement_log_path(record, irc_step)
        if not os.path.isfile(irc_log):
            return f"the IRC job log is missing at {irc_log}", ""
        from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

        checks: list[str] = []
        irc_input = TsGuess_input_schema(
            mode="verify", irc_log=irc_log, engine=record.declaration.engine,
            output_dir=os.path.join(record.run_dir, VERDICT_STAGE_DIR),
        )
        try:
            info = TsGuess._extract_irc_endpoints(irc_input, checks, require_two_sides=True)
        except Exception as exc:
            return f"IRC outer-frame extraction failed: {exc}", ""
        if info is None:
            return "IRC has no usable outer geometry on both sides: " + "; ".join(checks), ""
        source = info["path_a" if role == "reactant" else "path_b"]
        if not source or not os.path.isfile(source):
            return f"IRC side {'A' if role == 'reactant' else 'B'} outer frame is missing", ""
    else:
        opt_step = next(
            (step for step in reversed(record.job_steps) if step.purpose == f"{role}_opt"),
            None,
        )
        if opt_step is None:
            return f"{role} has no optimization job; refusing frequency on a raw seed", ""
        xyz, error = _endpoint_opt_frame(record, opt_step)
        if error:
            return f"{role} {error}", ""
        source = os.path.join(job_dir, "optimized.xyz")
        atomic_write_text(source, xyz.rstrip() + "\n")

    declaration = record.declaration
    head, _sep, basis = declaration.method.strip().partition("/")
    task_type = [{"opt": None}] if task == "opt" else [{"freq": None}]
    name = f"{role}_{task}.{'inp' if declaration.engine == 'orca' else 'gjf'}"
    input_path = os.path.join(job_dir, name)
    request = QmInputWriter_input_schema(
        engine=declaration.engine,
        source_type="xyz_file", source_value=source,
        method=head.strip(), basis_set=basis.strip(), task_type=task_type,
        extra_keywords=declaration.extra_keywords,
        charge=declaration.charge, multiplicity=declaration.multiplicity,
        title=f"IRC side {'A' if role == 'reactant' else 'B'} endpoint {task}",
        output_dir=input_path,
    )
    conflicts = validate_writer_request(request.model_dump())
    if conflicts:
        return f"{role} {task} input refused: " + " | ".join(
            f"[{item['code']}] {item['message']}" for item in conflicts
        ), ""
    content = (
        QmInputWriter._build_orca_input(request, _xyz_coords(source))
        if declaration.engine == "orca"
        else QmInputWriter._build_gjf(request, _xyz_coords(source))
    )
    if inspect_input(content, engine=declaration.engine).tasks != intent_from_writer(
        request.model_dump()
    ).tasks:
        return f"{role} {task} input task mismatch", ""
    atomic_write_text(input_path, content)
    return "", input_path


def _refine(record: TsProcessRecord) -> TsProcessRecord:
    """推进 TS Opt/Freq → IRC → 两端 Opt/Freq 作业序列。**从不轮询**。

    还没到终态时本阶段置 ``waiting`` 并**不推事件**：等计算不算"阻塞"，agent 不该被叫醒。
    作业终态由既有的 compute 通知路径投递，agent 收到后调 `ts_resume`（无需调整），
    本阶段重新读一次库里那一行继续推进。
    """
    from cloudra.services.compute_store import TERMINAL_STATES

    if not record.job_steps:
        return _block(
            record, "refine", "no_job_submitted",
            "the submit stage recorded no job, so there is nothing to refine",
            needs=["method", "engine"],
        )

    current = record.job_steps[-1]
    state = _read_job_state(record, current.job_id)
    current.state = state
    if state not in TERMINAL_STATES:
        record.waiting_for = f"job:{current.job_id}"
        _record_stage(
            record, "refine", "waiting",
            f"waiting for job {current.job_id} ({current.purpose}) to reach a terminal state; "
            "the existing compute notification path wakes the agent, so this stage never polls "
            "and emits no event",
        )
        return record

    record.waiting_for = ""
    if state != "done":
        log_path = _refinement_log_path(record, current)
        tail: list[str] = []
        if os.path.isfile(log_path):
            with open(log_path, encoding="utf-8", errors="replace") as handle:
                tail = handle.read().splitlines()[-15:]
        details = tail if tail else [f"log not found at {log_path}"]
        return _block(
            record, "refine", f"job_{state}",
            f"refinement job {current.job_id} ({current.purpose}) ended as {state!r}; plain "
            "per-engine failure classes come from the log below — the run is stopped, not silently "
            "retried",
            atom_details=details,
            needs=["method", "engine", "budget", "reaction_center"],
        )

    if current.purpose == "ts_opt":
        # 优化完成：取优化末帧写频率作业（频率是独立作业，见 skill）
        jobs_root = os.path.join(record.run_dir, JOBS_STAGE_DIR)
        job_dir = os.path.join(jobs_root, f"job_{len(record.job_steps) + 1:04d}")
        os.makedirs(job_dir, exist_ok=True)
        error, input_path = _write_frequency_input(record, job_dir)
        if error:
            return _block(
                record, "refine", "frequency_input_failed", error, needs=["method", "engine"]
            )
        job_type = "orca" if record.declaration.engine == "orca" else "gaussian"
        error, job_id = _submit_step(record, "frequency", input_path, job_type)
        if error:
            return _block(
                record, "refine", "compute_admission_rejected", error,
                needs=["method", "engine", "budget"],
            )
        record.job_steps.append(TsJobStep(
            purpose="frequency", job_id=job_id, input_path=input_path, state="ready",
        ))
        record.waiting_for = f"job:{job_id}"
        _record_stage(
            record, "refine", "waiting",
            f"TS optimisation converged (job {current.job_id}); frequency job {job_id} submitted on "
            "the optimised geometry. Waiting for its terminal state via the existing notification "
            "path",
            [input_path],
        )
        return record

    if current.purpose == "frequency":
        # 频率完成：TS 已由频率数据支持，接着跑 IRC（第二道闸），复用同一几何的 Hessian
        jobs_root = os.path.join(record.run_dir, JOBS_STAGE_DIR)
        job_dir = os.path.join(jobs_root, f"job_{len(record.job_steps) + 1:04d}")
        os.makedirs(job_dir, exist_ok=True)
        error, input_path = _write_irc_input(record, job_dir)
        if error:
            return _block(record, "refine", "irc_input_failed", error, needs=["method", "engine"])
        job_type = "orca" if record.declaration.engine == "orca" else "gaussian"
        error, job_id = _submit_step(record, "irc", input_path, job_type)
        if error:
            return _block(
                record, "refine", "compute_admission_rejected", error,
                needs=["method", "engine", "budget"],
            )
        record.job_steps.append(TsJobStep(
            purpose="irc", job_id=job_id, input_path=input_path, state="ready",
        ))
        record.waiting_for = f"job:{job_id}"
        _record_stage(
            record, "refine", "waiting",
            f"frequency job {current.job_id} finished; IRC job {job_id} submitted (both "
            "directions) from the same optimised geometry. Waiting for its terminal state via the "
            "existing notification path",
            [input_path],
        )
        return record

    if current.purpose in ("reactant_frequency", "product_frequency"):
        role = "reactant" if current.purpose.startswith("reactant") else "product"
        _minimum, reason = _validated_endpoint_minimum(record, role)
        if _minimum is None:
            return _terminal(
                record, "verdict", "candidate_only",
                f"IRC side {'A' if role == 'reactant' else 'B'} did not qualify as an "
                f"optimized minimum: {reason}",
            )

    endpoint_next = {
        "irc": ("reactant", "opt"),
        "reactant_opt": ("reactant", "frequency"),
        "reactant_frequency": ("product", "opt"),
        "product_opt": ("product", "frequency"),
    }.get(current.purpose)
    if endpoint_next is not None:
        role, task = endpoint_next
        jobs_root = os.path.join(record.run_dir, JOBS_STAGE_DIR)
        job_dir = os.path.join(jobs_root, f"job_{len(record.job_steps) + 1:04d}")
        os.makedirs(job_dir, exist_ok=True)
        error, input_path = _write_endpoint_input(record, job_dir, role, task)
        if error:
            if task == "frequency":
                return _terminal(
                    record, "verdict", "candidate_only",
                    f"{role} endpoint optimization cannot support a minimum: {error}. "
                    "Start a new TS run with a different endpoint seed if needed",
                )
            return _block(
                record, "refine", "endpoint_input_failed", error,
                needs=["method", "engine", f"{role}_smiles"],
            )
        job_type = "orca" if record.declaration.engine == "orca" else "gaussian"
        purpose = f"{role}_{task}"
        error, job_id = _submit_step(record, purpose, input_path, job_type)
        if error:
            return _block(
                record, "refine", "compute_admission_rejected", error,
                needs=["method", "engine", "budget"],
            )
        record.job_steps.append(TsJobStep(
            purpose=purpose, job_id=job_id, input_path=input_path, state="ready",
        ))
        record.waiting_for = f"job:{job_id}"
        _record_stage(
            record, "refine", "waiting",
            f"IRC side {'A' if role == 'reactant' else 'B'} endpoint {task} job {job_id} "
            "submitted; awaiting its compute notification",
            [input_path],
        )
        return record

    _record_stage(
        record, "refine", "done",
        f"refinement sequence complete: {[step.purpose for step in record.job_steps]}",
    )
    return record


def _validated_endpoint_minimum(
    record: TsProcessRecord, role: Literal["reactant", "product"],
) -> tuple[tuple[list[str], list[list[float]]] | None, str]:
    """Return a converged, zero-imaginary QM endpoint; identity is checked at verdict."""
    import math

    from cloudra.dag.evidence_ingest import snapshot_evidence_file, validate_species_minimum
    from cloudra.tools.core import gaussian_frames, orca_frames
    from cloudra.tools.core.irc_path import parse_xyz

    opt_step = next(
        (step for step in reversed(record.job_steps) if step.purpose == f"{role}_opt"), None,
    )
    freq_step = next(
        (step for step in reversed(record.job_steps) if step.purpose == f"{role}_frequency"),
        None,
    )
    if opt_step is None or freq_step is None:
        return None, f"{role} minimum has no endpoint Opt and Freq job evidence"
    if opt_step.state != "done" or freq_step.state != "done":
        return None, f"{role} endpoint Opt and Freq jobs have not both completed"
    opt_xyz, reason = _endpoint_opt_frame(record, opt_step)
    if reason:
        return None, f"{role} {reason}"
    freq_log = _refinement_log_path(record, freq_step)
    if not os.path.isfile(freq_log):
        return None, f"{role} endpoint frequency log is missing"
    snapshot = snapshot_evidence_file(freq_log, workspace_root=record.workspace_dir)
    minimum = validate_species_minimum(
        snapshot.frequencies, snapshot.imaginary_frequencies,
    )
    if not (minimum.verified and minimum.is_valid):
        return None, f"{role} endpoint minimum is unverified: {minimum.message}"
    xyz_path = os.path.join(os.path.dirname(freq_step.input_path), "optimized.xyz")
    if not os.path.isfile(xyz_path):
        return None, f"{role} optimized endpoint geometry is missing at {xyz_path}"
    optimized = parse_xyz(opt_xyz)
    saved = parse_xyz(Path(xyz_path).read_text(encoding="utf-8"))
    if record.declaration.engine == "orca":
        freq_xyz = orca_frames.final_xyz_from_text(
            Path(freq_log).read_text(encoding="utf-8", errors="replace")
        )
    else:
        try:
            frames = gaussian_frames.extract_frames(freq_log)
        except Exception as exc:
            return None, f"{role} endpoint frequency geometry is unreadable: {exc}"
        freq_xyz = frames[-1].xyz if frames else ""
    measured = parse_xyz(freq_xyz) if freq_xyz else None

    def same_geometry(left, right) -> bool:
        return bool(
            left is not None and right is not None
            and left[0] == right[0]
            and len(left[1]) == len(right[1])
            and all(
                math.dist(a, b) <= 1e-4
                for a, b in zip(left[1], right[1], strict=True)
            )
        )

    if not same_geometry(optimized, saved) or not same_geometry(optimized, measured):
        return None, (
            f"{role} endpoint geometry in the optimization log, saved frequency source, and frequency "
            "log does not match; it cannot serve as a proven minimum reference"
        )
    return (optimized[0], optimized[1]), ""


def _endpoint_identity_error(
    record: TsProcessRecord, role: Literal["reactant", "product"],
    optimized: tuple[list[str], list[list[float]]],
) -> str:
    """Require the optimized full-atom bond graph to remain the declared species."""
    import math

    from rdkit import Chem

    from cloudra.tools.core.irc_path import (
        COVALENT_RADII,
        DISTANCE_CONNECTIVITY_FACTOR,
        perceive_bonds,
    )

    source_role = (
        "reactant" if role == "product" and record.declaration.product_geometry is not None
        else role
    )
    built = _read_built_xyz(record, source_role)
    if built is None or not built[3] or not os.path.isfile(built[3]):
        return f"{role} declared endpoint MOL is missing; connectivity is unverified"
    mol = Chem.MolFromMolBlock(Path(built[3]).read_text(encoding="utf-8"), removeHs=False)
    if mol is None:
        return f"{role} declared endpoint MOL cannot be parsed; connectivity is unverified"
    expected_smiles = (
        record.declaration.reactant_smiles if source_role == "reactant"
        else record.declaration.product_smiles
    )
    declared = Chem.MolFromSmiles(expected_smiles)
    if declared is None or Chem.MolToSmiles(Chem.RemoveHs(mol)) != Chem.MolToSmiles(declared):
        return f"{role} built MOL does not match its declared SMILES; connectivity is unverified"
    n = mol.GetNumAtoms()
    if role == "product" and record.declaration.product_geometry is None:
        remap = list(record.declaration.atom_map)
    else:
        remap = list(range(n))
    if sorted(remap) != list(range(n)) or len(optimized[0]) != n:
        return f"{role} endpoint atom map or atom count is inconsistent; connectivity is unverified"
    expected_symbols = [""] * n
    for atom in mol.GetAtoms():
        expected_symbols[remap[atom.GetIdx()]] = atom.GetSymbol()
    if expected_symbols != optimized[0]:
        return f"{role} optimized atom order differs from the declared species; connectivity is unverified"
    expected_bonds = {
        tuple(sorted((remap[bond.GetBeginAtomIdx()], remap[bond.GetEndAtomIdx()]))):
        float(bond.GetBondTypeAsDouble())
        for bond in mol.GetBonds()
    }
    fragments = Chem.GetMolFrags(mol)
    if len(fragments) == 1:
        actual_bonds, source = perceive_bonds(
            optimized[0], optimized[1], record.declaration.charge,
        )
        if source != "rdDetermineBonds":
            return f"{role} optimized connectivity could not be determined by RDKit"
    else:
        # A charged entrance complex often defeats whole-molecule bond perception:
        # infer each declared fragment with its own formal charge, then screen
        # cross-fragment pairs geometrically rather than calling an H-bond covalent.
        actual_bonds = {}
        fragment_ids: dict[int, int] = {}
        fragment_charges: list[int] = []
        ionic_metal_fragments: set[int] = set()
        for fragment_number, original_indices in enumerate(fragments):
            indices = [remap[index] for index in original_indices]
            fragment_ids.update((index, fragment_number) for index in indices)
            fragment_charge = sum(
                mol.GetAtomWithIdx(index).GetFormalCharge() for index in original_indices
            )
            fragment_charges.append(fragment_charge)
            if len(original_indices) == 1 and fragment_charge > 0 and (
                mol.GetAtomWithIdx(original_indices[0]).GetSymbol()
                in {"Li", "Na", "K", "Rb", "Cs", "Mg", "Ca", "Sr", "Ba"}
            ):
                ionic_metal_fragments.add(fragment_number)
            fragment_bonds, source = perceive_bonds(
                [optimized[0][index] for index in indices],
                [optimized[1][index] for index in indices],
                fragment_charge,
            )
            if source != "rdDetermineBonds":
                return f"{role} optimized fragment connectivity could not be determined by RDKit"
            actual_bonds.update({
                tuple(sorted((indices[left], indices[right]))): order
                for (left, right), order in fragment_bonds.items()
            })
        for left in range(n):
            for right in range(left + 1, n):
                if fragment_ids[left] == fragment_ids[right]:
                    continue
                left_fragment = fragment_ids[left]
                right_fragment = fragment_ids[right]
                # Monatomic metal counterions can sit well inside a covalent-radius
                # cutoff while the declared species remains a disconnected salt.
                if (
                    left_fragment in ionic_metal_fragments
                    and fragment_charges[right_fragment] < 0
                ) or (
                    right_fragment in ionic_metal_fragments
                    and fragment_charges[left_fragment] < 0
                ):
                    continue
                limit = DISTANCE_CONNECTIVITY_FACTOR * (
                    COVALENT_RADII.get(optimized[0][left], 1.2)
                    + COVALENT_RADII.get(optimized[0][right], 1.2)
                )
                if math.dist(optimized[1][left], optimized[1][right]) <= limit:
                    return (
                        f"{role} has an ambiguous close interfragment contact "
                        f"{left + atom_index_base(record.declaration.engine)}-{right + atom_index_base(record.declaration.engine)}; connectivity cannot be verified"
                    )

    missing = set(expected_bonds) - set(actual_bonds)
    extra = {
        pair for pair in set(actual_bonds) - set(expected_bonds)
        if math.dist(optimized[1][pair[0]], optimized[1][pair[1]]) <=
        DISTANCE_CONNECTIVITY_FACTOR * (
            COVALENT_RADII.get(optimized[0][pair[0]], 1.2)
            + COVALENT_RADII.get(optimized[0][pair[1]], 1.2)
        )
    }
    if missing or extra:
        return (
            f"{role} optimized connectivity differs from the declared species: "
            f"missing bonds={sorted(missing)}, extra bonds={sorted(extra)}"
        )
    different_orders = [
        pair for pair in expected_bonds.keys() & actual_bonds.keys()
        if abs(expected_bonds[pair] - actual_bonds[pair]) > 0.1
    ]
    if different_orders:
        return f"{role} optimized bond order differs from the declared species at {different_orders}"
    return ""


def _irc_interval_proof(
    record: TsProcessRecord, irc_log: str, freq_step: "TsJobStep",
    reactant: tuple[list[str], list[list[float]]],
    product: tuple[list[str], list[list[float]]],
    expected_assignment: Literal["direct", "swapped"],
) -> tuple[bool, str]:
    """verified 的区间证明：每个 IRC 双侧端点几何上位于 TS 与对应声明极小值之间。

    材料：TS 几何（频率作业旁的 ``optimized.xyz``）、两端经 Opt 收敛且 Freq
    零虚频的极小值、IRC 双侧端点（复用 ts_guess 的引擎分发提取，
    原子对齐用 irc_path.align_atom_order）。证明本体是
    irc_path.assign_irc_endpoints（与 ts_guess strict / benchmark selfconsistency
    同一实现）。任何材料缺失、对齐不可判或证明不成立都返回 ``(False, 原因)``——
    调用方落 candidate_only，绝不升格 verified。
    """
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
    from cloudra.tools.core.irc_path import (
        align_atom_order,
        assign_irc_endpoints,
        parse_xyz,
    )
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    ts_xyz = os.path.join(os.path.dirname(freq_step.input_path), "optimized.xyz")
    if not os.path.isfile(ts_xyz):
        return False, (
            f"the optimised TS geometry kept next to the frequency job ({ts_xyz}) is missing, "
            "so the interval proof has no TS anchor"
        )
    ts_atoms = read_xyz_atoms(ts_xyz)
    ts_symbols = [symbol for symbol, _ in ts_atoms]
    ts_pos = [list(position) for _, position in ts_atoms]

    checks: list[str] = []
    irc_input = TsGuess_input_schema(
        mode="verify",
        irc_log=irc_log,
        engine=record.declaration.engine,
        output_dir=os.path.join(record.run_dir, VERDICT_STAGE_DIR),
        charge=record.declaration.charge,
    )
    info = TsGuess._extract_irc_endpoints(irc_input, checks, require_two_sides=True)
    if info is None:
        return False, "no usable bidirectional IRC endpoint geometries: " + "; ".join(checks)
    end_a = parse_xyz(info["end_a"].xyz)
    end_b = parse_xyz(info["end_b"].xyz)
    if end_a is None or end_b is None:
        return False, "the extracted IRC endpoint geometries could not be parsed"

    aligned: list[list] = []
    for label, symbols, positions in (
        ("IRC endpoint A", end_a[0], end_a[1]),
        ("IRC endpoint B", end_b[0], end_b[1]),
        ("reactant minimum", reactant[0], reactant[1]),
        ("product minimum", product[0], product[1]),
    ):
        result = align_atom_order(ts_symbols, ts_pos, list(symbols), positions)
        if result is None:
            return False, (
                f"{label} could not be aligned to the TS atom order (composition mismatch, no "
                "element-consistent assignment, or aligned distance-matrix rmsd above the gate); "
                "this combination is undecidable"
            )
        aligned.append([list(positions[k]) for k in result[0]])

    watch_pairs = [
        [int(left) + 1, int(right) + 1] for left, right in _active_reaction_center(record)
    ]
    proof = assign_irc_endpoints(
        ts_symbols, ts_pos, aligned[0], aligned[1], aligned[2], aligned[3],
        watch_pairs, record.declaration.charge,
    )
    if not proof["is_decidable"]:
        return False, (
            "the geometric change between the TS and the declared minima is too small to "
            "judge the direction of the IRC endpoints"
        )
    if not proof["is_match"]:
        return False, (
            "at least one IRC endpoint does not lie between the TS and any declared minimum; "
            "the path does not demonstrably connect the declared minima"
        )
    if proof["assignment"] != expected_assignment:
        return False, (
            "the interval pairing contradicts the provenance of the optimized IRC outer "
            f"frames (proof={proof['assignment']}, source={expected_assignment})"
        )
    return True, (
        "each IRC endpoint lies between the TS and the corresponding declared minimum "
        f"({proof['assignment']} pairing; interval proof per irc_path.assign_irc_endpoints)"
    )


def _verdict(record: TsProcessRecord) -> TsProcessRecord:
    """判定四态终态：TS 一虚频、IRC 双侧可用几何、两端 Opt/Freq 证实为极小值，
    且各 IRC 端点位于 TS 与对应极小值之间，才算 ``verified``。

    判定只读**交付物**（频率作业的日志），缺失频率数据一律算"未验证"——
    "没做频率分析"绝不能被当成"已验证的鞍点"（与 `dag/evidence_ingest` 同一套三态语义）。
    IRC 的引擎收敛标志不证明连通，也不是区间证明的前置条件；两侧几何或
    端点证据不足时仍只能到 candidate_only。
    """
    from cloudra.dag.evidence_ingest import snapshot_evidence_file

    freq_step = next(
        (step for step in reversed(record.job_steps) if step.purpose == "frequency"), None
    )
    if freq_step is None:
        return _terminal(
            record, "verdict", "candidate_only",
            "no frequency job was run, so the stationary point is UNVERIFIED",
        )
    log_path = _refinement_log_path(record, freq_step)
    if not os.path.isfile(log_path):
        return _terminal(
            record, "verdict", "candidate_only",
            f"the frequency job's log was not found at its registered location {log_path}; "
            "without it the stationary point is UNVERIFIED",
        )

    snapshot = snapshot_evidence_file(log_path, workspace_root=record.workspace_dir)
    freqs = snapshot.frequencies
    imaginary = snapshot.imaginary_frequencies
    if freqs is None and imaginary is None:
        return _terminal(
            record, "verdict", "candidate_only",
            "the frequency job produced no frequency data, so the stationary point is UNVERIFIED",
        )
    imag = imaginary if imaginary is not None else [f for f in (freqs or []) if f < 0]
    if len(imag) != 1:
        kind = "a local minimum" if not imag else f"a point with {len(imag)} imaginary modes"
        return _terminal(
            record, "verdict", "candidate_only",
            f"frequency analysis found {len(imag)} imaginary mode(s) ({imag}); the candidate is "
            f"{kind}, not a first-order saddle point. This falsifies the candidate — it does NOT "
            "mean the reaction is impossible",
        )

    # 频率支持一阶鞍点。IRC 是第二道闸：没有 IRC 就只能到 candidate_only，绝不升格成 verified。
    # IRC 日志优先取本流程自己提交的 IRC 作业（声明里的 irc_log 只是兜底，供外部先跑好 IRC 的情形）
    irc_step = next((step for step in reversed(record.job_steps) if step.purpose == "irc"), None)
    irc_log = _refinement_log_path(record, irc_step) if irc_step else record.declaration.irc_log.strip()
    if not irc_log:
        return _terminal(
            record, "verdict", "candidate_only",
            f"frequency analysis supports a first-order saddle point ({imag[0]:.1f} cm^-1, exactly "
            "one imaginary mode), but no IRC was run: the two path directions were not checked to "
            "connect the declared minima. The candidate is a plausible saddle, NOT a verified one "
            "(submitting IRC needs the native %irc settings that live in the engine skill)",
        )
    if not os.path.isfile(irc_log):
        return _terminal(
            record, "verdict", "candidate_only",
            f"the declared IRC log does not exist at {irc_log}; the candidate stays unverified",
        )
    side_a, reason = _validated_endpoint_minimum(record, "reactant")
    if side_a is None:
        return _terminal(record, "verdict", "candidate_only", f"IRC side A minimum is unverified: {reason}")
    side_b, reason = _validated_endpoint_minimum(record, "product")
    if side_b is None:
        return _terminal(record, "verdict", "candidate_only", f"IRC side B minimum is unverified: {reason}")

    failures: list[str] = []
    for assignment, reactant, product in (
        ("direct", side_a, side_b), ("swapped", side_b, side_a),
    ):
        identity_errors = [
            _endpoint_identity_error(record, "reactant", reactant),
            _endpoint_identity_error(record, "product", product),
        ]
        if any(identity_errors):
            failures.append(f"{assignment} identity: {'; '.join(error for error in identity_errors if error)}")
            continue
        passed, detail = _irc_interval_proof(
            record, irc_log, freq_step, reactant, product, assignment,
        )
        if passed:
            return _terminal(
                record, "verdict", "verified",
                f"verified transition state: exactly one imaginary mode ({imag[0]:.1f} cm^-1), "
                f"usable IRC geometries from both directions, and {detail}; "
                f"optimized side-to-species assignment is {assignment}",
            )
        failures.append(f"{assignment} interval proof: {detail}")
    return _terminal(
        record, "verdict", "candidate_only",
        "The optimized IRC outer frames did not establish one consistent species identity, "
        "source provenance, and endpoint interval proof: " + "; ".join(failures)
        + ". The candidate stays UNVERIFIED",
    )


def _stop_at_unimplemented(record: TsProcessRecord, stage: TsStage) -> TsProcessRecord:
    """未接线的阶段：如实标 ``not_implemented`` 并阻塞，绝不假装跑过。"""
    why = _NOT_IMPLEMENTED_STAGES[stage]
    _record_stage(record, stage, "not_implemented", why)
    record.blocked = TsBlocked(
        failure_class="not_implemented", stage=stage, message=why, needs=[],
    )
    return record


#: 阶段顺序（有界推进沿这条线走）
STAGE_ORDER: tuple[TsStage, ...] = (
    "declare", "build", "map", "assemble", "guess", "validate", "submit", "refine", "verdict",
)
_STAGE_FUNCS: dict[str, Callable[[TsProcessRecord], TsProcessRecord]] = {
    "declare": _declare,
    "build": _build,
    "map": _map,
    "assemble": _assemble,
    "guess": _guess,
    "validate": _validate,
    "submit": _submit,
    "refine": _refine,
    "verdict": _verdict,
}


def advance(record: TsProcessRecord) -> TsProcessRecord:
    """从当前阶段沿顺序推进，直到阻塞、落终态，或撞上未接线的阶段。

    **有界**：``max_interventions`` 限制 agent 介入次数，耗尽即落终态（``search_failed``），
    不无限续；路径精修的轮数上限由 ``path_refinement_runs`` 声明，未声明时用 runner 默认。
    """
    if record.is_terminal:
        return record
    if record.intervention_count > record.declaration.budget.max_interventions:
        return _terminal(
            record, record.stage, "search_failed",
            f"the intervention budget ({record.declaration.budget.max_interventions}) is exhausted; "
            "stopping rather than looping. Search failure is NOT a claim that the reaction is "
            "impossible",
        )
    start = STAGE_ORDER.index(record.stage)
    for stage in STAGE_ORDER[start:]:
        if stage in _NOT_IMPLEMENTED_STAGES:
            return _stop_at_unimplemented(record, stage)
        record = _STAGE_FUNCS[stage](record)
        # 三种停下方式：终态、需要 agent 决策的阻塞、以及在等计算（waiting）。
        # 少了 waiting 这一条，循环会继续往下一阶段走——那就变成"作业还没算完就去判定"。
        if record.terminal is not None or record.blocked is not None or record.waiting_for:
            return record
    return record


# ---------------------------------------------------------------------------
# 公开入口（由 ts_prepare / ts_resume 两个工具包起来）
# ---------------------------------------------------------------------------


def start(request: TsStartRequest,
          event_sink: Optional[Callable[[str, dict], None]] = None) -> TsProcessRecord:
    """起一次 TS 搜索：建运行目录、落声明、沿阶段推进到阻塞/终态/未接线处。

    同步函数（CPU + 文件 IO）；异步调用方必须经 ``asyncio.to_thread`` 卸载。
    """
    run_id = _next_run_id(request.workspace_dir)
    run_dir = os.path.join(request.workspace_dir, TS_ROOT_NAME, run_id)
    os.makedirs(run_dir, exist_ok=False)
    _make_stage_dirs(run_dir)
    record = TsProcessRecord(
        run_id=run_id, run_dir=run_dir, workspace_dir=request.workspace_dir,
        owner_conversation_id=request.owner_conversation_id,
        owner_session_id=request.owner_session_id,
        declaration=request.declaration,
    )
    save_record(record)
    record = advance(record)
    save_record(record)
    if event_sink is not None:
        _emit(event_sink, record)
    return record


def resume(record: TsProcessRecord, adjustment: TsAdjustment,
           event_sink: Optional[Callable[[str, dict], None]] = None) -> TsProcessRecord:
    """在阻塞处带调整继续：**只接受局部覆盖**，不是重新声明整条反应。"""
    if record.is_terminal:
        raise ValueError(
            f"run {record.run_id} is terminal ({record.terminal}); a terminal run is not resumed"
        )
    declaration = record.declaration.model_copy(deep=True)
    scan_changed = adjustment.scan is not None and adjustment.scan != declaration.scan
    if scan_changed:
        if record.job_id is not None or record.job_steps or record.waiting_for:
            raise ValueError("scan cannot change with a pending job or after refinement submission")
        declaration.scan = adjustment.scan
    if adjustment.ring_order is not None:
        declaration.ring_order = list(adjustment.ring_order)
    if adjustment.distance_filters is not None:
        declaration.distance_filters = list(adjustment.distance_filters)
    if adjustment.reaction_center is not None:
        declaration.reaction_center = list(adjustment.reaction_center)
    if adjustment.atom_map is not None:
        declaration.atom_map = list(adjustment.atom_map)
    if adjustment.path_refinement_runs is not None:
        declaration.budget.path_refinement_runs = adjustment.path_refinement_runs
    if adjustment.max_interventions is not None:
        declaration.budget.max_interventions = adjustment.max_interventions
    guidance_changed = (
        declaration.ring_order != record.declaration.ring_order
        or declaration.distance_filters != record.declaration.distance_filters
    )
    geometry_changed = guidance_changed or (
        bool(declaration.ring_order)
        and declaration.reaction_center != record.declaration.reaction_center
    )
    if geometry_changed and (record.job_id is not None or record.job_steps or record.waiting_for):
        raise ValueError("guidance cannot change after refinement was submitted in this run")
    record.declaration = declaration
    # A compute notification calls resume with an empty adjustment. It advances
    # the persisted job sequence, but is not an agent intervention and must not
    # consume the finite budget (one wakeup per submitted job).
    compute_continuation = record.waiting_for and record.blocked is None and all(
        getattr(adjustment, field) is None
        for field in (
            "reaction_center", "ring_order", "distance_filters", "atom_map",
            "path_refinement_runs", "max_interventions", "scan",
        )
    ) and not adjustment.budget_override_note
    if not compute_continuation:
        record.intervention_count += 1
    record.blocked = None
    if geometry_changed:
        record.scan_step = None
        record.stage = "build"
        record.stage_records = [
            entry for entry in record.stage_records
            if STAGE_ORDER.index(entry.stage) < STAGE_ORDER.index("build")
        ]
        record.evidence_candidates = []
        record.guidance_attempt += 1
        record.active_attempt_dir = os.path.join(
            record.run_dir, BUILD_STAGE_DIR,
            f"guided_attempt_{record.guidance_attempt:04d}",
        )
        record.current_seed_xyz_path = ""
        record.current_seed_mol_path = ""
        record.current_reactant_prepared_path = ""
        record.current_ts_guess_path = ""
        record.guidance_manifest_path = ""
        record.effective_reaction_center = []
        record.path_kind = "not_attempted"
    if scan_changed:
        record.scan_step = None
        record.current_ts_guess_path = ""
        record.path_kind = "not_attempted"
        if not geometry_changed and STAGE_ORDER.index(record.stage) >= STAGE_ORDER.index("guess"):
            record.stage = "guess"
            record.stage_records = [entry for entry in record.stage_records
                                    if STAGE_ORDER.index(entry.stage) < STAGE_ORDER.index("guess")]
    # 回到阻塞发生的那个阶段重跑；校验是内部的，agent 不需要知道细节
    save_record(record)
    record = advance(record)
    save_record(record)
    if event_sink is not None:
        _emit(event_sink, record)
    return record


def _emit(event_sink: Callable[[str, dict], None], record: TsProcessRecord) -> None:
    """只推两类事件：**阻塞与终态**。阶段推进不推（避免污染上下文）。"""
    if record.terminal is not None:
        event_sink("ts.terminal", {
            "run_id": record.run_id,
            "terminal": record.terminal,
            "stage": record.stage,
            "evidence_candidates": record.evidence_candidates,
        })
    elif record.blocked is not None:
        event_sink("ts.blocked", {
            "run_id": record.run_id,
            "stage": record.blocked.stage,
            "failure_class": record.blocked.failure_class,
            "message": record.blocked.message,
            "atom_details": record.blocked.atom_details,
            "needs": record.blocked.needs,
        })


def evidence_binding_candidates(record: TsProcessRecord) -> list[str]:
    """可进证据集的产物：**只含小而有意义的文件**，逐迭代帧永远不在其中（SOP §7 第 2 条）。"""
    return [path for path in record.evidence_candidates if TRAJECTORY_DIR_NAME not in path]
