"""Catalog source replay keeps an already bound archive without guessing."""

import json
from pathlib import Path

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.services.conformer_store import list_candidates, put_region_snapshot
from cloudra.tools.core.conformer_regions import RegionConfig, partition_candidates
from cloudra.tools.core.ts_candidate_pipeline import use_catalog_source
from cloudra.tools.core.ts_inputs import CatalogConformer
from tests.test_ts_selected_optimizer import catalog_seed
from tests.test_ts_stage_inputs import record_fixture

pytestmark = pytest.mark.usefixtures("ts_producer_authority", "rdkit_chemistry")


def _source_and_record(tmp_path):
    values, _ = catalog_seed(tmp_path)
    source = CatalogConformer(**values, optimization={
        "engine": "xtb", "method": "GFN2-xTB", "basis_set": ""})
    record = record_fixture(tmp_path)
    record.owner_conversation_id, record.owner_session_id = "project", "owner"
    return source, record


def _archive_second_partition(source):
    db = ComputeDB().init()
    members = list_candidates(db, source.catalog_id, project_id="project", owner_id="owner")
    second = partition_candidates(members, RegionConfig(descriptor_specs=[]))
    put_region_snapshot(db, second, project_id="project", owner_id="owner")
    return second


def test_bound_product_keeps_original_archive_after_another_partition(tmp_path):
    source, record = _source_and_record(tmp_path)
    use_catalog_source(record, source, "product")
    seed = (Path(record.run_dir) / "selected_candidates" / source.candidate_id / "seed.xyz")
    table = seed.with_name("atom_table.json")
    before_seed, before_table = seed.read_bytes(), table.read_bytes()
    original_revision = json.loads(before_table)["partition_revision"]
    second = _archive_second_partition(source)
    assert second.revision != original_revision

    use_catalog_source(record, source, "product")

    assert record.blocked is None
    assert json.loads(table.read_bytes())["partition_revision"] == original_revision
    assert seed.read_bytes() == before_seed
    assert table.read_bytes() == before_table


@pytest.mark.parametrize("role", ["reactant", "product"])
def test_unbound_candidate_with_multiple_archives_is_not_selected(tmp_path, role):
    source, record = _source_and_record(tmp_path)
    _archive_second_partition(source)
    with pytest.raises(ValueError, match="unique bound archive"):
        use_catalog_source(record, source, role)
    assert record.selected_candidate_id is None
    assert record.product_seed_candidate_id is None


def test_bound_reactant_keeps_original_archive_after_another_partition(tmp_path):
    source, record = _source_and_record(tmp_path)
    use_catalog_source(record, source, "reactant")
    original_revision = record.partition_revision
    _archive_second_partition(source)
    use_catalog_source(record, source, "reactant")
    assert record.partition_revision == original_revision


def test_foreign_catalog_owner_cannot_bind_candidate(tmp_path):
    source, record = _source_and_record(tmp_path)
    record.owner_session_id = "foreign-owner"
    with pytest.raises(ValueError, match="project/owner mismatch"):
        use_catalog_source(record, source, "product")


def test_foreign_candidate_is_not_bound_to_an_owned_catalog(tmp_path):
    source, record = _source_and_record(tmp_path)
    source.candidate_id = "foreign-candidate"
    use_catalog_source(record, source, "product")
    assert record.blocked.failure_class == "candidate_identity_mismatch"
    assert record.product_seed_candidate_id is None


def test_product_pin_cannot_use_a_nonexistent_archive(tmp_path):
    source, record = _source_and_record(tmp_path)
    use_catalog_source(record, source, "product")
    table = (Path(record.run_dir) / "selected_candidates" / source.candidate_id / "seed.xyz").with_name("atom_table.json")
    metadata = json.loads(table.read_text())
    metadata["partition_revision"] = "nonexistent-archive"
    table.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="snapshot not found"):
        use_catalog_source(record, source, "product")


def test_unbound_run_cannot_borrow_another_runs_private_pin(tmp_path):
    source, bound = _source_and_record(tmp_path)
    use_catalog_source(bound, source, "product")
    _archive_second_partition(source)
    unbound = record_fixture(tmp_path / "another-run")
    unbound.owner_conversation_id, unbound.owner_session_id = "project", "owner"
    original = (Path(bound.run_dir) / "selected_candidates" / source.candidate_id / "seed.xyz").parent
    borrowed = Path(unbound.run_dir) / "selected_candidates" / source.candidate_id
    borrowed.mkdir(parents=True)
    for name in ("seed.xyz", "atom_table.json"):
        (borrowed / name).write_bytes((original / name).read_bytes())
    with pytest.raises(ValueError, match="metadata"):
        use_catalog_source(unbound, source, "product")
    assert unbound.product_seed_candidate_id is None


@pytest.mark.parametrize("field", ["catalog_id", "candidate_id", "geometry_hash", "artifact_hash"])
def test_product_pin_metadata_cannot_claim_a_different_source(tmp_path, field):
    source, record = _source_and_record(tmp_path)
    use_catalog_source(record, source, "product")
    table = (Path(record.run_dir) / "selected_candidates" / source.candidate_id / "seed.xyz").with_name("atom_table.json")
    metadata = json.loads(table.read_text())
    metadata[field] = "foreign-or-forged"
    table.write_text(json.dumps(metadata))
    _archive_second_partition(source)
    with pytest.raises(ValueError, match="metadata"):
        use_catalog_source(record, source, "product")
