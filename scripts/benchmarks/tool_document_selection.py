#!/usr/bin/env python3
"""Read-only document selection evaluation; live calls require explicit --run.

Run from the repository root with PYTHONPATH=. . No scientific tools execute.
Scores describe documentation coverage, not chemistry or task acceptance.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from cloudra.infra.config import get_config
from cloudra.runtime_v2.adapters import LegacyLLMProvider
from cloudra.runtime_v2.compaction import estimate_tokens
from cloudra.runtime_v2.schemas import AgentSession, OrchestrationMode
from cloudra.runtime_v2.tool_catalog import guest_tool_names, tool_capability_manifest, tool_declarations
from cloudra.runtime_v2.tool_selection import ToolDocumentSelector
from cloudra.tools import get_tools_lst
from cloudra.tools.documentation import build_tool_documents, tool_capability_summaries

CASES = (
    {'id': 'ts', 'task': 'Inspect the existing TS workflow state and its evidence before resuming the existing run.',
     'required': [['ts_inspect']], 'useful': ['ts_resume', 'read', 'query_compute_job']},
    {'id': 'qm', 'task': 'Prepare a quantum calculation input using the method I supplied, then submit it to my selected node.',
     'required': [['qm_input_writer'], ['submit_compute_job']], 'useful': ['read', 'query_compute_queue']},
    {'id': 'logs', 'task': 'Read calculation.out, parse its energies and convergence status, and explain what evidence is missing.',
     'required': [['log_parser']], 'useful': ['read', 'search', 'thermo_analysis']},
    {'id': 'literature', 'task': 'Find original literature on this reaction mechanism and retain source links.',
     'required': [['browser', 'search']], 'useful': ['get_skill', 'read']},
    {'id': 'dag', 'task': 'Inspect the current mechanism graph and bind the provided calculation evidence to its existing step.',
     'required': [['dag_view'], ['dag_bind_evidence', 'dag_submit_step_evidence']],
     'useful': ['dag_view_evidence', 'dag_delivery_report', 'read']},
    {'id': 'image', 'task': 'Convert the supplied image of a chemical structure to SMILES and inspect the drawing.',
     'required': [['image_to_smiles']], 'useful': ['molecule_drawer', 'read', 'pymol_render']},
    {'id': 'multi', 'task': 'Find the SMILES for this chemical name, draw it, and parse the supplied calculation log.',
     'required': [['name_to_structure'], ['molecule_drawer'], ['log_parser']], 'useful': ['read', 'search']},
    {'id': 'explanation', 'task': 'Explain conceptually what an imaginary frequency means. No files or calculations are needed.',
     'required': [], 'useful': []},
)


def grade_selection(case: dict, names: list[str]) -> dict:
    selected = set(names)
    missing = [group for group in case['required'] if selected.isdisjoint(group)]
    useful = set(case['useful']) | {name for group in case['required'] for name in group}
    irrelevant = sorted(selected - useful - {'get_tool_docs'})
    return {'acceptable': not missing and not irrelevant, 'missing_groups': missing, 'irrelevant': irrelevant}


def _baseline():
    entries = get_tools_lst()
    names = guest_tool_names([entry.tool_name for entry in entries],
        visual_mode=True, orchestration_mode=OrchestrationMode.DAG_GUIDED, role_id='coordinator')
    manifest = tool_capability_manifest(names, orchestration_mode=OrchestrationMode.DAG_GUIDED, role_id='coordinator')
    all_contracts = tool_declarations(names, entries=entries,
        orchestration_mode=OrchestrationMode.DAG_GUIDED, role_id='coordinator')
    loader = build_tool_documents(['get_tool_docs'], allowed_names=names, entries=entries)[0]
    return entries, names, tool_capability_summaries(names, entries=entries), {
        'tool_count': len(names), 'catalog_tokens_estimate': estimate_tokens(manifest),
        'loader_tokens_estimate': estimate_tokens(loader.content),
        'all_contract_tokens_estimate': estimate_tokens(all_contracts),
        'tokenizer': 'cl100k_base; estimates exclude identity, task and dynamic snapshots',
    }


async def build_report(*, sources: list[str]) -> dict:
    entries, names, summaries, baseline = await asyncio.to_thread(_baseline)
    config = await asyncio.to_thread(lambda: get_config().tool_document_loading.model_copy(deep=True))
    agent = AgentSession(id='document-selection-evaluation', project_id='document-selection-evaluation',
        role_id='coordinator', display_name='Document selection evaluation')
    agent.settings.orchestration_mode = OrchestrationMode.DAG_GUIDED
    provider = LegacyLLMProvider()
    settings = await asyncio.to_thread(provider.resolve_effective_settings, agent)
    report = {'baseline': baseline, 'live_connections': {source: 'unverified' for source in ('llm', 'jev', 'reranker')},
        'measured_prompt_tokens': None, 'execution_validation': 'not_run',
        'scientific_evidence_validation': 'not_run', 'cases': []}
    failed_sources: set[str] = set()
    for case in CASES:
        row = {'id': case['id'], 'task': case['task'], 'sources': {}}
        for source in sources:
            if source in failed_sources:
                row['sources'][source] = {'status': 'unverified', 'error_code': 'previous_probe_failed'}
                continue
            try:
                selected_config = config.with_patch({'strategy': 'llm' if source == 'llm' else 'semantic',
                    **({'semantic_backend': source} if source != 'llm' else {})})
            except ValueError:
                row['sources'][source] = {'status': 'unverified', 'error_code': 'backend_not_configured'}
                continue
            result = await ToolDocumentSelector(provider).select(agent=agent,
                task_messages=[{'role': 'user', 'content': case['task']}],
                resolved_settings=settings, candidates=summaries, config=selected_config)
            if result.status == 'failed':
                failed_sources.add(source)
            docs = await asyncio.to_thread(build_tool_documents, list(result.names), allowed_names=names, entries=entries)
            document_tokens = sum(estimate_tokens(doc.content) for doc in docs if doc.name != 'get_tool_docs')
            row['sources'][source] = {**result.model_dump(mode='json'),
                'quality': grade_selection(case, list(result.names)) if result.status != 'failed' else None,
                'preload_tokens_estimate': document_tokens,
                'initial_document_tokens_estimate': baseline['catalog_tokens_estimate'] + baseline['loader_tokens_estimate'] + document_tokens,
                'measured_selection_prompt_tokens': result.usage.get('input_tokens', result.usage.get('prompt_tokens')),
            }
        report['cases'].append(row)
    for source in sources:
        statuses = [row['sources'][source]['status'] for row in report['cases']]
        successful = sum(status in ('selected', 'empty') for status in statuses)
        report['live_connections'][source] = 'verified' if successful == len(CASES) else 'partial' if successful else 'unverified'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='append', choices=['llm', 'jev', 'reranker'], default=[],
        help='Explicitly call a configured selection service; may be repeated.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(build_report(sources=list(dict.fromkeys(args.run))))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'live_connections': report['live_connections'],
        'baseline': report['baseline']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
