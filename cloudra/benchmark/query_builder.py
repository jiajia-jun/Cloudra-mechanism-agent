"""Benchmark Query Builder utilities.

Prompt generation must be parameter-driven rather than hardcoding specific
computational methods or engines into template strings.
"""

from collections.abc import Sequence

# mechanism_graph.json 的字段级契约示例：题面 prompt 里给出具体键名，agent 不再
# 靠猜（生产教训：type/role 双写撞 NodeRole 枚举 → 整图被评成 unparseable）。
GRAPH_JSON_EXAMPLE = (
    "Use exactly this JSON shape (key names matter: nodes carry `id`, `role` "
    "(one of reactant/intermediate/product/transition_state) and `smiles` (a list "
    "of SMILES strings); edges carry `id`, `from`, `to`, `via`, `bond_changes` and "
    "optionally `barrier_kcal_mol`): "
    '{"nodes": [{"id": "RC", "role": "reactant", "smiles": ["..."]}, '
    '{"id": "TS1", "role": "transition_state", "smiles": []}, '
    '{"id": "P", "role": "product", "smiles": ["..."]}], '
    '"edges": [{"id": "e1", "from": "RC", "to": "P", "via": "TS1", '
    '"bond_changes": {"break": [[1, 2]], "form": [[1, 5]]}, '
    '"barrier_kcal_mol": 21.3}]}. '
)


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
        "b3lyp": "B3LYP",
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
