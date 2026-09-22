"""真实模型评测模块的单测：只覆盖 fake 路径与「拒绝」路径，零真实 key。

真实调用路径（--provider real --confirm-real-api + config 槽位有 key）不进本文件，
也不进任何需要 key 的 CI（评审 5.8）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import real_model_eval as rme
from tests.real_model_eval import (
    BudgetedProvider,
    ConfigSlotSummary,
    EvalBudgetExceeded,
    RunOptions,
    real_run_precondition,
    run_all,
    summarize_lines,
    write_results,
)


def _slot(*, key_set: bool) -> ConfigSlotSummary:
    return ConfigSlotSummary(
        model="test-model",
        endpoint={"redacted": "https://example.invalid/v1"},
        key_set=key_set,
        timeout=60,
        context_window=8192,
        reasoning_effort=None,
        native_search="off",
    )


def test_real_path_requires_explicit_opt_in():
    reason = real_run_precondition(opt_in=False)
    assert reason and "--confirm-real-api" in reason


def test_real_path_refuses_when_slot_has_no_key(monkeypatch):
    monkeypatch.setattr(rme, "config_slot_summary", lambda slot="coordinator": _slot(key_set=False))
    reason = real_run_precondition(opt_in=True)
    assert reason and "key" in reason


def test_real_path_refuses_partial_run_when_child_slot_has_no_key(monkeypatch):
    def fake(slot: str = "coordinator") -> ConfigSlotSummary:
        return _slot(key_set=(slot == "coordinator"))

    monkeypatch.setattr(rme, "config_slot_summary", fake)
    reason = real_run_precondition(opt_in=True, spawns_children=True)
    assert reason and "follower" in reason


def test_cli_main_refuses_real_without_opt_in(monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    script = Path(rme.REPO_ROOT) / "scripts" / "eval_real_model.py"
    spec = importlib.util.spec_from_file_location("eval_real_model_entry", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--provider", "real"]) == 2
    assert "--confirm-real-api" in capsys.readouterr().err


def test_cli_refuses_child_scenario_without_follower_key(monkeypatch, capsys, tmp_path):
    import importlib.util
    from pathlib import Path

    script = Path(rme.REPO_ROOT) / "scripts" / "eval_real_model.py"
    spec = importlib.util.spec_from_file_location("eval_real_model_entry", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        rme,
        "config_slot_summary",
        lambda slot="coordinator": _slot(key_set=(slot == "coordinator")),
    )

    async def fake_run_all(_options):
        return {"run_id": "test", "summary": {"failed": 0}}

    monkeypatch.setattr(module, "run_all", fake_run_all)
    monkeypatch.setattr(module, "summarize_lines", lambda _document: [])
    monkeypatch.setattr(module, "write_results", lambda _document, path: path)
    assert module.main([
        "--provider", "real", "--confirm-real-api",
        "--scenarios", "delegation_report_once", "--out", str(tmp_path / "out.json"),
    ]) == 2
    assert "follower" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_budget_counts_failed_provider_attempts():
    class FailingProvider:
        def __init__(self):
            self.attempts = 0

        async def complete(self, _agent, _messages, _tools, **_kwargs):
            self.attempts += 1
            raise RuntimeError("transient failure")

    inner = FailingProvider()
    provider = BudgetedProvider(inner, max_calls=1, label="failure_retries")
    with pytest.raises(RuntimeError, match="transient failure"):
        await provider.complete(None, [], [])
    with pytest.raises(EvalBudgetExceeded):
        await provider.complete(None, [], [])
    assert inner.attempts == 1
    assert provider.stats.as_dict()["llm_calls"] == 1
    assert provider.stats.as_dict()["llm_failures"] == 1


@pytest.mark.asyncio
async def test_zero_call_budget_never_invokes_provider(tmp_path):
    document = await run_all(RunOptions(
        provider_kind="fake",
        work_dir=tmp_path,
        timeout_s=10.0,
        max_llm_calls=0,
        scenario_names=["plain_qa"],
    ))
    assert document["scenarios"][0]["provider"]["llm_calls"] == 0
    assert document["summary"]["failed"] == 1


@pytest.mark.asyncio
async def test_fixture_workspace_stays_inside_eval_work_dir(tmp_path):
    eval_dir = tmp_path / "eval"
    document = await run_all(RunOptions(
        provider_kind="fake",
        work_dir=eval_dir,
        timeout_s=60.0,
        scenario_names=["read_fixture_token"],
    ))
    row = document["scenarios"][0]
    fixture_path = row["observations"]["workspace_files"]["EVAL_FIXTURE.txt"]
    assert eval_dir in Path(fixture_path).parents
    assert not (tmp_path / "data" / "conversations").exists()


@pytest.mark.asyncio
async def test_fake_read_fixture_scenario_repeats_seeded_token(tmp_path):
    document = await run_all(RunOptions(
        provider_kind="fake",
        work_dir=tmp_path / "eval",
        timeout_s=60.0,
        scenario_names=["read_fixture_token"],
    ))
    row = document["scenarios"][0]
    assert row["passed"] is True, [check for check in row["checks"] if not check["ok"]]


@pytest.mark.asyncio
async def test_real_style_child_scenario_restores_without_api(monkeypatch, tmp_path):
    spec = rme.scenario_by_name("restart_no_replay")
    assert spec is not None
    monkeypatch.setattr(rme, "build_real_provider", lambda: rme.build_fake_provider(spec))
    document = await run_all(RunOptions(
        provider_kind="real",
        work_dir=tmp_path / "eval",
        timeout_s=60.0,
        scenario_names=[spec.name],
    ))
    row = document["scenarios"][0]
    assert row["passed"] is True, [check for check in row["checks"] if not check["ok"]]
    assert any(check["name"] == "restart_restored" and check["ok"] for check in row["checks"])


@pytest.mark.asyncio
async def test_result_redacts_provider_error_url_and_api_key(monkeypatch, tmp_path):
    from cloudra.infra.config import get_config

    secret = "DEMO_SECRET"
    query_secret = "UNRELATED_QUERY_SECRET"
    monkeypatch.setattr(get_config().coordinator, "key", secret)
    message = (
        f"401 Error for url https://user:{secret}@example.invalid/v1?opaque={query_secret}: "
        f"upstream echoed {secret}"
    )

    class FailingProvider:
        async def complete(self, _agent, _messages, _tools, **_kwargs):
            raise RuntimeError(message)

    monkeypatch.setattr(rme, "build_real_provider", FailingProvider)
    document = await run_all(RunOptions(
        provider_kind="real",
        work_dir=tmp_path / "eval",
        timeout_s=10.0,
        max_turn_retries=0,
        scenario_names=["plain_qa"],
    ))
    result_text = json.dumps(document)
    assert secret not in result_text
    assert query_secret not in result_text
    assert "opaque=" not in result_text
    assert "user:" not in result_text
    assert "https://example.invalid" in result_text
    row = document["scenarios"][0]
    row["error"] = message
    row["checks"].append({"name": "synthetic_error", "ok": False, "detail": message})
    row["observations"]["nested_error"] = {"messages": [message]}
    written = write_results(document, tmp_path / "result.json")
    persisted = written.read_text(encoding="utf-8")
    assert secret not in persisted
    assert query_secret not in persisted
    assert "user:" not in persisted
    summary = "\n".join(summarize_lines(document))
    assert secret not in summary
    assert query_secret not in summary


@pytest.mark.asyncio
async def test_fake_path_runs_one_scenario_and_records_trend_metadata(tmp_path):
    options = RunOptions(
        provider_kind="fake",
        work_dir=tmp_path,
        timeout_s=60.0,
        max_llm_calls=6,
        scenario_names=["plain_qa"],
    )
    document = await run_all(options)
    assert document["schema"] == rme.SCHEMA
    assert document["provider_kind"] == "fake"
    assert document["summary"]["total"] == 1
    assert document["evaluation_scope"]["domain"] == "generic_agent_behavior"
    assert document["evaluation_scope"]["dag_delivery_semantics"] == "not_evaluated"
    row = document["scenarios"][0]
    assert row["name"] == "plain_qa"
    assert row["checks"], "检查面不能为空（每条不变量都要留证据）"
    assert row["passed"] is True, [c for c in row["checks"] if not c["ok"]]
    meta = document["metadata"]
    assert meta["prompt_revision"]["sha256"], "要记录 prompt revision 供趋势对比"
    assert meta["tool_catalog_revision"]["sha256"], "要记录 tool catalog revision"
    assert meta["randomness"]["max_llm_calls_per_scenario"] == 6
    assert meta["model"]["configured"] is not None
    out = write_results(document, tmp_path / "fake.json")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["schema"] == document["schema"]
    assert loaded["summary"]["passed"] == 1
    assert any("plain_qa" in line for line in summarize_lines(document))
    assert any("DAG delivery" in line and "not evaluated" in line for line in summarize_lines(document))
