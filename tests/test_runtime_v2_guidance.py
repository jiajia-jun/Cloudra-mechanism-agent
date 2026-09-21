"""GuidanceStage：行为引导经 pin 常驻上下文通知（永不阻拦、按键幂等去重）。

通道纪律的回归守卫：行为引导（TS 走 ts_prepare、Coordinator 派单、bash
手写文件/坐标）不再进工具返回结果，而是 pin 进上下文；本文件同时钉住
TS/IRC 输入嗅探的 fail-soft 语义（读不出/不声明就不提示）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall
from cloudra.runtime_v2.policies.guidance import GuidanceStage, sniff_ts_or_irc_input
from cloudra.runtime_v2.schemas import AgentCapabilities, PermissionSet, RuntimeSettings


def _ctx(role_id: str, notices, workspace_dir: str | None = None) -> PipelineContext:
    return PipelineContext(
        agent=SimpleNamespace(id="as_g", role_id=role_id),
        run_id="r",
        settings_snapshot=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        emit=lambda *_args, **_kwargs: None,
        workspace_dir=workspace_dir,
        notices=notices,
    )


def _run(stage, ctx, call):
    return asyncio.run(stage.before_tool(ctx, call))


def _submit(path: str) -> ToolCall:
    return ToolCall(id="t1", name="submit_compute_job", arguments={"input_file": path})


def _bash(command: str) -> ToolCall:
    return ToolCall(id="t2", name="bash", arguments={"command": command})


# ---------------------------------------------------------------- 嗅探纯函数


def test_sniff_detects_ts_irc_qst_routes():
    assert sniff_ts_or_irc_input("! B3LYP def2-SVP OptTS Freq\n")
    assert sniff_ts_or_irc_input("# opt=(ts,calcfc,noeigentest) b3lyp/def2svp\n")
    assert sniff_ts_or_irc_input("# qst2 b3lyp/def2svp\n")
    assert sniff_ts_or_irc_input("! IRC\n%irc MaxIter 50 end\n")
    assert sniff_ts_or_irc_input("# irc=calcfC\n")


def test_sniff_ignores_plain_and_scan_jobs():
    assert not sniff_ts_or_irc_input("! B3LYP def2-SVP Opt Freq\n")
    assert not sniff_ts_or_irc_input("# opt b3lyp/def2svp\n")
    # 松弛扫描是 agent 侧正当手段，不触发 TS 引导
    assert not sniff_ts_or_irc_input("# opt=modredundant b3lyp/def2svp\nB 1 2 S 10 0.1\n")
    assert not sniff_ts_or_irc_input("")


# ---------------------------------------------------------------- submit 引导


def test_ts_submission_pins_sop_guidance(tmp_path):
    inp = tmp_path / "ts.inp"
    inp.write_text("! OptTS B3LYP def2-SVP\n* xyz 0 1\nC 0 0 0\n*\n", encoding="utf-8")
    notices = NoticeManager()
    result = _run(GuidanceStage(), _ctx("small_mol", notices, str(tmp_path)), _submit("ts.inp"))
    assert result.outcome == "allow"
    pin = notices.pin_content("as_g", "guidance-ts-sop")
    assert pin is not None and "ts_prepare" in pin and "QST2/QST3" in pin


def test_plain_opt_submission_no_pin(tmp_path):
    inp = tmp_path / "opt.inp"
    inp.write_text("! B3LYP def2-SVP Opt\n* xyz 0 1\nC 0 0 0\n*\n", encoding="utf-8")
    notices = NoticeManager()
    _run(GuidanceStage(), _ctx("small_mol", notices, str(tmp_path)), _submit("opt.inp"))
    assert notices.pin_content("as_g", "guidance-ts-sop") is None


def test_unreadable_input_file_is_fail_soft(tmp_path):
    notices = NoticeManager()
    result = _run(
        GuidanceStage(), _ctx("small_mol", notices, str(tmp_path)), _submit("ghost.inp")
    )
    assert result.outcome == "allow"
    assert notices.pin_content("as_g", "guidance-ts-sop") is None


def test_coordinator_submission_pins_delegation(tmp_path):
    inp = tmp_path / "opt.inp"
    inp.write_text("! B3LYP def2-SVP Opt\n", encoding="utf-8")
    notices = NoticeManager()
    _run(GuidanceStage(), _ctx("coordinator", notices, str(tmp_path)), _submit("opt.inp"))
    pin = notices.pin_content("as_g", "guidance-delegate-compute")
    assert pin is not None and "small_mol" in pin


def test_expert_submission_no_delegation_pin(tmp_path):
    inp = tmp_path / "opt.inp"
    inp.write_text("! B3LYP def2-SVP Opt\n", encoding="utf-8")
    notices = NoticeManager()
    _run(GuidanceStage(), _ctx("small_mol", notices, str(tmp_path)), _submit("opt.inp"))
    assert notices.pin_content("as_g", "guidance-delegate-compute") is None


def test_pin_is_idempotent_across_calls(tmp_path):
    inp = tmp_path / "ts.inp"
    inp.write_text("! OptTS B3LYP def2-SVP\n", encoding="utf-8")
    notices = NoticeManager()
    stage = GuidanceStage()
    ctx = _ctx("small_mol", notices, str(tmp_path))
    _run(stage, ctx, _submit("ts.inp"))
    _run(stage, ctx, _submit("ts.inp"))
    # 幂等：重复 pin 同内容不产生新事件（NoticeManager 按键去重）
    pins = notices.render_current("as_g")
    assert len(pins) == 1


# ---------------------------------------------------------------- bash 引导


def test_bash_handwritten_coords_pin(tmp_path):
    command = (
        "cat > ts.gjf <<'EOF'\n0 1\nC 1.66 -0.67 0.05\nC 1.66 0.67 0.05\n"
        "H 1.74 -1.24 -0.87\nEOF"
    )
    notices = NoticeManager()
    _run(GuidanceStage(), _ctx("small_mol", notices, str(tmp_path)), _bash(command))
    pin = notices.pin_content("as_g", "guidance-handwritten-coords")
    assert pin is not None and "smiles_to_mol" in pin


def test_bash_file_write_pin(tmp_path):
    notices = NoticeManager()
    _run(GuidanceStage(), _ctx("small_mol", notices, str(tmp_path)),
         _bash("echo hello > out.txt"))
    assert notices.pin_content("as_g", "guidance-bash-file-write") is not None


def test_bash_harmless_command_no_pin(tmp_path):
    notices = NoticeManager()
    _run(GuidanceStage(), _ctx("small_mol", notices, str(tmp_path)), _bash("ls -la"))
    assert notices.render_current("as_g") == []


def test_no_notices_sink_is_noop(tmp_path):
    ctx = _ctx("small_mol", None, str(tmp_path))
    result = _run(GuidanceStage(), ctx, _bash("echo x > y.txt"))
    assert result.outcome == "allow"
