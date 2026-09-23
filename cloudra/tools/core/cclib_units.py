"""Unit conversion for numerical values returned by cclib."""


def energy_ev_to_hartree(energy_ev: float) -> float:
    """Undo cclib's own Hartree-to-eV conversion without mixing constants."""
    from cclib.parser.utils import convertor

    return float(convertor(float(energy_ev), "eV", "hartree"))
