"""Advisory log discovery must not change a failed scientific verdict."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.dag.evidence_inbox import EvidenceInboxMixin
from cloudra.dag.models import GraphRef
from cloudra.tools.core.irc_evidence import diagnose_short_irc_materials
from tests.test_irc_endpoint_optimization import write_lineage_bundle


def _unusable_log(tmp_path, monkeypatch, kind):
    path = tmp_path / 'unrelated_old_freq.log'
    fixture = Path(__file__).parent / 'fixtures/gaussian/water_opt_freq_g16.out'
    path.write_text(fixture.read_text().replace('Frequencies --', 'Frequencies -- NOT_A_NUMBER', 1)
                    if kind == 'malformed' else fixture.read_text())
    if kind == 'unreadable':
        original = Path.read_text

        def read_text(candidate, *args, **kwargs):
            if candidate == path:
                raise PermissionError('diagnostic candidate is unreadable')
            return original(candidate, *args, **kwargs)

        monkeypatch.setattr(Path, 'read_text', read_text)
    return path


@pytest.mark.parametrize('kind', ['malformed', 'unreadable'])
def test_bad_unbound_log_preserves_structured_short_irc_failure(tmp_path, monkeypatch, kind):
    paths = write_lineage_bundle(tmp_path)
    _unusable_log(tmp_path, monkeypatch, kind)
    inbox = EvidenceInboxMixin()
    inbox.working_directory = tmp_path
    inbox.store = SimpleNamespace(resolve_evidence_with_source=lambda ref: ('log_parser', {
        'arguments': {'log_path': str(paths['irc'])},
    }))
    monkeypatch.setattr('cloudra.services.ts_pipeline_store.atom_binding_for_log', lambda *_: None)

    passed, reason = inbox._passes_short_irc_check(
        GraphRef(ref_type='tool_result', ref_id='irc-ref'),
        SimpleNamespace(source_node_id='R', target_node_id='P'), [], SimpleNamespace(nodes=[]))

    assert not passed
    assert 'missing TS material' in reason
    assert 'missing endpoint_a' in reason
    assert 'missing endpoint_b' in reason


@pytest.mark.parametrize('kind', ['malformed', 'unreadable'])
@pytest.mark.parametrize('bound', [False, True])
def test_bad_diagnostic_candidate_does_not_hide_usable_saddle(tmp_path, monkeypatch, kind, bound):
    paths = write_lineage_bundle(tmp_path)
    bad = _unusable_log(tmp_path, monkeypatch, kind)
    saddle = tmp_path / 'matching_ts_freq.log'
    saddle.write_text(paths['ts'].read_text())

    hints = diagnose_short_irc_materials(paths['irc'], [bad] if bound else [], workspace=tmp_path)

    assert any(str(saddle) in hint and 'exactly one imaginary frequency' in hint for hint in hints)
    assert not any(str(bad) in hint for hint in hints)
