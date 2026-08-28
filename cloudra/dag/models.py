"""Shared types for DAG-guided orchestration."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, computed_field, model_validator


class OrchestrationMode(str, Enum):
    STANDARD = "standard"
    DAG_RECORD = "dag_record"
    DAG_GUIDED = "dag_guided"


class GraphKind(str, Enum):
    PROCESS = "process"
    DELIVERY = "delivery"


GraphRefType = Literal["artifact", "compute_job", "tool_result", "species"]


class GraphRef(BaseModel):
    """A durable pointer from a graph record to canonical data elsewhere."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref_type: GraphRefType
    ref_id: str = Field(min_length=1)
    content_hash: str | None = None
    revision: int | None = Field(default=None, ge=0)


class SpeciesRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    species_id: str
    canonical_key: str
    identifiers: dict[str, str]
    charge: int
    multiplicity: int = Field(ge=1)
    metadata: dict = Field(default_factory=dict)


# process 图节点 status 的历史词表：仅用于旧 journal 的只读兼容解析
# （Phase 4 起 process 图已删除，新写入一律 process_graph_removed）。
ProcessStatusValue = Literal[
    "proposed",
    "ready",
    "running",
    "succeeded",
    "failed",
    "blocked",
    "skipped",
    "superseded",
]

# delivery 元素的证据等级阶梯（completion._LEVEL_RANK 同序）加两个处置级。
# 高于 proposed 的等级只能由 harness 确定性派生写入（见 engine 分权守卫）。
DeliveryEvidenceLevel = Literal[
    "proposed",
    "structure_supported",
    "saddle_supported",
    "endpoint_supported",
    "thermo_annotated",
    "rejected",
    "inconclusive",
]
_DELIVERY_EVIDENCE_LEVELS = set(DeliveryEvidenceLevel.__args__)
_PROCESS_STATUS_VALUES = set(ProcessStatusValue.__args__)


class StageKind(str, Enum):
    """delivery 元素的阶段词表：Coordinator 按元素选子集，harness 不外推链条。

    occurrence 用 geometry/frequency/single_point；elementary-step 边用其余
    （frequency 两边共用）。ts_guess 只是建议性阶段，永远不能充抵
    ts_opt/frequency。
    """

    GEOMETRY = "geometry"
    FREQUENCY = "frequency"
    SINGLE_POINT = "single_point"
    TS_GUESS = "ts_guess"
    TS_OPT = "ts_opt"
    SHORT_IRC = "short_irc"
    ENDPOINT_A = "endpoint_a"
    ENDPOINT_B = "endpoint_b"
    DIRECTION = "direction"
    IDENTITY = "identity"
    THERMOCHEMISTRY = "thermochemistry"


class StageStatus(str, Enum):
    PENDING = "pending"
    SUPPORTED = "supported"
    SKIPPED = "skipped"
    # 该证据槽对此元素物理上/逻辑上不成立（无能垒步无 TS、单分子步无
    # endpoint_b 络合物等）；带理由时计入完成，语义上"不欠"，区别于
    # skipped 的"本该算但选择不算"。
    NOT_APPLICABLE = "not_applicable"
    REJECTED = "rejected"


class StageState(BaseModel):
    """元素上一个阶段的绑定状态；skipped/not_applicable/rejected 必须附非空
    reason 才算处置（not_applicable 的 reason 须说明该槽为何不成立）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: StageKind
    required: bool = True
    status: StageStatus = StageStatus.PENDING
    reason: str = ""  # skipped/rejected 时必填（覆盖评估强制，schema 层不拦旧数据）
    ref: GraphRef | None = None


class StageContract(BaseModel):
    """元素的阶段契约：list 顺序即允许的绑定顺序。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stages: list[StageState]


# occurrence 与 elementary-step 边各自的合法阶段词表（frequency 两边共用）。
OCCURRENCE_STAGE_KINDS = frozenset(
    {StageKind.GEOMETRY, StageKind.FREQUENCY, StageKind.SINGLE_POINT}
)
ELEMENTARY_STEP_STAGE_KINDS = frozenset({
    StageKind.TS_GUESS,
    StageKind.TS_OPT,
    StageKind.FREQUENCY,
    StageKind.SHORT_IRC,
    StageKind.ENDPOINT_A,
    StageKind.ENDPOINT_B,
    StageKind.DIRECTION,
    StageKind.IDENTITY,
    StageKind.THERMOCHEMISTRY,
})


class CallReview(BaseModel):
    """一次待复核的工具调用/计算作业终态（D12：append-only 收件箱行，不是图）。

    sidecar 字段（caller/tool/arguments_digest/is_success/compute_job_id）只供
    Supervisor 判断，不构成任何自动绑定权威；is_success 对计算作业是作业的
    终态（D11），不是 submit 调用的成败。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: str
    tool_call_id: str = ""
    tool_name: str
    is_success: bool
    caller_session_id: str = ""
    caller_role_id: str = ""  # v2 role_id，如 small_mol
    caller_legacy_id: str = ""  # legacy a-N（D13 单一映射路径）
    arguments_digest: str = ""
    result_summary: str = ""
    # 来源/判别元数据（sidecar only，供 Supervisor 判断，不构成绑定权威）：
    # source_path 是产生本 artifact 的源文件绝对路径（如解析工具的 log_path）；
    # result_kind 是机器可读的失败类别（ok / source_missing / parse_failed /
    # environment / failed），用于区分"证据坏"与"解析管线坏"。
    source_path: str = ""
    result_kind: str = ""
    compute_job_id: str | None = None
    suggested_target_id: str | None = None  # Coordinator 提示，sidecar only
    suggested_stage: str = ""  # Coordinator 声明的目标阶段（sidecar only）
    state: Literal["pending", "reviewed", "ignored"] = "pending"
    created_at: str = ""


# 旧行读取映射：stages 为空 ⇒ 由存储的 evidence_level 一次性映射出阶段
# （stages 列见 persistence/database.py 的 _RELATED_EXTRA_COLUMNS）。
_LEGACY_OCCURRENCE_STAGES = {
    "structure_supported": (StageKind.GEOMETRY,),
    "thermo_annotated": (StageKind.GEOMETRY, StageKind.SINGLE_POINT),
}
_LEGACY_EDGE_STAGES = {
    "saddle_supported": (StageKind.TS_OPT, StageKind.FREQUENCY),
    "endpoint_supported": (
        StageKind.TS_OPT,
        StageKind.FREQUENCY,
        StageKind.SHORT_IRC,
        StageKind.ENDPOINT_A,
        StageKind.ENDPOINT_B,
        StageKind.DIRECTION,
        StageKind.IDENTITY,
    ),
    "thermo_annotated": (
        StageKind.TS_OPT,
        StageKind.FREQUENCY,
        StageKind.SHORT_IRC,
        StageKind.ENDPOINT_A,
        StageKind.ENDPOINT_B,
        StageKind.DIRECTION,
        StageKind.IDENTITY,
        StageKind.THERMOCHEMISTRY,
    ),
}


def map_legacy_stages(
    evidence_level: str, reason: str = "", *, is_edge: bool
) -> list[StageState]:
    """旧物化行（无 stages）→ 阶段列表；rejected/inconclusive 映射为单个
    合成阶段（geometry/ts_opt），带上存储的 reason。"""
    if evidence_level in ("rejected", "inconclusive"):
        status = (
            StageStatus.REJECTED
            if evidence_level == "rejected"
            else StageStatus.SKIPPED
        )
        kind = StageKind.TS_OPT if is_edge else StageKind.GEOMETRY
        return [StageState(kind=kind, status=status, reason=reason)]
    table = _LEGACY_EDGE_STAGES if is_edge else _LEGACY_OCCURRENCE_STAGES
    return [
        StageState(kind=kind, status=StageStatus.SUPPORTED)
        for kind in table.get(evidence_level, ())
    ]


def derive_evidence_level(
    stages: list[StageState], *, is_edge: bool
) -> DeliveryEvidenceLevel:
    """由阶段状态确定性派生证据等级（display/compat 专用，模型永不直写）。

    not_applicable 阶段视为"该槽不成立、已正确处理"：不计入 pending，也
    不触发 inconclusive；派生时把 supported 与 not_applicable 一并视为已
    满足，使无能垒步（无 ts_opt/frequency 槽）仍能按其余 supported 阶段
    派生到 endpoint_supported 等。
    """
    required = [stage for stage in stages if stage.required]
    if not required:
        return "proposed"
    has_pending = any(stage.status is StageStatus.PENDING for stage in required)
    has_rejected = any(stage.status is StageStatus.REJECTED for stage in required)
    has_skipped = any(stage.status is StageStatus.SKIPPED for stage in required)
    all_supported = all(stage.status is StageStatus.SUPPORTED for stage in required)
    if has_rejected and not has_pending:
        return "rejected"
    if has_skipped and not has_rejected and not all_supported:
        return "inconclusive"
    satisfied = {
        stage.kind
        for stage in stages
        if stage.status in {StageStatus.SUPPORTED, StageStatus.NOT_APPLICABLE}
    }
    if is_edge:
        if StageKind.THERMOCHEMISTRY in satisfied:
            return "thermo_annotated"
        if {
            StageKind.SHORT_IRC,
            StageKind.ENDPOINT_A,
            StageKind.ENDPOINT_B,
            StageKind.DIRECTION,
            StageKind.IDENTITY,
        } <= satisfied:
            return "endpoint_supported"
        if {StageKind.TS_OPT, StageKind.FREQUENCY} <= satisfied:
            return "saddle_supported"
        return "proposed"
    if all_supported:
        return (
            "thermo_annotated"
            if StageKind.SINGLE_POINT in satisfied
            else "structure_supported"
        )
    return "proposed"

# delivery 节点 role 的约定词表（机理图中物种出现的位置）。
_DELIVERY_NODE_ROLES = {"reactant", "intermediate", "product"}

# 旧词表 → 现行词表：仅读取/重放兼容（旧 journal 与旧物化行里的
# node_type/edge_type），写入路径只接受现行值。
_LEGACY_NODE_TYPE_ALIASES = {
    "workflow": "planned",
    "work": "planned",
    "calculation": "planned",
    "planned_tool_call": "planned",
    "intermediate_occurrence": "occurrence",
    "deliverable": "occurrence",
}
_LEGACY_EDGE_TYPE_ALIASES = {
    "depends_on": "dependency",
}

# 旧 journal 保留的是提交原文，引擎写入时才把同义词归一化（不回写日志），
# 因此重放旧日志仍需这张映射。只读兼容：新写入由 Literal 直接拒绝词表外值。
_LEGACY_STATUS_ALIASES = {
    "pending": "proposed",
    "planned": "proposed",
    "queued": "proposed",
    "todo": "proposed",
    "in_progress": "running",
    "in-progress": "running",
    "started": "running",
    "active": "running",
    "done": "succeeded",
    "completed": "succeeded",
    "complete": "succeeded",
    "success": "succeeded",
    "cancelled": "skipped",
    "canceled": "skipped",
    "error": "failed",
    "failure": "failed",
}


def _map_legacy_status(data: Any) -> Any:
    """旧形状元素/changes 字典里的 status 同义词映射（仅迁移路径调用）。

    旧元素的 status 多在 ``payload`` 里（折叠发生在类 validator，更晚），
    顶层与嵌套两个位置都要看。
    """
    if not isinstance(data, dict):
        return data

    def _map(value: Any) -> Any:
        if isinstance(value, str):
            return _LEGACY_STATUS_ALIASES.get(value.strip().lower(), value)
        return value

    if "status" in data:
        mapped = _map(data["status"])
        if mapped != data["status"]:
            data = {**data, "status": mapped}
    payload = data.get("payload")
    if isinstance(payload, dict) and "status" in payload:
        mapped = _map(payload["status"])
        if mapped != payload["status"]:
            data = {**data, "payload": {**payload, "status": mapped}}
    return data


class _GraphElement(BaseModel):
    """图元素公共基座：显式约定字段 + ``metadata`` 自由扩展位。

    旧格式兼容（只读）：旧 journal/物化行把约定键塞在自由 ``payload`` dict
    里，这里把 ``payload`` 内容展平为显式字段、未识别键并入 ``metadata``，
    保证旧数据可重放；新写入走显式字段，schema 即文档。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    refs: list[GraphRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # 自由文本备注（模型可写），视图截断展示；不约束结构。
    annotations: Any = None

    @model_validator(mode="before")
    @classmethod
    def _fold_legacy_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        legacy = data.pop("payload", None)
        if isinstance(legacy, dict):
            for key, value in legacy.items():
                data.setdefault(key, value)
        known = set(cls.model_fields)
        extras = {key: data.pop(key) for key in list(data) if key not in known}
        if extras:
            metadata = dict(data.get("metadata") or {})
            for key, value in extras.items():
                metadata.setdefault(key, value)
            data["metadata"] = metadata
        # 旧日志里 priority 出现过 "high" 等脏值：读取侧归零容忍，
        # 写入侧由 schema（int）约束。
        if "priority" in cls.model_fields and "priority" in data:
            try:
                data["priority"] = int(data["priority"])
            except (TypeError, ValueError):
                data["priority"] = 0
        return data

    @computed_field
    @property
    def payload(self) -> dict[str, Any]:
        """视图投影：非默认值的显式字段 + metadata 合并成的展示字典。

        只为序列化视图（service / 子图 view / TUI）保留旧外形；
        逻辑代码一律读显式字段，不写这个投影。
        """
        skipped = {
            "node_id", "edge_id", "source_node_id", "target_node_id",
            "node_type", "edge_type", "label", "refs", "metadata",
        }
        out: dict[str, Any] = {}
        for name, info in type(self).model_fields.items():
            if name in skipped:
                continue
            value = getattr(self, name)
            default = info.get_default(call_default_factory=True)
            if value != default:
                out[name] = value
        out.update(self.metadata)
        return out


class _ProcessNodeBase(_GraphElement):
    """process 图节点的公共字段（计划节点与观察记录共用一套状态语义）。"""

    node_id: str
    label: str
    status: ProcessStatusValue = "proposed"
    priority: int = 0
    # 排产归属：子 agent 只能回报 assignee 等于自己 agent id 的节点
    assignee: str | None = None
    reason: str = ""
    blocked_reason: str = ""
    required: bool = False
    supersedes: str | None = None
    created_at: str = ""
    # 工具绑定：Supervisor 排产写入 tool_name/delivery_target_*/evidence_role，
    # harness 观察时回填 tool_call_id/arguments_hash/evidence_source
    tool_name: str | None = None
    tool_call_id: str | None = None
    arguments_hash: str | None = None
    delivery_target_type: Literal["node", "edge"] | None = None
    delivery_target_id: str | None = None
    evidence_role: str | None = None
    evidence_source: str | None = None
    unplanned: bool = False


class PlannedNode(_ProcessNodeBase):
    """process 图上的计划工作节点（Supervisor 排产，可进入 frontier）。"""

    node_type: Literal["planned"] = "planned"


class ObservedNode(_ProcessNodeBase):
    """process 图上的工具调用遥测记录（harness 自动记账，不是排产工作）。"""

    node_type: Literal["observed_tool_call"] = "observed_tool_call"
    # 关键参数的短摘要（路径类优先），供 Coordinator 在多个同工具 observed
    # 节点间消歧后走 bind_evidence 的 observed_<hex> 别名补挂证据。
    arguments_summary: str = ""


class OccurrenceNode(_GraphElement):
    """delivery 图上的物种出现节点（反应物/中间体/产物的一次出现）。"""

    node_id: str
    node_type: Literal["occurrence"] = "occurrence"
    label: str
    role: Literal["reactant", "intermediate", "product"] | None = None
    smiles: str | None = None
    evidence_level: DeliveryEvidenceLevel = "proposed"
    # rejected/inconclusive 处置级必须附 reason（分支处置审计）
    reason: str = ""
    required: bool = False
    supersedes: str | None = None
    # ts_guess/scan_parse 的建议性来源（不提升证据等级，只留痕）
    advisory_sources: list[str] = Field(default_factory=list)
    # Supervisor 否决标记（review_evidence 写入）
    evidence_vetoed: bool = False
    # 阶段契约：Coordinator 建机理时声明；空列表 = 旧元素，读取时按
    # evidence_level 映射（map_legacy_stages）。状态只由 harness 阶段绑定推进。
    stages: list[StageState] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _demote_legacy_values(cls, data: Any) -> Any:
        # 旧自由 payload 里可能有词表外的 role/evidence_level：降级进
        # metadata 保留原文，字段回默认值，保证旧数据可重放。
        if not isinstance(data, dict):
            return data
        data = dict(data)
        metadata = dict(data.get("metadata") or {})
        role = data.get("role")
        if role is not None and role not in _DELIVERY_NODE_ROLES:
            metadata.setdefault("role", role)
            data["role"] = None
        level = data.get("evidence_level")
        if level is not None and level not in _DELIVERY_EVIDENCE_LEVELS:
            metadata.setdefault("evidence_level", level)
            data["evidence_level"] = "proposed"
        if metadata:
            data["metadata"] = metadata
        return data


class DependencyEdge(_GraphElement):
    """process 图上的依赖边（ predecessor 成功/跳过后 successor 才 ready）。"""

    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: Literal["dependency"] = "dependency"
    label: str = ""
    # 边自身的处置状态（skipped/superseded 的边不再参与依赖判定）；None = 生效中
    status: ProcessStatusValue | None = None
    reason: str = ""
    blocked_reason: str = ""
    required: bool = False
    supersedes: str | None = None


class ElementaryStepEdge(_GraphElement):
    """delivery 图上的基元步骤边（连接两次物种出现，证据挂在边上）。"""

    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: Literal["elementary_step"] = "elementary_step"
    label: str = ""
    evidence_level: DeliveryEvidenceLevel = "proposed"
    reason: str = ""
    required: bool = False
    supersedes: str | None = None
    advisory_sources: list[str] = Field(default_factory=list)
    evidence_vetoed: bool = False
    # 派生证据位：仅 harness 确定性派生可写（engine._DERIVED_EVIDENCE_FIELDS），
    # 模型直写会被分权守卫拒绝。
    saddle_supported: bool = False
    short_irc_supported: bool = False
    endpoint_a_minimum_supported: bool = False
    endpoint_b_minimum_supported: bool = False
    endpoint_direction_consistent: bool = False
    endpoint_identity_matched: bool = False
    thermochemistry_supported: bool = False
    # 阶段契约：同 OccurrenceNode.stages。
    stages: list[StageState] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _demote_legacy_values(cls, data: Any) -> Any:
        # 同 OccurrenceNode：词表外的旧 evidence_level 降级进 metadata。
        if not isinstance(data, dict):
            return data
        level = data.get("evidence_level")
        if level is not None and level not in _DELIVERY_EVIDENCE_LEVELS:
            data = dict(data)
            metadata = dict(data.get("metadata") or {})
            metadata.setdefault("evidence_level", level)
            data["metadata"] = metadata
            data["evidence_level"] = "proposed"
        return data


DagNode = Annotated[
    Union[PlannedNode, ObservedNode, OccurrenceNode],
    Field(discriminator="node_type"),
]
DagEdge = Annotated[
    Union[DependencyEdge, ElementaryStepEdge],
    Field(discriminator="edge_type"),
]

_NODE_ADAPTER = TypeAdapter(DagNode)
_EDGE_ADAPTER = TypeAdapter(DagEdge)


def parse_dag_node(data: Any) -> DagNode:
    """解析节点（存储读取路径，新旧格式双兼容）：旧词表/同义词先映射再走判别联合。"""
    if isinstance(data, dict):
        data = _map_legacy_status(data)
        alias = _LEGACY_NODE_TYPE_ALIASES.get(data.get("node_type"))
        if alias:
            data = {**data, "node_type": alias}
    return _NODE_ADAPTER.validate_python(data)


def parse_dag_edge(data: Any) -> DagEdge:
    """解析边（存储读取路径，新旧格式双兼容）：旧词表/同义词先映射再走判别联合。"""
    if isinstance(data, dict):
        data = _map_legacy_status(data)
        alias = _LEGACY_EDGE_TYPE_ALIASES.get(data.get("edge_type"))
        if alias:
            data = {**data, "edge_type": alias}
    return _EDGE_ADAPTER.validate_python(data)


class GraphData(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_id: str
    graph_kind: GraphKind
    revision: int = Field(ge=0)
    metadata: dict = Field(default_factory=dict)
    nodes: list[DagNode] = Field(default_factory=list)
    edges: list[DagEdge] = Field(default_factory=list)


class GraphBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    process_graph_id: str
    delivery_graph_id: str
    revisions: dict[str, int]


class GraphSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bundle: GraphBundle
    process: GraphData
    delivery: GraphData


class GraphActor(str, Enum):
    HARNESS = "harness"
    SUPERVISOR = "supervisor"
    AGENT = "agent"
    USER = "user"


class _OperationBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_data(cls, data: Any) -> Any:
        """旧格式兼容（只读）：旧 op 形如 ``{"op", "graph", "data": {...}}``，
        把 ``data`` 内容提升到顶层具名字段。add_node/add_edge/set_coverage_contract/
        waive_gate 在各自子类里再包一层。"""
        if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
            return data
        legacy = data["data"]
        data = {key: value for key, value in data.items() if key != "data"}
        for key, value in legacy.items():
            data.setdefault(key, value)
        return data


class AddNode(_OperationBase):
    """新增节点：``node`` 是完整节点对象（node_type 判别 planned/occurrence）。"""

    op: Literal["add_node"]
    graph: GraphKind
    node: DagNode

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: Any) -> Any:
        # 旧形状（data 包裹）才做词表/同义词迁移；新形状写错由 Literal 报错教学。
        if not (isinstance(data, dict) and "node" not in data and isinstance(data.get("data"), dict)):
            return data
        node = _map_legacy_status(data["data"])
        alias = _LEGACY_NODE_TYPE_ALIASES.get(node.get("node_type"))
        if alias:
            node = {**node, "node_type": alias}
        data = {**data, "node": node}
        del data["data"]
        return data


class AddEdge(_OperationBase):
    """新增边：``edge`` 是完整边对象（edge_type 判别 dependency/elementary_step）。"""

    op: Literal["add_edge"]
    graph: GraphKind
    edge: DagEdge

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: Any) -> Any:
        # 旧形状（data 包裹）才做词表/同义词迁移；新形状写错由 Literal 报错教学。
        if not (isinstance(data, dict) and "edge" not in data and isinstance(data.get("data"), dict)):
            return data
        edge = _map_legacy_status(data["data"])
        alias = _LEGACY_EDGE_TYPE_ALIASES.get(edge.get("edge_type"))
        if alias:
            edge = {**edge, "edge_type": alias}
        # 旧引擎不校验 add_edge 的 status：词表外旧值降级进 metadata 保留原文。
        # 旧形状的 status 多在 payload 里，两个位置都要清。
        payload = edge.get("payload") if isinstance(edge.get("payload"), dict) else {}
        status = edge.get("status", payload.get("status"))
        if status is not None and status not in _PROCESS_STATUS_VALUES:
            metadata = dict(edge.get("metadata") or {})
            metadata.setdefault("status", status)
            edge = {key: value for key, value in edge.items() if key != "status"}
            if "status" in payload:
                edge = {**edge, "payload": {k: v for k, v in payload.items() if k != "status"}}
            edge = {**edge, "metadata": metadata}
        data = {**data, "edge": edge}
        del data["data"]
        return data


class RemoveEdge(_OperationBase):
    """删除边：批次必须带 rationale，删除留在变更日志供审计。"""

    op: Literal["remove_edge"]
    graph: GraphKind
    edge_id: str


class UpdateNode(_OperationBase):
    """更新节点：``changes`` 是部分字段字典（键为节点显式字段名，未知键入 metadata）。"""

    op: Literal["update_node"]
    graph: GraphKind
    node_id: str
    changes: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: Any) -> Any:
        # 旧日志的 changes.status 是未归一化的原文，映射同义词。
        # before-validator 子类先于基类执行，这里看到的 "data" 即旧形状；
        # 新形状的顶层 changes 不碰——同义词在写入路径由引擎校验拒绝。
        if not isinstance(data, dict):
            return data
        legacy = data.get("data")
        if isinstance(legacy, dict) and isinstance(legacy.get("changes"), dict):
            data = {
                **data,
                "data": {**legacy, "changes": _map_legacy_status(legacy["changes"])},
            }
        return data


class UpdateEdge(_OperationBase):
    """更新边：``changes`` 语义同 UpdateNode。"""

    op: Literal["update_edge"]
    graph: GraphKind
    edge_id: str
    changes: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        legacy = data.get("data")
        if isinstance(legacy, dict) and isinstance(legacy.get("changes"), dict):
            data = {
                **data,
                "data": {**legacy, "changes": _map_legacy_status(legacy["changes"])},
            }
        if isinstance(data.get("changes"), dict):
            data = {**data, "changes": _map_legacy_status(data["changes"])}
        return data


class AttachRef(_OperationBase):
    """给节点/边挂载一条不可变证据引用（GraphRef 指向真实证据库记录）。"""

    op: Literal["attach_ref"]
    graph: GraphKind
    target_type: Literal["node", "edge"]
    target_id: str
    ref: GraphRef
    # 事后认领挂钩：带 evidence_role 的 delivery attach_ref 会触发确定性重派生
    evidence_role: str | None = None


class AddLink(_OperationBase):
    """跨图簿记：把 process 计划节点关联到它服务的 delivery 元素（graph 置空）。"""

    op: Literal["add_link"]
    graph: GraphKind | None = None
    link_id: str
    process_node_id: str
    delivery_element_type: Literal["node", "edge"]
    delivery_element_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class SetCoverageContract(_OperationBase):
    """设定 delivery 覆盖契约（只有用户可以降低要求）。"""

    op: Literal["set_coverage_contract"]
    graph: GraphKind | None = None
    contract: "CoverageContract"

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: Any) -> Any:
        if isinstance(data, dict) and "contract" not in data and isinstance(data.get("data"), dict):
            legacy = data["data"]
            data = {key: value for key, value in data.items() if key != "data"}
            data["contract"] = legacy.get("contract", legacy)
        return data


class WaiveGate(_OperationBase):
    """豁免一条覆盖缺口（只有用户可以豁免，豁免留在契约里供审计）。"""

    op: Literal["waive_gate"]
    graph: GraphKind | None = None
    waiver: "CoverageWaiver"

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: Any) -> Any:
        if isinstance(data, dict) and "waiver" not in data and isinstance(data.get("data"), dict):
            data = {**data, "waiver": data["data"]}
            del data["data"]
        return data


GraphOperation = Annotated[
    Union[
        AddNode,
        AddEdge,
        RemoveEdge,
        UpdateNode,
        UpdateEdge,
        AttachRef,
        AddLink,
        SetCoverageContract,
        WaiveGate,
    ],
    Field(discriminator="op"),
]

_OPERATION_ADAPTER = TypeAdapter(GraphOperation)


def parse_graph_operation(data: Any) -> GraphOperation:
    """解析一条 operation（新旧格式双兼容；迁移在各 op 类的 before-validator）。"""
    return _OPERATION_ADAPTER.validate_python(data)


class MechanismDraft(BaseModel):
    """Coordinator 提出的机理草稿：delivery-only ops + 每元素阶段契约。

    ``stage_contracts`` 的键必须解析到草稿自身 add 出的元素（harness 在
    propose 时校验引用完整性）。guided 下只有 Supervisor
    ``dag_accept_mechanism`` 落图；record 下 harness 自动接受（D1）。
    ``mechanism_accepted = EXISTS(dag_drafts WHERE state='accepted')``（D4）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    operations: list[GraphOperation] = Field(min_length=1)
    stage_contracts: dict[str, StageContract] = Field(default_factory=dict)
    rationale: str = ""
    state: Literal["open", "accepted", "rejected"] = "open"


class MutationBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(min_length=1)
    actor: GraphActor
    actor_id: str = Field(min_length=1)
    base_revisions: dict[str, int]
    operations: list[GraphOperation] = Field(min_length=1)
    rationale: str = ""


class MutationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    mutation_id: str
    revisions: dict[str, int]
    rejection_code: str | None = None
    rejection_reason: str | None = None


class CoverageWaiver(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    gate_code: str
    target_type: Literal["graph", "node", "edge"]
    target_id: str
    user_id: str
    session_id: str
    rationale: str = Field(min_length=1)


class CoverageContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    required_node_level: str = "structure_supported"
    required_edge_level: str = "endpoint_supported"
    require_branch_disposition: bool = True
    require_thermochemistry: bool = False
    waivers: list[CoverageWaiver] = Field(default_factory=list)

    @classmethod
    def mechanism_default(
        cls,
        *,
        require_thermochemistry: bool = False,
        waivers: list[CoverageWaiver] | None = None,
    ) -> "CoverageContract":
        return cls(
            require_thermochemistry=require_thermochemistry,
            waivers=waivers or [],
        )


class CoverageGateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    target_type: Literal["graph", "node", "edge"]
    target_id: str
    detail: str
    waiver: CoverageWaiver | None = None


class DeliveryReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    complete: bool
    satisfied: list[CoverageGateResult] = Field(default_factory=list)
    unresolved: list[CoverageGateResult] = Field(default_factory=list)
    inconclusive: list[CoverageGateResult] = Field(default_factory=list)
    waived: list[CoverageGateResult] = Field(default_factory=list)


# 投影头部的模式横幅与行为纪律：让 agent 明确自己处在哪种编排模式、
# 该模式下能做什么。只讲意图，不讲 op 细节——操作手册见 dag-operations skill。
_MODE_GUIDANCE = {
    OrchestrationMode.DAG_RECORD: (
        "Current orchestration mode: dag_record (DAG is recorded by the system; Supervisor is offline)\n"
        "- Your first delivery artifact is a mechanism proposal: dag_propose_mechanism (delivery draft + "
        "per-element stage contracts you choose). The harness auto-accepts it; no compute before that.\n"
        "- Run the task as usual afterwards; tool and compute results are recorded as evidence automatically.\n"
        "- Bind a finished call to a stage with dag_bind_evidence (tool_call_id, bind_target, stage_kind); "
        "stages bind strictly in contract order, ts_guess never satisfies ts_opt/frequency, and a "
        "submit_compute_job call is never evidence (bind the finished job's parser output)."
    ),
    OrchestrationMode.DAG_GUIDED: (
        "Current orchestration mode: dag_guided (DAG-guided orchestration; Supervisor is online)\n"
        "You must follow this orchestration discipline:\n"
        "1. Your first delivery artifact is a mechanism proposal: dag_propose_mechanism (delivery draft + "
        "per-element stage contracts — you choose which stages each element owes, in bind order). "
        "No compute runs before the Supervisor accepts the draft with dag_accept_mechanism.\n"
        "2. Work at your own pace afterwards — there is no frontier. Sub-agents run tools and report; "
        "they never write the graph. Structural changes (dag_add_species / dag_add_step / "
        "dag_update_delivery_element) wake the Supervisor for audit.\n"
        "3. Delivery-relevant calls land in the Supervisor's review inbox; it binds stages via "
        "dag_review_call. A disagree means the stage is still owed — re-run and let a later call be "
        "bound, or explicitly skip it with a reason. ts_guess is advisory and never satisfies "
        "ts_opt/frequency; a submit_compute_job call is never evidence.\n"
        "4. Delivery completeness is decided by stage coverage, not by your declaration; before "
        "stop(delivery_disposition=complete), self-check with dag_delivery_report: every required "
        "stage must be supported or skipped with a reason. If there are gaps, keep filling evidence "
        "or explicitly choose partial / user_terminated."
    ),
}

# dag_guided 下子 agent（follower）的模式引导：机理设计是 Coordinator 专属职责，
# 证据复核是 Supervisor 的；子 agent 只跑工具、报告结果（与子 agent prompt 的
# "You do not maintain the graph" 一致）。
_DAG_GUIDED_FOLLOWER_GUIDANCE = (
    "Current orchestration mode: dag_guided (DAG-guided orchestration; Supervisor is online)\n"
    "You are a sub-agent in this orchestration: the Coordinator designs the mechanism hypothesis "
    "and chooses stage contracts; the Supervisor reviews evidence. You do not maintain the graph. "
    "Your discipline:\n"
    "1. Run the tools your task requires and report results with concrete tool_call_ids and file "
    "paths; never write the graph yourself.\n"
    "2. Only post-completion artifacts count as stage evidence (parser output on a finished job); "
    "a submit_compute_job call or a ts_guess result is never proof of an optimized saddle point.\n"
    "3. If the Supervisor disagrees with your evidence, the stage is still owed — expect a re-run "
    "request from the Coordinator."
)

# dag_record 下子 agent（follower）的模式引导：机理设计与证据自绑是 Coordinator 专属职责；
# 子 agent 只跑工具、报告结果。
_DAG_RECORD_FOLLOWER_GUIDANCE = (
    "Current orchestration mode: dag_record (DAG is recorded by the system; Supervisor is offline)\n"
    "You are a sub-agent in this orchestration: the Coordinator designs the mechanism hypothesis, "
    "chooses stage contracts, and binds evidence. You do not maintain the graph. "
    "Your discipline:\n"
    "1. Run the tools your task requires and report results with concrete tool_call_ids and file "
    "paths; never write the graph yourself.\n"
    "2. Only post-completion artifacts count as stage evidence (parser output on a finished job); "
    "a submit_compute_job call or a ts_guess result is never proof of an optimized saddle point."
)

# 机理设计职责的持有者：Coordinator（a-0）。其余 actor 在 dag_guided / dag_record 下
# 投影 follower 版引导。
_COORDINATOR_ACTOR_IDS = frozenset({"a-0", "coordinator"})

# 阶段语义词典：随投影注入，让 Coordinator 与子 agent 对每个阶段的含义
# （尤其 endpoint_a/b 的端点定义）有共同理解，避免子 agent 凭直觉把
# endpoint_a/b 命名反了。stage list 的顺序即绑定顺序。
_STAGE_GLOSSARY = (
    "Delivery stage semantics (list order is the bind order):\n"
    "- geometry: optimized minimum structure of a species occurrence (0 imaginary frequencies).\n"
    "- frequency: frequency analysis — for a species, all real; for a step, exactly one imaginary.\n"
    "- single_point: a single-point energy of a species.\n"
    "- ts_guess: advisory scan/guess for a transition structure; NEVER satisfies ts_opt/frequency.\n"
    "- ts_opt: transition-state optimization converging to a first-order saddle point.\n"
    "- short_irc: an IRC path from the saddle connecting both sides.\n"
    "- endpoint_a: the TARGET-node side of the step (the product).\n"
    "- endpoint_b: the SOURCE-node side of the step (the reactant complex).\n"
    "- direction: the IRC direction/connectivity is consistent with the declared reaction coordinate.\n"
    "- identity: the endpoint's structure matches the declared species (SMILES/connectivity).\n"
    "- thermochemistry: energy corrections for the step.\n"
    "Stage statuses: pending (not yet bound); supported (evidence bound); "
    "skipped (the stage COULD be computed but you deliberately abandoned it — "
    "reason required, counts as disposed); not_applicable (the slot does not "
    "apply to this element — e.g. a barrierless step has no ts_opt/frequency, a "
    "unimolecular step has no endpoint_b complex — reason required, counts as "
    "complete and is NOT owed); rejected (binding failed — still an open gap, "
    "NOT a disposal)."
)


class DagProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: OrchestrationMode
    revisions: dict[str, int]
    delivery_gaps: list[dict[str, Any]] = Field(default_factory=list)
    recent_mutations: list[dict[str, Any]] = Field(default_factory=list)
    # 待 Supervisor 复核的调用（sidecar 摘要；guided 下 Coordinator 据此了解
    # 哪些证据在审）
    pending_reviews: list[dict[str, Any]] = Field(default_factory=list)
    # 最近被 Supervisor 驳回的机理草稿（draft_id/rationale/reject_reason）；
    # Coordinator 据此修订重提，否则驳回理由只躺在 dag_drafts 里无人读。
    rejected_draft: dict[str, Any] | None = None

    def to_prompt_text(self, actor_id: str | None = None) -> str:
        import json

        guidance = _MODE_GUIDANCE.get(
            self.mode, "Current orchestration mode: standard (no DAG orchestration; dag_* tools are unavailable)"
        )
        # dag_guided / dag_record 的完整版引导含机理设计职责，只对 Coordinator 投影；
        # 子 agent 投影 follower 版。actor_id 缺省（如直接构造投影）时保持完整版，向后兼容。
        if actor_id is not None and actor_id not in _COORDINATOR_ACTOR_IDS:
            if self.mode is OrchestrationMode.DAG_GUIDED:
                guidance = _DAG_GUIDED_FOLLOWER_GUIDANCE
            elif self.mode is OrchestrationMode.DAG_RECORD:
                guidance = _DAG_RECORD_FOLLOWER_GUIDANCE
        payload = self.model_dump(mode="json")
        # revisions 是存储层并发控制的内部状态，不投影给模型：
        # 写工具不传 base_revisions：由 harness 固定版本并自动重试。
        payload.pop("revisions", None)
        return (
            f"[DAG orchestration] {guidance}\n"
            f"{_STAGE_GLOSSARY}\n"
            "Graph projection (bounded, stable refs only, no compute body):\n"
            + json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )


GRAPH_POLICY_REVISION = "sha256:" + hashlib.sha256(
    b"cloudra-dag-policy-v1"
).hexdigest()


def normalize_orchestration_mode(
    value: str | OrchestrationMode | None,
) -> OrchestrationMode:
    if value is None:
        return OrchestrationMode.STANDARD
    if isinstance(value, OrchestrationMode):
        return value
    return OrchestrationMode(value)


def build_orchestration_config(
    mode: str | OrchestrationMode,
) -> dict[str, str]:
    normalized = normalize_orchestration_mode(mode)
    snapshot = {"orchestration_mode": normalized.value}
    if normalized is OrchestrationMode.STANDARD:
        return snapshot
    snapshot["graph_policy_revision"] = GRAPH_POLICY_REVISION
    if normalized is OrchestrationMode.DAG_GUIDED:
        from cloudra.core.supervisor import load_supervisor_prompt
        from cloudra.infra.config import get_config

        snapshot["supervisor_model"] = get_config().follower.model
        snapshot["supervisor_prompt_revision"] = "sha256:" + hashlib.sha256(
            load_supervisor_prompt().encode("utf-8")
        ).hexdigest()
    return snapshot
