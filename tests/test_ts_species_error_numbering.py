"""Public TS species mismatches use the source geometry's 1-based atom pairs."""

import pytest

pytest.importorskip("rdkit")
from rdkit import Chem

from cloudra.tools.core.ts_process import _geometry_connectivity_error


def test_connectivity_error_reports_remapped_missing_and_extra_pairs_1based(monkeypatch):
    monkeypatch.setattr("cloudra.tools.core.irc_path.perceive_bonds", lambda *_: ({(1, 2): 1.0}, "rdDetermineBonds"))
    mol = Chem.MolFromSmiles("CCC")
    error = _geometry_connectivity_error(
        mol, (["C", "C", "C"], [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]),
        0, "product", remap=[2, 0, 1],
    )
    assert error == (
        "product optimized connectivity differs from the declared species (atom pairs 1-based): "
        "missing bonds=[(1, 2), (1, 3)], extra bonds=[(2, 3)]"
    )


def test_bond_order_error_reports_1based_pair(monkeypatch):
    monkeypatch.setattr("cloudra.tools.core.irc_path.perceive_bonds", lambda *_: ({(0, 1): 1.0}, "rdDetermineBonds"))
    error = _geometry_connectivity_error(
        Chem.MolFromSmiles("C=O"), (["C", "O"], [[0., 0., 0.], [1.3, 0., 0.]]), 0, "reactant",
    )
    assert error == "reactant optimized bond order differs from the declared species (atom pairs 1-based) at [(1, 2)]"
