#!/usr/bin/env python3
"""Read committed benchmark data; create audit artifacts only. Never run QM or edit sources."""
import argparse
import ast
import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

COMMIT = '3ec62c55c8e3433854246ea50f889668b2659cc4'
LABELS = {'backfilled': '已回填数值', 'open': '缺测且未明确放弃',
          'waived': '明确豁免参考垒', 'inaccessible_ts': 'impossible 明确 TS 不可达',
          'non_barrier_property': '性质/态变化边，不是活化垒交付'}


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def csv_write(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in row.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', type=Path, default=Path('/private/tmp/cloudra-hl1-20260930'))
    ap.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument('--commit', default=COMMIT)
    args = ap.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    decisions = json.loads((Path(__file__).parent / 'decisions.json').read_text())
    tracked = git(args.repo, 'ls-tree', '-r', '--name-only', args.commit).decode().splitlines()
    manifest = []
    saved = {}

    def source(path, local=False):
        key = ('LOCAL:' if local else '') + path
        if key not in saved:
            blob = (args.workspace / path).read_bytes() if local else git(args.repo, 'show', f'{args.commit}:{path}')
            dest = out / 'source_snapshot' / ('local_evidence' if local else 'published') / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            saved[key] = blob
            manifest.append({'source': key, 'snapshot': str(dest.relative_to(out)),
                             'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest(),
                             'origin_commit': None if local else args.commit})
        return saved[key]

    # AST retains exact step positions and source line numbers; no execution/import of registries.
    registry = {}
    for tier in ['normal', 'hard', 'impossible']:
        prefix = f'cloudra/benchmark/{tier}_registry/'
        for path in tracked:
            if not path.startswith(prefix) or not path.endswith('.py') or path.endswith('__init__.py'):
                continue
            tree = ast.parse(source(path).decode())
            assignments = [n for n in tree.body if isinstance(n, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == 'TASKS' for t in n.targets)]
            for assignment in assignments:
                for key_node, task_node in zip(assignment.value.keys, assignment.value.values):
                    key = ast.literal_eval(key_node)
                    task_data = ast.literal_eval(task_node)
                    task_id = {'normal': 'N', 'hard': 'H', 'impossible': 'I'}[tier] + key
                    field_nodes = {ast.literal_eval(k): v for k, v in zip(task_node.keys, task_node.values)}
                    edge_refs, edge_values = {}, {}
                    for field, stem in [('steps', 'E'), ('competing', 'EM')]:
                        for i, step_node in enumerate(getattr(field_nodes.get(field), 'elts', []), 1):
                            edge_refs[f'{task_id}_{stem}{i}'] = f'{path}:{step_node.lineno}'
                            edge_values[f'{task_id}_{stem}{i}'] = ast.literal_eval(step_node).get('barrier')
                    registry[task_id] = {'data': task_data, 'path': path, 'line': task_node.lineno,
                                         'edge_refs': edge_refs, 'edge_values': edge_values}

    edges, tasks, errors = [], [], []
    for path in tracked:
        parts = path.split('/')
        if len(parts) != 4 or parts[:2] != ['ideapool', 'tasks'] or not path.endswith('.json'):
            continue
        if parts[2] not in ['easy', 'normal', 'hard', 'impossible']:
            continue
        blob = source(path)
        d = json.loads(blob)
        tid, tier = d['task_id'], d['tier']
        graph = d['gold']['mechanism_graph']
        nodes = {n['id']: n for n in graph['nodes']}
        reg = registry.get(tid, {})
        tasks.append({'tier': tier, 'task_id': tid, 'name': d['name'], 'edge_count': len(graph['edges']),
                      'sha256': hashlib.sha256(blob).hexdigest(), 'source': path,
                      'deliverable_kind': reg.get('data', {}).get('deliverable_kind', 'mechanism'),
                      'reference_properties': d['gold'].get('reference_properties', {})})
        for e in graph['edges']:
            eid = e['id']
            for ref in [e['from'], e['to']] + ([e['via']] if e.get('via') else []):
                if ref not in nodes:
                    errors.append(f'{eid}: dangling {ref}')
            if reg and e.get('barrier_kcal_mol') != reg['edge_values'].get(eid):
                errors.append(f'{eid}: registry/TaskSpec barrier mismatch')
            ts_access = nodes.get(e.get('via'), {}).get('accessible')
            effective = e.get('accessible', True) and (not e.get('via') or ts_access is not False)
            decision = decisions['open'].get(eid) or decisions['waived'].get(eid)
            if e.get('barrier_kcal_mol') is not None:
                status, reason = 'backfilled', '现行 TaskSpec 已有数值；自算来源见题源/交接。此状态不自动等于严格科学证据全过。'
            elif eid in decisions['open']:
                status, reason = 'open', decision['reason']
            elif eid in decisions['waived']:
                status, reason = 'waived', decision['reason']
            elif tier == 'impossible' and reg['data']['kind'] == 'property':
                status, reason = 'non_barrier_property', '源明确为性质/自旋态/解离交付，无 TS；目标态不可达，不要求活化垒。'
            elif not effective:
                status, reason = 'inaccessible_ts', '现行 registry 和 TaskSpec 明确标 TS accessible=false；不属遗漏待补的可达 TS 边。'
            else:
                status, reason = 'UNCLASSIFIED', '没有可追溯分类'
                errors.append(f'{eid}: unclassified')
            refs = list(decisions['provenance'][tier + '_default'])
            refs.extend(decisions['provenance'].get(tid, []))
            if eid in reg.get('edge_refs', {}):
                refs.append(reg['edge_refs'][eid])
            if decision:
                refs.extend(decision['evidence'])
            caveat = decisions['numeric_caveats'].get(eid)
            if caveat:
                refs.extend(caveat['evidence'])
            row = {'tier': tier, 'task_id': tid, 'edge_id': eid, 'name': d['name'],
                   'from': e['from'], 'to': e['to'], 'via': e.get('via'), 'step_type': e.get('step_type'),
                   'barrier_kcal_mol': e.get('barrier_kcal_mol'), 'weight': e.get('weight'),
                   'edge_accessible': e.get('accessible', True), 'ts_accessible': ts_access,
                   'effective_edge_accessible': effective, 'target_accessible': nodes[e['to']].get('accessible'),
                   'status': status, 'status_zh': LABELS.get(status, status), 'reason': reason,
                   'short_name': decision.get('label', e.get('step_type')) if decision else e.get('step_type'),
                   'evidence_caveat': caveat['reason'] if caveat else '',
                   'task_spec': path, 'source_refs': sorted(set(refs))}
            edges.append(row)

    for row in edges:
        for ref in row['source_refs']:
            local = ref.startswith('LOCAL:')
            path = ref[6:] if local else ref
            if ':' in path:
                file, line = path.rsplit(':', 1)
                if line.isdigit():
                    path = file
            try:
                source(path, local)
            except (FileNotFoundError, subprocess.CalledProcessError) as ex:
                errors.append(f'{row["edge_id"]}: missing evidence source {ref}: {type(ex).__name__}')
    # Explicit PT rule and retrospective contradiction context must also be frozen.
    for path in ['cloudra/benchmark/normal_registry/__init__.py', 'gold_compute/README.md',
                 'gold_compute/archive/retired_tasks_20261001/HE3.json',
                 'gold_compute/archive/retired_tasks_20261001/HG2.json']:
        if path in tracked:
            source(path)

    deltas = []
    published_tasks = {t['source']: t for t in tasks}
    local_paths = {str(p.relative_to(args.workspace)) for tier in ['easy','normal','hard','impossible']
                   for p in (args.workspace / 'ideapool/tasks' / tier).glob('*.json')}
    for path in sorted(set(published_tasks) | local_paths):
        if path not in published_tasks:
            deltas.append({'task_spec': path, 'difference': '仅本地主工作区存在；已不在发布活跃题库', 'details': ''})
            continue
        if path not in local_paths:
            deltas.append({'task_spec': path, 'difference': '发布版本有，本地主工作区缺少', 'details': ''})
            continue
        b = (args.workspace / path).read_bytes()
        if hashlib.sha256(b).hexdigest() == published_tasks[path]['sha256']:
            continue
        a, z = json.loads(b), json.loads(saved[path])
        ae = {e['id']: e for e in a['gold']['mechanism_graph']['edges']}
        ze = {e['id']: e for e in z['gold']['mechanism_graph']['edges']}
        details = []
        for eid in sorted(set(ae) | set(ze)):
            av, zv = ae.get(eid), ze.get(eid)
            if av != zv:
                details.append({'edge': eid, 'local_barrier': av.get('barrier_kcal_mol') if av else 'absent',
                                'published_barrier': zv.get('barrier_kcal_mol') if zv else 'absent',
                                'local_step_type': av.get('step_type') if av else None,
                                'published_step_type': zv.get('step_type') if zv else None})
        deltas.append({'task_spec': path, 'difference': '文件内容与发布版本不同', 'details': details})

    edges.sort(key=lambda r: (r['tier'], r['task_id'], r['edge_id']))
    tasks.sort(key=lambda r: (r['tier'], r['task_id']))
    ids = [r['edge_id'] for r in edges]
    if len(ids) != len(set(ids)):
        errors.append('duplicate edge ids')
    if set(decisions['open']) != {r['edge_id'] for r in edges if r['status'] == 'open'}:
        errors.append('open decisions do not match active edges')
    if len(tasks) != 52 or len(edges) != 81:
        errors.append('unexpected task/edge count')
    counts = {tier: {'tasks': sum(t['tier']==tier for t in tasks),
                     'edges': sum(r['tier']==tier for r in edges),
                     'statuses': dict(Counter(r['status'] for r in edges if r['tier']==tier))}
              for tier in ['easy','normal','hard','impossible']}
    summary = {'published_commit': args.commit, 'remote_master_observed': json.loads((Path(__file__).parent / 'remote_reference.json').read_text())['sha'],
               'workspace_head': git(args.workspace, 'rev-parse', 'HEAD').decode().strip(),
               'task_count': len(tasks), 'edge_count': len(edges),
               'numeric_count': sum(r['barrier_kcal_mol'] is not None for r in edges),
               'null_count': sum(r['barrier_kcal_mol'] is None for r in edges),
               'status_counts': dict(Counter(r['status'] for r in edges)), 'tiers': counts,
               'numeric_caveat_count': sum(bool(r['evidence_caveat']) for r in edges),
               'working_tree_difference_count': len(deltas),
               'scope': '52 active generated TaskSpecs in all four tiers; archived/unused candidate pools excluded',
               'limits': ['Read-only source/provenance closure audit; not a fresh scientific validation of every raw QM log.',
                          'No numeric value and no explicit per-edge waiver => open, even when deferred or previous attempts failed.',
                          'Historic computed JSON and edge ids may be stale; committed current registry/TaskSpec takes precedence.'],
               'errors': errors, 'verified': not errors}
    write_json(out / 'all_edges.json', edges)
    write_json(out / 'tasks.json', tasks)
    write_json(out / 'working_tree_differences.json', deltas)
    write_json(out / 'source_manifest.json', sorted(manifest, key=lambda r: r['source']))
    write_json(out / 'verification.json', summary)
    csv_write(out / 'all_edges.csv', edges, list(edges[0]))
    csv_write(out / 'open_edges.csv', [r for r in edges if r['status']=='open'],
              ['tier','task_id','edge_id','short_name','barrier_kcal_mol','reason','source_refs'])
    csv_write(out / 'numeric_caveats.csv', [r for r in edges if r['evidence_caveat']],
              ['tier','task_id','edge_id','barrier_kcal_mol','evidence_caveat','source_refs'])
    csv_write(out / 'working_tree_differences.csv', deltas, ['task_spec','difference','details'])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
