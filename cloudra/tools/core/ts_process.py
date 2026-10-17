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

import hashlib
import json
import os
from pathlib import Path
from typing import Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cloudra.persistence.fs_utils import atomic_write_bytes, atomic_write_text
from cloudra.tools.core.conformer_cards import AttemptEvidence
from cloudra.tools.core.geometry_inputs import atom_index_base
from cloudra.tools.core.geometry_optimization import OptimizationCheckpoint
from cloudra.tools.core.molecule import (
    read_molecule,
    renumber_atoms,
    to_xyz,
    with_positions,
)
from cloudra.tools.core.qm_calculation import QmCalculation
from cloudra.tools.core.reaction_state import (
    ReactionStructures,
    export_structure,
    heavy_binding,
    import_file_structure,
    path_endpoints,
    set_heavy_binding,
)
from cloudra.tools.core.structure_builder import (
    BuildStrategy,
    PreparationRequest,
    StructureInput,
    prepare_structure,
)
from cloudra.tools.core.ts_inputs import TsInput, TsResumeRequest, resolve_calculation

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
    issues: list[dict] = Field(default_factory=list, description="Recoverable input facts with code and field")

class TsStageRecord(BaseModel):
    stage: TsStage
    status: StageStatus
    detail: str = ""
    artifacts: list[str] = Field(default_factory=list)
    source_input_revision: int = 1


class TsArtifactBinding(BaseModel):
    source_path: str
    snapshot_path: str
    sha256: str


class TsProvidedGuessBinding(BaseModel):
    xyz: TsArtifactBinding
    evidence: list[TsArtifactBinding]


class TsAttemptHistory(BaseModel):
    declaration_revision: int
    selected_candidate_id: str | None = None
    job_steps: list["TsJobStep"]
    stage_records: list[TsStageRecord]
    reason: str
    input: TsInput | None = None
    structures: ReactionStructures | None = None
    provided_guess_binding: TsProvidedGuessBinding | None = None
    terminal: TsTerminal | None = None
    blocked: TsBlocked | None = None
    failed_attempt: dict | None = None
    stop_reason: str | None = None


class TsProcessRecord(BaseModel):
    """持久运行记录（``ts/<run_id>/process.json``）。"""

    model_config = ConfigDict(extra='forbid')
    format_version: Literal[7] = 7
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
    structures: ReactionStructures = Field(default_factory=ReactionStructures)
    provided_guess_binding: TsProvidedGuessBinding | None = None
    failed_attempt: dict | None = None
    method_checks: dict[str, dict] = Field(default_factory=dict)
    stage: TsStage = "declare"
    stage_records: list[TsStageRecord] = Field(default_factory=list)
    terminal: Optional[TsTerminal] = None
    stop_reason: str | None = None
    blocked: Optional[TsBlocked] = None
    intervention_count: int = 0
    path_kind: PathKind = "not_attempted"
    guidance_attempt: int = 0
    active_attempt_dir: str = ""
    guidance_manifest_path: str = ""
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

def _workspace_input_path(record: TsProcessRecord, path: str) -> Path:
    """Resolve declared files against the bound workspace and enforce its boundary."""
    root = Path(record.workspace_dir).resolve()
    resolved = (root / path).resolve()
    resolved.relative_to(root)
    return resolved


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

def _write_immutable_input(path: str, content: str | bytes) -> None:
    """A bound engine input may be retried, never silently overwritten."""
    data = content.encode('utf-8') if isinstance(content, str) else content
    existing = Path(path)
    if existing.exists():
        if existing.read_bytes() != data:
            raise ValueError('immutable stage input conflict')
        return
    atomic_write_bytes(path, data)


def _bind_provided_artifact(record, source: str, target: Path) -> TsArtifactBinding:
    path = _workspace_input_path(record, source)
    data = path.read_bytes()
    _write_immutable_input(str(target), data)
    return TsArtifactBinding(source_path=str(path), snapshot_path=str(target),
                             sha256=hashlib.sha256(data).hexdigest())


def _verify_provided_guess_binding(record) -> None:
    binding = record.provided_guess_binding
    if binding is not None:
        for artifact in (binding.xyz, *binding.evidence):
            path = _workspace_input_path(record, artifact.snapshot_path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
                raise ValueError(f'Bound provided guess artifact changed: {path}')

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
    if data.get("format_version") != 7:
        raise ValueError("Unsupported TS input format; existing compute jobs remain intact.")
    return TsProcessRecord.model_validate(data)

def _record_stage(record: TsProcessRecord, stage: TsStage, status: StageStatus,
                  detail: str = "", artifacts: Optional[list[str]] = None) -> None:
    entry = TsStageRecord(stage=stage, status=status, detail=detail, artifacts=list(artifacts or []), source_input_revision=record.declaration_revision)
    record.stage_records = [r for r in record.stage_records if r.stage != stage] + [entry]
    record.stage = stage

def _block(record: TsProcessRecord, stage: TsStage, failure_class: str, message: str,
           atom_details: Optional[list[str]] = None,
           needs: Optional[list[str]] = None, issues: Optional[list[dict]] = None) -> TsProcessRecord:
    record.blocked = TsBlocked(
        failure_class=failure_class, stage=stage, message=message,
        atom_details=list(atom_details or []), needs=list(needs or []), issues=list(issues or []),
    )
    _record_stage(record, stage, "blocked", message)
    return record

def _artifact_sha256(path: Path) -> str | None:
    import hashlib

    if not path.is_file():
        return None
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _record_candidate_failure(record, failure_class, step, evidence_path, diagnostics=None):
    record.failed_attempt = dict(attempt_id=f'{step.source_input_revision}:{step.purpose}:{step.job_id}',
        failure_class=failure_class, purpose=step.purpose, job_id=step.job_id,
        input_revision=step.source_input_revision, evidence_refs=[evidence_path],
        input_path=step.input_path, log_path=evidence_path,
        input_sha256=_artifact_sha256(Path(step.input_path)),
        log_sha256=_artifact_sha256(Path(evidence_path)),
        diagnostics=list(diagnostics or []))
    if not record.catalog_id or not record.selected_candidate_id:
        return
    from cloudra.tools.core.conformer_catalog import content_digest
    attempt=AttemptEvidence(candidate_id=record.selected_candidate_id,region_id='',stage=step.purpose,
        input_hash=content_digest(Path(step.input_path).read_bytes().hex()) if Path(step.input_path).is_file() else record.selected_candidate_id,
        failure_class=failure_class,job_id=step.job_id,evidence_refs=[evidence_path])
    if attempt not in record.candidate_attempts:
        record.candidate_attempts.append(attempt)


def _native_failure_details(log_path: str, engine: str) -> tuple[str, list[str]]:
    """Preserve native failure warnings even when reference/timing footers follow."""
    path = Path(log_path)
    if not path.is_file():
        return 'unclassified_failure', [f'log not found at {log_path}']
    text = path.read_text(errors='replace')
    markers = (
        'GEOMETRY OPTIMIZATION DID NOT CONVERGE', 'FAILED TO CONVERGE',
        'SCF NOT CONVERGED', 'CONVERGENCE FAILURE', 'NUMBER OF STEPS EXCEEDED',
    )
    nonconverged = any(marker in text.upper() for marker in markers)
    if engine == 'orca':
        from cloudra.tools.core.orca_frames import opt_converged
        nonconverged = nonconverged or opt_converged(text) is False
    lines = text.splitlines()
    warnings = [index for index, line in enumerate(lines)
                if any(marker in line.upper() for marker in
                       (*markers, 'DID NOT CONVERGE', 'ERROR', 'ABORT', 'FAILED'))]
    selected = set(range(max(0, len(lines) - 15), len(lines)))
    for index in warnings[-5:]:
        selected.update(range(max(0, index - 2), min(len(lines), index + 4)))
    details = [f'native log: {log_path}', *(lines[index] for index in sorted(selected))]
    return 'nonconvergence' if nonconverged else 'unclassified_failure', details


def _terminal(record: TsProcessRecord, stage: TsStage, terminal: TsTerminal,
              detail: str) -> TsProcessRecord:
    record.terminal = terminal
    record.blocked = None
    _record_stage(record, stage, "done", detail)
    return record

# ---------------------------------------------------------------------------
# 阶段实现
# ---------------------------------------------------------------------------

def stage_calculation(record: TsProcessRecord, purpose: str) -> QmCalculation | None:
    if purpose == 'ts_opt':
        value = record.input.ts_optimization
    elif purpose in ('frequency', 'irc'):
        value = getattr(record.input.verification, purpose)
    elif purpose in ('reactant_opt', 'product_opt', 'reactant_frequency', 'product_frequency'):
        side, task = purpose.split('_', 1)
        value = getattr(getattr(record.input.verification, side + '_endpoint'), 'optimization' if task == 'opt' else task)
    elif purpose == 'scan':
        guess = record.input.guess
        value = guess.calculation if guess and guess.kind == 'scan' else None
    elif purpose == 'path':
        guess = record.input.guess
        value = QmCalculation(engine='xtb', method=guess.method, basis_set='', keywords='') if guess and guess.kind == 'xtb_path' else None
    elif purpose in ('candidate_opt', 'candidate_evaluation', 'product_seed_opt'):
        source = getattr(record.input.conformers, 'product' if purpose == 'product_seed_opt' else 'reactant')
        value = getattr(source, 'optimization', None)
    else:
        return None
    return resolve_calculation(value, record.input.calculations)

def _calculation_field(purpose: str) -> str:
    if purpose == 'ts_opt':
        return 'ts_optimization'
    if purpose in ('frequency', 'irc'):
        return 'verification.' + purpose
    if purpose == 'scan':
        return 'guess.calculation'
    side, task = purpose.split('_', 1)
    return f'verification.{side}_endpoint.{"optimization" if task == "opt" else task}'

def _open_shell_singlet(record) -> bool:
    """Read the declared/graph state without choosing its wavefunction settings."""
    if record.input.reaction.multiplicity != 1:
        return False
    from rdkit import Chem

    from cloudra.tools.core.electronic_state import electronic_state_details

    reaction = record.input.reaction
    for smiles in (reaction.reactant_smiles, reaction.product_smiles):
        graph = Chem.MolFromSmiles(smiles)
        if graph is not None and electronic_state_details(
            graph, charge=reaction.charge, multiplicity=reaction.multiplicity,
            electronic_character=reaction.electronic_character,
        )['is_open_shell']:
            return True
    return False


def _xtb_state_checkpoint(record, stage, field) -> bool:
    if not _open_shell_singlet(record):
        return False
    _block(record, stage, 'electronic_state_backend_unsupported',
           'The current GFN-xTB interface cannot represent an open-shell singlet through --uhf 0. '
           'Supply an externally prepared guess or an explicitly declared capable QM calculation '
           'with its initial-spin settings; the workflow will not choose them automatically.', needs=[field])
    return True


def _require_calculation(record, purpose, stage) -> bool:
    calculation = stage_calculation(record, purpose)
    if calculation is None:
        field = _calculation_field(purpose)
        _block(record, stage, 'missing_input', f'Explicit calculation required: {field}', needs=[field])
        return True
    if calculation.engine == 'xtb' and _xtb_state_checkpoint(record, stage, _calculation_field(purpose)):
        return True
    if calculation.engine not in (('orca', 'gaussian', 'xtb') if purpose == 'scan' else ('orca', 'gaussian')):
        _block(record, stage, 'unsupported_calculation', f'{purpose} does not support {calculation.engine}', needs=[_calculation_field(purpose)])
        return True
    return False

def _step_calculation(record, step) -> QmCalculation:
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
    else:
        from cloudra.tools.core.electronic_state import electronic_state_issue
        for role, graph in (('reactant', reactant_graph), ('product', product_graph)):
            issue = electronic_state_issue(graph, charge=declaration.charge,
                multiplicity=declaration.multiplicity, electronic_character=declaration.electronic_character)
            if issue:
                problems.append(f'{role}: {issue[1]}')
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
        # 已导入的分子是当前事实；推进、改设置和读取状态不重读源文件。
        if source.kind == 'file':
            if getattr(record.structures, role) is None:
                try:
                    setattr(record.structures, role, import_file_structure(record, role, source))
                except (ValueError, OSError) as exc:
                    return _block(record, 'build', 'conformer_source_invalid', str(exc), needs=[f'conformers.{role}'],
                        issues=[dict(code='source_missing' if isinstance(exc, FileNotFoundError) else 'source_invalid',
                            field=f'conformers.{role}', role=role, path=getattr(exc, 'filename', None))])
            if source.optimization is not None:
                record = _optimize_conformer_source(record, role)
                if record.blocked or record.waiting_for:
                    return record
            continue
        if source.kind == 'catalog':
            from cloudra.tools.core.ts_candidate_pipeline import use_catalog_source
            if getattr(record.structures, role) is None:
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
        if getattr(record.structures, role) is not None:
            if source.optimization is not None:
                record = _optimize_conformer_source(record, role)
                if record.blocked or record.waiting_for:
                    return record
            continue
        target_dir = (
            os.path.join(record.active_attempt_dir, role)
            if record.active_attempt_dir else os.path.join(out_dir, f'input_{record.declaration_revision:04d}', role)
        )
        prepared = prepare_structure(PreparationRequest(
            structure=StructureInput(kind="smiles", value=smiles),
            output_dir=target_dir,
            total_charge=declaration.charge,
            multiplicity=declaration.multiplicity,
            electronic_character=declaration.electronic_character,
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
                seed_path, mol_path, seed_mol = _bind_generated_seed(prepared, target_dir, source.seed)
            except (ValueError, OSError) as exc:
                return _block(record, 'build', 'conformer_generation_failed', str(exc), needs=[f'conformers.{role}'])
        else:
            return _block(
                record, "build", prepared.status,
                f"{role} ({smiles}) could not be built: {prepared.message}",
                atom_details=list(prepared.diagnostics),
                needs=[f"reaction.{role}_smiles"],
            )
        # 将构建身份直接带入分子；绑定时不再回读 prepared_structure.json。
        from rdkit import Chem
        heavy = [a.GetIdx() for a in Chem.MolFromSmiles(smiles).GetAtoms() if a.GetAtomicNum() != 1]
        for identity in prepared.atom_identities:
            value = identity.model_dump() if hasattr(identity, 'model_dump') else identity
            atom = seed_mol.GetAtomWithIdx(value['index'])
            identity = (f"in:{value['input_atom_index']}" if value['origin'] == 'input_atom' else f"in:{value['parent_input_atom_index']}#H{value['hydrogen_ordinal']}")
            atom.SetProp('cloudra_atom_id', identity)
            atom.SetProp('cloudra_component_id', value['component_id'])
            if value.get('origin') == 'input_atom' and value.get('symbol') != 'H':
                atom.SetIntProp('cloudra_smiles_heavy_index', heavy.index(value['input_atom_index']))
        setattr(record.structures, role, seed_mol)
        record.evidence_candidates.extend([seed_path, mol_path, prepared.artifact_path])
        if source.optimization is not None:
            record = _optimize_conformer_source(record, role)
            if record.blocked or record.waiting_for:
                return record
    guidance_warnings = []
    if guidance.ring_order or guidance.distance_filters:
        try:
            from cloudra.tools.core.preorganization import qualify_geometry
            plan, graph = _seed_guidance_plan(record)
            built = _read_built_xyz(record, 'reactant')
            passed, reasons, _, guidance_warnings = qualify_geometry(plan, graph, built[0], built[1])
            if not passed:
                raise ValueError('; '.join([*reasons, *guidance_warnings]))
        except (ValueError, OSError) as exc:
            return _block(record, 'build', 'seed_guidance_failed', str(exc), needs=['conformers.reactant', 'conformers.guidance'])
    detail = "both endpoints built" if len(endpoints) == 2 else (
        "first endpoint built; the second endpoint is derived from it by the declared rotation"
    )
    if guidance_warnings:
        detail += '\n' + '\n'.join(guidance_warnings)
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
    components = [Chem.Mol(component.mol) for component in prepared.components]
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
        graph = with_positions(graph, placement.positions)
    symbols = [atom.GetSymbol() for atom in graph.GetAtoms()]
    if symbols != prepared.symbols:
        raise ValueError('Generated seed changed the prepared atom identity order')
    xyz = to_xyz(graph)
    xyz_path, mol_path = str(Path(directory) / 'generated_seed.xyz'), str(Path(directory) / 'generated_seed.mol')
    _write_immutable_input(xyz_path, xyz)
    _write_immutable_input(mol_path, Chem.MolToMolBlock(graph))
    return xyz_path, mol_path, graph

def _seed_guidance_plan(record):
    """Use existing qualification and ring fallback on the actual bound graph."""
    from cloudra.tools.core.complex_assembly import AssemblyParameters
    from cloudra.tools.core.preorganization import DistanceWindow, GuidancePlan
    built = _read_built_xyz(record, 'reactant')
    if built is None:
        raise ValueError('Guidance requires the bound reactant MOL graph; supply conformers.reactant.mol_path')
    graph = _bound_input_structure(record, 'reactant', require_identity=False)[1]
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
    if calculation.engine == 'xtb' and _xtb_state_checkpoint(record, 'build', f'conformers.{role}.optimization'):
        return record
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
        setattr(record.structures, role, with_positions(getattr(record.structures, role), result['positions']))
        return record
    if step is None:
        if calculation.engine == 'xtb':
            if calculation.method != 'GFN2-xTB' or calculation.keywords:
                return _block(record, 'build', 'unsupported_calculation', 'Native seed optimization supports explicitly declared GFN2-xTB with empty keywords; use a prepared external seed for other native settings.', needs=[f'conformers.{role}.optimization'])
            manifest = directory / 'seed-opt.json'
            task = ChemTask(task='xtb_opt', reactant_xyz=Path(built[2]).read_text(),
                charge=record.input.reaction.charge, multiplicity=record.input.reaction.multiplicity,
                electronic_character=record.input.reaction.electronic_character, cpus=record.compute_cpus)
            _write_immutable_input(str(manifest), task.model_dump_json())
            job_type = 'chem_task'
        else:
            if calculation.engine == 'gaussian':
                opt_subopts, rem_keywords, warn = _extract_gaussian_opt_keywords(calculation.keywords, is_ts=False)
                task_type = [{'opt': opt_subopts}]
                calc_copy = calculation.model_copy(update={'keywords': rem_keywords or ''})
            else:
                task_type = [{'opt': None}]
                calc_copy = calculation
            manifest = directory / ('seed-opt.inp' if calculation.engine == 'orca' else 'seed-opt.gjf')
            request = QmInputWriter_input_schema(**calc_copy.model_dump(mode='json'),
                source_type='xyz_file', source_value=built[2], task_type=task_type,
                nproc=record.compute_cpus, mem=f'{record.compute_memory_mb}MB', output_path=str(manifest),
                charge=record.input.reaction.charge, multiplicity=record.input.reaction.multiplicity,
                electronic_character=record.input.reaction.electronic_character)
            from cloudra.tools.core.calculation_intent import validate_writer_request
            conflicts = validate_writer_request(request.model_dump())
            if conflicts:
                return _block(record, 'build', 'conformer_input_invalid', str(conflicts), needs=[f'conformers.{role}.optimization'])
            molecule = getattr(record.structures, role)
            content = QmInputWriter.render_input(request, molecule)
            _write_immutable_input(str(manifest), content)
            job_type = calculation.engine
        error, job = _submit_step(record, purpose, str(manifest), job_type)
        if error:
            return _block(record, 'build', 'conformer_admission_failed', error, needs=[f'conformers.{role}.optimization'])
        step = TsJobStep(purpose=purpose, job_id=job, input_path=str(manifest), state='ready', actual_calculation=calculation, source_input_revision=record.declaration_revision, atom_binding=_direction_atom_binding(record))
        record.job_steps.append(step)
    step.state = _step_state(record, step)
    if step.state not in TERMINAL_STATES:
        record.waiting_for = f'job:{step.job_id}'
        return record
    record.waiting_for = ''
    recovery = (
        f'Use ts_resume to revise changes.conformers.{role}, or retry the same requested optimization with changes={{}}. '
        f'To keep the imported seed without build pre-optimization, submit changes.conformers.{role} '
        'with {"optimization": null}; the existing source and proven identity are retained. '
        'Later TS/IRC and endpoint verification remain required.'
    )
    if step.state != 'done':
        _record_candidate_failure(record, 'conformer_optimization_failed', step, _refinement_log_path(record, step))
        return _block(record, 'build', 'conformer_optimization_failed', f'{purpose} job {step.job_id} failed. {recovery}', needs=[f'conformers.{role}'])
    if calculation.engine == 'xtb':
        data, _ = read_task_result(step.input_path)
        result = data['result']
        if not (result.get('normal_termination') is True and result.get('optimization_converged') is True):
            _record_candidate_failure(record, 'nonconvergence', step, step.input_path)
            return _block(record, 'build', 'conformer_optimization_failed', f'Seed optimization has no converged native evidence. {recovery}', needs=[f'conformers.{role}'])
        xyz = Path(result['optimized_xyz']).read_text()
    else:
        xyz, error = _endpoint_opt_frame(record, step)
        if error:
            _record_candidate_failure(record, 'nonconvergence', step, _refinement_log_path(record, step))
            return _block(record, 'build', 'conformer_optimization_failed', f'{error} {recovery}', needs=[f'conformers.{role}'])
    target = str(directory / 'optimized_seed.xyz')
    _write_immutable_input(target, xyz)
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    optimized_atoms = read_xyz_atoms(target)
    if [s for s, _ in optimized_atoms] != built[0]:
        return _block(record, 'build', 'conformer_identity_mismatch', 'Optimized seed changed the atom order.', needs=[f'conformers.{role}'])
    setattr(record.structures, role, with_positions(getattr(record.structures, role), [point for _, point in optimized_atoms]))
    return record

def _active_reaction_center(record: TsProcessRecord) -> list[tuple[int, int]]:
    center = list(record.input.reaction.reaction_center)
    guidance = record.input.conformers.guidance
    if guidance.ring_order or guidance.distance_filters:
        plan, _ = _seed_guidance_plan(record)
        center = list(dict.fromkeys([*center, *plan.forming_pairs]))
    return center


def _read_built_xyz(record: TsProcessRecord, role: str):
    """执行边界的文件视图；没有目录猜测、原始文件回读或平行结构缓存。"""
    mol = getattr(record.structures, role)
    if mol is None:
        return None
    xyz, graph = export_structure(record, role)
    return ([atom.GetSymbol() for atom in mol.GetAtoms()],
            mol.GetConformer().GetPositions().tolist(), xyz, graph)

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
    mol = record.structures.reactant
    if mol is None and not mol_path:
        return (
            "the built endpoint's MOL file is missing, so the bond to rotate about cannot be "
            "identified from the real bond graph",
            [],
        )
    if mol is None:
        mol = read_molecule(mol_path, input_format='mol')
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


def _bound_input_structure(record, role, *, require_identity=True):
    """读取当前分子，必要时确认声明身份；不再从导出文件重建状态。"""
    from cloudra.tools.Chemtool.reaction_mapping import _identity_and_binding
    mol = getattr(record.structures, role)
    if mol is None:
        raise ValueError(f'{role} concrete geometry is missing')
    smiles = getattr(record.input.reaction, role + '_smiles')
    from rdkit import Chem

    from cloudra.tools.core.electronic_state import electronic_state_issue
    reaction = record.input.reaction
    for graph in (Chem.MolFromSmiles(smiles), mol):
        if graph is None:
            raise ValueError(f'{role}: declared SMILES cannot be parsed')
        issue = electronic_state_issue(graph, charge=reaction.charge, multiplicity=reaction.multiplicity,
            electronic_character=reaction.electronic_character)
        if issue:
            raise ValueError(f'{role}: {issue[1]}')
    if require_identity:
        identity, binding, diagnostic = _identity_and_binding(smiles, mol,
            [i - 1 for i in heavy_binding(mol)] or None)
        if identity != 'match':
            raise ValueError(f'{role}: {diagnostic or identity}')
    return smiles, mol, {}


def _direction_atom_binding(record: TsProcessRecord) -> dict | None:
    """把当前结构和对应冻结到作业证据；历史不依赖以后修改的状态。"""
    import hashlib

    from rdkit import Chem
    if record.structures.product_to_reactant is None:
        return None
    record.structures.complete_correspondence()
    frequency = next((step for step in reversed(record.job_steps) if step.purpose == 'frequency'), None)
    log = Path(_refinement_log_path(record, frequency)) if frequency else None
    return dict(process_id=record.pipeline_id, declaration_revision=record.declaration_revision,
        atom_map=[i + 1 for i in record.structures.product_to_reactant], charge=record.input.reaction.charge,
        ts_log_sha256=hashlib.sha256(log.read_bytes()).hexdigest() if log and log.is_file() else None,
        reactant_mol=Chem.MolToMolBlock(record.structures.reactant),
        product_mol=Chem.MolToMolBlock(record.structures.product))


def _bind_structures(record: TsProcessRecord) -> TsProcessRecord:
    from cloudra.tools.Chemtool.reaction_mapping import bind_reaction_structures
    try:
        if record.structures.product_to_reactant is not None:
            record.structures.complete_correspondence()
            return record
        result = bind_reaction_structures(record.input, record.structures.reactant, record.structures.product)
        if result.get('binding_status') != 'complete':
            diagnostics = result.get('binding_diagnostics', [])
            candidates = result.get('candidates', [])
            issues, needs = [], []
            if candidates:
                needs = ['reaction.selected_candidate']
                issues.append(dict(code='concrete_mapping_ambiguous', field=needs[0], candidates=candidates))
            else:
                for role in ('reactant', 'product'):
                    identity = result.get(role + '_identity')
                    details = [item for item in diagnostics if item.startswith(role + ':')]
                    if identity == 'match' and not details:
                        continue
                    if identity == 'match' and result.get('heavy_atom_bindings', {}).get(role):
                        continue
                    # 结构错误应要求替换该端来源；不能让模型拿映射数组修补错误物种。
                    field = f'conformers.{role}'
                    needs.append(field)
                    if identity == 'mismatch':
                        needs.append(f'reaction.{role}_smiles')
                    issues.append(dict(code='endpoint_identity_mismatch' if identity == 'mismatch' else 'endpoint_binding_unconfirmed',
                        field=field, role=role, details=details))
            return _block(record, 'map', 'input_identity_unconfirmed',
                '; '.join(diagnostics) or 'Concrete endpoint correspondence requires a candidate selection.',
                atom_details=_endpoint_numbering(record), needs=needs or ['conformers'], issues=issues)
        for role, indices in result.get('heavy_atom_bindings', {}).items():
            molecule = getattr(record.structures, role)
            derived = not heavy_binding(molecule) or (molecule.HasProp('cloudra_mapping_binding_derived') and molecule.GetBoolProp('cloudra_mapping_binding_derived'))
            bound = set_heavy_binding(molecule, indices)
            # 记录来源，不把上一次选择反过来当作分子固有身份，缩窄下次候选。
            if derived:
                bound.SetBoolProp('cloudra_mapping_binding_derived', True)
            setattr(record.structures, role, bound)
        record.structures.product_to_reactant = tuple(index - 1 for index in result['atom_map'])
        record.structures.complete_correspondence()
    except (ValueError, OSError) as exc:
        return _block(record, 'map', 'input_identity_unconfirmed', str(exc), needs=['conformers', 'reaction.selected_candidate'])
    return record


def _map(record: TsProcessRecord) -> TsProcessRecord:
    """程序维护具体原子对应；只有真实歧义才要求研究选择。"""
    if _rotated_product(record) is not None:
        built = _read_built_xyz(record, 'reactant')
        if built is None:
            return _block(record, 'map', 'missing_built_geometry', 'The first endpoint is missing.', needs=['conformers.reactant'])
        error, positions = _derive_product_geometry(record, built)
        if error:
            return _block(record, 'map', 'product_geometry_failed', error, needs=['conformers.product'])
        record.structures.product = with_positions(record.structures.reactant, positions)
        try:
            # 构造保证同序，仍须证明实际分子确实是声明的物种和电子态。
            for role in ('reactant', 'product'):
                _bound_input_structure(record, role)
        except (ValueError, OSError) as exc:
            record.structures.product_to_reactant = None
            return _block(record, 'map', 'input_identity_unconfirmed', str(exc),
                needs=['conformers.reactant', 'reaction.reactant_smiles', 'reaction.product_smiles'])
        # 同一个分子经过显式旋转，原子身份由构造保证。
        record.structures.product_to_reactant = tuple(range(record.structures.reactant.GetNumAtoms()))
    left, right = record.structures.reactant, record.structures.product
    if left is not None and right is not None and left.GetNumAtoms() != right.GetNumAtoms():
        return _block(record, 'map', 'atom_count_mismatch', 'Endpoint atom counts differ; a path requires the same atom set.',
            atom_details=[f"reactant: {[a.GetSymbol() for a in left.GetAtoms()]}",
                          f"product: {[a.GetSymbol() for a in right.GetAtoms()]}"],
            needs=['reaction.reactant_smiles', 'reaction.product_smiles'])
    record = _bind_structures(record)
    if not record.blocked:
        _record_stage(record, 'map', 'done', 'Concrete endpoint correspondence confirmed and owned by this reaction.')
    return record

def _assemble(record: TsProcessRecord) -> TsProcessRecord:
    """反应中心引导的组装。组装本身在 build 阶段由 structure_builder 完成，这里只核对声明。"""
    # 组装只对**多组分**体系有意义：单组分（分子内重排、阻转异构、环翻转）没有片间取向可采样，
    # 因此不要求 reaction_center——这是"反应中心"这个概念本身不适用，不是调用方漏填
    from rdkit import Chem
    mol = record.structures.reactant
    if mol is None:
        return _block(record, 'assemble', 'missing_component_identity',
            'Reactant molecular identity is unavailable.', needs=['conformers.reactant'])
    components = len(Chem.GetMolFrags(mol))
    identities = [dict(index=atom.GetIdx(), symbol=atom.GetSymbol()) for atom in mol.GetAtoms()]
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

def _accept_candidate(record, path):
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    atoms = read_xyz_atoms(path)
    reference = record.structures.reactant
    if reference is None or [a.GetSymbol() for a in reference.GetAtoms()] != [symbol for symbol, _ in atoms]:
        raise ValueError('Candidate atom identity/order differs from the owned reactant')
    record.structures.candidate = with_positions(reference, [point for _, point in atoms])


def _guess_scan(record: TsProcessRecord) -> TsProcessRecord:
    """Advance a declared scan via the same job ledger and parser as manual scans."""
    import math

    from cloudra.services.compute_store import TERMINAL_STATES
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    declaration = record.input.reaction
    calculation = stage_calculation(record, 'scan')
    plan = record.input.guess.model_copy(update={'calculation': calculation})
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
        if calculation.engine == 'xtb':
            from cloudra.runtime.chem_task import ChemTask
            input_path = str(folder / 'scan-task.json')
            task = ChemTask(task='xtb_scan', reactant_xyz=Path(built[2]).read_text(),
                charge=declaration.charge, multiplicity=declaration.multiplicity,
                electronic_character=declaration.electronic_character, cpus=record.compute_cpus, scan=plan)
            _write_immutable_input(input_path, task.model_dump_json())
            job_type = 'chem_task'
        else:
            base = atom_index_base(calculation.engine)
            def public_rows(rows):
                return [dict(row.model_dump(), atoms=[i + base for i in row.atoms]) for row in rows]
            request = TsGuess_input_schema(
                mode="scan_prepare", input_path=built[2], **calculation.model_dump(mode='json'),
                charge=declaration.charge, multiplicity=declaration.multiplicity,
                electronic_character=declaration.electronic_character,
                scans=public_rows(plan.scans), freeze=public_rows(plan.freeze), scan_mode=plan.mode,
                output_path=str(folder / ("scan.inp" if calculation.engine == "orca" else "scan.gjf")),
                nproc=record.compute_cpus, mem=f'{record.compute_memory_mb}MB',
            )
            try:
                prepared = TsGuess()._scan_prepare(request)
            except ValueError as exc:
                return _block(record, "guess", "invalid_scan", str(exc), needs=["guess"])
            if not prepared.is_success:
                return _block(record, "guess", "invalid_scan", prepared.message, needs=["guess"])
            input_path = prepared.input_file_path
            job_type = calculation.engine
        error, job_id = _submit_step(record, "scan", input_path, job_type)
        if error:
            return _block(record, "guess", "compute_admission_rejected", error, needs=["guess"])
        record.scan_step = TsJobStep(purpose="scan", job_id=job_id, input_path=input_path, state="ready", actual_calculation=calculation, source_input_revision=record.declaration_revision, atom_binding=_direction_atom_binding(record))
        record.waiting_for = f"job:{job_id}"
        _record_stage(record, "guess", "waiting", f"Scan job {job_id} submitted; compute completion advances the system driver.", [input_path])
        return record
    step = record.scan_step
    step.state = _step_state(record, step)
    if step.state not in TERMINAL_STATES and step.state != "missing":
        record.waiting_for = f"job:{step.job_id}"
        return record
    record.waiting_for = ""
    if step.state != "done":
        log_path = _refinement_log_path(record, step)
        failure, details = _native_failure_details(log_path, calculation.engine)
        _record_candidate_failure(record, failure, step, log_path, details)
        return _block(
            record, "guess", "scan_job_failed",
            f"Scan job {step.job_id}: {step.state}. Inspect the native log, then revise "
            "the scan inputs or retry with ts_resume; the previous attempt remains recorded.",
            atom_details=details, needs=["compute_artifacts"],
        )
    target = str(Path(step.input_path).parent / "scan_peak.xyz")
    if calculation.engine == 'xtb':
        from cloudra.runtime.chem_task import read_task_result
        try:
            result = read_task_result(step.input_path)[0]['result']
        except (ValueError, OSError, KeyError) as exc:
            return _block(record, 'guess', 'scan_artifacts_incomplete', str(exc), needs=['compute_artifacts'])
        if result['scan_status'] != 'complete':
            _record_candidate_failure(record, 'scan_artifacts_incomplete', step, result['log_file'])
            return _block(record, 'guess', 'scan_artifacts_incomplete',
                'Native xTB scan has incomplete point convergence or artifacts.',
                atom_details=result.get('issues', []), needs=['compute_artifacts'])
        if len(result.get('candidates', [])) > 1:
            points = {point['index']: point for point in result['points']}
            details = [f"Candidate point {candidate['point_index']}: energy={points[candidate['point_index']]['energy_hartree']:.12f} Hartree; XYZ={candidate['frame_path']}"
                       for candidate in result['candidates']]
            return _block(record, 'guess', 'scan_choice_required',
                f"Multiple internal local-peak candidates. Choose one with guess.kind=provided; formal validation remains required. Native log: {result['log_file']}",
                atom_details=details, needs=['guess'])
        if not result['usable_as_guess'] or not result.get('candidate_path'):
            _record_candidate_failure(record, 'scan_no_candidate', step, result['log_file'])
            return _block(record, 'guess', 'scan_no_candidate',
                'Native xTB scan completed but has no unique internal-peak candidate; inspect the point evidence.',
                atom_details=[str(item) for item in result.get('candidates', [])], needs=['guess'])
        target = result['candidate_path']
    else:
        try:
            parsed = TsGuess()._scan_parse(TsGuess_input_schema(
                mode="scan_parse", engine=_step_calculation(record, step).engine,
                log_path=_refinement_log_path(record, step), ts_candidate_path=target,
            ))
        except (ValueError, OSError) as exc:
            _record_candidate_failure(record, "scan_parse_failed", step, _refinement_log_path(record, step))
            return _block(record, "guess", "scan_parse_failed", str(exc), needs=["guess"])
        if (parsed.scan_has_internal_peak is True and not parsed.candidate_unavailable
                and not parsed.ts_candidate_path):
            return _block(record, 'guess', 'scan_choice_required',
                parsed.message + f" Native log: {_refinement_log_path(record, step)}",
                atom_details=parsed.verdicts, needs=['guess'])
        if (not parsed.is_success or parsed.scan_has_internal_peak is not True
                or parsed.candidate_unavailable or not parsed.ts_candidate_path
                or not Path(parsed.ts_candidate_path).is_file()):
            _record_candidate_failure(record, "scan_no_candidate", step, _refinement_log_path(record, step))
            return _block(record, "guess", "scan_no_candidate",
                          "Scan produced no usable internal-peak geometry. " + parsed.message,
                          atom_details=parsed.verdicts, needs=["guess"])
        target = parsed.ts_candidate_path
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    try:
        candidate_atoms = read_xyz_atoms(target)
        built = _read_built_xyz(record, "reactant")
        if built is None or [symbol for symbol, _ in candidate_atoms] != built[0]:
            raise ValueError("Scan peak atom identity/order differs from the assembled reactant")
        if not all(math.isfinite(value) for _, position in candidate_atoms for value in position):
            raise ValueError("Scan peak has nonfinite coordinates")
    except (ValueError, OSError) as exc:
        _record_candidate_failure(record, "scan_invalid_geometry", step, _refinement_log_path(record, step))
        return _block(record, "guess", "scan_invalid_geometry", str(exc), needs=["guess"])
    _accept_candidate(record, target)
    record.path_kind = "scan"
    record.evidence_candidates.extend([_refinement_log_path(record, step), target])
    _record_stage(record, "guess", "done", "Scan internal peak extracted; unconstrained refinement still required.", [target])
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
            electronic_character=record.input.reaction.electronic_character,
            solvation=record.input.guess.solvation.model_dump() if record.input.guess.solvation else None,
            refinement_runs=record.input.guess.refinement_runs)
        _write_immutable_input(path,task.model_dump_json())
        error,job = _submit_step(record, 'path', path, 'chem_task')
        if error:
            return None,_block(record,'guess','path_admission_failed',error,needs=['execution.compute_node','execution.limits'])
        step = TsJobStep(purpose='path',job_id=job,input_path=path,state='ready', actual_calculation=stage_calculation(record, 'path'), source_input_revision=record.declaration_revision, atom_binding=_direction_atom_binding(record))
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
    if record.structures.product_to_reactant is None:
        _bind_structures(record)
        if record.blocked:
            return record
    guess = record.input.guess
    if guess is None:
        return _block(record, 'guess', 'missing_input', 'Explicit guess source required', needs=['guess'])
    if guess.kind == 'xtb_path' and _xtb_state_checkpoint(record, 'guess', 'guess'):
        return record
    if guess.kind == 'provided':
        try:
            _verify_provided_guess_binding(record)
        except (OSError, ValueError) as exc:
            return _block(record, 'guess', 'provided_guess_artifact_changed', str(exc), needs=['guess'])
        try:
            import math

            from cloudra.tools.core.structure_artifacts import read_xyz_atoms
            binding = record.provided_guess_binding
            if binding is None:
                target = Path(record.run_dir) / PATH_STAGE_DIR / f'input_{record.declaration_revision:04d}'
                target.mkdir(parents=True, exist_ok=True)
                binding = TsProvidedGuessBinding(
                    xyz=_bind_provided_artifact(record, guess.xyz_path, target / 'provided.xyz'),
                    evidence=[_bind_provided_artifact(record, reference,
                        target / f'provenance_{index:04d}{Path(reference).suffix}')
                        for index, reference in enumerate(guess.evidence_refs)])
            candidate = Path(binding.xyz.snapshot_path)
            atoms = read_xyz_atoms(str(candidate))
            reactant = _read_built_xyz(record, 'reactant')
            if reactant is None or [s for s, _ in atoms] != reactant[0]:
                raise ValueError('Provided candidate atom identity/order differs from the bound reactant')
            if not all(math.isfinite(v) for _, point in atoms for v in point):
                raise ValueError('Provided candidate contains nonfinite coordinates')
        except (OSError, ValueError) as exc:
            return _block(record, 'guess', 'provided_guess_invalid', str(exc), needs=['guess'])
        _accept_candidate(record, str(candidate))
        record.provided_guess_binding = binding
        record.path_kind = 'provided'
        _record_stage(record, 'guess', 'done', 'Provided candidate bound; formal optimization and verification remain required.',
            [str(candidate), *[artifact.snapshot_path for artifact in binding.evidence]])
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
    record.structures.candidate = None
    os.makedirs(out_dir, exist_ok=True)

    try:
        reactant_mol, product_mol = path_endpoints(record.structures)
    except ValueError as exc:
        return _block(record, 'guess', 'input_identity_unconfirmed', str(exc), needs=['reaction.selected_candidate'])
    r_symbols = [a.GetSymbol() for a in reactant_mol.GetAtoms()]
    r_pos = reactant_mol.GetConformer().GetPositions().tolist()
    reordered = product_mol.GetConformer().GetPositions().tolist()

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
        electronic_character=record.input.reaction.electronic_character,
        run_label="guess",
        extra_args=(
            [f"--{guess.solvation.model}", guess.solvation.solvent]
            if guess.solvation else []
        ),
    )
    # An explicit cap overrides the runner default; a truncated path remains unverified.
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
            return _block(
                record, "guess", run.termination_reason, run.message,
                atom_details=list(run.diagnostics), needs=["guess"],
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
            f"Next step: ts_resume with changes.guess (kind=scan, calculation, scans, optional freeze) when one "
            f"forming/breaking bond or angle is clear (take the atom indices from "
            f"internal_coordinates first); (b) ts_guess mode='interpolate' (IDPP) — only when both "
            f"endpoint geometries and their internally confirmed correspondence are available. Either way the "
            f"result is a path/guess, not a saddle: an unconstrained OptTS with frequency and IRC "
            f"is still required.",
            atom_details=list(run.diagnostics),
            needs=["guess", "reaction.reaction_center", "reaction.selected_candidate", "reaction.reactant_smiles", "reaction.product_smiles"],
        )
    record.path_kind = "xtb_path"
    _accept_candidate(record, run.ts_xyz_path)
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
    if record.structures.candidate is not None:
        positions = np.asarray(record.structures.candidate.GetConformer().GetPositions())
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
                needs=["reaction.reaction_center", "reaction.selected_candidate"],
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
    declaration = record.input.reaction
    calculation = stage_calculation(record, 'ts_opt')
    if calculation is None:
        return 'Explicit ts_optimization calculation required', ''
    if record.structures.candidate is None:
        return 'no TS candidate was produced by the guess stage', ''
    source, _ = export_structure(record, 'candidate')

    input_name = REFINEMENT_INPUT_NAMES[calculation.engine]
    input_path = os.path.join(job_dir, input_name)
    # 引擎各自的原生 TS 写法由项目的 skill 规定（references/orca-inputs.md /
    # gaussian-inputs.md）。ORCA 用 `! OptTS`，初始 Hessian 走原生 %geom 块；
    # **频率是后续独立作业**（skill 的"Frequency and IRC follow-ups"），因此这里只写 TS 优化，
    # 频率/IRC 归 refine 阶段。若 skill 里的配方变了，改这里一处即可。
    if calculation.engine == "orca":
        task_type: list[dict] = [{"opt": "ts"}]
        orca_blocks: Optional[str] = "%geom\n  Calc_Hess true\nend"
        calc_copy = calculation.model_copy(update={'orca_blocks': '\n'.join(filter(None, [orca_blocks, calculation.orca_blocks])) or None})
    else:
        import warnings
        opt_subopts, rem_keywords, warn = _extract_gaussian_opt_keywords(calculation.keywords, is_ts=True)
        if warn:
            warnings.warn(warn, UserWarning, stacklevel=2)
        task_type = [{"opt": opt_subopts}]
        calc_copy = calculation.model_copy(update={'keywords': rem_keywords or ''})
    request = QmInputWriter_input_schema(
        **calc_copy.model_dump(mode='json'),
        nproc=record.compute_cpus,
        mem=f"{record.compute_memory_mb}MB",
        source_type="xyz_file",
        source_value=source,
        task_type=task_type,
        charge=declaration.charge,
        multiplicity=declaration.multiplicity,
        electronic_character=declaration.electronic_character,
        title=f"TS refinement: {declaration.reactant_smiles} -> {declaration.product_smiles} | smiles: {declaration.reactant_smiles}",
        output_path=input_path,
    )
    # 输入冲突前置校验（与 qm_input_writer 同一份）
    conflicts = validate_writer_request(request.model_dump())
    if conflicts:
        return "refinement input refused: " + " | ".join(
            f"[{c['code']}] {c['message']}" for c in conflicts
        ), ""

    content = QmInputWriter.render_input(request, record.structures.candidate)
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
    if record.structures.product_to_reactant is None:
        _bind_structures(record)
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
    atom_binding=_direction_atom_binding(record)))
    _record_stage(
        record, "submit", "done",
        f"refinement job {job_id} submitted as 'ready' ({job_type}, {calculation.method}); the "
        "scheduler daemon claims it and its terminal state arrives through the existing compute "
        "notification path",
        [input_path],
    )
    return record

class EndpointSource(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    kind: Literal['species_reference', 'irc_outer_frame']
    label: Literal['reactant', 'product', 'A', 'B']
    source_path: str
    sha256: str
    irc_job_id: int | None = None
    irc_log_sha256: str | None = None

    @model_validator(mode='after')
    def source_contract(self):
        if self.kind == 'species_reference' and self.label not in {'reactant', 'product'}:
            raise ValueError('Species reference requires its declared species role.')
        if self.kind == 'irc_outer_frame' and (self.label not in {'A', 'B'} or
            self.irc_job_id is None or not self.irc_log_sha256):
            raise ValueError('IRC outer-frame source requires side, accepted job and log digest.')
        return self

class TsJobStep(BaseModel):
    """精修作业序列里的一步（TS、IRC 与两端极小值验证）。"""

    purpose: Literal[
        "sampling", "path", "candidate_opt", "candidate_evaluation", "product_seed_opt", "scan", "ts_opt", "frequency", "irc", "reactant_opt", "reactant_frequency",
        "product_opt", "product_frequency",
    ]
    job_id: Optional[int] = None
    input_path: str = ""
    state: str = Field(default="", description="compute_jobs 里的状态；终态见 TERMINAL_STATES")
    actual_calculation: QmCalculation | None = None
    source_input_revision: int = 1
    method_contract: dict | None = None
    stage_key: str | None = None
    external_source: dict | None = None
    endpoint_source: EndpointSource | None = None
    atom_binding: dict | None = None
    frequency_analysis: dict | None = None


def _record_frequency_analysis(record, step, log_path, snapshot):
    """记录虚频的运动组成，供 Agent 判断；不另设科学合格阈值。"""
    from cloudra.tools.Chemtool.ts_guess import _assess_imag_mode_alignment, _parse_freq_log
    from cloudra.tools.core.mode_analysis import imaginary_mode_summaries_from_text

    if step.frequency_analysis is not None:
        return
    path = Path(log_path)
    pairs = [[left + 1, right + 1] for left, right in _active_reaction_center(record)]
    frequencies = snapshot.frequencies or snapshot.imaginary_frequencies or []
    engine = _step_calculation(record, step).engine
    try:
        parsed = _parse_freq_log(str(path), engine)
    except ValueError as exc:
        alignment = dict(status='missing', aligned=None, message=str(exc), details=[])
    else:
        alignment = _assess_imag_mode_alignment(
            parsed['vibfreqs'], parsed['vibdisps'], pairs,
            symbols=parsed.get('symbols'), positions=parsed.get('positions'),
            charge=(step.atom_binding or {}).get('charge', record.input.reaction.charge),
            index_base=1,
        )
    step.frequency_analysis = dict(
        log_path=str(path), log_sha256=_artifact_sha256(path), reaction_center_pairs=pairs,
        fraction_basis='unweighted_squared_displacement',
        modes=imaginary_mode_summaries_from_text(
            engine, path.read_text(errors='replace'), frequencies, pairs),
        mode_alignment=alignment,
    )

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
    from cloudra.tools.Chemtool.ts_guess import TsGuess
    from cloudra.tools.core import gaussian_frames, orca_frames
    from cloudra.tools.core.calculation_intent import inspect_input, native_input_geometry
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    source_log = _workspace_input_path(record, record.input.verification.irc_log)
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
    info = TsGuess._extract_irc_endpoints(str(source_log), checks, engine=engine,
        output_dir=str(Path(_job_directory(record, 'irc')) / 'source_endpoints'), require_two_sides=True)
    if info is None or not all(info.get(key) and Path(info[key]).is_file() for key in ('path_a', 'path_b')):
        raise ValueError('Existing IRC has no usable two-sided endpoint evidence: ' + '; '.join(checks))
    directory = Path(_job_directory(record, 'irc'))
    directory.mkdir(parents=True, exist_ok=True)
    native_path = str(directory / ('existing.inp' if engine == 'orca' else 'existing.gjf'))
    log_path = str(directory / 'existing.log')
    _write_immutable_input(native_path, text)
    _write_immutable_input(log_path, source_log.read_text())
    facts = dict(source_job_id=job, source_input=str(source_input), source_log=str(source_log),
        log_path=log_path, frequency_input=frequency.input_path, atom_binding=_direction_atom_binding(record),
        artifact_hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (native_path, log_path)})
    record.method_checks[native_path] = record.method_checks[str(source_input)]
    return TsJobStep(purpose='irc', state='done', input_path=native_path, actual_calculation=stage_calculation(record, 'irc'),
        source_input_revision=record.declaration_revision, stage_key='external:irc', external_source=facts, atom_binding=_direction_atom_binding(record))

def _check_calculation_submission(record, purpose, input_path, job_type):
    from cloudra.runtime_v2.method_policy import check_input_content, check_method
    from cloudra.services.ts_pipeline_context import require_pipeline_authority
    from cloudra.tools.core.calculation_intent import compare_calculation_input
    policy = require_pipeline_authority(record.owner_conversation_id, record.owner_session_id)
    calculation = stage_calculation(record, purpose)
    if calculation is None:
        raise ValueError(f"{purpose} has no explicit calculation")
    content = Path(input_path).read_text()
    if policy is not None:
        verdict = (check_method(calculation.method, policy) if job_type == 'chem_task' else
            check_input_content(content, policy, filename=input_path, strict=True))
        if not verdict.allowed:
            raise ValueError(verdict.reason)
    if job_type == 'chem_task':
        from cloudra.runtime.chem_task import ChemTask
        task = ChemTask.model_validate_json(content)
        expected_task = dict(path='xtb_path', scan='xtb_scan', candidate_opt='xtb_opt', product_seed_opt='xtb_opt')
        allowed_tasks = {'xtb_gradient', 'xtb_hessian'} if purpose == 'candidate_evaluation' else {expected_task.get(purpose)}
        if calculation.engine != 'xtb' or calculation.method != 'GFN2-xTB' or calculation.keywords or calculation.orca_blocks or calculation.end_setting:
            raise ValueError('Native chemistry task contract supports explicit GFN2-xTB with no native ORCA/Gaussian directives')
        if _open_shell_singlet(record):
            raise ValueError('The native GFN task cannot represent the accepted open-shell singlet electronic state')
        if task.task not in allowed_tasks or (task.charge, task.multiplicity, task.electronic_character, task.cpus) != (record.input.reaction.charge, record.input.reaction.multiplicity, record.input.reaction.electronic_character, record.compute_cpus):
            raise ValueError('Native chemistry task/charge/multiplicity/electronic character/resources differ from accepted input')
        solvation = task.solvation.model_dump() if task.solvation else None
        expected_solvation = record.input.guess.solvation.model_dump() if purpose == 'path' and record.input.guess.solvation else None
        if solvation != expected_solvation:
            raise ValueError('Native task solvation differs from its own accepted stage input')
        if purpose == 'scan':
            plan = record.input.guess.model_copy(update={'calculation': calculation})
            if task.scan != plan or task.reactant_xyz != Path(_read_built_xyz(record, 'reactant')[2]).read_text():
                raise ValueError('Native scan declaration or bound XYZ differs from accepted input')
        contract = policy.calculation_contracts.get(purpose) if policy is not None else None
        if contract:
            actual = {**calculation.model_dump(mode='json'),
                'charge': task.charge, 'multiplicity': task.multiplicity, 'cpus': task.cpus,
                'scan': task.scan.model_dump(mode='json') if task.scan else None,
                'force_constant': task.scan.force_constant if task.scan else None,
                'mode': task.scan.mode if task.scan else None,
                'solvation': task.scan.solvation.model_dump(mode='json') if task.scan and task.scan.solvation else solvation}
            mismatched = [key for key, value in contract.items() if key not in actual or actual[key] != value]
            if mismatched:
                raise ValueError(f'Native task differs from trusted {purpose} calculation contract: {mismatched}')
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
        contract = policy.calculation_contracts.get(purpose) if policy is not None else None
        if contract:
            differences += compare_calculation_input(content, contract, charge=contract.get('charge', record.input.reaction.charge), multiplicity=contract.get('multiplicity', record.input.reaction.multiplicity))
    result = dict(input_revision=record.declaration_revision, purpose=purpose, actual=calculation.model_dump(),
        source='project_method_policy' if policy is not None else 'stage_declaration',
        differences=[d.model_dump() for d in differences], matched=not differences)
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
    if step.purpose == 'scan' and _step_calculation(record, step).engine == 'xtb':
        from cloudra.runtime.chem_task import read_task_result
        try:
            return read_task_result(step.input_path)[0]['result']['log_file']
        except (KeyError, OSError, ValueError):
            resolved = resolve_log_path(step.input_path, job_type='xtb', task_id=step.job_id)
            if Path(resolved).is_file() and Path(resolved).resolve() != Path(step.input_path).resolve():
                return resolved
            captured = Path(step.input_path).parent / '.cloudra' / f'calc-{step.job_id}.out.log'
            return str(captured) if captured.is_file() else ''
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
    declaration = record.input.reaction
    calculation = stage_calculation(record, 'frequency')
    if calculation is None:
        return 'Explicit verification.frequency required', ''
    input_path = os.path.join(job_dir, f"frequency.{'inp' if calculation.engine == 'orca' else 'gjf'}")
    if calculation.engine == "gaussian":
        import warnings
        freq_subopts, rem_keywords, warn = _extract_gaussian_freq_keywords(calculation.keywords)
        if warn:
            warnings.warn(warn, UserWarning, stacklevel=2)
        task_type = [{"freq": freq_subopts}]
        calc_copy = calculation.model_copy(update={'keywords': rem_keywords or ''})
    else:
        task_type = [{"freq": None}]
        calc_copy = calculation
    request = QmInputWriter_input_schema(
        **calc_copy.model_dump(mode='json'),
        nproc=record.compute_cpus,
        mem=f"{record.compute_memory_mb}MB",
        source_type="xyz_file",
        source_value=optimized_xyz,
        task_type=task_type,
        charge=declaration.charge,
        multiplicity=declaration.multiplicity,
        electronic_character=declaration.electronic_character,
        title=f"frequency at the refined stationary point: {declaration.reactant_smiles} | smiles: {declaration.reactant_smiles}",
        output_path=input_path,
    )
    conflicts = validate_writer_request(request.model_dump())
    if conflicts:
        return "frequency input refused: " + " | ".join(
            f"[{c['code']}] {c['message']}" for c in conflicts
        ), ""
    content = QmInputWriter.render_input(request, read_molecule(optimized_xyz, charge=declaration.charge))
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


def _extract_gaussian_opt_keywords(keywords: str | None, *, is_ts: bool = True) -> tuple[str | None, str, str | None]:
    """从关键字中解析 Gaussian 的 opt 子参数，剥离 opt 后的其余关键字，并校验/补充必要参数。

    - is_ts=True: 用于过渡态优化阶段。默认确保包含 ts, calcfc, noeigen；若用户指定了 opt 但遗漏关键选项，则补充并返回警告。
    - is_ts=False: 用于极小值（端点/种子）优化阶段。若用户指定了 opt 则提取其子参数（无子参数返回 None 表示裸 opt），未指定 opt 返回 None。

    返回: (opt_suboptions, remaining_keywords, warning_message)
    严格遵守 AGENTS.md 规范：不使用正则表达式 (re)，采用显式 token 与字符串拆分。
    """
    if not keywords or not keywords.strip():
        if is_ts:
            return "TS,calcfc,noeigen", "", None
        return None, "", None

    from cloudra.tools.core.calculation_intent import native_tokens

    try:
        tokens = native_tokens(keywords)
    except ValueError:
        tokens = keywords.split()

    opt_subopts: list[str] = []
    other_tokens: list[str] = []
    found_opt = False

    for raw_token in tokens:
        token = raw_token.strip().rstrip(",")
        if not token:
            continue
        token_lower = token.lower()
        if token_lower == "opt" or token_lower.startswith("opt=") or token_lower.startswith("opt("):
            found_opt = True
            if token_lower.startswith("opt="):
                val = token[4:].strip()
            elif token_lower.startswith("opt("):
                val = token[3:].strip()
            else:
                val = ""
            if val.startswith("(") and val.endswith(")"):
                val = val[1:-1].strip()
            if val:
                for sub in val.split(","):
                    s = sub.strip()
                    if s:
                        opt_subopts.append(s)
        else:
            other_tokens.append(token)

    warning = None
    if is_ts:
        if found_opt:
            has_ts = any(s.lower() in ("ts", "qst2", "qst3") for s in opt_subopts)
            has_fc = any(s.lower() in ("calcfc", "rcfc", "readfc", "calcall") for s in opt_subopts)
            if not has_ts:
                opt_subopts.insert(0, "ts")
                warning = (
                    "Gaussian TS optimization requires 'ts'. "
                    "Automatically prepended 'ts' to opt suboptions; "
                    "please declare 'ts' explicitly in 'keywords' (e.g., opt=(ts,...))."
                )
            if not has_fc:
                idx = 1 if opt_subopts and opt_subopts[0].lower() in ("ts", "qst2", "qst3") else 0
                opt_subopts.insert(idx, "calcfc")
                if warning:
                    warning += " Also added 'calcfc' because Gaussian Berny TS optimization requires initial force constants."
                else:
                    warning = (
                        "Gaussian TS optimization requires force constants ('calcfc'). "
                        "Automatically added 'calcfc' to opt suboptions; "
                        "please declare 'calcfc' explicitly in 'keywords' (e.g., opt=(ts,calcfc,...))."
                    )
            if not any(s.lower() == "noeigen" for s in opt_subopts):
                opt_subopts.append("noeigen")
        else:
            opt_subopts = ["TS", "calcfc", "noeigen"]
        return ",".join(opt_subopts), " ".join(other_tokens), warning
    else:
        if found_opt:
            sub = ",".join(opt_subopts) if opt_subopts else None
            return sub, " ".join(other_tokens), None
        return None, " ".join(other_tokens), None


def _extract_gaussian_freq_keywords(keywords: str | None) -> tuple[str | None, str, str | None]:
    """从关键字中解析 Gaussian 的 freq 子参数，并返回剥离了 freq 后的其余关键字。

    返回: (freq_suboptions, remaining_keywords, warning_message)
    严格遵守 AGENTS.md 规范：不使用正则表达式 (re)，采用显式 token 与字符串拆分。
    """
    if not keywords or not keywords.strip():
        return None, "", None

    from cloudra.tools.core.calculation_intent import native_tokens

    try:
        tokens = native_tokens(keywords)
    except ValueError:
        tokens = keywords.split()

    freq_subopts: list[str] = []
    other_tokens: list[str] = []
    found_freq = False

    for raw_token in tokens:
        token = raw_token.strip().rstrip(",")
        if not token:
            continue
        token_lower = token.lower()
        if token_lower == "freq" or token_lower.startswith("freq=") or token_lower.startswith("freq("):
            found_freq = True
            if token_lower.startswith("freq="):
                val = token[5:].strip()
            elif token_lower.startswith("freq("):
                val = token[4:].strip()
            else:
                val = ""
            if val.startswith("(") and val.endswith(")"):
                val = val[1:-1].strip()
            if val:
                for sub in val.split(","):
                    s = sub.strip()
                    if s:
                        freq_subopts.append(s)
        else:
            other_tokens.append(token)

    if found_freq:
        sub = ",".join(freq_subopts) if freq_subopts else None
        return sub, " ".join(other_tokens), None
    return None, " ".join(other_tokens), None


def _extract_gaussian_irc_keywords(keywords: str | None) -> tuple[str, str, str | None]:
    """从关键字中解析 Gaussian 的 IRC 子参数，确保包含 calcfc，并返回剥离了 irc 后的其余关键字。

    返回: (irc_suboptions, remaining_keywords, warning_message)
    严格遵守 AGENTS.md 规范：不使用正则表达式 (re)，采用显式 token 与字符串拆分。
    """
    if not keywords or not keywords.strip():
        return "calcfc", "", None

    from cloudra.tools.core.calculation_intent import native_tokens

    try:
        tokens = native_tokens(keywords)
    except ValueError:
        tokens = keywords.split()

    irc_subopts: list[str] = []
    other_tokens: list[str] = []
    found_irc = False

    for raw_token in tokens:
        token = raw_token.strip().rstrip(",")
        if not token:
            continue
        token_lower = token.lower()
        if token_lower == "irc" or token_lower.startswith("irc=") or token_lower.startswith("irc("):
            found_irc = True
            if token_lower.startswith("irc="):
                val = token[4:].strip()
            elif token_lower.startswith("irc("):
                val = token[3:].strip()
            else:
                val = ""
            if val.startswith("(") and val.endswith(")"):
                val = val[1:-1].strip()
            if val:
                for sub in val.split(","):
                    s = sub.strip()
                    if s:
                        irc_subopts.append(s)
        elif any(token_lower.startswith(prefix) for prefix in ("maxpoints=", "stepsize=", "recalc=")):
            found_irc = True
            for sub in token.split(","):
                s = sub.strip()
                if s:
                    irc_subopts.append(s)
        else:
            other_tokens.append(token)

    warning = None
    if found_irc:
        has_calcfc = any(s.lower() == "calcfc" for s in irc_subopts)
        if not has_calcfc:
            irc_subopts.insert(0, "calcfc")
            warning = (
                "Gaussian IRC requires initial force constants ('calcfc'). "
                "Automatically prepended 'calcfc' to IRC suboptions; "
                "please declare 'calcfc' explicitly in 'keywords' (e.g., irc=(calcfc,...))."
            )
    else:
        irc_subopts = ["calcfc"]

    return ",".join(irc_subopts), " ".join(other_tokens), warning


def _write_irc_input(record: TsProcessRecord, job_dir: str) -> tuple[str, str]:
    """写 IRC 作业输入；返回 ``(错误, 输入路径)``。

    几何与频率作业**同一帧**（TS 优化末帧）——skill 要求"reuse its same-geometry frequency
    Hessian for both IRC directions"。两个引擎的原生写法照
    ``references/{orca,gaussian}-inputs.md``：

    - Gaussian：``task_type=[{"irc": irc_subopts}]``（根据用户输入解析或默认 calcfc）。
    - ORCA：``task_type=[{"irc": None}]`` + 原生 ``%irc`` 块。Hessian 走哪个分支由**证据**决定，
      不是偏好：频率作业真的落下了同名 ``.hess`` 就用 ``InitHess read`` + ``Hess_Filename``；
      没有就按 skill 说的 ``InitHess calc_numfreq``（数值评估），绝不默认请求解析外部 Hessian。
    """
    import warnings

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
        clean_keywords = calculation.keywords
    else:
        irc_subopts, clean_keywords, warning = _extract_gaussian_irc_keywords(calculation.keywords)
        if warning:
            warnings.warn(warning, UserWarning)
        task_type = [{"irc": irc_subopts}]
        orca_blocks = None

    request = QmInputWriter_input_schema(
        **calculation.model_copy(update={
            'orca_blocks': '\n'.join(filter(None, [orca_blocks, calculation.orca_blocks])) or None,
            'keywords': clean_keywords,
        }).model_dump(mode='json'),
        nproc=record.compute_cpus,
        mem=f"{record.compute_memory_mb}MB",
        source_type="xyz_file",
        source_value=geometry,
        task_type=task_type,
        charge=declaration.charge,
        multiplicity=declaration.multiplicity,
        electronic_character=declaration.electronic_character,
        title=f"IRC both directions from the refined saddle: {declaration.reactant_smiles} | smiles: {declaration.reactant_smiles}",
        output_path=input_path,
    )
    conflicts = validate_writer_request(request.model_dump())
    if conflicts:
        return "IRC input refused: " + " | ".join(
            f"[{c['code']}] {c['message']}" for c in conflicts
        ), ""
    content = QmInputWriter.render_input(request, read_molecule(geometry, charge=declaration.charge))
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


def _endpoint_seed_atoms(record: TsProcessRecord, role: str, seed):
    """Normalize a species-order seed; native IRC files already use TS order."""
    from rdkit import Chem

    from cloudra.tools.core import gaussian_frames, orca_frames
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    path = _workspace_input_path(record, seed.xyz_path)
    atoms = read_xyz_atoms(path)

    for step in reversed(record.job_steps):
        if step.purpose != 'irc' or step.state != 'done':
            continue
        log = _refinement_log_path(record, step)
        if _step_calculation(record, step).engine == 'orca':
            endpoints = orca_frames.extract_irc_endpoints(log)
            for item in endpoints.values():
                if item.get('geometry_ref') and Path(item['geometry_ref']).resolve() == path:
                    from cloudra.tools.core.irc_path import parse_xyz
                    geometry = parse_xyz(orca_frames.read_endpoint_geometry(item) or '')
                    if geometry is None:
                        raise ValueError('native IRC endpoint geometry is unreadable')
                    return list(zip(*geometry))
        else:
            from cloudra.tools.core.irc_path import parse_xyz
            frames, _ = gaussian_frames.extract_irc(log)
            valid = [frame for frame in frames if frame.xyz and frame.reaction_coordinate is not None]
            for side in ([f for f in valid if f.reaction_coordinate < 0],
                         [f for f in valid if f.reaction_coordinate > 0]):
                if not side:
                    continue
                outer = max(side, key=lambda frame: abs(frame.reaction_coordinate))
                symbols, positions = parse_xyz(outer.xyz)
                if atoms == list(zip(symbols, positions)):
                    return atoms

    if role != 'product' or _rotated_product(record) is not None:
        return atoms
    mapping = record.structures.product_to_reactant
    if len(atoms) != len(mapping) or sorted(mapping) != list(range(len(atoms))):
        raise ValueError('product endpoint seed and bound atom map differ in atom count')

    if seed.mol_path:
        supplied = Chem.MolFromMolFile(str(_workspace_input_path(record, seed.mol_path)), removeHs=False)
        built = _read_built_xyz(record, 'product')
        reference = record.structures.product
        if reference is None and built and built[3]:
            reference = read_molecule(built[3], input_format='mol')
        if supplied is None or reference is None:
            raise ValueError('product endpoint seed MOL is missing or unreadable')

        supplied_smiles = Chem.MolToSmiles(Chem.RemoveHs(supplied))
        if supplied_smiles != Chem.MolToSmiles(Chem.RemoveHs(reference)):
            reactant = Chem.MolFromSmiles(record.input.reaction.reactant_smiles)
            repair = (
                ' Use verification.reactant_endpoint.seed for the declared reactant.'
                if reactant is not None and supplied_smiles == Chem.MolToSmiles(reactant)
                else ''
            )
            raise ValueError(
                f'Endpoint seed MOL represents {supplied_smiles}, not the declared product '
                f'{record.input.reaction.product_smiles}.{repair}'
            )

        def indexed_graph(mol):
            return ([(a.GetSymbol(), a.GetFormalCharge(), a.GetIsotope()) for a in mol.GetAtoms()],
                sorted((min(b.GetBeginAtomIdx(), b.GetEndAtomIdx()), max(b.GetBeginAtomIdx(), b.GetEndAtomIdx()),
                        b.GetBondTypeAsDouble()) for b in mol.GetBonds()))

        if [a.GetSymbol() for a in supplied.GetAtoms()] != [s for s, _ in atoms]:
            raise ValueError('product endpoint seed XYZ and MOL atom orders differ')
        inverse = [mapping.index(i) for i in range(len(mapping))]
        working = renumber_atoms(reference, inverse)
        native_order = indexed_graph(supplied) == indexed_graph(reference)
        working_order = indexed_graph(supplied) == indexed_graph(working)
        if native_order and working_order and inverse != list(range(len(mapping))):
            # A symmetric graph cannot identify rows. Retain the bound MOL's concrete row identities.
            supplied_positions = supplied.GetConformer().GetPositions().tolist()
            # MOL 序列化仅保留四位小数；比较同一文件表示，不给分子坐标降精度。
            def file_rows(points):
                return [tuple(format(float(value), '.4f') for value in row) for row in points]
            native_order = file_rows(supplied_positions) == file_rows(reference.GetConformer().GetPositions())
            working_order = file_rows(supplied_positions) == file_rows(working.GetConformer().GetPositions())
        if working_order and not native_order:
            return atoms
        if not native_order:
            raise ValueError(f'product endpoint MOL does not establish the bound atom order; reuse {built[3]} or an accepted native IRC endpoint')
    reordered = [None] * len(atoms)
    for source, target in enumerate(mapping):
        reordered[target] = atoms[source]
    return reordered


def _irc_side_for_role(record: TsProcessRecord, info: dict, role: str) -> str:
    """Choose an optimization source, never certify a species or IRC direction.

    A/B are native direction labels. Compare both pairings with the declared
    geometries in the frozen TS atom order; rough or undecidable frames still
    proceed to Opt/Freq and the independent final identity/interval checks.
    """
    from cloudra.tools.core.irc_path import evaluate_endpoint_between, parse_xyz
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    other = 'product' if role == 'reactant' else 'reactant'
    retained = next((step for step in reversed(record.job_steps)
                     if step.purpose == other + '_opt'), None)
    if retained and retained.endpoint_source and retained.endpoint_source.kind == 'irc_outer_frame':
        return 'B' if retained.endpoint_source.label == 'A' else 'A'

    fallback = 'A' if role == 'reactant' else 'B'
    frequency = next((step for step in reversed(record.job_steps)
                      if step.purpose == 'frequency'), None)
    if frequency is None:
        return fallback
    ts_path = Path(frequency.input_path).parent / 'optimized.xyz'
    if not ts_path.is_file():
        return fallback
    ts_atoms = read_xyz_atoms(ts_path)
    symbols = [symbol for symbol, _ in ts_atoms]
    ts_positions = [point for _, point in ts_atoms]
    ends = [read_xyz_atoms(info['path_' + side]) for side in ('a', 'b')]
    if any([symbol for symbol, _ in atoms] != symbols for atoms in ends):
        return fallback
    watch_pairs = [[left + 1, right + 1] for left, right in _active_reaction_center(record)]
    # An explicit opposite species that has already optimized is the useful
    # anchor. Do not discard it in favor of an older, rough search geometry.
    if retained and retained.state == 'done' and retained.endpoint_source:
        xyz, error = _endpoint_opt_frame(record, retained)
        anchor = parse_xyz(xyz) if not error else None
        if anchor and anchor[0] == symbols:
            preferred = 'A' if other == 'reactant' else 'B'
            choices = []
            for side, atoms in zip(('A', 'B'), ends, strict=True):
                result = evaluate_endpoint_between(symbols, ts_positions,
                    [point for _, point in atoms], anchor[1], watch_pairs, record.input.reaction.charge)
                choices.append((not result['is_between'], result['score'], side != preferred, side))
            return 'B' if min(choices)[3] == 'A' else 'A'
    reactant = _read_built_xyz(record, 'reactant')
    if reactant is None or reactant[0] != symbols:
        return fallback
    try:
        references = list(path_endpoints(record.structures))
    except ValueError:
        return fallback
    product_positions = references[1].GetConformer().GetPositions().tolist()
    references = [with_positions(mol, positions) if mol is not None else None
                  for mol, positions in zip(references, (reactant[1], product_positions), strict=True)]
    choices = []
    for swapped, targets in ((False, (reactant[1], product_positions)),
                             (True, (product_positions, reactant[1]))):
        results = [evaluate_endpoint_between(reactant[0], ts_positions,
            [point for _, point in endpoint], target, watch_pairs, record.input.reaction.charge,
            intermediate_molecule=molecule)
            for endpoint, target, molecule in zip(ends, targets, reversed(references) if swapped else references, strict=True)]
        choices.append((not all(item['is_between'] for item in results),
                        sum(item['score'] for item in results), swapped))
    swapped = min(choices)[2]
    return ('B' if fallback == 'A' else 'A') if swapped else fallback


def _write_endpoint_input(record: TsProcessRecord, job_dir: str,
                          role: Literal["reactant", "product"],
                          task: Literal["opt", "frequency"]) -> tuple[str, str]:
    """Write endpoint Opt from a declared species seed or native IRC outer frame.

    Record the actual source when writing; a Freq inherits its accepted Opt
    provenance and uses that converged geometry. Roles and IRC A/B are distinct.
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
    provenance = None
    normalized_source = None
    if task == 'opt' and endpoint.seed is not None:
        path = _workspace_input_path(record, endpoint.seed.xyz_path)
        source = str(path)
        for reference in endpoint.seed.evidence_refs:
            artifact = _workspace_input_path(record, reference)
            if not artifact.is_file():
                return 'Endpoint replacement source/evidence missing', ''
        if not path.is_file():
            return 'Endpoint replacement source/evidence missing', ''
        try:
            atoms = _endpoint_seed_atoms(record, role, endpoint.seed)
        except (OSError, ValueError) as exc:
            return str(exc), ''
        normalized_source = '\n'.join([str(len(atoms)), 'Endpoint seed in TS working atom order',
            *[symbol + ' ' + ' '.join(repr(float(value)) for value in point) for symbol, point in atoms]]) + '\n'
        provenance = dict(kind='species_reference', label=role)
    elif task == "opt":
        irc_step = next(
            (step for step in reversed(record.job_steps) if step.purpose == "irc"), None,
        )
        if irc_step is None or irc_step.state != "done":
            return "a completed IRC job is required before optimizing its outer frames", ""
        irc_log = _refinement_log_path(record, irc_step)
        if not os.path.isfile(irc_log):
            return f"the IRC job log is missing at {irc_log}", ""
        from cloudra.tools.Chemtool.ts_guess import TsGuess

        checks: list[str] = []
        try:
            info = TsGuess._extract_irc_endpoints(
                irc_log, checks, engine=_step_calculation(record, irc_step).engine,
                output_dir=os.path.join(record.run_dir, VERDICT_STAGE_DIR), require_two_sides=True,
            )
        except Exception as exc:
            return f"IRC outer-frame extraction failed: {exc}", ""
        if info is None:
            return "IRC has no usable outer geometry on both sides: " + "; ".join(checks), ""
        for side in ('A', 'B'):
            source = info['path_' + side.lower()]
            if not source or not os.path.isfile(source):
                return f"IRC side {side} outer frame is missing", ""
        side = _irc_side_for_role(record, info, role)
        source = info['path_' + side.lower()]
        import hashlib
        provenance = dict(kind='irc_outer_frame', label=side,
            irc_job_id=irc_step.external_source['source_job_id'] if irc_step.external_source else irc_step.job_id,
            irc_log_sha256=hashlib.sha256(Path(irc_log).read_bytes()).hexdigest())
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
        if opt_step.endpoint_source is None:
            return f'{role} accepted optimization has no endpoint source provenance', ''
        provenance = opt_step.endpoint_source.model_dump()
        source = os.path.join(job_dir, "optimized.xyz")
        atomic_write_text(source, xyz.rstrip() + "\n")

    source_copy=os.path.join(job_dir,f'{role}_source.xyz')
    _write_immutable_input(source_copy, normalized_source if normalized_source is not None else Path(source).read_text())
    source=source_copy
    import hashlib
    if task == 'opt':
        provenance.update(source_path=source_copy, sha256=hashlib.sha256(Path(source_copy).read_bytes()).hexdigest())
    _write_immutable_input(os.path.join(job_dir, 'endpoint_source.json'),
        EndpointSource.model_validate(provenance).model_dump_json())
    declaration = record.input.reaction
    origin_label = (
        'IRC side ' + provenance['label']
        if provenance['kind'] == 'irc_outer_frame' else 'explicit species seed'
    )
    if calculation.engine == "gaussian":
        import warnings
        if task == "opt":
            opt_subopts, rem_keywords, warn = _extract_gaussian_opt_keywords(calculation.keywords, is_ts=False)
            task_type = [{"opt": opt_subopts}]
        else:
            freq_subopts, rem_keywords, warn = _extract_gaussian_freq_keywords(calculation.keywords)
            task_type = [{"freq": freq_subopts}]
        if warn:
            warnings.warn(warn, UserWarning, stacklevel=2)
        calc_copy = calculation.model_copy(update={'keywords': rem_keywords or ''})
    else:
        task_type = [{"opt": None}] if task == "opt" else [{"freq": None}]
        calc_copy = calculation
    name = f"{role}_{task}.{'inp' if calculation.engine == 'orca' else 'gjf'}"
    input_path = os.path.join(job_dir, name)
    request = QmInputWriter_input_schema(
        **calc_copy.model_dump(mode='json'),
        nproc=record.compute_cpus,
        mem=f"{record.compute_memory_mb}MB",
        source_type="xyz_file", source_value=source,
        task_type=task_type,
        charge=declaration.charge, multiplicity=declaration.multiplicity,
        electronic_character=declaration.electronic_character,
        title=f"Endpoint {role} {task} from {origin_label}; identity unverified | declared_species: {getattr(declaration, role + '_smiles')}",
        output_path=input_path,
    )
    conflicts = validate_writer_request(request.model_dump())
    if conflicts:
        return f"{role} {task} input refused: " + " | ".join(
            f"[{item['code']}] {item['message']}" for item in conflicts
        ), ""
    frame = read_molecule(source, charge=declaration.charge)
    reference = path_endpoints(record.structures)[0 if role == 'reactant' else 1]
    if [a.GetSymbol() for a in reference.GetAtoms()] != [a.GetSymbol() for a in frame.GetAtoms()]:
        return f'{role} endpoint frame differs from the owned atom identities', ''
    molecule = with_positions(reference, frame.GetConformer().GetPositions())
    content = QmInputWriter.render_input(request, molecule)
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
    系统 driver 重新读账本并推进；agent 可在任务尚未启动时主动修订输入。
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
        failure, details = _native_failure_details(log_path, _step_calculation(record, current).engine)
        _record_candidate_failure(record, failure, current, log_path, details)
        return _block(
            record, "refine", f"job_{state}",
            f"refinement job {current.job_id} ({current.purpose}) ended as {state!r}; plain "
            "per-engine failure classes come from the log below — the run is stopped, not silently "
            "retried",
            atom_details=details,
            needs=[_calculation_field(current.purpose), "execution", "reaction.reaction_center"],
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
        atom_binding=_direction_atom_binding(record)))
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
        from cloudra.dag.evidence_ingest import snapshot_evidence_file
        log_path = _refinement_log_path(record, current)
        if not Path(log_path).is_file():
            return _block(record, 'refine', 'frequency_evidence_missing',
                          'TS frequency log is missing; IRC cannot be admitted.', needs=['compute_artifacts'])
        snapshot = snapshot_evidence_file(log_path, workspace_root=record.workspace_dir)
        if snapshot.frequencies is None and snapshot.imaginary_frequencies is None:
            return _block(record, 'refine', 'frequency_evidence_missing',
                          'TS frequency data is unavailable; IRC cannot be admitted.', needs=['compute_artifacts'])
        _record_frequency_analysis(record, current, log_path, snapshot)
        imaginary = snapshot.imaginary_frequencies if snapshot.imaginary_frequencies is not None else [f for f in snapshot.frequencies if f < 0]
        if len(imaginary) != 1:
            _record_candidate_failure(record, 'wrong_mode', current, log_path)
            return _block(record, 'refine', 'wrong_mode',
                          f'TS frequency evidence has {len(imaginary)} imaginary modes; exactly one is required before IRC.', needs=['conformers', 'guess', 'verification.frequency'])
        if _require_calculation(record, 'irc', 'refine'):
            return record
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
        atom_binding=_direction_atom_binding(record)))
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
            origin = current.endpoint_source
            source = f'IRC side {origin.label}' if origin and origin.kind == 'irc_outer_frame' else 'explicit species seed'
            return _terminal(
                record, "verdict", "candidate_only",
                f"The {role} endpoint candidate from {source} did not qualify as an "
                f"optimized minimum: {reason}. Repair verification.{role}_endpoint.seed "
                f"for the declared {role} {getattr(record.input.reaction, role + '_smiles')}; "
                "IRC A/B labels do not declare species identity.",
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
        return _block(record,'refine','endpoint_failed','Existing endpoint attempt failed; revise or retry through ts_resume.',needs=[f'verification.{role}_endpoint'])
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
                    "Revise this run with an explicit endpoint seed through ts_resume",
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
            endpoint_source=EndpointSource.model_validate_json(Path(job_dir, 'endpoint_source.json').read_text()),
        atom_binding=_direction_atom_binding(record)))
        record.waiting_for = f"job:{job_id}"
        _record_stage(
            record, "refine", "waiting",
            f"Endpoint {role} {task} job {job_id} "
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
    if not (minimum.frequency_data_present and minimum.frequency_count_valid):
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
    mol = getattr(record.structures, source_role)
    if mol is None:
        return f"{role} declared molecular identity is missing; connectivity is unverified"
    expected_smiles = (
        record.input.reaction.reactant_smiles if source_role == "reactant"
        else record.input.reaction.product_smiles
    )
    declared = Chem.MolFromSmiles(expected_smiles)
    if declared is None or Chem.MolToSmiles(Chem.RemoveHs(mol)) != Chem.MolToSmiles(declared):
        return f"{role} built MOL does not match its declared SMILES; connectivity is unverified"
    n = mol.GetNumAtoms()
    if role == "product" and _rotated_product(record) is None:
        remap = list(record.structures.product_to_reactant)
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
    from cloudra.tools.Chemtool.reaction_mapping import _axis_config_consistency
    observed = Chem.Mol(mol)
    observed.RemoveAllConformers()
    conformer = Chem.Conformer(n)
    for index in range(n):
        conformer.SetAtomPosition(index, optimized[1][remap[index]])
    observed.AddConformer(conformer)
    binding = heavy_binding(mol)
    matches = [tuple(index - 1 for index in binding)] if binding else observed.GetSubstructMatches(declared, useChirality=True)
    axis_error = _axis_config_consistency(declared, observed, matches)
    if axis_error:
        return f'{role} {axis_error}'
    from cloudra.tools.core.electronic_state import electronic_state_issue
    issue = electronic_state_issue(mol, charge=record.input.reaction.charge,
        multiplicity=record.input.reaction.multiplicity, electronic_character=record.input.reaction.electronic_character)
    if issue:
        return f'{role}: {issue[1]}'
    return _geometry_connectivity_error(mol, optimized, record.input.reaction.charge, role, remap,
        multiplicity=record.input.reaction.multiplicity, electronic_character=record.input.reaction.electronic_character)

def _geometry_bond_pairs(symbols, positions):
    """Perceive geometric pairs without inferring an electronic state or bond order."""
    from rdkit import Chem
    from rdkit.Chem import rdDetermineBonds

    from cloudra.tools.core.irc_path import xyz_block
    try:
        probe = Chem.MolFromXYZBlock(xyz_block(symbols, positions))
        if probe is None:
            return None
        rdDetermineBonds.DetermineConnectivity(probe)
    except (RuntimeError, ValueError):
        return None
    return {tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))) for bond in probe.GetBonds()}


def _endpoint_geometry_note(record, label, geometry):
    """Describe observed geometry without changing any acceptance criterion."""
    from rdkit import Chem
    from rdkit.Chem import rdDetermineBonds

    from cloudra.tools.core.irc_path import xyz_block

    try:
        mol = Chem.MolFromXYZBlock(xyz_block(*geometry))
        if mol is None:
            raise ValueError('unreadable geometry')
        rdDetermineBonds.DetermineBonds(mol, charge=record.input.reaction.charge)
        return f'Optimized endpoint in {label} slot, geometry-perceived SMILES: {Chem.MolToSmiles(Chem.RemoveHs(mol))}'
    except (RuntimeError, ValueError) as exc:
        return f'Optimized endpoint in {label} slot, molecular identity could not be perceived: {exc}'


def _geometry_connectivity_error(mol, optimized, charge, role, remap=None, *, multiplicity=1, electronic_character=None):
    """Spin-aware geometry proves bond pairs; bond orders remain declared identity."""
    import math

    from rdkit import Chem

    from cloudra.tools.core.electronic_state import electronic_state_details
    from cloudra.tools.core.irc_path import COVALENT_RADII, DISTANCE_CONNECTIVITY_FACTOR, perceive_bonds
    spin_aware_geometry = electronic_state_details(mol, charge=charge, multiplicity=multiplicity,
                                                  electronic_character=electronic_character)['requires_spin_aware_geometry']
    n = mol.GetNumAtoms()
    remap = list(range(n)) if remap is None else remap
    expected_bonds = {
        tuple(sorted((remap[bond.GetBeginAtomIdx()], remap[bond.GetEndAtomIdx()]))):
        float(bond.GetBondTypeAsDouble())
        for bond in mol.GetBonds()
    }
    fragments = Chem.GetMolFrags(mol)
    if len(fragments) == 1:
        if spin_aware_geometry:
            pairs = _geometry_bond_pairs(optimized[0], optimized[1])
            if pairs is None:
                return f'{role} geometric bond pairs for the declared electronic identity could not be determined by RDKit'
            actual_bonds = dict.fromkeys(pairs)
        else:
            actual_bonds, source = perceive_bonds(optimized[0], optimized[1], charge)
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
            fragment_symbols = [optimized[0][index] for index in indices]
            fragment_positions = [optimized[1][index] for index in indices]
            if spin_aware_geometry:
                pairs = _geometry_bond_pairs(fragment_symbols, fragment_positions)
                if pairs is None:
                    return f'{role} fragment bond pairs for the declared electronic identity could not be determined by RDKit'
                fragment_bonds = dict.fromkeys(pairs)
            else:
                fragment_bonds, source = perceive_bonds(fragment_symbols, fragment_positions, fragment_charge)
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
        missing_1based = sorted((left + 1, right + 1) for left, right in missing)
        extra_1based = sorted((left + 1, right + 1) for left, right in extra)
        return (
            f"{role} optimized connectivity differs from the declared species (atom pairs 1-based): "
            f"missing bonds={missing_1based}, extra bonds={extra_1based}"
        )
    if not spin_aware_geometry:
        different_orders = [
            pair for pair in expected_bonds.keys() & actual_bonds.keys()
            if abs(expected_bonds[pair] - actual_bonds[pair]) > 0.1
        ]
        if different_orders:
            pairs_1based = sorted((left + 1, right + 1) for left, right in different_orders)
            return f"{role} optimized bond order differs from the declared species (atom pairs 1-based) at {pairs_1based}"
    return ""

def _irc_interval_proof(
    record: TsProcessRecord, irc_log: str, freq_step: "TsJobStep",
    reactant: tuple[list[str], list[list[float]]],
    product: tuple[list[str], list[list[float]]],
    expected_origins: dict[str, str],
) -> tuple[bool, str]:
    """verified 的区间证明：每个 IRC 双侧端点几何上位于 TS 与对应声明极小值之间。

    材料：TS 几何（频率作业旁的 ``optimized.xyz``）、两端经 Opt 收敛且 Freq
    零虚频的极小值、IRC 双侧端点（复用 ts_guess 的引擎分发提取，
    原子对齐用 irc_path.align_atom_order）。证明本体是
    irc_path.assign_irc_endpoints（与 ts_guess strict / benchmark selfconsistency
    同一实现）。任何材料缺失、对齐不可判或证明不成立都返回 ``(False, 原因)``——
    调用方落 candidate_only，绝不升格 verified。
    """
    from cloudra.tools.Chemtool.ts_guess import TsGuess
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
    info = TsGuess._extract_irc_endpoints(
        irc_log, checks,
        engine=stage_calculation(record, 'irc').engine,
        output_dir=os.path.join(record.run_dir, VERDICT_STAGE_DIR),
        require_two_sides=True,
    )
    if info is None:
        return False, "no usable bidirectional IRC endpoint geometries: " + "; ".join(checks)
    end_a = parse_xyz(info["end_a"].xyz)
    end_b = parse_xyz(info["end_b"].xyz)
    if end_a is None or end_b is None:
        return False, "the extracted IRC endpoint geometries could not be parsed"
    from cloudra.tools.core.irc_path import same_geometry
    for role in ('reactant', 'product'):
        opt = next(s for s in reversed(record.job_steps) if s.purpose == role + '_opt')
        origin = opt.endpoint_source
        if origin.kind == 'irc_outer_frame':
            saved = parse_xyz(Path(origin.source_path).read_text())
            if not same_geometry(saved, end_a if origin.label == 'A' else end_b):
                return False, f'{role} source provenance is not the accepted IRC {origin.label} outer-frame geometry'

    try:
        references = list(path_endpoints(record.structures))
    except ValueError:
        references = [None, None]
    aligned: list[list] = []
    for slot, (label, symbols, positions) in enumerate((
        ("IRC endpoint A", end_a[0], end_a[1]),
        ("IRC endpoint B", end_b[0], end_b[1]),
        ("reactant minimum", reactant[0], reactant[1]),
        ("product minimum", product[0], product[1]),
    )):
        result = align_atom_order(ts_symbols, ts_pos, list(symbols), positions)
        if result is None:
            return False, (
                f"{label} could not be aligned to the TS atom order (composition mismatch, no "
                "element-consistent assignment, or aligned distance-matrix rmsd above the gate); "
                "this combination is undecidable"
            )
        aligned.append([list(positions[k]) for k in result[0]])
        if slot >= 2 and references[slot - 2] is not None:
            reference = references[slot - 2]
            if [atom.GetSymbol() for atom in reference.GetAtoms()] != list(symbols):
                references[slot - 2] = None
            else:
                references[slot - 2] = with_positions(renumber_atoms(reference, result[0]), aligned[-1])

    watch_pairs = [
        [int(left) + 1, int(right) + 1] for left, right in _active_reaction_center(record)
    ]
    proof = assign_irc_endpoints(
        ts_symbols, ts_pos, aligned[0], aligned[1], aligned[2], aligned[3],
        watch_pairs, record.input.reaction.charge,
        reference_molecules=tuple(references),
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
    actual = {'A': 'reactant', 'B': 'product'} if proof['assignment'] == 'direct' else {'A': 'product', 'B': 'reactant'}
    if any(actual[side] != species for side, species in expected_origins.items()):
        return False, (
            "the interval pairing contradicts the provenance of the optimized IRC outer "
            f"frames (proof={proof['assignment']}, source={expected_origins})"
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
    _record_frequency_analysis(record, freq_step, log_path, snapshot)
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
    reactant, reason = _validated_endpoint_minimum(record, "reactant")
    if reactant is None:
        return _terminal(record, "verdict", "candidate_only", f"Declared reactant minimum is unverified: {reason}")
    product, reason = _validated_endpoint_minimum(record, "product")
    if product is None:
        return _terminal(record, "verdict", "candidate_only", f"Declared product minimum is unverified: {reason}")

    failures: list[str] = []
    import hashlib
    sources = {}
    for slot in ('reactant', 'product'):
        opt = next((s for s in reversed(record.job_steps) if s.purpose == slot + '_opt'), None)
        freq = next((s for s in reversed(record.job_steps) if s.purpose == slot + '_frequency'), None)
        origin = opt.endpoint_source if opt else None
        if origin is None or freq is None or freq.endpoint_source != origin:
            return _terminal(record, 'verdict', 'candidate_only', f'{slot} endpoint source provenance is missing or differs between Opt and Freq')
        if not Path(origin.source_path).is_file() or hashlib.sha256(Path(origin.source_path).read_bytes()).hexdigest() != origin.sha256:
            return _terminal(record, 'verdict', 'candidate_only', f'{slot} endpoint source provenance changed')
        if origin.kind == 'irc_outer_frame' and (origin.label not in {'A', 'B'} or
            origin.irc_job_id != (irc_step.external_source['source_job_id'] if irc_step.external_source else irc_step.job_id) or
            origin.irc_log_sha256 != hashlib.sha256(Path(irc_log).read_bytes()).hexdigest()):
            return _terminal(record, 'verdict', 'candidate_only', f'{slot} endpoint IRC source provenance does not match the accepted IRC')
        if origin.kind == 'species_reference' and origin.label != slot:
            return _terminal(record, 'verdict', 'candidate_only', f'{slot} explicit seed declared a different species role')
        sources[slot] = origin
    sides = [origin.label for origin in sources.values() if origin.kind == 'irc_outer_frame']
    if len(sides) != len(set(sides)):
        return _terminal(record, 'verdict', 'candidate_only', 'Endpoint source provenance repeats an IRC side; both origins must be checked independently.')
    expected_origins = {origin.label: role for role, origin in sources.items()
                        if origin.kind == 'irc_outer_frame'}
    identity_errors = [
        _endpoint_identity_error(record, "reactant", reactant),
        _endpoint_identity_error(record, "product", product),
    ]
    if any(identity_errors):
        failures.append(f"Declared species identity: {'; '.join(error for error in identity_errors if error)}")
    else:
        passed, detail = _irc_interval_proof(
            record, irc_log, freq_step, reactant, product, expected_origins,
        )
        if passed:
            return _terminal(
                record, "verdict", "verified",
                f"verified transition state: exactly one imaginary mode ({imag[0]:.1f} cm^-1), "
                f"usable IRC geometries from both directions, and {detail}; "
                "optimized endpoint identities match the declared reactant and product",
            )
        failures.append(f"IRC interval proof: {detail}")
    return _terminal(
        record, "verdict", "candidate_only",
        "The optimized IRC outer frames did not establish one consistent species identity, "
        "source provenance, and endpoint interval proof: " + "; ".join(failures)
        + ". " + _endpoint_geometry_note(record, 'reactant', reactant)
        + "; " + _endpoint_geometry_note(record, 'product', product)
        + ". These observations do not override the failed checks. The candidate stays UNVERIFIED",
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
    if record.is_terminal or record.stop_reason:
        return record
    try:
        _verify_provided_guess_binding(record)
    except (OSError, ValueError) as exc:
        return _block(record, record.stage, 'provided_guess_artifact_changed', str(exc), needs=['guess'])
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


def stop(record: TsProcessRecord, reason: str) -> TsProcessRecord:
    """Stop this pipeline and request cancellation through the compute ledger."""
    from cloudra.infra.flocks import locked
    from cloudra.services.ts_pipeline_context import pipeline_database, require_pipeline_producer
    from cloudra.services.ts_pipeline_store import stop_process

    require_pipeline_producer(record.owner_conversation_id, record.owner_session_id)
    with locked(str(Path(record.run_dir) / '.pipeline.lock')):
        state = stop_process(pipeline_database(), process_id=record.pipeline_id,
            project_id=record.owner_conversation_id, owner_id=record.owner_session_id, reason=reason)
    return TsProcessRecord.model_validate(state)







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
