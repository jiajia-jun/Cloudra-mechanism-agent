"""Candidate catalog selection and queued, selected-only native optimization."""
from __future__ import annotations

from pathlib import Path

from cloudra.tools.core.conformer_catalog import CatalogModel


class CandidateCatalogReference(CatalogModel):
    catalog_id: str
    partition_revision: str


def prepare_candidate_seed(record, prepared):
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
    from cloudra.tools.core.conformer_cards import build_region_cards
    from cloudra.tools.core.conformer_catalog import EnergyObservation, Qualification, content_digest
    from cloudra.tools.core.conformer_regions import partition_candidates
    from cloudra.tools.core.conformer_selection import SelectionContext, select_default
    from cloudra.tools.core.preorganization import load_resolved_graph, qualify_geometry, resolve_guidance
    from cloudra.tools.core.ts_process import (
        TsJobStep,
        _block,
        _job_directory,
        _read_job_state,
        _submit_step,
        _write_immutable_input,
    )

    db=pipeline_database()
    candidates=list_candidates(db,record.catalog_id,project_id=record.owner_conversation_id,owner_id=record.owner_session_id)
    snapshot=get_region_snapshot(db,record.catalog_id,record.partition_revision,project_id=record.owner_conversation_id,owner_id=record.owner_session_id)
    members=[c for c in candidates if c.candidate_id in snapshot.descriptors]
    graph=load_resolved_graph(prepared,allow_unoptimized=True)
    ids=[f'a{a.input_atom_index}' if a.origin=='input_atom' else f'h{a.parent_input_atom_index}:{a.hydrogen_ordinal}' for a in prepared.atom_identities]
    species=content_digest([Chem.MolToSmiles(graph,isomericSmiles=True),Chem.GetFormalCharge(graph),record.declaration.multiplicity])
    plan=resolve_guidance(prepared,record.declaration.ring_order,[w.model_dump() for w in record.declaration.distance_filters],index_base=0)
    cards=build_region_cards(snapshot,members,record.candidate_attempts)
    import json

    from cloudra.persistence.fs_utils import atomic_write_text
    record.cards_path=str(Path(record.run_dir)/"candidate_cards.json")
    atomic_write_text(record.cards_path,json.dumps([c.model_dump() for c in cards],ensure_ascii=False))
    context=SelectionContext(project_id=record.owner_conversation_id,owner_id=record.owner_session_id,
        catalog_id=record.catalog_id,partition_revision=record.partition_revision,declaration_hash=content_digest(record.declaration.model_dump(mode='json')),
        method_fingerprint=record.declaration.method,cards=cards,attempts=record.candidate_attempts)
    if record.selected_candidate_id is None:
        decision=select_default(cards,context)
        if decision.status!='ready':
            return _block(record,'build','decision_needed',decision.reason,needs=['selection_decision'])
        record.selected_candidate_id=decision.candidate_id
        record.selection_decision_id=decision.decision_id
        record.selection_decisions.append(decision)
    candidate=next((c for c in candidates if c.candidate_id==record.selected_candidate_id),None)
    if candidate is None or candidate.species_key!=species or dict(zip(candidate.atom_ids,candidate.symbols))!=dict(zip(ids,prepared.symbols)):
        return _block(record,'build','candidate_identity_mismatch','Catalog candidate does not match the declared endpoint identities, charge or spin.',needs=['candidate_catalog'])
    candidate.verify_artifact()
    positions=dict(zip(candidate.atom_ids,candidate.positions))
    ordered=[positions[a] for a in ids]
    if candidate.qualification.status!='qualified':
        constrained = bool(plan.windows)
        if constrained:
            from cloudra.tools.core.constrained_optimization import OptimizationRequest
            from cloudra.tools.core.geometry_optimization import advance_optimization
            request = OptimizationRequest(symbols=prepared.symbols, positions=ordered,
                distance_constraints=[dict(atoms=list(w.atoms),min_ang=w.min_ang,max_ang=w.max_ang) for w in plan.windows])
            result = advance_optimization(record,candidate.candidate_id,request)
            if result is None:
                return record
            step = record.job_steps[-1]
        else:
            step=next((s for s in record.job_steps if s.purpose=='candidate_opt'),None)
            if step is None:
                directory=Path(_job_directory(record,'candidate_opt'))
                directory.mkdir(parents=True,exist_ok=True)
                manifest=directory/'candidate-opt.json'
                xyz='\n'.join([str(len(ids)),'selected candidate '+candidate.candidate_id,*[f'{s} '+' '.join(f'{v:.12f}' for v in p) for s,p in zip(prepared.symbols,ordered)]])+'\n'
                task=ChemTask(task='xtb_opt',reactant_xyz=xyz,charge=record.declaration.charge,multiplicity=record.declaration.multiplicity,
                              cpus=record.compute_cpus,solvation=record.declaration.path_solvation.model_dump() if record.declaration.path_solvation else None)
                _write_immutable_input(str(manifest),task.model_dump_json())
                error,job=_submit_step(record,'candidate_opt',str(manifest),'chem_task')
                if error:
                    return _block(record,'build','candidate_optimization_admission_failed',error,needs=['compute_capability','exploration_budget'])
                record.job_steps.append(TsJobStep(purpose='candidate_opt',job_id=job,input_path=str(manifest),state='ready'))
                record.waiting_for=f'job:{job}'
                return record
            step.state=_read_job_state(record,step.job_id)
            if step.state not in TERMINAL_STATES:
                record.waiting_for=f'job:{step.job_id}'
                return record
            try:
                data,_=read_task_result(step.input_path)
            except (OSError,ValueError) as exc:
                return _block(record,'build','candidate_optimization_result_missing',str(exc),needs=['compute_artifacts'])
            result=data['result']
        symbols=result.get('symbols',[])
        optimized=result.get('positions',[])
        converged=(result.get('returncode')==0 and result.get('normal_termination') is True and result.get('optimization_converged') is True)
        eligible,reasons,_=qualify_geometry(plan,graph,symbols,optimized) if optimized else (False,['optimized geometry missing'],{})
        if not converged:
            reasons.append('candidate optimization not proven converged')
        conf=Chem.Conformer(graph.GetNumAtoms())
        for i,p in enumerate(optimized if symbols==prepared.symbols and len(optimized)==len(ordered) else ordered):
            conf.SetAtomPosition(i,p)
        graph.RemoveAllConformers()
        cid=graph.AddConformer(conf,assignId=True)
        energies=[]
        if converged and eligible and result.get('energy_hartree') is not None:
            energies=[EnergyObservation(value=result['energy_hartree'],unit='Ha',method_fingerprint='GFN2-xTB/constrained_rfo' if constrained else 'GFN2-xTB/native_opt',species_key=species,
                charge=record.declaration.charge,multiplicity=record.declaration.multiplicity,solvent=str(record.declaration.path_solvation or ''),convergence='converged',artifact_ref=result['log_file'])]
        capture=CandidateCapture(catalog_id=record.catalog_id,project_id=record.owner_conversation_id,owner_id=record.owner_session_id,
            output_dir=str(Path(record.run_dir)/'candidate_results'),atom_ids=ids,multiplicity=record.declaration.multiplicity,sink=lambda c:put_candidate(db,c))
        child=capture.capture(graph,cid,generator='constrained_xtb_rfo' if constrained else 'native_xtb_opt',parent_id=candidate.candidate_id,state='optimized' if converged and eligible else 'failed',
            qualification=Qualification(status='qualified' if converged and eligible else 'rejected',reasons=reasons,evidence_refs=result.get('artifact_refs',[step.input_path,result.get('log_file',step.input_path)])),
            energies=energies,job_ids=result.get('job_ids',[step.job_id]),parameters={'job_id':step.job_id,'native_opt':not constrained, 'optimizer': result.get('coordinate_backend','native_xtb_opt'), 'numerical_source':result.get('numerical_source','xTB')})
        if not converged or not eligible:
            from cloudra.tools.core.conformer_cards import AttemptEvidence
            record.candidate_attempts.append(AttemptEvidence(candidate_id=candidate.candidate_id,region_id='',stage='candidate_opt',input_hash=content_digest(Path(step.input_path).read_text()),failure_class='nonconvergence' if not converged else 'geometry',job_id=step.job_id,evidence_refs=[step.input_path,result.get('log_file',step.input_path)]))
            return _block(record,'build','candidate_optimization_failed','; '.join(reasons),needs=['selection_decision'])
        # A new optimization child can move between regions. Statistical policies
        # require a new explicit partition decision rather than silently changing.
        if snapshot.partition_method!='fixed_tolerance_baseline':
            record.selected_candidate_id=child.candidate_id
            return _block(record,'build','partition_revision_needed','Optimized child retained; update the exploratory partition before selecting it.',needs=['partition_revision'])
        snapshot=partition_candidates([*members,child],snapshot.config,previous=snapshot)
        put_region_snapshot(db,snapshot,project_id=record.owner_conversation_id,owner_id=record.owner_session_id)
        record.partition_revision=snapshot.revision
        record.selected_candidate_id=child.candidate_id
        candidate=child
        ordered=optimized
    qualified,reasons,_=qualify_geometry(plan,graph,prepared.symbols,ordered)
    if not qualified:
        return _block(record,'build','candidate_geometry_rejected','; '.join(reasons),needs=['selection_decision'])
    conf=Chem.Conformer(graph.GetNumAtoms())
    for i,p in enumerate(ordered):
        conf.SetAtomPosition(i,p)
    graph.RemoveAllConformers()
    graph.AddConformer(conf,assignId=True)
    directory=Path(record.run_dir)/'selected_candidates'/candidate.candidate_id
    directory.mkdir(parents=True,exist_ok=True)
    xyz='\n'.join([str(len(ids)),'selected '+candidate.candidate_id,*[f'{s} '+' '.join(f'{v:.12f}' for v in p) for s,p in zip(prepared.symbols,ordered)]])+'\n'
    _write_immutable_input(str(directory/'seed.xyz'),xyz)
    _write_immutable_input(str(directory/'seed.mol'),Chem.MolToMolBlock(graph))
    record.current_seed_xyz_path=str(directory/'seed.xyz')
    record.current_seed_mol_path=str(directory/'seed.mol')
    record.current_reactant_prepared_path=prepared.artifact_path
    record.effective_reaction_center=list(dict.fromkeys([*record.declaration.reaction_center,*plan.forming_pairs]))
    return record


def prepare_product_seed(record,prepared):
    """One archived raw product seed and one queued native product optimization."""
    from rdkit import Chem

    from cloudra.runtime.chem_task import ChemTask, read_task_result
    from cloudra.services.compute_store import TERMINAL_STATES
    from cloudra.services.conformer_store import list_candidates, put_candidate
    from cloudra.services.ts_pipeline_context import pipeline_database
    from cloudra.tools.core.conformer_capture import CandidateCapture
    from cloudra.tools.core.conformer_catalog import EnergyObservation, Qualification
    from cloudra.tools.core.preorganization import GuidancePlan, load_resolved_graph, qualify_geometry
    from cloudra.tools.core.ts_process import (
        TsJobStep,
        _block,
        _job_directory,
        _read_job_state,
        _submit_step,
        _write_immutable_input,
    )
    if record.product_seed_xyz_path and Path(record.product_seed_xyz_path).is_file():
        return record
    if any(c.embed_status=='failed' or not c.mol_path for c in prepared.components):
        return _block(record,'build','product_embedding_failed',prepared.message,needs=['product_smiles'])
    graph=load_resolved_graph(prepared,allow_unoptimized=True)
    if graph.GetNumConformers()!=1:
        return _block(record,'build','product_embedding_missing','Raw product seed has no complete coordinates.',needs=['product_smiles'])
    ids=[f'a{a.input_atom_index}' if a.origin=='input_atom' else f'h{a.parent_input_atom_index}:{a.hydrogen_ordinal}' for a in prepared.atom_identities]
    capture=CandidateCapture(catalog_id=record.catalog_id,project_id=record.owner_conversation_id,owner_id=record.owner_session_id,
        output_dir=str(Path(record.run_dir)/'product_candidates'),sink=lambda c:put_candidate(pipeline_database(),c),atom_ids=ids,multiplicity=record.declaration.multiplicity)
    if record.product_seed_candidate_id is None:
        if len(prepared.components)>1:
            from cloudra.tools.core.complex_assembly import AssemblyParameters, sample_independent_placements
            placement=sample_independent_placements(graph,[list(g) for g in Chem.GetMolFrags(graph)],seed=42,count=1,parameters=AssemblyParameters())[0]
            for i,p in enumerate(placement.positions):
                graph.GetConformer().SetAtomPosition(i,p)
        raw=capture.capture(graph,0,generator='product_raw_endpoint',seed=42,parameters={'endpoint_role':'product','selection_source':'one_declared_endpoint_seed'})
        record.product_seed_candidate_id=raw.candidate_id
    candidates=list_candidates(pipeline_database(),record.catalog_id,project_id=record.owner_conversation_id,owner_id=record.owner_session_id)
    raw=next(c for c in candidates if c.candidate_id==record.product_seed_candidate_id)
    step=next((s for s in record.job_steps if s.purpose=='product_seed_opt'),None)
    if step is None:
        directory=Path(_job_directory(record,'product_seed_opt'))
        directory.mkdir(parents=True,exist_ok=True)
        manifest=directory/'product-opt.json'
        task=ChemTask(task='xtb_opt',reactant_xyz=Path(raw.geometry_ref).read_text(),cpus=record.compute_cpus,
            charge=record.declaration.charge,multiplicity=record.declaration.multiplicity,
            solvation=record.declaration.path_solvation.model_dump() if record.declaration.path_solvation else None)
        _write_immutable_input(str(manifest),task.model_dump_json())
        error,job=_submit_step(record,'product_seed_opt',str(manifest),'chem_task')
        if error:
            return _block(record,'build','product_optimization_admission_failed',error,needs=['compute_capability','exploration_budget'])
        record.job_steps.append(TsJobStep(purpose='product_seed_opt',job_id=job,input_path=str(manifest),state='ready'))
        record.waiting_for=f'job:{job}'
        return record
    step.state=_read_job_state(record,step.job_id)
    if step.state not in TERMINAL_STATES:
        record.waiting_for=f'job:{step.job_id}'
        return record
    try:
        data,_=read_task_result(step.input_path)
    except (OSError,ValueError) as exc:
        return _block(record,'build','product_optimization_result_missing',str(exc),needs=['compute_artifacts'])
    result=data['result']
    symbols=result.get('symbols',[])
    positions=result.get('positions',[])
    converged=result.get('returncode')==0 and result.get('normal_termination') is True and result.get('optimization_converged') is True
    plan=GuidancePlan(ring_order=(),windows=(),forming_pairs=(),bonded_pairs=(),index_base=0)
    eligible,reasons,_=qualify_geometry(plan,graph,symbols,positions) if positions else (False,['optimized product geometry missing'],{})
    if not converged:
        reasons.append('native product optimization not proven converged')
    for i,p in enumerate(positions if symbols==prepared.symbols and len(positions)==len(raw.positions) else raw.positions):
        graph.GetConformer().SetAtomPosition(i,p)
    energies=[]
    if converged and eligible and result.get('energy_hartree') is not None:
        energies=[EnergyObservation(value=result['energy_hartree'],unit='Ha',method_fingerprint='GFN2-xTB/native_opt',species_key=raw.species_key,
            charge=record.declaration.charge,multiplicity=record.declaration.multiplicity,solvent=str(record.declaration.path_solvation or ''),convergence='converged',artifact_ref=result['log_file'])]
    child=capture.capture(graph,0,generator='native_product_xtb_opt',parent_id=raw.candidate_id,state='optimized' if converged and eligible else 'failed',
        job_ids=[step.job_id],energies=energies,parameters={'endpoint_role':'product'},
        qualification=Qualification(status='qualified' if converged and eligible else 'rejected',reasons=reasons,evidence_refs=[step.input_path,result.get('log_file',step.input_path)]))
    if not converged or not eligible:
        return _block(record,'build','product_optimization_failed','; '.join(reasons),needs=['endpoint_seed_retry'])
    target=Path(record.run_dir)/'product_seed'/child.candidate_id
    target.mkdir(parents=True,exist_ok=True)
    _write_immutable_input(str(target/'product.xyz'),Path(child.geometry_ref).read_text())
    _write_immutable_input(str(target/'product.mol'),Chem.MolToMolBlock(graph))
    record.product_seed_xyz_path=str(target/'product.xyz')
    record.product_seed_mol_path=str(target/'product.mol')
    return record


def replace_product_seed(record, adjustment):
    """Replace a failed native product seed; retain the completed reactant branch."""

    from cloudra.services.conformer_store import list_candidates, put_candidate
    from cloudra.services.ts_pipeline_context import pipeline_database
    from cloudra.tools.core.conformer_capture import CandidateCapture
    from cloudra.tools.core.preorganization import GuidancePlan, qualify_geometry
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_process import BUILD_STAGE_DIR, TsAttemptHistory
    if (not record.pipeline_id or adjustment.role!='product' or not record.blocked
            or record.blocked.failure_class!='product_optimization_failed'):
        raise ValueError('seed retry requires a failed native product optimization')
    if not adjustment.reason.strip():
        raise ValueError('seed retry reason required')
    path=Path(adjustment.seed_xyz_path).resolve()
    path.relative_to(Path(record.workspace_dir).resolve())
    atoms=read_xyz_atoms(str(path))
    symbols=[s for s,_ in atoms]
    positions=[p for _,p in atoms]
    db=pipeline_database()
    candidates=list_candidates(db,record.catalog_id,project_id=record.owner_conversation_id,owner_id=record.owner_session_id)
    old=next(c for c in candidates if c.candidate_id==record.product_seed_candidate_id)
    if symbols!=old.symbols or positions==old.positions:
        raise ValueError('product seed needs changed geometry with unchanged atom identities')
    from cloudra.tools.core.preorganization import load_resolved_graph
    from cloudra.tools.core.structure_builder import PreparedStructure
    directory=Path(record.active_attempt_dir) if record.active_attempt_dir else Path(record.run_dir)/BUILD_STAGE_DIR
    prepared=PreparedStructure.model_validate_json((directory/'product'/'prepared_structure.json').read_text())
    graph=load_resolved_graph(prepared,allow_unoptimized=True)
    if graph is None:
        raise ValueError('declared product graph missing')
    plan=GuidancePlan(ring_order=(),windows=(),forming_pairs=(),bonded_pairs=(),index_base=0)
    eligible,reasons,_=qualify_geometry(plan,graph,symbols,positions)
    if not eligible:
        raise ValueError('product seed rejected: '+'; '.join(reasons))
    for i,p in enumerate(positions):
        graph.GetConformer().SetAtomPosition(i,p)
    capture=CandidateCapture(catalog_id=record.catalog_id,project_id=record.owner_conversation_id,owner_id=record.owner_session_id,
        output_dir=str(Path(record.run_dir)/'product_candidates'),atom_ids=old.atom_ids,
        multiplicity=record.declaration.multiplicity,sink=lambda c:put_candidate(db,c))
    child=capture.capture(graph,0,generator='product_seed_retry',parent_id=old.candidate_id,
        parameters={'retry_id':adjustment.retry_id,'reason':adjustment.reason,'source_artifact':str(path)})
    record.attempt_history.append(TsAttemptHistory(declaration_revision=record.declaration_revision,
        selected_candidate_id=record.selected_candidate_id,job_steps=[s.model_copy(deep=True) for s in record.job_steps],
        stage_records=[s.model_copy(deep=True) for s in record.stage_records],reason=adjustment.reason))
    record.declaration_revision+=1
    record.product_seed_candidate_id=child.candidate_id
    record.product_seed_xyz_path=''
    record.product_seed_mol_path=''
    record.job_steps=[s for s in record.job_steps if s.purpose!='product_seed_opt']
    record.budget_action_keys.pop('product_seed_opt',None)
    record.budget_reservations.pop('product_seed_opt',None)
    record.seed_retry_decisions[adjustment.retry_id]=adjustment
    record.stage='build'
    record.blocked=None
    return record
