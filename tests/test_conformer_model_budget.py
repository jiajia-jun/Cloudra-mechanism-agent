from types import SimpleNamespace

import pytest

from tests.test_ts_pipeline_driver import waiting_process


@pytest.mark.asyncio
async def test_model_requests_count_retries_and_preserve_blocked_checkpoint(tmp_path):
    from cloudra.infra.llm_client import LLMClient
    from cloudra.services.conformer_model_budget import ModelRequestAccounting
    from cloudra.services.exploration_budget_store import ExplorationBudget, budget_usage, configure_budget
    from cloudra.services.ts_pipeline_store import get_process, save_process_record
    from cloudra.tools.core.ts_process import TsBlocked, TsProcessRecord

    db, pid, _ = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    record.catalog_id = "cat"
    record.waiting_for = ""
    record.blocked = TsBlocked(stage="build", failure_class="decision_needed", message="synthetic")
    configure_budget(
        db,
        process_id=pid,
        project_id="project",
        owner_id="owner",
        budget=ExplorationBudget(source="explicit_user", max_model_calls=2),
    )
    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    before = get_process(db, pid)["record"]
    accounting = await ModelRequestAccounting.for_agent(db, "project", "owner")
    client = LLMClient(api_key="fake", base_url="https://example.invalid")
    client.request_accounting = accounting
    calls = []

    async def failed():
        calls.append(1)
        raise RuntimeError("synthetic transport failure")

    async def successful():
        calls.append(1)
        return SimpleNamespace(usage=None)

    with pytest.raises(RuntimeError):
        await client._accounted_request(failed)
    await client._accounted_request(successful)
    with pytest.raises(ValueError, match="budget exhausted"):
        await client._accounted_request(successful)
    await accounting.finish(success=True, usage={"total_tokens": 27})
    assert len(calls) == 2
    assert budget_usage(db, pid).model_calls == 2
    assert get_process(db, pid)["record"] == before
    with db.connect() as con:
        import json

        actuals = [json.loads(r[0]) for r in con.execute("SELECT actual FROM exploration_actions ORDER BY action_key")]
    assert {a["terminal_state"] for a in actuals} == {"done", "failed"}
    assert sorted(a["model_tokens"] for a in actuals if a["model_tokens"] is not None) == [27]


@pytest.mark.asyncio
async def test_normal_waiting_process_does_not_reserve_model_request(tmp_path):
    from cloudra.services.conformer_model_budget import ModelRequestAccounting
    from cloudra.services.exploration_budget_store import ExplorationBudget, budget_usage, configure_budget

    db, pid, _ = waiting_process(tmp_path)
    configure_budget(
        db,
        process_id=pid,
        project_id="project",
        owner_id="owner",
        budget=ExplorationBudget(source="explicit_user", max_model_calls=0),
    )
    accounting = await ModelRequestAccounting.for_agent(db, "project", "owner")
    assert accounting is None
    assert budget_usage(db, pid).model_calls == 0


@pytest.mark.asyncio
async def test_existing_provider_budget_stops_transport_retry_without_new_request(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    import httpx
    import openai

    from cloudra.infra.llm_client import LLMClient
    from cloudra.runtime_v2.adapters import LegacyLLMProvider
    from cloudra.runtime_v2.schemas import RuntimeSettings
    from cloudra.services.exploration_budget_store import ExplorationBudget, budget_usage, configure_budget
    from cloudra.services.ts_pipeline_store import get_process, save_process_record
    from cloudra.tools.core.ts_process import TsBlocked, TsProcessRecord

    db, pid, _ = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    record.catalog_id = "cat"
    record.waiting_for = ""
    record.blocked = TsBlocked(stage="build", failure_class="decision_needed", message="synthetic")
    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    configure_budget(
        db,
        process_id=pid,
        project_id="project",
        owner_id="owner",
        budget=ExplorationBudget(source="explicit_user", max_model_calls=1),
    )
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.invalid"))
    create = AsyncMock(side_effect=openai.RateLimitError("synthetic", response=response, body={}))
    client = LLMClient(api_key="fake", base_url="https://example.invalid", max_retries=1)
    client._openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)), aclose=AsyncMock()
    )
    provider = LegacyLLMProvider(client_factory=lambda settings: client)

    async def no_delay(*args):
        pass

    monkeypatch.setattr("cloudra.infra.llm_client.asyncio.sleep", no_delay)
    agent = SimpleNamespace(
        project_id="project",
        id="owner",
        role_id="coordinator",
        current_run=None,
        settings=RuntimeSettings(
            model="synthetic", base_url="https://example.invalid", api_key="fake", invocation_protocol="traditional"
        ),
    )
    with pytest.raises(ValueError, match="budget exhausted"):
        await provider.complete(agent, [{"role": "user", "content": "synthetic decision"}], [])
    assert create.await_count == 1 and budget_usage(db, pid).model_calls == 1
    assert get_process(db, pid)["record"]["blocked"]["failure_class"] == "decision_needed"


@pytest.mark.asyncio
async def test_candidate_only_terminal_keeps_model_decision_budget(tmp_path):
    from cloudra.services.conformer_model_budget import ModelRequestAccounting
    from cloudra.services.exploration_budget_store import ExplorationBudget, configure_budget
    from cloudra.services.ts_pipeline_store import get_process, save_process_record
    from cloudra.tools.core.ts_process import TsProcessRecord
    db,pid,_=waiting_process(tmp_path)
    record=TsProcessRecord.model_validate(get_process(db,pid)['record'])
    record.catalog_id='cat'
    record.waiting_for=''
    record.terminal='candidate_only'
    configure_budget(db,process_id=pid,project_id='project',owner_id='owner',budget=ExplorationBudget(source='explicit_user',max_model_calls=0))
    save_process_record(db,process_id=pid,record=record.model_dump(mode='json'))
    accounting=await ModelRequestAccounting.for_agent(db,'project','owner')
    assert accounting is not None
    with pytest.raises(ValueError,match='budget exhausted'):
        await accounting.before_request()
