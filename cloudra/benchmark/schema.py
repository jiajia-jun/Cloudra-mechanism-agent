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
from typing import Literal, Optional

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

    `smiles` is a list because a node may be a multi-species complex
    (reactant complex, ion-dipole complex). `accessible=false` is the
    impossible-tier annotation: the species/TS is physically unreachable at the
    allowed level of theory.

    `properties` 是交付侧结构化性质声明（impossible 性质/态序题）：键自带单位
    （如 ``bond_length_angstrom``、``singlet_triplet_gap_kcal_mol``），值为数值
    或字符串（``state_ordering`` 等描述性条目）。评分器只读这个字典，不解析
    最终消息散文。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    role: NodeRole
    smiles: list[str] = Field(default_factory=list)
    accessible: bool = True
    label: str = ""
    properties: dict[str, float | str] = Field(default_factory=dict)


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

    ``barrier_kcal_mol`` 逐边承载能垒（kcal/mol，相对该步起点最小值；easy 单步
    题即"相对反应物络合物"）：gold 侧 = 参考答案能垒，交付侧 = agent 声明的值。
    评分不读最终消息散文：harness 从交付日志逐边推出能垒，gold 边与交付步
    **按端点物种对应匹配**（gold 的 ``<任务>_E<n>`` 边 id 是题库内部约定、
    agent 不可知，绝不参与匹配），逐条要求声明值与推算值都存在且一致
    （复用 accuracy 容差），缺一或冲突的边 fail-loud 记 0 分。

    ``weight`` 是 gold 侧逐边评分权重（越难算准/越不可核实的边权重越小，逐边
    分数按此加权平均）；交付侧忽略。

    ``channel``/``favored`` 是 hard 档选择性交付字段：竞争立体化学通道的每条
    边声明通道标签（``channel``）与该通道是否被计算能垒支持为优势通道
    （``favored``）；favored-channel 归属定性计分（对错），能垒差数值只记录。
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: str = Field(min_length=1)
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    via: Optional[str] = None  # transition-state node id
    step_type: str = ""        # e.g. "concerted_[4+2]", "SN2_backside"
    bond_changes: BondChangeSet = Field(default_factory=BondChangeSet)
    accessible: bool = True
    barrier_kcal_mol: Optional[float] = None
    weight: float = 1.0
    channel: Optional[str] = None
    favored: Optional[bool] = None


class RefusalDeclaration(BaseModel):
    """交付的拒答声明（可选字段）。

    impossible 档与兄弟题共用同一句协议：无法可信计算时，交付
    ``mechanism_graph.json`` 且内容为 ``{"refusal": {"refused": true,
    "reason": "..."}}``，而不是机理图。拒答分类只读这个结构化声明与交付图
    是否存在，绝不解析最终消息散文。
    """

    model_config = ConfigDict(extra="ignore")

    refused: bool = False
    reason: str = ""


class GoldMechanismGraph(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: list[MechanismNode]
    edges: list[MechanismEdge] = Field(default_factory=list)


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


class ExpectedOutcome(str, Enum):
    MECHANISM_FOUND = "mechanism_found"
    MECHANISM_WITH_INACCESSIBLE = "mechanism_with_inaccessible_nodes"
    CORRECT_REFUSAL = "correct_refusal"


class IntegrityRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require_graph_json: bool = True
    require_evidence_files: bool = True
    # 证据绑定方式：当前实现是 smiles 注释匹配（交付协议要求证据文件携带
    # `smiles:` 注释行）；parse_structure_from_file 为保留档位，未实现。
    evidence_match: Literal["smiles_annotation", "parse_structure_from_file"] = (
        "smiles_annotation"
    )
    # 全绑阈值：指纹/哈希 cost ≤ 此值记质量 1.0。超过时查质子化骨架——仅
    # 电荷态/质子化形式不同的变体按可变 partial 记分（质量 = 1-(1-锚点)·w，
    # w = 指纹相对误差 1-Tanimoto；protonation_partial_quality 是最差锚点，
    # 即指纹完全退化时的质量），其余不绑。binding_quality（平均质量）作为
    # composite 的乘性因子进入 runner。
    match_threshold: float = 0.2
    protonation_partial_quality: float = 0.7
    # 零证据倒扣分（负分下限）：图缺失/不可解析/没有任何节点绑到证据时，
    # final = -no_evidence_penalty。缺部分证据不触发本条（走 binding_quality
    # 比例扣），只有"完全没有证据支撑"才倒扣。
    no_evidence_penalty: float = 1.0


class SelfConsistencyRubric(BaseModel):
    """Layer 2 物理自检。物种身份（SMILES 一致性）由 Layer 1 的证据绑定承担，
    不在此重复检查。

    TS 合格判定仅由 n_imag == 1（一阶鞍点）与 IRC 方向区间证明
    （irc_connects_endpoints，ts_guess strict 同口径：不要求收敛到极小值，
    但双侧端点几何须各自位于 TS 与端点验证极小值之间；几何判定唯一实现
    在 tools/core/irc_path.py）构成；不设任何虚频绝对值下限。
    min_abs_imag_freq_cm1 已按用户决策移除——虚频大小是否"合适"交由 IRC
    方向证明/虚频方向判断，两者由验证层（ts_guess/IRC）实现，本层不再引入
    虚频大小下限判断。"""

    model_config = ConfigDict(extra="forbid")

    ts_first_order_saddle: bool = True   # n_imag == 1
    irc_connects_endpoints: bool = True


class GraphSimilarityRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["chemical_parameterized_ged"] = "chemical_parameterized_ged"
    # 子图打分：交付图覆盖 gold 即满分，多出的节点/边不罚（多想总是好事）。
    subgraph_scoring: bool = True
    node_cost: str = "molhash_shortcut_then_morgan_sigmoid"
    sigmoid_center: float = 0.40
    sigmoid_steepness: Optional[float] = None
    stereo_tier_rule: Literal[
        "easy_normal_stereo_free", "hard_stereo_costly"
    ] = "easy_normal_stereo_free"
    edge_cost: str = "bond_change_symmetric_difference"
    output: list[str] = Field(default_factory=lambda: ["scalar_score", "edit_script"])


class AccuracyRubric(BaseModel):
    """Gaussian-tolerance barrier scoring. `sigma_kcal_mol` is per-task (not
    global); `enabled=false` means this task is scored on self-consistency
    only. `max_penalty_fraction` caps how much accuracy can cost (avoid
    over-penalizing legitimate method-level differences).

    小能垒口径：gold ≤ `small_barrier_threshold_kcal` 时 RDS 对 gold 的
    比较高斯宽度放宽到 `small_barrier_sigma_kcal`（低能垒的文献锚点与
    DFT 电子能口径天然差几个 kcal，3 kcal 的 sigma 会把物理上正确的
    答案压到不及格）。声明值 vs 日志推算值的内部一致性核对不放宽。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    barrier_scoring: Literal["gaussian"] = "gaussian"
    sigma_kcal_mol: float = 3.0
    max_penalty_fraction: float = 0.3
    small_barrier_threshold_kcal: float = 10.0
    small_barrier_sigma_kcal: float = 5.0


class ImpossibleCaseRubric(BaseModel):
    """Impossible 档 rubric（expected_outcome 为拒答/含不可达节点的题必填）。

    判分哲学（impossible.md "定稿圈定"）：不内嵌"合理拒答"定义——本 rubric
    只携带结构性事实（哪些 gold 节点在允许方法下不可达、错误作答的惩罚档位、
    出题证据强度），拒答理由质量留给 judge 层。`evidence_strength` 区分铁板
    MR 题（"ironclad"，文献多参考计算直接背书）与灰色地带题（"gray_zone"，
    多参考论断为机理外推、无专门高等级计算背书——直接给分方案下这些题只进
    跨档校准矩阵，judge 评估必须连同证据强度一并给出）。"""

    model_config = ConfigDict(extra="forbid")

    require_inaccessible_annotation: bool = True
    gold_inaccessible_nodes: list[str] = Field(default_factory=list)
    scoring: str = "identify_mechanism AND flag_inaccessible"
    wrongly_solve_penalty: Literal["high", "medium", "low"] = "high"
    evidence_strength: Literal["ironclad", "gray_zone"] = "ironclad"


class RubricSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_outcome: ExpectedOutcome = ExpectedOutcome.MECHANISM_FOUND
    integrity: IntegrityRubric = Field(default_factory=IntegrityRubric)
    self_consistency: SelfConsistencyRubric = Field(
        default_factory=SelfConsistencyRubric
    )
    graph_similarity: GraphSimilarityRubric = Field(
        default_factory=GraphSimilarityRubric
    )
    accuracy: AccuracyRubric = Field(default_factory=AccuracyRubric)
    impossible_case: Optional[ImpossibleCaseRubric] = None

    @model_validator(mode="after")
    def _impossible_requires_case(self) -> "RubricSpec":
        if (
            self.expected_outcome
            in (
                ExpectedOutcome.MECHANISM_WITH_INACCESSIBLE,
                ExpectedOutcome.CORRECT_REFUSAL,
            )
            and self.impossible_case is None
        ):
            raise ValueError(
                "impossible-tier outcomes require impossible_case to be set"
            )
        return self


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
    # 兄弟题配对（impossible 档专用）：本题 task_id ↔ 对照题 task_id 双向互指。
    # 本档信号 = 本题拒答 × 兄弟题正常作答，runner 同批发次时据此配对分析。
    pair_id: Optional[str] = None
    prompt: PromptSpec
    system: SystemSpec
    method_policy: MethodPolicy = Field(default_factory=MethodPolicy)
    gold: GoldSpec
    rubric: RubricSpec = Field(default_factory=RubricSpec)


def complex_smiles(components: list[str]) -> list[str]:
    """多组分体系以络合物（点连接的单条 SMILES）表达；单组分原样返回。

    query 协议要求机理图从反应物络合物起步（与 query 展示的 Reactant
    SMILES 同形）；gold 的 R/P 节点必须用同一形态——组分列表形态会让遵循
    协议的交付图在子图覆盖评分里被判为不同物种（毒 gold）。
    """
    if len(components) <= 1:
        return list(components)
    return [".".join(components)]
