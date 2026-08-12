"""对话级按-agent 上下文统计。"""

from __future__ import annotations

import json
from pathlib import Path

from cloudra.infra.config import get_config
from cloudra.persistence.context_stats import (
    collect_conversation_context_stats,
    format_context_report,
    format_status_bar_context_info,
)
from cloudra.services.service import SessionRecord


def _write_jsonl(path: Path, messages: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in messages) + "\n",
        encoding="utf-8",
    )


def test_collect_splits_agents_and_roles(tmp_path, monkeypatch):
    get_config().data_dir = tmp_path
    conv = "conv_stats_demo"
    base = tmp_path / "conversations" / conv / "contexts"
    _write_jsonl(
        base / "a-0.json",
        [
            {"role": "system", "content": "[Skill 资料] big " + ("x" * 200)},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
    )
    _write_jsonl(
        base / "supervisor.json",
        [
            {"role": "user", "content": "trigger"},
            {"role": "assistant", "content": "view"},
        ],
    )
    _write_jsonl(
        base / "sessions" / "a-4_a-4_task1.json",
        [
            {"role": "system", "content": "follower"},
            {"role": "assistant", "content": "working"},
        ],
    )

    records = [
        SessionRecord(
            session_id="a-0_run",
            agent_id="a-0",
            agent_type="coordinator",
            parent_session_id=None,
            query="q",
            state="completed",
            result=None,
            error=None,
            pid=None,
            worker_id=None,
            created_at=None,
            started_at=None,
            heartbeat_at=None,
            finished_at=None,
            exit_code=None,
        ),
        SessionRecord(
            session_id="a-4_task1",
            agent_id="a-4",
            agent_type="dft",
            parent_session_id="a-0_run",
            query="opt",
            state="completed",
            result=None,
            error=None,
            pid=None,
            worker_id=None,
            created_at=None,
            started_at=None,
            heartbeat_at=None,
            finished_at=None,
            exit_code=None,
        ),
    ]

    stats = collect_conversation_context_stats(conv, session_records=records)
    assert len(stats.agents) == 3
    keys = {a.key for a in stats.agents}
    assert keys == {"a-0", "supervisor", "a-4/a-4_task1"}
    coord = next(a for a in stats.agents if a.key == "a-0")
    assert coord.messages == 3
    assert coord.skill_pin_tokens > 0
    assert "system" in coord.by_role
    assert stats.total_messages == 3 + 2 + 2
    assert stats.total_tokens == sum(a.tokens for a in stats.agents)

    bar = format_status_bar_context_info(stats)
    assert "Coordinator" in bar
    assert "3路Σ" in bar

    report = format_context_report(stats, focus_key="a-0", include_previews=True)
    assert "Supervisor" in report or "supervisor" in report
    assert "Skill钉" in report
    assert "tiktoken" in report


def test_status_bar_single_agent(tmp_path):
    get_config().data_dir = tmp_path
    conv = "conv_only_coord"
    base = tmp_path / "conversations" / conv / "contexts"
    _write_jsonl(base / "a-0.json", [{"role": "user", "content": "only"}])
    stats = collect_conversation_context_stats(conv)
    assert len(stats.agents) == 1
    assert "路Σ" not in format_status_bar_context_info(stats)
