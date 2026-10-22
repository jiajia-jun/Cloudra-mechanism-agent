import pytest
from pydantic import ValidationError


def test_geometry_input_shapes_are_explicit_and_reject_typoes():
    from cloudra.tools.core.geometry_inputs import DistanceWindowInput, FrozenCoordinateInput, ScanCoordinateInput
    assert 'atoms' in DistanceWindowInput.model_json_schema()['properties']
    assert FrozenCoordinateInput(coord_type='bond', atoms=[0, 1]).atoms == [0, 1]
    with pytest.raises(ValidationError):
        DistanceWindowInput(atoms=[1, 2], min_ang=1, max_ang=2, max_angle=3)
    with pytest.raises(ValidationError):
        ScanCoordinateInput(coord_type='dihedral', atoms=[0, 1], scan_end=180, scan_steps=10)
    with pytest.raises(ValidationError):
        DistanceWindowInput(atoms=[1, 2], min_ang=2, max_ang=1)
    with pytest.raises(ValidationError):
        ScanCoordinateInput(coord_type='bond', atoms=[0, 1], scan_end=float('nan'), scan_steps=10)


def test_resume_requires_reason_without_model_revision_and_limits_have_no_time_estimate():
    from cloudra.tools.Chemtool.ts_search_process import TsResume_input_schema
    from cloudra.tools.core.ts_inputs import TsExecutionLimits
    with pytest.raises(ValidationError):
        TsResume_input_schema(run_id='run')
    request = TsResume_input_schema(run_id='run',reason='Repair environment')
    assert request.changes.model_fields_set == set()
    with pytest.raises(ValidationError):
        TsResume_input_schema(run_id='run', reason='Repair environment', expected_revision=2)
    assert 'estimated_cpu_hours' not in TsExecutionLimits.model_json_schema()['properties']


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('engine,atoms,freeze', [('gaussian',[1,2],[2,3]), ('orca',[0,1],[1,2])])
def test_scan_freezes_current_coordinate_in_native_numbering(tmp_path, engine, atoms, freeze):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
    target = tmp_path/'scan.inp'
    request = TsGuess_input_schema(charge=0, mode='scan_prepare', engine=engine, method='HF', basis_set='STO-3G',
        input_text='3\nwater\nO 0 0 0\nH 1 0 0\nH 0 1 0\n', output_path=str(target),
        scans=[{'coord_type':'bond','atoms':atoms,'scan_end':2,'scan_steps':5}],
        freeze=[{'coord_type':'bond','atoms':freeze}])
    result = TsGuess()._scan_prepare(request)
    assert result.is_success
    text = target.read_text()
    if engine == 'gaussian':
        assert 'B 2 3 F' in text
    else:
        assert '{ B 1 2 C }' in text
        assert text.count('%geom') == 1


@pytest.mark.usefixtures('rdkit_chemistry')
def test_scanning_and_freezing_same_pair_fails_before_writing(tmp_path):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
    target = tmp_path/'scan.inp'
    request = TsGuess_input_schema(mode='scan_prepare', engine='gaussian', method='HF', basis_set='STO-3G',
        input_text='2\nH2\nH 0 0 0\nH 1 0 0\n', output_path=str(target),
        scans=[{'atoms':[1,2],'scan_end':2,'scan_steps':5}],
        freeze=[{'coord_type':'bond','atoms':[2,1]}])
    with pytest.raises(ValueError, match='both scanned and frozen'):
        TsGuess()._scan_prepare(request)
    assert not target.exists()


@pytest.mark.parametrize('engine',['gaussian','orca'])
def test_structure_fields_keep_one_based_numbering_independent_of_engine(engine):
    from cloudra.tools.core.ts_inputs import normalize_ts_input_atoms
    from tests.ts_fixtures import calculation_input
    value = calculation_input(reactant_smiles='CC',product_smiles='CC',method='HF',engine=engine,
        reaction_center=[(1,2)],ring_order=[1,2,3],
        distance_filters=[{'atoms':[1,2],'min_ang':1,'max_ang':2}])
    normalized = normalize_ts_input_atoms(value,atom_tables={})
    assert normalized.reaction.selected_candidate is None
    assert normalized.reaction.reaction_center == [(0,1)]
    assert normalized.conformers.guidance.ring_order == [0,1,2]


def test_wire_projection_exposes_concrete_coordinate_fields():
    from cloudra.runtime_v2.tool_catalog import _render_alias
    from cloudra.tools.Chemtool.ts_search_process import TsPrepare_input_schema
    wire = "\n".join(_render_alias("Prepare", TsPrepare_input_schema.model_json_schema()))
    for field in ("min_ang", "max_ang", "scan_end", "scan_steps", "coord_type", "freeze"):
        assert field in wire
    assert "max_compute_seconds" not in wire
