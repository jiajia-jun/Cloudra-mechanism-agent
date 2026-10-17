"""Research changes need scientific inputs, not administrative repair files."""

from pathlib import Path

import pytest

from cloudra.tools.Chemtool.ts_search_process import TsResume_input_schema
from cloudra.tools.core import ts_process
from cloudra.tools.core.ts_inputs import EndpointSeed, FileConformer, QmCalculation, TsResumeRequest
from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
from tests.test_ts_stage_inputs import record_fixture


def _failed_scan(tmp_path, *, completed=False):
    record = record_fixture(tmp_path, stage="guess")
    source = tmp_path / "scan.inp"
    source.write_text("original scan input\n")
    record.scan_step = ts_process.TsJobStep(purpose="scan", job_id=7,
        input_path=str(source), state="done" if completed else "failed",
        actual_calculation=record.input.guess.calculation)
    log = Path(ts_process._refinement_log_path(record, record.scan_step))
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("completed monotonic scan\n" if completed else "engine failed\n")
    ts_process._record_candidate_failure(record, "scan_no_candidate" if completed else "nonconvergence",
        record.scan_step, str(log))
    record.blocked = ts_process.TsBlocked(stage="guess", failure_class="scan_no_candidate" if completed else "scan_job_failed",
        message="No peak" if completed else "Engine failed")
    return record, source, log


def _request(record, changes):
    return TsResumeRequest(changes=changes, reason="Try the next research step",
        request_key="research-change", expected_revision=record.revision)


def test_public_resume_does_not_require_repair_files():
    assert "scan_recovery" not in TsResume_input_schema.model_fields


@pytest.mark.parametrize("completed", [False, True])
def test_failed_or_no_peak_scan_can_switch_to_a_provided_candidate(tmp_path, completed):
    record, source, log = _failed_scan(tmp_path, completed=completed)
    original = source.read_bytes(), log.read_bytes()
    candidate = tmp_path / "candidate.xyz"
    candidate.write_text("1\ncandidate frame\nH 0 0 0\n")
    change = _request(record, {"guess": {"kind": "provided", "xyz_path": str(candidate),
        "evidence_refs": [str(log)]}})

    revised = revise_record(record, change, plan_input_revision(record, change))

    assert revised.input.guess.kind == "provided"
    assert revised.scan_step is None
    assert revised.attempt_history[-1].failed_attempt == record.failed_attempt
    assert revised.attempt_history[-1].blocked == record.blocked
    assert revised.terminal is None
    assert (source.read_bytes(), log.read_bytes()) == original


def test_engine_failure_can_retry_without_a_repair_certificate(tmp_path):
    record, source, log = _failed_scan(tmp_path)
    change = _request(record, {})

    revised = revise_record(record, change, plan_input_revision(record, change))

    assert revised.scan_step is None
    assert revised.attempt_history[-1].failed_attempt == record.failed_attempt
    assert source.read_text() == "original scan input\n"
    assert log.read_text() == "engine failed\n"


def _file_molecule(tmp_path, name, smiles, *, distorted=False):
    Chem = pytest.importorskip("rdkit.Chem")
    AllChem = pytest.importorskip("rdkit.Chem.AllChem")
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(atom.GetIdx() + 1)
    assert AllChem.EmbedMolecule(mol, randomSeed=42) == 0
    if distorted:
        point = mol.GetConformer().GetAtomPosition(2)
        mol.GetConformer().SetAtomPosition(2, [point.x + 5.0, point.y, point.z])
    xyz, graph = tmp_path / (name + ".xyz"), tmp_path / (name + ".mol")
    xyz.write_text(Chem.MolToXYZBlock(mol))
    graph.write_text(Chem.MolToMolBlock(mol))
    return FileConformer(kind="file", xyz_path=str(xyz), mol_path=str(graph)), mol


def test_coarse_coordinates_do_not_block_atom_binding_or_seed_optimization(tmp_path):
    record = record_fixture(tmp_path)
    record.input.reaction.reactant_smiles = record.input.reaction.product_smiles = "CCO"
    record.input.conformers.guidance.ring_order = []
    for role in ("reactant", "product"):
        source, _ = _file_molecule(tmp_path, role, "CCO", distorted=True)
        setattr(record.input.conformers, role, source)

    ts_process._build(record)
    ts_process._map(record)

    assert record.blocked is None
    assert record.structures.product_to_reactant is not None
    assert record.terminal is None


def test_explicit_endpoint_seed_may_be_coarse_before_its_optimization(tmp_path):
    record = record_fixture(tmp_path)
    record.input.reaction.reactant_smiles = record.input.reaction.product_smiles = "CCO"
    record.input.conformers.guidance.ring_order = []
    for role in ("reactant", "product"):
        source, _ = _file_molecule(tmp_path, role, "CCO", distorted=True)
        setattr(record.input.conformers, role, source)
    ts_process._build(record)
    ts_process._map(record)
    source = record.input.conformers.reactant
    record.input.verification.reactant_endpoint.seed = EndpointSeed(kind="file",
        xyz_path=source.xyz_path, mol_path=source.mol_path, evidence_refs=[source.xyz_path])
    record.input.verification.reactant_endpoint.optimization = QmCalculation(
        engine="orca", method="HF", basis_set="STO-3G")
    directory = tmp_path / "endpoint_opt"
    directory.mkdir()

    error, input_path = ts_process._write_endpoint_input(record, str(directory), "reactant", "opt")

    assert error == "", error
    assert Path(input_path).exists()


@pytest.mark.parametrize("redeclare", [False, True])
def test_new_molecular_graph_can_start_with_fresh_numbering(tmp_path, redeclare):
    record = record_fixture(tmp_path)
    record.input.reaction.reactant_smiles = record.input.reaction.product_smiles = "CCO"
    record.input.reaction.reaction_center = [(0, 1)]
    record.input.conformers.guidance.ring_order = []
    for role in ("reactant", "product"):
        source, _ = _file_molecule(tmp_path, role, "CCO")
        setattr(record.input.conformers, role, source)
    ts_process._build(record)
    ts_process._map(record)
    assert record.blocked is None
    inputs = {}
    for role in ("reactant", "product"):
        source, _ = _file_molecule(tmp_path, "new_" + role, "COC")
        inputs[role] = source.model_dump()
    reaction = {"reactant_smiles": "COC", "product_smiles": "COC"}
    if redeclare:
        reaction.update(selected_candidate=0, reaction_center=[[0, 1]])
    change = _request(record, {"reaction": reaction, "conformers": inputs})

    revised = revise_record(record, change, plan_input_revision(record, change))

    assert revised.stage == "declare"
    assert revised.input.reaction.selected_candidate == (0 if redeclare else None)
    assert revised.input.reaction.reaction_center == ([(0, 1)] if redeclare else [])
    assert revised.input.guess is None
    assert not revised.job_steps
    ts_process._build(revised)
    ts_process._map(revised)
    if redeclare:
        assert revised.blocked is None
        assert revised.structures.product_to_reactant is not None
    else:
        assert revised.blocked is None
        assert revised.structures.product_to_reactant is not None
