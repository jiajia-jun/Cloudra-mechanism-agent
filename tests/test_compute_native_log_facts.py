"""Native termination, optimization and science remain separate facts."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cloudra.dag.evidence_inbox import EvidenceInboxMixin
from cloudra.dag.fact_adapters import log_parser_facts
from cloudra.dag.file_science import _ts_optimization_check
from cloudra.dag.models import GraphRef
from cloudra.infra.slurm import _engine_success_from_log
from cloudra.runtime import monitor
from cloudra.runtime.remote_compute import _terminal_verdict
from cloudra.tools.Chemtool.log_parser import LogParser
from cloudra.tools.core import gaussian_frames, orca_frames
from cloudra.tools.core.irc_evidence import normal_log

FIXTURES = Path(__file__).parent / "fixtures"
FIELDS = LogParser._resolve_requested_fields(["convergence", "job_type"])


@pytest.mark.asyncio
@pytest.mark.parametrize("engine,fixture,failure", [
    ("gaussian", "gaussian/water_opt_freq_g16.out",
     " Error termination via Lnk1e in /synthetic/g16/l9999.exe"),
    ("orca", "orca/co2_freq_orca42.out",
     "ORCA finished by error termination in /synthetic/orca_scf"),
])
async def test_later_native_error_invalidates_historical_success_everywhere(
    tmp_path, monkeypatch, engine, fixture, failure,
):
    # Captured success fixture plus an explicitly synthetic later native failure.
    log = tmp_path / "synthetic_success_then_error.out"
    log.write_text((FIXTURES / fixture).read_text() + "\n" + failure + "\n")
    native = gaussian_frames if engine == "gaussian" else orca_frames
    result = LogParser()._parse_log(str(log), FIELDS)
    data, ok = await monitor._parse_log(log, 1, job_type=engine)
    monkeypatch.setattr("cloudra.infra.compute_utils.resolve_log_path", lambda *_a, **_k: str(log))
    remote_ok = _engine_success_from_log(engine, str(tmp_path / "input"))

    # Exercise real finalization while replacing only the external ledger/inbox.
    ledger = AsyncMock(return_value=True)
    monkeypatch.setattr(monitor, "afinalize_compute_job", ledger)
    monkeypatch.setattr("cloudra.dag.controller.enqueue_compute_review", AsyncMock())
    await monitor._finalize(None, 1, log, str(tmp_path), 1, engine, 1)

    assert result.is_success is True  # Parsing is independent from engine success.
    assert native.normal_termination(log.read_text()) is False
    assert result.normal_termination is False
    assert data["is_success"] is ok is False
    assert remote_ok is False
    assert _terminal_verdict(remote_ok, "scheduler exited 1")[0] == "failed"
    assert ledger.await_args.args[2] == "failed"
    assert normal_log(log) is False


@pytest.mark.asyncio
async def test_captured_gaussian_irc_corrector_does_not_support_stationary_point():
    log = FIXTURES / "gaussian/hcn_ts_irc_g16.log"
    result = LogParser()._parse_log(str(log), FIELDS)
    data, ok = await monitor._parse_log(log, 1, job_type="gaussian")
    payload = {"arguments": {"log_path": str(log)}, "result": result.model_dump()}
    ref = GraphRef(ref_type="tool_result", ref_id="captured-irc")
    inbox = EvidenceInboxMixin()
    inbox.store = SimpleNamespace(resolve_evidence_with_source=lambda _: ("log_parser", payload))

    assert result.normal_termination is ok is True
    assert result.job_types == ["irc"]
    assert result.opt_converged is None
    assert data["normal_termination"] is True
    assert data["opt_converged"] is None
    assert not any(fact.check == "stationary_point" for fact in log_parser_facts(payload, ref))
    assert inbox._passes_ts_opt_check(ref) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("marker,cclib_optdone,expected", [
    ("Optimization stopped.", True, False),
    ("Optimization completed.", False, True),
    ("Stationary point found.", False, True),
])
async def test_gaussian_native_optimization_markers_override_cclib(
    tmp_path, monkeypatch, marker, cclib_optdone, expected,
):
    import cclib

    log = tmp_path / "synthetic_optimization.log"
    log.write_text("Gaussian 16\n # opt hf/sto-3g\n" + marker + "\nNormal termination\n")
    monkeypatch.setattr(cclib.io, "ccread", lambda *_a, **_k: SimpleNamespace(optdone=cclib_optdone))

    async def cclib_data(_target):
        return {"optdone": cclib_optdone}, cclib_optdone

    monkeypatch.setattr(monitor, "_cclib_parse", cclib_data)
    result = LogParser()._parse_log(str(log), FIELDS)
    data, ok = await monitor._parse_log(log, 1, job_type="gaussian")

    assert result.normal_termination is ok is True
    assert result.opt_converged is expected
    assert data["normal_termination"] is True
    assert data["opt_converged"] is expected


@pytest.mark.asyncio
async def test_orca_normal_unconverged_job_is_done_but_scientifically_failed(tmp_path, monkeypatch):
    # GH21/22 excerpt, not a complete captured output; the original was deleted.
    from tests.test_log_parser import _ORCA_EXTOPT_OPT_NOT_CONVERGED

    log = tmp_path / "maxcycle.out"
    log.write_text(_ORCA_EXTOPT_OPT_NOT_CONVERGED)
    result = LogParser()._parse_log(str(log), FIELDS)
    data, ok = await monitor._parse_log(log, 1, job_type="orca")
    monkeypatch.setattr("cloudra.infra.compute_utils.resolve_log_path", lambda *_a, **_k: str(log))
    remote_ok = _engine_success_from_log("orca", str(tmp_path / "input.inp"))
    ledger = AsyncMock(return_value=True)
    monkeypatch.setattr(monitor, "afinalize_compute_job", ledger)
    monkeypatch.setattr("cloudra.dag.controller.enqueue_compute_review", AsyncMock())
    await monitor._finalize(None, 2, log, str(tmp_path), 1, "orca", 0)

    assert result.normal_termination is remote_ok is ok is True
    assert result.opt_converged is data["opt_converged"] is False
    assert data["normal_termination"] is True
    assert data["is_success"] is True
    assert ledger.await_args.args[2] == "done"
    assert _terminal_verdict(remote_ok, None) == ("done", None)
    payload = {"result": result.model_dump()}
    ref = GraphRef(ref_type="tool_result", ref_id="unconverged-opt")
    stationary = [fact for fact in log_parser_facts(payload, ref) if fact.check == "stationary_point"]
    assert len(stationary) == 1 and stationary[0].outcome == "refutes"
    assert _ts_optimization_check([str(log)]).status == "failed"
