#!/usr/bin/env python3
"""Read-only chemistry-oriented mining of the final P2 200-row archive.
No re-scoring, no QM, no modification of source archive or repository.
"""
import csv
import io
import json
import statistics
import subprocess
import tarfile
from collections import Counter
from pathlib import Path

DATA=Path('/Users/cloudrayyy/Desktop/Cloudra实验数据/Cloudra-P2-final-20261031')
REPO=Path('/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master')
OUT=Path(__file__).resolve().parent
SOURCE=OUT.parent/'source_publication_scores_per_run.csv'
rows=list(csv.DictReader(SOURCE.open()))
for row in rows:
 for key,publication in [('graph','graph_publication'),('selfc_all','selfc_all_publication'),('accuracy','accuracy_publication')]:
     row[key]=row[publication]
assert len(rows)==200 and len({(r['arm'],r['task']) for r in rows})==200
for i,r in enumerate(rows,2):
    r['source_csv_line']=i
archive=subprocess.run(['git','archive','53309d0e','ideapool/tasks'],cwd=REPO,check=True,capture_output=True)
tar=tarfile.open(fileobj=io.BytesIO(archive.stdout))
tasks={}
for member in tar.getmembers():
 if not member.name.endswith('.json'):
     continue
 d=json.load(tar.extractfile(member))
 g=d['gold']['mechanism_graph']
 edges=g['edges']
 def depth(node,seen=()):
  if node in seen:
      raise ValueError('Gold graph cycle')
  return max([1+depth(e['to'],seen+(node,)) for e in edges if e['from']==node]+[0])
 tasks[d['task_id']]={'task':d['task_id'],'tier':d['tier'],'name':d['name'],'gold_edges':len(edges),
  'gold_sequential_depth':max([depth(n['id']) for n in g['nodes']]+[0]),
  'gold_intermediates':sum(n['role']=='intermediate' for n in g['nodes']),
  'gold_numeric_barrier_edges':sum(e.get('barrier_kcal_mol') is not None for e in edges),
  'gold_negative_edges':sum(e.get('accessible') is False for e in edges),
  'allowed_methods':';'.join(d['method_policy']['allowed_methods']),
  'qualitative_selectivity':bool(d['gold'].get('selectivity')),
  'gold_source':f'git:53309d0e:{member.name}'}
assert len(tasks)==50

def mean(vals):return statistics.mean(vals) if vals else None

def summary(rr):
 valid=[r for r in rr if float(r['score'])>=0]
 out={'n':len(rr),'score_negative_n':len(rr)-len(valid),'score_mean_all':mean([float(r['score']) for r in rr]),
  'score_mean_nonnegative':mean([float(r['score']) for r in valid])}
 for metric in ['graph','selfc_all','accuracy']:
  vals=[float(r[metric]) for r in valid if r[metric]!='']
  out[metric]={'n':len(vals),'mean':mean(vals)}
 return out
result={'source':str(SOURCE),'n':len(rows),'task_structure_source':'git commit 53309d0e (campaign base documented by archive)',
 'evidence_scope':'Archive reports and reconstructed provenance only; no native .log files are present locally.',
 'tier':{tier:summary([r for r in rows if r['tier']==tier]) for tier in ['easy','normal','hard','impossible']},
 'accessible_by_gold_sequential_depth':{str(dep):summary([r for r in rows if r['tier']!='impossible' and tasks[r['task']]['gold_sequential_depth']==dep]) for dep in [1,2,3,4]}}
cc={tier:[r for r in rows if r['tier']==tier and float(r['score'])>=0 and all(r[k]!='' for k in ['graph','selfc_all','accuracy'])] for tier in ['normal','hard']}
weighted={metric:weight*(mean([float(r[metric]) for r in cc['hard']])-mean([float(r[metric]) for r in cc['normal']])) for metric,weight in [('graph',.1),('selfc_all',.3),('accuracy',.6)]}
result['normal_hard_complete_component_gap']={'normal_n':len(cc['normal']),'hard_n':len(cc['hard']),
 'hard_minus_normal_weighted_contributions':weighted,'accuracy_fraction':weighted['accuracy']/sum(weighted.values()),
 'note':'Accuracy includes missing Gold steps and task-specific qualitative/numerical rubrics; not pure chemical numerical error.'}
imp=[r for r in rows if r['tier']=='impossible']
result['impossible']={'accuracy_histogram':dict(Counter(r['accuracy'] for r in imp)),
 'selfc_exactly_1_accuracy_exactly_0_n':sum(r['selfc_all']=='1.0' and r['accuracy']=='0.0' for r in imp),
 'accuracy_1_pairs':[(r['arm'],r['task']) for r in imp if r['accuracy']=='1.0'],
 'all_four_accuracy_0_tasks':[t for t in sorted(tasks) if tasks[t]['tier']=='impossible' and all(r['accuracy']=='0.0' for r in rows if r['task']==t)],
 'per_arm':{arm:{'accuracy_1_n':sum(r['accuracy']=='1.0' for r in imp if r['arm']==arm),'accuracy_0_n':sum(r['accuracy']=='0.0' for r in imp if r['arm']==arm)} for arm in sorted({r['arm'] for r in rows})},
 'caution':'accuracy=0 does not universally mean incorrect refusal: archived record/IA5 is a documented channel-matching under-score; brief/IC3 .4 appears in fair and repaired.'}
result['hindsight_oracle']={}
for tier in ['easy','normal','hard','impossible']:
 ts=[t for t in tasks if tasks[t]['tier']==tier]
 maxima=[]
 wins=Counter()
 for t in ts:
  rr=[r for r in rows if r['task']==t]
  top=max(float(r['score']) for r in rr)
  maxima.append(top)
  winners=[r['arm'] for r in rr if float(r['score'])==top]
  for arm in winners:
      wins[arm]+=1/len(winners)
 result['hindsight_oracle'][tier]={'score_mean':mean(maxima),'fractional_wins':dict(wins),'not_a_deployed_policy':'Uses all four runs plus outcome knowledge; merely a descriptive complementarity ceiling.'}
result['hard_by_rubric']={}
for qualitative in [True,False]:
 rr=[r for r in rows if r['tier']=='hard' and tasks[r['task']]['qualitative_selectivity']==qualitative]
 result['hard_by_rubric']['qualitative_selectivity' if qualitative else 'numerical_barrier']=summary(rr)
result['guided_minus_record']={}
lookup={(r['arm'],r['task']):r for r in rows}
for name,tiers in [('normal',('normal',)),('hard',('hard',)),('normal_and_hard',('normal','hard'))]:
 ts=sorted({r['task'] for r in rows if r['tier'] in tiers})
 complete=[t for t in ts if all(lookup[arm,t][k]!='' for arm in ['guided','record'] for k in ['graph','selfc_all','accuracy'])]
 dif={k:mean([float(lookup['guided',t][k])-float(lookup['record',t][k]) for t in complete])*w for k,w in [('graph',.1),('selfc_all',.3),('accuracy',.6)]}
 result['guided_minus_record'][name]={'all_task_n':len(ts),'score_gap_all_tasks':mean([float(lookup['guided',t]['score'])-float(lookup['record',t]['score']) for t in ts]),'component_complete_pair_n':len(complete),'excluded_tasks':sorted(set(ts)-set(complete)),'weighted_component_differences':dif,'graph_plus_selfc_fraction':(dif['graph']+dif['selfc_all'])/sum(dif.values())}
result['offline_organization']={'runs':200,'components':600,'method':'Existing run records organized into mechanism graphs and evidence references before scoring; totals unchanged.'}
(OUT/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
per=[]
for t in sorted(tasks):
 d=dict(tasks[t])
 rr=[r for r in rows if r['task']==t]
 d['best_score']=max(float(r['score']) for r in rr)
 d['best_score_arms']=';'.join(r['arm'] for r in rr if float(r['score'])==d['best_score'])
 d['max_available_accuracy']=max(float(r['accuracy']) for r in rr if r['accuracy'])
 d['missing_component_arms']=';'.join(r['arm'] for r in rr if r['accuracy']=='')
 for r in rr:
  for k in ['score','fair_final','graph','selfc_all','accuracy','source_csv_line']:
      d[f"{r['arm']}_{k}"]=r[k]
 per.append(d)
with (OUT/'task_structure_and_final_scores.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(per[0]))
 w.writeheader()
 w.writerows(per)
with (OUT/'impossible_final_runs.csv').open('w') as f:
 fields=['arm','task','score','raw_final','fair_final','graph','selfc_all','accuracy','repaired_final','flags','source_csv_line']
 w=csv.DictWriter(f,fieldnames=fields)
 w.writeheader()
 w.writerows({k:r[k] for k in fields} for r in imp)
depth_rows=[]
for dep,v in result['accessible_by_gold_sequential_depth'].items():
 d={'gold_sequential_depth':dep,'tasks_n':sum(t['tier']!='impossible' and t['gold_sequential_depth']==int(dep) for t in tasks.values()),'task_ids':';'.join(sorted(t for t in tasks if tasks[t]['tier']!='impossible' and tasks[t]['gold_sequential_depth']==int(dep))),'runs_n':v['n'],'score_negative_n':v['score_negative_n'],'score_mean_all':v['score_mean_all'],'score_mean_nonnegative':v['score_mean_nonnegative']}
 for k in ['graph','selfc_all','accuracy']:
  d[k+'_n']=v[k]['n']
  d[k+'_mean']=v[k]['mean']
 depth_rows.append(d)
with (OUT/'sequential_depth_summary.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(depth_rows[0]))
 w.writeheader()
 w.writerows(depth_rows)
print(json.dumps({'output':str(OUT),'metrics':str(OUT/'metrics.json'),'depth':result['accessible_by_gold_sequential_depth'],'impossible':result['impossible'],'gap':result['normal_hard_complete_component_gap']},ensure_ascii=False,indent=2))
