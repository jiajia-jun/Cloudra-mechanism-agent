"""Extract real pilot batch elapsed times from copied, read-only benchmark DBs.
Each batch contains four tasks at concurrency two. A batch is the analysis grain.
"""
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, stdev

OUT = Path(__file__).resolve().parent
ARMS = ['standard', 'guided', 'record', 'brief-errors']


def write(name, rows):
    with (OUT / name).open('w') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


pilot = list(csv.DictReader((OUT / 'p1b_source_runs.csv').open()))
pilot_index = {(r['arm'], r['round'], r['task']): r for r in pilot}
assert len(pilot_index) == len(pilot) == 48
batch_times, run_records = [], []
for a in ARMS:
    for rnd in ['r1', 'r2', 'r3']:
        path = OUT / 'p1b_databases' / a / rnd / 'benchmark.db'
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as conn:
            conn.row_factory = sqlite3.Row
            batches = list(conn.execute('SELECT * FROM batches'))
            runs = list(conn.execute('SELECT * FROM runs'))
        assert len(batches) == 1 and len(runs) == 4
        b = dict(batches[0])
        cfg = json.loads(b['config'])
        assert cfg['concurrency'] == 2 and set(cfg['task_ids']) == {'E1', 'NB1', 'HA1', 'IA1'}
        assert b['status'] == 'done' and b['finished_at'] > b['started_at']
        for r in runs:
            s = pilot_index[a, rnd, r['task_id']]
            assert abs(float(s['final']) - r['final_score']) < .00011
            assert b['started_at'] <= r['ts'] <= b['finished_at']
            run_records.append(dict(arm=a, round=rnd, task=r['task_id'],
                                    raw_final=r['final_score'], raw_sc_passed=r['selfconsistency_passed'],
                                    raw_sc_score=r['selfconsistency_score'],
                                    old_manifest_undelivered=r['undelivered'],
                                    scoring_ts=r['ts'], notes_json=r['notes'],
                                    batch_id=b['batch_id']))
        elapsed = b['finished_at'] - b['started_at']
        batch_times.append(dict(arm=a, round=rnd, batch_id=b['batch_id'], n_tasks=4,
                                concurrency=2, status=b['status'],
                                started_at_epoch=b['started_at'], finished_at_epoch=b['finished_at'],
                                started_at_utc=datetime.fromtimestamp(b['started_at'], timezone.utc).isoformat(),
                                finished_at_utc=datetime.fromtimestamp(b['finished_at'], timezone.utc).isoformat(),
                                elapsed_seconds=elapsed, elapsed_hours=elapsed/3600,
                                source_archive_member=f'cloudra-p1b-20261024/{a}/{rnd}/benchmark.db',
                                source_table='batches'))
write('p1b_batch_elapsed.csv', batch_times)
write('p1b_original_run_records.csv', run_records)
summary = []
for a in ARMS:
    rr = [r for r in batch_times if r['arm'] == a]
    values = [r['elapsed_hours'] for r in rr]
    summary.append(dict(arm=a, n_batches=3, n_tasks_per_batch=4, n_total_runs=12, concurrency=2,
                        mean_batch_hours=mean(values), median_batch_hours=median(values),
                        sample_sd_batch_hours=stdev(values), min_batch_hours=min(values),
                        max_batch_hours=max(values), total_batch_hours=sum(values)))
write('p1b_batch_elapsed_arm_summary.csv', summary)
pairs = []
for a, b in [('guided', 'standard'), ('guided', 'record'), ('guided', 'brief-errors')]:
    for rnd in ['r1', 'r2', 'r3']:
        x = next(r for r in batch_times if (r['arm'], r['round']) == (a, rnd))
        y = next(r for r in batch_times if (r['arm'], r['round']) == (b, rnd))
        pairs.append(dict(a=a, b=b, round=rnd, elapsed_hours_a=x['elapsed_hours'],
                          elapsed_hours_b=y['elapsed_hours'],
                          delta_hours=x['elapsed_hours'] - y['elapsed_hours']))
write('p1b_batch_time_paired_deltas.csv', pairs)
(OUT / 'p1b_batch_time_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
