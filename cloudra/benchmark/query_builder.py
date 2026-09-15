"""Benchmark Query Builder utilities.

Prompt generation must be parameter-driven rather than hardcoding specific
computational methods or engines into template strings.
"""

from collections.abc import Sequence

# mechanism_graph.json 的字段级契约示例：题面 prompt 里给出具体键名，agent 不再
# 靠猜（生产教训：type/role 双写撞 NodeRole 枚举 → 整图被评成 unparseable）。
# 示例块在题面中独立成句——前置契约句必须先说完，再给出示例，最后补注。
GRAPH_JSON_EXAMPLE = (
    "Use exactly this JSON shape (key names matter: nodes carry `id`, `role` "
    "(one of reactant/intermediate/product/transition_state) and `smiles` (a list "
    "of SMILES strings), and may optionally carry a `properties` object for "
    "declared quantities; edges carry `id`, `from`, `to`, `via`, `bond_changes` "
    "and optionally `barrier_kcal_mol`, `channel` and `favored`): "
    '{"nodes": [{"id": "RC", "role": "reactant", "smiles": ["..."]}, '
    '{"id": "TS1", "role": "transition_state", "smiles": []}, '
    '{"id": "P", "role": "product", "smiles": ["..."]}], '
    '"edges": [{"id": "e1", "from": "RC", "to": "P", "via": "TS1", '
    '"bond_changes": {"break": [[1, 2]], "form": [[1, 5]]}, '
    '"barrier_kcal_mol": 21.3}]}. '
)

# 能垒交付契约（easy/normal/hard 共用；impossible 的机理类交付句同样引用其中的
# 能量类型声明）：能量类型必须是电子能差 ΔE‡——不含 ZPE 与热校正，各自相对该步
# 起点最小值（双分子：预反应络合物）。
BARRIER_DECLARATION_CLAUSE = (
    "Declare every barrier you actually compute in kcal/mol on that elementary "
    "step's edge as `barrier_kcal_mol` in mechanism_graph.json. Barriers are "
    "electronic energy differences (ΔE‡) in kcal/mol, without ZPE or thermal "
    "corrections, each relative to that step's own starting minimum: for a "
    "bimolecular reaction that minimum is the reactant complex (e.g. the "
    "ion-dipole complex), and for a unimolecular process it is simply the "
    "reactant minimum. The scorer derives every declared step barrier from "
    "your log files and takes the highest as the rate-determining step; a "
    "barrier that is undeclared, has no bound ORCA/Gaussian log, or disagrees "
    "with those logs is not scorable. "
)

TS_EVIDENCE_CLAUSE = (
    "A transition-state evidence file must carry `smiles: <the SMILES of that "
    "step's reactant>` so the scorer can attach the saddle to the step it "
    "belongs to. "
)

# 节点能量声明（能垒评分题必填）：评分器用声明值指认"交付的是哪一份日志"
# （同物种多份合法日志/多构象时），因此每个节点都要把能量与日志路径写清楚。
_NODE_ENERGY_CLAUSE = (
    "Every species node and transition-state node must declare "
    "`properties.energy_hartree` (the electronic energy of the geometry you "
    "delivered for that node, in Hartree, exactly as it appears in that node's "
    "evidence log) and `properties.evidence_log` (the sandbox-relative path of "
    "that log). The scorer uses the declared energy to identify which evidence "
    "file you delivered for each node; a node missing either field violates the "
    "delivery contract. "
)


def barrier_declaration_clause(require_node_energies: bool = True) -> str:
    """能垒交付契约；`require_node_energies` 与 IntegrityRubric 的同名开关
    保持一致——题面要求与评分器强制必须同源（不需要能垒评分的题不写这句）。"""
    return BARRIER_DECLARATION_CLAUSE + (
        _NODE_ENERGY_CLAUSE if require_node_energies else ""
    )

def conditions_modeling_guidance(conditions: str) -> str:
    """题面 conditions 之后的建模要求句。

    口径（用户决策）：**要求 agent 在允许的计算方法范围内尽量逼近题面描述的
    真实条件**——相、溶剂、催化剂按 conditions 原文由 agent 自行权衡建模，
    题面不指定具体溶剂模型（这是 Cloudra 的判断，不是题面的处方）。
    含明确温度时另加评分口径句：只报电子能垒、不因该温度加热校正。
    """
    text = conditions.lower()
    words = [w.strip(".,;:()[]") for w in text.replace("-", " ").replace("–", " ").split()]
    has_temperature = "degc" in text or "°c" in text or "k" in words
    guidance = (
        "Within the allowed methods, model the system so that it approximates the "
        "real conditions stated above as closely as the level of theory permits."
    )
    if has_temperature:
        guidance += (
            " Report electronic barriers only; do not add thermal corrections "
            "for the stated temperature."
        )
    return guidance


def format_allowed_methods_clause(allowed_methods: Sequence[str] | None) -> str:
    """Format the method whitelist clause dynamically from allowed_methods.

    If allowed_methods is empty or None, returns an empty string.
    Otherwise, maps known method tokens to standard display names and formats
    a trailing clause:
    "Allowed computational methods are limited to <methods>; calls beyond the whitelist are intercepted."
    Combo entries (`b3lyp/def2svp`) render with their basis (`B3LYP/def2-SVP`):
    the basis is part of the allowance, so it must be visible in the query.
    """
    if not allowed_methods:
        return ""
    display_map = {
        "xtb": "xTB",
        "mace-omol25": "MACE-OMol25",
        "mace": "MACE",
        # 本基准的 B3LYP 允可默认带 D3(BJ) 色散（与 gen_* 文档口径一致）：
        # 渲染必须写全，否则 agent 按查询写裸 B3LYP，能量与 gold 差几 kcal。
        "b3lyp": "B3LYP-D3(BJ)",
        "pbe": "PBE",
        "pbe0": "PBE0",
        "m062x": "M06-2X",
        "m06-2x": "M06-2X",
        "wb97x-d": "ωB97X-D",
        "wb97m-v": "ωB97M-V",
        "dft": "DFT",
    }
    basis_display = {
        "def2svp": "def2-SVP",
        "def2sv(p)": "def2-SV(P)",
        "def2tzvp": "def2-TZVP",
        "def2tzvpp": "def2-TZVPP",
        "def2qzvp": "def2-QZVP",
    }

    def _display(m: str) -> str:
        fam, sep, basis = m.partition("/")
        name = display_map.get(fam.lower(), fam)
        if sep:
            name = f"{name}/{basis_display.get(basis.lower(), basis)}"
        return name

    names = [_display(m) for m in allowed_methods]
    if len(names) == 1:
        joined = names[0]
    elif len(names) == 2:
        joined = f"{names[0]} and {names[1]}"
    else:
        joined = ", ".join(names[:-1]) + f", and {names[-1]}"
    return f"Allowed computational methods are limited to {joined}; calls beyond the whitelist are intercepted."
