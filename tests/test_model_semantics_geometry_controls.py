"""Follow-up controls separate numbering lookup from distance computation."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/model_semantics/geometry_controls.py"
XYZ = "4\noriginal comment\nC 0.000 0 0\nC 10.000 0 0\nH 0 3.000 0\nH 0 0 4.000\n"


@pytest.fixture
def api():
    return runpy.run_path(str(SCRIPT))


def selected():
    return {"base_case_id": "geometry/fixture", "source": {"event_id": "fixture"},
            "source_pairs": [
                {"source_atoms_1based": [1, 3], "source_atom_labels": ["C1", "H3"],
                 "distance_angstrom": 3.0, "reported_angstrom": "3.000"},
                {"source_atoms_1based": [2, 3], "source_atom_labels": ["C2", "H3"],
                 "distance_angstrom": 109 ** 0.5, "reported_angstrom": "10.440"},
            ]}


def test_each_condition_transposes_ab_without_relabeling_source_atoms(api):
    probes = api["make_controls"](selected(), XYZ)
    assert len({p["id"] for p in probes}) == 6
    assert {p["condition"] for p in probes} == {
        "indexed_coordinates", "coordinate_lookup", "pair_coordinates",
    }
    for condition in {p["condition"] for p in probes}:
        direct, swapped = [p for p in probes if p["condition"] == condition]
        assert (direct["expected"], swapped["expected"]) == ("A", "B")
        assert direct["choices"]["A"] == swapped["choices"]["B"]
        assert direct["choices"]["B"] == swapped["choices"]["A"]
        assert direct["presentation"] == swapped["presentation"]
        assert direct["distance_values_supplied"] is False


def test_lookup_uses_same_element_distractor_and_exact_source_coordinate_tokens(api):
    probes = api["make_controls"](selected(), XYZ)
    lookup = next(p for p in probes if p["condition"] == "coordinate_lookup")
    assert XYZ in lookup["prompt"]  # Preserve the original implicit row-numbering burden.
    assert lookup["lookup_target_source_atom_1based"] == 1
    assert lookup["lookup_distractor_source_atom_1based"] == 2
    assert lookup["choices"]["A"]["element"] == lookup["choices"]["B"]["element"] == "C"
    assert lookup["choices"]["A"]["coordinate_tokens"] == ["0.000", "0", "0"]
    assert lookup["choices"]["B"]["coordinate_tokens"] == ["10.000", "0", "0"]
    indexed = next(p for p in probes if p["condition"] == "indexed_coordinates")
    assert "1 C 0.000 0 0" in indexed["prompt"]
    assert "4 H 0 0 4.000" in indexed["prompt"]
    assert indexed["information_change"]["coordinate_information_equivalent"] is True
    pairs = next(p for p in probes if p["condition"] == "pair_coordinates")
    assert pairs["information_change"]["retained_source_atoms_1based"] == [1, 2, 3]
    assert pairs["information_change"]["omitted_source_atoms_1based"] == [4]
    assert pairs["information_change"]["coordinate_information_equivalent"] is False
    assert "4.000" not in pairs["prompt"]


def frozen_fixture(tmp_path):
    source = tmp_path / "source.xyz"
    source.write_text(XYZ)
    parent_probes = tmp_path / "geometry_probes.jsonl"
    parent_probes.write_text('{"frozen": true}\n')
    case = selected()
    case["source"].update({"source_xyz_path": str(source),
                            "source_xyz_sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    parent_provenance = tmp_path / "geometry_probe_provenance.json"
    parent_provenance.write_text(json.dumps({"selected": [case],
        "output_sha256": hashlib.sha256(parent_probes.read_bytes()).hexdigest()}))
    return source, parent_probes, parent_provenance


def test_build_preserves_frozen_inputs_and_marks_followup_exploratory(api, tmp_path):
    inputs = frozen_fixture(tmp_path)
    before = {p: p.read_bytes() for p in inputs}
    provenance = api["build"](tmp_path)
    assert all(p.read_bytes() == data for p, data in before.items())
    assert provenance["total_probe_count"] == 6
    assert provenance["preregistered"] is False
    assert provenance["no_llm_executed"] is True
    assert provenance["study_phase"] == "exploratory_followup_after_initial_geometry_probe"
    assert (tmp_path / "geometry_controls.jsonl").is_file()
    assert (tmp_path / "geometry_controls_provenance.json").is_file()


def test_build_rejects_changed_frozen_source_instead_of_replacing_case(api, tmp_path):
    source, _, _ = frozen_fixture(tmp_path)
    source.write_text(XYZ.replace("10.000", "11.000"))
    with pytest.raises(ValueError, match="frozen_source_hash_mismatch"):
        api["build"](tmp_path)
    assert not (tmp_path / "geometry_controls.jsonl").exists()
