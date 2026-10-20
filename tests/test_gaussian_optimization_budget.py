"""Keep declared optimization limits intact without predicting engine behavior."""

import pytest

pytest.importorskip("ase")
pytest.importorskip("rdkit")

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.core.molecule import read_molecule
from cloudra.tools.core.qm_calculation import QmCalculation
from cloudra.tools.core.ts_process import _stage_writer_tasks


@pytest.mark.parametrize("workflow,expected_opt", [
    ("direct", "opt=(readfc,maxcycles=200)"),
    ("minimum", "opt=(readfc,maxcycles=200)"),
    ("ts", "opt=(readfc,maxcycles=200)"),
])
@pytest.mark.parametrize("explicit_iop", ["", "iop(1/152=200)"])
def test_render_preserves_requested_optimization_cycles_and_explicit_iop(
    tmp_path, workflow, expected_opt, explicit_iop,
):
    remaining = " ".join(filter(None, ["scf=tight", explicit_iop]))
    if workflow == "direct":
        task_type = [{"opt": "readfc,maxcycles=200"}, {"freq": None}]
    else:
        calculation, task_type = _stage_writer_tasks(
            QmCalculation(engine="gaussian", method="B3LYP", basis_set="def2SVP",
                keywords="opt=(readfc,maxcycles=200) " + remaining),
            [{"opt": "TS" if workflow == "ts" else None}],
        )
        remaining = calculation.keywords
    request = QmInputWriter_input_schema(
        engine="gaussian", method="B3LYP", basis_set="def2SVP",
        source_type="xyz_file", source_value="water.xyz", output_path=str(tmp_path / "opt.gjf"),
        charge=0, multiplicity=1, task_type=task_type, keywords=remaining,
    )
    molecule = read_molecule(
        input_text="3\nwater\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n", charge=0,
    )

    content = QmInputWriter.render_input(request, molecule)
    route = next(line.lower().split() for line in content.splitlines() if line.startswith("#"))

    assert expected_opt in route
    assert "scf=tight" in route
    assert ("freq" in route) is (workflow == "direct")
    if explicit_iop:
        assert route.count("iop(1/152=200)") == 1
    else:
        assert all(not token.startswith("iop(") for token in route)
