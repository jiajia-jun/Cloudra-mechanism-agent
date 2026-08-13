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


# process 图节点 status 的规范词表：frontier/blockers 投影只认这些值
# （completion.build_projection）。类型即校验：模型写出词表外的值在
# schema 层直接被拒，不再靠引擎同义词归一化兜底。
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

        只为序列化视图（service.dag_graph / 子图 view / TUI）保留旧外形；
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
        "- Run the task as usual; tool and compute results are recorded into both DAGs automatically.\n"
        "- If the projection shows a process node whose assignee equals your agent id, that work is assigned to you; "
        "success/failure is reported automatically. Use dag_graph update_node when you need extra notes.\n"
        "- To attach existing unplanned evidence to the mechanism graph, use dag_graph bind_evidence "
        "(tool_call_id, target, evidence_role); the system verifies success and rederives evidence level."
    ),
    OrchestrationMode.DAG_GUIDED: (
        "Current orchestration mode: dag_guided (DAG-guided orchestration; Supervisor is online)\n"
        "You must follow this orchestration discipline:\n"
        "1. You design the mechanism hypothesis and compute plan: use dag_graph mutate to write the hypothesis "
        "(intermediates, elementary steps) into the delivery graph, with rationale explaining the compute plan. "
        "After the change is accepted, Supervisor is woken automatically to review the plan and schedule compute "
        "work onto the process graph.\n"
        "2. Only execute compute tasks in the frontier below: frontier = planned nodes whose dependencies are met "
        "and whose status is `proposed` or `ready` (do not use status_filter=ready alone — many scheduled nodes "
        "enter the frontier as proposed). Dispatch or run by node assignee (a legal sub-agent id such as a-4). "
        "After a successful compute, use dag_graph bind_evidence to attach the result to the matching "
        "mechanism-graph element (evidence authenticity and level are verified and derived by the system; "
        "Supervisor review may veto, and a veto is delivered to you as an event).\n"
        "3. Follow the mechanism-research SOP without skipping steps: reaction mapping → TS guess → "
        "TS optimization + unique imaginary-frequency confirmation → IRC → endpoint optimization and matching → "
        "thermochemistry.\n"
        "4. Delivery completeness is decided by graph evidence, not by your declaration; before "
        "stop(delivery_disposition=complete), self-check with dag_graph(action=delivery_report). If there are gaps, "
        "keep filling evidence or explicitly choose partial / user_terminated."
    ),
}


class DagProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: OrchestrationMode
    revisions: dict[str, int]
    frontier: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    delivery_gaps: list[dict[str, Any]] = Field(default_factory=list)
    recent_mutations: list[dict[str, Any]] = Field(default_factory=list)
    # 按 assignee == actor_id 过滤出的"派给我的"节点：
    # 子 agent 回报路径的一等入口，免从 frontier/blockers 里自行筛选
    assigned_to_me: list[dict[str, Any]] = Field(default_factory=list)

    def to_prompt_text(self) -> str:
        import json

        guidance = _MODE_GUIDANCE.get(
            self.mode, "Current orchestration mode: standard (no DAG orchestration; dag_graph is unavailable)"
        )
        payload = self.model_dump(mode="json")
        # revisions 是存储层并发控制的内部状态，不投影给模型：
        # mutate 不传 base_revisions 时由 harness 固定版本并自动重试。
        payload.pop("revisions", None)
        return (
            f"[DAG orchestration] {guidance}\n"
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
        from cloudra.core.supervisor import SUPERVISOR_SYSTEM_PROMPT
        from cloudra.infra.config import get_config

        snapshot["supervisor_model"] = get_config().follower.model
        snapshot["supervisor_prompt_revision"] = "sha256:" + hashlib.sha256(
            SUPERVISOR_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest()
    return snapshot
