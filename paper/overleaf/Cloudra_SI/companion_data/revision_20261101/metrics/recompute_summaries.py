"""Recompute uncapped statistics using the final target-correspondence selection."""
import csv
import json
import math
import statistics
from pathlib import Path

root = Path(__file__).resolve().parent
rows = list(csv.DictReader((root / 'uncapped_barrier_observations.csv').open()))
expected = list(csv.DictReader((root / 'uncapped_barrier_summary.csv').open()))
replay_path = root.parents[1] / 'revision_20261102/target_matching/accuracy_replay.json'
replay = json.loads(replay_path.read_text())
l2 = next(r for r in replay['runs'] if r['arm'] == 'standard' and r['task'] == 'L2')
old_selected, new_selected = l2['old_selected'], l2['new_selected']
assert old_selected['edge_id'] == 'e1' and new_selected['edge_id'] == 'e2'
native = l2['native_selected_log_energies']
final_l2_barrier = (
    native[new_selected['ts_path']]['electronic_energy_hartree']
    - native[new_selected['base_path']]['electronic_energy_hartree']
) * 627.509474
assert math.isclose(final_l2_barrier, new_selected['barrier_kcal_mol'], abs_tol=1e-8)


def numerical_error(row):
    barrier = (
        float(row['ts_native_energy_hartree'])
        - float(row['reference_native_energy_hartree'])
    ) * 627.509474
    if row['arm'] == 'standard' and row['task'] == 'L2':
        assert row['delivered_edge'] == old_selected['edge_id']
        assert math.isclose(barrier, old_selected['barrier_kcal_mol'], abs_tol=1e-8)
        barrier = final_l2_barrier
    return barrier - float(row['gold_task_fullprecision_kcal_mol'])


fields = {
    'final_aligned_available_positive': 'final_aligned_native_positive_observation',
    'four_arm_common_final_aligned': 'four_arm_common_final_aligned',
    'four_arm_common_gold_input_corroborated': 'four_arm_common_gold_input_corroborated',
}
result = []
for e in expected:
    rr = [r for r in rows if r['arm'] == e['arm'] and r[fields[e['cohort']]] == 'True']
    if e['arm'] == 'standard':
        assert sum(r['task'] == 'L2' for r in rr) == 1
    errors = [numerical_error(r) for r in rr]
    d = {
        'cohort': e['cohort'],
        'arm': e['arm'],
        'observed_reference_edges': len(rr),
        'observed_task_runs': len({r['task'] for r in rr}),
        'MAE_kcal_mol': statistics.mean(map(abs, errors)),
        'RMSE_kcal_mol': math.sqrt(statistics.mean(x * x for x in errors)),
        'median_absolute_error_kcal_mol': statistics.median(map(abs, errors)),
        'maximum_absolute_error_kcal_mol': max(map(abs, errors)),
    }
    assert d['observed_reference_edges'] == int(e['observed_reference_edges'])
    assert d['observed_task_runs'] == int(e['observed_task_runs'])
    for k in [
        'MAE_kcal_mol', 'RMSE_kcal_mol',
        'median_absolute_error_kcal_mol', 'maximum_absolute_error_kcal_mol',
    ]:
        assert math.isclose(d[k], float(e[k]), rel_tol=0, abs_tol=1e-12), (e['cohort'], e['arm'], k)
    result.append(d)
assert len(result) == 12
print(json.dumps(result, indent=2))
