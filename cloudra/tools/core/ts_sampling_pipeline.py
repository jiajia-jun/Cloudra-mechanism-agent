"""Explicit, ledger-owned supplemental sampling; archives every returned frame."""
from __future__ import annotations

import json
from pathlib import Path


def advance_sampling(record):
    from rdkit import Chem

    from cloudra.runtime.chem_task import ChemTask, read_task_result
    from cloudra.services.compute_store import TERMINAL_STATES
    from cloudra.services.conformer_store import (
        get_region_snapshot,
        list_candidates,
        put_candidate,
        put_region_snapshot,
    )
    from cloudra.services.ts_pipeline_context import pipeline_database
    from cloudra.tools.core.conformer_capture import CandidateCapture
    from cloudra.tools.core.conformer_regions import partition_candidates
    from cloudra.tools.core.preorganization import load_resolved_graph
    from cloudra.tools.core.structure_builder import (
        BuildStrategy,
        PreparationRequest,
        StructureInput,
        prepare_structure,
    )
    from cloudra.tools.core.ts_process import (
        TsJobStep,
        _block,
        _job_directory,
        _read_job_state,
        _submit_step,
        _write_immutable_input,
    )

    decision = record.sampling_pending
    db = pipeline_database()
    candidates = list_candidates(db, record.catalog_id, project_id=record.owner_conversation_id, owner_id=record.owner_session_id)
    previous = get_region_snapshot(db, record.catalog_id, record.partition_revision,
        project_id=record.owner_conversation_id, owner_id=record.owner_session_id)
    directory = Path(_job_directory(record, 'sampling'))
    directory.mkdir(parents=True, exist_ok=True)
    prepared = prepare_structure(PreparationRequest(structure=StructureInput(kind='smiles', value=record.declaration.reactant_smiles),
        output_dir=str(directory/'graph'), strategy=BuildStrategy(embed=False, optimize=False)))
    graph = load_resolved_graph(prepared, allow_unoptimized=True)
    ids = [f'a{a.input_atom_index}' if a.origin == 'input_atom' else f'h{a.parent_input_atom_index}:{a.hydrogen_ordinal}' for a in prepared.atom_identities]
    source = next(c for c in candidates if c.candidate_id == record.selected_candidate_id)
    if decision.sampling.method == 'independent_rigid_fragments':
        if len(Chem.GetMolFrags(graph)) < 2:
            raise ValueError('rigid sampling requires multiple fragments')
        positions = dict(zip(source.atom_ids, source.positions))
        conf = Chem.Conformer(graph.GetNumAtoms())
        for i, atom_id in enumerate(ids):
            conf.SetAtomPosition(i, positions[atom_id])
        graph.RemoveAllConformers()
        graph.AddConformer(conf)
    task = ChemTask(task='rdkit_sampling', reactant_xyz='', mol_block=Chem.MolToMolBlock(graph),
                    sampling=decision.sampling, cpus=record.compute_cpus)
    manifest = directory/'sampling.json'
    _write_immutable_input(str(manifest), task.model_dump_json())
    step = next((s for s in record.job_steps if s.purpose == 'sampling' and s.input_path == str(manifest)), None)
    if step is None:
        error, job = _submit_step(record, 'sampling', str(manifest), 'chem_task')
        if error:
            return _block(record, 'build', 'sampling_admission_failed', error, needs=['exploration_budget','compute_capability'])
        record.job_steps.append(TsJobStep(purpose='sampling', job_id=job, input_path=str(manifest), state='ready'))
        record.waiting_for = f'job:{job}'
        return record
    step.state = _read_job_state(record, step.job_id)
    if step.state not in TERMINAL_STATES:
        record.waiting_for = f'job:{step.job_id}'
        return record
    try:
        data, success = read_task_result(str(manifest))
    except (OSError, ValueError) as exc:
        return _block(record, 'build', 'sampling_artifacts_missing', str(exc), needs=['compute_artifacts'])
    result = data['result']
    if result.get('symbols') != prepared.symbols:
        return _block(record, 'build', 'sampling_identity_mismatch', 'Returned symbols differ from declared graph.', needs=['compute_artifacts'])
    capture = CandidateCapture(catalog_id=record.catalog_id, project_id=record.owner_conversation_id,
        owner_id=record.owner_session_id, atom_ids=ids, multiplicity=record.declaration.multiplicity,
        output_dir=str(directory), sink=lambda c: put_candidate(db,c))
    for index, frame in enumerate(result.get('frames', [])):
        conf = Chem.Conformer(graph.GetNumAtoms())
        if len(frame['positions']) != len(ids):
            raise ValueError('sampling returned incomplete geometry')
        for i, p in enumerate(frame['positions']):
            conf.SetAtomPosition(i,p)
        graph.RemoveAllConformers()
        cid = graph.AddConformer(conf)
        capture.capture(graph, cid, generator=result['method'], seed=decision.sampling.seed,
            parent_id=source.candidate_id if result['method']=='independent_rigid_fragments' else None,
            parameters={'decision_id':decision.decision_id,'ordinal':index,
                        'fragment_transforms':json.dumps(frame.get('transforms'))}, job_ids=[step.job_id])
    record.sampling_pending = None
    members = [c for c in candidates if c.candidate_id in previous.descriptors]
    snapshot = partition_candidates([*members,*capture.records], previous.config, previous=previous) if capture.records else previous
    put_region_snapshot(db,snapshot,project_id=record.owner_conversation_id,owner_id=record.owner_session_id)
    record.partition_revision = snapshot.revision
    record.waiting_for = ''
    return _block(record, 'build', 'decision_needed',
        'Supplement returned archived raw choices; select a representative using current cards. '
        + ('The new baseline requires an explicit exploratory repartition decision.' if previous.partition_method!='fixed_tolerance_baseline' else '')
        + ('' if success else ' Sampling did not complete successfully.'), needs=['selection_decision'])
