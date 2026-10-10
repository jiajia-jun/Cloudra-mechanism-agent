"""Selection quality accepts alternative tool sets; estimates are not live evidence."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope='module')
def report_module():
    path = Path(__file__).resolve().parents[1] / 'scripts/benchmarks/tool_document_selection.py'
    spec = importlib.util.spec_from_file_location('tool_document_selection_report', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_required_and_unrelated_documents_are_separate(report_module):
    case = next(case for case in report_module.CASES if case['id'] == 'logs')
    grade = report_module.grade_selection(case, ['search', 'molecule_drawer'])
    assert grade['missing_groups'] == [['log_parser']]
    assert grade['irrelevant'] == ['molecule_drawer']
    assert grade['acceptable'] is False


def test_alternative_sets_and_explanation_only_are_accepted(report_module):
    case = next(case for case in report_module.CASES if case['id'] == 'literature')
    assert report_module.grade_selection(case, ['browser'])['acceptable']
    case = next(case for case in report_module.CASES if case['id'] == 'explanation')
    assert report_module.grade_selection(case, [])['acceptable']


@pytest.mark.asyncio
async def test_baseline_reports_no_live_connection_or_scientific_verification(report_module):
    report = await report_module.build_report(sources=[])
    assert report['live_connections'] == {'llm': 'unverified', 'jev': 'unverified', 'reranker': 'unverified'}
    assert len(report['cases']) == 8
    assert report['baseline']['catalog_tokens_estimate'] < report['baseline']['all_contract_tokens_estimate']
    assert report['baseline']['all_contract_tokens_estimate'] > 0
    assert report['execution_validation'] == 'not_run'
    assert report['scientific_evidence_validation'] == 'not_run'
    assert report['measured_prompt_tokens'] is None


@pytest.mark.asyncio
async def test_live_failure_stops_remaining_backend_calls(report_module, monkeypatch):
    from cloudra.runtime_v2.schemas import RuntimeSettings
    calls = []

    class Unavailable:
        def resolve_effective_settings(self, agent):
            return RuntimeSettings()

        async def select_tool_names(self, *args, **kwargs):
            calls.append('attempt')
            raise RuntimeError('service unavailable')

    monkeypatch.setattr(report_module, 'LegacyLLMProvider', Unavailable)
    report = await report_module.build_report(sources=['llm'])
    assert len(calls) == 1
    assert report['live_connections']['llm'] == 'unverified'
    assert report['cases'][0]['sources']['llm']['status'] == 'failed'
    assert report['cases'][1]['sources']['llm']['error_code'] == 'previous_probe_failed'
