"""Recompute the observed, uncapped statistics; changes no frozen score records."""
from pathlib import Path
import csv,json,math,statistics
root=Path(__file__).resolve().parent
rows=list(csv.DictReader((root/'uncapped_barrier_observations.csv').open()))
expected=list(csv.DictReader((root/'uncapped_barrier_summary.csv').open()))
fields={'final_aligned_available_positive':'final_aligned_native_positive_observation','four_arm_common_final_aligned':'four_arm_common_final_aligned','four_arm_common_gold_input_corroborated':'four_arm_common_gold_input_corroborated'}
result=[]
for e in expected:
 rr=[r for r in rows if r['arm']==e['arm'] and r[fields[e['cohort']]]=='True']
 errors=[(float(r['ts_native_energy_hartree'])-float(r['reference_native_energy_hartree']))*627.509474-float(r['gold_task_fullprecision_kcal_mol']) for r in rr]
 d={'cohort':e['cohort'],'arm':e['arm'],'observed_reference_edges':len(rr),'observed_task_runs':len({r['task'] for r in rr}),'MAE_kcal_mol':statistics.mean(map(abs,errors)),'RMSE_kcal_mol':math.sqrt(statistics.mean(x*x for x in errors)),'median_absolute_error_kcal_mol':statistics.median(map(abs,errors)),'maximum_absolute_error_kcal_mol':max(map(abs,errors))}
 assert d['observed_reference_edges']==int(e['observed_reference_edges'])
 assert d['observed_task_runs']==int(e['observed_task_runs'])
 for k in ['MAE_kcal_mol','RMSE_kcal_mol','median_absolute_error_kcal_mol','maximum_absolute_error_kcal_mol']:
  assert math.isclose(d[k],float(e[k]),rel_tol=0,abs_tol=1e-12),(e['cohort'],e['arm'],k)
 result.append(d)
print(json.dumps(result,indent=2))
