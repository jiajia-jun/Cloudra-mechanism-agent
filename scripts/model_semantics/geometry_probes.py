#!/usr/bin/env python3
"""Build geometry diagnostic primitives from read-only original P1b evidence.

No LLM calls or scientific-success labels are produced. The seed is prescribed;
additional structures follow database path / SQLite rowid order, never answers.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sqlite3
import tarfile
from pathlib import Path, PurePosixPath

SEED_EVENT = "evt_9964bbb2ba494123"
SCOPE = "diagnostic_primitive_not_scientific_success"
ROTATION = ((36 / 65, -48 / 65, 5 / 13), (4 / 5, 3 / 5, 0), (-3 / 13, 4 / 13, 12 / 13))
TRANSLATION = (2.75, -1.25, 0.5)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_xyz(text: str) -> list[tuple[str, tuple[float, ...]]]:
    lines = text.splitlines()
    count = int(lines[0].strip())
    rows = [line.split() for line in lines[2:] if line.strip()]
    if count < 2 or len(rows) != count or any(len(row) != 4 for row in rows):
        raise ValueError("invalid_xyz_atom_rows")
    atoms = [(row[0], tuple(float(x) for x in row[1:])) for row in rows]
    if any(not math.isfinite(x) for _, xyz in atoms for x in xyz):
        raise ValueError("nonfinite_xyz_coordinate")
    return atoms


def format_xyz(atoms: list, comment: str) -> str:
    return f"{len(atoms)}\n{comment}\n" + "".join(
        f"{symbol} " + " ".join(f"{x:.12f}" for x in xyz) + "\n" for symbol, xyz in atoms
    )


def checked_pairs(atoms: list, watch_pairs: list, report: str) -> list[dict]:
    block = report.partition("[Watched atom pairs]")[2]
    reported = {}
    for line in block.splitlines():
        token = line.strip()
        if token.startswith("==") or token.startswith("[Reactive-center atoms]"):
            break
        if token.startswith("r("):
            label, separator, tail = token[2:].partition(")=")
            if separator:
                reported[label] = tail.split()[0]
    pairs = []
    for raw_pair in watch_pairs:
        a, b = raw_pair
        if not 1 <= a <= len(atoms) or not 1 <= b <= len(atoms) or a == b:
            raise ValueError("invalid_source_atom_pair")
        labels = [f"{atoms[i - 1][0]}{i}" for i in (a, b)]
        value = reported.get("-".join(labels), reported.get("-".join(reversed(labels))))
        if value is None:
            raise ValueError(f"reported_pair_missing:{labels}")
        distance = math.dist(atoms[a - 1][1], atoms[b - 1][1])
        if f"{distance:.3f}" != value:
            raise ValueError(f"report_distance_mismatch:{labels}:{distance:.12f}:{value}")
        pairs.append({"source_atoms_1based": [a, b], "source_atom_labels": labels,
                      "distance_angstrom": distance, "reported_angstrom": value})
    return pairs


def make_geometry_probes(candidate: dict, source_xyz: str) -> list[dict]:
    atoms = parse_xyz(source_xyz)
    verified = checked_pairs(atoms, candidate["watch_pairs"], candidate["report"])
    pair_pair = next((pair for pair in itertools.combinations(verified, 2)
                      if pair[0]["reported_angstrom"] != pair[1]["reported_angstrom"]), None)
    if pair_pair is None:
        raise ValueError("no_distinct_reported_pair_distances")
    source_pairs = list(pair_pair)
    source_comment = source_xyz.splitlines()[1]
    transformed = [(symbol, tuple(sum(r * x for r, x in zip(row, xyz, strict=True)) + shift
                                 for row, shift in zip(ROTATION, TRANSLATION, strict=True)))
                   for symbol, xyz in atoms]
    identity = {str(i): i for i in range(1, len(atoms) + 1)}
    reversed_map = {str(i): len(atoms) + 1 - i for i in range(1, len(atoms) + 1)}
    presentations = {
        "original_xyz": {"xyz": source_xyz, "source_to_presented_1based": identity},
        "rotated_translated_xyz": {
            "xyz": format_xyz(transformed, source_comment),
            "source_to_presented_1based": identity, "rotation": ROTATION, "translation_angstrom": TRANSLATION,
        },
        "reordered_xyz": {"xyz": format_xyz(list(reversed(atoms)), source_comment),
                          "source_to_presented_1based": reversed_map},
        "tool_distances": {"distances_angstrom": [p["reported_angstrom"] for p in source_pairs]},
    }
    # This is a numerical serialization check, not a scientific geometry threshold.
    for presentation in presentations.values():
        if "xyz" not in presentation:
            continue
        current = parse_xyz(presentation["xyz"])
        mapping = presentation["source_to_presented_1based"]
        for a, b in itertools.combinations(range(1, len(atoms) + 1), 2):
            original = math.dist(atoms[a - 1][1], atoms[b - 1][1])
            changed = math.dist(current[mapping[str(a)] - 1][1], current[mapping[str(b)] - 1][1])
            if not math.isclose(original, changed, rel_tol=0, abs_tol=1e-9):
                raise ValueError("transformed_geometry_distance_changed")
    probes = []
    for condition, presentation in presentations.items():
        mapping = presentation.get("source_to_presented_1based", identity)
        options = [{**pair, "presented_atoms_1based": [mapping[str(i)] for i in pair["source_atoms_1based"]]}
                   for pair in source_pairs]
        for order, indices in (("forward", (0, 1)), ("swapped", (1, 0))):
            choices = dict(zip(("A", "B"), (options[i] for i in indices), strict=True))
            expected = min(choices, key=lambda label: choices[label]["distance_angstrom"])
            if condition == "tool_distances":
                body = "工具测得以下距离（Å）：\n" + "\n".join(
                    f"r({'-'.join(pair['source_atom_labels'])}) = {pair['reported_angstrom']}"
                    for pair in source_pairs
                )
            else:
                body = "下面是 XYZ 坐标，坐标单位 Å，原子编号从 1 开始，按行计数：\n" + presentation["xyz"]
            labels = {}
            for label, choice in choices.items():
                a, b = choice["presented_atoms_1based"]
                labels[label] = f"原子 {a} 与原子 {b}"
            prompt = body + "\n哪一对原子的欧氏距离更短？\n" + "\n".join(
                f"{label}. {value}" for label, value in labels.items()
            ) + "\n只回答 A 或 B。"
            probes.append({
                "id": f"{candidate['base_case_id']}/{condition}/{order}", "mainline": "A",
                "base_case_id": candidate["base_case_id"], "condition": condition, "option_order": order,
                "source": candidate["source"], "prompt": prompt, "expected": expected,
                "choices": choices, "source_pairs": source_pairs, "presentation": presentation,
                "representation_vs_computation": "outsourced_computation" if condition == "tool_distances"
                else "geometry_preserving_representation",
                "evaluation_scope": SCOPE,
            })
    return probes


def copy_archive_members(archive: Path, members: set[str], destination: Path) -> dict[str, Path]:
    for name in members:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe_requested_member:{name}")
    copied = {}
    with tarfile.open(archive, "r|gz") as tf:
        for member in tf:
            if member.name not in members or not member.isfile():
                continue
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with tf.extractfile(member) as source:
                target.write_bytes(source.read())
            copied[member.name] = target
    return copied


def collect_candidates(source_root: Path, project_map: list[dict]) -> tuple[list[dict], list[dict]]:
    projects = {row["project_id"]: row for row in project_map}
    candidates, excluded = [], []
    for database in sorted(source_root.glob("*/r*/runtime/runtime-v2.db")):
        relative = database.relative_to(source_root).as_posix()
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            requests = {row["event_id"]: json.loads(row["data"]) for row in connection.execute(
                "SELECT event_id,data FROM events WHERE type='tool.requested'"
            )}
            rows = connection.execute(
                "SELECT rowid AS source_rowid,event_id,project_id,data,created_at FROM events "
                "WHERE type='tool.result_recorded' ORDER BY rowid"
            )
            for row in rows:
                data = json.loads(row["data"])
                if data.get("tool_name") != "internal_coordinates":
                    continue
                request_id = data.get("request_event_id")
                arguments = requests.get(request_id, {}).get("arguments_summary", {})
                if arguments.get("mode") != "analyze" or len(arguments.get("watch_pairs", [])) < 2:
                    continue
                source = {"database": str(database), "database_relative": relative,
                          "event_id": row["event_id"], "source_rowid": row["source_rowid"],
                          "request_event_id": request_id, "created_at": row["created_at"],
                          "project_id": row["project_id"], "input_path": arguments.get("input_path")}
                project = projects.get(row["project_id"])
                path = PurePosixPath(arguments.get("input_path") or "")
                reason = None
                if project is None:
                    reason = "project_workspace_mapping_missing"
                elif path.suffix.lower() != ".xyz":
                    reason = "input_is_not_xyz"
                elif ".." in path.parts or arguments.get("operations"):
                    reason = "input_path_or_operations_not_plain_source_xyz"
                if reason:
                    excluded.append({"source": source, "reason": reason})
                    continue
                if path.is_absolute():
                    try:
                        path = path.relative_to(PurePosixPath(project["original_workspace"]))
                    except ValueError:
                        excluded.append({"source": source, "reason": "input_outside_mapped_workspace"})
                        continue
                source.update({key: project[key] for key in ("arm", "round", "task", "original_workspace")})
                source["archive_member"] = str(PurePosixPath(project["archive_sandbox_prefix"]) / path)
                payload = data.get("result", {}).get("data") or {}
                candidates.append({"base_case_id": f"geometry/{project['arm']}/{project['round']}/{row['event_id']}",
                                   "source": source, "watch_pairs": arguments["watch_pairs"],
                                   "report": payload.get("report", "")})
    seed = [c for c in candidates if c["source"]["event_id"] == SEED_EVENT]
    if len(seed) != 1:
        raise ValueError("prescribed_seed_not_uniquely_available")
    return seed + [c for c in candidates if c["source"]["event_id"] != SEED_EVENT], excluded


def ha1_source(source_root: Path, project_map: list[dict]) -> dict:
    project = next(p for p in project_map if p["arm"] == "guided" and p["round"] == "r1" and p["task"] == "HA1")
    database = source_root / "guided/r1/runtime/runtime-v2.db"
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
        for rowid, event_id, event_type, raw in connection.execute(
            "SELECT rowid,event_id,type,data FROM events WHERE project_id=? ORDER BY rowid", (project["project_id"],)
        ):
            data = json.loads(raw)
            content = data.get("content")
            if data.get("sender") == "user" and isinstance(content, str) and "product SMILES: " in content:
                name = content.partition("Determine the mechanism of the following reaction: ")[2]
                name = name.partition(". Reactant SMILES: ")[0]
                target = content.partition("product SMILES: ")[2].partition(";")[0].strip()
                if not name or not target:
                    raise ValueError("HA1_source_name_or_target_missing")
                return {"name": name, "product_smiles": target,
                        "source": {"database": str(database), "event_id": event_id, "source_rowid": rowid,
                                   "event_type": event_type, "task": "HA1", "project_id": project["project_id"],
                                   "content_sha256": hashlib.sha256(content.encode()).hexdigest()}}
    raise ValueError("HA1_original_user_task_not_found")


def make_ha1_probes(source: dict) -> list[dict]:
    from rdkit import Chem

    molecule = Chem.MolFromSmiles(source["product_smiles"])
    if molecule is None:
        raise ValueError("invalid_HA1_source_SMILES")
    carbon_count = sum(atom.GetAtomicNum() == 6 for atom in molecule.GetAtoms())
    if "3-methylcyclobutene" not in source["name"]:
        raise ValueError("HA1_source_name_changed_requires_review")
    questions = [
        ("target_carbon_count", f"源任务目标 SMILES：{source['product_smiles']}\n该 SMILES 含有几个碳原子？",
         [carbon_count, carbon_count - 1]),
        ("source_name_description", f"源任务名称：{source['name']}\n哪一项与源名称中的取代描述相符？",
         ["含甲基取代", "未提及甲基取代"]),
    ]
    probes = []
    for kind, question, values in questions:
        for order, indices in (("forward", (0, 1)), ("swapped", (1, 0))):
            choices = dict(zip(("A", "B"), (values[i] for i in indices), strict=True))
            probes.append({
                "id": f"chemistry/HA1/{kind}/{order}", "base_case_id": f"chemistry/HA1/{kind}",
                "mainline": "A", "condition": kind, "option_order": order, "source": source["source"],
                "source_name": source["name"], "source_product_smiles": source["product_smiles"],
                "prompt": question + "\n" + "\n".join(f"{label}. {value}" for label, value in choices.items())
                + "\n只回答 A 或 B。", "choices": choices, "expected": "A" if order == "forward" else "B",
                "representation_vs_computation": "source_object_reading_control", "evaluation_scope": SCOPE,
                "interpretation": "仅标签源字符串碳数或名称描述，不标签机理、立体结果、TS 或研究成功。",
            })
    return probes


def build(study_dir: Path) -> dict:
    trace_path = study_dir / "system_trace.json"
    index_path = study_dir / "formal48/member_index.json"
    trace = json.loads(trace_path.read_text())["formal_dataset"]
    source_root = study_dir / "formal48/archive_metadata/cloudra-p1b-20261024"
    index = {row["path"]: row for row in json.loads(index_path.read_text())}
    candidates, excluded = collect_candidates(source_root, trace["project_task_map"])
    wanted = {c["source"]["archive_member"] for c in candidates if c["source"]["archive_member"] in index}
    archive = Path(trace["archive"])
    copied = copy_archive_members(archive, wanted, study_dir / "geometry_source_files")
    probes, selected, used_members = [], [], set()
    for candidate in candidates:
        member = candidate["source"]["archive_member"]
        if member in used_members:
            excluded.append({"source": candidate["source"], "reason": "duplicate_source_structure_member"})
            continue
        path = copied.get(member)
        if path is None:
            excluded.append({"source": candidate["source"], "reason": "source_member_unavailable"})
            continue
        candidate["source"].update({"source_xyz_path": str(path), "source_xyz_sha256": digest(path),
                                     "archive_member_bytes": index[member]["bytes"]})
        try:
            generated = make_geometry_probes(candidate, path.read_text())
        except (ValueError, IndexError) as error:
            excluded.append({"source": candidate["source"], "reason": str(error)})
            continue
        probes.extend(generated)
        selected.append({"base_case_id": candidate["base_case_id"], "source": candidate["source"],
                         "watch_pairs": candidate["watch_pairs"], "source_pairs": generated[0]["source_pairs"],
                         "report_sha256": hashlib.sha256(candidate["report"].encode()).hexdigest(),
                         "report_rounding_check": "all requested watch pairs match XYZ rounded to 3 decimals"})
        used_members.add(member)
        if sum(row["source"]["event_id"] != SEED_EVENT for row in selected) == 3:
            break
    chemistry = ha1_source(source_root, trace["project_task_map"])
    probes.extend(make_ha1_probes(chemistry))
    output = study_dir / "geometry_probes.jsonl"
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in probes))
    provenance = {
        "evaluation_scope": SCOPE, "no_llm_executed": True, "mainline": "A", "archive": str(archive),
        "archive_bytes": archive.stat().st_size, "member_index_sha256": digest(index_path),
        "system_trace_sha256": digest(trace_path), "prescribed_seed_event_id": SEED_EVENT,
        "prescribed_seed_status": "included" if any(row["source"]["event_id"] == SEED_EVENT for row in selected) else "excluded",
        "selection_rule": "Prescribed seed first; then lexical relative database path, then SQLite source rowid; first 3 additional distinct available XYZ members with >=2 watch_pairs and every report distance verified; no model outcome consulted.",
        "pair_selection_rule": "First combination of requested watch_pairs in source order whose reported 3-decimal distances differ; options always emitted both forward and swapped.",
        "coordinate_serialization_tolerance_angstrom": 1e-9,
        "tolerance_scope": "Floating point/12-decimal serialization invariance only; not a chemical or scientific acceptance threshold.",
        "rotation": ROTATION, "translation_angstrom": TRANSLATION, "atom_permutation": "reverse source row order, with every query index remapped",
        "conditions": {"original_xyz": "archived source coordinates",
                       "rotated_translated_xyz": "same geometry, proper rotation determinant +1 and translation",
                       "reordered_xyz": "same geometry, atom rows reordered and query indices synchronized",
                       "tool_distances": "historically reported measured distances; outsourced computation, not pure format equivalence"},
        "selected": selected, "excluded": excluded, "candidate_count": len(candidates),
        "copied_member_count": len(copied), "geometry_base_cases": len(selected),
        "geometry_probe_count": 8 * len(selected), "chemistry_probe_count": 4, "total_probe_count": len(probes),
        "ha1_source": chemistry, "output": str(output), "output_sha256": digest(output),
        "historical_provider_boundary": "Later Qwen probes cannot explain the unavailable internal activations or immutable backend revision of the historical actual provider.",
        "scientific_boundary": "No TS, frequency, IRC, mechanism, scientific acceptance, or real research success is labeled by these primitives.",
    }
    (study_dir / "geometry_probe_provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, default=Path("output/cloudra_model_study_20261028"))
    arguments = parser.parse_args()
    result = build(arguments.study_dir.resolve())
    print(json.dumps({key: result[key] for key in ("geometry_base_cases", "geometry_probe_count", "chemistry_probe_count", "total_probe_count", "output")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
