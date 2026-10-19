"""Structure readers preserve native declarations without running QM backends."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cloudra.tools.Chemtool.electronic_analysis import (
    ElectronicAnalysis,
    ElectronicAnalysis_input_schema,
    ElectronicAnalysis_output_schema,
)
from cloudra.tools.Chemtool.internal_coordinates import (
    InternalCoordinates,
    InternalCoordinates_input_schema,
)
from cloudra.tools.core.molecule import read_molecule, to_xyz, total_charge

GAUSSIAN = (
    "%chk=water.chk\n%mem=1GB\n#p hf/sto-3g\n\n2026 10\n\n-1 2\n"
    "O 0 0 0\nH 0 0 0.96\nH 0.92 0 -0.24\n\n"
)
XYZ = "3\n\nO 0 0 0\nH 0 0 0.96\nH 0.92 0 -0.24\n"


@pytest.mark.parametrize("suffix", [None, "gjf", "com", "gau", "txt", "xyz"])
def test_gaussian_content_has_one_reading_for_paths_and_inline_text(tmp_path, suffix):
    arguments = {"input_text": GAUSSIAN}
    if suffix is not None:
        path = tmp_path / f"water.{suffix}"
        path.write_text(GAUSSIAN)
        arguments = {"input_path": path}

    mol = read_molecule(**arguments)

    assert mol.GetNumAtoms() == 3
    assert mol.GetNumBonds() == 0
    assert [atom.GetFormalCharge() for atom in mol.GetAtoms()] == [0, 0, 0]
    assert mol.GetProp("cloudra_graph_status") == "unresolved"
    assert total_charge(mol) == -1
    assert mol.GetIntProp("cloudra_multiplicity") == 2
    assert mol.GetProp("cloudra_coordinate_units") == "angstrom"
    np.testing.assert_array_equal(mol.GetConformer().GetPositions(), [[0, 0, 0], [0, 0, .96], [.92, 0, -.24]])


def test_gaussian_decimal_coordinates_and_explicit_angstroms_are_supported():
    text = GAUSSIAN.replace("hf/sto-3g", "hf/sto-3g units=(angstroms)").replace("O 0 0 0", "O 0.0 0.0 0.0")

    assert read_molecule(input_text=text).GetNumAtoms() == 3


@pytest.mark.parametrize('units', ['bohr', 'au', 'a.u.', '( bohr )'])
def test_gaussian_bohr_coordinates_are_converted_to_angstroms(units):
    from ase.units import Bohr

    text = GAUSSIAN.replace('hf/sto-3g', f'hf/sto-3g units={units}')

    mol = read_molecule(input_text=text)

    np.testing.assert_allclose(mol.GetConformer().GetPositions(), np.array([[0, 0, 0], [0, 0, .96], [.92, 0, -.24]]) * Bohr)
    assert mol.GetProp('cloudra_coordinate_units') == 'angstrom'
    assert mol.GetProp('cloudra_source_coordinate_units') == 'bohr'
    assert total_charge(mol) == -1


def test_gaussian_route_keyword_adjacent_to_hash_keeps_its_units():
    from ase.units import Bohr

    mol = read_molecule(input_text=GAUSSIAN.replace('#p hf/sto-3g', '#units=bohr hf/sto-3g'))

    assert mol.GetConformer().GetAtomPosition(1).z == pytest.approx(.96 * Bohr)


def test_gaussian_explicit_charge_must_match_the_native_declaration():
    with pytest.raises(ValueError, match="charge.*0.*-1"):
        read_molecule(input_text=GAUSSIAN, charge=0)
    assert total_charge(read_molecule(input_text=GAUSSIAN, charge=-1)) == -1


@pytest.mark.parametrize('task', ['qst2', 'qst3', 'calcfc, qst2', 'qst3 , calcfc'])
def test_gaussian_qst_multi_geometry_job_is_rejected_by_the_single_structure_reader(task):
    text = GAUSSIAN.replace('hf/sto-3g', f'hf/sto-3g opt=({task})')
    text += 'second geometry\n\n-1 2\nO 0 0 0\nH 0 0 1.2\nH 1.2 0 0\n\n'

    with pytest.raises(ValueError, match='QST2/QST3.*multiple geometries'):
        read_molecule(input_text=text)


@pytest.mark.parametrize("text,reason", [
    (GAUSSIAN + "--Link1--\n# hf/sto-3g geom=allcheck\n\n", "Link1"),
    (GAUSSIAN.replace("hf/sto-3g", "hf/sto-3g geom=check"), "checkpoint"),
    (GAUSSIAN.replace("hf/sto-3g", "hf/sto-3g geom=(allcheck)"), "checkpoint"),
    (GAUSSIAN.replace("hf/sto-3g", "hf/sto-3g geom=( check )"), "checkpoint"),
    (GAUSSIAN.replace("#p hf/sto-3g", "#geom=check hf/sto-3g"), "checkpoint"),
    (GAUSSIAN.replace("hf/sto-3g", "hf/sto-3g units=meters"), "units"),
    (GAUSSIAN.replace("hf/sto-3g", "hf/sto-3g units=bohr units=angstroms"), "units"),
    (GAUSSIAN.replace("O 0 0 0\nH 0 0 0.96\nH 0.92 0 -0.24", "O\nH 1 .96\nH 1 .96 2 104.5"), "Cartesian"),
    (GAUSSIAN.replace("O 0 0 0", "O 0 0 nan"), "finite"),
    (GAUSSIAN.replace("O 0 0 0", "O(Iso=18) 0 0 0"), "atom"),
    (GAUSSIAN.replace("-1 2\n", "-1 0\n"), "multiplicity"),
])
def test_unsupported_gaussian_inputs_are_rejected_without_guessing(text, reason):
    with pytest.raises(ValueError, match=reason):
        read_molecule(input_text=text)


def test_explicit_xyz_does_not_silently_accept_gaussian_content():
    with pytest.raises(ValueError, match="Gaussian.*auto"):
        read_molecule(input_text=GAUSSIAN, input_format="xyz")


@pytest.mark.parametrize("text", [XYZ, "O 0 0 0\nH 0 0 0.96\nH 0.92 0 -0.24\n"])
def test_shared_reader_accepts_real_headered_and_headerless_xyz(text):
    mol = read_molecule(input_text=text)

    assert mol.GetNumAtoms() == 3
    assert mol.GetNumBonds() == 0
    assert total_charge(mol) == 0


def test_shared_reader_keeps_extended_xyz_property_order_and_last_trajectory_frame():
    text = (
        '1\nProperties=pos:R:3:species:S:1\n0 0 0 H\n'
        '1\nProperties=pos:R:3:species:S:1\n1.25 0 0 O\n'
    )

    mol = read_molecule(input_text=text)

    assert mol.GetNumAtoms() == 1
    assert mol.GetAtomWithIdx(0).GetSymbol() == 'O'
    assert mol.GetConformer().GetAtomPosition(0).x == 1.25


@pytest.mark.parametrize('from_path', [False, True])
def test_cif_leading_comment_is_not_misidentified_as_gaussian(tmp_path, from_path):
    text = (
        '# generated using pymatgen\ndata_C\n'
        '_cell_length_a 3.57\n_cell_length_b 3.57\n_cell_length_c 3.57\n'
        '_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n'
        "_symmetry_space_group_name_H-M 'P 1'\n"
        'loop_\n_atom_site_label\n_atom_site_type_symbol\n'
        '_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\nC1 C 0 0 0\n'
    )
    arguments = {'input_text': text, 'input_format': 'cif'}
    if from_path:
        path = tmp_path / 'carbon.cif'
        path.write_text(text)
        arguments = {'input_path': path}

    mol = read_molecule(**arguments)

    assert mol.GetNumAtoms() == 1
    assert mol.GetAtomWithIdx(0).GetSymbol() == 'C'
    assert mol.GetNumBonds() == 0


@pytest.mark.parametrize('fmt', ['auto', 'mol'])
def test_mol_title_starting_with_hash_keeps_its_declared_graph(fmt):
    from rdkit import Chem

    source = Chem.MolFromSmiles('CO')
    source.SetProp('_Name', '#p molecule title')
    source.AddConformer(Chem.Conformer(2))

    mol = read_molecule(input_text=Chem.MolToMolBlock(source), input_format=fmt)

    assert mol.GetNumBonds() == 1
    assert mol.GetProp('_Name') == '#p molecule title'


@pytest.mark.parametrize("text", [
    "nonsense\nO 0 0 0\n",
    "0\n\n",
    "2\n\nO 0 0 0\n",
    "1\n\nO 0 0 0\nH 0 0 1\n",
    "1\n\nO 0 0 nan\n",
    "not an xyz header\nO 0 0 0\n",
])
def test_unknown_or_malformed_coordinate_text_has_an_actionable_format_error(text):
    with pytest.raises(ValueError, match="XYZ|format|finite"):
        read_molecule(input_text=text)


def test_missing_structure_path_has_a_named_path_error(tmp_path):
    path = tmp_path / "missing.gjf"

    with pytest.raises(FileNotFoundError, match="Input structure file.*missing.gjf"):
        read_molecule(input_path=path)


def test_internal_coordinates_inherits_native_charge_without_default_override():
    mol, _, _ = InternalCoordinates._load_molecule(None, GAUSSIAN, "auto", None)

    assert total_charge(mol) == -1
    assert mol.GetIntProp("cloudra_multiplicity") == 2
    with pytest.raises(ValueError, match="charge.*0.*-1"):
        InternalCoordinates._load_molecule(None, GAUSSIAN, "auto", 0)


@pytest.mark.asyncio
async def test_internal_coordinates_missing_path_returns_existing_path_guidance(tmp_path, mock_session):
    tool = InternalCoordinates(subagent=SimpleNamespace(working_directory=str(tmp_path)))

    result = await tool.tool_call(InternalCoordinates_input_schema(input_path="missing.gjf"), mock_session)

    assert result.is_success is False
    assert "missing.gjf" in result.message
    assert "Tried:" in result.message


@pytest.mark.asyncio
@pytest.mark.parametrize("from_path", [False, True])
async def test_electronic_analysis_receives_native_charge_and_spin_before_backend(
    tmp_path, mock_session, monkeypatch, from_path,
):
    def inspect_backend(self, request, molecule):
        return ElectronicAnalysis_output_schema(is_success=True, summary={
            "charge": request.charge, "spin": request.spin, "xyz": to_xyz(molecule),
        })

    monkeypatch.setattr(ElectronicAnalysis, "_run_xtb", inspect_backend)
    arguments = {"input_text": GAUSSIAN}
    if from_path:
        path = tmp_path / "water.gjf"
        path.write_text(GAUSSIAN)
        arguments = {"input_path": "water.gjf"}
    tool = ElectronicAnalysis(subagent=SimpleNamespace(working_directory=str(tmp_path)))

    result = await tool.tool_call(ElectronicAnalysis_input_schema(backend="xtb", **arguments), mock_session)

    assert result.is_success, result.message
    assert result.summary["charge"] == -1
    assert result.summary["spin"] == 2
    assert result.summary["xyz"].startswith("3\n")
    assert "%chk" not in result.summary["xyz"]


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides,reason", [({"charge": 0}, "charge"), ({"spin": 1}, "spin")])
async def test_electronic_analysis_rejects_explicit_native_metadata_conflicts_before_backend(
    mock_session, monkeypatch, overrides, reason,
):
    def no_calculation(*_):
        pytest.fail("Conflicting native metadata must fail before calculation")

    monkeypatch.setattr(ElectronicAnalysis, "_run_xtb", no_calculation)

    result = await ElectronicAnalysis().tool_call(ElectronicAnalysis_input_schema(
        input_text=GAUSSIAN, backend="xtb", **overrides,
    ), mock_session)

    assert result.is_success is False
    assert reason in result.message
    assert "Gaussian" in result.message


@pytest.mark.asyncio
async def test_electronic_analysis_rejects_garbage_instead_of_skipping_headers(mock_session, monkeypatch):
    def no_calculation(*_):
        pytest.fail("Unknown structure text must fail before calculation")

    monkeypatch.setattr(ElectronicAnalysis, "_run_xtb", no_calculation)

    result = await ElectronicAnalysis().tool_call(ElectronicAnalysis_input_schema(
        input_text="unknown header\nO 0 0 0\n", backend="xtb",
    ), mock_session)

    assert result.is_success is False
    assert "format" in result.message.lower()


@pytest.mark.asyncio
async def test_xtb_receives_only_normalized_xyz_and_native_electronic_state(mock_session, monkeypatch):
    from cloudra.tools.Chemtool import electronic_analysis

    observed = {}

    def fake_process(arguments, *, cwd, **kwargs):
        observed['arguments'] = arguments
        observed['input'] = (Path(cwd) / 'input.xyz').read_text()
        return SimpleNamespace(returncode=0, stdout='| TOTAL ENERGY -5.0 Eh |\n', stderr='')

    monkeypatch.setattr(electronic_analysis.shutil, 'which', lambda _: '/unused/xtb')
    monkeypatch.setattr(electronic_analysis.subprocess, 'run', fake_process)

    result = await ElectronicAnalysis().tool_call(ElectronicAnalysis_input_schema(
        input_text=GAUSSIAN, backend='xtb',
    ), mock_session)

    assert result.is_success, result.message
    assert observed['arguments'][-4:] == ['--chrg', '-1', '--uhf', '1']
    assert observed['input'].startswith('3\n\n')
    assert '%chk' not in observed['input']
    assert read_molecule(input_text=observed['input']).GetNumAtoms() == 3
    assert 'Charge / Spin  : -1 / 2' in result.report


def test_internal_analysis_reports_the_inherited_native_charge(tmp_path):
    request = InternalCoordinates_input_schema(input_text=GAUSSIAN, zmat_path=str(tmp_path / 'water.zmat'))

    result = InternalCoordinates()._analyze(request)

    assert result.is_success, result.message
    assert 'Total charge: -1' in result.report
