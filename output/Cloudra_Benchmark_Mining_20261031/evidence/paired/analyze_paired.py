#!/usr/bin/env python3
"""Read-only P2 paired analysis. Run with Python + NumPy/Pandas/SciPy.

Source artifacts remain untouched. 'Official/repaired' follows final README:
nonempty repaired_final overrides fair_final. This is not scientific acceptance.
Task bootstrap resamples complete four-arm task clusters, not independent runs.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr


ARMS = ["guided", "record", "standard", "brief-errors"]
TIERS = ["easy", "normal", "hard", "impossible"]
SEED = 20261031
WEIGHTS = np.array([.1, .3, .6])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(Path(__file__).resolve().parents[1] / "source_publication_scores_per_run.csv"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--replicates", type=int, default=100000)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    source = Path(args.source)
    df = pd.read_csv(source, keep_default_na=False)
    for c in ["raw_final", "fair_final", "graph", "selfc_all", "selfc_gold", "accuracy", "repaired_final"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    assert len(df) == 200 and not df.duplicated(["arm", "task"]).any()
    assert set(df.arm) == set(ARMS)
    df["official_repaired"] = df.repaired_final.fillna(df.fair_final)
    assert np.allclose(df.official_repaired, pd.to_numeric(df["score"]), atol=1e-12)
    for current, publication in [("graph", "graph_publication"), ("selfc_all", "selfc_all_publication"), ("accuracy", "accuracy_publication")]:
        df["source_" + current] = df[current]
        df[current] = pd.to_numeric(df[publication], errors="raise")
    df["missing_graph_zero"] = df.fair_final.mask(df["flags"].str.contains("branch=no_graph", regex=False), 0.)
    df["delivery_strict"] = df.fair_final
    df.loc[(df.arm == "brief-errors") & (df.task == "IC3"), "delivery_strict"] = -1.
    tasks = sorted(df.task.unique())
    tiers = df.drop_duplicates("task").set_index("task").loc[tasks, "tier"].to_numpy()
    matrices = {c: df.pivot(index="task", columns="arm", values=c).loc[tasks, ARMS].to_numpy(float)
                for c in ["raw_final", "fair_final", "official_repaired", "missing_graph_zero", "delivery_strict"]}
    assert all(np.isfinite(m).all() for m in matrices.values())
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(tasks), size=(args.replicates, len(tasks)))
    sidx = np.concatenate([rng.choice(np.flatnonzero(tiers == t), size=(args.replicates, sum(tiers == t))) for t in TIERS], axis=1)
    pairs = list(itertools.combinations(range(4), 2))
    summary_rows, pair_rows, tier_rows = [], [], []
    for track, mat in matrices.items():
        boot = mat[idx].mean(axis=1)
        boot_s = mat[sidx].mean(axis=1)
        for i, arm in enumerate(ARMS):
            vals = mat[:, i]
            lo, hi = np.quantile(boot[:, i], [.025, .975])
            summary_rows.append(dict(track=track, arm=arm, n=len(vals), mean=vals.mean(), ci_low=lo, ci_high=hi,
                                     median=np.median(vals), p10=np.quantile(vals, .1), minimum=vals.min(),
                                     bottom10_mean=np.sort(vals)[:10].mean(), n_lt_0=sum(vals < 0),
                                     n_lt_point4=sum(vals < .4), n_ge_point9=sum(vals >= .9),
                                     n_ge_point99=sum(vals >= .99)))
        for i, j in pairs:
            d = mat[:, i] - mat[:, j]
            lo, hi = np.quantile(boot[:, i] - boot[:, j], [.025, .975])
            slo, shi = np.quantile(boot_s[:, i] - boot_s[:, j], [.025, .975])
            leave = (d.sum() - d)/(len(d)-1)
            trim = np.sort(d)[5:-5].mean()
            pair_rows.append(dict(track=track, arm_a=ARMS[i], arm_b=ARMS[j], n=len(d), mean_difference=d.mean(),
                                  ci_low=lo, ci_high=hi, stratified_ci_low=slo, stratified_ci_high=shi,
                                  a_wins=sum(d > 1e-9), b_wins=sum(d < -1e-9), ties=sum(abs(d) <= 1e-9),
                                  median_difference=np.median(d), trimmed_10pct_difference=trim,
                                  loo_min=leave.min(), loo_max=leave.max(),
                                  largest_a_win_task=tasks[int(d.argmax())], largest_a_win=float(d.max()),
                                  largest_b_win_task=tasks[int(d.argmin())], largest_b_win=float(d.min()),
                                  n_a_wins_gt_point1=sum(d > .1), n_b_wins_gt_point1=sum(d < -.1)))
        for t in TIERS:
            take = np.flatnonzero(tiers == t)
            mt = mat[take]
            bt = mt[rng.integers(0, len(take), (args.replicates, len(take)))].mean(axis=1)
            for i, j in pairs:
                d = mt[:, i] - mt[:, j]
                lo, hi = np.quantile(bt[:, i] - bt[:, j], [.025, .975])
                tier_rows.append(dict(track=track, tier=t, arm_a=ARMS[i], arm_b=ARMS[j], n=len(d),
                                      mean_difference=d.mean(), ci_low=lo, ci_high=hi,
                                      a_mean=mt[:, i].mean(), b_mean=mt[:, j].mean(),
                                      a_wins=sum(d > 1e-9), b_wins=sum(d < -1e-9), ties=sum(abs(d) <= 1e-9),
                                      median_difference=np.median(d)))
    for name, rows in [("arm_summary", summary_rows), ("pairwise", pair_rows), ("tier_pairwise", tier_rows)]:
        pd.DataFrame(rows).to_csv(out/f"{name}.csv", index=False)

    official = matrices["official_repaired"]
    per_task = pd.DataFrame(official, index=pd.Index(tasks, name="task"), columns=ARMS)
    per_task["tier"] = tiers
    per_task["range"] = official.max(axis=1)-official.min(axis=1)
    per_task["oracle"] = official.max(axis=1)
    per_task["worst_arm_score"] = official.min(axis=1)
    per_task["oracle_winner"] = ["|".join(np.array(ARMS)[abs(v-v.max()) <= 1e-9]) for v in official]
    for i, j in pairs:
        per_task[f"{ARMS[i]}_minus_{ARMS[j]}"] = official[:, i]-official[:, j]
    per_task.to_csv(out/"per_task_official.csv")

    # Totals and components use the same complete offline-organization track.
    df["component_sum"] = df[["graph", "selfc_all", "accuracy"]].to_numpy(float) @ WEIGHTS
    df["component_ok"] = abs(df.component_sum-df.official_repaired) <= .000051
    df["component_error"] = df.component_sum-df.official_repaired
    assert df.component_ok.all()
    df.loc[~df.component_ok, ["arm", "task", "flags", "fair_final", "component_sum", "component_error"]].to_csv(out/"component_exclusions.csv", index=False)
    component_rows, component_details, component_groups = [], [], []
    for i, j in pairs:
        a, b = df[df.arm == ARMS[i]].set_index("task"), df[df.arm == ARMS[j]].set_index("task")
        good = a.component_ok & b.component_ok
        ts = list(a.index[good])
        da = a.loc[ts, ["graph", "selfc_all", "accuracy"]].to_numpy()-b.loc[ts, ["graph", "selfc_all", "accuracy"]].to_numpy()
        contrib = da*WEIGHTS
        d = a.loc[ts, "official_repaired"].to_numpy()-b.loc[ts, "official_repaired"].to_numpy()
        row = dict(arm_a=ARMS[i], arm_b=ARMS[j], n=len(ts), excluded_tasks="|".join(sorted(set(tasks)-set(ts))),
                   final_difference=d.mean(), component_difference=contrib.sum(axis=1).mean(),
                   graph_contribution=contrib[:, 0].mean(), selfc_contribution=contrib[:, 1].mean(), accuracy_contribution=contrib[:, 2].mean())
        component_rows.append(row)
        for group in ["all"]+TIERS+["normal+hard", "possible"]:
            tt=a.loc[ts,"tier"].to_numpy()
            mask = (np.ones(len(ts),dtype=bool) if group=="all" else
                    np.isin(tt,["normal","hard"]) if group=="normal+hard" else
                    tt!="impossible" if group=="possible" else tt==group)
            nc=int(mask.sum())
            gc=contrib[mask]
            gd=d[mask]
            gb=gc[rng.integers(0,nc,(args.replicates,nc))].mean(axis=1)
            intervals=np.quantile(gb,[.025,.975],axis=0)
            fci=np.quantile(gb.sum(axis=1),[.025,.975])
            component_groups.append(dict(arm_a=ARMS[i],arm_b=ARMS[j],group=group,n=nc,
                                         final_difference=gd.mean(),ci_low=fci[0],ci_high=fci[1],
                                         graph_contribution=gc[:,0].mean(),graph_ci_low=intervals[0,0],graph_ci_high=intervals[1,0],
                                         selfc_contribution=gc[:,1].mean(),selfc_ci_low=intervals[0,1],selfc_ci_high=intervals[1,1],
                                         accuracy_contribution=gc[:,2].mean(),accuracy_ci_low=intervals[0,2],accuracy_ci_high=intervals[1,2],
                                         included_tasks="|".join(np.array(ts)[mask])))
        for k, task in enumerate(ts):
            component_details.append(dict(arm_a=ARMS[i], arm_b=ARMS[j], task=task, tier=a.loc[task,"tier"],
                                          final_difference=d[k], graph_contribution=contrib[k,0],
                                          selfc_contribution=contrib[k,1], accuracy_contribution=contrib[k,2]))
    pd.DataFrame(component_rows).to_csv(out/"component_decomposition.csv", index=False)
    pd.DataFrame(component_details).to_csv(out/"component_details.csv", index=False)
    pd.DataFrame(component_groups).to_csv(out/"component_groups.csv", index=False)

    # Interactions: differences in paired arm effects, not comparisons of unpaired run means.
    interactions=[]
    for i,j in pairs:
        for t,u in itertools.combinations(TIERS,2):
            dt=(official[:,i]-official[:,j])[tiers==t]
            du=(official[:,i]-official[:,j])[tiers==u]
            boot_t=dt[rng.integers(0,len(dt),(args.replicates,len(dt)))].mean(axis=1)
            boot_u=du[rng.integers(0,len(du),(args.replicates,len(du)))].mean(axis=1)
            lo,hi=np.quantile(boot_t-boot_u,[.025,.975])
            interactions.append(dict(arm_a=ARMS[i],arm_b=ARMS[j],tier_t=t,tier_u=u,
                                     difference_of_effects=dt.mean()-du.mean(),ci_low=lo,ci_high=hi))
    pd.DataFrame(interactions).to_csv(out/"tier_interactions.csv",index=False)

    # Sensitivity exclusions preserve pairing by dropping a task in every arm.
    fallback_tasks=sorted(df.loc[df["flags"].str.contains("fair=raw",regex=False),"task"].unique())
    missing_tasks=sorted(df.loc[df["flags"].str.contains("branch=no_graph",regex=False),"task"].unique())
    repair_tasks=sorted(df.loc[df.repaired_final.notna(),"task"].unique())
    sensitivities=[]
    keep_sets={"exclude_any_raw_fallback":set(tasks)-set(fallback_tasks),
               "exclude_any_standard_missing_graph":set(tasks)-set(missing_tasks),
               "exclude_impossible":set(np.array(tasks)[tiers!="impossible"]),
               "only_impossible":set(np.array(tasks)[tiers=="impossible"]),
               "exclude_raw_fallback_and_standard_missing_graph":set(tasks)-set(fallback_tasks)-set(missing_tasks),
               "exclude_raw_fallback_and_all_repairs":set(tasks)-set(fallback_tasks)-set(repair_tasks)}
    for label, keep in keep_sets.items():
        take=[k for k,t in enumerate(tasks) if t in keep]
        mat=official[take]
        boot=mat[rng.integers(0,len(take),(args.replicates,len(take)))].mean(axis=1)
        for i,j in pairs:
            d=mat[:,i]-mat[:,j]
            lo,hi=np.quantile(boot[:,i]-boot[:,j],[.025,.975])
            sensitivities.append(dict(sensitivity=label,arm_a=ARMS[i],arm_b=ARMS[j],n=len(d),
                                      mean_difference=d.mean(),ci_low=lo,ci_high=hi,
                                      a_wins=sum(d>1e-9),b_wins=sum(d < -1e-9),ties=sum(abs(d)<=1e-9)))
    pd.DataFrame(sensitivities).to_csv(out/"sensitivity_subsets.csv",index=False)

    # Oracle: descriptive hindsight, with no deployable task router inferred.
    routes=[]
    for size in range(1,5):
        for sub in itertools.combinations(range(4),size):
            vals=official[:,sub].max(axis=1)
            routes.append(dict(arms="|".join(ARMS[i] for i in sub),n_arms=size,
                               oracle_mean=vals.mean(),gain_over_guided=(vals-official[:,0]).mean(),
                               n_ge_point9=sum(vals>=.9),n_ge_point99=sum(vals>=.99)))
    pd.DataFrame(routes).to_csv(out/"hindsight_oracles.csv",index=False)

    correlations=[]
    for i,j in pairs:
        for tier in ["all"]+TIERS:
            take=np.ones(50,dtype=bool) if tier=="all" else tiers==tier
            correlations.append(dict(tier=tier,arm_a=ARMS[i],arm_b=ARMS[j],n=sum(take),
                                     pearson=pearsonr(official[take,i],official[take,j]).statistic,
                                     spearman=spearmanr(official[take,i],official[take,j]).statistic))
    pd.DataFrame(correlations).to_csv(out/"task_correlations.csv",index=False)

    # Publication components cover all four arms on all 50 shared tasks.
    comp = df.pivot(index="task",columns="arm",values="component_ok").loc[tasks,ARMS]
    common=comp.all(axis=1)
    pareto=[]
    for task in np.array(tasks)[common]:
        v=df[df.task==task].set_index("arm").loc[ARMS,["graph","selfc_all","accuracy"]].to_numpy()
        for i,arm in enumerate(ARMS):
            dominators=[ARMS[j] for j in range(4) if np.all(v[j]>=v[i]-1e-9) and np.any(v[j]>v[i]+1e-9)]
            pareto.append(dict(task=task,arm=arm,dominated=bool(dominators),dominators="|".join(dominators)))
    pd.DataFrame(pareto).to_csv(out/"component_pareto.csv",index=False)

    # Scorer/repair changes may themselves be arm-imbalanced.
    df["fair_minus_raw"]=df.fair_final-df.raw_final
    df["official_minus_fair"]=df.official_repaired-df.fair_final
    changed=df.loc[(df.fair_minus_raw.abs()>1e-9)|(df.official_minus_fair.abs()>1e-9)]
    changed.to_csv(out/"changed_scores.csv",index=False)
    df.to_csv(out/"source_with_analysis_columns.csv",index=False)
    meta=dict(source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),rows=len(df),tasks=len(tasks),
              arms=ARMS,tiers={t:int(sum(tiers==t)) for t in TIERS},seed=SEED,bootstrap_replicates=args.replicates,
              bootstrap_unit="task cluster retaining all four arms; percentile 95%, two-sided, unadjusted",
              estimand="Mean across this task-bank mix, not independent repeated runs or scientific acceptance",
              track_definitions={"raw_final":"database campaign scores, scoring defects retained",
                                 "fair_final":"as supplied final table; contains six raw fallbacks and hand-repaired brief IC3",
                                 "official_repaired":"nonempty repaired_final overrides fair_final; README final policy",
                                 "missing_graph_zero":"fair_final, but seven no-graph standard scores -1 -> 0",
                                 "delivery_strict":"fair_final, but brief IC3 hand-correction removed back to raw -1"},
              fallback_tasks=fallback_tasks,standard_missing_graph_tasks=missing_tasks,all_repair_tasks=repair_tasks,
              shared_component_tasks=list(np.array(tasks)[common]),
              caveats=["One run per task/arm: no independent estimate of stochastic run-to-run variation.",
                       "Bootstrap describes task-composition uncertainty under exchangeability; fixed bank itself is observed in full.",
                       "Tiers are not randomized difficulty levels; tier interactions are descriptive.",
                       "All 200 publication rows have Graph, SC and Accuracy from the same offline organization track as the final score.",
                       "Offline graph and reference organization uses preserved run records; no new scientific results or scoring changes are introduced.",
                       "The latest README overrides older methodology's rule to exclude reconstructed graphs from official means.",
                       "Threshold counts at .9/.99 are score descriptions, not scientific success rates.",
                       "All pairwise and interaction intervals are exploratory and unadjusted for multiple comparisons."])
    (out/"metadata.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False))
    report=dict(metadata=meta,arm_summary=summary_rows,pairwise=pair_rows,tier_pairwise=tier_rows,
                component_decomposition=component_rows,component_groups=component_groups,tier_interactions=interactions,
                sensitivity_subsets=sensitivities,hindsight_oracles=routes,
                score_change_sums=df.groupby("arm")[["fair_minus_raw","official_minus_fair"]].sum().to_dict("index"))
    def native(x):
        if isinstance(x,np.generic): return x.item()
        raise TypeError(type(x).__name__)
    (out/"results.json").write_text(json.dumps(report,indent=2,ensure_ascii=False,default=native))
    print(pd.DataFrame(summary_rows).query("track=='official_repaired'").to_string(index=False))
    print(pd.DataFrame(pair_rows).query("track=='official_repaired'").to_string(index=False))
    print(pd.DataFrame(component_rows).to_string(index=False))


if __name__ == "__main__":
    main()
