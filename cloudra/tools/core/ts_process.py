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
- **统一账本**：系统拥有的流水线使用既有 ComputeDB 阶段/作业事务；运行目录的
  ``process.json`` 是可读检查点，干预仍可通过 ``event_sink`` 记录。
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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.conformer_cards import AttemptEvidence
from cloudra.tools.core.geometry_inputs import atom_index_base
from cloudra.tools.core.geometry_optimization import OptimizationCheckpoint
from cloudra.tools.core.structure_builder import (
    BuildStrategy,
    PreparationRequest,
    StructureInput,
    prepare_structure,
)
from cloudra.tools.core.ts_inputs import TsCalculation, TsInput, TsResumeRequest

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
PathKind = Literal["", "xtb_path", "xtb_path_failed", "not_attempted", "scan", "provided"]

#: 尚未接线的阶段：停下来并如实说明，绝不假装跑过
#: 尚未接线的阶段（保留机制：新增阶段若还没实现，必须标 not_implemented 并停下，不假装跑过）
_NOT_IMPLEMENTED_STAGES: dict[str, str] = {}

#: 精修输入的文件名（放在 jobs/<job_dir>/ 下，与作业现场同处）
REFINEMENT_INPUT_NAMES = {"orca": "refine.inp", "gaussian": "refine.gjf"}
#: 精修作业的申请资源。保守默认，且**必须**与写进输入文件的 %pal/%nprocshared 一致——
#: 准入会核对"申请量不得低于输入自述"，不一致会被直接拒收（这正是该检查的用处）。







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
    source_input_revision: int = 1

class TsAttemptHistory(BaseModel):
    declaration_revision: int
    selected_candidate_id: str | None = None
    job_steps: list["TsJobStep"]
    stage_records: list[TsStageRecord]
    reason: str
    input: TsInput | None = None
    terminal: TsTerminal | None = None
    blocked: TsBlocked | None = None
    failed_attempt: dict | None = None


class TsProcessRecord(BaseModel):
    """持久运行记录（``ts/<run_id>/process.json``）。"""

    model_config = ConfigDict(extra='forbid')
    format_version: Literal[3] = 3
    run_id: str
    pipeline_id: str = ""
    declaration_revision: int = 1
    optimization_checkpoints: dict[str, OptimizationCheckpoint] = Field(default_factory=dict)
    budget_action_keys: dict[str, str] = Field(default_factory=dict)
    budget_reservations: dict[str, str] = Field(default_factory=dict)
    attempt_history: list[TsAttemptHistory] = Field(default_factory=list)
    catalog_id: str | None = None
    partition_revision: str | None = None
    candidate_attempts: list[AttemptEvidence] = Field(default_factory=list)
    cards_path: str = ""
    product_seed_candidate_id: str | None = None
    product_seed_xyz_path: str = ""
    product_seed_mol_path: str = ""
    selected_candidate_id: str | None = None
    run_dir: str
    workspace_dir: str = Field(default="", description="工作区根（证据快照的沙箱边界）")
    owner_conversation_id: str = Field(
        default="", description="发起项目的 conversation_id（compute_jobs 归属，随记录持久化）"
    )
    owner_session_id: Optional[str] = Field(
        default=None, description="发起 agent 的 session_id（作业终态推送收件人）"
    )
    input: TsInput
    input_binding: dict = Field(default_factory=dict)
    failed_attempt: dict | None = None
    method_checks: dict[str, dict] = Field(default_factory=dict)
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
    def compute_cpus(self):
        return self.input.execution.cpus

    @property
    def compute_memory_mb(self):
        return self.input.execution.memory_mb

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

    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1)
    input: TsInput
    workspace_dir: str = Field(description="工作区根目录；运行目录建在 <workspace_dir>/ts/<run_id>/")
    owner_conversation_id: str = Field(
        default="", description="发起项目的 conversation_id（计算作业归属；缺失时 submit 阶段拒收）"
    )
    owner_session_id: Optional[str] = Field(
        default=None, description="发起 agent 的 session_id（作业终态推送的收件人）"
    )

    @field_validator('request_key')
    @classmethod
    def stable_key(cls, value):
        if not value.strip():
            raise ValueError('nonblank request_key required for prepare replay')
        return value


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

def _write_immutable_input(path: str, content: str) -> None:
    """A bound engine input may be retried, never silently overwritten."""
    existing = Path(path)
    if existing.exists():
        if existing.read_bytes() != content.encode('utf-8'):
            raise ValueError('immutable stage input conflict')
        return
    atomic_write_text(path, content)

def save_record(record: TsProcessRecord) -> str:
    """落 ``process.json``；同时刷新 ``declare.json``（声明单独可读，便于人核对）。"""
    if record.pipeline_id:
        from cloudra.services.ts_pipeline_context import pipeline_database
        from cloudra.services.ts_pipeline_store import get_process, save_process_record
        if record.catalog_id and record.partition_revision:
            from cloudra.services.conformer_store import get_region_snapshot, list_candidates
            from cloudra.tools.core.conformer_cards import build_region_cards
            snapshot=get_region_snapshot(pipeline_database(),record.catalog_id,record.partition_revision,
                project_id=record.owner_conversation_id,owner_id=record.owner_session_id)
            members=list_candidates(pipeline_database(),record.catalog_id,project_id=record.owner_conversation_id,owner_id=record.owner_session_id)
            members=[c for c in members if c.candidate_id in snapshot.descriptors]
            cards=build_region_cards(snapshot,members,record.candidate_attempts)
            record.cards_path=str(Path(record.run_dir)/'candidate_cards.json')
            atomic_write_text(record.cards_path,json.dumps([c.model_dump() for c in cards],ensure_ascii=False))
        save_process_record(pipeline_database(), process_id=record.pipeline_id, record=record.model_dump(mode='json'))
        record.revision = get_process(pipeline_database(), record.pipeline_id)['revision']
    path = os.path.join(record.run_dir, PROCESS_JSON_NAME)
    atomic_write_text(path, record.model_dump_json(indent=2) + "\n")
    atomic_write_text(
        os.path.join(record.run_dir, DECLARE_JSON_NAME),
        record.input.model_dump_json(indent=2) + "\n",
    )
    return path

def load_record(workspace_dir: str, run_id: str) -> TsProcessRecord:
    path = os.path.join(workspace_dir, TS_ROOT_NAME, run_id, PROCESS_JSON_NAME)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format_version") != 3:
        raise ValueError("Unsupported TS input format; existing compute jobs remain intact.")
    return TsProcessRecord.model_validate(data)

def _record_stage(record: TsProcessRecord, stage: TsStage, status: StageStatus,
                  detail: str = "", artifacts: Optional[list[str]] = None) -> None:
    entry = TsStageRecord(stage=stage, status=status, detail=detail, artifacts=list(artifacts or []), source_input_revision=record.declaration_revision)
    record.stage_records = [r for r in record.stage_records if r.stage != stage] + [entry]
    record.stage = stage

def _block(record: TsProcessRecord, stage: TsStage, failure_class: str, message: str,
           atom_details: Optional[list[str]] = None,
           needs: Optional[list[str]] = None) -> TsProcessRecord:
    record.blocked = TsBlocked(
        failure_class=failure_class, stage=stage, message=message,
        atom_details=list(atom_details or []), needs=list(needs or []),
    )
    _record_stage(record, stage, "blocked", message)
    return record

def _record_candidate_failure(record, failure_class, step, evidence_path):
    record.failed_attempt = dict(attempt_id=f'{step.source_input_revision}:{step.purpose}:{step.job_id}',
        failure_class=failure_class, purpose=step.purpose, job_id=step.job_id,
        input_revision=step.source_input_revision, evidence_refs=[evidence_path])
    if not record.catalog_id or not record.selected_candidate_id:
        return
    from cloudra.tools.core.conformer_catalog import content_digest
    attempt=AttemptEvidence(candidate_id=record.selected_candidate_id,region_id='',stage=step.purpose,
        input_hash=content_digest(Path(step.input_path).read_bytes().hex()) if Path(step.input_path).is_file() else record.selected_candidate_id,
        failure_class=failure_class,job_id=step.job_id,evidence_refs=[evidence_path])
    if attempt not in record.candidate_attempts:
        record.candidate_attempts.append(attempt)

def _terminal(record: TsProcessRecord, stage: TsStage, terminal: TsTerminal,
              detail: str) -> TsProcessRecord:
    record.terminal = terminal
    record.blocked = None
    _record_stage(record, stage, "done", detail)
    return record

# ---------------------------------------------------------------------------
# 阶段实现
# ---------------------------------------------------------------------------

def stage_calculation(record: TsProcessRecord, purpose: str) -> TsCalculation | None:
    if purpose == 'ts_opt':
        return record.input.ts_optimization
    if purpose in ('frequency', 'irc'):
        return getattr(record.input.verification, purpose)
    if purpose in ('reactant_opt', 'product_opt', 'reactant_frequency', 'product_frequency'):
        side, task = purpose.split('_', 1)
        return getattr(getattr(record.input.verification, side + '_endpoint'), 'optimization' if task == 'opt' else task)
    if purpose == 'scan':
        guess = record.input.guess
        return guess.calculation if guess and guess.kind == 'scan' else None
    if purpose == 'path':
        guess = record.input.guess
        return TsCalculation(engine='xtb', method=guess.method, keywords='') if guess and guess.kind == 'xtb_path' else None
    if purpose in ('candidate_opt', 'candidate_evaluation', 'product_seed_opt'):
        source = getattr(record.input.conformers, 'product' if purpose == 'product_seed_opt' else 'reactant')
        return getattr(source, 'optimization', None)
    return None

def _calculation_field(purpose: str) -> str:
    if purpose == 'ts_opt':
        return 'ts_optimization'
    if purpose in ('frequency', 'irc'):
        return 'verification.' + purpose
    if purpose == 'scan':
        return 'guess.calculation'
    side, task = purpose.split('_', 1)
    return f'verification.{side}_endpoint.{"optimization" if task == "opt" else task}'

def _require_calculation(record, purpose, stage) -> bool:
    calculation = stage_calculation(record, purpose)
    if calculation is None:
        field = _calculation_field(purpose)
        _block(record, stage, 'missing_input', f'Explicit calculation required: {field}', needs=[field])
        return True
    if calculation.engine not in ('orca', 'gaussian'):
        _block(record, stage, 'unsupported_calculation', f'{purpose} does not support {calculation.engine}', needs=[_calculation_field(purpose)])
        return True
    return False

def _step_calculation(record, step) -> TsCalculation:
    if step.actual_calculation is None and step.source_input_revision != record.declaration_revision:
        raise ValueError(f"Calculation provenance missing for historical job {step.job_id}")
    value = step.actual_calculation or stage_calculation(record, step.purpose)
    if value is None:
        raise ValueError(f'Calculation provenance missing for job {step.job_id}')
    return value

def _rotated_product(record):
    source = record.input.conformers.product
    return source if source and source.kind == 'rotate_about_bond' else None

def _declare(record: TsProcessRecord) -> TsProcessRecord:
    declaration = record.input.reaction
    problems: list[str] = []
    if not declaration.reactant_smiles.strip():
        problems.append("reactant_smiles is empty")
    if not declaration.product_smiles.strip():
        problems.append("product_smiles is empty")
    if declaration.multiplicity < 1:
        problems.append(f"multiplicity must be >= 1 (2S+1), got {declaration.multiplicity}")
    from rdkit import Chem
    reactant_graph = Chem.MolFromSmiles(declaration.reactant_smiles)
    product_graph = Chem.MolFromSmiles(declaration.product_smiles)
    if reactant_graph is None or product_graph is None:
        problems.append('Reaction species must have parseable SMILES')
    if _rotated_product(record) is not None:
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
    _record_stage(record, "declare", "done", "reaction declared; each calculation requires its own method")
    return record

def _build(record: TsProcessRecord) -> TsProcessRecord:
    """建两端结构。多组分会被组装，因此这里要求 embed=True。"""
    record.stage = "build"
    declaration = record.input.reaction
    guidance = record.input.conformers.guidance
    out_dir = os.path.join(record.run_dir, BUILD_STAGE_DIR)
    if (guidance.ring_order or guidance.distance_filters) and not record.active_attempt_dir:
        record.guidance_attempt += 1
        record.active_attempt_dir = os.path.join(
            out_dir, f"guided_attempt_{record.guidance_attempt:04d}",
        )
    endpoints = [("reactant", declaration.reactant_smiles)]
    if _rotated_product(record) is None:
        endpoints.append(("product", declaration.product_smiles))
    # 第二端几何由声明派生（绕键旋转）时**不单独建**：那一端就是第一端的一个刚体旋转，
    # 另外建一个构象既浪费又可能被误当成"产物"（两端 SMILES 相同的题型必然踩这个坑）
    for role, smiles in endpoints:
        source = getattr(record.input.conformers, role)
        if source is None:
            return _block(record, 'build', 'missing_input', f'Explicit conformer source required for {role}', needs=[f'conformers.{role}'])
        if source.kind == 'file':
            try:
                from cloudra.tools.core.structure_artifacts import read_xyz_atoms
                path = Path(source.xyz_path).resolve()
                path.relative_to(Path(record.workspace_dir).resolve())
                atoms = read_xyz_atoms(str(path))
                target = Path(record.run_dir) / BUILD_STAGE_DIR / f'input_{record.declaration_revision:04d}' / role
                target.mkdir(parents=True, exist_ok=True)
                _write_immutable_input(str(target / 'seed.xyz'), path.read_text())
                mol_path = ''
                if source.mol_path:
                    mol = Path(source.mol_path).resolve()
                    mol.relative_to(Path(record.workspace_dir).resolve())
                    mol_path = str(target / 'seed.mol')
                    _write_immutable_input(mol_path, mol.read_text())
                if role == 'reactant':
                    record.current_seed_xyz_path = str(target / 'seed.xyz')
                    record.current_seed_mol_path = mol_path
                    metadata = dict(atom_identities=[dict(index=i, symbol=s) for i, (s, _) in enumerate(atoms)], components=[])
                    record.current_reactant_prepared_path = str(target / 'atom_table.json')
                    _write_immutable_input(record.current_reactant_prepared_path, json.dumps(metadata))
                else:
                    record.product_seed_xyz_path = str(target / 'seed.xyz')
                    record.product_seed_mol_path = mol_path
                record.evidence_candidates.append(str(target / 'seed.xyz'))
            except (ValueError, OSError) as exc:
                return _block(record, 'build', 'conformer_source_invalid', str(exc), needs=[f'conformers.{role}'])
            if source.optimization is not None:
                record = _optimize_conformer_source(record, role)
                if record.blocked or record.waiting_for:
                    return record
            continue
        if source.kind == 'catalog':
            from cloudra.tools.core.ts_candidate_pipeline import use_catalog_source
            record = use_catalog_source(record, source, role)
            if record.blocked:
                return record
            if source.optimization is not None:
                record = _optimize_conformer_source(record, role)
                if record.blocked or record.waiting_for:
                    return record
            continue
        if source.kind != 'generate':
            return _block(record, 'build', 'conformer_source_invalid', f'Unsupported {role} source {source.kind}', needs=[f'conformers.{role}'])
        if role == 'reactant' and (guidance.ring_order or guidance.distance_filters) and source.optimization is None:
            return _block(record, 'build', 'missing_input', 'Guided generation requires an explicitly declared conformer optimization calculation.', needs=['conformers.reactant.optimization'])
        target_dir = (
            os.path.join(record.active_attempt_dir, role)
            if record.active_attempt_dir else os.path.join(out_dir, f'input_{record.declaration_revision:04d}', role)
        )
        prepared = prepare_structure(PreparationRequest(
            structure=StructureInput(kind="smiles", value=smiles),
            output_dir=target_dir,
            total_charge=declaration.charge,
            multiplicity=declaration.multiplicity,
            random_seed=source.seed,
            strategy=BuildStrategy(
                name="per_component", embed=False, optimize=False,
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
                needs=["reaction.reaction_center"],
            )
        if prepared.components and prepared.status in ('ok', 'assembly_failed'):
            try:
                seed_path, mol_path = _bind_generated_seed(prepared, target_dir, source.seed)
            except (ValueError, OSError) as exc:
                return _block(record, 'build', 'conformer_generation_failed', str(exc), needs=[f'conformers.{role}'])
        else:
            return _block(
                record, "build", prepared.status,
                f"{role} ({smiles}) could not be built: {prepared.message}",
                atom_details=list(prepared.diagnostics),
                needs=[f"reaction.{role}_smiles"],
            )
        if role == "reactant":
            record.current_reactant_prepared_path = prepared.artifact_path
            record.current_seed_xyz_path, record.current_seed_mol_path = seed_path, mol_path
        else:
            record.product_seed_xyz_path, record.product_seed_mol_path = seed_path, mol_path
        record.evidence_candidates.extend([seed_path, mol_path, prepared.artifact_path])
        if source.optimization is not None:
            record = _optimize_conformer_source(record, role)
            if record.blocked or record.waiting_for:
                return record
    if guidance.ring_order or guidance.distance_filters:
        try:
            from cloudra.tools.core.preorganization import qualify_geometry
            plan, graph = _seed_guidance_plan(record)
            built = _read_built_xyz(record, 'reactant')
            passed, reasons, _ = qualify_geometry(plan, graph, built[0], built[1])
            if not passed:
                raise ValueError('; '.join(reasons))
            record.effective_reaction_center = list(dict.fromkeys([*record.input.reaction.reaction_center, *plan.forming_pairs]))
        except (ValueError, OSError) as exc:
            return _block(record, 'build', 'seed_guidance_failed', str(exc), needs=['conformers.reactant', 'conformers.guidance'])
    detail = "both endpoints built" if len(endpoints) == 2 else (
        "first endpoint built; the second endpoint is derived from it by the declared rotation"
    )
    _record_stage(record, "build", "done", detail, record.evidence_candidates)
    return record

def _bind_generated_seed(prepared, directory, seed):
    """Bind explicitly embedded components as a seed, without force-field work."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.tools.core.complex_assembly import (
        AssemblyParameters,
        combine_components,
        sample_independent_placements,
    )
    components = [Chem.MolFromMolFile(component.mol_path, removeHs=False) for component in prepared.components]
    if any(mol is None for mol in components):
        raise ValueError('Prepared component graph missing')
    for mol in components:
        mol.RemoveAllConformers()
        if mol.GetNumAtoms() == 1:
            mol.AddConformer(Chem.Conformer(1), assignId=True)
        else:
            parameters = AllChem.ETKDGv3()
            parameters.randomSeed = seed
            if AllChem.EmbedMolecule(mol, parameters) < 0:
                raise ValueError('Explicit ETKDGv3 generation failed; no replacement method was selected')
    graph = combine_components([(mol, -1) for mol in components])
    if len(components) > 1:
        groups, offset = [], 0
        for mol in components:
            groups.append(list(range(offset, offset + mol.GetNumAtoms())))
            offset += mol.GetNumAtoms()
        placement = sample_independent_placements(graph, groups, seed=seed, count=1, parameters=AssemblyParameters())[0]
        for index, point in enumerate(placement.positions):
            graph.GetConformer().SetAtomPosition(index, point)
    symbols = [atom.GetSymbol() for atom in graph.GetAtoms()]
    if symbols != prepared.symbols:
        raise ValueError('Generated seed changed the prepared atom identity order')
    xyz = '\n'.join([str(len(symbols)), 'ETKDGv3 seed; unoptimized',
        *[symbol + ' ' + ' '.join(repr(float(v)) for v in graph.GetConformer().GetAtomPosition(index))
          for index, symbol in enumerate(symbols)]]) + '\n'
    xyz_path, mol_path = str(Path(directory) / 'generated_seed.xyz'), str(Path(directory) / 'generated_seed.mol')
    _write_immutable_input(xyz_path, xyz)
    _write_immutable_input(mol_path, Chem.MolToMolBlock(graph))
    return xyz_path, mol_path

def _seed_guidance_plan(record):
    """Use existing qualification and ring fallback on the actual bound graph."""
    from rdkit import Chem

    from cloudra.tools.core.complex_assembly import AssemblyParameters
    from cloudra.tools.core.preorganization import DistanceWindow, GuidancePlan
    built = _read_built_xyz(record, 'reactant')
    if built is None or not built[3]:
        raise ValueError('Guidance requires the bound reactant MOL graph; supply conformers.reactant.mol_path')
    graph = Chem.MolFromMolFile(built[3], removeHs=False)
    if graph is None or [atom.GetSymbol() for atom in graph.GetAtoms()] != built[0]:
        raise ValueError('Guidance MOL graph does not match the bound XYZ atom order')
    guidance = record.input.conformers.guidance
    order = tuple(guidance.ring_order)
    if order and (len(order) < 3 or len(set(order)) != len(order)):
        raise ValueError('ring_order requires at least three distinct bound atoms')
    if any(not 0 <= atom < len(built[0]) for atom in order):
        raise ValueError('ring_order references an unbound atom')
    windows = {}
    for row in guidance.distance_filters:
        if any(not 0 <= atom < len(built[0]) for atom in row.atoms):
            raise ValueError('distance_filter references an unbound atom')
        pair = tuple(sorted(row.atoms))
        window = DistanceWindow(pair, row.min_ang, row.max_ang, 'explicit')
        if pair in windows and windows[pair] != window:
            raise ValueError('Conflicting distance windows for the same atom pair')
        windows[pair] = window
    forming, bonded = [], []
    fallback = AssemblyParameters().reaction_center_window
    for left, right in zip(order, order[1:] + order[:1]):
        pair = tuple(sorted((left, right)))
        if graph.GetBondBetweenAtoms(left, right):
            bonded.append(pair)
        else:
            forming.append(pair)
            windows.setdefault(pair, DistanceWindow(pair, *fallback, 'fallback'))
    if order and not forming:
        raise ValueError('ring_order is already a fully covalent cycle')
    return GuidancePlan(order, tuple(windows.values()), tuple(forming), tuple(bonded), 0), graph

def _optimize_conformer_source(record, role):
    """Optimize only the explicitly supplied side with its own calculation."""
    from cloudra.runtime.chem_task import ChemTask, read_task_result
    from cloudra.services.compute_store import TERMINAL_STATES
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema

    purpose = 'candidate_opt' if role == 'reactant' else 'product_seed_opt'
    calculation = stage_calculation(record, purpose)
    built = _read_built_xyz(record, role)
    if built is None:
        return _block(record, 'build', 'conformer_source_invalid', 'No conformer geometry to optimize', needs=[f'conformers.{role}'])
    try:
        _bound_input_structure(record, role)
    except (ValueError, OSError) as exc:
        return _block(record, 'build', 'input_identity_unconfirmed', str(exc), needs=[f'conformers.{role}'])
    step = next((s for s in record.job_steps if s.purpose == purpose), None)
    directory = Path(_job_directory(record, purpose))
    directory.mkdir(parents=True, exist_ok=True)
    guidance = record.input.conformers.guidance
    if role == 'reactant' and (guidance.ring_order or guidance.distance_filters):
        if calculation.engine != 'xtb' or calculation.method != 'GFN2-xTB' or calculation.keywords:
            return _block(record, 'build', 'unsupported_calculation', 'The existing constrained seed optimizer supports explicit GFN2-xTB with empty keywords. Supply an externally qualified seed for another calculation.', needs=['conformers.reactant.optimization'])
        from cloudra.tools.core.constrained_optimization import OptimizationRequest
        from cloudra.tools.core.geometry_optimization import advance_optimization
        plan, _ = _seed_guidance_plan(record)
        result = advance_optimization(record, 'reactant_guidance', OptimizationRequest(symbols=built[0], positions=built[1],
            method_fingerprint=calculation.method,
            distance_constraints=[dict(atoms=list(w.atoms), min_ang=w.min_ang, max_ang=w.max_ang) for w in plan.windows]))
        if result is None:
            return record
        xyz = '\n'.join([str(len(built[0])), 'Explicit constrained conformer optimization',
            *[symbol + ' ' + ' '.join(repr(v) for v in point) for symbol, point in zip(result['symbols'], result['positions'])]]) + '\n'
        target = str(directory / 'optimized_seed.xyz')
        _write_immutable_input(target, xyz)
        record.current_seed_xyz_path = target
        return record
    if step is None:
        if calculation.engine == 'xtb':
            if calculation.method != 'GFN2-xTB' or calculation.keywords:
                return _block(record, 'build', 'unsupported_calculation', 'Native seed optimization supports explicitly declared GFN2-xTB with empty keywords; use a prepared external seed for other native settings.', needs=[f'conformers.{role}.optimization'])
            manifest = directory / 'seed-opt.json'
            task = ChemTask(task='xtb_opt', reactant_xyz=Path(built[2]).read_text(),
                charge=record.input.reaction.charge, multiplicity=record.input.reaction.multiplicity, cpus=record.compute_cpus)
            _write_immutable_input(str(manifest), task.model_dump_json())
            job_type = 'chem_task'
        else:
            head, _, basis = calculation.method.partition('/')
            manifest = directory / ('seed-opt.inp' if calculation.engine == 'orca' else 'seed-opt.gjf')
            request = QmInputWriter_input_schema(engine=calculation.engine, source_type='xyz_file', source_value=built[2],
                method=head, basis_set=basis, task_type=[{'opt': None}], extra_keywords=calculation.keywords,
                orca_blocks=calculation.orca_blocks, end_setting=calculation.end_setting,
                nproc=record.compute_cpus, mem=f'{record.compute_memory_mb}MB',
                charge=record.input.reaction.charge, multiplicity=record.input.reaction.multiplicity)
            from cloudra.tools.core.calculation_intent import validate_writer_request
            conflicts = validate_writer_request(request.model_dump())
            if conflicts:
                return _block(record, 'build', 'conformer_input_invalid', str(conflicts), needs=[f'conformers.{role}.optimization'])
            content = QmInputWriter._build_orca_input(request, _xyz_coords(built[2])) if calculation.engine == 'orca' else QmInputWriter._build_gjf(request, _xyz_coords(built[2]))
            _write_immutable_input(str(manifest), content)
            job_type = calculation.engine
        error, job = _submit_step(record, purpose, str(manifest), job_type)
        if error:
            return _block(record, 'build', 'conformer_admission_failed', error, needs=[f'conformers.{role}.optimization'])
        step = TsJobStep(purpose=purpose, job_id=job, input_path=str(manifest), state='ready', actual_calculation=calculation, source_input_revision=record.declaration_revision)
        record.job_steps.append(step)
    step.state = _step_state(record, step)
    if step.state not in TERMINAL_STATES:
        record.waiting_for = f'job:{step.job_id}'
        return record
    record.waiting_for = ''
    if step.state != 'done':
        _record_candidate_failure(record, 'conformer_optimization_failed', step, _refinement_log_path(record, step))
        return _block(record, 'build', 'conformer_optimization_failed', f'{purpose} job {step.job_id} failed; recovery evidence required.', needs=[f'conformers.{role}'])
    if calculation.engine == 'xtb':
        data, _ = read_task_result(step.input_path)
        result = data['result']
        if not (result.get('normal_termination') is True and result.get('optimization_converged') is True):
            _record_candidate_failure(record, 'nonconvergence', step, step.input_path)
            return _block(record, 'build', 'conformer_optimization_failed', 'Seed optimization has no converged native evidence.', needs=[f'conformers.{role}'])
        xyz = Path(result['optimized_xyz']).read_text()
    else:
        xyz, error = _endpoint_opt_frame(record, step)
        if error:
            _record_candidate_failure(record, 'nonconvergence', step, _refinement_log_path(record, step))
            return _block(record, 'build', 'conformer_optimization_failed', error, needs=[f'conformers.{role}'])
    target = str(directory / 'optimized_seed.xyz')
    _write_immutable_input(target, xyz)
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    if [s for s, _ in read_xyz_atoms(target)] != built[0]:
        return _block(record, 'build', 'conformer_identity_mismatch', 'Optimized seed changed the atom order.', needs=[f'conformers.{role}'])
    if role == 'reactant':
        record.current_seed_xyz_path = target
    else:
        record.product_seed_xyz_path = target
    return record

def _active_reaction_center(record: TsProcessRecord) -> list[tuple[int, int]]:
    return (record.effective_reaction_center if (record.input.conformers.guidance.ring_order or record.input.conformers.guidance.distance_filters)
            else record.input.reaction.reaction_center)

def _read_built_xyz(record: TsProcessRecord, role: str):
    """读回某端已构建的几何，返回 ``(symbols, positions, xyz_path, mol_path)``；
    找不到返回 ``None``。

    多组分输入建出来的是**组装候选**（已按能量排序，取第一个）；单组分是 ``prepared.xyz``。
    """
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    if role=='product' and record.product_seed_xyz_path:
        if not Path(record.product_seed_xyz_path).is_file():
            return None
        atoms=read_xyz_atoms(record.product_seed_xyz_path)
        return ([s for s,_ in atoms],[p for _,p in atoms],record.product_seed_xyz_path,record.product_seed_mol_path)
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

    geometry = _rotated_product(record)
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
        base = 1
        lines.append(
            f"{role} atoms ({base}-based): "
            + ", ".join(f"{i}={s}" for i, s in enumerate(symbols, start=base))
        )
    return lines

def _bound_input_structure(record, role, *, require_identity=True, persist_artifact=True):
    """Check one concrete source before spending compute, retaining its graph."""
    import hashlib

    from rdkit import Chem

    from cloudra.tools.Chemtool.reaction_mapping import _identity_and_binding, _read_structure
    built = _read_built_xyz(record, role)
    if built is None:
        raise ValueError(f'{role} concrete geometry is missing')
    symbols, positions, xyz_path, mol_path = built
    hashes = {role + '_xyz': hashlib.sha256(Path(xyz_path).read_bytes()).hexdigest()}
    expected_smiles = getattr(record.input.reaction, role + '_smiles')
    mol = _read_structure(mol_path or xyz_path, None, 'mol' if mol_path else 'xyz', record.input.reaction.charge, role)
    if [a.GetSymbol() for a in mol.GetAtoms()] != symbols:
        raise ValueError(f'{role} MOL and XYZ atom orders differ')
    conf = Chem.Conformer(len(symbols))
    for i, point in enumerate(positions):
        conf.SetAtomPosition(i, point)
    mol.RemoveAllConformers()
    mol.AddConformer(conf)
    connectivity = _geometry_connectivity_error(mol, (symbols, positions), record.input.reaction.charge, role)
    if connectivity:
        raise ValueError(connectivity)
    source = getattr(record.input.conformers, role)
    constructed_role = 'reactant' if source and source.kind == 'rotate_about_bond' else role
    original_source = getattr(record.input.conformers, constructed_role)
    if original_source and original_source.kind == 'generate':
        metadata_path = record.current_reactant_prepared_path if constructed_role == 'reactant' else str(Path(mol_path).parent / 'prepared_structure.json')
        identities = json.loads(Path(metadata_path).read_text())['atom_identities']
        expected = Chem.MolFromSmiles(expected_smiles)
        for atom in expected.GetAtoms():
            if atom.GetAtomicNum() != 1:
                atom.SetAtomMapNum(atom.GetIdx() + 1)
        for identity in identities:
            if identity['symbol'] != 'H' and identity['origin'] == 'input_atom':
                mol.GetAtomWithIdx(identity['index']).SetAtomMapNum(identity['input_atom_index'] + 1)
        expected_smiles = Chem.MolToSmiles(expected, canonical=False)
        hashes[role + '_construction'] = hashlib.sha256(Path(metadata_path).read_bytes()).hexdigest()
    identity, binding, diagnostic = _identity_and_binding(expected_smiles, mol)
    if require_identity and (identity != 'match' or (any(a.GetAtomicNum() != 1 for a in mol.GetAtoms()) and not binding)):
        raise ValueError(f'{role}: {diagnostic or identity}')
    from cloudra.tools.core.preorganization import geometry_stereochemistry_errors
    stereo = geometry_stereochemistry_errors(mol, positions)
    if require_identity and stereo:
        raise ValueError(f'{role}: {stereo}')
    if not mol_path and not persist_artifact:
        return expected_smiles, mol, hashes
    if not mol_path:
        mol_path = str(Path(xyz_path).with_suffix('.bound.mol'))
        _write_immutable_input(mol_path, Chem.MolToMolBlock(mol))
        if role == 'reactant':
            record.current_seed_mol_path = mol_path
        else:
            record.product_seed_mol_path = mol_path
    hashes[role + '_mol'] = hashlib.sha256(Path(mol_path).read_bytes()).hexdigest()
    return expected_smiles, mol, hashes

def _check_input_binding(record: TsProcessRecord) -> dict:
    from rdkit import Chem

    from cloudra.tools.Chemtool.reaction_mapping import ReactionMapping_input_schema, check_concrete_binding
    request = dict(reactant_charge=record.input.reaction.charge, product_charge=record.input.reaction.charge)
    hashes = {}
    for role in ('reactant', 'product'):
        expected, mol, artifacts = _bound_input_structure(record, role, require_identity=False)
        request.update({role + '_smiles': expected, role + '_text': Chem.MolToMolBlock(mol), role + '_format': 'mol'})
        hashes.update(artifacts)
    result = check_concrete_binding(ReactionMapping_input_schema(**request),
        dict(atom_map=list(range(1, mol.GetNumAtoms() + 1)) if _rotated_product(record) else [i + 1 for i in record.input.reaction.atom_map], watch_pairs=[]))
    return dict(input_revision=record.declaration_revision, hashes=hashes, **result)

def _validate_input_binding(record: TsProcessRecord) -> TsProcessRecord:
    try:
        record.input_binding = _check_input_binding(record)
    except (ValueError, OSError) as exc:
        record.input_binding = dict(input_revision=record.declaration_revision, binding_status="inconclusive", binding_diagnostics=[str(exc)])
    if record.input_binding["binding_status"] != "complete":
        return _block(record, "map", "input_identity_unconfirmed", "; ".join(record.input_binding.get("binding_diagnostics", [])) or "Concrete endpoint identity or atom binding is inconclusive.", needs=["reaction", "conformers"])
    return record

def _map(record: TsProcessRecord) -> TsProcessRecord:
    """原子映射：校验声明的映射能把产物重排到**与反应物同一原子序列**。

    这一步是必需的，不是形式：构建器按连通分量拼装两端，两端的原子顺序**本来就不一样**
    （实测 ``[F-].CCl`` → ``[F,C,Cl,H,H,H]``，``CF.[Cl-]`` → ``[C,F,H,H,H,Cl]``），而
    路径搜索要求两端是同一套、同序的原子。歧义与错映射必须**点名到原子**地报出来。
    """
    declaration = record.input.reaction
    base = 1
    geometry = _rotated_product(record)
    if geometry is not None:
        # 第二端几何由第一端绕键旋转而来 -> 原子对应关系是**恒等**（构造保证），不需要 atom_map
        built = _read_built_xyz(record, "reactant")
        if built is None:
            return _block(
                record, "map", "missing_built_geometry",
                "the first endpoint has no built geometry, so the declared rotation cannot be "
                "applied",
                needs=["reaction.reactant_smiles"],
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
        directory = Path(record.run_dir) / BUILD_STAGE_DIR / f"input_{record.declaration_revision:04d}" / "product"
        directory.mkdir(parents=True, exist_ok=True)
        xyz = "\n".join([str(len(built[0])), "Declared bond rotation",
            *[symbol + " " + " ".join(repr(float(v)) for v in point) for symbol, point in zip(built[0], positions)]]) + "\n"
        record.product_seed_xyz_path = str(directory / "rotated_seed.xyz")
        _write_immutable_input(record.product_seed_xyz_path, xyz)
        record.product_seed_mol_path = built[3]
        _validate_input_binding(record)
        if record.blocked:
            return record
        _record_stage(
            record, "map", "done",
            "the second endpoint is the first endpoint rotated about the declared bond "
            f"({geometry.atoms}, {geometry.degrees} deg), so "
            "the atom correspondence is the identity by construction; no atom_map is needed",
        )
        return record
    if not declaration.atom_map:
        return _block(
            record, "map", "atom_map_missing",
            "no atom_map was declared: the reactant→product atom correspondence is ambiguous, and "
            "an ambiguous mapping must be declared rather than guessed (a wrong mapping produces a "
            "non-physical path no matter how good the path search is). To fix: declare the FULL "
            "1-based structure map, in product atom order for every engine, "
            "covering EVERY atom including hydrogens (a heavy-atom-only map is rejected). Atom "
            "numbers refer to the built endpoint XYZs listed in atom_details (component-wise "
            "assembly order, NOT raw SMILES order): read them, or call reaction_mapping on the "
            "built structures for a draft and verify it element-wise before ts_resume.",
            atom_details=_endpoint_numbering(record),
            needs=["reaction.atom_map"],
        )

    reactant = _read_built_xyz(record, "reactant")
    product = _read_built_xyz(record, "product")
    if reactant is None or product is None:
        return _block(
            record, "map", "missing_built_geometry",
            "the built endpoint geometries are missing from the run directory, so the atom map "
            "could not be checked",
            needs=["reaction.reactant_smiles", "reaction.product_smiles"],
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
            needs=["reaction.reactant_smiles", "reaction.product_smiles"],
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
            needs=["reaction.atom_map"],
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
            needs=["reaction.atom_map"],
        )
    _validate_input_binding(record)
    if record.blocked:
        return record
    _record_stage(record, "map", "done", f"{n} atoms mapped; concrete endpoint identities bound to input revision {record.declaration_revision}")
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
            needs=["reaction.reactant_smiles"],
        )
    atom_count = len(identities)
    invalid_pairs = [
        (left, right) for left, right in active_center
        if not (0 <= left < atom_count and 0 <= right < atom_count) or left == right
    ]
    if invalid_pairs and _rotated_product(record) is None:
        base = 1
        invalid_pairs = [(left + base, right + base) for left, right in invalid_pairs]
        numbering = ", ".join(f"{atom['index'] + base}={atom['symbol']}" for atom in identities)
        return _block(
            record, "assemble", "invalid_reaction_center",
            f"reaction_center pair(s) {invalid_pairs} are invalid for the built reactant with "
            f"{atom_count} atoms. Use {base}-based indices {base}..{atom_count - 1 + base} in the full output "
            "atom order, including hydrogens; each pair must name two different atoms.",
            atom_details=[f"reactant atoms ({base}-based): {numbering}"],
            needs=["reaction.reaction_center"],
        )
    if components <= 1 and _rotated_product(record) is not None:
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
            needs=["reaction.reaction_center"],
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

    declaration = record.input.reaction
    plan = record.input.guess
    calculation = plan.calculation
    if _require_calculation(record, 'scan', 'guess'):
        return record
    if record.scan_step is None:
        built = _read_built_xyz(record, "reactant")
        if built is None:
            return _block(record, "guess", "missing_built_geometry", "Reactant geometry missing", needs=["reaction.reactant_smiles"])
        root = Path(record.run_dir) / PATH_STAGE_DIR
        root.mkdir(parents=True, exist_ok=True)
        folder = Path(_job_directory(record, 'scan'))
        folder.mkdir(parents=True, exist_ok=True)
        base = atom_index_base(calculation.engine)
        def public_rows(rows):
            return [dict(row.model_dump(), atoms=[i + base for i in row.atoms]) for row in rows]
        request = TsGuess_input_schema(
            mode="scan_prepare", input_path=built[2], engine=calculation.engine,
            method=calculation.method, charge=declaration.charge, spin=declaration.multiplicity,
            extra_route=calculation.keywords, orca_blocks=calculation.orca_blocks,
            end_setting=calculation.end_setting,
            scans=public_rows(plan.scans), freeze=public_rows(plan.freeze),
            output_path=str(folder / ("scan.inp" if calculation.engine == "orca" else "scan.gjf")),
            nprocs=record.compute_cpus,
        )
        try:
            prepared = TsGuess()._scan_prepare(request)
        except ValueError as exc:
            return _block(record, "guess", "invalid_scan", str(exc), needs=["guess"])
        if not prepared.is_success:
            return _block(record, "guess", "invalid_scan", prepared.message, needs=["guess"])
        error, job_id = _submit_step(record, "scan", prepared.input_file_path, calculation.engine)
        if error:
            return _block(record, "guess", "compute_admission_rejected", error, needs=["guess"])
        record.scan_step = TsJobStep(purpose="scan", job_id=job_id, input_path=prepared.input_file_path, state="ready", actual_calculation=calculation, source_input_revision=record.declaration_revision)
        record.waiting_for = f"job:{job_id}"
        _record_stage(record, "guess", "waiting", f"Scan job {job_id} submitted; compute completion advances the system driver.", [prepared.input_file_path])
        return record
    step = record.scan_step
    step.state = _step_state(record, step)
    if step.state not in TERMINAL_STATES and step.state != "missing":
        record.waiting_for = f"job:{step.job_id}"
        return record
    record.waiting_for = ""
    if step.state != "done":
        _record_candidate_failure(record, "scan_job_failed", step, _refinement_log_path(record, step))
        return _block(record, "guess", "scan_job_failed", f"Scan job {step.job_id}: {step.state}", needs=["guess"])
    target = str(Path(step.input_path).parent / "scan_peak.xyz")
    try:
        parsed = TsGuess()._scan_parse(TsGuess_input_schema(
            mode="scan_parse", engine=_step_calculation(record, step).engine,
            log_path=_refinement_log_path(record, step), ts_candidate_path=target,
        ))
    except (ValueError, OSError) as exc:
        _record_candidate_failure(record, "scan_parse_failed", step, _refinement_log_path(record, step))
        return _block(record, "guess", "scan_parse_failed", str(exc), needs=["guess"])
    if (not parsed.is_success or parsed.scan_has_internal_peak is not True
            or parsed.candidate_unavailable or not parsed.ts_candidate_path
            or not Path(parsed.ts_candidate_path).is_file()):
        _record_candidate_failure(record, "scan_no_candidate", step, _refinement_log_path(record, step))
        return _block(record, "guess", "scan_no_candidate",
                      "Scan produced no usable internal-peak geometry. " + parsed.message,
                      atom_details=parsed.verdicts, needs=["guess"])
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    try:
        candidate_atoms = read_xyz_atoms(parsed.ts_candidate_path)
        built = _read_built_xyz(record, "reactant")
        if built is None or [symbol for symbol, _ in candidate_atoms] != built[0]:
            raise ValueError("Scan peak atom identity/order differs from the assembled reactant")
        if not all(math.isfinite(value) for _, position in candidate_atoms for value in position):
            raise ValueError("Scan peak has nonfinite coordinates")
    except (ValueError, OSError) as exc:
        _record_candidate_failure(record, "scan_invalid_geometry", step, _refinement_log_path(record, step))
        return _block(record, "guess", "scan_invalid_geometry", str(exc), needs=["guess"])
    record.current_ts_guess_path = parsed.ts_candidate_path
    record.path_kind = "scan"
    record.evidence_candidates.extend([_refinement_log_path(record, step), parsed.ts_candidate_path])
    _record_stage(record, "guess", "done", "Scan internal peak extracted; unconstrained refinement still required.", [parsed.ts_candidate_path])
    return record

def _queued_path(record: TsProcessRecord, reactant_xyz: str, product_xyz: str):
    from cloudra.runtime.chem_task import ChemTask, read_task_result
    from cloudra.services.compute_store import TERMINAL_STATES
    from cloudra.tools.core.xtb_path_runner import XtbPathResult
    step = next((step for step in record.job_steps if step.purpose == 'path'), None)
    if step is None:
        directory = _job_directory(record, 'path')
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, 'path-task.json')
        task = ChemTask(task='xtb_path',reactant_xyz=reactant_xyz,product_xyz=product_xyz,
            charge=record.input.reaction.charge,multiplicity=record.input.reaction.multiplicity,cpus=record.compute_cpus,
            solvation=record.input.guess.solvation.model_dump() if record.input.guess.solvation else None,
            refinement_runs=record.input.guess.refinement_runs)
        _write_immutable_input(path,task.model_dump_json())
        error,job = _submit_step(record, 'path', path, 'chem_task')
        if error:
            return None,_block(record,'guess','path_admission_failed',error,needs=['execution.compute_node','execution.limits'])
        step = TsJobStep(purpose='path',job_id=job,input_path=path,state='ready', actual_calculation=stage_calculation(record, 'path'), source_input_revision=record.declaration_revision)
        record.job_steps.append(step)
        record.waiting_for=f'job:{job}'
        return None,record
    step.state=_read_job_state(record,step.job_id)
    if step.state not in TERMINAL_STATES:
        record.waiting_for=f'job:{step.job_id}'
        return None,record
    try:
        data,_=read_task_result(step.input_path)
        return XtbPathResult.model_validate(data['result']),record
    except (OSError,ValueError,KeyError) as exc:
        return None,_block(record,'guess','path_result_missing',str(exc),needs=['compute_artifacts'])

def _guess(record: TsProcessRecord) -> TsProcessRecord:
    """路径初猜：**先把产物按 atom_map 重排到与反应物同序**，再跑 xTB MTD 路径。

    重排是必须的：路径搜索要求两端是同一套、同序的原子，而两端是各自按连通分量拼装的
    （实测元素序列不同）。重排后的产物几何落在 ``path/product_reordered.xyz``，可复查。
    Scientific search choices are explicit; failure never switches methods.
    """
    record.stage = "guess"
    if record.input_binding:
        _validate_input_binding(record)
        if record.blocked:
            return record
    guess = record.input.guess
    if guess is None:
        return _block(record, 'guess', 'missing_input', 'Explicit guess source required', needs=['guess'])
    if guess.kind == 'provided':
        try:
            import math

            from cloudra.tools.core.structure_artifacts import read_xyz_atoms
            candidate = Path(guess.xyz_path).resolve()
            candidate.relative_to(Path(record.workspace_dir).resolve())
            atoms = read_xyz_atoms(str(candidate))
            reactant = _read_built_xyz(record, 'reactant')
            if reactant is None or [s for s, _ in atoms] != reactant[0]:
                raise ValueError('Provided candidate atom identity/order differs from the bound reactant')
            if not all(math.isfinite(v) for _, point in atoms for v in point):
                raise ValueError('Provided candidate contains nonfinite coordinates')
            for reference in guess.evidence_refs:
                artifact = Path(reference).resolve()
                artifact.relative_to(Path(record.workspace_dir).resolve())
                if not artifact.is_file():
                    raise ValueError(f'Provided candidate provenance artifact missing: {reference}')
        except (OSError, ValueError) as exc:
            return _block(record, 'guess', 'provided_guess_invalid', str(exc), needs=['guess'])
        target = Path(record.run_dir) / PATH_STAGE_DIR / f'input_{record.declaration_revision:04d}'
        target.mkdir(parents=True, exist_ok=True)
        bound_candidate = target / 'provided.xyz'
        try:
            _write_immutable_input(str(bound_candidate), candidate.read_text())
            bound_refs = []
            for index, reference in enumerate(guess.evidence_refs):
                artifact = target / f'provenance_{index:04d}{Path(reference).suffix}'
                _write_immutable_input(str(artifact), Path(reference).read_text())
                bound_refs.append(str(artifact))
        except (OSError, ValueError) as exc:
            return _block(record, 'guess', 'provided_guess_invalid', str(exc), needs=['guess'])
        record.current_ts_guess_path = str(bound_candidate)
        record.path_kind = 'provided'
        _record_stage(record, 'guess', 'done', 'Provided candidate bound; formal optimization and verification remain required.', [str(bound_candidate), *bound_refs])
        return record
    if guess.kind == 'scan':
        return _guess_scan(record)
    if guess.method != 'GFN2-xTB':
        return _block(record, 'guess', 'unsupported_calculation', 'The current xTB path runner implements GFN2-xTB only; declare a supported method explicitly.', needs=['guess.method'])

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
            needs=["reaction.reactant_smiles"],
        )
    r_symbols, r_pos = reactant[0], reactant[1]
    if _rotated_product(record) is not None:
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
                needs=["reaction.product_smiles"],
            )
        p_pos = product[1]
        atom_map = record.input.reaction.atom_map
        if len(atom_map) != len(r_symbols):
            return _block(
                record, "guess", "atom_map_length_mismatch",
                f"atom_map has {len(atom_map)} entries for {len(r_symbols)} atoms",
                needs=["reaction.atom_map"],
            )
        # 产物第 k 个原子 → 反应物第 atom_map[k]-1 个位置
        reordered = [None] * len(r_symbols)
        for product_index, target in enumerate(atom_map):
            reordered[target] = list(p_pos[product_index])
        if any(position is None for position in reordered):
            return _block(
                record, "guess", "atom_map_not_a_permutation",
                "the atom_map does not cover every reordered position; reordering would leave holes",
                needs=["reaction.atom_map"],
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
        charge=record.input.reaction.charge,
        multiplicity=record.input.reaction.multiplicity,
        run_label="guess",
        extra_args=(
            [f"--{guess.solvation.model}", guess.solvation.solvent]
            if guess.solvation else []
        ),
    )
    # 声明给了上限就用它（GH #39：撞上限的截断路径不是初猜，抬高上限重跑才是出路）；
    # 0 = 未声明，交给 runner 默认值。
    if guess.refinement_runs is not None:
        request.refinement_runs = guess.refinement_runs
    if record.pipeline_id:
        run, record = _queued_path(record, reactant_xyz, product_xyz)
        if run is None:
            return record
    else:
        run = run_xtb_path(request)
    if run.termination_reason == "executable_missing":
        return _block(record, 'guess', 'executable_missing', 'The declared xTB path engine is unavailable; repair the environment or revise guess explicitly.', needs=['guess'])
    if not run.usable_as_guess:
        path_step = next((step for step in reversed(record.job_steps) if step.purpose == 'path'), None)
        if path_step:
            evidence = run.stdout_path or path_step.input_path
            failure = 'path_failed' if run.termination_reason in XTB_ENGINE_STARTED_TERMINATIONS else 'unclassified_failure'
            _record_candidate_failure(record, failure, path_step, evidence)
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
            needs=["guess", "reaction.reaction_center", "reaction.atom_map", "reaction.reactant_smiles", "reaction.product_smiles"],
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
    if record.path_kind in ("xtb_path", "scan", "provided") and (record.current_ts_guess_path or run_dirs):
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
            base = 1
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
                    needs=["reaction.reaction_center", "reaction.atom_map"],
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

    declaration = record.input.reaction
    calculation = stage_calculation(record, 'ts_opt')
    if calculation is None:
        return 'Explicit ts_optimization calculation required', ''
    method = calculation.method.strip()
    if "/" in method:
        head, _sep, basis = method.partition("/")
        method_name, basis_name = head.strip(), basis.strip()
    else:
        method_name, basis_name = method, ""
    if not method_name:
        return f"method {calculation.method!r} has no method part before '/'", ""

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

    input_name = REFINEMENT_INPUT_NAMES[calculation.engine]
    input_path = os.path.join(job_dir, input_name)
    # 引擎各自的原生 TS 写法由项目的 skill 规定（references/orca-inputs.md /
    # gaussian-inputs.md）。ORCA 用 `! OptTS`，初始 Hessian 走原生 %geom 块；
    # **频率是后续独立作业**（skill 的"Frequency and IRC follow-ups"），因此这里只写 TS 优化，
    # 频率/IRC 归 refine 阶段。若 skill 里的配方变了，改这里一处即可。
    if calculation.engine == "orca":
        task_type: list[dict] = [{"opt": "ts"}]
        orca_blocks: Optional[str] = "%geom\n  Calc_Hess true\nend"
    else:
        task_type = [{"opt": "TS,calcfc,noeigen"}]
        orca_blocks = None
    request = QmInputWriter_input_schema(
        nproc=record.compute_cpus,
        mem=f"{record.compute_memory_mb}MB",
        engine=calculation.engine,
        source_type="xyz_file",
        source_value=source,
        method=method_name,
        basis_set=basis_name,
        task_type=task_type,
        extra_keywords=calculation.keywords,
        orca_blocks='\n'.join(filter(None, [orca_blocks, calculation.orca_blocks])) or None,
        frequency_mode=calculation.frequency_mode,
        end_setting=calculation.end_setting,
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
        if calculation.engine == "orca"
        else QmInputWriter._build_gjf(request, coords)
    )
    # 不信 writer 自述：从生成文本重新 inspect，任务集合不一致即失败（同一份纪律）
    inspected = inspect_input(content, engine=calculation.engine)
    requested = intent_from_writer(request.model_dump())
    if inspected.tasks != requested.tasks:
        return (
            "refinement input internal mismatch: the generated file encodes tasks "
            f"{sorted(inspected.tasks)} but {sorted(requested.tasks)} were requested",
            "",
        )
    _write_immutable_input(input_path, content)
    return "", input_path

def _job_directory(record: TsProcessRecord, purpose: str) -> str:
    if record.pipeline_id:
        return os.path.join(record.run_dir, JOBS_STAGE_DIR, f'declaration_{record.declaration_revision:04d}', purpose)
    return os.path.join(record.run_dir, JOBS_STAGE_DIR, f'job_{len(record.job_steps) + 1:04d}')

def _submit(record: TsProcessRecord) -> TsProcessRecord:
    """提交精修作业：写输入 → **复用**唯一一份准入校验 → 入库为 ready。

    入库用**同步** ``insert_compute_job``：本进程整体跑在工具的工作线程里（不是事件循环
    线程），项目的同步 SQLite 纪律允许在工作线程使用。关键是准入判断与
    ``submit_compute_job`` 共用 ``services/compute_admission.admit_job``——**没有第二套**，
    否则同一份作业会在两条入口下得出不同的准入结论。
    """
    if record.input_binding:
        _validate_input_binding(record)
        if record.blocked:
            return record
    if _require_calculation(record, 'ts_opt', 'submit'):
        return record
    calculation = stage_calculation(record, 'ts_opt')
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
    job_dir = _job_directory(record, "ts_opt")
    os.makedirs(job_dir, exist_ok=True)

    error, input_path = _write_refinement_input(record, job_dir)
    if error:
        return _block(
            record, "submit", "refinement_input_failed", error, needs=["method", "engine"]
        )

    # 精修是重活：资源按声明申请；方法与基组已写进输入，准入据此核对输入自述需求。
    # 准入 + 入库收在 _submit_step（与 refine 的频率作业走同一条路径，只有一份）。
    job_type = calculation.engine
    error, job_id = _submit_step(record, "ts_opt", input_path, job_type)
    if error:
        return _block(
            record, "submit", "compute_admission_rejected", error,
            needs=["method", "engine", "budget"],
        )
    record.job_id = int(job_id)
    record.job_input_path = input_path
    record.job_steps.append(TsJobStep(
        purpose="ts_opt", job_id=job_id, input_path=input_path, state="ready",
        actual_calculation=calculation, source_input_revision=record.declaration_revision,
    ))
    _record_stage(
        record, "submit", "done",
        f"refinement job {job_id} submitted as 'ready' ({job_type}, {calculation.method}); the "
        "scheduler daemon claims it and its terminal state arrives through the existing compute "
        "notification path",
        [input_path],
    )
    return record

class TsJobStep(BaseModel):
    """精修作业序列里的一步（TS、IRC 与两端极小值验证）。"""

    purpose: Literal[
        "sampling", "path", "candidate_opt", "candidate_evaluation", "product_seed_opt", "scan", "ts_opt", "frequency", "irc", "reactant_opt", "reactant_frequency",
        "product_opt", "product_frequency",
    ]
    job_id: Optional[int] = None
    input_path: str = ""
    state: str = Field(default="", description="compute_jobs 里的状态；终态见 TERMINAL_STATES")
    actual_calculation: TsCalculation | None = None
    source_input_revision: int = 1
    method_contract: dict | None = None
    stage_key: str | None = None
    external_source: dict | None = None

def _read_job_state(record: TsProcessRecord, job_id: Optional[int]) -> str:
    """读作业当前状态；读不到返回 ``"missing"``（不猜成成功）。"""
    if job_id is None:
        return "missing"
    from cloudra.services.ts_pipeline_context import pipeline_database

    db = pipeline_database().init()
    with db.connect() as con:
        row = con.execute("SELECT state FROM compute_jobs WHERE id = ?", (job_id,)).fetchone()
    return str(row[0]) if row else "missing"

def _step_state(record, step):
    if step.external_source:
        import hashlib
        for path, digest in step.external_source['artifact_hashes'].items():
            if not Path(path).is_file() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
                return 'missing'
        return 'done'
    return _read_job_state(record, step.job_id)

def _reuse_existing_irc(record):
    """Reuse a registered, immutable native IRC; never infer success from a path."""
    import hashlib

    from cloudra.infra.compute_utils import resolve_log_path
    from cloudra.services.ts_pipeline_context import pipeline_database
    from cloudra.services.ts_pipeline_store import verify_stage_input
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
    from cloudra.tools.core import gaussian_frames, orca_frames
    from cloudra.tools.core.calculation_intent import inspect_input, native_input_geometry
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    source_log = Path(record.input.verification.irc_log).resolve()
    source_log.relative_to(Path(record.workspace_dir).resolve())
    db = pipeline_database()
    with db.connect() as con:
        jobs = con.execute("SELECT id,path,jobtype FROM compute_jobs WHERE conversation_id=? AND state='done'", (record.owner_conversation_id,)).fetchall()
    source = next(((job, Path(path).resolve(), engine) for job, path, engine in jobs
        if Path(resolve_log_path(path, job_type=engine, task_id=job)).resolve() == source_log), None)
    if source is None:
        raise ValueError('Existing IRC needs an authoritative same-project completed job with a bound native input')
    job, source_input, engine = source
    source_input.relative_to(Path(record.workspace_dir).resolve())
    if verify_stage_input(db, job) is None:
        raise ValueError('Existing IRC lacks an authoritative immutable input digest; source provenance is incomplete')
    text = source_input.read_text()
    if inspect_input(text, engine=engine).tasks != {'irc'}:
        raise ValueError('The existing source input does not exclusively request IRC')
    _check_calculation_submission(record, 'irc', str(source_input), engine)
    log_text = source_log.read_text(errors='replace')
    parser = orca_frames if engine == 'orca' else gaussian_frames
    if not parser.normal_termination(log_text):
        raise ValueError('Existing IRC lacks native normal termination')
    frequency = next((s for s in reversed(record.job_steps) if s.purpose == 'frequency'), None)
    if frequency is None:
        raise ValueError('Existing IRC requires the accepted TS frequency geometry')
    geometry = Path(frequency.input_path).parent / 'optimized.xyz'
    # Native writers submit eight decimal places. Compare those exact rendered
    # coordinates, using their existing precision rather than a new tolerance.
    def canonical(atoms):
        return [(s, tuple(f'{float(v):.8f}' for v in point)) for s, point in atoms]
    if canonical(native_input_geometry(text, engine=engine)) != canonical(read_xyz_atoms(str(geometry))):
        raise ValueError('Existing IRC input geometry differs from the accepted TS frequency frame')
    checks = []
    info = TsGuess._extract_irc_endpoints(TsGuess_input_schema(mode='verify', irc_log=str(source_log), engine=engine,
        output_dir=str(Path(_job_directory(record, 'irc')) / 'source_endpoints')), checks, require_two_sides=True)
    if info is None or not all(info.get(key) and Path(info[key]).is_file() for key in ('path_a', 'path_b')):
        raise ValueError('Existing IRC has no usable two-sided endpoint evidence: ' + '; '.join(checks))
    directory = Path(_job_directory(record, 'irc'))
    directory.mkdir(parents=True, exist_ok=True)
    native_path = str(directory / ('existing.inp' if engine == 'orca' else 'existing.gjf'))
    log_path = str(directory / 'existing.log')
    _write_immutable_input(native_path, text)
    _write_immutable_input(log_path, source_log.read_text())
    facts = dict(source_job_id=job, source_input=str(source_input), source_log=str(source_log),
        log_path=log_path, frequency_input=frequency.input_path, input_binding=record.input_binding,
        artifact_hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (native_path, log_path)})
    record.method_checks[native_path] = record.method_checks[str(source_input)]
    return TsJobStep(purpose='irc', state='done', input_path=native_path, actual_calculation=stage_calculation(record, 'irc'),
        source_input_revision=record.declaration_revision, stage_key='external:irc', external_source=facts)

def _check_calculation_submission(record, purpose, input_path, job_type):
    from cloudra.runtime_v2.method_policy import check_method
    from cloudra.services.ts_pipeline_context import require_pipeline_authority
    from cloudra.tools.core.calculation_intent import compare_calculation_input
    policy = require_pipeline_authority(record.owner_conversation_id, record.owner_session_id)
    calculation = stage_calculation(record, purpose)
    if calculation is None:
        raise ValueError(f"{purpose} has no explicit calculation")
    verdict = check_method(calculation.method, policy)
    if not verdict.allowed:
        raise ValueError(verdict.reason)
    content = Path(input_path).read_text()
    if job_type == 'chem_task':
        from cloudra.runtime.chem_task import ChemTask
        task = ChemTask.model_validate_json(content)
        expected_task = dict(path='xtb_path', candidate_opt='xtb_opt', product_seed_opt='xtb_opt')
        allowed_tasks = {'xtb_gradient', 'xtb_hessian'} if purpose == 'candidate_evaluation' else {expected_task.get(purpose)}
        if calculation.engine != 'xtb' or calculation.method != 'GFN2-xTB' or calculation.keywords or calculation.orca_blocks or calculation.end_setting:
            raise ValueError('Native chemistry task contract supports explicit GFN2-xTB with no native ORCA/Gaussian directives')
        if task.task not in allowed_tasks or (task.charge, task.multiplicity, task.cpus) != (record.input.reaction.charge, record.input.reaction.multiplicity, record.compute_cpus):
            raise ValueError('Native chemistry task/charge/multiplicity/resources differ from accepted input')
        solvation = task.solvation.model_dump() if task.solvation else None
        expected_solvation = record.input.guess.solvation.model_dump() if purpose == 'path' and record.input.guess.solvation else None
        if solvation != expected_solvation:
            raise ValueError('Native task solvation differs from its own accepted stage input')
        differences = []
    else:
        if job_type != calculation.engine:
            raise ValueError('Actual engine differs from accepted stage input')
        from cloudra.tools.core.calculation_intent import inspect_input
        actual_intent = inspect_input(content, engine=job_type)
        expected_tasks = {'scan': {'relaxed_scan'}, 'ts_opt': {'ts_opt'}, 'frequency': {'frequency'},
            'irc': {'irc'}, 'reactant_opt': {'minimum_opt'}, 'product_opt': {'minimum_opt'},
            'reactant_frequency': {'frequency'}, 'product_frequency': {'frequency'},
            'candidate_opt': {'minimum_opt'}, 'product_seed_opt': {'minimum_opt'}}
        if actual_intent.tasks != expected_tasks.get(purpose, set()):
            raise ValueError(f'Actual task {actual_intent.tasks} differs from accepted purpose {purpose}')
        differences = compare_calculation_input(content, calculation.model_dump(), charge=record.input.reaction.charge, multiplicity=record.input.reaction.multiplicity)
        # Complete task/user contracts, when present, come from project settings.
        contract = policy.calculation_contracts.get(purpose)
        if contract:
            differences += compare_calculation_input(content, contract, charge=contract.get('charge', record.input.reaction.charge), multiplicity=contract.get('multiplicity', record.input.reaction.multiplicity))
    result = dict(input_revision=record.declaration_revision, purpose=purpose, actual=calculation.model_dump(),
        source='project_method_policy', differences=[d.model_dump() for d in differences], matched=not differences)
    record.method_checks[input_path] = result
    if differences:
        raise ValueError('; '.join(d.message for d in differences))

def _submit_step(record: TsProcessRecord, purpose: str, input_path: str,
                 job_type: str, *, stage_key: str | None = None, action_kind: str | None = None,
                 ) -> tuple[str, int]:
    """准入 + 入库为 ready，并把这一步登记进作业序列。返回 ``(错误, job_id)``。

    归属与 ``submit_compute_job`` 同一纪律：conversation_id 是发起项目、
    session_id 是发起 agent——终态推送（ComputeNotifyBroker）只认这两个字段，
    缺归属的作业是投递不到的死信，宁可拒收也不入库。
    """
    from cloudra.services.compute_admission import admit_job
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.ts_pipeline_context import pipeline_database

    if not record.owner_conversation_id:
        return (
            "this run carries no owner identity (owner_conversation_id is empty), so its "
            "compute jobs would be undeliverable dead letters; refusing to submit. Start the "
            "run through ts_prepare so the calling project/agent is stamped.",
            -1,
        )

    try:
        _check_calculation_submission(record, purpose, input_path, job_type)
    except (ValueError, OSError) as exc:
        return str(exc), -1

    # charge/multiplicity 是 xtb 专属运行参数，orca/gaussian 作业必须留默认——电荷/自旋已经
    # 写在输入文件里，再传一次会被准入 fail-loud 拒收（"绝不静默丢弃"那道门）
    admission = admit_job(
        input_file=input_path,
        job_type=job_type,
        cpus=record.compute_cpus,
        memory_mb=record.compute_memory_mb,
        execution_backend="auto",
    )
    if not admission.ok:
        return admission.message, -1

    db = pipeline_database().init()
    payload = dict(
        conversation_id=record.owner_conversation_id,
        session_id=record.owner_session_id,
        path=input_path,
        state="ready",
        jobtype=job_type,
        node_id=admission.node_id,
        scheduler=admission.scheduler,
        scheduler_options=json.dumps(admission.scheduler_options, ensure_ascii=False),
        priority=0,
        req_cpus=record.compute_cpus,
        req_memory_mb=record.compute_memory_mb,
    )
    if record.pipeline_id:
        from cloudra.services.ts_pipeline_store import bind_stage_job
        effective_stage = stage_key or purpose
        binding = {}
        if record.input.execution.limits is not None:
            from cloudra.services.exploration_budget_store import CostEstimate, reserve_actions
            stages = ['ts_opt','frequency','irc','reactant_opt','reactant_frequency','product_opt','product_frequency'] if purpose == 'ts_opt' else [purpose,purpose.removesuffix('_opt')+'_frequency'] if purpose in ('reactant_opt','product_opt') else [effective_stage]
            tag=f"{record.declaration_revision}:{record.selected_candidate_id or record.run_id}"
            keys={stage:f'{tag}:{stage}' for stage in stages}
            # Subsequent stages consume the previously reserved validation chain.
            if effective_stage not in record.budget_action_keys:
                try:
                    reserved=reserve_actions(db,process_id=record.pipeline_id,decision_id=f'validation:{tag}' if purpose=='ts_opt' else f'{tag}:{effective_stage}',estimates=[CostEstimate(
                        action_key=keys[stage],action_kind=action_kind or ('sampling' if stage=='sampling' else 'path' if stage=='path' else 'ts' if stage=='ts_opt' else 'irc' if stage=='irc' else 'frequency' if 'frequency' in stage else 'optimization'),
                        source='ts_action_count') for stage in stages])
                except ValueError as exc:
                    return str(exc), -1
                for stage in stages:
                    record.budget_action_keys[stage]=keys[stage]
                    record.budget_reservations[stage]=reserved.reservation_id
            binding=dict(reservation_id=record.budget_reservations[effective_stage],action_key=record.budget_action_keys[effective_stage])
        job_id = bind_stage_job(db, process_id=record.pipeline_id, declaration_revision=record.declaration_revision,
                               stage_key=effective_stage, attempt=1, job_payload=payload, **binding)
    else:
        job_id = int(insert_compute_job(db, **payload))
    return "", job_id

def _refinement_log_path(record: TsProcessRecord, step: TsJobStep) -> str:
    """该步作业的实测日志路径（走统一的 resolve_log_path，不猜文件名）。"""
    from cloudra.infra.compute_utils import resolve_log_path

    if step.external_source:
        return step.external_source['log_path']
    job_type = _step_calculation(record, step).engine
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
    step = next(step for step in reversed(record.job_steps) if step.purpose == 'ts_opt')
    log_path = _refinement_log_path(record, step)
    if not os.path.isfile(log_path):
        return (
            f"the TS-optimisation job's log was not found at its registered location {log_path}; "
            "refusing to run frequencies on an unverified geometry",
            "",
        )
    frames_mod = orca_frames if _step_calculation(record, step).engine == "orca" else gaussian_frames
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

    declaration = record.input.reaction
    calculation = stage_calculation(record, 'frequency')
    if calculation is None:
        return 'Explicit verification.frequency required', ''
    method = calculation.method.strip()
    head, _sep, basis = method.partition("/")
    input_path = os.path.join(job_dir, f"frequency.{'inp' if calculation.engine == 'orca' else 'gjf'}")
    request = QmInputWriter_input_schema(
        nproc=record.compute_cpus,
        mem=f"{record.compute_memory_mb}MB",
        engine=calculation.engine,
        source_type="xyz_file",
        source_value=optimized_xyz,
        method=head.strip(),
        basis_set=basis.strip(),
        task_type=[{"freq": None}],
        extra_keywords=calculation.keywords,
        frequency_mode=calculation.frequency_mode,
        orca_blocks=calculation.orca_blocks,
        end_setting=calculation.end_setting,
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
        if calculation.engine == "orca"
        else QmInputWriter._build_gjf(request, coords)
    )
    inspected = inspect_input(content, engine=calculation.engine)
    requested = intent_from_writer(request.model_dump())
    if inspected.tasks != requested.tasks:
        return (
            "frequency input internal mismatch: generated "
            f"{sorted(inspected.tasks)} but {sorted(requested.tasks)} were requested",
            "",
        )
    _write_immutable_input(input_path, content)
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

    declaration = record.input.reaction
    calculation = stage_calculation(record, 'irc')
    if calculation is None:
        return 'Explicit verification.irc required', ''
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

    method = calculation.method.strip()
    head, _sep, basis = method.partition("/")
    input_path = os.path.join(job_dir, f"irc.{'inp' if calculation.engine == 'orca' else 'gjf'}")

    if calculation.engine == "orca":
        task_type: list[dict] = [{"irc": None}]
        hess_path = os.path.splitext(frequency_step.input_path)[0] + ".hess"
        previous_calculation = _step_calculation(record, frequency_step)
        same_theory = previous_calculation.model_dump(exclude={'frequency_mode'}) == calculation.model_dump(exclude={'frequency_mode'})
        if os.path.isfile(hess_path) and same_theory:
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
        nproc=record.compute_cpus,
        mem=f"{record.compute_memory_mb}MB",
        engine=calculation.engine,
        source_type="xyz_file",
        source_value=geometry,
        method=head.strip(),
        basis_set=basis.strip(),
        task_type=task_type,
        extra_keywords=calculation.keywords,
        orca_blocks='\n'.join(filter(None, [orca_blocks, calculation.orca_blocks])) or None,
        frequency_mode=calculation.frequency_mode,
        end_setting=calculation.end_setting,
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
        if calculation.engine == "orca"
        else QmInputWriter._build_gjf(request, _xyz_coords(geometry))
    )
    inspected = inspect_input(content, engine=calculation.engine)
    requested = intent_from_writer(request.model_dump())
    if inspected.tasks != requested.tasks:
        return (
            f"IRC input internal mismatch: generated {sorted(inspected.tasks)} but "
            f"{sorted(requested.tasks)} were requested",
            "",
        )
    _write_immutable_input(input_path, content)
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
    if _step_calculation(record, step).engine == "orca":
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

    calculation = stage_calculation(record, f'{role}_{task}')
    if calculation is None:
        return f'Explicit {_calculation_field(f"{role}_{task}")} required', ''
    endpoint = getattr(record.input.verification, role + '_endpoint')
    if task == 'opt' and endpoint.seed is not None:
        source = endpoint.seed.xyz_path
        path = Path(source).resolve()
        path.relative_to(Path(record.workspace_dir).resolve())
        for reference in endpoint.seed.evidence_refs:
            artifact = Path(reference).resolve()
            artifact.relative_to(Path(record.workspace_dir).resolve())
            if not artifact.is_file():
                return 'Endpoint replacement source/evidence missing', ''
        if not path.is_file():
            return 'Endpoint replacement source/evidence missing', ''
        from cloudra.tools.core.structure_artifacts import read_xyz_atoms
        atoms = read_xyz_atoms(path)
        error = _endpoint_identity_error(record, role, ([s for s, _ in atoms], [point for _, point in atoms]))
        if error:
            return error, ''
    elif task == "opt":
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
            mode="verify", irc_log=irc_log, engine=_step_calculation(record, irc_step).engine,
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

    source_copy=os.path.join(job_dir,f'{role}_source.xyz')
    _write_immutable_input(source_copy,Path(source).read_text())
    source=source_copy
    declaration = record.input.reaction
    head, _sep, basis = calculation.method.strip().partition("/")
    task_type = [{"opt": None}] if task == "opt" else [{"freq": None}]
    name = f"{role}_{task}.{'inp' if calculation.engine == 'orca' else 'gjf'}"
    input_path = os.path.join(job_dir, name)
    request = QmInputWriter_input_schema(
        nproc=record.compute_cpus,
        mem=f"{record.compute_memory_mb}MB",
        engine=calculation.engine,
        source_type="xyz_file", source_value=source,
        method=head.strip(), basis_set=basis.strip(), task_type=task_type,
        extra_keywords=calculation.keywords,
        frequency_mode=calculation.frequency_mode, orca_blocks=calculation.orca_blocks,
        end_setting=calculation.end_setting,
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
        if calculation.engine == "orca"
        else QmInputWriter._build_gjf(request, _xyz_coords(source))
    )
    if inspect_input(content, engine=calculation.engine).tasks != intent_from_writer(
        request.model_dump()
    ).tasks:
        return f"{role} {task} input task mismatch", ""
    _write_immutable_input(input_path, content)
    return "", input_path



def _refine(record: TsProcessRecord) -> TsProcessRecord:
    """推进 TS Opt/Freq → IRC → 两端 Opt/Freq 作业序列。**从不轮询**。

    还没到终态时本阶段置 ``waiting`` 并**不推事件**：等计算不算"阻塞"，agent 不该被叫醒。
    作业终态由既有的 compute 通知路径交给系统 driver，
    系统 driver 重新读账本并推进；agent 只处理受阻后的显式调整。
    """
    from cloudra.services.compute_store import TERMINAL_STATES

    if not record.job_steps:
        return _block(
            record, "refine", "no_job_submitted",
            "the submit stage recorded no job, so there is nothing to refine",
            needs=["method", "engine"],
        )

    # A local endpoint revision can retain the opposite endpoint. Resume from
    # the last contiguous predecessor, rather than whichever job was appended
    # last in an earlier input revision.
    current = None
    formal_order = ('ts_opt', 'frequency', 'irc', 'reactant_opt', 'reactant_frequency', 'product_opt', 'product_frequency')
    first = next((i for i, purpose in enumerate(formal_order) if any(s.purpose == purpose for s in record.job_steps)), len(formal_order))
    for purpose in formal_order[first:]:
        step = next((s for s in reversed(record.job_steps) if s.purpose == purpose), None)
        if step is None:
            break
        current = step
        if _step_state(record, step) != 'done':
            break
    if current is None:
        return _block(record, 'refine', 'no_job_submitted', 'A TS optimization is required before verification.', needs=['ts_optimization'])
    state = _step_state(record, current)
    current.state = state
    if state not in TERMINAL_STATES:
        record.waiting_for = f"job:{current.job_id}"
        _record_stage(
            record, "refine", "waiting",
            f"waiting for job {current.job_id} ({current.purpose}) to reach a terminal state; "
            "the existing compute notification path advances the system driver, so this stage never polls "
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
        failure = 'unclassified_failure'
        if Path(log_path).is_file():
            engine_text = Path(log_path).read_text(errors='replace').upper()
            if any(marker in engine_text for marker in (
                'GEOMETRY OPTIMIZATION DID NOT CONVERGE', 'FAILED TO CONVERGE',
                'SCF NOT CONVERGED', 'CONVERGENCE FAILURE', 'NUMBER OF STEPS EXCEEDED',
            )):
                failure = 'nonconvergence'
        _record_candidate_failure(record, failure, current, log_path)
        return _block(
            record, "refine", f"job_{state}",
            f"refinement job {current.job_id} ({current.purpose}) ended as {state!r}; plain "
            "per-engine failure classes come from the log below — the run is stopped, not silently "
            "retried",
            atom_details=details,
            needs=[_calculation_field(current.purpose), "execution", "reaction.reaction_center", "recovery"],
        )

    if current.purpose == "ts_opt":
        if _require_calculation(record, 'frequency', 'refine'):
            return record
        # 优化完成：取优化末帧写频率作业（频率是独立作业，见 skill）
        job_dir = _job_directory(record, "frequency")
        os.makedirs(job_dir, exist_ok=True)
        error, input_path = _write_frequency_input(record, job_dir)
        if error:
            return _block(
                record, "refine", "frequency_input_failed", error, needs=["method", "engine"]
            )
        job_type = stage_calculation(record, 'frequency').engine
        error, job_id = _submit_step(record, "frequency", input_path, job_type)
        if error:
            return _block(
                record, "refine", "compute_admission_rejected", error,
                needs=["method", "engine", "budget"],
            )
        record.job_steps.append(TsJobStep(
            purpose="frequency", job_id=job_id, input_path=input_path, state="ready",
            actual_calculation=stage_calculation(record, 'frequency'), source_input_revision=record.declaration_revision,
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
        if _require_calculation(record, 'irc', 'refine'):
            return record
        # 频率完成：TS 已由频率数据支持，接着跑 IRC（第二道闸），复用同一几何的 Hessian
        from cloudra.dag.evidence_ingest import snapshot_evidence_file
        log_path = _refinement_log_path(record, current)
        if not Path(log_path).is_file():
            return _block(record, 'refine', 'frequency_evidence_missing',
                          'TS frequency log is missing; IRC cannot be admitted.', needs=['compute_artifacts'])
        snapshot = snapshot_evidence_file(log_path, workspace_root=record.workspace_dir)
        if snapshot.frequencies is None and snapshot.imaginary_frequencies is None:
            return _block(record, 'refine', 'frequency_evidence_missing',
                          'TS frequency data is unavailable; IRC cannot be admitted.', needs=['compute_artifacts'])
        imaginary = snapshot.imaginary_frequencies if snapshot.imaginary_frequencies is not None else [f for f in snapshot.frequencies if f < 0]
        if len(imaginary) != 1:
            _record_candidate_failure(record, 'wrong_mode', current, log_path)
            return _block(record, 'refine', 'wrong_mode',
                          f'TS frequency evidence has {len(imaginary)} imaginary modes; exactly one is required before IRC.', needs=['conformers', 'guess', 'verification.frequency', 'recovery'])
        if record.input.verification.irc_log:
            try:
                record.job_steps.append(_reuse_existing_irc(record))
            except (ValueError, OSError) as exc:
                return _block(record, 'refine', 'irc_source_unconfirmed', str(exc), needs=['verification.irc_log', 'verification.irc'])
            return _refine(record)
        job_dir = _job_directory(record, "irc")
        os.makedirs(job_dir, exist_ok=True)
        error, input_path = _write_irc_input(record, job_dir)
        if error:
            return _block(record, "refine", "irc_input_failed", error, needs=["method", "engine"])
        job_type = stage_calculation(record, 'irc').engine
        error, job_id = _submit_step(record, "irc", input_path, job_type)
        if error:
            return _block(
                record, "refine", "compute_admission_rejected", error,
                needs=["method", "engine", "budget"],
            )
        record.job_steps.append(TsJobStep(
            purpose="irc", job_id=job_id, input_path=input_path, state="ready",
            actual_calculation=stage_calculation(record, 'irc'), source_input_revision=record.declaration_revision,
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
            _record_candidate_failure(record, 'endpoint_unconfirmed', current, _refinement_log_path(record, current))
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
    while endpoint_next is not None:
        role, task=endpoint_next
        purpose=role+'_'+task
        existing=next((s for s in reversed(record.job_steps) if s.purpose==purpose),None)
        if existing is None:
            break
        existing.state=_step_state(record,existing)
        if existing.state=='done':
            endpoint_next={"reactant_opt":("reactant","frequency"),"reactant_frequency":("product","opt"),"product_opt":("product","frequency")}.get(purpose)
            continue
        if existing.state not in TERMINAL_STATES:
            record.waiting_for=f'job:{existing.job_id}'
            return record
        _record_candidate_failure(record, 'endpoint_failed', existing, _refinement_log_path(record, existing))
        return _block(record,'refine','endpoint_failed','Existing endpoint attempt failed; relevant repair evidence is required.',needs=[f'verification.{role}_endpoint', 'recovery'])
    if endpoint_next is not None:
        role, task = endpoint_next
        purpose = f'{role}_{task}'
        if _require_calculation(record, purpose, 'refine'):
            return record
        job_dir = _job_directory(record, f"{role}_{task}")
        os.makedirs(job_dir, exist_ok=True)
        error, input_path = _write_endpoint_input(record, job_dir, role, task)
        if error:
            if task == "frequency":
                return _terminal(
                    record, "verdict", "candidate_only",
                    f"{role} endpoint optimization cannot support a minimum: {error}. "
                    "Revise this run with an explicit endpoint seed and relevant recovery evidence through ts_resume",
                )
            return _block(
                record, "refine", "endpoint_input_failed", error,
                needs=[f"verification.{role}_endpoint", f"reaction.{role}_smiles"],
            )
        job_type = stage_calculation(record, purpose).engine
        purpose = f"{role}_{task}"
        error, job_id = _submit_step(record, purpose, input_path, job_type)
        if error:
            return _block(
                record, "refine", "compute_admission_rejected", error,
                needs=["method", "engine", "budget"],
            )
        record.job_steps.append(TsJobStep(
            purpose=purpose, job_id=job_id, input_path=input_path, state="ready",
            actual_calculation=stage_calculation(record, purpose), source_input_revision=record.declaration_revision,
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
    if _step_calculation(record, freq_step).engine == "orca":
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
    from rdkit import Chem

    source_role = (
        "reactant" if role == "product" and _rotated_product(record) is not None
        else role
    )
    built = _read_built_xyz(record, source_role)
    if built is None or not built[3] or not os.path.isfile(built[3]):
        return f"{role} declared endpoint MOL is missing; connectivity is unverified"
    mol = Chem.MolFromMolBlock(Path(built[3]).read_text(encoding="utf-8"), removeHs=False)
    if mol is None:
        return f"{role} declared endpoint MOL cannot be parsed; connectivity is unverified"
    expected_smiles = (
        record.input.reaction.reactant_smiles if source_role == "reactant"
        else record.input.reaction.product_smiles
    )
    declared = Chem.MolFromSmiles(expected_smiles)
    if declared is None or Chem.MolToSmiles(Chem.RemoveHs(mol)) != Chem.MolToSmiles(declared):
        return f"{role} built MOL does not match its declared SMILES; connectivity is unverified"
    n = mol.GetNumAtoms()
    if role == "product" and _rotated_product(record) is None:
        remap = list(record.input.reaction.atom_map)
    else:
        remap = list(range(n))
    if sorted(remap) != list(range(n)) or len(optimized[0]) != n:
        return f"{role} endpoint atom map or atom count is inconsistent; connectivity is unverified"
    expected_symbols = [""] * n
    for atom in mol.GetAtoms():
        expected_symbols[remap[atom.GetIdx()]] = atom.GetSymbol()
    if expected_symbols != optimized[0]:
        return f"{role} optimized atom order differs from the declared species; connectivity is unverified"
    from cloudra.tools.core.preorganization import geometry_stereochemistry_errors
    stereo_errors = geometry_stereochemistry_errors(
        mol, [optimized[1][remap[index]] for index in range(n)],
    )
    if stereo_errors:
        return f"{role} " + "; ".join(stereo_errors)
    return _geometry_connectivity_error(mol, optimized, record.input.reaction.charge, role, remap)

def _geometry_connectivity_error(mol, optimized, charge, role, remap=None):
    """Use the existing endpoint bond-perception contract for concrete seeds too."""
    import math

    from rdkit import Chem

    from cloudra.tools.core.irc_path import COVALENT_RADII, DISTANCE_CONNECTIVITY_FACTOR, perceive_bonds
    n = mol.GetNumAtoms()
    remap = list(range(n)) if remap is None else remap
    expected_bonds = {
        tuple(sorted((remap[bond.GetBeginAtomIdx()], remap[bond.GetEndAtomIdx()]))):
        float(bond.GetBondTypeAsDouble())
        for bond in mol.GetBonds()
    }
    fragments = Chem.GetMolFrags(mol)
    if len(fragments) == 1:
        actual_bonds, source = perceive_bonds(
            optimized[0], optimized[1], charge,
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
                        f"{left + 1}-{right + 1}; connectivity cannot be verified"
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
        engine=stage_calculation(record, 'irc').engine,
        output_dir=os.path.join(record.run_dir, VERDICT_STAGE_DIR),
        charge=record.input.reaction.charge,
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
        watch_pairs, record.input.reaction.charge,
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
        _record_candidate_failure(record,'wrong_mode',freq_step,log_path)
        kind = "a local minimum" if not imag else f"a point with {len(imag)} imaginary modes"
        return _terminal(
            record, "verdict", "candidate_only",
            f"frequency analysis found {len(imag)} imaginary mode(s) ({imag}); the candidate is "
            f"{kind}, not a first-order saddle point. This falsifies the candidate — it does NOT "
            "mean the reaction is impossible",
        )

    # 频率支持一阶鞍点。IRC 是第二道闸：没有 IRC 就只能到 candidate_only，绝不升格成 verified。
    # Verdict uses only the immutable, validated accepted IRC step.
    irc_step = next((step for step in reversed(record.job_steps) if step.purpose == "irc"), None)
    irc_log = _refinement_log_path(record, irc_step) if irc_step else ''
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
    limits = record.input.execution.limits
    if limits and limits.max_interventions is not None and record.intervention_count > limits.max_interventions:
        return _terminal(
            record, record.stage, "search_failed",
            f"the intervention budget ({limits.max_interventions}) is exhausted; "
            "stopping rather than looping. Search failure is NOT a claim that the reaction is "
            "impossible",
        )
    start = STAGE_ORDER.index(record.stage)
    for stage in STAGE_ORDER[start:]:
        if stage in _NOT_IMPLEMENTED_STAGES:
            return _stop_at_unimplemented(record, stage)
        record = _STAGE_FUNCS[stage](record)
        if record.pipeline_id:
            save_record(record)
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
    from cloudra.infra.flocks import locked
    from cloudra.services.ts_pipeline_context import pipeline_database, require_pipeline_producer
    from cloudra.services.ts_pipeline_store import create_process
    from cloudra.tools.core.ts_pipeline_driver import advance_process
    require_pipeline_producer(request.owner_conversation_id, request.owner_session_id)
    root = os.path.join(request.workspace_dir, TS_ROOT_NAME)
    os.makedirs(root, exist_ok=True)
    with locked(os.path.join(root, '.creation.lock')):
        process = None
        if request.owner_conversation_id:
            process = create_process(pipeline_database(), request_key=request.request_key, payload=dict(
                project_id=request.owner_conversation_id, owner_id=request.owner_session_id,
                workspace_dir=request.workspace_dir, input=request.input.model_dump(mode='json')))
            if process['record'] is not None:
                return TsProcessRecord.model_validate(process['record'])
        run_id = _next_run_id(request.workspace_dir)
        run_dir = os.path.join(root, run_id)
        os.makedirs(run_dir, exist_ok=False)
        _make_stage_dirs(run_dir)
        record = TsProcessRecord(run_id=run_id, run_dir=run_dir, workspace_dir=request.workspace_dir,
            owner_conversation_id=request.owner_conversation_id, owner_session_id=request.owner_session_id,
            input=request.input, pipeline_id=process['process_id'] if process else '')
        if record.pipeline_id and record.input.execution.limits:
            from cloudra.services.exploration_budget_store import ExplorationBudget, configure_budget
            limits = record.input.execution.limits
            configure_budget(pipeline_database(),process_id=record.pipeline_id,project_id=record.owner_conversation_id,
                             owner_id=record.owner_session_id,budget=ExplorationBudget(source=limits.source,
                                max_compute_actions=limits.max_compute_actions,max_model_calls=limits.max_model_calls))
        save_record(record)
    if record.pipeline_id:
        record = TsProcessRecord.model_validate(advance_process(pipeline_database(), record.pipeline_id)['record'])
    else:
        record = advance(record)
        save_record(record)
    if event_sink is not None:
        _emit(event_sink, record)
    return record

def resume(record: TsProcessRecord, request: TsResumeRequest,
           event_sink: Optional[Callable[[str, dict], None]] = None) -> TsProcessRecord:
    """Accept a durable input revision before automatically continuing."""
    from cloudra.tools.core.ts_revision import resume_revised_process
    return resume_revised_process(record, request, event_sink=event_sink)







def _emit(event_sink: Callable[[str, dict], None], record: TsProcessRecord) -> None:
    """只推两类事件：**阻塞与终态**。阶段推进不推（避免污染上下文）。"""
    if record.terminal is not None or record.blocked is not None:
        from cloudra.services.ts_pipeline_context import pipeline_database
        from cloudra.tools.core.ts_state_view import build_process_view, recorded_notification_view
        value = record.model_dump(mode='json')
        view = recorded_notification_view(pipeline_database(), value) if record.pipeline_id else build_process_view(value, [], can_write=True).model_dump(mode='json')
        event_sink('ts.terminal' if record.terminal is not None else 'ts.blocked', view)

def evidence_binding_candidates(record: TsProcessRecord) -> list[str]:
    """可进证据集的产物：**只含小而有意义的文件**，逐迭代帧永远不在其中（SOP §7 第 2 条）。"""
    return [path for path in record.evidence_candidates if TRAJECTORY_DIR_NAME not in path]
