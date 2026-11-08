"""Smoke tests for the archived-delivery rescore command.

The fixture is a tiny P2/P1b directory layout. It checks that organized graphs
are preferred, workstation-absolute paths are rewritten only in the staged
copy, and the 2 November overlay copies published cells instead of inventing
scores. No agent, model, or quantum-chemistry program is run.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from cloudra.benchmark.rescore_archive import (
    main,
    relativize_evidence_path,
    repair_source_names_reconstruction,
)
from cloudra.benchmark.runner import BenchmarkRunner
from cloudra.benchmark.schema import TaskSpec

GRAPH = {
    "nodes": [
        {
            "id": "R",
            "role": "reactant",
            "smiles": ["C"],
            "accessible": False,
            "properties": {},
        }
    ],
    "edges": [],
}


def _task(task_id: str, tier: str) -> dict:
    return {
        "task_id": task_id,
        "tier": tier,
        "prompt": {"query": "Write mechanism_graph.json for this fixture."},
        "system": {"reactants": ["C"]},
        "gold": {"mechanism_graph": GRAPH},
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _p2_fixture(root: Path) -> Path:
    archive = root / "Cloudra-P2-final-20261031"
    native = {
        **GRAPH,
        "nodes": [
            {
                **GRAPH["nodes"][0],
                "properties": {
                    "evidence_log": (
                        "/home/ly/cloudra-p2c-20261025/guided/r1/sandboxes/F4/"
                        "batch_aaa/evidence.log"
                    )
                },
            }
        ],
    }
    f4 = archive / "campaign_data/cloudra-p2c-20261025/guided/r1/sandboxes/F4/batch_aaa"
    f1 = archive / "campaign_data/cloudra-p2c-20261025/standard/r1/sandboxes/F1/batch_bbb"
    _write_json(f4 / "mechanism_graph.json", native)
    (f4 / "evidence.log").write_text("not a calculation\n", encoding="utf-8")
    _write_json(
        f1 / "mechanism_graph.json",
        {
            "nodes": [
                {"id": "R", "role": "reactant", "smiles": ["C"], "accessible": True}
            ],
            "edges": [],
        },
    )
    _write_json(archive / "reconstructions/standard/F1/mechanism_graph.json", GRAPH)
    hi1 = archive / "campaign_data/cloudra-p2c-20261025/guided/r1/sandboxes/HI1/batch_94084d85d0634ca0"
    _write_json(hi1 / "mechanism_graph.json", GRAPH)
    _write_json(
        archive / "reconstructions/guided/HI1/mechanism_graph.json",
        {
            "nodes": [
                {"id": "fallback", "role": "reactant", "smiles": ["C"], "accessible": True}
            ],
            "edges": [],
        },
    )
    table = archive / "tables/final_scores_per_run.csv"
    table.parent.mkdir(parents=True, exist_ok=True)
    with table.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["campaign", "arm", "task", "tier", "sandbox", "repair_source"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "campaign": "cloudra-p2c-20261025",
                    "arm": "guided",
                    "task": "F4",
                    "tier": "easy",
                    "sandbox": "/home/ly/cloudra-p2c-20261025/guided/r1/sandboxes/F4/batch_aaa",
                    "repair_source": "",
                },
                {
                    "campaign": "cloudra-p2c-20261025",
                    "arm": "standard",
                    "task": "F1",
                    "tier": "easy",
                    "sandbox": "/home/ly/cloudra-p2c-20261025/standard/r1/sandboxes/F1/batch_bbb",
                    "repair_source": (
                        "/home/ly/adjudication/reconstructed/standard/F1/mechanism_graph.json"
                    ),
                },
                {
                    "campaign": "cloudra-p2c-20261025",
                    "arm": "guided",
                    "task": "HI1",
                    "tier": "hard",
                    "sandbox": (
                        "/home/ly/cloudra-p2c-20261025/guided/r1/sandboxes/HI1/"
                        "batch_94084d85d0634ca0"
                    ),
                    "repair_source": "",
                },
            ]
        )
    return archive


def _tasks(root: Path) -> Path:
    tasks = root / "tasks"
    _write_json(tasks / "easy/F4.json", _task("F4", "easy"))
    _write_json(tasks / "easy/F1.json", _task("F1", "easy"))
    _write_json(tasks / "hard/HA1.json", _task("HA1", "hard"))
    _write_json(tasks / "hard/HI1.json", _task("HI1", "hard"))
    return tasks


def _p1b_fixture(root: Path) -> tuple[Path, Path]:
    campaign = root / "cloudra-p1b-20261024"
    sandbox = campaign / "standard/r2/sandboxes/HA1/batch_x"
    sandbox.mkdir(parents=True)
    (sandbox / "native.log").write_text("untouched\n", encoding="utf-8")
    offline = root / "p1b-offline"
    offline.mkdir()
    _write_json(offline / "ha1_r2_graph.json", GRAPH)
    with (offline / "standard_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["arm", "round", "task_id", "sandbox", "offline_reconstruction"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "arm": "standard",
                "round": "r2",
                "task_id": "HA1",
                "sandbox": "cloudra-p1b-20261024/standard/r2/sandboxes/HA1/batch_x",
                "offline_reconstruction": "human_reconstructed_from_own_run",
            }
        )
    return campaign, offline


def _rows(output: Path) -> list[dict[str, str]]:
    with (output / "rescored_runs.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _by_task(output: Path) -> dict[tuple[str, str], dict[str, str]]:
    return {(row["archive"], row["task"]): row for row in _rows(output)}


def test_repair_source_does_not_treat_a_completed_delivery_as_reconstructed():
    assert repair_source_names_reconstruction(
        "/home/ly/adjudication/reconstructed/brief-errors/IC3/mechanism_graph.json",
        "brief-errors",
        "IC3",
    )
    assert repair_source_names_reconstruction(
        "/home/ly/adjudication/reconstructed/standard/F1/mechanism_graph.json",
        "standard",
        "F1",
    )
    assert not repair_source_names_reconstruction("", "guided", "HI1")
    assert not repair_source_names_reconstruction(
        "/home/ly/cloudra-p2c-20261025/guided/r1/sandboxes/HI1/batch_94084d85d0634ca0/mechanism_graph.json",
        "guided",
        "HI1",
    )


def test_relativize_keeps_unknown_absolute_paths(tmp_path):
    (tmp_path / "evidence.log").write_text("x\n", encoding="utf-8")
    assert (
        relativize_evidence_path("/home/ly/campaign/sandboxes/T/batch/evidence.log", tmp_path)
        == "evidence.log"
    )
    assert relativize_evidence_path("evidence.log", tmp_path) == "evidence.log"
    assert (
        relativize_evidence_path("/home/ly/missing.log", tmp_path) == "/home/ly/missing.log"
    )


def test_rescore_uses_organized_graph_without_editing_archive(tmp_path):
    archive = _p2_fixture(tmp_path)
    campaign, offline = _p1b_fixture(tmp_path)
    tasks = _tasks(tmp_path)
    output = tmp_path / "out"
    native_f4 = archive / "campaign_data/cloudra-p2c-20261025/guided/r1/sandboxes/F4/batch_aaa/mechanism_graph.json"
    native_f1 = archive / "campaign_data/cloudra-p2c-20261025/standard/r1/sandboxes/F1/batch_bbb/mechanism_graph.json"
    native_hi1 = (
        archive
        / "campaign_data/cloudra-p2c-20261025/guided/r1/sandboxes/HI1/batch_94084d85d0634ca0/mechanism_graph.json"
    )
    fallback_hi1 = archive / "reconstructions/guided/HI1/mechanism_graph.json"
    p1b_log = campaign / "standard/r2/sandboxes/HA1/batch_x/native.log"
    before = {
        native_f4: native_f4.read_bytes(),
        native_f1: native_f1.read_bytes(),
        native_hi1: native_hi1.read_bytes(),
        fallback_hi1: fallback_hi1.read_bytes(),
        p1b_log: p1b_log.read_bytes(),
    }

    assert main(
        [
            "--p2-root",
            str(tmp_path),
            "--p1b-root",
            str(campaign),
            "--p1b-offline",
            str(offline),
            "--tasks-root",
            str(tasks),
            "--output",
            str(output),
        ]
    ) == 0

    rows = _by_task(output)
    assert set(rows) == {("p2", "F4"), ("p2", "F1"), ("p2", "HI1"), ("p1b", "HA1")}
    f4 = rows[("p2", "F4")]
    f1 = rows[("p2", "F1")]
    hi1 = rows[("p2", "HI1")]
    ha1 = rows[("p1b", "HA1")]
    assert f4["reconstruction"] == "false"
    assert f4["paths_relativized"] == "1"
    assert f4["score_input"] == "staged"
    assert "/home/ly/" in native_f4.read_text(encoding="utf-8")
    staged_graph = output / f4["scored_sandbox"] / "mechanism_graph.json"
    staged_text = staged_graph.read_text(encoding="utf-8")
    assert "/home/ly/" not in staged_text
    assert "evidence.log" in staged_text

    assert f1["reconstruction"] == "true"
    assert f1["graph_source"] == "reconstructions/standard/F1/mechanism_graph.json"
    assert f1["score_input"] == "staged"
    assert float(f1["final_score"]) > 0
    native_scored = BenchmarkRunner(tmp_path / "native-score").score_sandbox(
        TaskSpec.model_validate_json((tasks / "easy/F1.json").read_text(encoding="utf-8")),
        native_f1.parent,
    )
    assert native_scored.final_score == -1
    assert float(f1["final_score"]) != native_scored.final_score

    # guided/HI1 keeps the completed delivery. The reconstructions/ file is a
    # fallback and the score table does not name it as repair_source.
    assert hi1["reconstruction"] == "false"
    assert hi1["graph_source"] == ""
    assert hi1["score_input"] == "archive"
    assert hi1["graph_sha256"] == hashlib.sha256(native_hi1.read_bytes()).hexdigest()
    assert "fallback" not in native_hi1.read_text(encoding="utf-8")
    direct_hi1 = BenchmarkRunner(tmp_path / "hi1-direct").score_sandbox(
        TaskSpec.model_validate_json((tasks / "hard/HI1.json").read_text(encoding="utf-8")),
        native_hi1.parent,
    )
    assert float(hi1["graph_score"]) == direct_hi1.graph_score
    assert float(hi1["selfconsistency_score"]) == direct_hi1.selfconsistency_score
    assert float(hi1["accuracy_score"]) == direct_hi1.accuracy_score
    assert float(hi1["final_score"]) == direct_hi1.final_score
    assert float(hi1["final_score"]) != -1

    staged_f1 = output / f1["scored_sandbox"]
    direct = BenchmarkRunner(tmp_path / "direct-score").score_sandbox(
        TaskSpec.model_validate_json((tasks / "easy/F1.json").read_text(encoding="utf-8")),
        staged_f1,
    )
    assert float(f1["graph_score"]) == direct.graph_score
    assert float(f1["selfconsistency_score"]) == direct.selfconsistency_score
    assert float(f1["accuracy_score"]) == direct.accuracy_score
    assert float(f1["final_score"]) == direct.final_score
    assert f1["target_overlay"] == ""

    assert ha1["reconstruction"] == "true"
    assert ha1["graph_source"] == "ha1_r2_graph.json"
    assert not (campaign / "standard/r2/sandboxes/HA1/batch_x/mechanism_graph.json").exists()
    assert float(ha1["final_score"]) == float(f1["final_score"])

    for path, payload in before.items():
        assert path.read_bytes() == payload
    document = json.loads((output / "rescored_runs.json").read_text(encoding="utf-8"))
    assert document["agents_rerun"] is False
    assert document["quantum_chemistry_rerun"] is False
    assert document["target_overlay"] is None


def test_target_overlay_copies_published_cells(tmp_path):
    archive = _p2_fixture(tmp_path)
    tasks = _tasks(tmp_path)
    plain = tmp_path / "plain"
    overlaid = tmp_path / "overlaid"
    common = [
        "--p2-root",
        str(archive),
        "--tasks-root",
        str(tasks),
        "--only",
        "guided/F4",
    ]
    assert main([*common, "--output", str(plain)]) == 0
    correction = tmp_path / "corrections.csv"
    with correction.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["arm", "task", "accuracy", "score"])
        writer.writeheader()
        writer.writerow({"arm": "guided", "task": "F4", "accuracy": "0.25", "score": "0.125"})
    assert main(
        [
            *common,
            "--output",
            str(overlaid),
            "--apply-target-overlay",
            "--target-overlay",
            str(correction),
        ]
    ) == 0
    before = _by_task(plain)[("p2", "F4")]
    after = _by_task(overlaid)[("p2", "F4")]
    assert after["graph_score"] == before["graph_score"]
    assert after["selfconsistency_score"] == before["selfconsistency_score"]
    assert after["scorer_accuracy"] == before["accuracy_score"]
    assert after["scorer_final"] == before["final_score"]
    assert float(after["accuracy_score"]) == 0.25
    assert float(after["final_score"]) == 0.125
    assert after["target_overlay"] == "applied"
    assert float(after["scorer_accuracy"]) != 0.25


def test_output_inside_archive_is_rejected(tmp_path):
    archive = _p2_fixture(tmp_path)
    code = main(
        [
            "--p2-root",
            str(archive),
            "--tasks-root",
            str(_tasks(tmp_path)),
            "--output",
            str(archive / "inside"),
            "--only",
            "F4",
        ]
    )
    assert code == 2
    assert not (archive / "inside").exists()


def test_only_limits_rows(tmp_path):
    archive = _p2_fixture(tmp_path)
    output = tmp_path / "only"
    assert main(
        [
            "--p2-root",
            str(archive),
            "--tasks-root",
            str(_tasks(tmp_path)),
            "--output",
            str(output),
            "--only",
            "standard/r1/F1",
        ]
    ) == 0
    rows = _rows(output)
    assert [row["task"] for row in rows] == ["F1"]
    assert rows[0]["round"] == "r1"
