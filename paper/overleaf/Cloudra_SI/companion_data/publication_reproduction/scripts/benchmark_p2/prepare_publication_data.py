"""Assemble the final evaluation results and their recorded score components."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "paper/figures/benchmark_p2_20261031/source_data"
OUT = SRC
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--postprocess-overlay", type=Path)
args = parser.parse_args()
r = pd.read_csv(SRC / "source_final_scores_per_run.csv")
raw = pd.read_csv(SRC / "raw_scores_p2.csv")
r["score"] = r.repaired_final.fillna(r.fair_final)
for col in ["graph", "selfc_all", "accuracy"]:
    r[col + "_publication"] = r[col]
r["component_source"] = "final offline score table"
links = []
for i, row in r.iterrows():
    if "fair=raw" in row["flags"]:
        batch = {"cloudra-p2c-20261025": "P2c", "cloudra-p2b-20261025": "P2b"}[row.campaign]
        matches = raw[(raw.arm == row.arm) & (raw.task_id == row.task) & (raw.batch == batch)]
        assert len(matches) == 1, (row.arm, row.task)
        z = matches.iloc[0]
        assert abs(z["final"] - row.score) < 1e-9
        vals = {"graph": z.graph, "selfc_all": z.selfconsistency, "accuracy": z.accuracy}
        for col, val in vals.items():
            r.loc[i, col + "_publication"] = val
        r.loc[i, "component_source"] = "original score components retained by offline protocol"
        links.append(
            {
                "arm": row.arm,
                "task": row.task,
                "source": "runs/raw_scores_p2.csv",
                "source_line": int(matches.index[0]) + 2,
                "values": vals,
            }
        )
    if row.arm == "standard" and pd.notna(row.repaired_final):
        rel = Path("reconstructions/standard") / row.task / "provenance.md"
        lines = (SRC / rel).read_text().splitlines()
        matches = [(j + 1, line) for j, line in enumerate(lines) if line.strip().startswith("- Component scores:")]
        assert len(matches) == 1, (row.task, matches)
        ln, line = matches[0]
        parts = line.split("Component scores:", 1)[1].split(",")[:3]
        vals = {}
        names = {"graph": "graph", "self-consistency": "selfc_all", "accuracy": "accuracy"}
        for part in parts:
            key, val = part.split("=", 1)
            vals[names[key.strip()]] = float(val.strip())
        assert len(vals) == 3
        for col, val in vals.items():
            r.loc[i, col + "_publication"] = val
        r.loc[i, "component_source"] = "offline graph organization score record"
        links.append({"arm": row.arm, "task": row.task, "source": str(rel), "source_line": ln, "values": vals})
        dest = OUT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
overlay_path = args.postprocess_overlay or SRC / "target_matching_accuracy_corrections.csv"
overlay_provenance = None
if args.postprocess_overlay is not None or overlay_path.is_file():
    corrections = pd.read_csv(overlay_path)
    assert not corrections.duplicated(["arm", "task"]).any(), "duplicate postprocessing run"
    applied = []
    for _, correction in corrections.iterrows():
        matches = r.index[(r.arm == correction.arm) & (r.task == correction.task)]
        assert len(matches) == 1, (correction.arm, correction.task)
        index = matches[0]
        applied.append(
            {
                **correction.to_dict(),
                "previous_accuracy": float(r.loc[index, "accuracy_publication"]),
                "previous_score": float(r.loc[index, "score"]),
                "retained_component_source": r.loc[index, "component_source"],
            }
        )
        r.loc[index, "accuracy_publication"] = float(correction.accuracy)
        r.loc[index, "score"] = float(correction.score)
        r.loc[index, "component_source"] += "; Accuracy: target-identity postprocessing"
    overlay_provenance = {
        "file": overlay_path.name,
        "sha256": hashlib.sha256(overlay_path.read_bytes()).hexdigest(),
        "scope": "Accuracy and composite corrected; recorded Graph and SC retained.",
        "applied_rows": applied,
    }
assert r[["graph_publication", "selfc_all_publication", "accuracy_publication"]].notna().all().all()
r["recomputed_publication"] = 0.1 * r.graph_publication + 0.3 * r.selfc_all_publication + 0.6 * r.accuracy_publication
r["rounding_difference"] = r.recomputed_publication - r.score
assert r.rounding_difference.abs().max() < 0.000051, r.loc[
    r.rounding_difference.abs().gt(0.000051), ["arm", "task", "rounding_difference"]
]
r.to_csv(OUT / "publication_scores_per_run.csv", index=False)
(OUT / "component_provenance.json").write_text(
    json.dumps(
        {
            "n": 200,
            "recovered_rows": links,
            "max_rounding_difference": r.rounding_difference.abs().max(),
            "rule": "Final evaluation totals aligned with their recorded component scores; preparation does not infer or overwrite run conclusions.",
            "postprocess_overlay": overlay_provenance,
        },
        ensure_ascii=False,
        indent=2,
    )
)
groups = []
for a, b in [("guided", "standard"), ("guided", "record"), ("guided", "brief-errors"), ("brief-errors", "guided")]:
    for group, tiers in [
        ("all", None),
        ("easy", ["easy"]),
        ("normal", ["normal"]),
        ("hard", ["hard"]),
        ("impossible", ["impossible"]),
        ("normal+hard", ["normal", "hard"]),
    ]:
        rr = r if tiers is None else r[r.tier.isin(tiers)]
        p = rr.pivot(
            index="task",
            columns="arm",
            values=["score", "graph_publication", "selfc_all_publication", "accuracy_publication"],
        )
        record = {
            "arm_a": a,
            "arm_b": b,
            "group": group,
            "n": len(p),
            "final_difference": (p["score"][a] - p["score"][b]).mean(),
        }
        for name, field, w in [
            ("graph", "graph_publication", 0.1),
            ("selfc", "selfc_all_publication", 0.3),
            ("accuracy", "accuracy_publication", 0.6),
        ]:
            record[name + "_contribution"] = float(((p[field][a] - p[field][b]) * w).mean())
        groups.append(record)
pd.DataFrame(groups).to_csv(OUT / "publication_component_groups.csv", index=False)
summary = []
for arm, rr in r.groupby("arm"):
    for group, gg in [("all", rr), ("non-impossible", rr[rr.tier.ne("impossible")])]:
        v = gg.selfc_all_publication
        summary.append(
            {
                "arm": arm,
                "scope": group,
                "n": len(gg),
                "sc_full": int(np.isclose(v, 1, rtol=0, atol=1e-10).sum()),
                "sc_zero": int(np.isclose(v, 0, rtol=0, atol=1e-10).sum()),
                "sc_partial": int(((v > 1e-10) & (v < 1 - 1e-10)).sum()),
                "sc_mean": v.mean(),
                "graph_mean": gg.graph_publication.mean(),
                "accuracy_mean": gg.accuracy_publication.mean(),
            }
        )
pd.DataFrame(summary).to_csv(OUT / "publication_component_summary.csv", index=False)
print(pd.DataFrame(groups).query("arm_a=='guided' and arm_b=='standard'").to_string(index=False))
print(pd.DataFrame(summary).to_string(index=False))
