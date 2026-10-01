"""Engine spelling of declared QM keywords; does not choose a theory level."""


def orca_basis_keyword(basis: str) -> str:
    """Render compact def2 aliases using ORCA's native hyphenated spelling.

    Preserve already-native and other basis names. The declaration stays intact;
    this conversion belongs at input rendering, not in scientific policy.
    """
    lowered = basis.lower()
    if lowered.startswith("def2") and not lowered.startswith("def2-"):
        return "def2-" + basis[4:].upper()
    return basis
