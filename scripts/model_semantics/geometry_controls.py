#!/usr/bin/env python3
"""Exploratory follow-up: separate XYZ indexing, coordinate lookup and arithmetic.

Use the same frozen source structures and pairs as geometry_probes.jsonl. This
script neither reruns selection nor changes any original probe or source file.
Run from the repository root with python -m scripts.model_semantics.geometry_controls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from scripts.model_semantics.geometry_probes import SCOPE, digest, parse_xyz

PHASE = "exploratory_followup_after_initial_geometry_probe"


def make_controls(selected: dict, source_xyz: str) -> list[dict]:
    atoms = parse_xyz(source_xyz)
    raw_rows = [line.split() for line in source_xyz.splitlines()[2:] if line.strip()]
    coordinates = [{"source_atom_1based": i, "element": row[0], "coordinate_tokens": row[1:],
                    "coordinates_angstrom": list(atoms[i - 1][1])}
                   for i, row in enumerate(raw_rows, 1)]
    pairs = []
    for pair in selected["source_pairs"]:
        a, b = pair["source_atoms_1based"]
        distance = math.dist(atoms[a - 1][1], atoms[b - 1][1])
        if f"{distance:.3f}" != pair["reported_angstrom"]:
            raise ValueError("frozen_pair_distance_mismatch")
        pairs.append({**pair, "distance_angstrom": distance,
                      "presented_atoms_1based": [a, b]})
    if len(pairs) != 2 or pairs[0]["distance_angstrom"] == pairs[1]["distance_angstrom"]:
        raise ValueError("frozen_two_distinct_pairs_required")

    # Fix lookup selection by original query order, then original atom row order.
    query_atoms = list(dict.fromkeys(i for pair in pairs for i in pair["source_atoms_1based"]))
    lookup = next(((coordinates[i - 1], other) for i in query_atoms for other in coordinates
                   if other["source_atom_1based"] != i
                   and other["element"] == coordinates[i - 1]["element"]
                   and other["coordinates_angstrom"] != coordinates[i - 1]["coordinates_angstrom"]), None)
    if lookup is None:
        raise ValueError("same_element_coordinate_distractor_unavailable")
    target, distractor = lookup
    relevant = sorted(query_atoms)
    omitted = [i for i in range(1, len(atoms) + 1) if i not in relevant]
    indexed_body = (
        "下面是原始坐标，坐标单位 Å。每一行显式给出原子编号（从 1 开始）：\n"
        f"原子数：{len(atoms)}\n原始注释：{source_xyz.splitlines()[1]}\n编号 元素 x y z\n"
        + "\n".join(f"{row['source_atom_1based']} {row['element']} " + " ".join(row["coordinate_tokens"])
                     for row in coordinates)
    )
    lookup_body = "下面是 XYZ 坐标，坐标单位 Å，原子编号从 1 开始，按行计数：\n" + source_xyz
    pair_rows = [[coordinates[i - 1] for i in pair["source_atoms_1based"]] for pair in pairs]
    pair_body = "下面只列出所比较两对原子的原始坐标（Å）；没有给出计算距离：\n"
    for number, rows in enumerate(pair_rows, 1):
        pair_body += f"第 {number} 对：\n" + "\n".join(
            f"原子 {row['source_atom_1based']} ({row['element']}): ("
            + ", ".join(row["coordinate_tokens"]) + ")" for row in rows
        ) + "\n"

    conditions = [
        ("indexed_coordinates", indexed_body, pairs,
         {"coordinate_rows": coordinates, "source_comment": source_xyz.splitlines()[1]},
         {"coordinate_information_equivalent": True, "task_equivalent_to_original_distance_query": True,
          "retained_source_atoms_1based": list(range(1, len(atoms) + 1)), "omitted_source_atoms_1based": [],
          "change": "Make the already implicit 1-based XYZ row indices explicit; retain every source atom and coordinate."},
         "equal_information_explicit_indexing"),
        ("coordinate_lookup", lookup_body, [target, distractor],
         {"xyz": source_xyz, "numbering": "implicit_1based_xyz_row"},
         {"coordinate_information_equivalent": True, "task_equivalent_to_original_distance_query": False,
          "retained_source_atoms_1based": list(range(1, len(atoms) + 1)), "omitted_source_atoms_1based": [],
          "change": "Keep the original full XYZ and implicit indexing; replace distance comparison with one coordinate lookup. Both answer candidates occur in that XYZ."},
         "same_information_changed_task_coordinate_lookup"),
        ("pair_coordinates", pair_body, pairs,
         {"pair_coordinate_rows": pair_rows},
         {"coordinate_information_equivalent": False, "task_equivalent_to_original_distance_query": True,
          "retained_source_atoms_1based": relevant, "omitted_source_atoms_1based": omitted,
          "change": "Filter and group only the original coordinates named by the two frozen query pairs; omit unrelated atoms, XYZ header and comment. No distances are supplied."},
         "task_relevant_coordinate_filtering_without_distance_computation"),
    ]
    probes = []
    for condition, body, options, presentation, information, distinction in conditions:
        for order, indices in (("forward", (0, 1)), ("swapped", (1, 0))):
            choices = dict(zip(("A", "B"), (options[i] for i in indices), strict=True))
            if condition == "coordinate_lookup":
                question = f"原子 {target['source_atom_1based']} ({target['element']}) 的 (x, y, z) 坐标是哪一项？"
                labels = {label: "(" + ", ".join(value["coordinate_tokens"]) + ")"
                          for label, value in choices.items()}
                expected = "A" if order == "forward" else "B"
            else:
                question = "哪一对原子的欧氏距离更短？"
                labels = {label: f"原子 {value['source_atoms_1based'][0]} 与原子 {value['source_atoms_1based'][1]}"
                          for label, value in choices.items()}
                expected = min(choices, key=lambda label: choices[label]["distance_angstrom"])
            probe = {
                "id": f"{selected['base_case_id']}/{condition}/{order}", "mainline": "A",
                "base_case_id": selected["base_case_id"], "condition": condition, "option_order": order,
                "source": selected["source"], "source_pairs": pairs,
                "prompt": body + "\n" + question + "\n"
                + "\n".join(f"{label}. {value}" for label, value in labels.items()) + "\n只回答 A 或 B。",
                "choices": choices, "expected": expected, "presentation": presentation,
                "information_change": information, "representation_vs_computation": distinction,
                "distance_values_supplied": False, "answer_source": "exact frozen source coordinate tokens; distance labels recomputed offline only",
                "study_phase": PHASE, "preregistered": False, "evaluation_scope": SCOPE,
            }
            if condition == "coordinate_lookup":
                probe.update({"lookup_target_source_atom_1based": target["source_atom_1based"],
                              "lookup_distractor_source_atom_1based": distractor["source_atom_1based"],
                              "lookup_same_element": target["element"]})
            probes.append(probe)
    return probes


def build(study_dir: Path) -> dict:
    parent_path = study_dir / "geometry_probe_provenance.json"
    original_path = study_dir / "geometry_probes.jsonl"
    parent_bytes = parent_path.read_bytes()
    parent = json.loads(parent_bytes)
    original_hash = digest(original_path)
    if original_hash != parent["output_sha256"]:
        raise ValueError("frozen_original_probe_hash_mismatch")
    probes, frozen_sources = [], []
    for selected in parent["selected"]:
        path = Path(selected["source"]["source_xyz_path"])
        payload = path.read_bytes()
        checksum = hashlib.sha256(payload).hexdigest()
        if checksum != selected["source"]["source_xyz_sha256"]:
            raise ValueError(f"frozen_source_hash_mismatch:{path}")
        frozen_sources.append({"base_case_id": selected["base_case_id"], "path": str(path), "sha256": checksum})
        probes.extend(make_controls(selected, payload.decode()))
    output = study_dir / "geometry_controls.jsonl"
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in probes))
    provenance = {
        "mainline": "A", "study_phase": PHASE, "preregistered": False, "no_llm_executed": True,
        "trigger": {"source": "parent task report, not recomputed by this generator",
                    "observation": "The initial think-disabled direct A/B run reportedly selected A in every XYZ condition, while supplied tool-distance items were correct.",
                    "purpose": "Discriminate indexing/coordinate reading from distance calculation and task-relevant information selection; not establish a general geometry deficit."},
        "selection_rule": "Reuse every selected base case and source pair from the frozen original geometry provenance, in that exact order. No new structures, replacements or outcome-based filtering.",
        "lookup_selection_rule": "Traverse source atoms in the frozen query-pair order; use the first atom with another same-element atom at different coordinates, then the first such distractor in original source row order.",
        "frozen_original_probes": {"path": str(original_path), "sha256": original_hash},
        "frozen_original_provenance": {"path": str(parent_path), "sha256": hashlib.sha256(parent_bytes).hexdigest()},
        "frozen_sources": frozen_sources, "base_case_count": len(frozen_sources),
        "condition_counts": dict(Counter(row["condition"] for row in probes)),
        "expected_counts": dict(Counter(row["expected"] for row in probes)), "total_probe_count": len(probes),
        "condition_interpretations": {
            "indexed_coordinates": "Same complete coordinates and same distance question; make implicit source row indices explicit. No coordinate values or distances added.",
            "coordinate_lookup": "Original full XYZ and implicit row numbering; different task requiring retrieval only. Correct and same-element distractor coordinate tokens both come verbatim from this structure.",
            "pair_coordinates": "Same distance question after selecting and grouping only its source atoms; full-input information is reduced. Arithmetic remains with the model; no measured/computed distances appear in the prompt.",
        },
        "answer_provenance": "Coordinate values preserve the exact lexical tokens of frozen XYZ rows. Distance answers use the same frozen atom pairs and independently recomputed Euclidean distances; these numeric labels are metadata, never prompt content.",
        "exploratory_boundary": "Designed after inspecting the initial failure pattern. These follow-up conditions and any later results are exploratory, not preregistered or confirmatory findings.",
        "scientific_boundary": "All items remain diagnostic primitives, never TS/Freq/IRC acceptance or real research-success labels. Later Qwen behavior does not explain the historical provider's hidden mechanism.",
        "output": str(output), "output_sha256": digest(output),
    }
    (study_dir / "geometry_controls_provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, default=Path("output/cloudra_model_study_20261028"))
    args = parser.parse_args()
    result = build(args.study_dir.resolve())
    print(json.dumps({key: result[key] for key in ("base_case_count", "condition_counts", "total_probe_count", "output")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
