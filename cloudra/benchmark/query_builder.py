"""Benchmark Query Builder utilities.

Prompt generation must be parameter-driven rather than hardcoding specific
computational methods or engines into template strings.
"""

from collections.abc import Sequence


def format_allowed_methods_clause(allowed_methods: Sequence[str] | None) -> str:
    """Format the method whitelist clause dynamically from allowed_methods.

    If allowed_methods is empty or None, returns an empty string.
    Otherwise, maps known method tokens to standard display names and formats
    a trailing clause:
    "Allowed computational methods are limited to <methods>; calls beyond the whitelist are intercepted."
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
    names = [display_map.get(m.lower(), m) for m in allowed_methods]
    if len(names) == 1:
        joined = names[0]
    elif len(names) == 2:
        joined = f"{names[0]} and {names[1]}"
    else:
        joined = ", ".join(names[:-1]) + f", and {names[-1]}"
    return f"Allowed computational methods are limited to {joined}; calls beyond the whitelist are intercepted."
