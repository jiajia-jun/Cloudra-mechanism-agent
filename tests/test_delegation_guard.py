"""Coordinator 自行提交计算的轻量提示（delegation_guard）。"""

from types import SimpleNamespace

from cloudra.tools.Chemtool.submit_compute_job import (
    SubmitComputeJob,
    SubmitComputeJob_output_schema,
)
from cloudra.tools.core.delegation_guard import coordinator_self_compute_warning


def test_warning_only_for_coordinator():
    assert coordinator_self_compute_warning(SimpleNamespace(type="coordinator")) is not None
    assert coordinator_self_compute_warning(SimpleNamespace(type="follower")) is None
    assert coordinator_self_compute_warning(SimpleNamespace(type="dft")) is None
    assert coordinator_self_compute_warning(None) is None
    assert coordinator_self_compute_warning(SimpleNamespace()) is None


def test_warning_mentions_delegation():
    warning = coordinator_self_compute_warning(SimpleNamespace(type="coordinator"))
    assert "Coordinator" in warning
    assert "子 Agent" in warning
    assert "submit_compute_job" in warning


def test_submit_output_gets_hint_for_coordinator():
    tool = SubmitComputeJob()
    tool.subagent = SimpleNamespace(type="coordinator", conversation_id="test")
    out = tool._with_delegation_hint(
        SubmitComputeJob_output_schema(
            is_success=True,
            job_id=1,
            job_dir="/tmp",
            state="ready",
            message="任务已提交到 local 后端，将会在终态时唤醒。",
        )
    )
    assert out.is_success
    assert out.message.startswith("【提示：Coordinator 自行提交计算】")
    assert "任务已提交到 local 后端" in out.message


def test_submit_output_unchanged_for_follower():
    tool = SubmitComputeJob()
    tool.subagent = SimpleNamespace(type="follower", conversation_id="test")
    original = "任务运行完毕，最终状态：done"
    out = tool._with_delegation_hint(
        SubmitComputeJob_output_schema(
            is_success=True,
            job_id=2,
            job_dir="/tmp",
            state="done",
            message=original,
        )
    )
    assert out.message == original


def test_failed_submit_skips_hint():
    tool = SubmitComputeJob()
    tool.subagent = SimpleNamespace(type="coordinator", conversation_id="test")
    out = tool._with_delegation_hint(
        SubmitComputeJob_output_schema(
            is_success=False,
            message="文件或目录不存在。",
        )
    )
    assert out.message == "文件或目录不存在。"
