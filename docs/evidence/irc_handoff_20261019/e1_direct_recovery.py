"""Replay E1's direct IRC handoff without submitting or fabricating QM results.

Run with the absolute directory containing E1's original calc files. All input
copies, runtime data and ready-to-review GJFs stay in a fresh /tmp directory.
Only --output may explicitly save the compact report elsewhere. The original
evidence is read-only; this probe is not an end-to-end QM success claim.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digests(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob('*')) if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('calc_dir', type=Path, help='Absolute path to the external E1 calc directory')
    parser.add_argument('--output', type=Path, help='Report JSON; defaults to the isolated /tmp directory')
    args = parser.parse_args()
    require(args.calc_dir.is_absolute(), 'calc_dir must be an absolute path')
    source = args.calc_dir.resolve(strict=True)
    require(source.is_dir(), 'calc_dir must be a directory')
    output = args.output.resolve() if args.output else None
    require(output is None or not output.is_relative_to(source), 'Report output cannot modify the original evidence')
    originals = digests(source)
    work = Path(tempfile.mkdtemp(prefix='cloudra-e1-direct-recovery-', dir='/tmp'))
    workspace = work / 'workspace'
    calc = workspace / 'calc'
    shutil.copytree(source, calc)
    os.environ['CLOUDRA_CONFIG_FILE'] = str(work / 'absent.yaml')
    os.environ['CLOUDRA_DATA_DIR'] = str(work / 'runtime')
    os.environ['CLOUDRA_DAEMON_WATCHDOG'] = 'off'
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    os.chdir(workspace)

    from cloudra.base.session_class import Session
    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.services.compute_admission import declared_cpus, declared_memory_mb
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
    from cloudra.tools.core.calculation_intent import (
        compare_calculation_input,
        gaussian_routes,
        inspect_input,
        native_input_geometry,
    )
    from cloudra.tools.core.irc_endpoint_artifacts import read_irc_endpoint_artifacts
    from cloudra.tools.core.irc_evidence import irc_endpoint_geometries, verify_short_irc_direction
    from cloudra.tools.core.irc_path import parse_xyz, same_geometry
    from cloudra.tools.core.native_input_sections import gaussian_sections

    # This is an E1-specific reproduction, not a method-selection heuristic.
    # Refuse changed source settings instead of guessing how to regenerate them.
    route = '#p opt=(maxcycle=200) freq B3LYP/def2SVP EmpiricalDispersion=GD3BJ int=ultrafine\n\n'
    settings = dict(engine='gaussian', method='B3LYP', basis_set='def2SVP',
        keywords='EmpiricalDispersion=GD3BJ int=ultrafine',
        task_type=[{'opt': '(maxcycle=200)'}, {'freq': None}],
        charge=-1, multiplicity=1, nproc=8, mem='8GB')
    expected_calculation = dict(engine='gaussian', method=settings['method'], basis_set=settings['basis_set'],
        keywords='opt=(maxcycle=200) freq ' + settings['keywords'])
    verified_inputs = {}
    for name in ('endpoint_rev5.gjf', 'endpoint_fwd5.gjf'):
        path = calc / name
        text = path.read_text()
        sections = gaussian_sections(text)
        require(len(sections) == 1, f'{name}: expected one native Gaussian job')
        require(sorted(gaussian_routes(text)[0]) == sorted(gaussian_routes(route)[0]),
            f'{name}: source route differs from the explicitly reproduced E1 settings')
        require(sections[0].charge == (-1, 1) and not any(sections[0].trailing),
            f'{name}: source molecular state or trailing settings changed')
        link0 = {}
        for line in text.splitlines():
            if line.strip().startswith('#'):
                break
            if line.strip().startswith('%'):
                key, separator, value = line.strip().partition('=')
                require(separator and key.lower() not in link0, f'{name}: ambiguous Link0 command')
                link0[key.lower()] = value
        require(set(link0) == {'%chk', '%mem', '%nprocshared'}, f'{name}: additional Link0 setting')
        require(link0['%mem'].upper() == settings['mem'] and int(link0['%nprocshared']) == settings['nproc'],
            f'{name}: source resource declarations changed')
        require(declared_cpus(str(path), 'gaussian') == 8 and declared_memory_mb(str(path), 'gaussian') == 8192,
            f'{name}: shared native resource parser disagrees')
        differences = compare_calculation_input(text, expected_calculation, charge=-1, multiplicity=1)
        require(not differences, f'{name}: shared calculation comparison failed: {differences}')
        smiles = [line.partition(':')[2].strip() for line in text.splitlines()
                  if line.strip().lower().startswith('smiles:')]
        require(len(smiles) == 1, f'{name}: missing or ambiguous declared endpoint identity')
        verified_inputs[name] = dict(path=str(path), sha256=originals[name],
            route=sections[0].route, molecular_state=sections[0].charge,
            link0=link0, declared_smiles=smiles[0], full_settings_match=True)

    native_ends = irc_endpoint_geometries(calc / 'irc3.log')
    require(native_ends is not None, 'Original IRC must contain both canonical native sides')
    snapshot = snapshot_evidence_file(calc / 'irc3.log', workspace)
    exported = read_irc_endpoint_artifacts(snapshot.snapshot_path)
    require(set(exported) == {'irc_end_a_path', 'irc_end_b_path'}, 'DAG snapshot did not export both canonical sides')
    require(all(snapshot.metadata.get(key) == value for key, value in exported.items()),
        'DAG snapshot metadata does not expose the validated canonical paths')
    matches = {side: same_geometry(parse_xyz(Path(exported[f'irc_end_{side}_path']).read_text()), native_ends[index])
               for index, side in enumerate(('a', 'b'))}
    require(all(matches.values()), 'Exported XYZ differs from the native canonical IRC outer frame')
    passed, details = verify_short_irc_direction(snapshot.snapshot_path, [calc / 'ts1.log'],
        [calc / 'endpoint_fwd5.log'], [calc / 'endpoint_rev5.log'], charge=-1,
        reactant_smiles=verified_inputs['endpoint_rev5.gjf']['declared_smiles'],
        product_smiles=verified_inputs['endpoint_fwd5.gjf']['declared_smiles'])
    require(not passed, 'Original unmatched Opt evidence must remain scientifically unaccepted')
    for name in ('endpoint_rev5.log', 'endpoint_fwd5.log'):
        require(any(name in detail and 'matches neither actual IRC' in detail for detail in details),
            f'Verifier did not identify the actual unmatched Opt: {name}')

    async def prepare_inputs():
        session = Session(id='e1-direct-recovery', path=str(work / 'session.json'))
        outputs = {}
        for index, side in enumerate(('a', 'b')):
            destination = work / 'ready_for_recalculation' / f'irc_end_{side}_opt_freq.gjf'
            request = QmInputWriter_input_schema(**settings, source_type='xyz_file',
                source_value=exported[f'irc_end_{side}_path'], output_path=str(destination),
                chk_name=str(destination.with_suffix('.chk')),
                title=f'E1 canonical IRC side {side.upper()}; Opt/Freq pending; identity unassigned')
            result = await QmInputWriter().tool_call(request, session)
            require(result.is_success, f'Public qm_input_writer failed: {result.message}')
            content = Path(result.input_path).read_text()
            rows = native_input_geometry(content, engine='gaussian')
            generated = ([row[0] for row in rows], [row[1] for row in rows])
            differences = compare_calculation_input(content, expected_calculation, charge=-1, multiplicity=1)
            require(not differences, f'Generated input lost copied E1 settings: {differences}')
            require(sorted(gaussian_routes(content)[0]) == sorted(gaussian_routes(route)[0]),
                'Generated route differs from the verified original E1 calculation')
            require(declared_cpus(result.input_path, 'gaussian') == 8
                and declared_memory_mb(result.input_path, 'gaussian') == 8192, 'Generated resources changed')
            require(same_geometry(generated, native_ends[index]), 'Writer roundtrip broke native IRC identity')
            outputs[side] = dict(writer_request=request.model_dump(mode='json'),
                writer_result=result.model_dump(mode='json'),
                native_intent=inspect_input(content, engine='gaussian').model_dump(mode='json'),
                canonical_identity_match=True, original_scientific_settings_match=True,
                sha256=hashlib.sha256(Path(result.input_path).read_bytes()).hexdigest())
        return outputs

    inputs = asyncio.run(prepare_inputs())
    require(digests(source) == originals, 'Original evidence changed during the probe')
    require(digests(calc) == originals, 'Copied native evidence changed during the probe')
    report = dict(source_calc_dir=str(source), temporary_workspace=str(work),
        qm_submitted=False, qm_outputs_fabricated=False,
        limitation='Prepared inputs only. New Opt/Freq jobs and scientific acceptance have not been performed.',
        copied_native_hashes=originals, original_hashes_unchanged=True, copied_native_hashes_unchanged=True,
        verified_original_inputs=verified_inputs, reused_writer_settings=settings,
        checkpoint_policy='New checkpoint paths stay with the new /tmp inputs; no old checkpoint is read.',
        dag_snapshot=snapshot.model_dump(mode='json'), exported_endpoints=exported,
        canonical_xyz_matches_native=matches,
        original_evidence_verifier=dict(passed=passed, details=details), prepared_inputs=inputs)
    output = output or work / 'e1_direct_recovery.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(report=str(output), temporary_workspace=str(work),
        original_evidence_accepted=passed, canonical_xyz_matches_native=matches,
        prepared_inputs={side: item['writer_result']['input_path'] for side, item in inputs.items()},
        original_hashes_unchanged=True, qm_submitted=False), indent=2))


if __name__ == '__main__':
    main()
