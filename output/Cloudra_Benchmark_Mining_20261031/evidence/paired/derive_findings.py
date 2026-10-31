#!/usr/bin/env python3
"""Derive useful descriptive contrasts from analyze_paired.py outputs."""
import json
from pathlib import Path

import numpy as np
import pandas as pd


p = Path(__file__).parent
d = pd.read_csv(p / "per_task_official.csv")
arms = ["guided", "record", "standard", "brief-errors"]
missing = ["F1", "HA1", "HF1", "IA9", "M17", "NR1", "P3"]
mask = d.task.isin(missing)
components = pd.read_csv(p / "component_groups.csv")
nh = components.query("arm_a == 'guided' and arm_b == 'record' and group == 'normal+hard'").iloc[0]
gmr = d.guided - d.record
easy = d.tier == "easy"
f4g2 = d.task.isin(["F4", "G2"])
best = d[arms].max(axis=1)
summary = {
    "standard_missing_graph_concentration": {
        "repaired_mean_on_seven": float(d.loc[mask, "standard"].mean()),
        "guided_net_gap_share_from_seven": float((d.guided-d.standard)[mask].sum()/(d.guided-d.standard).sum()),
        "record_net_gap_share_from_seven": float((d.record-d.standard)[mask].sum()/(d.record-d.standard).sum()),
        "guided_mean_on_same_seven": float(d.loc[mask, "guided"].mean()),
        "record_mean_on_same_seven": float(d.loc[mask, "record"].mean()),
    },
    "guided_record_tier_concentration": {
        "impossible_share_of_net_gap": float(gmr[d.tier == "impossible"].sum()/gmr.sum()),
        "easy_net_deficit_share_from_F4_G2": float(gmr[f4g2].sum()/gmr[easy].sum()),
        "normal_hard_all_20_mean_difference": float(gmr[d.tier.isin(["normal", "hard"])].mean()),
        "normal_hard_component_shares": {name: float(nh[f"{name}_contribution"]/nh.final_difference) for name in ["graph", "selfc", "accuracy"]},
    },
    "hindsight_routing": {
        "all_four_max_score_mean": float(best.mean()),
        "guided_brief_max_score_mean": float(d[["guided", "brief-errors"]].max(axis=1).mean()),
        "all_four_gain_over_guided": float((best-d.guided).mean()),
        "guided_brief_share_of_all_four_gain": float((d[["guided", "brief-errors"]].max(axis=1)-d.guided).sum()/(best-d.guided).sum()),
        "best_arm_by_tier_hindsight_mean": float(d.groupby("tier")[arms].mean().max(axis=1).mul(d.tier.value_counts()).sum()/50),
        "best_arm_by_tier": d.groupby("tier")[arms].mean().idxmax(axis=1).to_dict(),
        "all_four_max_score_ge_point9_count": int((best >= .9).sum()),
        "all_four_max_score_below_point9_tasks": d.loc[best < .9, "task"].to_list(),
        "best_or_tied_best_count": {arm: int((d[arm] == best).sum()) for arm in arms},
        "unique_best_count": {arm: int(((d[arm] == best) & d[arms].eq(best,axis=0).sum(axis=1).eq(1)).sum()) for arm in arms},
        "warning": "Descriptive hindsight ceiling with observed runs; not deployable router gains; no cost or scientific-success interpretation.",
    },
}
(p / "derived_findings.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print(json.dumps(summary, ensure_ascii=False, indent=2))
