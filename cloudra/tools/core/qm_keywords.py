"""Engine spelling of declared QM keywords; does not choose a theory level."""


def is_basis_keyword(token: str) -> bool:
    """Recognize basis spelling for field separation, not scientific selection."""
    value = token.lower()
    head, separator, tail = value.partition('-')
    numeric = bool(separator and head.isdigit() and tail and tail[0].isdigit())
    aliases = {'sv', 'svp', 'sv(p)', 'dz', 'dzp', 'tz', 'tzp', 'tzvp', 'tzvpp',
               'qz', 'qzvp', 'qzvpp', 'lanl2dz', 'lanl2mb', 'minis', 'midi',
               'gen', 'genecp', 'chkbasis', 'sto3g', 'sto6g'}
    return (value in aliases or numeric
            or value.startswith(('def2', 'cc-pv', 'ccpv', 'aug-', 'sto-', 'pcseg', 'ano',
                                 'minao', 'ma-', 'jun-', 'jul-'))
            or (value.startswith('pc-') and value[3:4].isdigit()))


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
