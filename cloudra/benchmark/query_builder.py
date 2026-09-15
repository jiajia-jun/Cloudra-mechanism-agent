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

# 条件建模指引的溶剂名单（结构化子串匹配，一律小写比对；新增题源条件里的溶剂
# 必须在此登记，否则按气相默认处理）。
_SOLVENT_TOKENS = (
    "water",
    "aqueous",
    "dmso",
    "thf",
    "meoh",
    "methanol",
    "ethanol",
    "et2o",
    "diethyl ether",
    "benzene",
    "toluene",
    "ch2cl2",
    "dichloromethane",
    "chloroform",
    "chcl3",
    "acetonitrile",
    "mecn",
    "h2so4",
    "solvent",
    "alcohol",
)


def conditions_modeling_guidance(conditions: str) -> str:
    """题面 conditions 之后的建模指引句（使题面条件与交付口径对齐）。

    默认气相；conditions 文本含溶剂名（结构化子串匹配，不用正则）时改述隐式
    溶剂模型；含明确温度（degC/°C 或开尔文）时追加"只报电子能垒、不加该温度
    的热校正"。
    """
    text = conditions.lower()
    has_solvent = any(tok in text for tok in _SOLVENT_TOKENS)
    words = [w.strip(".,;:()[]") for w in text.replace("-", " ").replace("–", " ").split()]
    has_temperature = "degc" in text or "°c" in text or "k" in words
    if has_solvent:
        guidance = (
            "Include the corresponding implicit solvent model (e.g. CPCM for "
            "B3LYP, ALPB/GBSA for xTB) in all energies you declare."
        )
    else:
        guidance = "Model the reaction in the gas phase."
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
