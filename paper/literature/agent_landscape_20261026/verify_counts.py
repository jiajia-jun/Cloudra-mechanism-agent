"""Small data/figure reconciliation, not a Cloudra software test."""
import csv
import json
from collections import Counter
from pathlib import Path
p=Path(__file__).resolve().parent
rows=json.loads((p/'systems.json').read_text())
summary=json.loads((p/'counts.json').read_text())
assert len(rows)==len({r['id'] for r in rows})==summary['sample_n']==26
assert Counter(r['physical_target'] for r in rows)==summary['physical_target_counts']
assert Counter(t for r in rows for t in r['demonstrated_tasks'])==summary['positive_task_counts']
assert all(r['sources'][0]['url'].startswith('https://') and r['sources'][0]['locator'] for r in rows)
assert all(set(r['demonstrated_tasks']) <= set('TEOFRD') for r in rows)
assert len(list((p/'systems').glob('*.json')))==26
with (p/'source_index.csv').open() as f:
    assert len(list(csv.DictReader(f)))==26
family_rows=[]
for r in rows:
    if r['family']=='El Agente' and any(x['family']=='El Agente' for x in family_rows):
        continue
    family_rows.append(r)
assert len(family_rows)==23
assert Counter(r['physical_target'] for r in family_rows)=={'extended_materials_surfaces':14,'finite_molecules_complexes':6,'soft_biomolecular':3}
figdir=p.parents[1]/'figures'
assert all((figdir/f'agent_landscape.{e}').stat().st_size>1000 for e in ['svg','pdf','png'])
print('Verified: N=26; targets=14/9/3; task positives T/E/O/F/R/D=18/17/18/9/6/8; family sensitivity N=23, 14/6/3; 26 source rows and all three exports present.')
