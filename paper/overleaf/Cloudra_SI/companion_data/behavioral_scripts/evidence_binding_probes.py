#!/usr/bin/env python3
"""Freeze synthetic evidence-link diagnostics grounded in formal48 records.

No model calls, native-log edits, geometry recomputation, scientific acceptance
labels, or changes to production code. Original databases are read immutable.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

SELECTED = (
    ("brief-errors/r1/evt_8ed26719359e47e0", "F", "geometry", "GR"),
    ("brief-errors/r1/evt_0c8ded93c02b415c", "I", "start_geometry", "GP"),
    ("brief-errors/r1/evt_f7ad8d7092784698", "P", "input_geometry", "source_endpoint_input_geometry"),
    ("brief-errors/r2/evt_4c0c8b41a6284357", "P", "species_ref", "alternate_target"),
)
PHASE = "exploratory_synthetic_evidence_binding_diagnostic"
SCOPE = "given_binding_requirements_only_not_scientific_acceptance"
REQUIREMENTS = (
    "给定关联要求：\n"
    "1. 所列 TS 优化末帧与 TS 单虚频分析必须是同一几何。\n"
    "2. 所列双向 IRC 的起点必须是该 TS 几何。\n"
    "3. 两份端点优化的原生起始几何，必须分别对应这份 IRC 的两个真实外帧；"
    "两个方向可以交换，不能用别份 IRC 的外帧替代。\n"
    "4. 每份端点优化末帧必须与其零虚频分析几何相同；两份末帧的物种身份"
    "必须分别是目标步骤声明的 source_species 和 target_species。\n"
    "局部正常终止、优化收敛、TS 一个虚频及端点零虚频的要求沿用原契约，"
    "在下面所有局部计算记录中均已作为给定事实列出；此题只检查记录之间的关联。"
)
INTRO = (
    "synthetic 关联诊断。局部数值摘自原运行的归档记录；几何对应关系按原程序的"
    "关联陈述转写为本题给定事实，没有重新核验原始坐标。几何编号是合成引用别名，"
    "同名表示题设给定同一几何，异名表示不同几何。只根据给定事实检查引用关联，"
    "不要求你从坐标、能量或文件名自行判断几何是否相同。"
)
CHOICES = ("所给关联要求满足。", "所给关联要求不满足。")


def read_only(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
    connection.execute("PRAGMA query_only=ON")
    connection.row_factory = sqlite3.Row
    return connection


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def short_path(value: str, workspace: str) -> str:
    return str(Path(value).relative_to(workspace))


def extract(case: dict, parser_cases: list[dict]) -> tuple[dict, dict]:
    """Join the recorded runtime result to its original review and file rows."""
    runtime = Path(case["source_database"])
    with read_only(runtime) as connection:
        original = connection.execute("SELECT data FROM events WHERE event_id=?",
                                      (case["source_event"]["event_id"],)).fetchone()
    if original is None or json.loads(original["data"])["result"] != case["raw_result"]:
        raise ValueError("formal_case_differs_from_original_runtime_event")
    review_id = case["raw_result"]["data"]["result"]["review_id"]
    database = runtime.parent / "conversations" / case["project_id"] / "tasks/database.db"
    with read_only(database) as connection:
        review = dict(connection.execute("SELECT * FROM dag_review_requests WHERE request_id=?",
                                         (review_id,)).fetchone())
        proposal = json.loads(review["proposal"])
        evidence = []
        for ref in json.loads(review["supporting_refs"]):
            row = dict(connection.execute("SELECT * FROM dag_evidence WHERE evidence_id=?",
                                          (ref["ref_id"],)).fetchone())
            row["payload"] = json.loads(row["payload"])
            evidence.append(row)
        alternate = None
        if case["task"] == "HA1":
            other = connection.execute("SELECT proposal FROM dag_review_requests WHERE request_id=?",
                                      ("rev_daba1ddbf38b4439aaee14f500a3e2eb",)).fetchone()
            alternate = json.loads(other["proposal"])["target_identity"]["target"]
    checks = proposal["scientific_checks"]
    # Source selection only. These old verdict words never enter the prompt.
    if any(checks[key]["status"] != "passed" for key in ("ts_opt", "frequency", "short_irc")):
        raise ValueError("selected_source_no_longer_has_the_recorded_relation_statement")
    relation = checks["short_irc"]["detail"].partition(" [advisory]")[0]
    pairing = relation.partition(" pairing:")[0]
    if pairing not in {"direct", "swapped"} or "both actual IRC outer frames" not in relation:
        raise ValueError("unrecognized_original_endpoint_relation_statement")

    def file_for(path: str) -> dict:
        return next(row for row in evidence if row["payload"]["original_path"].endswith("/" + path))

    freq = file_for(proposal["ts_file"])
    opt = file_for(proposal["opt_file"]) if proposal["opt_file"] else freq
    irc = next(row for row in evidence if row["payload"]["original_path"]
               == proposal["irc_files"]["irc_file"]["original_path"])
    endpoints = proposal["endpoint_refs"]
    source = next(row for row in evidence if row["evidence_id"] == endpoints["endpoint_b"]["ref_id"])
    target = next(row for row in evidence if row["evidence_id"] == endpoints["endpoint_a"]["ref_id"])
    identity = proposal["target_identity"]
    workspace = case["task_evidence"]["workspace_dir"]

    parser_observations = {}

    def local(row: dict, kind: str) -> dict:
        payload = row["payload"]
        observations = []
        for parser_case in parser_cases:
            requested = parser_case["source_request"]["data"]["arguments_summary"].get("log_path", "")
            parsed = parser_case["raw_result"]["data"]
            if (requested and (payload["original_path"] == requested
                               or payload["original_path"].endswith("/" + requested))
                    and parsed.get("normal_termination") is True
                    and parsed.get("electronic_energy_hartree") == payload["final_energy_hartree"]):
                observations.append({"case_id": parser_case["case_id"],
                                     "source_event": parser_case["source_event"],
                                     "local_facts": {key: parsed.get(key) for key in (
                                         "normal_termination", "opt_converged", "imaginary_frequencies",
                                         "electronic_energy_hartree")}})
        parser_observations[row["evidence_id"]] = observations
        result = {"kind": kind, "file": short_path(payload["original_path"], workspace),
                  "normal_termination": True, "energy_hartree": payload["final_energy_hartree"]}
        if kind != "IRC":
            result["optimization_converged" if kind == "TS_Opt" else "imaginary_frequencies_cm"] = (
                True if kind == "TS_Opt" else payload["imaginary_frequencies"])
        return result

    records = {
        "S": {"kind": "目标步骤", "step_id": identity["edge_id"], "name": identity["name"],
              "source_species": identity["source"]["node_id"],
              "target_species": identity["target"]["node_id"],
              "ts_opt": "O", "ts_frequency": "F", "irc": "I",
              "source_endpoint": "R", "target_endpoint": "P"},
        "O": {**local(opt, "TS_Opt"), "final_geometry": "G0"},
        "F": {**local(freq, "TS_Freq"), "geometry": "G0"},
        "I": {**local(irc, "IRC"), "start_geometry": "G0", "outer_geometries": ["EA", "EB"]},
        "R": {**local(source, "endpoint_OptFreq"), "optimization_converged": True,
              "input_geometry": "EA" if pairing == "direct" else "EB",
              "final_geometry": "GR", "frequency_geometry": "GR",
              "species_ref": identity["source"]["node_id"]},
        "P": {**local(target, "endpoint_OptFreq"), "optimization_converged": True,
              "input_geometry": "EB" if pairing == "direct" else "EA",
              "final_geometry": "GP", "frequency_geometry": "GP",
              "species_ref": identity["target"]["node_id"]},
    }
    symbols = ("G0", "EA", "EB", "GR", "GP")
    aliases = ("g_17", "g_42", "g_08", "g_63", "g_29")
    rotation = int(digest(case["case_id"]), 16) % len(aliases)
    alias_map = dict(zip(symbols, aliases[rotation:] + aliases[:rotation], strict=True))
    for record in records.values():
        for key, value in record.items():
            if isinstance(value, str) and value in alias_map:
                record[key] = alias_map[value]
            elif key == "outer_geometries":
                record[key] = [alias_map[item] for item in value]
    for node in (identity["source"], identity["target"], alternate):
        if node is not None:
            records[node["node_id"]] = {"kind": "物种", "name": node["name"], "smiles": node["smiles"]}
    assert len(records["F"]["imaginary_frequencies_cm"]) == 1
    assert records["R"]["imaginary_frequencies_cm"] == records["P"]["imaginary_frequencies_cm"] == []
    provenance = {
        "base_case_id": case["case_id"], "task": case["task"], "arm": case["arm"], "round": case["round"],
        "runtime_database": str(runtime), "runtime_event": case["source_event"],
        "runtime_result_sha256": digest(case["raw_result"]), "conversation_database": str(database),
        "review_request_id": review_id, "review_proposal_sha256": digest(proposal),
        "target_identity": identity, "file_rows": evidence, "matching_parser_observations": parser_observations,
        "recorded_relation_statements": {key: checks[key]["detail"] for key in checks},
        "endpoint_pairing_statement": relation, "alternate_target_identity": alternate,
        "relation_status": "historical_program_assertions_given_as_diagnostic_premises_not_reverified_truth",
        "local_fact_status": "numbers_from_dag_evidence_payloads; termination/convergence from historical check statements",
        "alias_status": "all geometry aliases and the record handles S/O/F/I/R/P are synthetic; alias spelling does not identify the correct association and no geometry hash is asserted",
        "geometry_alias_mapping_for_audit_only": alias_map,
    }
    return records, provenance


def relations_satisfied(records: dict) -> bool:
    """Only follow explicit references; do not infer chemistry from numbers."""
    step = records["S"]
    opt, freq, irc = (records[step[key]] for key in ("ts_opt", "ts_frequency", "irc"))
    source, target = (records[step[key]] for key in ("source_endpoint", "target_endpoint"))
    return (
        opt["final_geometry"] == freq["geometry"] == irc["start_geometry"]
        and sorted([source["input_geometry"], target["input_geometry"]]) == sorted(irc["outer_geometries"])
        and source["final_geometry"] == source["frequency_geometry"]
        and target["final_geometry"] == target["frequency_geometry"]
        and source["species_ref"] == step["source_species"]
        and target["species_ref"] == step["target_species"]
    )


def triples(records: dict) -> list[list]:
    return [[subject, key, value] for subject, fields in records.items() for key, value in fields.items()]


def geometry_ids(records: dict) -> set[str]:
    fields = {"geometry", "start_geometry", "input_geometry", "final_geometry", "frequency_geometry"}
    return {value for record in records.values() for key, value in record.items() if key in fields} | set(
        records["I"]["outer_geometries"])


def render(records: dict, presentation: str) -> str:
    if presentation == "linked":
        data = records
        description = "按记录编号组织；每个属性值中的编号引用对应记录："
    else:
        data = sorted(triples(records), key=lambda row: (row[1], row[0]))
        description = "平铺事实表；每行为 [记录编号, 属性, 值]，属性值中的编号引用对应记录："
        restored = {}
        for subject, key, value in data:
            restored.setdefault(subject, {})[key] = value
        assert restored == records
    return description + "\n" + json.dumps(data, ensure_ascii=False, indent=2)


def build(study_dir: Path) -> dict:
    source_path = study_dir / "formal_cases.jsonl"
    source_bytes = source_path.read_bytes()
    wanted = {item[0] for item in SELECTED}
    all_cases = [json.loads(line) for line in source_bytes.decode().splitlines()]
    cases = {case["case_id"]: case for case in all_cases if case["case_id"] in wanted}
    probes, sources = [], []
    for case_id, subject, attribute, replacement in SELECTED:
        case = cases[case_id]
        parser_cases = [row for row in all_cases
                        if row["tool_name"] == "log_parser" and row["project_id"] == case["project_id"]]
        records, source = extract(case, parser_cases)
        original = records[subject][attribute]
        if replacement == "alternate_target":
            replacement = source["alternate_target_identity"]["node_id"]
        elif replacement == "source_endpoint_input_geometry":
            replacement = records[records["S"]["source_endpoint"]]["input_geometry"]
        else:
            replacement = source["geometry_alias_mapping_for_audit_only"][replacement]
        source["single_counterfactual_link"] = {"record": subject, "attribute": attribute,
                                                "original": original, "replacement": replacement}
        sources.append(source)
        for binding in ("coherent", "altered"):
            variant = copy.deepcopy(records)
            if binding == "altered":
                variant[subject][attribute] = replacement
            satisfied = relations_satisfied(variant)
            assert satisfied == (binding == "coherent")
            changes = [(name, key) for name, record in records.items() for key, value in record.items()
                       if variant[name][key] != value]
            assert changes == ([] if binding == "coherent" else [(subject, attribute)])
            assert geometry_ids(variant) == geometry_ids(records)
            for name in ("O", "F", "I", "R", "P"):
                for key in ("normal_termination", "energy_hartree", "optimization_converged",
                            "imaginary_frequencies_cm"):
                    if key in records[name]:
                        assert variant[name][key] == records[name][key]
            restored = copy.deepcopy(variant)
            restored[subject][attribute] = original
            assert restored == records  # All numerical and local-success facts are unchanged.
            for presentation in ("flat", "linked"):
                context = INTRO + "\n\n" + REQUIREMENTS + "\n\n" + render(variant, presentation)
                for order, indices in (("forward", (0, 1)), ("swapped", (1, 0))):
                    choices = dict(zip(("A", "B"), (CHOICES[index] for index in indices), strict=True))
                    meaning_index = 0 if satisfied else 1
                    expected = ("A", "B")[indices.index(meaning_index)]
                    probes.append({
                        "id": f"evidence_binding/{case_id}/{binding}/{presentation}/{order}",
                        "base_case_id": case_id, "mainline": "B",
                        "condition": f"{binding}_{presentation}", "option_order": order,
                        "synthetic": True, "study_phase": PHASE, "preregistered": False,
                        "evaluation_scope": SCOPE, "prompt": context
                        + "\n\n对目标步骤 S，所列记录是否满足以上给定关联要求？\n"
                        + "\n".join(f"{label}. {value}" for label, value in choices.items()) + "\n只回答 A 或 B。",
                        "choices": choices, "expected": expected,
                        "expected_meaning": "given_binding_requirements_satisfied" if satisfied
                        else "given_binding_requirements_not_satisfied",
                        "binding_records": variant,
                    })
    assert len(probes) == len({row["id"] for row in probes}) == 32
    assert Counter(row["expected"] for row in probes) == {"A": 16, "B": 16}
    for row in probes:
        assert not any(token in row["prompt"] for token in (
            '"complete"', '"unresolved"', '"passed"', '"accepted"', '"next_action"', '"mismatch"'))
    output = study_dir / "evidence_binding_probes.jsonl"
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in probes), encoding="utf-8")
    provenance = {
        "study_phase": PHASE, "preregistered": False, "synthetic": True, "mainline": "B",
        "evaluation_scope": SCOPE, "no_llm_executed": True, "n": len(probes), "source_chains": sources,
        "formal_cases": {"path": str(source_path), "sha256": hashlib.sha256(source_bytes).hexdigest()},
        "system_trace": {"path": str(study_dir / "system_trace.json"),
                         "sha256": hashlib.sha256((study_dir / "system_trace.json").read_bytes()).hexdigest()},
        "contract_sources": ["cloudra/dag/models.py:1048-1072",
                             "cloudra/tools/core/irc_evidence.py:495-607",
                             "cloudra/tools/core/irc_evidence.py:610-699"],
        "label_basis": "Explicit reference equality, paired endpoint membership, and declared species references under the quoted existing contract; no scientific threshold or scoring rule added.",
        "factorial_design": "4 source chains x 2 binding conditions x 2 equivalent presentations x 2 option orders = 32 inputs; 16 per answer letter.",
        "presentation_control": "flat triples and linked records contain identical propositions; grouping/order alone differ.",
        "binding_control": "Exactly one existing reference changes per source chain. Geometry-ID sets are identical before/after; no new or deleted ID. All numerical values and all local termination/convergence/frequency facts are retained.",
        "excluded_from_prompts": ["complete", "unresolved", "accepted", "passed", "scientific_checks.status",
                                  "next_action", "supervisor verdicts", "expected labels"],
        "limitations": [
            "All 32 inputs are synthetic, source-grounded association diagnostics, not original-context replays.",
            "Geometry equivalences and local termination/convergence are premises normalized from historical program statements; native logs/coordinates were not independently reverified.",
            "The positive label means only that the explicitly given association requirements are satisfied; it is not scientific acceptance of any original run.",
            "Four chains cover three tasks; NB1's two chains share an original run and are not independent research tasks.",
            "Synthetic aliases and counterfactual links are not added to or substituted for original records.",
            "No results, general research-ability conclusions, or original-provider behavior claims exist until separately authorized model experiments.",
        ],
    }
    provenance_path = study_dir / "evidence_binding_provenance.json"
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"n": len(probes), "output": str(output), "provenance": str(provenance_path),
            "source_chain_ids": [item[0] for item in SELECTED], "no_llm_executed": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, default=Path("output/cloudra_model_study_20261028"))
    args = parser.parse_args()
    print(json.dumps(build(args.study_dir.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
