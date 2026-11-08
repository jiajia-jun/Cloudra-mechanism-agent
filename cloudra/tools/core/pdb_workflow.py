"""Single shared workflow for the two thin PDB tools."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from cloudra.tools.core.pdb_structure import (
    annotation_inventory,
    components,
    filter_components,
    gemmi_backend,
    load_structure,
    prune_connections,
    select_altlocs,
    summarize,
    verify_structure,
    write_structure,
)


def inspect_missing(*args):
    from cloudra.tools.core.pdb_repair import inspect_missing as analyze
    return analyze(*args)


def analyze_interactions(*args):
    from cloudra.tools.core.pdb_interactions import analyze_interactions as analyze
    return analyze(*args)


def inspect_structure(options):
    result = dict(is_success=False, warnings=[], analysis_status={})
    stage = 'parse'
    try:
        structure, keys, summary = load_structure(options['input_path'], options['model_index'], options['chains'])
        result.update(structure_summary=summary, components=components(structure, keys))
        versions = {'gemmi': gemmi_backend().__version__}
        for stage, analyze, arguments in (
            ('missing', inspect_missing, (structure, keys)),
            ('interactions', analyze_interactions, (structure, keys, options['interaction_overrides'])),
        ):
            try:
                findings = analyze(*arguments)
            except Exception as exc:
                result['analysis_status'][stage] = dict(status='unavailable' if isinstance(exc, ImportError) else 'failed', reason=str(exc))
                continue
            result['analysis_status'].update(findings.pop('analysis_status', {}))
            result['warnings'].extend(findings.pop('warnings', []))
            versions.update(findings.pop('backend_versions', {}))
            result.update(findings)
        result['structure_summary']['backend_versions'] = versions
        result['is_success'] = not any(item['status'] in {'failed', 'unavailable'} for item in result['analysis_status'].values())
        result['message'] = 'Inspection completed; water/metal labels are geometry candidates.' if result['is_success'] else 'Inspection incomplete; see analysis_status for missing or failed analyses.'
    except Exception as exc:
        result['analysis_status'][stage] = dict(status='unavailable' if isinstance(exc, ImportError) else 'failed', reason=str(exc))
        result['message'] = f'{stage} failed: {exc}'
    return result


def effective_options(options):
    defaults = dict(waters='candidates' if options['mode'] == 'docking' else 'all',
                    ligands='all', metals='all', add_missing_atoms=options['mode'] != 'preserve',
                    add_missing_residues='none')
    return {**options, **{key: options[key] if options[key] is not None else value for key, value in defaults.items()}}


def _selected_gaps(findings, options):
    all_gaps = [gap for kind in ('internal_gaps', 'n_terminal_gaps', 'c_terminal_gaps') for gap in findings.get(kind, [])]
    if options['gap_ids'] is not None and set(options['gap_ids']) - {g['gap_id'] for g in all_gaps}:
        raise ValueError('gap_ids contains gaps absent from this selected input')
    allowed = {g['gap_id'] for g in all_gaps if options['add_missing_residues'] == 'all' or
               options['add_missing_residues'] == 'internal' and g['kind'] == 'internal'}
    if options['gap_ids'] is not None:
        if set(options['gap_ids']) - allowed:
            raise ValueError('gap_ids must be within add_missing_residues selected types')
        allowed &= set(options['gap_ids'])
    selected = [g for g in all_gaps if g['gap_id'] in allowed]
    if any(g.get('status') not in {'detected', 'confirmed', 'completed', 'missing', 'available', 'resolved'} for g in selected):
        raise ValueError('Requested gaps do not have an unambiguous declared sequence and insertion position')
    if options['add_missing_residues'] != 'none':
        status = findings.get('analysis_status', {}).get('missing_residues', {})
        if options['gap_ids'] is None and status.get('status') in {'unknown', 'unavailable', 'failed', 'unsupported'}:
            raise ValueError(f"Missing-residue analysis is {status.get('status')}: {status.get('reason', '')}")
    return selected


def clean_structure(options):
    effective = effective_options(options)
    result = dict(is_success=False, effective_options=effective, changes=[], unresolved=[], warnings=[])
    stage = 'validate_paths'
    published = []
    temporary = []
    try:
        output = Path(effective['output_path'])
        log_path = Path(str(output) + '.changes.json')
        if output.suffix.lower() not in {'.pdb', '.cif', '.mmcif'}:
            raise ValueError('output_path must end in .pdb, .cif or .mmcif')
        if output.resolve() == Path(effective['input_path']).resolve():
            raise ValueError('output_path must be a new file, distinct from the input')
        if output.exists() or log_path.exists():
            raise FileExistsError('Output structure or changes JSON already exists; choose a new output_path')
        if not output.parent.is_dir():
            raise FileNotFoundError(f'Output directory does not exist: {output.parent}')
        stage = 'parse'
        structure, keys, input_summary = load_structure(effective['input_path'], effective['model_index'], effective['chains'])
        versions = {'gemmi': gemmi_backend().__version__}
        original_components = components(structure, keys)
        # Exact selections are validated even when their component policy would retain everything.
        known = set(keys.values())
        if set(effective['keep_residue_keys']) & set(effective['remove_residue_keys']):
            raise ValueError('The same residue_key cannot be both kept and removed')
        if (set(effective['keep_residue_keys']) | set(effective['remove_residue_keys'])) - known:
            raise ValueError('A residue_key is absent from selected model/chains; copy exact keys from pdb_inspect')
        stage = 'altloc_selection'
        result['changes'].extend(select_altlocs(structure, keys, effective['altloc']))
        stage = 'required_analysis'
        selected_gaps = []
        missing = None
        if effective['add_missing_residues'] != 'none' or effective['gap_ids'] is not None:
            missing = inspect_missing(structure, keys)
            selected_gaps = _selected_gaps(missing, effective)
        candidates, rules = set(), {}
        if effective['waters'] == 'candidates' and any(r.is_water() for c in structure[0] for r in c):
            interactions = analyze_interactions(structure, keys, effective['interaction_overrides'])
            incomplete = {name: value for name, value in interactions['analysis_status'].items()
                          if value['status'] != 'completed'}
            if incomplete:
                raise ValueError(f'Candidate-water analysis incomplete; no waters were removed: {incomplete}')
            candidates = {entry['residue_key'] for entry in interactions['water_candidates']}
            versions.update(interactions.get('backend_versions', {}))
            rules = interactions.get('effective_rules', {})
            result['warnings'].extend(interactions.get('warnings', []))
        stage = 'component_selection'
        keys, changes = filter_components(structure, keys, effective, candidates)
        result['changes'].extend(changes)
        # Component removal can shift indices; derive insertion positions from preserved anchors.
        reverse = {key: pair for pair, key in keys.items()}
        insertions = set()
        for gap in selected_gaps:
            missing_anchors = [gap[name] for name in ('left_anchor', 'right_anchor')
                               if gap.get(name) is not None and gap[name] not in reverse]
            if missing_anchors:
                raise ValueError(f"Selected gap {gap['gap_id']} requires removed anchors: {missing_anchors}; retain its anchors or omit that gap")
            right = reverse.get(gap.get('right_anchor'))
            left = reverse.get(gap.get('left_anchor'))
            anchor = right or left
            if anchor is None:
                raise ValueError(f"Selected gap {gap['gap_id']} lost both anchors during component filtering")
            position = (anchor[0], right[1] if right else left[1] + 1)
            if position in insertions:
                raise ValueError(f"Selected gap {gap['gap_id']} shares an insertion position with another selected gap")
            insertions.add(position)
            gap['insertion_position'] = dict(chain_index=position[0], residue_index=position[1])
        stage = 'repair'
        if any((effective['add_missing_atoms'], effective['replace_nonstandard_residues'],
                effective['add_hydrogens'], selected_gaps)):
            from cloudra.tools.core.pdb_repair import repair_structure
            structure, changes, unresolved, warnings, backends = repair_structure(structure, keys, effective, selected_gaps)
            result['changes'].extend(changes)
            result['unresolved'].extend(unresolved)
            result['warnings'].extend(warnings)
            versions.update(backends)
        result['warnings'].append('Selected-model output is not a lossless experimental-record archive. Unselected models, assembly references, and annotations not representable after selection/modeling are not retained as validated evidence.')
        result['changes'].extend(prune_connections(structure))
        stage = 'write_and_verify'
        # Stage and re-read before publishing either file. Exclusive hard links prevent overwrites.
        fd, temp = tempfile.mkstemp(prefix='.pdb-clean-', suffix=output.suffix, dir=output.parent)
        os.close(fd)
        temporary.append(Path(temp))
        write_structure(structure, temp)
        actual = verify_structure(structure, temp)
        before_annotations, after_annotations = annotation_inventory(structure), annotation_inventory(actual)
        for category, count in before_annotations.items():
            if count != after_annotations[category]:
                result['changes'].append(dict(kind='annotation_serialization_change', category=category,
                                              before_count=count, after_count=after_annotations[category]))
        log = dict(purpose=effective['purpose'], effective_options=effective, effective_rules=rules,
                   backend_versions=versions, input_summary=input_summary, output_summary=summarize(structure),
                   annotation_inventory_before_write=before_annotations, annotation_inventory_after_read=after_annotations,
                   input_components=original_components, changes=result['changes'], unresolved=result['unresolved'],
                   warnings=result['warnings'], modeled_gaps=selected_gaps,
                   candidate_water_keys=sorted(candidates),
                   annotation_retention='Gemmi-retained metadata is written where representable. Selection/modeling can invalidate experimental annotation and connection references; output annotations are not a lossless archive.')
        fd, temp_log = tempfile.mkstemp(prefix='.pdb-clean-', suffix='.json', dir=output.parent)
        temporary.append(Path(temp_log))
        with os.fdopen(fd, 'w') as handle:
            json.dump(log, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write('\n')
        os.link(temp, output)
        published.append(output)
        os.link(temp_log, log_path)
        published.append(log_path)
        result.update(is_success=True, output_path=str(output), change_log_path=str(log_path),
                      message='Requested cleaning operations completed. Review unresolved items and geometry before downstream simulation.')
    except Exception as exc:
        for path in reversed(published):
            path.unlink(missing_ok=True)
        result['message'] = f'{stage} failed: {exc}'
        result['unresolved'].append(dict(stage=stage, reason=str(exc), requested_operations_completed=False))
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)
    return result
