"""GuidanceStage：行为引导经 pin 常驻上下文通知（永不阻拦、按键幂等去重）。

通道纪律的回归守卫：行为引导（TS 走 ts_prepare、Coordinator 派单、bash
手写文件/坐标）不再进工具返回结果，而是 pin 进上下文；本文件同时钉住
TS/IRC 输入嗅探的 fail-soft 语义（读不出/不声明就不提示）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall, ToolResult
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


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("ts_prepare", {"declaration": {}}),
        ("ts_guess", {"mode": "scan_prepare"}),
        ("ts_guess", {"mode": "interpolate"}),
        ("ts_guess", {"mode": "xtb_path"}),
        ("qm_input_writer", {"task_type": [{"scan": "rigid"}]}),
        ("qm_input_writer", {"task_type": [{"opt": None}]}),
        ("qm_input_writer", {"task_type": [{"opt": "modredundant"}]}),
        ("submit_compute_job", {"job_type": "orca"}),
        ("submit_compute_job", {"job_type": "gaussian"}),
    ],
)
def test_molecular_pes_preparation_pins_nonblocking_guidance(name, arguments):
    notices = NoticeManager()
    ctx = _ctx("small_mol", notices)
    call = ToolCall(id="pes", name=name, arguments=arguments)
    result = _run(GuidanceStage(), ctx, call)
    assert result.outcome == "allow"
    assert notices.pin_content("as_g", "guidance-physical-thinking") is not None


def test_physical_guidance_replaces_unscoped_resident_method_policy_hint():
    notices = NoticeManager()
    notices.pin("as_g", "guidance-physical-thinking", "Always follow the global method policy.")
    result = _run(GuidanceStage(), _ctx("small_mol", notices),
                  ToolCall(id="prepare", name="ts_prepare", arguments={}))
    assert result.outcome == "allow"
    pin = notices.pin_content("as_g", "guidance-physical-thinking")
    assert pin is not None
    assert "Only active Benchmark projects use MethodPolicy" in pin
    assert "ordinary research projects have no default method/basis whitelist" in pin
    assert "global configuration, examples or past tasks" in pin
    assert len(notices.render_current("as_g")) == 1


def test_missing_ts_guess_mode_does_not_infer_a_compute_path():
    notices = NoticeManager()
    ctx = _ctx("small_mol", notices)
    result = _run(GuidanceStage(), ctx, ToolCall(id="missing-mode", name="ts_guess", arguments={}))
    assert result.outcome == "allow"
    assert notices.pin_content("as_g", "guidance-physical-thinking") is None


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("ts_guess", {"mode": "scan_parse"}),
        ("ts_guess", {"mode": "verify"}),
        ("ts_guess", {"mode": "scan", "log_path": "scan.log"}),
        ("submit_compute_job", {"job_type": "vasp"}),
        ("submit_compute_job", {"job_type": "cp2k"}),
        ("submit_compute_job", {"job_type": "xtb"}),
        ("submit_compute_job", {}),
        ("bash", {"command": "ls -la"}),
    ],
)
def test_unrelated_calls_do_not_pin_physical_guidance(name, arguments):
    notices = NoticeManager()
    call = ToolCall(id="other", name=name, arguments=arguments)
    assert _run(GuidanceStage(), _ctx("small_mol", notices), call).outcome == "allow"
    assert notices.pin_content("as_g", "guidance-physical-thinking") is None


def test_physical_guidance_is_idempotent_across_preparation_and_submit():
    notices = NoticeManager()
    ctx = _ctx("small_mol", notices)
    stage = GuidanceStage()
    _run(stage, ctx, ToolCall(id="prep", name="ts_prepare", arguments={}))
    _run(stage, ctx, ToolCall(id="submit", name="submit_compute_job", arguments={"job_type": "gaussian"}))
    _run(stage, ctx, ToolCall(id="again", name="ts_prepare", arguments={}))
    assert len(notices.render_current("as_g")) == 1


def _after(stage, ctx, call, result):
    return asyncio.run(stage.after_tool(ctx, call, result))


def _reflection_pins(notices, agent_id="as_g"):
    return {
        key: content
        for key, content in notices._pins.get(agent_id, {}).items()
        if key.startswith("guidance-scientific-reflection:")
    }


def _process_view(tmp_path):
    return {
        "run_id": "ts_observed", "run_dir": str(tmp_path / "attempt"),
        "status": "ended", "stage": "verdict",
        "result": {
            "outcome": "candidate_only", "verified": False,
            "reason": "Recorded endpoint connection was not established",
            "evidence_refs": [str(tmp_path / "attempt/irc.out")],
        },
    }


@pytest.mark.parametrize("tool", ["ts_prepare", "ts_resume", "ts_inspect"])
@pytest.mark.parametrize("outcome", ["candidate_only", "search_failed"])
def test_process_candidate_pins_evidence_guidance_without_altering_result(tmp_path, tool, outcome):
    notices = NoticeManager()
    data = _process_view(tmp_path)
    data["result"]["outcome"] = outcome
    result = ToolResult(is_success=True, data=data)
    _after(GuidanceStage(), _ctx("small_mol", notices),
           ToolCall(id="current", name=tool, arguments={"run_id": data["run_id"]}), result)
    pins = _reflection_pins(notices)
    assert len(pins) == 1
    content = next(iter(pins.values()))
    assert data["result"]["reason"] not in content
    assert "PROCESS.md" in content
    assert data["result"]["evidence_refs"][0] in content
    assert data["run_dir"] in content
    assert result.is_success and result.data == data


def test_process_reflection_updates_one_run_and_ignores_inspection_metadata(tmp_path):
    notices = NoticeManager()
    ctx = _ctx("small_mol", notices)
    stage = GuidanceStage()
    data = _process_view(tmp_path)
    _after(stage, ctx, ToolCall(id="first", name="ts_inspect", arguments={}),
           ToolResult(is_success=True, data=data))
    before = notices._local_seqs["as_g"]
    _after(stage, ctx, ToolCall(id="again", name="ts_inspect", arguments={}),
           ToolResult(is_success=True, data={**data, "revision": 42, "usage": {"wall_time_seconds": 99}}))
    assert notices._local_seqs["as_g"] == before
    _after(stage, ctx, ToolCall(id="new-evidence", name="ts_inspect", arguments={}),
           ToolResult(is_success=True, data={**data, "result": {
               **data["result"], "reason": "New recorded frequency evidence",
               "evidence_refs": [str(tmp_path / "attempt/frequency.out")],
           }}))
    assert len(_reflection_pins(notices)) == 1
    assert notices._local_seqs["as_g"] == before + 1
    assert str(tmp_path / "attempt/frequency.out") in next(iter(_reflection_pins(notices).values()))


@pytest.mark.parametrize("status,result", [
    ("waiting", None),
    ("running", None),
    ("ended", {"outcome": "verified", "verified": True, "reason": "Verified", "evidence_refs": []}),
])
def test_process_reflection_is_cleared_when_attempt_resumes_or_is_verified(tmp_path, status, result):
    notices = NoticeManager()
    stage = GuidanceStage()
    ctx = _ctx("small_mol", notices)
    data = _process_view(tmp_path)
    call = ToolCall(id="inspect", name="ts_inspect", arguments={})
    _after(stage, ctx, call, ToolResult(is_success=True, data=data))
    _after(stage, ctx, call, ToolResult(is_success=True, data={**data, "status": status, "result": result}))
    assert _reflection_pins(notices) == {}
    assert notices._local_seqs["as_g"] == 2


@pytest.mark.parametrize("failure_class", [
    "frequency_evidence_missing", "canonical_structure_unavailable", "compute_admission_rejected",
])
def test_process_engineering_block_does_not_pin_scientific_reflection(tmp_path, failure_class):
    data = {**_process_view(tmp_path), "status": "blocked", "result": None,
            "blocked": {"failure_class": failure_class, "message": "Repair the named input"}}
    notices = NoticeManager()
    _after(GuidanceStage(), _ctx("small_mol", notices),
           ToolCall(id="inspect", name="ts_inspect", arguments={}),
           ToolResult(is_success=True, data=data))
    assert _reflection_pins(notices) == {}


def test_process_wrong_mode_pins_recorded_failure_and_log(tmp_path):
    data = {**_process_view(tmp_path), "status": "blocked", "result": None,
            "blocked": {"failure_class": "wrong_mode", "message": "No first-order saddle found"},
            "failed_attempt": {"log_path": str(tmp_path / "attempt/frequency.out")}}
    notices = NoticeManager()
    _after(GuidanceStage(), _ctx("small_mol", notices),
           ToolCall(id="inspect", name="ts_inspect", arguments={}),
           ToolResult(is_success=True, data=data))
    content = next(iter(_reflection_pins(notices).values()))
    assert "target TS step" in content
    assert data["failed_attempt"]["log_path"] in content


def test_process_reflection_is_not_reinjected_after_notice_restore(tmp_path):
    log = EventLog(strict=True)
    notices = NoticeManager()
    notices.attach(log, lambda _agent_id: "project")
    data = _process_view(tmp_path)
    stage = GuidanceStage()
    call = ToolCall(id="first", name="ts_inspect", arguments={})
    _after(stage, _ctx("small_mol", notices), call, ToolResult(is_success=True, data=data))
    restored = NoticeManager()
    restored.attach(log, lambda _agent_id: "project")
    restored.restore_from(log)
    _after(stage, _ctx("small_mol", restored), call, ToolResult(is_success=True, data=data))
    assert len(_reflection_pins(restored)) == 1
    assert sum(event.type == "context.pin_set" for event in log) == 1


@pytest.mark.parametrize(
    ("mode", "arguments", "success", "data"),
    [
        ("scan_parse", {"log_path": "run/scan.log"}, True,
         {"scan_has_internal_peak": False, "candidate_unavailable": False}),
        ("scan_parse", {}, True,
         {"scan_has_internal_peak": False, "candidate_unavailable": False}),
        ("scan", {"log_path": "run/scan.log"}, True,
         {"scan_has_internal_peak": False, "candidate_unavailable": False}),
        ("verify", {"freq_log": "run/freq.log"}, True,
         {"verification_status": "fail"}),
        ("xtb_path", {"output_dir": "run/path"}, False,
         {"refinement_termination": "cycles_exhausted",
          "path_termination_reason": "path_not_converged"}),
    ],
)
def test_structured_ts_failure_pins_reflection_without_changing_result(
    tmp_path, mode, arguments, success, data,
):
    notices = NoticeManager()
    call = ToolCall(id="t", name="ts_guess", arguments={"mode": mode, **arguments})
    result = ToolResult(is_success=success, data=data)
    assert _after(GuidanceStage(), _ctx("small_mol", notices, str(tmp_path)), call, result) is None
    pins = _reflection_pins(notices)
    assert len(pins) == 1
    if mode in ("scan_parse", "scan") and arguments.get("log_path"):
        assert str(tmp_path / "run/scan.log") in next(iter(pins.values()))
    assert result.is_success is success and result.data == data


@pytest.mark.parametrize(
    ("name", "mode", "success", "data"),
    [
        ("log_parser", "scan_parse", True,
         {"scan_has_internal_peak": False, "candidate_unavailable": False}),
        ("ts_guess", "scan_prepare", True,
         {"scan_has_internal_peak": False, "candidate_unavailable": False}),
        ("ts_guess", "scan_parse", False,
         {"scan_has_internal_peak": False, "candidate_unavailable": False}),
        ("ts_guess", "scan_parse", True,
         {"scan_has_internal_peak": None, "candidate_unavailable": False}),
        ("ts_guess", "scan_parse", True,
         {"scan_has_internal_peak": False}),
        ("ts_guess", "scan_parse", True,
         {"scan_has_internal_peak": False, "candidate_unavailable": True}),
        ("ts_guess", "verify", True, {}),
        ("ts_guess", "verify", True, {"verification_status": "inconclusive"}),
        ("ts_guess", "verify", True, {"verification_status": "candidate"}),
        ("ts_guess", "xtb_path", False, {"refinement_termination": ""}),
        ("ts_guess", "xtb_path", False, {
            "refinement_termination": "cycles_exhausted",
            "path_termination_reason": "timeout",
        }),
    ],
)
def test_unrelated_or_incomplete_ts_results_do_not_pin_reflection(name, mode, success, data):
    notices = NoticeManager()
    arguments = {"mode": mode}
    if mode == "scan_parse":
        arguments["log_path"] = "scan.log"
    elif mode == "verify":
        arguments["freq_log"] = "freq.log"
    call = ToolCall(id="t", name=name, arguments=arguments)
    _after(GuidanceStage(), _ctx("small_mol", notices), call,
           ToolResult(is_success=success, data=data))
    assert _reflection_pins(notices) == {}


def test_ts_exception_result_does_not_pin_reflection():
    notices = NoticeManager()
    call = ToolCall(id="t", name="ts_guess", arguments={
        "mode": "scan_parse", "log_path": "scan.log",
    })
    result = ToolResult(
        is_success=True,
        data={"scan_has_internal_peak": False, "candidate_unavailable": False},
        error=SimpleNamespace(code="unexpected"),
    )
    _after(GuidanceStage(), _ctx("small_mol", notices), call, result)
    assert _reflection_pins(notices) == {}


def test_reflection_deduplicates_reparse_across_sources_and_call_ids(tmp_path):
    notices = NoticeManager()
    ctx = _ctx("small_mol", notices, str(tmp_path))
    stage = GuidanceStage()
    result = ToolResult(is_success=True, data={
        "scan_has_internal_peak": False, "candidate_unavailable": False,
        "profile_table": "0 0.0\n1 2.0",
    })
    a = ToolCall(id="a1", name="ts_guess", arguments={"mode": "scan_parse", "log_path": "a.log"})
    b = ToolCall(id="b1", name="ts_guess", arguments={"mode": "scan_parse", "log_path": "b.log"})
    _after(stage, ctx, a, result)
    _after(stage, ctx, b, result)
    before = notices._local_seqs["as_g"]
    _after(stage, ctx, ToolCall(id="b2", name="ts_guess", arguments={
        "mode": "scan_parse", "log_path": str(tmp_path / "b.log"),
    }), result)
    assert len(_reflection_pins(notices)) == 1
    assert str(tmp_path / "b.log") in next(iter(_reflection_pins(notices).values()))
    assert notices._local_seqs["as_g"] == before


def test_xtb_reflection_uses_actual_run_directory_for_attempt_identity(tmp_path):
    notices = NoticeManager()
    ctx = _ctx("small_mol", notices, str(tmp_path))
    stage = GuidanceStage()
    call = ToolCall(id="path", name="ts_guess", arguments={
        "mode": "xtb_path", "output_dir": "path-search",
    })
    for run_dir in ("path-search/run-1", "path-search/run-2", "path-search/run-1"):
        result = ToolResult(is_success=False, data={
            "refinement_termination": "cycles_exhausted",
            "path_termination_reason": "path_not_converged",
            "images_dir": run_dir,
        })
        _after(stage, ctx, call, result)
    pins = _reflection_pins(notices)
    assert len(pins) == 1
    assert str(tmp_path / "path-search/run-1") in next(iter(pins.values()))


def test_changed_profile_does_not_repeat_same_observation_or_print_evidence_hash(tmp_path):
    notices = NoticeManager()
    ctx = _ctx("small_mol", notices, str(tmp_path))
    call = ToolCall(id="a", name="ts_guess", arguments={
        "mode": "scan_parse", "log_path": "scan.log",
    })
    stage = GuidanceStage()
    data = {"scan_has_internal_peak": False, "candidate_unavailable": False}
    _after(stage, ctx, call, ToolResult(is_success=True, data={**data, "profile_table": "0 0\n1 2"}))
    first = _reflection_pins(notices)
    _after(stage, ctx, call, ToolResult(is_success=True, data={**data, "profile_table": "0 0\n1 3"}))
    second = _reflection_pins(notices)
    assert len(first) == len(second) == 1
    assert first == second
    assert "Evidence revision" not in next(iter(second.values()))


def test_reflection_is_agent_scoped_and_missing_sink_is_noop(tmp_path):
    notices = NoticeManager()
    call = ToolCall(id="t", name="ts_guess", arguments={
        "mode": "verify", "freq_log": "freq.log",
    })
    result = ToolResult(is_success=True, data={"verification_status": "fail"})
    stage = GuidanceStage()
    _after(stage, _ctx("small_mol", notices, str(tmp_path)), call, result)
    second = _ctx("small_mol", notices, str(tmp_path))
    second.agent.id = "as_other"
    _after(stage, second, call, result)
    assert len(_reflection_pins(notices, "as_g")) == 1
    assert len(_reflection_pins(notices, "as_other")) == 1
    assert _after(stage, _ctx("small_mol", None), call, result) is None


def test_reflection_reparse_after_notice_restore_does_not_emit_again(tmp_path):
    log = EventLog(strict=True)
    notices = NoticeManager()
    notices.attach(log, lambda _agent_id: "project")
    call = ToolCall(id="first", name="ts_guess", arguments={
        "mode": "scan_parse", "log_path": "scan.log",
    })
    result = ToolResult(is_success=True, data={
        "scan_has_internal_peak": False,
        "candidate_unavailable": False,
        "profile_table": "0 0\n1 2",
    })
    stage = GuidanceStage()
    _after(stage, _ctx("small_mol", notices, str(tmp_path)), call, result)
    assert sum(event.type == "context.pin_set" for event in log) == 1

    restored = NoticeManager()
    restored.attach(log, lambda _agent_id: "project")
    restored.restore_from(log)
    reparse = ToolCall(id="after-restart", name="ts_guess", arguments={
        "mode": "scan_parse", "log_path": str(tmp_path / "scan.log"),
    })
    _after(stage, _ctx("small_mol", restored, str(tmp_path)), reparse, result)
    assert len(_reflection_pins(restored)) == 1
    assert sum(event.type == "context.pin_set" for event in log) == 1


@pytest.mark.parametrize('mode', ['scan_prepare', 'interpolate', 'xtb_path'])
def test_manual_ts_preparation_pins_workflow_before_submission(mode):
    notices = NoticeManager()
    ctx = _ctx('small_mol', notices)
    stage = GuidanceStage()
    call = ToolCall(id='prepare', name='ts_guess', arguments={'mode': mode})
    _run(stage, ctx, call)
    assert notices.pin_content('as_g', 'guidance-ts-sop') is not None
    count = len(notices.render_current('as_g'))
    _run(stage, ctx, call)
    assert len(notices.render_current('as_g')) == count


def test_ts_notice_uses_inspection_and_grouped_explicit_inputs(tmp_path):
    path=tmp_path/'ts.inp'
    path.write_text('! OptTS HF STO-3G\n')
    notices=NoticeManager()
    _run(GuidanceStage(),_ctx('small_mol',notices,str(tmp_path)),_submit(str(path)))
    pin=notices.pin_content('as_g','guidance-ts-sop')
    assert 'ts_inspect' in pin and 'guess.calculation' in pin
    assert 'ts_resume(run_id) without adjustments' not in pin


def test_ts_notice_allows_retry_and_preserves_explicit_calculation_replacement():
    notices = NoticeManager()
    _run(GuidanceStage(), _ctx('small_mol', notices),
         ToolCall(id='prepare-contract', name='ts_guess', arguments={'mode': 'scan_prepare'}))
    pin = notices.pin_content('as_g', 'guidance-ts-sop')
    assert 'scan_recovery' not in pin
    assert 'changes={}' in pin
    assert 'basis_set' in pin
    assert 'replace' in pin
    assert 'without recovery evidence' not in pin


@pytest.mark.parametrize('key,old_content', [
    ('guidance-ts-sop', '[Guidance] Failed scans may retry without recovery evidence; use changes={}.'),
    ('guidance-physical-thinking', '[Guidance] Always follow the global method policy.'),
])
@pytest.mark.parametrize('fresh', [False, True])
def test_before_llm_refreshes_restored_static_guidance_in_actual_notice_batch(key, old_content, fresh):
    from cloudra.runtime_v2.policies.guidance import _PHYSICAL_THINKING_NOTICE, _TS_NOTICE

    log = EventLog(strict=True)
    old = NoticeManager()
    old.attach(log, lambda _session_id: 'project')
    old.pin('as_g', key, old_content)
    dynamic = {
        'guidance-scientific-reflection:attempt': 'Keep the recorded reflection and its evidence.',
        'guidance-delegate-compute': 'Keep the existing delegation guidance.',
        'guidance-handwritten-coords': 'Keep the existing coordinate guidance.',
    }
    for dynamic_key, content in dynamic.items():
        old.pin('as_g', dynamic_key, content)
    old.pin('as_other', key, old_content)
    restored = NoticeManager()
    restored.restore_from(log)
    restored.attach(log, lambda _session_id: 'project')
    if not fresh:
        restored.collect_batch('as_g', fresh=True)
        restored.confirm_consumed('as_g')
    before = sum(event.type == 'context.pin_set' for event in log)
    stage, ctx = GuidanceStage(), _ctx('small_mol', restored)
    asyncio.run(stage.before_llm(ctx, []))
    expected = _TS_NOTICE if key == 'guidance-ts-sop' else _PHYSICAL_THINKING_NOTICE
    assert restored.pin_content('as_g', key) == expected
    assert restored.pin_content('as_other', key) == old_content
    for dynamic_key, content in dynamic.items():
        assert restored.pin_content('as_g', dynamic_key) == content
    batch = restored.collect_batch('as_g', fresh=fresh)
    assert any(expected in message['content'] for message in batch)
    assert not any(old_content in message['content'] for message in batch)
    assert sum(event.type == 'context.pin_set' for event in log) == before + 1
    restored.confirm_consumed('as_g')
    asyncio.run(stage.before_llm(ctx, []))
    assert restored.collect_batch('as_g', fresh=False) == []
    assert sum(event.type == 'context.pin_set' for event in log) == before + 1


def test_before_llm_does_not_create_static_guidance_for_agents_without_existing_pins():
    notices = NoticeManager()
    notices.pin('as_g', 'guidance-scientific-reflection:attempt', 'Existing dynamic evidence guidance')
    stage, ctx = GuidanceStage(), _ctx('small_mol', notices)
    asyncio.run(stage.before_llm(ctx, []))
    assert notices.pin_content('as_g', 'guidance-ts-sop') is None
    assert notices.pin_content('as_g', 'guidance-physical-thinking') is None
    assert notices.render_current('as_g') == [{'role': 'system', 'content': 'Existing dynamic evidence guidance'}]


def test_before_llm_static_guidance_refresh_without_notice_sink_is_noop():
    messages = [{'role': 'user', 'content': 'Continue the current task'}]
    assert asyncio.run(GuidanceStage().before_llm(_ctx('small_mol', None), messages)) is None
    assert messages == [{'role': 'user', 'content': 'Continue the current task'}]


def test_scientific_reflection_is_one_slot_across_tools_and_process_runs(tmp_path):
    notices = NoticeManager()
    notices.pin('as_g', 'guidance-delegate-compute', 'Keep delegation')
    stage, ctx = GuidanceStage(), _ctx('small_mol', notices, str(tmp_path))
    for number in range(12):
        _after(stage, ctx, ToolCall(id=str(number), name='ts_guess', arguments={
            'mode': 'scan_parse', 'log_path': f'scan-{number}.out'}),
            ToolResult(is_success=True, data={'scan_has_internal_peak': False, 'candidate_unavailable': False}))
        data = {**_process_view(tmp_path), 'run_id': f'ts_{number}'}
        _after(stage, ctx, ToolCall(id=str(number), name='ts_inspect', arguments={}),
               ToolResult(is_success=True, data=data))
        pins = _reflection_pins(notices)
        assert list(pins) == [f'guidance-scientific-reflection:ts-process:ts_{number}']
    assert notices.pin_content('as_g', 'guidance-delegate-compute') == 'Keep delegation'


@pytest.mark.parametrize('status,result', [
    ('running', None), ('waiting', None),
    ('ended', {'outcome': 'verified', 'verified': True, 'evidence_refs': []}),
])
def test_old_process_progress_cannot_clear_current_other_process_reflection(tmp_path, status, result):
    notices = NoticeManager()
    stage, ctx = GuidanceStage(), _ctx('small_mol', notices)
    data = _process_view(tmp_path)
    for run in ('ts_old', 'ts_current'):
        _after(stage, ctx, ToolCall(id=run, name='ts_inspect', arguments={}),
               ToolResult(is_success=True, data={**data, 'run_id': run}))
    _after(stage, ctx, ToolCall(id='old-event', name='ts_inspect', arguments={}),
           ToolResult(is_success=True, data={**data, 'run_id': 'ts_old', 'status': status, 'result': result}))
    assert list(_reflection_pins(notices)) == ['guidance-scientific-reflection:ts-process:ts_current']


@pytest.mark.parametrize('mode,source,failure,confirmed', [
    ('scan_parse', {'log_path': 'scan.out'}, {'scan_has_internal_peak': False, 'candidate_unavailable': False},
        {'scan_has_internal_peak': True, 'candidate_unavailable': False}),
    ('verify', {'freq_log': 'frequency.out'}, {'verification_status': 'fail'}, {'verification_status': 'pass'}),
    ('xtb_path', {'output_dir': 'path', 'images_dir': 'path/run'},
        {'refinement_termination': 'cycles_exhausted', 'path_termination_reason': 'path_not_converged', 'images_dir': 'path/run'},
        {'refinement_termination': 'converged', 'images_dir': 'path/run'}),
])
def test_confirmed_tool_evidence_clears_only_its_current_source(tmp_path, mode, source, failure, confirmed):
    notices = NoticeManager()
    stage, ctx = GuidanceStage(), _ctx('small_mol', notices, str(tmp_path))
    call = ToolCall(id='source', name='ts_guess', arguments={'mode': mode, **source})
    _after(stage, ctx, call, ToolResult(is_success=mode != 'xtb_path', data=failure))
    _after(stage, ctx, call, ToolResult(is_success=True, data=confirmed))
    assert _reflection_pins(notices) == {}
    _after(stage, ctx, call, ToolResult(is_success=mode != 'xtb_path', data=failure))
    _after(stage, ctx, ToolCall(id='other', name='ts_inspect', arguments={}),
           ToolResult(is_success=True, data=_process_view(tmp_path)))
    _after(stage, ctx, call, ToolResult(is_success=True, data=confirmed))
    assert list(_reflection_pins(notices)) == ['guidance-scientific-reflection:ts-process:ts_observed']


@pytest.mark.parametrize('already_consumed', [False, True])
def test_before_llm_collapses_restored_reflections_by_last_update_and_is_agent_scoped(tmp_path, already_consumed):
    log = EventLog(strict=True)
    old = NoticeManager()
    old.attach(log, lambda _agent: 'project')
    prefix = 'guidance-scientific-reflection:'
    old.pin('as_g', prefix + 'first', 'First old observation')
    old.pin('as_g', prefix + 'second', 'Second old observation')
    old.pin('as_g', prefix + 'first', 'Latest updated observation')
    old.pin('as_g', 'task-goal', 'Keep task goal')
    old.pin('as_other', prefix + 'other', 'Other agent observation')
    restored = NoticeManager()
    restored.restore_from(log)
    restored.attach(log, lambda _agent: 'project')
    if already_consumed:
        restored.collect_batch('as_g', fresh=True)
        restored.confirm_consumed('as_g')
    stage, ctx = GuidanceStage(), _ctx('small_mol', restored)
    asyncio.run(stage.before_llm(ctx, []))
    assert _reflection_pins(restored) == {prefix + 'first': 'Latest updated observation'}
    assert restored.pin_content('as_g', 'task-goal') == 'Keep task goal'
    assert _reflection_pins(restored, 'as_other') == {prefix + 'other': 'Other agent observation'}
    assert not any('Second old observation' in row['content'] for row in restored.collect_batch('as_g', fresh=True))
    restored.confirm_consumed('as_g')
    before = len(log)
    asyncio.run(stage.before_llm(ctx, []))
    assert len(log) == before
    assert restored.collect_batch('as_g', fresh=False) == []


def test_process_hint_does_not_expand_with_reason_or_evidence_history(tmp_path):
    stage = GuidanceStage()
    data = _process_view(tmp_path)
    one = NoticeManager()
    _after(stage, _ctx('small_mol', one), ToolCall(id='one', name='ts_inspect', arguments={}),
           ToolResult(is_success=True, data=data))
    data['result']['reason'] = 'large-log-sentinel' * 1000
    data['result']['evidence_refs'].extend(str(tmp_path / f'old-{n}.out') for n in range(2000))
    many = NoticeManager()
    _after(stage, _ctx('small_mol', many), ToolCall(id='many', name='ts_inspect', arguments={}),
           ToolResult(is_success=True, data=data))
    assert next(iter(_reflection_pins(one).values())) == next(iter(_reflection_pins(many).values()))
    assert 'large-log-sentinel' not in next(iter(_reflection_pins(many).values()))
