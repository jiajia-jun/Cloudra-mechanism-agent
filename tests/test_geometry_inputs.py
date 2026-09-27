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


def test_resume_needs_only_run_id_and_budget_has_no_unimplemented_limit():
    from cloudra.tools.Chemtool.ts_search_process import TsResume_input_schema
    from cloudra.tools.core.ts_process import TsBudget
    assert TsResume_input_schema(run_id='run').adjustment.model_dump(exclude_defaults=True) == {}
    assert 'max_compute_seconds' not in TsBudget.model_json_schema()['properties']


@pytest.mark.parametrize('engine,atoms,freeze', [('gaussian',[1,2],[2,3]), ('orca',[0,1],[1,2])])
def test_scan_freezes_current_coordinate_in_native_numbering(tmp_path, engine, atoms, freeze):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
    target = tmp_path/'scan.inp'
    request = TsGuess_input_schema(mode='scan_prepare', engine=engine, method='HF/STO-3G',
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


def test_scanning_and_freezing_same_pair_fails_before_writing(tmp_path):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema
    target = tmp_path/'scan.inp'
    request = TsGuess_input_schema(mode='scan_prepare', method='HF/STO-3G',
        input_text='2\nH2\nH 0 0 0\nH 1 0 0\n', output_path=str(target),
        scans=[{'atoms':[1,2],'scan_end':2,'scan_steps':5}],
        freeze=[{'coord_type':'bond','atoms':[2,1]}])
    with pytest.raises(ValueError, match='both scanned and frozen'):
        TsGuess()._scan_prepare(request)
    assert not target.exists()


@pytest.mark.parametrize('engine,base',[('gaussian',1),('orca',0)])
def test_workflow_atom_fields_share_engine_numbering(engine, base):
    from cloudra.tools.core.geometry_inputs import normalize_ts_atoms
    from cloudra.tools.core.ts_process import TsDeclaration
    declaration = TsDeclaration(reactant_smiles='CC', product_smiles='CC', method='HF', engine=engine,
        atom_map=[base,base+1], reaction_center=[(base,base+1)], ring_order=[base,base+1,base+2],
        distance_filters=[{'atoms':[base,base+1],'min_ang':1,'max_ang':2}])
    internal = normalize_ts_atoms(declaration, engine=engine)
    assert internal.atom_map == [0,1]
    assert internal.reaction_center == [(0,1)]
    assert internal.ring_order == [0,1,2]
    assert internal.distance_filters[0].atoms == [0,1]


def test_wire_projection_exposes_concrete_coordinate_fields():
    from cloudra.runtime_v2.tool_catalog import _render_alias
    from cloudra.tools.Chemtool.ts_search_process import TsPrepare_input_schema
    wire = "\n".join(_render_alias("Prepare", TsPrepare_input_schema.model_json_schema()))
    for field in ("min_ang", "max_ang", "scan_end", "scan_steps", "coord_type", "freeze"):
        assert field in wire
    assert "max_compute_seconds" not in wire
