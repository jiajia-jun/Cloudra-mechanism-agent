#!/usr/bin/env python3
"""Select requested same-backbone guided-standard contrasts; no new tests."""
from pathlib import Path

import pandas as pd


p = Path(__file__).parent
src = Path("/Users/cloudrayyy/Desktop/Cloudra实验数据/Cloudra-P2-final-20261031")
rows = []
pair = pd.read_csv(p / "pairwise.csv")
tier = pd.read_csv(p / "tier_pairwise.csv")
components = pd.read_csv(p / "component_groups.csv")
sensitivity = pd.read_csv(p / "sensitivity_subsets.csv")
per_task = pd.read_csv(p / "per_task_official.csv")


def add(row_type, label, row, extras=None):
    d = dict(row_type=row_type, label=label, arm_a="guided", arm_b="standard", track="official_repaired")
    d.update(row.to_dict() if hasattr(row, "to_dict") else row)
    if "a_mean" in d:
        d["guided_mean"] = d.pop("a_mean")
        d["baseline_mean"] = d.pop("b_mean")
    if "final_difference" in d:
        d["mean_difference"] = d.pop("final_difference")
    if extras:
        d.update(extras)
    rows.append(d)


q = "arm_a == 'guided' and arm_b == 'standard'"
all_row = pair.query(q + " and track == 'official_repaired'").iloc[0]
add("paired_final", "all", all_row)
rows[-1].update(guided_mean=float(per_task.guided.mean()), baseline_mean=float(per_task.standard.mean()))
for _, row in tier.query(q + " and track == 'official_repaired'").iterrows():
    add("paired_final", row.tier, row)
for _, row in components.query(q + " and group in ['normal', 'hard', 'normal+hard']").iterrows():
    add("publication_components", row.group, row, {"track": "complete offline publication components"})
    sub = per_task[per_task.task.isin(row.included_tasks.split("|"))]
    rows[-1].update(guided_mean=float(sub.guided.mean()), baseline_mean=float(sub.standard.mean()))
for name in ["exclude_any_standard_missing_graph", "exclude_raw_fallback_and_all_repairs"]:
    row = sensitivity.query(q + " and sensitivity == @name").iloc[0]
    add("discussion_sensitivity", name, row)
    # These subset task IDs are already documented in the analysis metadata.
    import json
    meta = json.loads((p / "metadata.json").read_text())
    dropped = set(meta["standard_missing_graph_tasks"] if name == "exclude_any_standard_missing_graph"
                  else meta["fallback_tasks"] + meta["all_repair_tasks"])
    sub = per_task[~per_task.task.isin(dropped)]
    rows[-1].update(guided_mean=float(sub.guided.mean()), baseline_mean=float(sub.standard.mean()))

# Published reconstruction provenance supplies REPAIRED components. The final CSV's
# component columns on these rows are pre-repair zeros and must not be substituted.
for task, graph, selfc, accuracy, finding in [
    ("HA1", 1.0, 0.0, 0.0,
     "Both stereochemical channels were proposed, but neither saddle converged; no barriers, IRC, endpoint verification or favored-channel conclusion could be reconstructed."),
    ("HF1", 0.799505475368673, 0.875, 0.0,
     "Both diastereofacial channels had frequency/IRC/endpoint evidence; run favored anti/trans by 0.43 kcal/mol, contrary to the reference's syn/directing-face preference."),
]:
    row = per_task[per_task.task == task].iloc[0]
    add("discussion_reconstructed_case", task,
        dict(task=task, n=1, guided_mean=row.guided, baseline_mean=row.standard,
             mean_difference=row.guided-row.standard, baseline_graph=graph,
             baseline_selfc=selfc, baseline_accuracy=accuracy, finding=finding,
             provenance=str(src / "reconstructions" / "standard" / task / "provenance.md")))

pd.DataFrame(rows).to_csv(p / "baseline_comparison.csv", index=False)
print(pd.DataFrame(rows).to_string(index=False))
