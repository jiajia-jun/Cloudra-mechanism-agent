import pytest
from pydantic import ValidationError

from tests.test_conformer_cards import cards_fixture
from tests.test_conformer_selection import context_for


def decision_for(cards, **overrides):
    from cloudra.tools.core.conformer_selection import SelectionDecision

    card = cards[0]
    fields = dict(decision_id='agent-decision',catalog_id='cat',partition_revision=card.revision,
                  declaration_hash='declaration',action='refine_representative',candidate_id=card.candidate_ids[0],
                  region_id=card.region_id,reason='Try the recorded distinct geometry',evidence_refs=card.evidence_refs)
    fields.update(overrides)
    return SelectionDecision(**fields)


def test_rejects_stale_or_foreign_candidate(tmp_path):
    from cloudra.tools.core.conformer_selection import validate_selection

    cards = cards_fixture(tmp_path)
    with pytest.raises(ValueError,match='stale'):
        validate_selection(decision_for(cards,partition_revision='old'),context_for(cards))
    with pytest.raises(ValueError,match='foreign'):
        validate_selection(decision_for(cards,candidate_id='foreign'),context_for(cards))


def test_ai_cannot_raise_hard_budget_or_change_method():
    from cloudra.tools.core.conformer_selection import SelectionDecision

    decision = SelectionDecision(decision_id='decision', catalog_id='cat', partition_revision='revision',
                                 declaration_hash='declaration', reason='Validate decision fields')
    for override in [{'method_fingerprint':'different'},{'max_compute_actions':100}]:
        with pytest.raises(ValidationError) as error:
            SelectionDecision(**decision.model_dump(), **override)
        assert error.value.errors()[0]['type'] == 'extra_forbidden'


def test_reason_requires_current_evidence(tmp_path):
    from cloudra.tools.core.conformer_selection import validate_selection

    cards = cards_fixture(tmp_path)
    with pytest.raises(ValueError,match='evidence'):
        validate_selection(decision_for(cards,evidence_refs=['invented']),context_for(cards))
    with pytest.raises(ValueError):
        decision_for(cards,reason='   ')


def test_stop_returns_incomplete_not_scientific_success(tmp_path):
    from cloudra.tools.core.conformer_selection import validate_selection

    cards = cards_fixture(tmp_path)
    decision = validate_selection(decision_for(cards,action='stop',candidate_id=None,region_id=None),
                                  context_for(cards,budget_available=False))
    assert decision.status == 'stopped'
    assert decision.blocked_reason == 'incomplete'


def test_supplement_needs_supported_sampling_request(tmp_path):
    from cloudra.tools.core.conformer_selection import validate_selection

    cards = cards_fixture(tmp_path)
    with pytest.raises(ValueError,match='sampling'):
        validate_selection(decision_for(cards,action='supplement_sampling'),context_for(cards))


def test_failed_decision_preserves_catalog_and_context(tmp_path):
    from cloudra.tools.core.conformer_selection import validate_selection

    cards = cards_fixture(tmp_path)
    context = context_for(cards)
    before = context.model_dump_json()
    with pytest.raises(ValueError):
        validate_selection(decision_for(cards,candidate_id='missing'),context)
    assert context.model_dump_json() == before


def test_existing_job_can_reconcile_without_new_budget(tmp_path):
    from cloudra.tools.core.conformer_selection import AttemptEvidence, select_default

    cards = cards_fixture(tmp_path)
    a = AttemptEvidence(candidate_id=cards[0].candidate_ids[0],region_id=cards[0].region_id,
                        stage='path',input_hash='input',failure_class='infrastructure',job_id=17,evidence_refs=['log'])
    result = select_default(cards,context_for(cards,attempts=[a],budget_available=False))
    assert result.reuse_job_id == 17


def test_sampling_cannot_bypass_budget_with_job_reuse(tmp_path):
    from cloudra.tools.core.conformer_selection import SamplingRequest, validate_selection
    cards = cards_fixture(tmp_path)
    decision = decision_for(cards, action='supplement_sampling', reuse_job_id=999,
                            sampling=SamplingRequest(method='ETKDGv3', count=100, seed=42))
    with pytest.raises(ValueError, match='reuse'):
        validate_selection(decision, context_for(cards, budget_available=False))
