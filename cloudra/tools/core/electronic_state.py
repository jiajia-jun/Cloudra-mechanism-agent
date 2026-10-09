"""Summarize declared electronic states and check electron arithmetic.

Localized graph radicals are diagnostic. These checks do not select spin coupling,
infer a ground state, or qualify a geometry or electronic-structure calculation.
"""

from typing import Literal


def electronic_state_details(
    mol,
    *,
    charge: int,
    multiplicity: int,
    electronic_character: Literal["closed_shell", "open_shell"] | None = None,
) -> dict[str, int | bool | str | None]:
    """Retain the declaration and report electron populations without importing RDKit."""
    atoms = tuple(mol.GetAtoms())
    # Hydrogen atoms present as neighbors contribute through their own atomic Z.
    # Atom H-count properties cover implicit and bracket H only.
    electron_count = sum(
        atom.GetAtomicNum() + atom.GetNumImplicitHs() + atom.GetNumExplicitHs()
        for atom in atoms
    ) - charge
    localized_radical_electrons = sum(atom.GetNumRadicalElectrons() for atom in atoms)
    net_spin = multiplicity - 1
    valid_populations = (
        electron_count >= 0
        and 0 <= net_spin <= electron_count
        and (electron_count - net_spin) % 2 == 0
    )
    is_open_shell = (
        electronic_character == "open_shell" if electronic_character is not None
        else multiplicity > 1 or localized_radical_electrons > 0
    )
    return {
        "charge": charge,
        "multiplicity": multiplicity,
        "electronic_character": electronic_character,
        "electron_count": electron_count,
        "localized_radical_electrons": localized_radical_electrons,
        "n_alpha": (electron_count + net_spin) // 2 if valid_populations else None,
        "n_beta": (electron_count - net_spin) // 2 if valid_populations else None,
        "is_open_shell": is_open_shell,
        "requires_spin_aware_geometry": is_open_shell or localized_radical_electrons > 0,
    }


def electronic_state_issue(
    mol,
    *,
    charge: int,
    multiplicity: int,
    electronic_character: Literal["closed_shell", "open_shell"] | None = None,
) -> tuple[str, str] | None:
    """Return a charge, electron-population, or explicit-character contradiction."""
    formal_charge = sum(atom.GetFormalCharge() for atom in mol.GetAtoms())
    if formal_charge != charge:
        return (
            "charge_mismatch",
            f"Total charge mismatch: the input structure's formal charges sum to "
            f"{formal_charge}, but total_charge={charge} was requested. Fix the charge "
            "or the input's formal charges before using the structure.",
        )
    details = electronic_state_details(
        mol, charge=charge, multiplicity=multiplicity, electronic_character=electronic_character,
    )
    if details["n_alpha"] is None:
        return (
            "unsupported_spin",
            f"The declared electron count N_e={details['electron_count']} and multiplicity={multiplicity} "
            "cannot give integer alpha/beta electron populations: N_e must be non-negative, "
            "and multiplicity - 1 must be between 0 and N_e with the same parity as N_e.",
        )
    if electronic_character == "closed_shell" and multiplicity > 1:
        return (
            "unsupported_spin",
            "electronic_character='closed_shell' contradicts a non-singlet multiplicity. "
            "Supply a consistent electronic-character declaration.",
        )
    return None
