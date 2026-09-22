"""真实模型评测模块的单测：只覆盖 fake 路径与「拒绝」路径，零真实 key。

真实调用路径（--provider real --confirm-real-api + config 槽位有 key）不进本文件，
也不进任何需要 key 的 CI（评审 5.8）。
"""

from __future__ import annotations

import json

import pytest

from tests import real_model_eval as rme
from tests.real_model_eval import (
    ConfigSlotSummary,
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
