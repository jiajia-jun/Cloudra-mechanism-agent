"""Benchmark task JSON schema — single source of truth for benchmark task specs.

A benchmark task JSON describes two things only: what to feed the agent
(`prompt`, `system`, `method_policy`) and what to deterministically score
against after the run (`gold`, `rubric`). It never pre-declares the DAG stage
contract — declaring stages is the agent's job and pre-declaring would leak
the answer.

Alignment with existing types:
- `PromptSpec.orchestration_mode` reuses `runtime_v2.schemas.OrchestrationMode`.
- `GoldMechanismGraph` nodes/edges mirror the delivery-graph projection
  (occurrence nodes / elementary-step edges) so a DAG-mode delivery graph can
  be projected into the same shape for comparison.
- `RubricSpec.self_consistency` stage kinds reuse `dag.models.StageKind`.

The scoring side reads `gold` + `rubric`; the agent side reads only
`prompt` + the agent-visible slice of `system` (SMILES / charge / multiplicity
/ conditions) + the allowed-methods slice of `method_policy`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cloudra.runtime_v2.schemas import MethodPolicy, OrchestrationMode

# GH #25：MethodPolicy 模型已上移到 runtime_v2.schemas（per-project live
# 拦截与 benchmark 任务共用），此处转引保持 benchmark 侧导入路径不变。


class Tier(str, Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    IMPOSSIBLE = "impossible"


# ---------------------------------------------------------------------------
# Mechanism graph (shared by gold reference and the agent-delivered graph)
# ---------------------------------------------------------------------------


class NodeRole(str, Enum):
    REACTANT = "reactant"
    PRODUCT = "product"
    INTERMEDIATE = "intermediate"
    TRANSITION_STATE = "transition_state"


class MechanismNode(BaseModel):
    """One species occurrence or transition state in a mechanism graph.

    点连接的单条 SMILES（``["C=O.CN"]``）表示络合物；多个列表成员
    （``["C=O", "CN"]``）表示分离物种。解析保留该区别，不自动合并。
    `accessible=false` 声明该物种/TS 在允许的方法级别下不可达：图分只要求标志
    与 gold 一致（不一致等同缺失），不要求证据绑定。

    `properties` 是交付侧结构化性质声明（impossible 性质/态序题）：键自带单位
    （如 ``bond_length_angstrom``、``singlet_triplet_gap_kcal_mol``），值为数值
    或字符串（``state_ordering`` 等描述性条目）。评分器只读这个字典，不解析
    最终消息散文。
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    role: NodeRole
    smiles: list[str] = Field(default_factory=list)
    accessible: bool = True
    # 交付侧可达性声明的来源：top_level（规范形状）、properties（agent 把
    # accessible 写在 properties 里的历史形状，加载时提升到顶层）、default
    # （两处都没写，按默认 accessible=true 处理）。gold 侧恒为 top_level。
    # 只作诊断/报告用，不参与任何评分口径。
    accessible_source: Literal["top_level", "properties", "default"] = "top_level"
    label: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class BondChangeSet(BaseModel):
    """Bond changes for one elementary step, as atom-mapped index pairs.

    `break_`/`form` hold [i, j] atom-mapped index pairs (1-based). The index
    convention is fixed per task by the atom-mapped reactant SMILES shown to
    the agent in the query (`gen_easy_tasks._MAPPED_REACTANTS`), and gold edges
    use the same numbers, so agent and gold bond change sets are directly
    comparable. A pair belongs to `break` if the bond order between the two
    atoms decreases over the step (including full cleavage), to `form` if it
    increases (including newly formed bonds); purely conformational/inversion
    steps carry two empty lists. The symmetric difference of two steps' bond
    change sets is the GED edge-substitution cost.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    break_: list[list[int]] = Field(default_factory=list, alias="break")
    form: list[list[int]] = Field(default_factory=list)

    def pairs(self) -> frozenset[tuple[int, int, str]]:
        out: set[tuple[int, int, str]] = set()
        for i, j in self.break_:
            out.add((min(i, j), max(i, j), "break"))
        for i, j in self.form:
            out.add((min(i, j), max(i, j), "form"))
        return frozenset(out)


class MechanismEdge(BaseModel):
    """One elementary step connecting two species nodes via a TS node.

    ``barrier_kcal_mol`` 逐边承载能垒（kcal/mol，相对对应稳定中间体；easy 单步
    题即"相对反应物络合物"）：gold 侧 = 参考答案能垒，交付侧 = agent 声明的值。
    评分不读最终消息散文：harness 从交付日志逐边推出能垒，gold 边与交付步
    **按端点物种对应匹配**（gold 的 ``<任务>_E<n>`` 边 id 是题库内部约定、
    agent 不可知，绝不参与匹配），逐条要求声明值与推算值都存在且一致
    （复用 accuracy 容差），缺一或冲突的边 fail-loud（accuracy 层置
    ``fail_loud`` 标记，runner 据此短路 composite）。

    ``weight`` 是 gold 侧逐边评分权重（越难算准/越不可核实的边权重越小，逐边
    分数按此加权平均）；交付侧忽略。

    ``channel``/``favored`` 是 hard 档选择性交付字段：竞争立体化学通道的每条
    边声明通道标签（``channel``）与该通道是否被计算能垒支持为优势通道
    （``favored``）；favored-channel 归属定性计分（对错），能垒差数值只记录。
    """

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    id: str = Field(min_length=1)
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    via: Optional[str] = None  # transition-state node id
    step_type: str = ""        # e.g. "concerted_[4+2]", "SN2_backside"
    bond_changes: BondChangeSet = Field(default_factory=BondChangeSet)
    accessible: bool = True
    # 同 MechanismNode.accessible_source：边级可达性声明的来源，仅诊断用。
    accessible_source: Literal["top_level", "properties", "default"] = "top_level"
    barrier_kcal_mol: Optional[float] = None
    weight: float = 1.0
    channel: Optional[str] = None
    favored: Optional[bool] = None


class GoldMechanismGraph(BaseModel):
    """机理图（gold 参考与交付图共用形状）。

    端点引用完整性：每条边的 from/to 必须指向已声明节点 id；via 非空时必须
    指向已声明的 transition_state 角色节点——违反即 ValidationError（gold
    侧 fail-loud；交付侧加载随之失败，不再静默造幽灵节点进图比较）。"""

    model_config = ConfigDict(frozen=True, extra="ignore")

    nodes: list[MechanismNode]
    edges: list[MechanismEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _edge_references_declared(self) -> "GoldMechanismGraph":
        roles = {n.id: n.role for n in self.nodes}
        for e in self.edges:
            for endpoint in (e.from_node, e.to_node):
                if endpoint not in roles:
                    raise ValueError(
                        f"edge {e.id}: endpoint {endpoint!r} is not a declared node"
                    )
            if e.via and roles.get(e.via) is not NodeRole.TRANSITION_STATE:
                raise ValueError(
                    f"edge {e.id}: via {e.via!r} is not a declared "
                    "transition_state node"
                )
        return self

    def edge_effectively_accessible(self, edge: MechanismEdge) -> bool:
        """边的有效可达性：``edge.accessible`` 且经由的 TS 节点（``via``）也可达。

        gold 和交付均可把不可达标在节点或边上；正式 IMP 负边显式标为 false。
        两侧同口径折叠成「有效可达性」再判定：经由不可达
        TS 的步在允许方法下同样算不了，视同不可达边；``via`` 为空的边不做端点
        检查。图分的标志一致性闸门、accuracy 的无参考边 1.0/0.0 规则、自洽的边
        豁免三处统一走这个口径，不得各抄一份。"""
        if not edge.accessible:
            return False
        if edge.via is None:
            return True
        via = next((n for n in self.nodes if n.id == edge.via), None)
        # validator 已保证 via 指向已声明的 TS 节点；防御性分支按不可达计
        return bool(via is not None and via.accessible)


# ---------------------------------------------------------------------------
# prompt / system / method_policy
# ---------------------------------------------------------------------------


class PromptSpec(BaseModel):
    """What is fed to the agent. `query` must explicitly instruct the agent to
    maintain `mechanism_graph.json` in the sandbox root (no冤枉分: the agent
    can never claim it did not know it had to write the graph)."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    role: str = "coordinator"
    orchestration_mode: OrchestrationMode = OrchestrationMode.DAG_GUIDED


class SystemSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reactants: list[str] = Field(min_length=1)
    products: list[str] = Field(default_factory=list)
    charge: int = 0
    multiplicity: int = Field(default=1, ge=1)
    conditions: str = "gas phase"
    elements: list[str] = Field(default_factory=list)
    max_heavy_atoms: Optional[int] = None
    closed_shell: bool = True
    single_step: bool = True


# ---------------------------------------------------------------------------
# gold reference
# ---------------------------------------------------------------------------


class SelectivityReference(BaseModel):
    """Hard 档选择性锚点：两个竞争非对映过渡态的能垒差（副通道 TS − 主通道 TS，
    同一反应物络合物基准），不是绝对能垒——绝不要塞进 barrier_kcal_mol
    （类型记号仍是 ΔΔG‡/ΔΔE‡ 等差值）。gold 机理图把两条竞争通道都带上；
    当前只作参考记录（spread 数值不评分）。

    `minor_channel` 描述副通道（如 "inward rotation -> (Z)-diene"）。
    `favored_channel` 是 gold 侧优势通道标签，与交付边 ``channel`` 字段同口径
    （定性计分：agent 声明的 favored 边标签与它对齐即对）。"""

    model_config = ConfigDict(extra="forbid")

    spread_kcal_mol: Optional[float] = None
    minor_channel: str = ""
    favored_channel: str = ""


class GoldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanism_graph: GoldMechanismGraph
    # 性质类参考答案（impossible 性质/态序题）：键自带单位，与交付侧
    # MechanismNode.properties 同构；缺值留空待文献回填，不编造
    reference_properties: dict[str, float | str] = Field(default_factory=dict)
    # hard 档选择性锚点（ΔΔ，仅作定性记录）
    selectivity: Optional[SelectivityReference] = None


# ---------------------------------------------------------------------------
# rubric (scoring rules)
# ---------------------------------------------------------------------------


class IntegrityRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 全绑阈值：指纹/哈希 cost ≤ 此值记质量 1.0。超过时查质子化骨架——仅
    # 电荷态/质子化形式不同的变体按可变 partial 记分（质量 = 1-(1-锚点)·w，
    # w = 指纹相对误差 1-Tanimoto；protonation_partial_quality 是最差锚点，
    # 即指纹完全退化时的质量），其余不绑。逐节点质量图并入图分（runner 传给
    # mechanism_similarity：未绑定的 accessible 节点按代价 1.0 记账）。
    match_threshold: float = 0.2
    protonation_partial_quality: float = 0.7
    # 零证据倒扣分（负分下限）：图缺失/不可解析，或没有任何 accessible 物种
    # 节点绑到证据时，final = -no_evidence_penalty。缺部分证据不触发本条
    # （逐节点质量并进图分扣），只有"完全没有证据支撑"才倒扣；交付图所有
    # 节点都声明 accessible=false 是合法交付，不触发。
    no_evidence_penalty: float = 1.0


class SelfConsistencyRubric(BaseModel):
    """Layer 2 物理自检。物种身份（SMILES 一致性）由 Layer 1 的证据绑定承担，
    不在此重复检查。

    TS 合格判定仅由 n_imag == 1（一阶鞍点）与同一 TS 双向 IRC 的真实外帧
    经实际优化到正确零虚频极小值的方向证明（irc_connects_endpoints）构成。
    IRC 本身无需收敛到底；虚频模式对齐与几何区间仅作诊断，不决定验收。
    不设任何虚频绝对值下限。"""

    model_config = ConfigDict(extra="forbid")

    ts_first_order_saddle: bool = True   # n_imag == 1
    irc_connects_endpoints: bool = True


class GraphSimilarityRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stereo_tier_rule: Literal[
        "easy_normal_stereo_free", "hard_stereo_costly"
    ] = "easy_normal_stereo_free"


class AccuracyRubric(BaseModel):
    """Gaussian-tolerance barrier scoring. `sigma_kcal_mol` is per-task (not
    global); `enabled=false` 表示本题可算但不评（accuracy 分量直通 1.0）。
    `max_penalty_fraction` caps how much accuracy can cost (avoid
    over-penalizing legitimate method-level differences).

    小能垒口径：gold ≤ `small_barrier_threshold_kcal` 时 RDS 对 gold 的
    比较高斯宽度放宽到 `small_barrier_sigma_kcal`（低能垒的文献锚点与
    DFT 电子能口径天然差几个 kcal，3 kcal 的 sigma 会把物理上正确的
    答案压到不及格）。声明值 vs 日志推算值的内部一致性核对不放宽。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    sigma_kcal_mol: float = 3.0
    # 只封顶带参考值边（高斯偏离/定义差异）的罚分；无参考边的 1.0/0.0 结构
    # 记账按面值计（见 accuracy.py 汇总段）
    max_penalty_fraction: float = 0.3
    small_barrier_threshold_kcal: float = 10.0
    small_barrier_sigma_kcal: float = 5.0


class RubricSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integrity: IntegrityRubric = Field(default_factory=IntegrityRubric)
    self_consistency: SelfConsistencyRubric = Field(
        default_factory=SelfConsistencyRubric
    )
    graph_similarity: GraphSimilarityRubric = Field(
        default_factory=GraphSimilarityRubric
    )
    accuracy: AccuracyRubric = Field(default_factory=AccuracyRubric)


# ---------------------------------------------------------------------------
# top-level task
# ---------------------------------------------------------------------------


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # task_id 会被拼进沙箱路径并整目录删除（runner.run_task），必须挡住路径逃逸
    task_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    tier: Tier
    family: str = ""
    name: str = ""
    prompt: PromptSpec
    system: SystemSpec
    method_policy: MethodPolicy = Field(default_factory=MethodPolicy)
    gold: GoldSpec
    rubric: RubricSpec = Field(default_factory=RubricSpec)


def complex_smiles(components: list[str]) -> list[str]:
    """生成器显式声明现有题库的络合物；schema 保留输入的物种分组。"""
    if len(components) <= 1:
        return list(components)
    return [".".join(components)]
