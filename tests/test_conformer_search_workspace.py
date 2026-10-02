"""Conformer artifacts stay with their Agent workspace or explicit output path."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.tools.Chemtool.conformer_search import (
    ConformerSearch,
    ConformerSearch_input_schema,
)

METHANE_XYZ = """5
methane
C  0.000  0.000  0.000
H  0.630  0.630  0.630
H  0.630 -0.630 -0.630
H -0.630  0.630 -0.630
H -0.630 -0.630  0.630
"""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "output", "expected_parent"),
    [
        ("smiles", None, "workspace/confs_output"),
        ("relative_file", None, "workspace/inputs/reactant_confs"),
        ("absolute_file", None, "inputs/reactant_confs"),
        ("smiles", "relative", "workspace/results/conformers"),
        ("smiles", "absolute", "explicit_output"),
    ],
)
async def test_conformer_artifact_path_uses_workspace_and_explicit_output(
    tmp_path, monkeypatch, mock_session, source, output, expected_parent,
):
    pytest.importorskip("rdkit", reason="requires RDKit (chem extra)")
    workspace = tmp_path / "workspace"
    runtime_cwd = tmp_path / "runtime"
    workspace.mkdir()
    runtime_cwd.mkdir()
    monkeypatch.chdir(runtime_cwd)
    tool = ConformerSearch(
        subagent=SimpleNamespace(working_directory=str(workspace)),
    )

    if source == "smiles":
        source_args = {"smiles": "C"}
    else:
        input_parent = workspace / "inputs" if source == "relative_file" else tmp_path / "inputs"
        input_parent.mkdir()
        input_path = input_parent / "reactant.xyz"
        input_path.write_text(METHANE_XYZ, encoding="utf-8")
        source_args = {
            "input_path": "inputs/reactant.xyz" if source == "relative_file" else str(input_path),
        }
    output_args = {}
    if output == "relative":
        output_args["output_dir"] = "results/conformers"
    elif output == "absolute":
        output_args["output_dir"] = str(tmp_path / "explicit_output")

    result = await tool.safe_call(
        ConformerSearch_input_schema(num_confs=1, **source_args, **output_args),
        mock_session,
    )

    assert result.is_success, result.message
    artifact = Path(result.ensemble_path)
    assert artifact.is_file()
    assert artifact.parent == tmp_path / expected_parent
    assert not (runtime_cwd / "confs_output").exists()
    assert not (runtime_cwd / "inputs" / "reactant_confs").exists()
