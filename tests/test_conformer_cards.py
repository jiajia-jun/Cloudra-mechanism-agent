import pytest

from tests.test_conformer_catalog import make_candidate


def cards_fixture(tmp_path):
    from cloudra.tools.core.conformer_cards import build_region_cards
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates

    candidates = [make_candidate(tmp_path), make_candidate(tmp_path, generator='other', geometry_ref='',
                                                          positions=[[0,0,0],[2.2,0,0]])]
    specs = [DescriptorSpec(kind='distance', stable_atom_ids=['C1','O1'])]
    snapshot = partition_candidates(candidates, RegionConfig(descriptor_specs=specs))
    return build_region_cards(snapshot,candidates,[])


def test_label_links_to_measurement(tmp_path):
    cards = cards_fixture(tmp_path)
    for card in cards:
        assert card.labels
        assert all(label.evidence_ref in card.evidence_refs for label in card.labels)
        assert all(m.unit == 'angstrom' for m in card.measurements)


def test_cards_expose_missing_energy(tmp_path):
    assert all('energy unmeasured' in card.unknowns for card in cards_fixture(tmp_path))


def test_pagination_lists_omitted_regions(tmp_path):
    from cloudra.tools.core.conformer_cards import paginate_cards

    cards = cards_fixture(tmp_path)
    page = paginate_cards(cards,offset=0,limit=1)
    assert page.total_regions == 2
    assert len(page.cards) == 1
    assert page.omitted_region_ids == [cards[1].region_id]


@pytest.mark.parametrize('use_child', [False, True])
def test_repartition_retains_candidate_and_parent_attempts(tmp_path, use_child):
    from cloudra.tools.core.conformer_cards import AttemptEvidence, build_region_cards
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates
    parent = make_candidate(tmp_path)
    old = partition_candidates([parent], RegionConfig(descriptor_specs=[DescriptorSpec(kind='distance', stable_atom_ids=['C1','O1'])]))
    old_id = next(iter(old.regions))
    current = make_candidate(tmp_path, generator='opt', parent_id=parent.candidate_id) if use_child else parent
    new = partition_candidates([current], RegionConfig(descriptor_specs=[DescriptorSpec(kind='distance', stable_atom_ids=['C1','O1'], tolerance=1)]), previous=old)
    attempt = AttemptEvidence(candidate_id=parent.candidate_id, region_id=old_id, stage='path', input_hash='input', failure_class='path_failed', job_id=17, evidence_refs=['log'])
    card = build_region_cards(new, [current], [attempt])[0]
    assert card.attempts == [attempt]
    assert card.attempts[0].region_id == old_id
    assert new.region_mapping[old_id] == [card.region_id]


def test_lineage_survives_multiple_partition_revisions(tmp_path):
    from cloudra.tools.core.conformer_cards import AttemptEvidence, build_region_cards
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates
    config = RegionConfig(descriptor_specs=[DescriptorSpec(kind='distance', stable_atom_ids=['C1','O1'])])
    parent = make_candidate(tmp_path)
    first = partition_candidates([parent], config)
    child = make_candidate(tmp_path, generator='opt1', parent_id=parent.candidate_id)
    second = partition_candidates([child], config, previous=first)
    grandchild = make_candidate(tmp_path, generator='opt2', parent_id=child.candidate_id)
    third = partition_candidates([grandchild], config, previous=second)
    attempt = AttemptEvidence(candidate_id=parent.candidate_id, region_id=next(iter(first.regions)), stage='path', input_hash='input', failure_class='path_failed', evidence_refs=['log'])
    card = build_region_cards(third, [grandchild], [attempt])[0]
    assert card.attempts == [attempt]
    assert third.region_mapping[attempt.region_id] == [card.region_id]


def test_card_discloses_partition_method_and_descriptor_configuration(tmp_path):
    card = cards_fixture(tmp_path)[0]
    assert card.partition_method == 'fixed_tolerance_baseline'
    assert card.partition_config.descriptor_specs[0].source == 'engineering_initial'
    assert card.partition_config.descriptor_specs[0].tolerance == .5
