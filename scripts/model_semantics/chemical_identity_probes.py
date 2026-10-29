#!/usr/bin/env python3
"""Freeze small chemical-identity controls; never call a model or edit evidence.

The label convention is RDKit canonical isomeric SMILES after removing atom
maps. It is a representation-reading task, not a mechanism or acceptance test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from rdkit import Chem, rdBase
from rdkit.Chem import rdMolDescriptors

SEED = 42
TASKS = {"E1", "NB1", "HA1", "IA1"}


def molecule(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid selected SMILES: {smiles}")
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return mol


def identity(smiles: str) -> str:
    return Chem.MolToSmiles(molecule(smiles), canonical=True, isomericSmiles=True)


def rewrite(smiles: str) -> str:
    """Change only the right operand's spelling, using a fixed RDKit seed."""
    candidates = Chem.MolToRandomSmilesVect(
        molecule(smiles), 64, randomSeed=SEED, isomericSmiles=True,
    )
    # RDKit preserves component order even when each component is symmetric.
    candidates = [".".join(reversed(value.split("."))) for value in candidates]
    rewritten = next(value for value in candidates if value != smiles)
    if identity(rewritten) != identity(smiles):
        raise ValueError("Random rewrite changed the represented identity")
    return rewritten


def source_event(database: Path, row: sqlite3.Row) -> dict:
    return {
        "database": str(database), "sqlite_open_mode": "ro&immutable=1",
        **{key: row[key] for key in ("event_id", "project_id", "type", "created_at")},
        "data_sha256": hashlib.sha256(row["data"].encode()).hexdigest(),
        "data": json.loads(row["data"]),
    }


def load_sources(study_dir: Path) -> dict:
    index = study_dir / "formal_cases.jsonl"
    projects = set()
    for line in index.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        if case["task"] in TASKS:
            projects.add((case["task"], case["source_database"], case["project_id"]))
    sources = {}
    for task, path, project in sorted(projects):
        if task in sources:
            continue
        database = Path(path).resolve()
        with sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT event_id,project_id,type,created_at,data FROM events "
                "WHERE project_id=? AND type='agent.message_injected' ORDER BY rowid", (project,),
            )
            for row in rows:
                data = json.loads(row["data"])
                if data.get("sender") == "user" and "Reactant SMILES: " in data.get("content", ""):
                    content = data["content"]
                    reactant = content.split("Reactant SMILES: ", 1)[1].split(";", 1)[0]
                    product = content.split("product SMILES: ", 1)[1].split(";", 1)[0]
                    sources[task] = {
                        "reactant": reactant, "product": product,
                        "task_event": source_event(database, row),
                    }
                    break
            if task == "HA1":
                rows = connection.execute(
                    "SELECT event_id,project_id,type,created_at,data FROM events "
                    "WHERE project_id=? AND type='tool.requested' ORDER BY rowid", (project,),
                )
                for row in rows:
                    data = json.loads(row["data"])
                    if data.get("tool_name") != "dag_propose_mechanism":
                        continue
                    species = data.get("arguments_summary", {}).get("species", [])
                    named = {item.get("name"): item.get("smiles") for item in species}
                    if named.get("P_E") and named.get("P_Z"):
                        sources[task].update({
                            "E": named["P_E"], "Z": named["P_Z"],
                            "stereo_declaration_event": source_event(database, row),
                        })
                        break
    if set(sources) != TASKS or not {"E", "Z"} <= sources["HA1"].keys():
        raise ValueError("Selected formal task/stereochemical declarations are missing")
    return sources


def selected_pairs(sources: dict) -> list[dict]:
    def source(task, field):
        return {"task": task, "field": field, "smiles": sources[task][field],
                "origin": "formal_task" if field in {"reactant", "product"} else "formal_model_declaration"}

    def synthetic(task, parent, smiles, operation):
        return {"task": task, "field": None, "smiles": smiles, "origin": "synthetic_control",
                "parent_field": parent, "operation": operation}

    pairs = []
    for task, field in (
        ("E1", "reactant"), ("E1", "product"), ("NB1", "reactant"), ("NB1", "product"),
        ("HA1", "reactant"), ("HA1", "E"), ("HA1", "Z"), ("IA1", "reactant"),
    ):
        operand = source(task, field)
        pairs.append({"left": operand, "right": operand.copy(), "change_type": "same_identity"})
    for task in ("E1", "NB1", "HA1"):
        pairs.append({"left": source(task, "reactant"), "right": source(task, "product"),
                      "change_type": "same_formula_connectivity_and_charge_relocation"
                      if task == "E1" else "same_formula_connectivity"})
    pairs.append({"left": source("HA1", "E"), "right": source("HA1", "Z"),
                  "change_type": "specified_double_bond_stereochemistry"})
    for task, smiles, operation, change_type in (
        ("NB1", "COC(=O)C(=O)O", "Replace malonic-acid connectivity by monomethyl-oxalate connectivity; retain formula.",
         "same_formula_connectivity"),
        ("HA1", "C=C1CCC1", "Replace methylcyclobutene by methylenecyclobutane connectivity; retain formula.",
         "same_formula_connectivity"),
        ("IA1", "C#CC=C", "Replace the four-membered ring by an acyclic enyne; retain formula.",
         "same_formula_connectivity"),
        ("NB1", "O=C([O-])CC(=O)O", "Remove one acidic hydrogen and set its oxygen formal charge to -1.",
         "protonation_and_formal_charge"),
    ):
        pairs.append({"left": source(task, "reactant"),
                      "right": synthetic(task, "reactant", smiles, operation), "change_type": change_type})
    return pairs


def build(study_dir: Path, output_dir: Path) -> dict:
    sources = load_sources(study_dir)
    pairs = selected_pairs(sources)
    probes = []
    for index, pair in enumerate(pairs, 1):
        pair["base_case_id"] = f"chemical_identity_{index:02d}"
        left, right = pair["left"]["smiles"], pair["right"]["smiles"]
        same = identity(left) == identity(right)
        if same != (pair["change_type"] == "same_identity"):
            raise ValueError("Selected pair disagrees with intended identity relation")
        pair["same_identity"] = same
        pair["canonical_identities"] = [identity(left), identity(right)]
        pair["molecular_formulas"] = [rdMolDescriptors.CalcMolFormula(molecule(value)) for value in (left, right)]
        pair["formal_charges"] = [Chem.GetFormalCharge(molecule(value)) for value in (left, right)]
        if pair["change_type"] in {"same_formula_connectivity", "same_formula_connectivity_and_charge_relocation"} and len(set(pair["molecular_formulas"])) != 1:
            raise ValueError("A same-formula connectivity control changed formula")
        pair["right_equivalent_rewrite"] = rewrite(right)
        pair["rewrite_seed"] = SEED
        for representation, right_value in (("literal", right), ("equivalent_rewrite", pair["right_equivalent_rewrite"])):
            for order, options in (("forward", ("Same represented chemical identity", "Different represented chemical identities")),
                                   ("swapped", ("Different represented chemical identities", "Same represented chemical identity"))):
                prompt = (
                    "Compare the chemical identities represented by these two SMILES. Atom traversal order, "
                    "ring digits and disconnected-component order are notation. Preserve connectivity, bond "
                    "orders, formal charges and specified stereochemistry. No inference about reaction "
                    "feasibility, energy, geometry or spin state is requested.\n"
                    f"SMILES 1: {left}\nSMILES 2: {right_value}\n"
                    f"A: {options[0]}\nB: {options[1]}\nReply with A or B only."
                )
                probes.append({
                    "id": f"{pair['base_case_id']}/{representation}/{order}",
                    "base_case_id": pair["base_case_id"],
                    "mainline": "chemical_identity/" + pair["change_type"],
                    "condition": representation + "/" + order, "prompt": prompt,
                    "expected": "A" if same == (order == "forward") else "B",
                })
    if len(probes) != 64 or len({row["id"] for row in probes}) != 64:
        raise ValueError("The frozen control set must contain exactly 64 unique inputs")
    if Counter(row["expected"] for row in probes) != {"A": 32, "B": 32}:
        raise ValueError("Option-swapping must balance both answer letters")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "chemical_identity_probes.jsonl"
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in probes), encoding="utf-8")
    provenance = {
        "scope": "Exploratory local identity-reading controls, not formal-run outcomes or a chemistry-success benchmark.",
        "no_model_executed": True, "rdkit_version": rdBase.rdkitVersion,
        "label_generator": "MolFromSmiles -> clear atom-map numbers -> MolToSmiles(canonical=True,isomericSmiles=True)",
        "randomization": "MolToRandomSmilesVect(...,64,randomSeed=42,isomericSmiles=True), then reverse dot-component order; first nonidentical string; canonical equality checked.",
        "representation_control": "Only SMILES 2 changes spelling; SMILES 1, instructions, option order and expected identity remain fixed.",
        "option_control": "Each literal and rewritten pair occurs with forward and swapped option meanings; labels stay outside prompt context.",
        "selection": "Eight same-identity pairs and eight changed-identity pairs. Four changed pairs are formal declarations; four are explicitly synthetic. Seven of eight changed pairs retain molecular formula, including HA1 E/Z. E1 combines connectivity changes with negative-charge relocation from F to Cl and is a separate mixed-change stratum, not a connectivity-only control.",
        "semantic_limits": [
            "Identity is equality under this RDKit representation convention, not reaction understanding or physical feasibility.",
            "Atom-map correspondence, conformation, geometry, energy, TS character and spin multiplicity are outside the label.",
            "IA1 automerized geometries can share this identity; a correct identity answer cannot resolve their geometry or scientific validity.",
            "Specified stereochemistry, formal charge and isotope labels are retained; tautomers/protonation states are not normalized together.",
            "Formal model declarations supply SMILES only; their names, mechanism reasoning and claims of scientific success are not labels.",
            "Random rewrites are reproducible for the recorded RDKit version; cross-version text identity is not promised.",
        ],
        "base_pair_count": len(pairs), "probe_count": len(probes),
        "change_type_counts": dict(Counter(pair["change_type"] for pair in pairs)),
        "expected_counts": dict(Counter(row["expected"] for row in probes)),
        "index": str((study_dir / "formal_cases.jsonl").resolve()),
        "index_sha256": hashlib.sha256((study_dir / "formal_cases.jsonl").read_bytes()).hexdigest(),
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "task_sources": sources, "pairs": pairs,
        "output": str(output.resolve()), "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    (output_dir / "chemical_identity_provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return {key: provenance[key] for key in ("base_pair_count", "probe_count", "change_type_counts", "rdkit_version", "output", "output_sha256")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, default=Path("output/cloudra_model_study_20261028"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or args.study_dir / "chemical_identity_controls"
    print(json.dumps(build(args.study_dir, output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
