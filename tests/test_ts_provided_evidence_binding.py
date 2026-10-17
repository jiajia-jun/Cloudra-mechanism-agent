"""Provided guess provenance binds bytes once and survives source-file edits."""
import hashlib
from pathlib import Path

import pytest

from cloudra.tools.core import ts_process
from cloudra.tools.core.ts_inputs import TsInput, TsResumeRequest
from cloudra.tools.core.ts_process import TsBlocked, TsJobStep, TsProcessRecord, _guess, advance
from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
from tests.test_ts_inputs import input_payload
from tests.test_ts_stage_inputs import owned_fixture_structure, record_fixture

pytestmark = pytest.mark.usefixtures('rdkit_chemistry')


def provided_record(tmp_path, evidence=b'accepted provenance\r\noriginal bytes\r\n'):
    candidate = tmp_path / 'candidate.xyz'
    candidate.write_bytes(b'2\r\nprovided\r\nH 0 0 0\r\nH 0 0 0.74\r\n')
    provenance = tmp_path / 'source.bin'
    provenance.write_bytes(evidence)
    value = input_payload()
    value['guess'] = dict(kind='provided', xyz_path=str(candidate), evidence_refs=[str(provenance)])
    record = record_fixture(tmp_path, input=TsInput.model_validate(value))
    owned_fixture_structure(record, candidate, '[H][H]')
    return record, candidate, provenance


@pytest.mark.parametrize('evidence', [b'accepted\r\nprovenance\r\n', b'\x00\xffbinary provenance\r\n'])
def test_provided_evidence_snapshot_preserves_source_bytes_and_records_hash(tmp_path, evidence):
    record, candidate, provenance = provided_record(tmp_path, evidence)
    candidate_bytes = candidate.read_bytes()
    result = _guess(record)
    assert result.blocked is None
    snapshots = result.stage_record('guess').artifacts
    assert Path(snapshots[0]).read_bytes() == candidate_bytes
    assert Path(snapshots[1]).read_bytes() == evidence
    bound = result.provided_guess_binding
    assert bound.xyz.source_path == str(candidate)
    assert bound.xyz.snapshot_path == snapshots[0]
    assert bound.xyz.sha256 == hashlib.sha256(candidate_bytes).hexdigest()
    assert bound.evidence[0].source_path == str(provenance)
    assert bound.evidence[0].snapshot_path == snapshots[1]
    assert bound.evidence[0].sha256 == hashlib.sha256(evidence).hexdigest()
    reloaded = TsProcessRecord.model_validate_json(result.model_dump_json())
    assert reloaded.provided_guess_binding == bound


def test_retry_keeps_bound_provenance_after_original_files_are_changed_or_removed(tmp_path):
    record, candidate, provenance = provided_record(tmp_path)
    record = _guess(record)
    original_snapshot = Path(record.stage_record('guess').artifacts[1]).read_bytes()
    provenance.write_bytes(b'corrected later provenance')
    candidate.unlink()
    record.stage = 'guess'
    record.blocked = TsBlocked(stage='guess', failure_class='test_retry', message='Retry the current guess')
    record.job_steps = [TsJobStep(purpose='path', state='failed', job_id=17)]
    request = TsResumeRequest(changes={}, reason='Retry the same accepted source', request_key='retry', expected_revision=0)
    revised = revise_record(record, request, plan_input_revision(record, request))
    revised = _guess(revised)
    assert revised.blocked is None
    assert revised.provided_guess_binding == record.provided_guess_binding
    assert revised.attempt_history[-1].provided_guess_binding == record.provided_guess_binding
    assert Path(revised.stage_record('guess').artifacts[1]).read_bytes() == original_snapshot
    assert revised.declaration_revision == 2


def test_explicit_same_path_guess_revision_binds_new_provenance_and_keeps_history(tmp_path):
    record, _, provenance = provided_record(tmp_path)
    record = _guess(record)
    original = record.provided_guess_binding
    provenance.write_bytes(b'explicitly revised provenance\r\n')
    request = TsResumeRequest(changes={'guess': record.input.guess.model_dump(mode='json')},
        reason='Import the corrected evidence at the same source path', request_key='rebind', expected_revision=0)
    receipt = plan_input_revision(record, request)
    revised = _guess(revise_record(record, request, receipt))
    assert revised.blocked is None
    assert revised.provided_guess_binding.evidence[0].sha256 == hashlib.sha256(provenance.read_bytes()).hexdigest()
    assert revised.provided_guess_binding.evidence[0].snapshot_path != original.evidence[0].snapshot_path
    assert revised.attempt_history[-1].provided_guess_binding == original
    assert Path(original.evidence[0].snapshot_path).read_bytes() == b'accepted provenance\r\noriginal bytes\r\n'


def test_durable_resume_accepts_same_path_reimport_once(tmp_path, monkeypatch, ts_producer_authority):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import create_process, get_process

    record, _, provenance = provided_record(tmp_path)
    db = ComputeDB(data_dir=tmp_path / 'ledger').init()
    process = create_process(db, request_key='prepare', payload={
        'project_id': 'project', 'owner_id': 'owner', 'workspace_dir': str(tmp_path),
        'input': record.input.model_dump(mode='json')})
    record.pipeline_id = process['process_id']
    record = _guess(record)
    old_binding = record.provided_guess_binding
    provenance.write_bytes(b'explicit durable revision\r\n')
    monkeypatch.setitem(ts_process._STAGE_FUNCS, 'validate',
        lambda current: ts_process._block(current, 'validate', 'fixture_stop', 'No real calculation in this fixture'))
    with use_pipeline_database(db):
        ts_process.save_record(record)
        request = TsResumeRequest(changes={'guess': record.input.guess.model_dump(mode='json')},
            reason='Import the corrected provenance', request_key='rebind', expected_revision=record.revision)
        revised = ts_process.resume(record, request)
        accepted = get_process(db, record.pipeline_id)
        assert revised.declaration_revision == 2
        assert revised.provided_guess_binding.evidence[0].sha256 == hashlib.sha256(provenance.read_bytes()).hexdigest()
        assert revised.attempt_history[-1].provided_guess_binding == old_binding
        provenance.write_bytes(b'further source edit after this revision was accepted')
        replayed = ts_process.resume(revised, request)
        assert replayed.provided_guess_binding == revised.provided_guess_binding
        assert get_process(db, record.pipeline_id) == accepted


@pytest.mark.parametrize('artifact', ['xyz', 'evidence'])
def test_changed_bound_snapshot_blocks_continuation_before_next_stage(tmp_path, monkeypatch, artifact):
    record, _, _ = provided_record(tmp_path)
    record = _guess(record)
    binding = record.provided_guess_binding
    snapshot = binding.xyz if artifact == 'xyz' else binding.evidence[0]
    Path(snapshot.snapshot_path).write_bytes(b'changed accepted snapshot')
    record.stage = 'submit'

    def must_not_submit(_record):
        raise AssertionError('Changed snapshot must be rejected before submitting another job')

    monkeypatch.setitem(ts_process._STAGE_FUNCS, 'submit', must_not_submit)
    result = advance(record)
    assert result.blocked.failure_class == 'provided_guess_artifact_changed'
    assert snapshot.snapshot_path in result.blocked.message
    assert result.provided_guess_binding == binding
