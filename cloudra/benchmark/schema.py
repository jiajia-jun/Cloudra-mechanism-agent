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

from cloudra.runtime_v2.schemas import OrchestrationMode


class Tier(str, Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    IMPOSSIBLE = "impossible"


class BarrierType(str, Enum):
    EA = "Ea"          # Arrhenius activation energy
    DH = "ΔH‡"         # activation enthalpy
    DE = "ΔE‡"         # electronic barrier
    DG = "ΔG‡"         # activation free energy


class BarrierReference(str, Enum):
    """能垒锚点的参考系。双阱型离子-分子反应里"中央能垒"（TS 相对离子-偶极
    络合物）与"TS 相对反应物渐近线"相差一个络合物阱深，必须分开记录，
    否则同一体系的两个口径会被误判成 ~10 kcal/mol 的偏差。easy 档统一记
    CENTRAL（反应物络合物口径；登记细节见 gen_easy_tasks）。"""

    CENTRAL = "central_complex"  # TS relative to the ion-dipole complex
    REACTANTS = "reactants"      # TS relative to the separated reactants


class VerificationStatus(str, Enum):
    VERIFIED = "verified"          # literature confirmed via web search
    PARTIAL = "partial"            # literature exists, numbers from memory
    UNVERIFIED = "unverified"      # source from memory, must recheck
    COMPUTED_BY_US = "computed_by_us"  # we computed the reference ourselves


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
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    role: NodeRole
    smiles: list[str] = Field(default_factory=list)
    accessible: bool = True
    label: str = ""


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
    """One elementary step connecting two species nodes via a TS node."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: str = Field(min_length=1)
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    via: Optional[str] = None  # transition-state node id
    step_type: str = ""        # e.g. "concerted_[4+2]", "SN2_backside"
    bond_changes: BondChangeSet = Field(default_factory=BondChangeSet)
    accessible: bool = True


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


class MethodPolicy(BaseModel):
    """Whitelisted computation levels: any method not in `allowed_methods` is
    blocked. A blacklist can always be bypassed, so interception is strictly
    positive (whitelist) matching, wired in at the layers named by
    `intercept_layers`:
    - `qm_input_writer`: structured computation entry with an explicit
      method field.
    - `submit_compute_job`: submits a prepared input file, so interception
      parses that file's content (Gaussian route card / ORCA keyword lines).
    - `bash`: the *content* of QM input files being written or executed is
      parsed the same way — the raw command text is never keyword-scanned.

    The easy-tier whitelist (MACE-OMol25 / xTB) has no basis-set concept at
    all, so the policy carries no basis fields. Whitelist matching happens at
    method-*family* granularity (any `mace-*` token matches the MACE entry, any
    token containing `xtb` matches the xTB entry): route-card text cannot
    distinguish MLIP model variants (mace-omol25 vs mace-off), so variant-level
    enforcement is out of band, at the method-provisioning side. Attempting a
    non-whitelisted method is intercepted, never penalized."""

    model_config = ConfigDict(extra="forbid")

    allowed_methods: list[str] = Field(
        default_factory=lambda: ["mace-omol25", "xtb"]
    )
    intercept_layers: list[str] = Field(
        default_factory=lambda: ["bash", "submit_compute_job", "qm_input_writer"]
    )


# ---------------------------------------------------------------------------
# gold reference
# ---------------------------------------------------------------------------


class ReferenceComputation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level_of_theory: str = ""
    barrier_kcal_mol: Optional[float] = None
    # 源文档未显式注明类型/口径时保持 None（诚实缺测），不默认贴 Ea 标签
    barrier_type: Optional[BarrierType] = None
    barrier_reference: Optional[BarrierReference] = None
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    reference_doi: str = ""
    computed_by_us: bool = False


class SelectivityReference(BaseModel):
    """Hard 档选择性锚点：两个竞争非对映过渡态的能垒差（副通道 TS − 主通道 TS，
    同一反应物络合物基准），不是绝对能垒——绝不要塞进 barrier_kcal_mol
    （类型记号仍是 ΔΔG‡/ΔΔE‡ 等差值）。gold 机理图把两条竞争通道都带上，
    accuracy 层对该差值的高斯容差评分待 runner 支持；当前只作参考记录。

    `minor_channel` 描述副通道（如 "inward rotation -> (Z)-diene"）。"""

    model_config = ConfigDict(extra="forbid")

    spread_kcal_mol: Optional[float] = None
    spread_type: Optional[BarrierType] = None
    minor_channel: str = ""
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    reference_doi: str = ""
    computed_by_us: bool = False


class GoldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanism_graph: GoldMechanismGraph
    reference_computation: ReferenceComputation = Field(
        default_factory=ReferenceComputation
    )
    # hard 档选择性锚点（ΔΔ）；绝对能垒锚点仍走 reference_computation
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

    TS 合格判定仅由 n_imag == 1（一阶鞍点）与 IRC 连通性
    （irc_connects_endpoints）构成；不设任何虚频绝对值下限。
    min_abs_imag_freq_cm1 已按用户决策移除——虚频大小是否"合适"交由 IRC
    连通性/虚频方向判断，两者由验证层（ts_guess/IRC）实现，本层不再引入
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
    over-penalizing legitimate method-level differences)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    barrier_scoring: Literal["gaussian"] = "gaussian"
    sigma_kcal_mol: float = 3.0
    max_penalty_fraction: float = 0.3


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
