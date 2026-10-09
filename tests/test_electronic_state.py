"""Declared electronic states use electron arithmetic, not localized-spin inference."""

import builtins
import importlib.util
from pathlib import Path

import pytest

import cloudra.tools.core.electronic_state as electronic_state


def _molecule(smiles):
    chem = pytest.importorskip("rdkit.Chem", reason="electronic-state graph tests require RDKit")
    params = chem.SmilesParserParams()
    params.removeHs = False
    molecule = chem.MolFromSmiles(smiles, params)
    assert molecule is not None
    return molecule


@pytest.mark.parametrize(
    "smiles,charge,multiplicity,electrons,radicals,n_alpha,n_beta,is_open_shell",
    [
        ("[CH2][CH2]", 0, 1, 16, 2, 8, 8, True),
        ("[CH2][CH2]", 0, 3, 16, 2, 9, 7, True),
        ("[CH2][CH2]", 0, 2, 16, 2, None, None, True),
        ("O=O", 0, 3, 16, 0, 9, 7, True),
        ("[CH3]", 0, 1, 9, 1, None, None, True),
        ("[CH3]", 0, 2, 9, 1, 5, 4, True),
        ("[Fe+2]", 2, 5, 24, 0, 14, 10, True),
        ("C", 0, 1, 10, 0, 5, 5, False),
        ("[H+]", 1, 1, 0, 0, 0, 0, False),
        ("[H+2]", 2, 1, -1, 3, None, None, True),
    ],
)
def test_details_report_declared_state_without_inferring_localized_spin(
    smiles, charge, multiplicity, electrons, radicals, n_alpha, n_beta, is_open_shell,
):
    details = electronic_state.electronic_state_details(
        _molecule(smiles), charge=charge, multiplicity=multiplicity,
    )
    assert details == {
        "charge": charge,
        "multiplicity": multiplicity,
        "electronic_character": None,
        "electron_count": electrons,
        "localized_radical_electrons": radicals,
        "n_alpha": n_alpha,
        "n_beta": n_beta,
        "is_open_shell": is_open_shell,
        "requires_spin_aware_geometry": is_open_shell,
    }


@pytest.mark.parametrize("smiles", ["C", "[CH4]", "[H]C([H])([H])[H]"])
def test_electron_count_includes_hydrogens_once_for_each_representation(smiles):
    details = electronic_state.electronic_state_details(_molecule(smiles), charge=0, multiplicity=1)
    assert details["electron_count"] == 10
    assert (details["n_alpha"], details["n_beta"]) == (5, 5)
    assert electronic_state.electronic_state_issue(_molecule(smiles), charge=0, multiplicity=1) is None


@pytest.mark.parametrize(
    "smiles,charge,multiplicity,electronic_character",
    [
        ("[CH2][CH2]", 0, 1, None),
        ("[CH2][CH2]", 0, 3, None),
        ("O=O", 0, 3, None),
        ("O=O", 0, 17, "open_shell"),
        ("[CH3]", 0, 2, None),
        ("[Fe+2]", 2, 5, "open_shell"),
        ("[H+]", 1, 1, None),
        ("C", 0, 1, "closed_shell"),
        ("C", 0, 1, "open_shell"),
        ("[CH2]", 0, 1, "closed_shell"),
    ],
)
def test_valid_electron_states_are_accepted_without_radical_count_or_coupling_gates(
    smiles, charge, multiplicity, electronic_character,
):
    assert electronic_state.electronic_state_issue(
        _molecule(smiles), charge=charge, multiplicity=multiplicity,
        electronic_character=electronic_character,
    ) is None


@pytest.mark.parametrize(
    "smiles,charge,multiplicity",
    [
        ("[CH2][CH2]", 0, 2),
        ("[CH3]", 0, 1),
        ("C", 0, 0),
        ("C", 0, -1),
        ("C", 0, 12),
        ("[H+]", 1, 2),
        ("[H+2]", 2, 1),
    ],
)
def test_invalid_electron_range_or_parity_is_refused(smiles, charge, multiplicity):
    molecule = _molecule(smiles)
    issue = electronic_state.electronic_state_issue(molecule, charge=charge, multiplicity=multiplicity)
    assert issue is not None
    assert issue[0] == "unsupported_spin"
    details = electronic_state.electronic_state_details(molecule, charge=charge, multiplicity=multiplicity)
    assert details["n_alpha"] is None
    assert details["n_beta"] is None


def test_formal_charge_mismatch_is_refused_before_spin_checks():
    issue = electronic_state.electronic_state_issue(_molecule("[Fe+2]"), charge=0, multiplicity=2)
    assert issue is not None
    assert issue[0] == "charge_mismatch"


@pytest.mark.parametrize("smiles,multiplicity", [("O=O", 3)])
def test_explicit_closed_shell_declaration_refuses_non_singlet_multiplicity(smiles, multiplicity):
    issue = electronic_state.electronic_state_issue(
        _molecule(smiles), charge=0, multiplicity=multiplicity, electronic_character="closed_shell",
    )
    assert issue is not None
    assert issue[0] == "unsupported_spin"


def test_declared_closed_shell_carbene_keeps_radicals_as_geometry_diagnostics_only():
    molecule = _molecule("[CH2]")
    details = electronic_state.electronic_state_details(
        molecule, charge=0, multiplicity=1, electronic_character="closed_shell",
    )
    assert details["electron_count"] == 8
    assert details["localized_radical_electrons"] == 2
    assert (details["n_alpha"], details["n_beta"]) == (4, 4)
    assert details["is_open_shell"] is False
    assert details["requires_spin_aware_geometry"] is True
    assert electronic_state.electronic_state_issue(
        molecule, charge=0, multiplicity=1, electronic_character="closed_shell",
    ) is None


def test_explicit_open_shell_singlet_is_retained_without_graph_radicals():
    details = electronic_state.electronic_state_details(
        _molecule("C"), charge=0, multiplicity=1, electronic_character="open_shell",
    )
    assert details["electronic_character"] == "open_shell"
    assert details["multiplicity"] == 1
    assert details["localized_radical_electrons"] == 0
    assert details["is_open_shell"] is True
    assert (details["n_alpha"], details["n_beta"]) == (5, 5)


def test_helper_can_be_loaded_without_rdkit_imports(monkeypatch):
    real_import = builtins.__import__

    def import_without_rdkit(name, *args, **kwargs):
        if name == "rdkit" or name.startswith("rdkit."):
            raise ImportError("RDKit is unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_rdkit)
    spec = importlib.util.spec_from_file_location("isolated_electronic_state", Path(electronic_state.__file__))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.electronic_state_issue)
    assert callable(module.electronic_state_details)
