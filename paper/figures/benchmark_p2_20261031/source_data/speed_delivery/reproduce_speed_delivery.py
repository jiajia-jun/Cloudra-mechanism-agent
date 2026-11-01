"""Read copied source tables and extracted pilot DBs; write derivatives only.
No scoring, remote access, quantum calculations, or original source writes.
"""
import csv
import json
from pathlib import Path
from statistics import mean, median

OUT = Path(__file__).resolve().parent
SRC = OUT / 'source'
ARMS = ['standard', 'guided', 'record', 'brief-errors']


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


runs = read(SRC / 'p2_final_scores_per_run.csv')
assert len(runs) == 200
run_index = {(r['arm'], r['task']): r for r in runs}
assert len(run_index) == 200
expected_missing = {'F1', 'M17', 'P3', 'NR1', 'HA1', 'HF1', 'IA9'}
assert {(r['arm'], r['task']) for r in runs if r['neg_class'] == 'missing_graph'} == {('standard', t) for t in expected_missing}

# A scoring artifact's existence and continuous SC score are separate observations.
# root_graph_present is adjudication-derived, not a new scan of omitted sandboxes.
delivery = []
for source_row, r in enumerate(runs, 2):
    sc = float(r['selfc_all']) if r['selfc_all'] else None
    delivery.append(dict(
        arm=r['arm'], task=r['task'], tier=r['tier'], campaign=r['campaign'],
        root_graph_present=int(r['neg_class'] != 'missing_graph'),
        root_graph_status_source='package adjudication: neg_class and KNOWN_ISSUES K1',
        posthoc_root_graph=int(r['neg_class'] == 'missing_graph'),
        prose_reference_repair=int(r['arm'] == 'brief-errors' and r['task'] == 'IC3'),
        raw_final=r['raw_final'], fair_final=r['fair_final'],
        official_final=r['repaired_final'] or r['fair_final'],
        fair_graph=r['graph'], fair_selfc_all=r['selfc_all'], fair_accuracy=r['accuracy'],
        selfc_equals_one='' if sc is None else int(sc == 1.0),
        component_missing=int(not r['graph'] or not r['selfc_all'] or not r['accuracy']),
        components_track='saved fair components; standard missing-graph repairs have repaired total only',
        known_runtime_crash=int((r['arm'], r['task']) == ('guided', 'HF1')),
        known_dag_delivery_failure_but_scored=int((r['arm'], r['task']) == ('brief-errors', 'HL1')),
        known_delayed_wake_then_completed=int((r['arm'], r['task']) == ('guided', 'HI1')),
        source_csv_row=source_row, source=r['source'], flags=r['flags']))
write('p2_delivery_run_data.csv', delivery)

summary = []
for a in ARMS:
    rr = [r for r in delivery if r['arm'] == a]
    available = [r for r in rr if r['fair_selfc_all'] != '']
    summary.append(dict(
        arm=a, n_runs=len(rr), root_graph_present=sum(r['root_graph_present'] for r in rr),
        root_graph_missing=sum(r['posthoc_root_graph'] for r in rr),
        posthoc_root_graphs=sum(r['posthoc_root_graph'] for r in rr),
        prose_reference_repairs=sum(r['prose_reference_repair'] for r in rr),
        sc_component_available=len(available), sc_component_missing=len(rr) - len(available),
        sc_equals_one=sum(int(r['selfc_equals_one']) for r in available),
        sc_less_than_one=sum(float(r['fair_selfc_all']) < 1.0 for r in available),
        n_complete_components=sum(not r['component_missing'] for r in rr),
        known_runtime_crash=sum(r['known_runtime_crash'] for r in rr),
        known_dag_failure_but_scored=sum(r['known_dag_delivery_failure_but_scored'] for r in rr),
        official_mean=mean(float(r['official_final']) for r in rr)))
write('p2_delivery_arm_summary.csv', summary)

flex = read(SRC / 'p2_flex_snapshot.csv')
flex_index = {(r['arm'], r['task']): r for r in flex}
assert len(flex_index) == len(flex) == 63
common = sorted(set.intersection(*[{r['task'] for r in flex if r['arm'] == a} for a in ARMS]))
assert len(common) == 15
assert all(int(r['n_qm_jobs']) == int(r['n_qm_done']) + int(r['n_qm_failed']) + int(r['n_qm_cancelled']) for r in flex)

paired_rows = []
for source_row, r in enumerate(flex, 2):
    if r['task'] not in common:
        continue
    s = run_index[r['arm'], r['task']]
    paired_rows.append(dict(
        arm=r['arm'], task=r['task'], tier=r['tier'], flex_class=r['flex_class'],
        job_hours=float(r['job_hours']), qm_jobs=int(r['n_qm_jobs']),
        qm_done=int(r['n_qm_done']), qm_failed=int(r['n_qm_failed']), qm_cancelled=int(r['n_qm_cancelled']),
        official_final=float(s['repaired_final'] or s['fair_final']),
        fair_final=float(s['fair_final']), final_score_source=s['source'],
        root_graph_present=int(s['neg_class'] != 'missing_graph'),
        manual_graph_repair=int(s['neg_class'] == 'missing_graph'),
        job_hours_method='native log Job CPU time / 4' if (r['arm'], r['task']) == ('standard', 'M1') else 'sum ledger QM job end_timestamp - start_timestamp',
        snapshot_undelivered=int(r['undelivered']), snapshot_selfc=r['selfconsistency'],
        snapshot_failure_mode=r['failure_mode'],
        n_ts_inputs=int(r['n_ts_inputs']), n_irc_inputs=int(r['n_irc_inputs']),
        source_csv_row=source_row))
write('p2_effort_common15.csv', paired_rows)

effort_summary = []
for a in ARMS:
    rr = [r for r in paired_rows if r['arm'] == a]
    jobs = sum(r['qm_jobs'] for r in rr)
    effort_summary.append(dict(
        arm=a, n_runs=len(rr), job_hours_total=sum(r['job_hours'] for r in rr),
        job_hours_mean=mean(r['job_hours'] for r in rr), job_hours_median=median(r['job_hours'] for r in rr),
        qm_jobs_total=jobs, qm_jobs_mean=mean(r['qm_jobs'] for r in rr),
        qm_done=sum(r['qm_done'] for r in rr), qm_failed=sum(r['qm_failed'] for r in rr),
        qm_cancelled=sum(r['qm_cancelled'] for r in rr),
        failure_or_cancel_fraction=sum(r['qm_failed'] + r['qm_cancelled'] for r in rr) / jobs,
        official_mean=mean(r['official_final'] for r in rr)))
write('p2_effort_arm_summary_common15.csv', effort_summary)

pairs = []
for a, b in [('guided', 'standard'), ('guided', 'record'), ('guided', 'brief-errors'), ('brief-errors', 'record')]:
    for t in common:
        x = next(r for r in paired_rows if (r['arm'], r['task']) == (a, t))
        y = next(r for r in paired_rows if (r['arm'], r['task']) == (b, t))
        pairs.append(dict(a=a, b=b, task=t, job_hours_a=x['job_hours'], job_hours_b=y['job_hours'],
                          job_hours_delta=x['job_hours'] - y['job_hours'],
                          score_a=x['official_final'], score_b=y['official_final'],
                          score_delta=x['official_final'] - y['official_final']))
write('p2_effort_paired_deltas.csv', pairs)

# This old marker records whether .cloudra/mechanism_evidence.json exists.
# It does not record the root graph's existence or scientific acceptance.
marker_audit = []
for a in ARMS:
    rr = [r for r in flex if r['arm'] == a]
    marker_audit.append(dict(arm=a, n_snapshot_rows=len(rr), evidence_manifest_present=sum(r['undelivered'] == '0' for r in rr),
                             evidence_manifest_absent=sum(r['undelivered'] == '1' for r in rr),
                             snapshot_sc_equals_one=sum(float(r['selfconsistency']) == 1 for r in rr)))
write('p2_old_marker_audit.csv', marker_audit)

raw = read(SRC / 'p2_raw_score_notes.csv')
def raw_key(r):
    return r['batch'].lower(), r['arm'], r['task_id']
raw_index = {raw_key(r): r for r in raw}
note_rows = []
for r in runs:
    batch = r['campaign'].replace('cloudra-', '').split('-2026')[0]
    note = raw_index[batch, r['arm'], r['task']]['notes_first']
    note_rows.append(dict(arm=r['arm'], task=r['task'], notes_first=note, notes_chars=len(note),
                          at_export_limit=int(len(note) == 220)))
write('p2_raw_note_coverage.csv', note_rows)

(OUT / 'analysis_summary.json').write_text(json.dumps(dict(
    p2_run_n=200, p2_delivery=summary, p2_effort_common_tasks=common,
    p2_effort=effort_summary, p2_raw_notes_at_220_char_limit=sum(r['at_export_limit'] for r in note_rows),
    p2_no_run_walltime_fields=True,
    p2_effort_is_run_latency=False,
    p2_effort_standard_M1_estimated_from_cpu_divided_by_four=True,
), indent=2) + '\n')
print(json.dumps(dict(delivery=summary, effort=effort_summary), indent=2))

# Separate mechanistic tasks from impossible items, where explicit refusal can score SC=1.
scoped = []
for scope in ['non_impossible', 'impossible']:
    for a in ARMS:
        rr = [r for r in delivery if r['arm'] == a and ((r['tier'] == 'impossible') == (scope == 'impossible'))]
        available = [r for r in rr if r['fair_selfc_all'] != '']
        scoped.append(dict(scope=scope, arm=a, n_runs=len(rr),
                           root_graph_present=sum(r['root_graph_present'] for r in rr),
                           root_graph_missing=sum(r['posthoc_root_graph'] for r in rr),
                           sc_component_available=len(available),
                           sc_component_missing=len(rr)-len(available),
                           sc_equals_one=sum(int(r['selfc_equals_one']) for r in available),
                           sc_less_than_one=sum(float(r['fair_selfc_all']) < 1.0 for r in available)))
write('p2_delivery_scoped_summary.csv', scoped)
