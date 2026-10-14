"""TS scan resources reach the native ORCA input; no calculations are run."""
from pathlib import Path

import pytest

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
from cloudra.tools.core.ts_inputs import TsInput
from cloudra.tools.core.ts_process import TsProcessRecord, _guess_scan

WATER = "3\nwater\nO 0 0 0\nH 0 0 1\nH 1 0 0\n"
CALCULATION = dict(engine="orca", method="B3LYP", basis_set="def2-SVP", keywords="D3BJ TightSCF")
SCANS = [dict(atoms=[0, 1], scan_start=1., scan_end=2., scan_steps=3),
         dict(atoms=[0, 2], scan_start=1., scan_end=2., scan_steps=3)]


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
    writer = QmInputWriter._build_orca_input(QmInputWriter_input_schema(
        source_type="xyz_file", source_value=str(source), output_path=str(tmp_path / "reference.inp"),
        task_type=[{"opt": None}],
        nproc=cpus, mem=f"{memory_mb}MB", **CALCULATION), "O 0 0 0\nH 0 0 1\nH 1 0 0")
    expected_resources = [line for line in writer.splitlines() if line.startswith(("%pal", "%maxcore"))]
    assert [line for line in native.splitlines() if line.startswith(("%pal", "%maxcore"))] == expected_resources
    assert native.splitlines()[0] == "! OPT B3LYP def2-SVP D3BJ TightSCF"
    assert "Scan B 0 1 = 1.000000, 2.000000, 3 end" in native
    assert ("Simul_Scan true" in native) is concerted
    coordinates = [line.split() for line in native[native.index("* xyz"):].splitlines()[1:4]]
    assert [row[0] for row in coordinates] == ["O", "H", "H"]
    assert [[float(value) for value in row[1:]] for row in coordinates] == [[0., 0., 0.], [0., 0., 1.], [1., 0., 0.]]



def test_standalone_scan_keeps_native_resource_default_without_public_memory_field(tmp_path):
    assert not {"mem", "memory_mb", "resources"} & TsGuess_input_schema.model_fields.keys()
    output = tmp_path / "scan.inp"
    result = TsGuess()._scan_prepare(TsGuess_input_schema(
        mode="scan_prepare", input_text=WATER, output_path=str(output), nprocs=8,
        scans=SCANS[:1], **CALCULATION))
    assert result.is_success
    assert "%pal nprocs 8 end" in output.read_text()
    assert "%maxcore" not in output.read_text()
