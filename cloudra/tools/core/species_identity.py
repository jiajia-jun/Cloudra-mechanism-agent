"""Keep a bound species separate from a collection of separated species."""
from __future__ import annotations


def chemical_smiles(value: str | list[str]) -> str:
    """Return the complete chemical graph without changing species grouping."""
    return '.'.join(value) if isinstance(value, list) else value


def species_smiles(value: str | list[str]) -> list[str]:
    """A scalar is one species, including a dot-joined bound complex."""
    return value if isinstance(value, list) else [value]
