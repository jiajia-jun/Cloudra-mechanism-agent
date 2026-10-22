"""TS scan resources reach the native ORCA input; no calculations are run."""
from pathlib import Path

import pytest

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
from cloudra.tools.core.ts_inputs import TsInput
from cloudra.tools.core.ts_process import TsProcessRecord, _guess_scan

WATER = "3\nwater\nO 0 0 0\nH 0 0 1\nH 1 0 0\n"
CALCULATION = dict(engine="orca", method="B3LYP", basis_set="def2-SVP", keywords="Opt D3BJ TightSCF")
SCANS = [dict(atoms=[0, 1], scan_start=1., scan_end=2., scan_steps=3),
         dict(atoms=[0, 2], scan_start=1., scan_end=2., scan_steps=3)]


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize("cpus,memory_mb,concerted", [(4, 4096, False), (8, 8192, True), (3, 8192, False)])
def test_ts_scan_execution_budget_matches_native_qm_resources(tmp_path, monkeypatch, cpus, memory_mb, concerted):
    declaration = TsInput.model_validate(dict(
        reaction=dict(reactant_smiles="O", product_smiles="O", charge=0, multiplicity=1),
        guess=dict(kind="scan", calculation=CALCULATION, scans=SCANS if concerted else SCANS[:1],
                   mode="concerted" if concerted else None),
        execution=dict(cpus=cpus, memory_mb=memory_mb),
    ))
    source = tmp_path / "water.xyz"
    source.write_text(WATER)
    record = TsProcessRecord(run_id="scan", run_dir=str(tmp_path), workspace_dir=str(tmp_path),
                             owner_conversation_id="project", owner_session_id="owner", input=declaration)
    monkeypatch.setattr("cloudra.tools.core.ts_process._read_built_xyz",
                        lambda *_: (["O", "H", "H"], [[0., 0., 0.], [0., 0., 1.], [1., 0., 0.]], str(source), ""))
    monkeypatch.setattr("cloudra.services.ts_pipeline_context.require_pipeline_authority", lambda *_: None)
    submitted = []

    def submit(record, purpose, path, engine):
        submitted.append((record.compute_cpus, record.compute_memory_mb, Path(path).read_text()))
        return "", 42

    monkeypatch.setattr("cloudra.tools.core.ts_process._submit_step", submit)
    _guess_scan(record)
    assert record.blocked is None
    assert record.waiting_for == "job:42"
    requested_cpus, requested_memory, native = submitted[0]
    assert (requested_cpus, requested_memory) == (cpus, memory_mb)
    from cloudra.tools.core.molecule import read_molecule
    writer = QmInputWriter._build_orca_input(QmInputWriter_input_schema(
        source_type="xyz_file", source_value=str(source), output_path=str(tmp_path / "reference.inp"),
        task_type=[],
        nproc=cpus, mem=f"{memory_mb}MB", **CALCULATION), read_molecule(str(source)))
    expected_resources = [line for line in writer.splitlines() if line.startswith(("%pal", "%maxcore"))]
    assert [line for line in native.splitlines() if line.startswith(("%pal", "%maxcore"))] == expected_resources
    assert native.splitlines()[0] == "! B3LYP def2-SVP Opt D3BJ TightSCF"
    assert "Scan\n        B 0 1 = 1.000000, 2.000000, 3\n" in native
    assert ("Simul_Scan true" in native) is concerted
    coordinates = [line.split() for line in native[native.index("* xyz"):].splitlines()[1:4]]
    assert [row[0] for row in coordinates] == ["O", "H", "H"]
    assert [[float(value) for value in row[1:]] for row in coordinates] == [[0., 0., 0.], [0., 0., 1.], [1., 0., 0.]]



@pytest.mark.usefixtures("rdkit_chemistry")
def test_standalone_scan_uses_shared_resource_fields(tmp_path):
    assert {'mem', 'nproc'} <= TsGuess_input_schema.model_fields.keys()
    output = tmp_path / "scan.inp"
    result = TsGuess()._scan_prepare(TsGuess_input_schema(
        mode="scan_prepare", input_text=WATER, charge=0, output_path=str(output), nproc=8,
        scans=SCANS[:1], **CALCULATION))
    assert result.is_success
    assert "%pal nprocs 8 end" in output.read_text()
    assert "%maxcore 512" in output.read_text()


@pytest.mark.parametrize('engine', ['gaussian', 'orca'])
def test_run_scan_inherits_electronic_state_and_resources(tmp_path, monkeypatch, engine):
    from cloudra.tools.core.calculation_intent import inspect_input
    from tests.test_ts_scan_shared_writer import _HYDRONIUM_XYZ

    calculation = dict(engine=engine, method='B3LYP', basis_set='def2SVP')
    declaration = TsInput.model_validate(dict(
        reaction=dict(reactant_smiles='[OH3+]', product_smiles='[OH3+]', charge=1,
                      multiplicity=1, electronic_character='closed_shell'),
        guess=dict(kind='scan', calculation=calculation,
                   scans=[dict(atoms=[0, 1], scan_end=1.5, scan_steps=6)]),
        execution=dict(cpus=8, memory_mb=8192),
    ))
    source = tmp_path / 'hydronium.xyz'
    source.write_text(_HYDRONIUM_XYZ)
    record = TsProcessRecord(run_id='inherited', run_dir=str(tmp_path), workspace_dir=str(tmp_path),
                             owner_conversation_id='project', owner_session_id='owner', input=declaration)
    monkeypatch.setattr('cloudra.tools.core.ts_process._read_built_xyz',
                        lambda *_: ([], [], str(source), ''))
    monkeypatch.setattr('cloudra.services.ts_pipeline_context.require_pipeline_authority', lambda *_: None)
    submitted = []
    requests = []
    original = TsGuess._scan_prepare

    def prepare(self, request):
        requests.append(request)
        return original(self, request)

    def submit(_record, _purpose, path, _engine):
        submitted.append(Path(path).read_text())
        return '', 42

    monkeypatch.setattr(TsGuess, '_scan_prepare', prepare)
    monkeypatch.setattr('cloudra.tools.core.ts_process._submit_step', submit)
    _guess_scan(record)
    assert record.blocked is None and record.waiting_for == 'job:42'
    request = requests[0]
    assert (request.charge, request.multiplicity, request.electronic_character) == (1, 1, 'closed_shell')
    assert (request.nproc, request.mem) == (8, '8192MB')
    native = submitted[0]
    assert (inspect_input(native, engine=engine).charge, inspect_input(native, engine=engine).multiplicity) == (1, 1)
    assert '%mem=8192MB' in native if engine == 'gaussian' else '%maxcore 1024' in native
