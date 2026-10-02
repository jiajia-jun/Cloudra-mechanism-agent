"""Candidate catalog selection and queued, selected-only native optimization."""
from __future__ import annotations

from pathlib import Path


def use_catalog_source(record, source, role):
    """Bind the explicitly selected immutable archived member, never auto-select."""
    from cloudra.services.conformer_store import get_region_snapshot, list_candidates
    from cloudra.services.ts_pipeline_context import pipeline_database
    from cloudra.tools.core.ts_process import _block, _write_immutable_input

    db = pipeline_database()
    snapshot = get_region_snapshot(db, source.catalog_id, source.partition_revision,
        project_id=record.owner_conversation_id, owner_id=record.owner_session_id)
    members = list_candidates(db, source.catalog_id, project_id=record.owner_conversation_id, owner_id=record.owner_session_id)
    selected = next((candidate for candidate in members if candidate.candidate_id == source.candidate_id), None)
    if selected is None or selected.candidate_id not in snapshot.descriptors:
        return _block(record, 'build', 'candidate_identity_mismatch', 'Selected candidate is absent from the referenced catalog partition.', needs=[f'conformers.{role}'])
    selected.verify_artifact()
    if selected.qualification.status != 'qualified' and source.optimization is None:
        return _block(record, 'build', 'missing_input', 'Unqualified catalog seed requires an explicit optimization calculation or qualified replacement.', needs=[f'conformers.{role}.optimization'])
    directory = Path(record.run_dir) / 'selected_candidates' / selected.candidate_id
    directory.mkdir(parents=True, exist_ok=True)
    path = str(directory / 'seed.xyz')
    _write_immutable_input(path, Path(selected.geometry_ref).read_text())
    if role == 'reactant':
        record.catalog_id, record.partition_revision = source.catalog_id, source.partition_revision
        record.selected_candidate_id = selected.candidate_id
        record.current_seed_xyz_path = path
    else:
        record.product_seed_candidate_id = selected.candidate_id
        record.product_seed_xyz_path = path
    return record






