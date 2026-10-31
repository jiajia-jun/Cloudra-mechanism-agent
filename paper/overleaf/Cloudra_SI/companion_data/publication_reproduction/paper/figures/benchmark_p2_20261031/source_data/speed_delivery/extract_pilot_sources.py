"""Stream only two root text/CSV files and 12 small benchmark DBs from the pilot tar.
This does not unpack any calculation sandbox. Existing extracted sources are replaced.
"""
from pathlib import Path
import json
import tarfile

BASE = Path('/Users/cloudrayyy/Desktop/Cloudra实验数据/P1b_20261024')
OUT = Path(__file__).resolve().parent
ARCHIVE = BASE / 'cloudra-p1b-20261024-v2.tar.gz'
targets = {
    'cloudra-p1b-20261024/SUMMARY.md': OUT / 'p1b_source_SUMMARY.md',
    'cloudra-p1b-20261024/runs.csv': OUT / 'p1b_source_runs.csv',
}
for arm in ['guided', 'record', 'standard', 'brief-errors']:
    for rnd in ['r1', 'r2', 'r3']:
        name = f'cloudra-p1b-20261024/{arm}/{rnd}/benchmark.db'
        targets[name] = OUT / 'p1b_databases' / arm / rnd / 'benchmark.db'
found = []
with tarfile.open(ARCHIVE, 'r|gz') as archive:
    for member in archive:
        if member.name not in targets:
            continue
        assert member.isfile() and member.size < 20_000_000
        dest = targets[member.name]
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = archive.extractfile(member).read()
        dest.write_bytes(data)
        found.append(dict(archive_member=member.name, bytes=len(data), output=str(dest)))
assert {r['archive_member'] for r in found} == set(targets)
(OUT / 'pilot_full_extract_manifest.json').write_text(json.dumps(found, indent=2) + '\n')
print(f'Extracted {len(found)} small files; {sum(r["bytes"] for r in found)} bytes total.')
