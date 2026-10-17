"""IRC direction labels must never change the meaning of chemical endpoint fields."""

import json
from pathlib import Path

import pytest

pytest.importorskip("rdkit", reason="endpoint identity requires the chem extra")

from cloudra.tools.core import ts_process
from cloudra.tools.core.structure_artifacts import read_xyz_atoms
from cloudra.tools.core.ts_inputs import EndpointSeed
from tests.test_ts_process import (
    _install_endpoint_minimum_jobs,
    _install_fake_irc_endpoints,
    _path_stage_uses_fast_idpp_fallback,  # noqa: F401 — shared fixture
    _record_with_freq_and_converged_irc,
    _sn2_minima,
    _xyz_text,
)

pytestmark = pytest.mark.usefixtures("ts_producer_authority")


def _endpoint_record(tmp_path, monkeypatch, *, swapped):
    record, symbols, frequency_dir = _record_with_freq_and_converged_irc(
        tmp_path, monkeypatch,
    )
    reactant, product = _sn2_minima(record, symbols)
    # References are supplied in their native species order. Routing must use
    # the frozen full-atom map, not align interchangeable atoms again.
    reference = tmp_path / "product_reference.xyz"
    reference.write_text(_xyz_text(
        [symbols[index] for index in record.structures.product_to_reactant],
        [product[index] for index in record.structures.product_to_reactant],
    ))
    from cloudra.tools.core.molecule import with_positions
    record.structures.product = with_positions(record.structures.product, [product[index] for index in record.structures.product_to_reactant])
    (frequency_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, 0.5 * (reactant + product)),
    )
    ends = (0.25 * reactant + 0.75 * product, 0.75 * reactant + 0.25 * product)
    if not swapped:
        ends = ends[::-1]
    _install_fake_irc_endpoints(monkeypatch, symbols, *ends)
    return record, symbols, reactant, product, ends


@pytest.mark.parametrize("swapped", [False, True])
@pytest.mark.parametrize("role", ["reactant", "product"])
def test_default_endpoint_selects_the_declared_role_before_optimization(
    tmp_path, monkeypatch, swapped, role,
):
    record, symbols, _reactant, _product, ends = _endpoint_record(
        tmp_path, monkeypatch, swapped=swapped,
    )
    directory = tmp_path / "endpoint_opt"
    directory.mkdir()

    error, input_path = ts_process._write_endpoint_input(record, str(directory), role, "opt")

    assert error == "", error
    side = ("B" if role == "reactant" else "A") if swapped else (
        "A" if role == "reactant" else "B"
    )
    origin = json.loads((directory / "endpoint_source.json").read_text())
    assert origin["label"] == side
    expected = ends[0 if side == "A" else 1]
    atoms = read_xyz_atoms(directory / f"{role}_source.xyz")
    assert [symbol for symbol, _ in atoms] == symbols
    assert [point for _, point in atoms] == pytest.approx(expected, abs=1e-6)
    title = Path(input_path).read_text().splitlines()[0]
    assert f"IRC side {side}" in title
    assert "identity unverified" in title


def test_undecidable_pairing_still_allows_endpoint_optimization(tmp_path, monkeypatch):
    record, _symbols, _reactant, _product, _ends = _endpoint_record(
        tmp_path, monkeypatch, swapped=True,
    )
    monkeypatch.setattr(ts_process, "_read_built_xyz", lambda *_args: None)
    directory = tmp_path / "undecidable_opt"
    directory.mkdir()

    error, input_path = ts_process._write_endpoint_input(record, str(directory), "reactant", "opt")

    assert error == "", error
    title = Path(input_path).read_text().splitlines()[0]
    assert "IRC side A" in title
    assert "identity unverified" in title


def test_endpoint_repair_does_not_reuse_the_retained_opposite_irc_side(tmp_path, monkeypatch):
    record, symbols, reactant, product, _ends = _endpoint_record(
        tmp_path, monkeypatch, swapped=True,
    )
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, reactant, product,
        origins={"reactant": "B", "product": "A"})
    record.job_steps = [step for step in record.job_steps
        if not step.purpose.startswith("reactant_")]
    # Even if a changed rough reference favors A, it belongs to the retained
    # product calculation. The new reactant attempt must consume B.
    monkeypatch.setattr(ts_process, "_read_built_xyz", lambda *_args: None)
    directory = tmp_path / "repaired_reactant_opt"
    directory.mkdir()

    error, _ = ts_process._write_endpoint_input(record, str(directory), "reactant", "opt")

    assert error == "", error
    assert json.loads((directory / "endpoint_source.json").read_text())["label"] == "B"


@pytest.mark.parametrize("role", ["reactant", "product"])
def test_mixed_seed_uses_the_completed_explicit_opposite_reference(tmp_path, monkeypatch, role):
    record, symbols, reactant, product, _ends = _endpoint_record(
        tmp_path, monkeypatch, swapped=True,
    )
    other = "product" if role == "reactant" else "reactant"
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, reactant, product,
        origins={"reactant": "reactant", "product": "product"})
    record.job_steps = [step for step in record.job_steps
        if not step.purpose.startswith(role + "_")]
    # The completed explicit reference is more useful than an unavailable or
    # stale initial search seed; it still does not certify the new endpoint.
    monkeypatch.setattr(ts_process, "_read_built_xyz", lambda *_args: None)
    directory = tmp_path / ("default_" + role)
    directory.mkdir()

    error, _ = ts_process._write_endpoint_input(record, str(directory), role, "opt")

    assert error == "", error
    assert json.loads((directory / "endpoint_source.json").read_text())["label"] == (
        "B" if other == "product" else "A"
    )


def test_verdict_cannot_swap_chemical_job_roles_to_hide_a_wrong_route(tmp_path, monkeypatch):
    record, symbols, reactant, product, _ends = _endpoint_record(
        tmp_path, monkeypatch, swapped=True,
    )
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, product, reactant)

    result = ts_process._verdict(record)

    assert result.terminal == "candidate_only"
    assert "identity" in result.stage_record("verdict").detail


def test_frequency_failure_names_actual_irc_source_and_chemical_repair_field(tmp_path, monkeypatch):
    record, symbols, reactant, product, _ends = _endpoint_record(
        tmp_path, monkeypatch, swapped=True,
    )
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, reactant, product,
        reactant_freqs=[-85.04, 120.0], origins={"reactant": "B", "product": "A"})
    record.job_steps = [step for step in record.job_steps
        if not step.purpose.startswith("product_")]
    monkeypatch.setattr(ts_process, "_step_state", lambda _record, step: step.state)

    result = ts_process._refine(record)

    assert result.terminal == "candidate_only"
    detail = result.stage_record("verdict").detail
    assert "IRC side B" in detail
    assert "verification.reactant_endpoint.seed" in detail
    assert record.input.reaction.reactant_smiles in detail


def test_wrong_species_mol_is_not_reported_as_an_atom_order_problem(tmp_path, monkeypatch):
    record, _symbols, _reactant, _product, _ends = _endpoint_record(
        tmp_path, monkeypatch, swapped=True,
    )
    reactant = ts_process._read_built_xyz(record, "reactant")
    record.input.verification.product_endpoint.seed = EndpointSeed(
        kind="file", xyz_path=reactant[2], mol_path=reactant[3], evidence_refs=[reactant[2]],
    )
    directory = tmp_path / "wrong_product_seed"
    directory.mkdir()

    error, _ = ts_process._write_endpoint_input(record, str(directory), "product", "opt")

    assert "declared product" in error
    assert "verification.reactant_endpoint.seed" in error
