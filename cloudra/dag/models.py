"""Shared types for DAG-guided orchestration."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class DagNode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    node_type: str
    label: str
    refs: list[GraphRef] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)


class DagEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: str
    label: str = ""
    refs: list[GraphRef] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)


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


OperationName = Literal[
    "add_node",
    "add_edge",
    "remove_edge",
    "update_node",
    "update_edge",
    "attach_ref",
    "add_link",
    "set_coverage_contract",
    "waive_gate",
]


class GraphOperation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    op: OperationName
    graph: GraphKind | None = None
    data: dict[str, Any] = Field(default_factory=dict)


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
# 该模式下能做什么、必须走什么流程（SOP 遵循与 Supervisor 拍板）。
_MODE_GUIDANCE = {
    OrchestrationMode.DAG_RECORD: (
        "当前编排模式: dag_record（DAG 由系统记录，Supervisor 不在线）\n"
        "- 按正常流程执行任务即可；工具与计算结果会被自动记入两张 DAG。\n"
        "- 若投影里出现 payload.assignee 等于你 agent id 的 process 节点，那是指派给你的"
        "工作：完成后立即用 dag_graph(action=mutate) 的 update_node 回报 status/reason"
        "（失败写 blocked_reason），不要等别人来问。\n"
        "- 你先于排产完成的计算已登记为证据；需要把它计入机理图时，用 attach_ref 挂到对应"
        "delivery 元素并带 evidence_role（8 个角色词见工具描述），系统会自动重算证据等级。"
    ),
    OrchestrationMode.DAG_GUIDED: (
        "当前编排模式: dag_guided（DAG 引导编排，Supervisor 在线）\n"
        "你必须遵守的编排纪律：\n"
        "1. 机理假设与计算方案由你设计，但方案出来必须先找 Supervisor 拍板："
        "用 dag_graph(action=mutate) 把机理假设（中间体、基元步骤）写入 delivery 图，"
        "并在 rationale 中说清拟开展的计算方案；变更被接受后 Supervisor 会被自动唤醒，"
        "审核方案并把计算工作排入 process 流程图。\n"
        "2. 只执行下方 frontier 中 status=ready 的计算任务；未经 Supervisor 排产的工作"
        "不要绕开流程图自行开算。\n"
        "3. 遵循机理研究 SOP，不跳步：反应映射 → TS 猜测 → TS 优化 + 唯一虚频确认 → "
        "IRC → 端点优化与匹配 → 热化学分析。\n"
        "4. 交付完成由图上证据决定，不由你的声明决定；stop(delivery_disposition=complete) "
        "之前先用 dag_graph(action=delivery_report) 自查，有缺口就继续补证或显式选 "
        "partial / user_terminated。"
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

    def to_prompt_text(self) -> str:
        import json

        guidance = _MODE_GUIDANCE.get(
            self.mode, "当前编排模式: standard（无 DAG 编排，dag_graph 工具不可用）"
        )
        payload = self.model_dump(mode="json")
        return (
            f"【DAG 编排】{guidance}\n"
            "图投影（有界，仅稳定引用，不含计算正文）:\n"
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
