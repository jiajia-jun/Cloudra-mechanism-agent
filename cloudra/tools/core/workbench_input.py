"""Render a draft through the same native writer and coordinate settings as Agents."""
from __future__ import annotations

from cloudra.tools.core.geometry_inputs import (
    FrozenCoordinateInput,
    ScanCoordinateInput,
    atom_index_base,
    native_coordinate_settings,
)
from cloudra.tools.core.molecule import _copy_molecule, total_charge


def render_workbench_input(mol, settings: dict, frozen_coordinates: list[dict],
                           scan_coordinates: list[dict], output_path: str) -> str:
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
    from cloudra.tools.core.calculation_intent import validate_writer_request

    for field in ('engine', 'method', 'basis_set', 'charge', 'multiplicity'):
        if field not in settings or settings[field] is None:
            raise ValueError(f'Generating input requires explicit {field}')
    request = QmInputWriter_input_schema(
        **settings, source_type='xyz_file' if mol.HasProp('cloudra_graph_status') else 'mol_file',
        source_value='<workbench-draft>', output_path=output_path,
    )
    request = QmInputWriter.normalize_task_request(request)
    engine = request.engine
    base = atom_index_base(engine)
    mol = _copy_molecule(mol)
    if mol.HasProp('cloudra_graph_status') and mol.GetProp('cloudra_graph_status') == 'unresolved':
        mol.SetIntProp('cloudra_total_charge', request.charge)
    elif total_charge(mol) != request.charge:
        raise ValueError('Requested charge differs from the molecular graph charge')

    def native_entries(entries, model):
        result = []
        for raw in entries:
            entry = model.model_validate(raw)
            if any(i < 1 for i in entry.atoms):
                raise ValueError('Workbench coordinates use 1-based atom indices')
            result.append(entry.model_copy(update={'atoms': [i - 1 + base for i in entry.atoms]}))
        return result

    if frozen_coordinates or scan_coordinates:
        coordinates = native_coordinate_settings(
            mol, engine=engine, scans=native_entries(scan_coordinates, ScanCoordinateInput),
            freeze=native_entries(frozen_coordinates, FrozenCoordinateInput), scan_mode='grid',
            orca_blocks=request.orca_blocks, end_setting=request.end_setting,
        )
        if engine == 'gaussian' and coordinates['start_mismatches']:
            raise ValueError('start_geometry_mismatch: ' + '; '.join(coordinates['start_mismatches'])
                             + '. Gaussian scans start at the current geometry; edit the starting structure first.')
        tasks = _coordinate_tasks(request, scanning=bool(scan_coordinates))
        request = request.model_copy(update={
            **{field: coordinates[field] for field in ('orca_blocks', 'end_setting')}, 'task_type': tasks,
        })
    errors = [entry for entry in validate_writer_request(request.model_dump()) if entry['severity'] == 'error']
    if errors:
        raise ValueError('Native input settings refused: ' + '; '.join(entry['message'] for entry in errors))
    content = QmInputWriter.render_input(request, mol)
    errors = QmInputWriter.validate_rendered_input(request, content, charge=total_charge(mol))
    if errors:
        raise ValueError('Native input validation failed: ' + '; '.join(errors))
    return content


def _coordinate_tasks(request, *, scanning: bool) -> list[dict]:
    """Keep declared tasks/options; constraints are not permission to change them."""
    from cloudra.tools.core.calculation_intent import (
        _gaussian_modredundant,
        declared_native_tasks,
        native_tokens,
    )
    from cloudra.tools.core.native_input_sections import gaussian_code, gaussian_option

    tasks, unknown = declared_native_tasks(request.model_dump())
    if scanning:
        conflicting = tasks - {'minimum_opt', 'relaxed_scan'}
        if conflicting or unknown:
            raise ValueError('Scan conflicts with the declared calculation tasks: '
                             + ', '.join(sorted(conflicting) + unknown))
    elif not tasks & {'minimum_opt', 'ts_opt'}:
        raise ValueError('Freezing coordinates requires an optimization task; '
                         'the declared calculation cannot honor these frozen coordinates')
    result = [dict(task) for task in request.task_type]
    if request.engine == 'orca':
        if scanning and not tasks:
            result.append({'opt': None})
        return result
    keyword_tokens = native_tokens(gaussian_code(request.keywords))
    native_opt = any(gaussian_option(token)[0] == 'opt' for token in keyword_tokens)
    if native_opt and not _gaussian_modredundant(keyword_tokens):
        raise ValueError('Gaussian frozen/scan coordinates require ModRedundant in the native Opt options; '
                         'the existing native optimization declaration was preserved')
    has_opt = native_opt
    for task in result:
        for key, value in list(task.items()):
            if key.lower() != 'opt':
                continue
            has_opt = True
            options = gaussian_option('opt=' + str(value or '').lower())[1]
            if 'modredundant' not in options:
                task[key] = ','.join(filter(None, [str(value) if value is not None else '', 'ModRedundant']))
    if scanning and not has_opt:
        result.append({'opt': 'ModRedundant'})
    return result
