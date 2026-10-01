import numpy as np

from cloudra.tools.core.conformer_regions import DescriptorRecord, DescriptorSpec


def observations(values, spec):
    return [DescriptorRecord(candidate_id=str(i), values={spec.key: float(x)}) for i, x in enumerate(values)]


def test_bimodal_coordinate_gives_explicit_split_and_resampling_evidence():
    from cloudra.tools.core.conformer_statistical_regions import propose_statistical_splits

    spec = DescriptorSpec(kind="distance", stable_atom_ids=["a", "b"], source="declared_reaction_coordinate")
    rng = np.random.default_rng(23)
    rows = observations(np.r_[rng.normal(1, 0.04, 20), rng.normal(3, 0.04, 20)], spec)
    result = propose_statistical_splits(rows, [spec], seed=42, resamples=64)
    best = result.proposals[0]
    assert set(best.left_ids) | set(best.right_ids) == {str(i) for i in range(40)}
    assert len(best.left_ids) == len(best.right_ids) == 20
    assert best.effect_fraction > 0.95
    assert best.full_search_null_percentile > 0.9
    assert best.split_stability > 0.9
    assert result.inference_kind == "exploratory"
    assert result.formal_p_value is None


def test_periodic_wrap_does_not_create_false_two_region_proposal():
    from cloudra.tools.core.conformer_statistical_regions import propose_statistical_splits

    spec = DescriptorSpec(kind="dihedral", stable_atom_ids=["a", "b", "c", "d"], source="declared_reaction_coordinate")
    values = [179, -179, 178, -178, 177, -177, 176, -176]
    result = propose_statistical_splits(observations(values, spec), [spec], seed=42, resamples=64)
    best = result.proposals[0]
    assert best.observed_span < 10
    assert best.full_search_null_percentile < 0.9
    assert "circular" in result.null_model


def test_result_is_reproducible_and_preserves_every_candidate():
    from cloudra.tools.core.conformer_statistical_regions import propose_statistical_splits

    spec = DescriptorSpec(kind="distance", stable_atom_ids=["a", "b"])
    rows = observations([1, 1.1, 1.2, 3, 3.1, 3.2], spec)
    a = propose_statistical_splits(rows, [spec], seed=7, resamples=16)
    b = propose_statistical_splits(list(reversed(rows)), [spec], seed=7, resamples=16)
    assert a == b
    assert a.candidate_ids == ["0", "1", "2", "3", "4", "5"]
    assert "sampling_independence_unverified" in a.warnings


def test_no_hidden_significance_threshold_and_small_sample_is_explicit():
    from cloudra.tools.core.conformer_statistical_regions import propose_statistical_splits

    spec = DescriptorSpec(kind="distance", stable_atom_ids=["a", "b"])
    result = propose_statistical_splits(observations([1, 2, 3], spec), [spec], seed=42, resamples=16)
    assert result.proposals == []
    assert "insufficient_samples_for_within_region_variation" in result.warnings


def test_energy_only_enters_with_explicit_comparability_and_coordinate_reason():
    import pytest

    from cloudra.tools.core.conformer_statistical_regions import StatisticalCoordinate

    with pytest.raises(ValueError):
        StatisticalCoordinate(key="energy", kind="energy", reason="energy axis", energy_comparison_key=None)
    with pytest.raises(ValueError):
        StatisticalCoordinate(key="torsion", kind="dihedral", reason="")


def test_accepting_exploratory_split_changes_partition_and_preserves_history(tmp_path):
    from cloudra.tools.core.conformer_cards import build_region_cards
    from cloudra.tools.core.conformer_regions import RegionConfig, partition_candidates
    from cloudra.tools.core.conformer_statistical_regions import apply_statistical_partition, propose_statistical_splits
    from tests.test_conformer_catalog import make_candidate

    spec = DescriptorSpec(
        kind="distance", stable_atom_ids=["C1", "O1"], source="declared_reaction_coordinate", tolerance=10
    )
    candidates = [
        make_candidate(tmp_path, geometry_ref="", positions=[[0, 0, 0], [x, 0, 0]]) for x in [1, 1.1, 1.2, 3, 3.1, 3.2]
    ]
    old = partition_candidates(candidates, RegionConfig(descriptor_specs=[spec]))
    evidence = propose_statistical_splits(list(old.descriptors.values()), [spec], seed=7, resamples=16)
    new = apply_statistical_partition(
        candidates,
        old,
        evidence,
        proposal_indices=[0],
        decision_id="accept-1",
        reason="explore separated approach distances",
    )
    assert len(old.regions) == 1 and len(new.regions) == 2
    assert set(cid for region in new.regions.values() for cid in region.member_ids) == {
        c.candidate_id for c in candidates
    }
    assert new.previous_revision == old.revision
    assert set(new.region_mapping[next(iter(old.regions))]) == set(new.regions)
    cards = build_region_cards(new, candidates, [])
    assert all(c.partition_method == "exploratory_statistical_split" for c in cards)
    assert all(c.partition_evidence["formal_p_value"] is None for c in cards)
    assert all(c.partition_evidence["decision_id"] == "accept-1" for c in cards)


def test_statistical_partition_rejects_stale_membership_and_empty_reason(tmp_path):
    import pytest

    from cloudra.tools.core.conformer_regions import RegionConfig, partition_candidates
    from cloudra.tools.core.conformer_statistical_regions import apply_statistical_partition, propose_statistical_splits
    from tests.test_conformer_catalog import make_candidate

    spec = DescriptorSpec(kind="distance", stable_atom_ids=["C1", "O1"], source="declared_window")
    candidates = [make_candidate(tmp_path, geometry_ref="", positions=[[0, 0, 0], [x, 0, 0]]) for x in [1, 1.1, 3, 3.1]]
    old = partition_candidates(candidates, RegionConfig(descriptor_specs=[spec]))
    evidence = propose_statistical_splits(list(old.descriptors.values()), [spec], seed=7, resamples=8)
    with pytest.raises(ValueError, match="membership"):
        apply_statistical_partition(
            candidates[:-1], old, evidence, proposal_indices=[0], decision_id="d", reason="reason"
        )
    with pytest.raises(ValueError, match="reason"):
        apply_statistical_partition(candidates, old, evidence, proposal_indices=[0], decision_id="d", reason=" ")


def test_synthetic_statistical_fixture_is_consumed_without_defining_production_thresholds():
    import json
    from pathlib import Path

    from cloudra.tools.core.conformer_statistical_regions import propose_statistical_splits

    fixture = json.loads((Path(__file__).parent / "fixtures/conformer_selection/statistical_cases.json").read_text())
    for case in fixture["cases"]:
        spec = DescriptorSpec(
            kind=case["kind"], stable_atom_ids=case["atom_ids"], source="synthetic_declared_coordinate"
        )
        result = propose_statistical_splits(observations(case["values"], spec), [spec], seed=42, resamples=64)
        if case["expected"] == "strong_exploratory_split":
            assert result.proposals[0].effect_fraction > 0.95 and result.proposals[0].split_stability > 0.9
        elif case["expected"] == "short_contiguous_arc":
            assert result.proposals[0].observed_span < 10
        else:
            assert result.proposals == []
        assert result.formal_p_value is None


def test_energy_axis_uses_only_a_complete_comparable_converged_set(tmp_path):
    from cloudra.tools.core.conformer_catalog import EnergyObservation
    from cloudra.tools.core.conformer_regions import RegionConfig, partition_candidates
    from cloudra.tools.core.conformer_statistical_regions import (
        StatisticalPartitionRequest,
        apply_statistical_partition,
        propose_statistical_splits,
        statistical_coordinates,
    )
    from tests.test_conformer_catalog import make_candidate

    base = make_candidate(tmp_path, geometry_ref="")
    candidates = [
        make_candidate(
            tmp_path,
            geometry_ref="",
            generator=f"frame-{i}",
            energies=[
                EnergyObservation(
                    value=e,
                    unit="Ha",
                    method_fingerprint="same_method",
                    species_key=base.species_key,
                    convergence="converged",
                )
            ],
        )
        for i, e in enumerate([-2, -2.001, -2.002, -1, -1.001, -1.002])
    ]
    snapshot = partition_candidates(candidates, RegionConfig(descriptor_specs=[]))
    request = StatisticalPartitionRequest(seed=42, resamples=16, include_energy=True)
    rows, coordinates, warnings = statistical_coordinates(snapshot, candidates, request)
    assert len(coordinates) == 1 and coordinates[0].kind == "energy"
    evidence = propose_statistical_splits(rows, coordinates, seed=request.seed, resamples=request.resamples)
    new = apply_statistical_partition(
        candidates,
        snapshot,
        evidence,
        proposal_indices=[0],
        decision_id="energy-d",
        reason="explore separable same-method energy populations",
    )
    assert len(new.regions) == 2 and new.partition_evidence["formal_p_value"] is None
    missing = candidates[:-1] + [make_candidate(tmp_path, geometry_ref="", generator="unknown_method")]
    other = partition_candidates(missing, RegionConfig(descriptor_specs=[]))
    rows, coords, warnings = statistical_coordinates(other, missing, request)
    assert coords == [] and "no_complete_comparable_converged_energy_axis" in warnings


def test_statistical_repartition_can_include_archived_optimization_child(tmp_path):
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates
    from cloudra.tools.core.conformer_statistical_regions import (
        StatisticalPartitionRequest,
        apply_statistical_partition,
        propose_statistical_splits,
        statistical_coordinates,
    )
    from tests.test_conformer_catalog import make_candidate

    candidates = [
        make_candidate(tmp_path, geometry_ref="", positions=[[0, 0, 0], [x, 0, 0]], generator=str(i))
        for i, x in enumerate([1.0, 1.1, 1.2, 4.0, 4.1, 4.2])
    ]
    previous = partition_candidates(
        candidates, RegionConfig(descriptor_specs=[DescriptorSpec(kind="distance", stable_atom_ids=["C1", "O1"])])
    )
    child = make_candidate(
        tmp_path,
        geometry_ref="",
        positions=[[0, 0, 0], [4.3, 0, 0]],
        generator="optimized",
        parent_id=candidates[-1].candidate_id,
    )
    all_candidates = [*candidates, child]
    request = StatisticalPartitionRequest(
        seed=42,
        resamples=16,
        source_catalog_id="cat",
        source_revision=previous.revision,
        additional_candidate_ids=[child.candidate_id],
    )
    rows, coordinates, _ = statistical_coordinates(previous, all_candidates, request)
    evidence = propose_statistical_splits(rows, coordinates, seed=42, resamples=16)
    updated = apply_statistical_partition(
        all_candidates,
        previous,
        evidence,
        proposal_indices=[0],
        decision_id="include-child",
        reason="Include measured optimizer child",
    )
    assert updated.previous_revision == previous.revision
    assert set(updated.descriptors) == {c.candidate_id for c in all_candidates}
