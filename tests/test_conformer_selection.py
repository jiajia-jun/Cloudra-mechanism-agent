from tests.test_conformer_cards import cards_fixture


def context_for(cards, **overrides):
    from cloudra.tools.core.conformer_selection import SelectionContext

    fields = dict(project_id='project',owner_id='owner',catalog_id='cat',partition_revision=cards[0].revision,
                  declaration_hash='declaration',method_fingerprint='formal-method',cards=cards)
    fields.update(overrides)
    return SelectionContext(**fields)


def test_selects_unattempted_region_before_repeat(tmp_path):
    from cloudra.tools.core.conformer_selection import AttemptEvidence, select_default

    cards = cards_fixture(tmp_path)
    attempt = AttemptEvidence(candidate_id=cards[0].candidate_ids[0],region_id=cards[0].region_id,
                              stage='guess',input_hash='input',failure_class='path_failed',evidence_refs=['log'])
    result = select_default(cards, context_for(cards,attempts=[attempt]))
    assert result.region_id == cards[1].region_id
    assert result.action == 'refine_representative'


def test_ambiguity_returns_decision_needed(tmp_path):
    from cloudra.tools.core.conformer_selection import select_default

    cards = cards_fixture(tmp_path)
    result = select_default(cards,context_for(cards,chemical_ambiguities=['two attack faces']))
    assert result.status == 'blocked'
    assert result.blocked_reason == 'chemical_decision_needed'


def test_infrastructure_failure_reuses_job(tmp_path):
    from cloudra.tools.core.conformer_selection import AttemptEvidence, select_default

    cards = cards_fixture(tmp_path)
    attempt = AttemptEvidence(candidate_id=cards[0].candidate_ids[0],region_id=cards[0].region_id,
                              stage='guess',input_hash='input',failure_class='infrastructure',job_id=17,evidence_refs=['log'])
    decision = select_default(cards,context_for(cards,attempts=[attempt]))
    assert decision.reuse_job_id == 17


def test_same_input_failed_attempt_not_requeued(tmp_path):
    from cloudra.tools.core.conformer_selection import AttemptEvidence, select_default

    cards = cards_fixture(tmp_path)
    attempts = [AttemptEvidence(candidate_id=candidate_id,region_id=c.region_id,stage='guess',input_hash='input',
                               failure_class='path_failed',evidence_refs=['log']) for c in cards for candidate_id in c.candidate_ids]
    assert select_default(cards,context_for(cards,attempts=attempts)).status == 'blocked'


def test_energy_orders_only_comparable_candidates(tmp_path):
    from cloudra.tools.core.conformer_cards import build_region_cards
    from cloudra.tools.core.conformer_catalog import EnergyObservation, Qualification
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates
    from cloudra.tools.core.conformer_selection import select_default
    from tests.test_conformer_catalog import make_candidate

    a = make_candidate(tmp_path,qualification=Qualification(status='qualified'))
    b = make_candidate(tmp_path,generator='second',geometry_ref='',positions=[[0,0,0],[2.2,0,0]],
                       qualification=Qualification(status='qualified'))
    a = a.model_copy(update={'energies':[EnergyObservation(value=100,unit='kcal/mol',method_fingerprint='m',species_key=a.species_key,convergence="converged")]})
    b = b.model_copy(update={'energies':[EnergyObservation(value=0,unit='kcal/mol',method_fingerprint='m',species_key=b.species_key,convergence="converged")]})
    snapshot = partition_candidates([a,b],RegionConfig(descriptor_specs=[DescriptorSpec(kind='distance',stable_atom_ids=['C1','O1'])]))
    cards = build_region_cards(snapshot,[a,b],[])
    assert select_default(cards,context_for(cards)).candidate_id == b.candidate_id
