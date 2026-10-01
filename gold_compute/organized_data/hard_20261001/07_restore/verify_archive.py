"""Read-only verification of the complete organized bundle after local transfer."""
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import urllib.parse

root = Path(__file__).resolve().parents[1]
project = root.parents[2]
errors = []


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


raw = json.loads((root / '08_integrity/raw_inventory.json').read_text())
for item in raw:
    path = project / item['path']
    if not path.is_file() or path.stat().st_size != item['bytes'] or sha(path) != item['sha256']:
        errors.append({'kind': 'raw_file', 'path': item['path']})

manifest = json.loads((root / '08_integrity/organized_manifest.json').read_text())
for item in manifest:
    path = root / item['path']
    if not path.is_file() or path.stat().st_size != item['bytes'] or sha(path) != item['sha256']:
        errors.append({'kind': 'organized_file', 'path': item['path']})

links = json.loads((root / '08_integrity/links.json').read_text())
for item in links:
    path = root / item['path']
    if not path.is_symlink() or os.readlink(path) != item['target'] or not path.exists():
        errors.append({'kind': 'link', 'path': item['path']})

original_dbs = json.loads((root / '04_databases/database_inventory.json').read_text())
for item in original_dbs + [{'source_path': str((root / 'catalog.sqlite3').relative_to(project))}]:
    path = project / item['source_path']
    uri = 'file:' + urllib.parse.quote(str(path), safe='/') + '?mode=ro&immutable=1'
    try:
        with sqlite3.connect(uri, uri=True) as database:
            result = database.execute('pragma integrity_check').fetchall()
            if result != [('ok',)]:
                errors.append({'kind': 'database_integrity', 'path': item['source_path']})
    except sqlite3.Error as error:
        errors.append({'kind': 'database_unreadable', 'path': item['source_path'], 'error': str(error)})

print(json.dumps({'verified': not errors, 'original_files': len(raw), 'derived_files': len(manifest),
                  'original_databases': len(original_dbs), 'links': len(links), 'errors': errors},
                 ensure_ascii=False))
raise SystemExit(1 if errors else 0)
