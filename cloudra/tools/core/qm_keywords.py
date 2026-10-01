"""Engine spelling of declared QM keywords; does not choose a theory level."""


def orca_basis_keyword(basis: str) -> str:
    """Render compact def2 aliases using ORCA's native hyphenated spelling.

    Preserve already-native and other basis names. The declaration stays intact;
    this conversion belongs at input rendering, not in scientific policy.
    """
    basis = basis.strip()
    head, separator, suffix = basis.partition("/")
    lowered = head.lower()
    if lowered.startswith("def2") and len(head) > 4 and not lowered.startswith("def2-"):
        head = "def2-" + head[4:].upper()
    return head + separator + suffix
