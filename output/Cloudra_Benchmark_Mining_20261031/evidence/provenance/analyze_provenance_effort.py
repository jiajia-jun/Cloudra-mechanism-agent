"""Read local release tables; writes audit derivatives only beside this script."""
import csv
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean, median

BASE = Path('/Users/cloudrayyy/Desktop/Cloudra实验数据')
P2 = BASE / 'Cloudra-P2-final-20261031'
OUT = Path(__file__).resolve().parent
ARMS = ['guided', 'record', 'standard', 'brief-errors']


def read(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def write(name, rows):
    if not rows:
        return
    with (OUT / name).open('w') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def corr(x, y):
    mx, my = mean(x), mean(y)
    a = sum((v-mx)*(w-my) for v,w in zip(x,y))
    d = math.sqrt(sum((v-mx)**2 for v in x)*sum((w-my)**2 for w in y))
    return a/d if d else None


def ranks(values):
    ordered = sorted(enumerate(values), key=lambda x:x[1])
    result = [0.0]*len(values)
    i = 0
    while i < len(values):
        j = i+1
        while j < len(values) and ordered[j][1] == ordered[i][1]:
            j += 1
        for k in range(i,j):
            result[ordered[k][0]] = (i+j+1)/2
        i = j
    return result


def rho(rows, a, b):
    return corr(ranks([float(x[a]) for x in rows]), ranks([float(x[b]) for x in rows]))


runs = read(OUT.parent/'source_publication_scores_per_run.csv')
for row in runs:
    for key,publication in [('graph','graph_publication'),('selfc_all','selfc_all_publication'),('accuracy','accuracy_publication')]:
        row[key]=row[publication]
assert len(runs) == 200
assert [(r['arm'],r['task'],r['raw_final'],r['fair_final'],r['repaired_final']) for r in runs] == [(r['arm'],r['task'],r['raw_final'],r['fair_final'],r['repaired_final']) for r in read(P2/'runs/all_runs_detail.csv')]
ix = {(r['arm'],r['task']):r for r in runs}
assert len(ix) == 200
repairs = [r for r in runs if r['repaired_final']]
std_missing = [r for r in runs if r['neg_class']=='missing_graph']
fair = mean(float(r['fair_final']) for r in runs)
official = mean(float(r['repaired_final'] or r['fair_final']) for r in runs)
strict_fair = mean(-1.0 if r['arm']=='brief-errors' and r['task']=='IC3' else float(r['fair_final']) for r in runs)
zero_missing = mean(0.0 if r['neg_class']=='missing_graph' else float(r['fair_final']) for r in runs)
raw = read(P2/'runs/raw_scores_p2.csv')

def final_key(r):
    return (r['campaign'].replace('cloudra-','').split('-2026')[0].lower(),r['arm'],r['task'])


retained_raw_keys = {final_key(r) for r in runs}


def raw_key(r):
    return (r['batch'].lower(),r['arm'],r['task_id'])


raw_index = {raw_key(r):r for r in raw}
excluded_raw = [r for r in raw if raw_key(r) not in retained_raw_keys]
raw_to_final_disagreement = []
for r in runs:
    raw_r = raw_index[final_key(r)]
    if float(r['raw_final']) != float(raw_r['final']):
        raw_to_final_disagreement.append(dict(arm=r['arm'],task=r['task'],table_raw=r['raw_final'],audit_raw=raw_r['final']))
write('raw_final_disagreement.csv',raw_to_final_disagreement)

score_tracks=[]
for arm in ARMS:
    rr=[r for r in runs if r['arm']==arm]
    score_tracks.append(dict(arm=arm,n=len(rr),raw=mean(float(r['raw_final']) for r in rr),table_fair=mean(float(r['fair_final']) for r in rr),strict_fair_no_IC3_repair=mean(-1.0 if r['arm']=='brief-errors' and r['task']=='IC3' else float(r['fair_final']) for r in rr),fair_plus_repair=mean(float(r['repaired_final'] or r['fair_final']) for r in rr),fair_nonnegative_only=mean(float(r['fair_final']) for r in rr if float(r['fair_final'])>=0),fair_missing_zero=mean(0 if r['neg_class']=='missing_graph' else float(r['fair_final']) for r in rr)))
write('score_track_audit.csv',score_tracks)

catalog=read(P2/'reports/catalog.csv')
catalog_deltas=[]
for rownum,r in enumerate(catalog,2):
    final=ix[r['arm'],r['task']]
    if abs(float(r['final'])-float(final['fair_final']))>0.00011:
        catalog_deltas.append(dict(arm=r['arm'],task=r['task'],catalog_row=rownum,catalog_score=r['final'],final_fair=final['fair_final'],delta=float(final['fair_final'])-float(r['final'])))
write('catalog_final_deltas.csv',catalog_deltas)

flex=read(P2/'reports/flex_table.csv')
flex_joined=[]
for rownum,r in enumerate(flex,2):
    s=ix[r['arm'],r['task']]
    flex_joined.append(dict(r,source_csv_row=rownum,final_raw=s['raw_final'],final_fair=s['fair_final'],final_repaired=s['repaired_final'] or s['fair_final'],final_selfc=s['selfc_all'],final_accuracy=s['accuracy'],final_source=s['source'],final_flags=s['flags'],final_neg_class=s['neg_class']))
write('flex_joined_final.csv',flex_joined)
tasks=sorted({r['task'] for r in flex})
common=sorted(t for t in tasks if all((a,t) in {(r['arm'],r['task']) for r in flex} for a in ARMS))
fi={(r['arm'],r['task']):r for r in flex_joined}
effort=[]
for scope,ts in [('snapshot63',tasks),('common15',common)]:
    for arm in ARMS:
        rr=[r for r in flex_joined if r['arm']==arm and r['task'] in ts]
        n=len(rr)
        hours=sum(float(r['job_hours']) for r in rr)
        done=sum(int(r['n_qm_done']) for r in rr)
        failed=sum(int(r['n_qm_failed']) for r in rr)
        cancelled=sum(int(r['n_qm_cancelled']) for r in rr)
        effort.append(dict(scope=scope,arm=arm,n=n,job_hours=hours,mean_job_hours=hours/n,median_job_hours=median(float(r['job_hours']) for r in rr),qm_jobs=sum(int(r['n_qm_jobs']) for r in rr),qm_done=done,qm_failed=failed,qm_cancelled=cancelled,engine_failure_rate=(failed+cancelled)/(done+failed+cancelled),snapshot_score=mean(float(r['final_score']) for r in rr),final_fair=mean(float(r['final_fair']) for r in rr),final_repaired=mean(float(r['final_repaired']) for r in rr),final_score_ge_point9=sum(float(r['final_repaired'])>=.9 for r in rr),final_selfc_one=sum(bool(r['final_selfc']) and float(r['final_selfc'])==1 for r in rr),snapshot_failure_modes=json.dumps(Counter(r['failure_mode'] for r in rr)),spearman_hours_final=rho(rr,'job_hours','final_repaired')))
write('effort_by_arm.csv',effort)

pairs=[]
pair_details=[]
for a,b in [('guided','record'),('guided','standard'),('guided','brief-errors'),('brief-errors','record'),('brief-errors','standard'),('record','standard')]:
    details=[]
    for t in common:
        x,y=fi[a,t],fi[b,t]
        details.append(dict(a=a,b=b,task=t,hours_a=float(x['job_hours']),hours_b=float(y['job_hours']),hours_delta=float(x['job_hours'])-float(y['job_hours']),hours_ratio=float(x['job_hours'])/float(y['job_hours']),score_a=float(x['final_repaired']),score_b=float(y['final_repaired']),score_delta=float(x['final_repaired'])-float(y['final_repaired'])))
    pair_details.extend(details)
    pairs.append(dict(a=a,b=b,n=len(details),mean_hours_a=mean(r['hours_a'] for r in details),mean_hours_b=mean(r['hours_b'] for r in details),ratio_total_hours=sum(r['hours_a'] for r in details)/sum(r['hours_b'] for r in details),median_task_hours_ratio=median(r['hours_ratio'] for r in details),a_more_hours=sum(r['hours_delta']>0 for r in details),mean_score_delta=mean(r['score_delta'] for r in details),a_better_score=sum(r['score_delta']>.00011 for r in details),a_worse_score=sum(r['score_delta']<-.00011 for r in details),a_dominated=sum(r['hours_delta']>0 and r['score_delta']<-.00011 for r in details),a_dominates=sum(r['hours_delta']<0 and r['score_delta']>.00011 for r in details),spearman_hours_delta_score_delta=rho(details,'hours_delta','score_delta')))
write('effort_paired_common15.csv',pairs)
write('effort_pair_details_common15.csv',pair_details)

failure_effort=[]
for mode in sorted({r['failure_mode'] for r in flex_joined}):
    rr=[r for r in flex_joined if r['failure_mode']==mode]
    failure_effort.append(dict(snapshot_failure_mode=mode,n=len(rr),hours=sum(float(r['job_hours']) for r in rr),mean_hours=mean(float(r['job_hours']) for r in rr),final_mean_score=mean(float(r['final_repaired']) for r in rr),jobs=sum(int(r['n_qm_jobs']) for r in rr),failed_cancelled=sum(int(r['n_qm_failed'])+int(r['n_qm_cancelled']) for r in rr)))
write('effort_by_snapshot_failure_mode.csv',failure_effort)

task_effort=[]
for t in tasks:
    rr=[r for r in flex_joined if r['task']==t]
    task_effort.append(dict(task=t,n=len(rr),hours=sum(float(r['job_hours']) for r in rr),mean_hours=mean(float(r['job_hours']) for r in rr),final_repaired=mean(float(r['final_repaired']) for r in rr),score_ge_point9=sum(float(r['final_repaired'])>=.9 for r in rr)))
write('effort_by_task.csv',sorted(task_effort,key=lambda r:-r['hours']))

counts=dict(zero_ts_job_rows=sum(int(r['n_ts_jobs'])==0 for r in flex),zero_ts_with_inputs=sum(int(r['n_ts_jobs'])==0 and int(r['n_ts_inputs'])>0 for r in flex),zero_ts_with_processes=sum(int(r['n_ts_jobs'])==0 and int(r['ts_processes'])>0 for r in flex),zero_irc_jobs_with_inputs=sum(int(r['n_irc_jobs'])==0 and int(r['n_irc_inputs'])>0 for r in flex),job_terminal_sum_mismatch=sum(int(r['n_qm_jobs'])!=int(r['n_qm_done'])+int(r['n_qm_failed'])+int(r['n_qm_cancelled']) for r in flex),ts_plus_irc_exceeds_total=sum(int(r['n_ts_jobs'])+int(r['n_irc_jobs'])>int(r['n_qm_jobs']) for r in flex))

p1=read(BASE/'复评分补充/results.csv')
p1_zip=read(OUT/'p1b_supplement/cloudra-p1b-20261024-supplement/RESCORED/results.csv')
assert p1==p1_zip
p1_summary=[]
for a in ARMS:
    rr=[r for r in p1 if r['arm']==a]
    p1_summary.append(dict(arm=a,n=len(rr),snapshot_rescored_mean=mean(float(r['new_final']) for r in rr),rescore_seconds=sum(float(r['seconds']) for r in rr)))
write('p1b_historical_summary.csv',p1_summary)

result=dict(n=len(runs),source_counts=Counter(r['source'] for r in runs),campaign_counts=Counter(r['campaign'] for r in runs),raw=mean(float(r['raw_final']) for r in runs),table_fair=fair,strict_fair_no_IC3_repair=strict_fair,official_fair_plus_repair=official,fair_missing_zero=zero_missing,missing_repair_mean=mean(float(r['repaired_final']) for r in std_missing),repair_gain_over_minus_one=official-fair,repair_gain_from_sentinel_removal=len(std_missing)/len(runs),repair_gain_from_positive_credit=sum(float(r['repaired_final']) for r in std_missing)/len(runs),brief_IC3_leaks_into_fair_effect=.007,raw_csv_rows=len(raw),raw_csv_batch_counts=Counter(r['batch'] for r in raw),excluded_raw_rows=len(excluded_raw),excluded_raw_stop_cancelled=sum(r['notes_first']=='cancelled by batch stop' for r in excluded_raw),raw_final_disagreement_n=len(raw_to_final_disagreement),catalog_n=len(catalog),catalog_final_deltas=len(catalog_deltas),flex_n=len(flex),flex_distinct_tasks=len(tasks),flex_common_tasks=common,flex_total_hours=sum(float(r['job_hours']) for r in flex),flex_total_jobs=sum(int(r['n_qm_jobs']) for r in flex),flex_count_audit=counts,timeout_filled=[dict(arm=r['arm'],task=r['task'],fair=r['fair_final']) for r in runs if r['source']=='snapshot_timeout_filled'],score_tracks=score_tracks,effort=effort,pairs=pairs,p1b_summary=p1_summary)
(OUT/'analysis.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(result,indent=2,ensure_ascii=False))

# D3 is a distinct optional recorded variant, not the official component scope.
variant=[]
for lineno,r in enumerate(runs,2):
    if not r['selfc_gold'] or r['neg_class']=='missing_graph':
        continue
    whole=float(r['selfc_all'])
    target=float(r['selfc_gold'])
    variant.append(dict(arm=r['arm'],task=r['task'],tier=r['tier'],selfc_all=whole,selfc_gold=target,
                        delta=target-whole,graph=float(r['graph']),accuracy=float(r['accuracy']),
                        score=float(r['score']),source_row=lineno))
write('d3_selfc_pairs.csv',variant)
def variant_summary(rr):
    return dict(n=len(rr),increase=sum(x['delta']>1e-4 for x in rr),
                decrease=sum(x['delta'] < -1e-4 for x in rr),same=sum(abs(x['delta'])<=1e-4 for x in rr),
                all_perfect_gold_zero=[x for x in rr if x['selfc_all']==1 and x['selfc_gold']==0],
                gold_perfect_all_lower=[x for x in rr if x['selfc_gold']==1 and x['selfc_all']<1])
d3=dict(publication_runs=200,publication_components=600,
        scope='Official components are complete. This auxiliary selfc_gold comparison uses only actual recorded variant values; it is not the main decomposition denominator.',
        variant_subset_all=variant_summary(variant),
        variant_subset_non_impossible=variant_summary([x for x in variant if x['tier']!='impossible']))
(OUT/'d3_selfc_summary.json').write_text(json.dumps(d3,indent=2,ensure_ascii=False)+'\n')
