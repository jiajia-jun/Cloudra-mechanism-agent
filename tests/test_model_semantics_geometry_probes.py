"""Geometry probes must preserve physical pairs while changing their presentation."""

import io
import json
import math
import runpy
import sqlite3
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/model_semantics/geometry_probes.py"
XYZ = "4\nhand-checked diagnostic fixture\nC 0 0 0\nH 1 0 0\nO 0 3 0\nN 0 0 4\n"


@pytest.fixture
def api():
    return runpy.run_path(str(SCRIPT))


def candidate():
    return {
        "base_case_id": "fixture/event",
        "source": {"event_id": "fixture", "archive_member": "fixture.xyz"},
        "watch_pairs": [[1, 2], [1, 3]],
        "report": "[Watched atom pairs]\n  r(C1-H2)=1.000 Å\n  r(C1-O3)=3.000 Å\n== Notes ==\n",
    }


def test_rotation_and_reordering_preserve_every_distance_and_source_pair(api):
    # A reflection, unsynchronized query index, or rounded coordinate corruption breaks this.
    probes = api["make_geometry_probes"](candidate(), XYZ)
    assert len(probes) == 8
    geometric = [p for p in probes if p["condition"] != "tool_distances"]
    for probe in geometric:
        atoms = api["parse_xyz"](probe["presentation"]["xyz"])
        source_to_presented = probe["presentation"]["source_to_presented_1based"]
        for a, b, want in ((1, 2, 1), (1, 3, 3), (1, 4, 4), (2, 3, math.sqrt(10))):
            pa = atoms[source_to_presented[str(a)] - 1][1]
            pb = atoms[source_to_presented[str(b)] - 1][1]
            assert math.dist(pa, pb) == pytest.approx(want, abs=1e-10)
        for choice in probe["choices"].values():
            source_pair = choice["source_atoms_1based"]
            displayed_pair = choice["presented_atoms_1based"]
            assert displayed_pair == [source_to_presented[str(i)] for i in source_pair]
    reordered = next(p for p in probes if p["condition"] == "reordered_xyz")
    assert reordered["presentation"]["source_to_presented_1based"] == {
        "1": 4, "2": 3, "3": 2, "4": 1,
    }
    matrix = next(p for p in probes if p["condition"] == "rotated_translated_xyz")["presentation"]["rotation"]
    determinant = (
        matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )
    assert determinant == pytest.approx(1)


def test_ab_options_are_transposed_without_changing_the_physical_answer(api):
    probes = api["make_geometry_probes"](candidate(), XYZ)
    for condition in {p["condition"] for p in probes}:
        direct, swapped = [p for p in probes if p["condition"] == condition]
        assert direct["expected"] == "A"
        assert swapped["expected"] == "B"
        assert direct["choices"]["A"] == swapped["choices"]["B"]
        assert direct["choices"]["B"] == swapped["choices"]["A"]
        assert "expected" not in direct["prompt"]
    tools = [p for p in probes if p["condition"] == "tool_distances"]
    assert all(p["representation_vs_computation"] == "outsourced_computation" for p in tools)
    assert all("xyz" not in p["presentation"] for p in tools)


def test_report_mismatch_is_rejected_instead_of_creating_a_label(api):
    c = candidate()
    c["report"] = c["report"].replace("1.000", "1.010")
    with pytest.raises(ValueError, match="report_distance_mismatch"):
        api["make_geometry_probes"](c, XYZ)


def test_targeted_archive_copy_ignores_unrequested_members(api, tmp_path):
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for name, content in (("root/one.xyz", XYZ), ("../escape.xyz", XYZ), ("root/other.xyz", XYZ)):
            payload = content.encode()
            entry = tarfile.TarInfo(name)
            entry.size = len(payload)
            tf.addfile(entry, io.BytesIO(payload))
    destination = tmp_path / "copied"
    copied = api["copy_archive_members"](archive, {"root/one.xyz"}, destination)
    assert set(copied) == {"root/one.xyz"}
    assert copied["root/one.xyz"].read_text() == XYZ
    assert not (tmp_path / "escape.xyz").exists()
    assert not (destination / "root/other.xyz").exists()


def test_ha1_controls_only_label_source_carbon_count_and_name(api):
    source = {
        "source": {"event_id": "fixture_ha1"},
        "product_smiles": "C=CC=CC",
        "name": "3-methylcyclobutene ring opening: determine the stereochemical outcome",
    }
    probes = api["make_ha1_probes"](source)
    assert len(probes) == 4
    assert [p["expected"] for p in probes] == ["A", "B", "A", "B"]
    assert probes[0]["choices"] == {"A": 5, "B": 4}
    assert all(p["evaluation_scope"] == "diagnostic_primitive_not_scientific_success" for p in probes)
    assert all(json.loads(json.dumps(p))["mainline"] == "A" for p in probes)


def test_build_records_seed_mismatch_in_provenance_without_guessing(api, tmp_path):
    # Losing exclusions on the failure path would hide why the prescribed real case was unusable.
    study = tmp_path / "study"
    database = study / "formal48/archive_metadata/cloudra-p1b-20261024/guided/r1/runtime/runtime-v2.db"
    database.parent.mkdir(parents=True)
    member = "cloudra-p1b-20261024/guided/r1/sandboxes/NB1/batch/source.xyz"
    archive = tmp_path / "archive.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        entry = tarfile.TarInfo(member)
        entry.size = len(XYZ.encode())
        tf.addfile(entry, io.BytesIO(XYZ.encode()))
    projects = [
        {"project_id": "nb", "arm": "guided", "round": "r1", "task": "NB1",
         "original_workspace": "/source", "archive_sandbox_prefix": member.rpartition("/")[0]},
        {"project_id": "ha", "arm": "guided", "round": "r1", "task": "HA1"},
    ]
    (study / "system_trace.json").write_text(json.dumps({"formal_dataset": {
        "archive": str(archive), "project_task_map": projects,
    }}))
    (study / "formal48/member_index.json").write_text(json.dumps([{"path": member, "bytes": len(XYZ.encode())}]))
    bad_report = candidate()["report"].replace("1.000", "1.010")
    events = [
        ("req", "tool.requested", {"arguments_summary": {
            "mode": "analyze", "input_path": "source.xyz", "watch_pairs": [[1, 2], [1, 3]],
        }}, "nb"),
        (api["SEED_EVENT"], "tool.result_recorded", {
            "tool_name": "internal_coordinates", "request_event_id": "req", "result": {"data": {"report": bad_report}},
        }, "nb"),
        ("ha1", "agent.message_injected", {"sender": "user", "content":
         "Determine the mechanism of the following reaction: 3-methylcyclobutene ring opening. "
         "Reactant SMILES: CC1CC=C1; product SMILES: C=CC=CC; total charge 0."}, "ha"),
    ]
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE events (event_id TEXT,type TEXT,data TEXT,project_id TEXT,created_at TEXT)")
        connection.executemany("INSERT INTO events VALUES (?,?,?,?,?)", [
            (event, kind, json.dumps(data), project, "fixture") for event, kind, data, project in events
        ])
    result = api["build"](study)
    assert result["geometry_probe_count"] == 0
    assert result["prescribed_seed_status"] == "excluded"
    assert any(e["reason"].startswith("report_distance_mismatch") for e in result["excluded"])
    assert (study / "geometry_probe_provenance.json").is_file()
