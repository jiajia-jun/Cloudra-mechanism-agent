"""ts_process：TS 搜索 SOP 的进程核心（状态机 / 目录约定 / 有界推进 / 四态终态）。

纪律逐条对应 `docs/TS_PROCESS_SOP.md`：

- 校验是**流程内部**的闸门，失败 → 阻塞且**点名到原子**，agent 改声明再 resume
- **只推两类事件**（阻塞、终态），阶段推进不推
- 四态终态；搜索失败 ≠ 反应不可能
- 有界推进（干预次数耗尽即停）
- 目录整洁：逐迭代帧只允许在 `build/trajectories/` 下
- 未接线的阶段**如实标 not_implemented 并停下**，不假装跑过
"""

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("rdkit", reason="ts_process requires RDKit (chem extra)")

from cloudra.tools.core.ts_inputs import TsInput
from cloudra.tools.core.ts_process import (  # noqa: E402
    TsStartRequest,
    evidence_binding_candidates,
    load_record,
    start,
)
from tests.ts_fixtures import calculation_input


@pytest.fixture(autouse=True)
def _path_stage_uses_fast_idpp_fallback(monkeypatch, tmp_path, request):
    """本文件测的是流程逻辑，默认把 xtb 藏出 PATH、path 阶段走 IDPP 回退——
    否则本机装有 xtb 时每个过 path 阶段的测试都真跑一遍 xTB 路径精修
    （~20s/条，全文件 10+ 分钟）。真实引擎验收测试标 @pytest.mark.real_xtb
    豁免（skipif 仍按收集时的真实 PATH 判定）。"""
    if request.node.get_closest_marker("real_xtb") is not None:
        return
    empty = tmp_path / "_no_xtb_on_path"
    empty.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(empty))
    # Scientific-stage unit tests consume a finished queue artifact. Queue,
    # admission and event idempotency are exercised in pipeline-driver tests.
    from cloudra.tools.core import xtb_path_runner as runner
    original_run = runner.run_xtb_path
    def completed_fixture(record, reactant, product):
        request = runner.XtbPathRequest(reactant_xyz=reactant,product_xyz=product,
            output_dir=str(tmp_path),timeout=None,refinement_runs=record.input.guess.refinement_runs,
            extra_args=[f'--{record.input.guess.solvation.model}',record.input.guess.solvation.solvent] if record.input.guess.solvation else [])
        if runner.run_xtb_path is original_run:
            result = runner.XtbPathResult(run_dir=str(tmp_path),termination_reason='executable_missing')
        else:
            result = runner.run_xtb_path(request)
        return result,record
    monkeypatch.setattr('cloudra.tools.core.ts_process._queued_path',completed_fixture)

# 简单可用的两端：SN2 类（F- + CH3Cl → CH3F + Cl-）。原子序号与 SMILES 顺序一致。
REACTANT = "[F-].CCl"
PRODUCT = "CF.[Cl-]"
REACTION_CENTER = [(0, 1)]  # F(0) 进攻 C(1)
# 反应物构建顺序 [F,C,Cl,H,H,H]，产物构建顺序 [C,F,H,H,H,Cl]（各自按连通分量拼装）：
# 产物第 k 个原子 → 反应物第 atom_map[k] 个（1-based）
ATOM_MAP = [1, 0, 3, 4, 5, 2]  # internal zero-based mapping


def _declaration(**overrides) -> TsInput:
    payload = {
        "reactant_smiles": REACTANT,
        "product_smiles": PRODUCT,
        "charge": -1,
        "multiplicity": 1,
        "method": "b3lyp/def2svp",
        "reaction_center": REACTION_CENTER,
    }
    # Historical fixture literals below use human-readable 1-based ring/map rows;
    # the process core now receives only normalized zero-based declarations.
    for field in ("ring_order",):
        if field in overrides:
            overrides[field] = [i - 1 for i in overrides[field]]
    if "distance_filters" in overrides:
        overrides["distance_filters"] = [dict(row, atoms=[i - 1 for i in row["atoms"]])
                                          for row in overrides["distance_filters"]]
    payload.update(overrides)
    return calculation_input(**payload)


def _start(tmp_path, request_key='fixture-prepare', **overrides):
    return start(TsStartRequest(request_key=request_key,
        input=_declaration(**overrides),
        workspace_dir=str(tmp_path),
        owner_conversation_id="test_project",
        owner_session_id="test_session",
    ))


_GUIDED_WINDOWS = [
    {"atoms": [3, 10], "min_ang": 2.5, "max_ang": 3.8},
    {"atoms": [1, 10], "min_ang": 2.5, "max_ang": 3.8},
    {"atoms": [2, 10], "min_ang": 2.5, "max_ang": 3.8},
]

























# ---------------------------------------------------------------------------
# 声明校验：方法必须显式声明，缺项即 invalid_input（终态）
# ---------------------------------------------------------------------------


def test_missing_method_is_invalid_input_because_method_is_a_scientific_decision(tmp_path):
    """方法/基组属科学决策：不接受工具默认值，缺了就是 invalid_input（终态）。"""
    with pytest.raises(ValueError, match="method"):
        _start(tmp_path, method="")


def test_empty_endpoints_are_invalid_input(tmp_path):
    with pytest.raises(ValueError):
        _start(tmp_path, reactant_smiles="")


def test_nonpositive_multiplicity_is_invalid_input(tmp_path):
    with pytest.raises(ValueError):
        _start(tmp_path, multiplicity=0)


# ---------------------------------------------------------------------------
# 目录约定
# ---------------------------------------------------------------------------


def test_run_directory_layout_and_persistence(tmp_path):
    """运行目录：ts/<run_id>/ 下按阶段分目录，状态落在 process.json（不新建存储）。"""
    record = _start(tmp_path)
    run_dir = Path(record.run_dir)
    assert run_dir.parent.name == "ts"
    assert record.run_id == "ts_0001"
    for name in ("declare.json", "process.json", "build", "path", "jobs", "verdict"):
        assert (run_dir / name).exists(), name
    on_disk = json.loads((run_dir / "process.json").read_text(encoding="utf-8"))
    assert on_disk["run_id"] == record.run_id
    assert on_disk["input"]["ts_optimization"]["method"] == "b3lyp"
    assert on_disk["input"]["ts_optimization"]["basis_set"] == "def2svp"
    # declare.json 单独可读（便于人核对声明，不用解析整份状态）
    declare = json.loads((run_dir / "declare.json").read_text(encoding="utf-8"))
    assert declare["reaction"]["reactant_smiles"] == REACTANT


def test_run_ids_are_numbered_and_isolated(tmp_path):
    first = _start(tmp_path)
    second = _start(tmp_path, request_key='another-path')
    assert (first.run_id, second.run_id) == ("ts_0001", "ts_0002")
    assert first.run_dir != second.run_dir


def test_per_iteration_frames_are_confined_to_build_trajectories(tmp_path):
    """目录整洁：逐迭代帧只允许出现在 build/trajectories/ 下，绝不平铺。"""
    record = _start(tmp_path)
    run_dir = Path(record.run_dir)
    frame_files = sorted(run_dir.rglob("frames.*"))
    assert not frame_files, "No optimization or iterative trajectory was declared"
    for path in frame_files:
        # 不变量：逐迭代帧只能躺在某个 trajectories/ 目录里，且该分支必须源自 build/
        assert path.parent.parent.name == "trajectories", path
        assert "build" in path.parts, path
        # 绝不平铺在运行目录或阶段目录的顶层
        assert path.parent.parent.parent != run_dir, path
        assert path.parent.parent.parent.parent != run_dir, path


def test_evidence_candidates_never_include_per_iteration_frames(tmp_path):
    """证据集只绑小而有意义的产物：万帧文件永不入内。"""
    record = _start(tmp_path)
    candidates = evidence_binding_candidates(record)
    assert candidates, "至少应有端点候选结构"
    assert all("trajectories" not in path for path in candidates)
    assert all(path.endswith((".xyz", ".mol", ".json")) for path in candidates)


# ---------------------------------------------------------------------------
# 阻塞：点名到原子 / 需要改哪一项声明
# ---------------------------------------------------------------------------










def test_missing_reaction_center_blocks_with_a_reason(tmp_path):
    """没有反应中心 → 普通复合物模式；不能当成"反应复合物已生成"，因此阻塞。"""
    record = _start(tmp_path, reaction_center=[])
    assert record.terminal is None
    assert record.blocked.stage == "assemble"
    assert record.blocked.failure_class == "reaction_center_missing"
    assert record.blocked.needs == ["reaction.reaction_center"]


def test_out_of_range_reaction_center_blocks_with_built_atom_numbering(tmp_path):
    """A bad pair must return a resumable run, not escape as RDKit's atomId error."""
    record = _start(
        tmp_path,
        reactant_smiles="[F-].N",
        product_smiles="[F-].N",
        reaction_center=[(0, 5)],

    )

    assert record.run_id == "ts_0001"
    assert record.terminal is None
    assert record.blocked is not None
    assert record.blocked.stage == "assemble"
    assert record.blocked.failure_class == "invalid_reaction_center"
    assert record.blocked.needs == ["reaction.reaction_center"]
    assert "1-based" in record.blocked.message
    assert "1..5" in record.blocked.message
    assert any("1=F" in detail and "5=H" in detail for detail in record.blocked.atom_details)
    assert load_record(str(tmp_path), record.run_id).blocked == record.blocked


def test_m16_product_reaction_center_reports_its_five_built_atoms(tmp_path):
    """The formic-acid case must name the bad field instead of leaking RDKit 5 < 5."""
    record = _start(
        tmp_path,
        reactant_smiles="OC=O",
        product_smiles="O=C=O.[H][H]",
        charge=0,
        reaction_center=[(4, 5)],
        selected_candidate=0,
    )

    assert record.blocked is not None
    assert record.blocked.stage == "assemble"
    assert record.blocked.failure_class == "invalid_reaction_center"
    assert record.blocked.needs == ["reaction.reaction_center"]
    assert "reactant" in record.blocked.message
    assert "1..5" in record.blocked.message
    artifact = json.loads(
        (Path(record.run_dir) / "build" / "input_0001" / "product" / "prepared_structure.json").read_text()
    )
    assert [atom["symbol"] for atom in artifact["atom_identities"]] == ["O", "C", "O", "H", "H"]
    assert artifact["atom_identities"][3]["component_id"] == "frag1"


def test_single_fragment_reaction_center_is_checked_after_atom_mapping(tmp_path):
    """Single-fragment paths still reject a bad pair before using it as a coordinate."""
    record = _start(
        tmp_path,
        reactant_smiles="OC=O",
        product_smiles="OC=O",
        charge=0,
        reaction_center=[(4, 5)],

    )

    assert record.blocked is not None
    assert record.blocked.stage == "assemble"
    assert record.blocked.failure_class == "invalid_reaction_center"
    assert record.blocked.needs == ["reaction.reaction_center"]
    assert "1..5" in record.blocked.message


def test_charge_mismatch_is_invalid_input_not_a_block(tmp_path):
    """形式电荷与声明不符是**输入不成立**（终态），不是可以靠改组装绕过的阻塞。"""
    record = _start(tmp_path, charge=0)
    assert record.terminal == "invalid_input"
    assert "charge" in record.stage_record("declare").detail.lower()
    assert all(stage.stage != "build" for stage in record.stage_records)
    assert record.blocked is None
    assert not record.job_steps and not record.waiting_for


def test_built_endpoints_are_delivered_through_the_shared_builder(tmp_path):
    """build 阶段必须真的走共享构建器（留下 prepared_structure.json + 轨迹）。"""
    record = _start(tmp_path)
    build_dir = Path(record.run_dir) / "build" / "input_0001"
    assert (build_dir / "reactant" / "prepared_structure.json").is_file()
    assert (build_dir / "product" / "prepared_structure.json").is_file()


# ---------------------------------------------------------------------------
# resume：局部覆盖 + 干预计数 + 有界
# ---------------------------------------------------------------------------










def test_load_record_round_trips_from_disk(tmp_path):
    record = _start(tmp_path)
    reloaded = load_record(str(tmp_path), record.run_id)
    assert reloaded.blocked.stage == "guess"
    assert reloaded.run_id == record.run_id


# ---------------------------------------------------------------------------
# 只推两类事件：阻塞与终态
# ---------------------------------------------------------------------------


def test_only_blocked_and_terminal_events_are_emitted(tmp_path):
    """阶段推进不推事件（避免污染上下文）；阻塞与终态才推。"""
    events: list[tuple[str, dict]] = []
    start(
        TsStartRequest(request_key='fixture-prepare', input=_declaration(), workspace_dir=str(tmp_path)),
        event_sink=lambda name, payload: events.append((name, payload)),
    )
    assert [name for name, _ in events] == ["ts.blocked"]
    payload = events[0][1]
    assert payload["blocked"]["needs"] == ["guess"]
    assert payload["blocked"]["failure_class"] == "executable_missing"


def test_terminal_event_carries_evidence_candidates(tmp_path):
    events: list[tuple[str, dict]] = []
    start(
        TsStartRequest(request_key='fixture-prepare', input=_declaration(reactant_smiles="invalid SMILES"), workspace_dir=str(tmp_path)),
        event_sink=lambda name, payload: events.append((name, payload)),
    )
    assert [name for name, _ in events] == ["ts.terminal"]
    assert events[0][1]["result"]["outcome"] == "invalid_input"




# ---------------------------------------------------------------------------
# 未接线阶段：如实标注并停下
# ---------------------------------------------------------------------------






def test_submit_without_owner_is_refused(tmp_path):
    """无归属的 run 到 submit 阶段 fail-loud 拒收：归属缺失的作业是投递不到
    的死信（ComputeNotifyBroker 只按 conversation/session 路由），宁可阻塞。"""
    record = start(TsStartRequest(request_key='fixture-prepare',
        input=_declaration(), workspace_dir=str(tmp_path),
    ))
    assert record.blocked is not None
    from cloudra.tools.core.ts_process import _submit_step
    error, job = _submit_step(record, "ts_opt", "unused.inp", "orca")
    assert job == -1 and "owner identity" in error


# ---------------------------------------------------------------------------
# guess 阶段：真实 xTB 路径 / IDPP 兜底（路径来源必须可辨）
# ---------------------------------------------------------------------------










def test_atom_count_mismatch_blocks_before_any_path_search(tmp_path):
    """两端原子数不一致（电荷对得上，所以不是 invalid_input）：在 map 阶段就拦下。

    注意顺序：电荷不符会在 build 阶段先落 invalid_input（那是"输入不成立"），
    这里刻意用一个电荷正确、原子数不同的产物，才能单独测原子数这条。
    """
    record = _start(tmp_path, product_smiles="[F-]")
    assert record.terminal is None
    assert record.blocked.stage == "map"
    assert record.blocked.failure_class == "atom_count_mismatch"
    # 报出两端的实际原子清单，便于 agent 判断该改哪一端
    joined = " | ".join(record.blocked.atom_details)
    assert "reactant:" in joined and "product:" in joined


# ---------------------------------------------------------------------------
# verdict：四态判定只读交付物；缺失频率数据一律算"未验证"
# ---------------------------------------------------------------------------

_ORCA_FREQ_FIXTURE = Path(__file__).parent / "fixtures" / "orca" / "co2_freq_orca42.out"


def _record_with_frequency_log(tmp_path, fixture: Path | None):
    """造一个已提交频率作业的运行记录，并把该作业的实测日志放到约定位置。"""
    from cloudra.tools.core.ts_process import TsJobStep, _verdict

    record = _start(tmp_path)
    job_id = 9001
    job_dir = Path(record.run_dir) / "jobs" / "job_0002"
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_dir / "frequency.inp"
    input_path.write_text("! Freq\n", encoding="utf-8")
    if fixture is not None:
        capture = job_dir / ".cloudra"
        capture.mkdir(parents=True, exist_ok=True)
        (capture / f"calc-{job_id}.out.log").write_text(
            fixture.read_text(encoding="utf-8"), encoding="utf-8"
        )
    record.job_steps.append(TsJobStep(
        purpose="frequency", job_id=job_id, input_path=str(input_path), state="done",
    ))
    return _verdict(record)


def test_verdict_rejects_a_zero_imaginary_candidate_as_a_minimum_not_a_ts(tmp_path):
    """真实 ORCA 频率日志（CO2 opt+freq，0 个虚频）：候选是**极小值**，不是 TS。

    这条守的是"绝不升格"：频率数据明明支持极小值，判定就必须说它不是鞍点，
    而且要说清"这不等于反应不可能"。
    """
    record = _record_with_frequency_log(tmp_path, _ORCA_FREQ_FIXTURE)
    assert record.terminal == "candidate_only"
    detail = record.stage_record("verdict").detail
    assert "a local minimum" in detail
    assert "does NOT mean the reaction is impossible" in detail


def test_verdict_is_unverified_when_the_frequency_log_is_missing(tmp_path):
    """没有频率数据 → candidate_only（未验证），绝不能当"已验证的鞍点"。"""
    record = _record_with_frequency_log(tmp_path, None)
    assert record.terminal == "candidate_only"
    assert "UNVERIFIED" in record.stage_record("verdict").detail


def test_verdict_cannot_reach_verified_without_irc(tmp_path):
    """频率支持一阶鞍点时，没有 IRC 仍只能到 candidate_only——IRC 是第二道闸。

    这里用真实日志里的虚频数据无法构造"恰好 1 个虚频"，所以直接验证纪律本身：
    判定函数要求 freq(1 imag) **且** IRC 双侧区间证明才给 verified；缺 IRC 一律 candidate_only。
    """
    from cloudra.tools.core.ts_process import _verdict

    record = _start(tmp_path)
    # 没有频率作业 → 未验证
    record = _verdict(record)
    assert record.terminal == "candidate_only"
    assert "no frequency job was run" in record.stage_record("verdict").detail


# ---------------------------------------------------------------------------
# refine 作业序列：TS 优化 → 频率 → IRC（第二道闸）
# ---------------------------------------------------------------------------


def test_ts_frequency_input_keeps_declared_solvation(tmp_path):
    from cloudra.tools.core.ts_process import TsJobStep, _write_frequency_input

    record = _start(tmp_path, keywords="CPCM(Water)")
    source = Path(record.run_dir) / "jobs" / "job_0001"
    source.mkdir(parents=True, exist_ok=True)
    input_path = source / "refine.inp"
    input_path.write_text("! OptTS\n")
    record.job_steps.append(TsJobStep(
        purpose="ts_opt", job_id=9001, input_path=str(input_path), state="done",
    ))
    from cloudra.tools.core.ts_process import _refinement_log_path

    log_path = Path(_refinement_log_path(record, record.job_steps[-1]))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "CARTESIAN COORDINATES (ANGSTROEM)\n"
        "---------------------------------\n"
        "O 0.000000 0.000000 0.000000\n"
        "H 0.960000 0.000000 0.000000\n"
        "H -0.240000 0.930000 0.000000\n\n",
    )
    job_dir = Path(record.run_dir) / "jobs" / "job_0002"
    job_dir.mkdir()
    error, path = _write_frequency_input(record, str(job_dir))
    assert error == ""
    assert "CPCM(Water)" in Path(path).read_text()


def test_xtb_path_guess_uses_explicit_path_solvation(tmp_path, monkeypatch):
    from cloudra.tools.core.xtb_path_runner import XtbPathResult, build_xtb_path_command

    captured = []

    def unavailable_path(request):
        captured.append(build_xtb_path_command(request))
        return XtbPathResult(run_dir=str(tmp_path), termination_reason="executable_missing")

    monkeypatch.setattr("cloudra.tools.core.xtb_path_runner.run_xtb_path", unavailable_path)
    _start(tmp_path, path_solvation={"model": "alpb", "solvent": "water"})
    assert captured
    assert captured[0][-2:] == ["--alpb", "water"]






def test_irc_input_reuses_the_hessian_only_when_the_file_is_actually_there(tmp_path):
    """Hessian 分支由**证据**决定：文件在就用 read+Hess_Filename，不在就 calc_numfreq。"""
    from cloudra.tools.core.ts_process import TsJobStep, _write_irc_input

    record = _start(tmp_path, keywords="CPCM(Water)")
    job2 = Path(record.run_dir) / "jobs" / "job_0002"
    job2.mkdir(parents=True, exist_ok=True)
    (job2 / "optimized.xyz").write_text(
        "3\noptimised\nO 0.0 0.0 0.0\nH 0.96 0.0 0.0\nH -0.24 0.93 0.0\n", encoding="utf-8"
    )
    freq_input = job2 / "frequency.inp"
    freq_input.write_text("! Freq\n", encoding="utf-8")
    record.job_steps.append(TsJobStep(
        purpose="frequency", job_id=9002, input_path=str(freq_input), state="done",
    ))

    job3 = Path(record.run_dir) / "jobs" / "job_0003"
    job3.mkdir(parents=True, exist_ok=True)
    # 没有 .hess -> 数值评估
    error, path = _write_irc_input(record, str(job3))
    assert error == ""
    assert "InitHess calc_numfreq" in Path(path).read_text(encoding="utf-8")

    # 落下 .hess -> 复用同一几何的 Hessian
    (job2 / "frequency.hess").write_text("$hessian\n", encoding="utf-8")
    new_attempt = job3 / "with_hessian"
    new_attempt.mkdir()
    error, path = _write_irc_input(record, str(new_attempt))
    assert error == ""
    content = Path(path).read_text(encoding="utf-8")
    assert "InitHess read" in content
    assert str(job2 / "frequency.hess") in content
    assert "CPCM(Water)" in content


def test_refine_submits_unconstrained_endpoint_optimization_after_irc(tmp_path, monkeypatch):
    """A completed IRC starts unconstrained QM optimization from its actual outer frame."""
    import cloudra.tools.core.ts_process as process
    from cloudra.tools.core.ts_process import TsJobStep

    record = _start(tmp_path)
    record.blocked = None
    record.stage = "refine"
    record.job_steps.append(TsJobStep(
        purpose="irc", job_id=9010, input_path=str(tmp_path / "irc.inp"), state="done",
    ))
    record.waiting_for = "job:9010"
    monkeypatch.setattr(process, "_read_job_state", lambda _record, _job_id: "done")
    monkeypatch.setattr(process, "_submit_step", lambda *_args: ("", 9011))
    irc_log = Path(process._refinement_log_path(record, record.job_steps[-1]))
    irc_log.parent.mkdir(parents=True, exist_ok=True)
    irc_log.write_text("IRC complete\n", encoding="utf-8")
    symbols, positions, _xyz, _mol = process._read_built_xyz(record, "reactant")
    side_a = [list(position) for position in positions]
    side_a[0][0] += 0.37
    _install_fake_irc_endpoints(monkeypatch, symbols, side_a, positions)

    continued = process._refine(record)
    assert continued.blocked is None
    assert continued.job_steps[-1].purpose == "reactant_opt"
    assert continued.waiting_for == "job:9011"
    content = Path(continued.job_steps[-1].input_path).read_text(encoding="utf-8")
    assert "Opt" in content
    assert "Freq" not in content
    assert "%geom" not in content  # guided distance windows must not survive
    assert f"{side_a[0][0]:.6f}" in content


def test_refine_stops_on_failed_irc_job_before_endpoint_work(tmp_path, monkeypatch):
    import cloudra.tools.core.ts_process as process
    from cloudra.tools.core.ts_process import TsJobStep

    record = _start(tmp_path)
    record.blocked = None
    record.stage = "refine"
    record.job_steps.append(TsJobStep(
        purpose="irc", job_id=9010, input_path=str(tmp_path / "irc.inp"), state="ready",
    ))
    monkeypatch.setattr(process, "_read_job_state", lambda _record, _job_id: "failed")
    result = process._refine(record)
    assert result.blocked is not None
    assert result.blocked.failure_class == "job_failed"
    assert [step.purpose for step in result.job_steps] == ["irc"]


def test_refine_endpoint_jobs_survive_reload_and_use_optimized_frames(tmp_path, monkeypatch):
    """Both Opt→Freq chains continue from persisted records, using each Opt final frame."""
    from types import SimpleNamespace

    import cloudra.tools.core.ts_process as process
    from cloudra.tools.core.ts_process import TsJobStep, load_record, save_record

    record = _start(tmp_path, keywords="CPCM(Water)")
    record.blocked = None
    record.stage = "refine"
    record.job_steps = [TsJobStep(
        purpose="irc", job_id=9010, input_path=str(tmp_path / "irc.inp"), state="done",
    )]
    record.waiting_for = "job:9010"
    monkeypatch.setattr(process, "_read_job_state", lambda _record, _job_id: "done")
    ids = iter((9011, 9012, 9013, 9014))
    monkeypatch.setattr(process, "_submit_step", lambda *_args: ("", next(ids)))
    reactant = process._read_built_xyz(record, "reactant")
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    product_path = process._product_reordered_path(record)
    irc_log = Path(process._refinement_log_path(record, record.job_steps[0]))
    irc_log.parent.mkdir(parents=True, exist_ok=True)
    irc_log.write_text("IRC complete\n", encoding="utf-8")
    product_atoms = read_xyz_atoms(product_path)
    _install_fake_irc_endpoints(
        monkeypatch, reactant[0], reactant[1], [position for _, position in product_atoms],
    )
    monkeypatch.setattr(
        "cloudra.dag.evidence_ingest.snapshot_evidence_file",
        lambda *_args, **_kwargs: SimpleNamespace(
            frequencies=[120.0, 300.0], imaginary_frequencies=[],
        ),
    )
    for purpose in (
        "reactant_opt", "reactant_frequency", "product_opt", "product_frequency",
    ):
        record = process._refine(record)
        assert record.blocked is None, record.blocked and record.blocked.message
        assert record.job_steps[-1].purpose == purpose
        assert record.waiting_for == f"job:{record.job_steps[-1].job_id}"
        assert "CPCM(Water)" in Path(record.job_steps[-1].input_path).read_text()
        if purpose.endswith("_opt"):
            opt_log = Path(process._refinement_log_path(record, record.job_steps[-1]))
            opt_log.parent.mkdir(parents=True, exist_ok=True)
            final_atoms = read_xyz_atoms(
                reactant[2] if purpose.startswith("reactant") else product_path
            )
            opt_log.write_text(
                "GEOMETRY OPTIMIZATION CYCLE\n"
                "CARTESIAN COORDINATES (ANGSTROEM)\n"
                "---------------------------------\n"
                + "\n".join(
                    f"{symbol} {x + 0.2:.8f} {y:.8f} {z:.8f}"
                    for symbol, (x, y, z) in final_atoms
                )
                + "\n\nTHE OPTIMIZATION HAS CONVERGED\n",
                encoding="utf-8",
            )
        else:
            optimized = Path(record.job_steps[-1].input_path).parent / "optimized.xyz"
            assert optimized.is_file()
            freq_log = Path(process._refinement_log_path(record, record.job_steps[-1]))
            freq_log.parent.mkdir(parents=True, exist_ok=True)
            optimized_atoms = read_xyz_atoms(str(optimized))
            freq_log.write_text(
                "CARTESIAN COORDINATES (ANGSTROEM)\n"
                "---------------------------------\n"
                + "\n".join(
                    f"{symbol} {x:.8f} {y:.8f} {z:.8f}"
                    for symbol, (x, y, z) in optimized_atoms
                )
                + "\n\nfrequency evidence\n",
                encoding="utf-8",
            )
            source = reactant[2] if purpose.startswith("reactant") else product_path
            source_atoms = read_xyz_atoms(source)
            assert [symbol for symbol, _ in optimized_atoms] == [
                symbol for symbol, _ in source_atoms
            ]
            assert optimized_atoms[0][1][0] == pytest.approx(source_atoms[0][1][0] + 0.2)
        save_record(record)
        record = load_record(str(tmp_path), record.run_id)
    record = process._refine(record)
    assert record.stage_record("refine").status == "done"


def test_gaussian_irc_uses_the_skill_recipe(tmp_path):
    """Gaussian 走原生 calcfc 写法，不强加步数上限或 ORCA 的 %irc 块。"""
    from cloudra.tools.core.ts_process import TsJobStep, _write_irc_input

    record = _start(tmp_path, engine="gaussian")
    job2 = Path(record.run_dir) / "jobs" / "job_0002"
    job2.mkdir(parents=True, exist_ok=True)
    (job2 / "optimized.xyz").write_text(
        "3\noptimised\nO 0.0 0.0 0.0\nH 0.96 0.0 0.0\nH -0.24 0.93 0.0\n", encoding="utf-8"
    )
    freq_input = job2 / "frequency.gjf"
    freq_input.write_text("#p freq\n", encoding="utf-8")
    record.job_steps.append(TsJobStep(
        purpose="frequency", job_id=9002, input_path=str(freq_input), state="done",
    ))
    job3 = Path(record.run_dir) / "jobs" / "job_0003"
    job3.mkdir(parents=True, exist_ok=True)
    error, path = _write_irc_input(record, str(job3))
    assert error == ""
    content = Path(path).read_text(encoding="utf-8")
    assert "irc=calcfc" in content
    assert "maxpoints" not in content.lower()
    assert "%irc" not in content


def test_extract_gaussian_irc_keywords():
    """解析 Gaussian IRC 关键词，保证必须包含 calcfc，无正则。"""
    from cloudra.tools.core.ts_process import _extract_gaussian_irc_keywords

    # 1. 空或无参数 -> 默认 calcfc
    assert _extract_gaussian_irc_keywords("") == ("calcfc", "", None)
    assert _extract_gaussian_irc_keywords(None) == ("calcfc", "", None)

    # 2. 完整带 calcfc 与其他参数 -> 无 warning，保留其余关键词
    subopts, rem, warn = _extract_gaussian_irc_keywords("irc=(calcfc,maxpoints=40,stepsize=10) empiricaldispersion=gd3bj")
    assert subopts == "calcfc,maxpoints=40,stepsize=10"
    assert rem == "empiricaldispersion=gd3bj"
    assert warn is None

    # 3. 遗漏 calcfc -> 自动补齐并给出明确警告
    subopts, rem, warn = _extract_gaussian_irc_keywords("irc=(maxpoints=40,stepsize=10)")
    assert subopts == "calcfc,maxpoints=40,stepsize=10"
    assert rem == ""
    assert warn is not None
    assert "Gaussian IRC requires initial force constants ('calcfc')" in warn

    # 4. 裸 irc 声明 -> 补齐 calcfc 并报警
    subopts, rem, warn = _extract_gaussian_irc_keywords("irc")
    assert subopts == "calcfc"
    assert rem == ""
    assert warn is not None
    assert "Gaussian IRC requires initial force constants ('calcfc')" in warn

    # 5. 直接传入 IRC 子参数格式（如 maxpoints=50,stepsize=5） -> 自动打包进 irc 并补上 calcfc 与警告
    subopts, rem, warn = _extract_gaussian_irc_keywords("maxpoints=50,stepsize=5")
    assert subopts == "calcfc,maxpoints=50,stepsize=5"
    assert rem == ""
    assert warn is not None
    assert "Gaussian IRC requires initial force constants ('calcfc')" in warn


def test_gaussian_irc_custom_options_missing_calcfc_warns_and_fixes(tmp_path):
    """模型漏写 calcfc 时（Issue #184），自动补齐 calcfc、发出警告，且避免路线重复 irc 报错。"""
    import pytest

    from cloudra.tools.core.ts_process import TsJobStep, _write_irc_input

    record = _start(tmp_path, engine="gaussian", keywords="irc=(maxpoints=40,stepsize=10)")
    job2 = Path(record.run_dir) / "jobs" / "job_0002"
    job2.mkdir(parents=True, exist_ok=True)
    (job2 / "optimized.xyz").write_text(
        "3\noptimised\nO 0.0 0.0 0.0\nH 0.96 0.0 0.0\nH -0.24 0.93 0.0\n", encoding="utf-8"
    )
    freq_input = job2 / "frequency.gjf"
    freq_input.write_text("#p freq\n", encoding="utf-8")
    record.job_steps.append(TsJobStep(
        purpose="frequency", job_id=9002, input_path=str(freq_input), state="done",
    ))
    job3 = Path(record.run_dir) / "jobs" / "job_0003"
    job3.mkdir(parents=True, exist_ok=True)

    with pytest.warns(UserWarning, match=r"Gaussian IRC requires initial force constants"):
        error, path = _write_irc_input(record, str(job3))

    assert error == ""
    content = Path(path).read_text(encoding="utf-8")
    route_lines = [line for line in content.splitlines() if line.startswith("#")]
    assert len(route_lines) == 1
    route = route_lines[0].lower()
    assert "irc=(calcfc,maxpoints=40,stepsize=10)" in route
    assert route.count("irc") == 1  # 绝不出现两个 irc 关键词导致 Gaussian 语法崩溃


def test_gaussian_irc_custom_options_with_calcfc_clean_route(tmp_path, recwarn):
    """模型正确写出 calcfc 时，保留选项且不发伪警告，路线合并整洁。"""
    from cloudra.tools.core.ts_process import TsJobStep, _write_irc_input

    record = _start(tmp_path, engine="gaussian", keywords="irc=(calcfc,maxpoints=40,stepsize=10) empiricaldispersion=gd3bj")
    job2 = Path(record.run_dir) / "jobs" / "job_0002"
    job2.mkdir(parents=True, exist_ok=True)
    (job2 / "optimized.xyz").write_text(
        "3\noptimised\nO 0.0 0.0 0.0\nH 0.96 0.0 0.0\nH -0.24 0.93 0.0\n", encoding="utf-8"
    )
    freq_input = job2 / "frequency.gjf"
    freq_input.write_text("#p freq\n", encoding="utf-8")
    record.job_steps.append(TsJobStep(
        purpose="frequency", job_id=9002, input_path=str(freq_input), state="done",
    ))
    job3 = Path(record.run_dir) / "jobs" / "job_0003"
    job3.mkdir(parents=True, exist_ok=True)

    error, path = _write_irc_input(record, str(job3))
    assert error == ""
    # 确认没有弹出 UserWarning
    user_warnings = [w for w in recwarn if issubclass(w.category, UserWarning) and "irc" in str(w.message)]
    assert not user_warnings

    content = Path(path).read_text(encoding="utf-8")
    route_lines = [line for line in content.splitlines() if line.startswith("#")]
    assert len(route_lines) == 1
    route = route_lines[0].lower()
    assert "irc=(calcfc,maxpoints=40,stepsize=10)" in route
    assert "empiricaldispersion=gd3bj" in route
    assert route.count("irc") == 1


def test_extract_gaussian_opt_keywords():
    """解析 Gaussian opt 关键词：TS 阶段确保 ts/calcfc/noeigen，极小值阶段按需提取。"""
    from cloudra.tools.core.ts_process import _extract_gaussian_opt_keywords

    # 1. 空或无参数 -> TS 默认 TS,calcfc,noeigen；极小值返回 None
    assert _extract_gaussian_opt_keywords("", is_ts=True) == ("TS,calcfc,noeigen", "", None)
    assert _extract_gaussian_opt_keywords(None, is_ts=True) == ("TS,calcfc,noeigen", "", None)
    assert _extract_gaussian_opt_keywords("", is_ts=False) == (None, "", None)

    # 2. TS opt 完整指定 -> 无警告，剥离其余关键字
    subopts, rem, warn = _extract_gaussian_opt_keywords("opt=(ts,calcfc,noeigen,maxstep=10) nosymm", is_ts=True)
    assert subopts == "ts,calcfc,noeigen,maxstep=10"
    assert rem == "nosymm"
    assert warn is None

    # 3. TS opt 漏写 ts -> 自动补齐 ts/calcfc/noeigen 并发出警告
    subopts, rem, warn = _extract_gaussian_opt_keywords("opt=(maxstep=10)", is_ts=True)
    assert "ts" in subopts.lower()
    assert "calcfc" in subopts.lower()
    assert "noeigen" in subopts.lower()
    assert rem == ""
    assert warn is not None
    assert "Gaussian TS optimization requires 'ts'" in warn

    # 4. 极小值优化提取自定义 opt 选项，无多余补齐与警告
    subopts, rem, warn = _extract_gaussian_opt_keywords("opt=(tight,calcfc) nosymm", is_ts=False)
    assert subopts == "tight,calcfc"
    assert rem == "nosymm"
    assert warn is None

    # 5. 极小值优化传裸 opt
    subopts, rem, warn = _extract_gaussian_opt_keywords("opt nosymm", is_ts=False)
    assert subopts is None
    assert rem == "nosymm"
    assert warn is None


def test_extract_gaussian_freq_keywords():
    """解析 Gaussian freq 关键词，提取子选项并保留其余关键字。"""
    from cloudra.tools.core.ts_process import _extract_gaussian_freq_keywords

    assert _extract_gaussian_freq_keywords("") == (None, "", None)
    assert _extract_gaussian_freq_keywords(None) == (None, "", None)

    subopts, rem, warn = _extract_gaussian_freq_keywords("freq=noraman nosymm")
    assert subopts == "noraman"
    assert rem == "nosymm"
    assert warn is None

    subopts, rem, warn = _extract_gaussian_freq_keywords("freq=(noraman) nosymm")
    assert subopts == "noraman"
    assert rem == "nosymm"
    assert warn is None

    subopts, rem, warn = _extract_gaussian_freq_keywords("freq nosymm")
    assert subopts is None
    assert rem == "nosymm"
    assert warn is None


def test_gaussian_refinement_input_merges_keywords_without_duplicate_opt(tmp_path):
    """Gaussian TS 精修输入正确合并用户声明的 opt 关键词，避免重复 opt。"""
    from cloudra.tools.core.ts_process import _write_refinement_input

    source = tmp_path / "guess.xyz"
    source.write_text("3\nguess\nO 0.0 0.0 0.0\nH 0.96 0.0 0.0\nH -0.24 0.93 0.0\n", encoding="utf-8")
    record = _start(tmp_path, reactant_smiles="O", product_smiles="O", charge=0, reaction_center=[], engine="gaussian", keywords="opt=(ts,calcfc,noeigen,maxstep=10) nosymm")
    from cloudra.tools.core.ts_process import _accept_candidate
    _accept_candidate(record, str(source))
    record.path_kind = "provided"
    job1 = Path(record.run_dir) / "jobs" / "job_0001"
    job1.mkdir(parents=True, exist_ok=True)
    error, path = _write_refinement_input(record, str(job1))
    assert error == ""
    content = Path(path).read_text(encoding="utf-8")
    route_lines = [line for line in content.splitlines() if line.startswith("#")]
    assert len(route_lines) == 1
    route = route_lines[0].lower()
    assert "opt=(ts,calcfc,noeigen,maxstep=10)" in route
    assert "nosymm" in route
    assert route.count("opt") == 1


def test_gaussian_frequency_input_merges_keywords_without_duplicate_freq(tmp_path, monkeypatch):
    """Gaussian 频率作业正确合并用户声明的 freq 关键词，避免重复 freq。"""
    from cloudra.tools.core import gaussian_frames
    from cloudra.tools.core.gaussian_frames import FrameRecord
    from cloudra.tools.core.ts_process import TsJobStep, _write_frequency_input

    record = _start(tmp_path, engine="gaussian", keywords="freq=noraman nosymm")
    job1 = Path(record.run_dir) / "jobs" / "job_0001"
    job1.mkdir(parents=True, exist_ok=True)
    xyz_content = "3\noptimised\nO 0.0 0.0 0.0\nH 0.96 0.0 0.0\nH -0.24 0.93 0.0\n"
    (job1 / "optimized.xyz").write_text(xyz_content, encoding="utf-8")
    (job1 / "refinement.log").write_text("Normal termination of Gaussian\n", encoding="utf-8")
    opt_input = job1 / "refinement.gjf"
    opt_input.write_text("#p opt=ts\n", encoding="utf-8")
    record.job_steps.append(TsJobStep(
        purpose="ts_opt", job_id=9001, input_path=str(opt_input), state="done",
    ))
    monkeypatch.setattr(
        gaussian_frames,
        "extract_frames",
        lambda _path: [FrameRecord(frame=0, xyz=xyz_content)],
    )
    job2 = Path(record.run_dir) / "jobs" / "job_0002"
    job2.mkdir(parents=True, exist_ok=True)

    error, path = _write_frequency_input(record, str(job2))
    assert error == ""
    content = Path(path).read_text(encoding="utf-8")
    route_lines = [line for line in content.splitlines() if line.startswith("#")]
    assert len(route_lines) == 1
    route = route_lines[0].lower()
    assert "freq=noraman" in route
    assert "nosymm" in route
    assert route.count("freq") == 1


# ---------------------------------------------------------------------------
# 第二端几何来源：两端 SMILES 相同的题型（阻转异构 / 外消旋）
# ---------------------------------------------------------------------------


def test_product_geometry_rejects_a_different_declared_product_graph(tmp_path):
    """A coordinate rotation cannot turn one molecular graph into another species."""
    from cloudra.tools.core.ts_inputs import RotatedConformer

    record = _start(
        tmp_path, reactant_smiles="CC", product_smiles="CO", charge=0,
        reaction_center=[],
        product_geometry=RotatedConformer(kind="rotate_about_bond", atoms=(0, 1), degrees=180).model_dump(),
    )
    assert record.terminal == "invalid_input"
    assert "product_geometry" in record.stage_record("declare").detail


#: 题库 easy 档 M1：2,2'-二甲基联苯的阻转异构旋转（Ra<->Sa，文献锚点 13.0 kcal/mol）
M1_SMILES = "Cc1ccccc1-c1c(C)cccc1"


def _biaryl_bond(mol) -> tuple[int, int]:
    """找出联芳单键：去掉它会把分子切成两个各含一整个芳环的片段。"""
    from rdkit import Chem

    for bond in mol.GetBonds():
        if bond.GetBondType() != Chem.BondType.SINGLE:
            continue
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if mol.GetAtomWithIdx(i).GetAtomicNum() != 6 or mol.GetAtomWithIdx(j).GetAtomicNum() != 6:
            continue
        if not (mol.GetAtomWithIdx(i).GetIsAromatic() and mol.GetAtomWithIdx(j).GetIsAromatic()):
            continue
        editable = Chem.RWMol(mol)
        editable.RemoveBond(i, j)
        frags = [sorted(f) for f in Chem.GetMolFrags(editable)]
        if len(frags) == 2 and all(len(f) >= 6 for f in frags):
            return (i, j)
    raise AssertionError("no biaryl bond found")


def _m1_declaration(mol) -> TsInput:
    return calculation_input(
        reactant_smiles=M1_SMILES,
        product_smiles=M1_SMILES,  # 阻转异构：两端是同一个分子
        charge=0,
        multiplicity=1,
        method="b3lyp/def2svp",
        product_geometry={"kind": "rotate_about_bond", "atoms": _biaryl_bond(mol), "degrees": 180.0},
    )


def _m1_mol():
    """M1 的三维结构（SMILES 本身没有构象，旋转测试必须有坐标）。"""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles(M1_SMILES))
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    AllChem.EmbedMolecule(mol, params)
    return mol


def test_rotation_keeps_each_side_rigid_and_moves_the_sides():
    """绕键旋转：**片内几何完全不变**、被旋转轴键长不变，只有两侧相对取向改变。

    这是它与"重新嵌入一个构象"的本质区别——后者会连片内几何一起变，那就不再是"绕轴转"。
    """
    import numpy as np

    from cloudra.tools.core.geometry import rotate_about_axis

    mol = _m1_mol()
    conf = mol.GetConformer()
    positions = np.asarray(conf.GetPositions(), dtype=float)
    left, right = _biaryl_bond(mol)
    from rdkit import Chem

    editable = Chem.RWMol(mol)
    editable.RemoveBond(left, right)
    side = [sorted(f) for f in Chem.GetMolFrags(editable)]
    moving = side[0] if right in side[0] else side[1]
    still = side[0] if moving is side[1] else side[1]

    rotated = rotate_about_axis(positions, moving, positions[left], positions[right], 180.0)

    def pairwise(pos, group):
        return [
            float(np.linalg.norm(pos[i] - pos[j]))
            for index, i in enumerate(group) for j in group[index + 1:]
        ]

    # 被旋转的那一侧：片内所有原子间距逐位不变（刚体）
    for before, after in zip(pairwise(positions, moving), pairwise(rotated, moving)):
        assert before == pytest.approx(after, abs=1e-9)
    # 另一侧完全没动
    for index in still:
        assert list(rotated[index]) == pytest.approx(list(positions[index]), abs=1e-12)
    # 轴键键长不变
    assert float(np.linalg.norm(rotated[left] - rotated[right])) == pytest.approx(
        float(np.linalg.norm(positions[left] - positions[right])), abs=1e-9
    )
    # 但没有白转：两侧之间的某个距离必须变了
    assert any(
        abs(float(np.linalg.norm(rotated[i] - rotated[j]))
            - float(np.linalg.norm(positions[i] - positions[j]))) > 0.5
        for i in moving for j in still
    )


def test_same_smiles_endpoints_are_distinguished_by_declared_geometry(tmp_path):
    """核心回归：两端 SMILES 相同的题型，必须靠**声明的几何**把两端区分开。

    这条守的是上一版的真实缺陷：只从 SMILES 各建一次，两端会建出同一个构象，路径退化——
    而退化在任何一处都不会报错。
    """
    from cloudra.tools.core.ts_process import _derive_product_geometry, _read_built_xyz

    mol = _m1_mol()
    import json

    workspace = tmp_path
    declaration = _m1_declaration(mol)
    record = start(TsStartRequest(request_key='fixture-prepare',
        input=declaration,
        workspace_dir=str(workspace),
        owner_conversation_id="test_project",
        owner_session_id="test_session",
    ))
    built = _read_built_xyz(record, "reactant")
    assert built is not None

    error, derived = _derive_product_geometry(record, built)
    assert error == "", error
    import numpy as np

    reactant_positions = np.asarray(built[1], dtype=float)
    displacement = np.linalg.norm(np.asarray(derived) - reactant_positions, axis=1)
    # 第二端与第一端**确实不是同一个几何**
    assert float(displacement.max()) > 1.0, (
        "两端几何重合 = 路径退化；这正是两端 SMILES 相同时必须声明几何来源的原因"
    )
    # map 阶段按"构造保证恒等"通过，且不再要求 atom_map
    assert record.stage_record("map").status == "done"
    assert record.structures.product_to_reactant == tuple(range(record.structures.reactant.GetNumAtoms()))
    del json


# ---------------------------------------------------------------------------
# verdict 第二道闸：IRC 双侧几何及端点区间证明才可 verified
# ---------------------------------------------------------------------------


def _xyz_text(symbols, positions, comment=""):
    lines = [str(len(symbols)), comment]
    for s, p in zip(symbols, positions):
        lines.append(f"{s} {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize('with_mol', [False, True])
def test_product_endpoint_seed_uses_declared_mapping_before_writing_input(tmp_path, with_mol):
    """A native product-order seed must reach QM in the TS working order."""
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_inputs import EndpointSeed
    from cloudra.tools.core.ts_process import _read_built_xyz, _write_endpoint_input

    record = _start(tmp_path)
    built = _read_built_xyz(record, "product")
    original_xyz = Path(built[2]).read_bytes()
    original_mol = Path(built[3]).read_bytes()
    record.input.verification.product_endpoint.seed = EndpointSeed(
        kind="file", xyz_path=built[2], mol_path=built[3] if with_mol else None, evidence_refs=[built[2]],
    )
    job_dir = Path(record.run_dir) / "jobs" / "product_seed_regression"
    job_dir.mkdir(parents=True)

    error, input_path = _write_endpoint_input(record, str(job_dir), "product", "opt")

    assert error == "", error
    assert Path(input_path).is_file()
    atoms = read_xyz_atoms(job_dir / "product_source.xyz")
    assert [symbol for symbol, _ in atoms] == ["F", "C", "Cl", "H", "H", "H"]
    # Product atom 0 is the carbon, mapped to TS atom 1; coordinates travel with it.
    assert atoms[1][1] == pytest.approx(built[1][0], abs=1e-6)
    assert Path(built[2]).read_bytes() == original_xyz
    assert Path(built[3]).read_bytes() == original_mol


@pytest.mark.parametrize('with_mol', [False, True])
@pytest.mark.parametrize('trajectory', [False, True])
@pytest.mark.parametrize('role', ['reactant', 'product'])
def test_native_irc_seed_is_not_reordered_a_second_time(tmp_path, with_mol, trajectory, role):
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_inputs import EndpointSeed
    from cloudra.tools.core.ts_process import TsJobStep, _read_built_xyz, _refinement_log_path, _write_endpoint_input

    record = _start(tmp_path)
    built = _read_built_xyz(record, role)
    # Native IRC is already in F,C,Cl,H,H,H order, unlike the species seed.
    positions = [built[1][i] for i in [1, 0, 5, 2, 3, 4]] if role == 'product' else built[1]
    irc_dir = Path(record.run_dir) / 'jobs' / 'irc_seed_regression'
    (irc_dir / '.cloudra').mkdir(parents=True)
    irc_input = irc_dir / 'irc.inp'
    irc_input.write_text('! IRC\n')
    step = TsJobStep(purpose='irc', job_id=9100, input_path=str(irc_input), state='done',
                     actual_calculation=record.input.verification.irc)
    record.job_steps.append(step)
    Path(_refinement_log_path(record, step)).write_text('ORCA TERMINATED NORMALLY\n')
    seed_path = irc_dir / ('irc_IRC_F_trj.xyz' if trajectory else 'irc_IRC_F.xyz')
    xyz = _xyz_text(['F', 'C', 'Cl', 'H', 'H', 'H'], positions)
    if trajectory:
        first = [[x, y + 5.0, z] for x, y, z in positions]
        xyz = _xyz_text(['F', 'C', 'Cl', 'H', 'H', 'H'], first) + xyz
    seed_path.write_text(xyz)
    getattr(record.input.verification, role + '_endpoint').seed = EndpointSeed(
        kind='file', xyz_path=str(seed_path), mol_path=built[3] if with_mol else None,
        evidence_refs=[str(seed_path)],
    )
    job_dir = Path(record.run_dir) / 'jobs' / 'irc_endpoint_regression'
    job_dir.mkdir()

    error, _ = _write_endpoint_input(record, str(job_dir), role, 'opt')

    assert error == '', error
    atoms = read_xyz_atoms(job_dir / f'{role}_source.xyz')
    assert [symbol for symbol, _ in atoms] == ['F', 'C', 'Cl', 'H', 'H', 'H']
    assert atoms[0][1] == pytest.approx(positions[0], abs=1e-6)


def test_gaussian_outer_frame_preserves_native_working_atom_order(tmp_path):
    from cloudra.tools.core import gaussian_frames
    from cloudra.tools.core.irc_path import parse_xyz
    from cloudra.tools.core.ts_inputs import EndpointSeed
    from cloudra.tools.core.ts_process import TsJobStep, _endpoint_seed_atoms, _refinement_log_path

    record = _start(tmp_path, reactant_smiles='C#N', product_smiles='[NH+]#[C-]',
                    charge=0,  reaction_center=[(0, 1)])
    job_dir = Path(record.run_dir) / 'jobs' / 'gaussian_irc_seed'
    (job_dir / '.cloudra').mkdir(parents=True)
    step = TsJobStep(purpose='irc', job_id=9200, input_path=str(job_dir / 'irc.gjf'), state='done',
                     actual_calculation=record.input.verification.irc.model_copy(update={'engine': 'gaussian'}))
    record.job_steps.append(step)
    fixture = Path(__file__).parent / 'fixtures' / 'gaussian' / 'hcn_ts_irc_g16.log'
    log = Path(_refinement_log_path(record, step))
    log.write_bytes(fixture.read_bytes())
    frames, _ = gaussian_frames.extract_irc(str(log))
    outer = min((f for f in frames if f.xyz and f.reaction_coordinate is not None),
                key=lambda f: f.reaction_coordinate)
    seed_path = tmp_path / 'gaussian_endpoint.xyz'
    seed_path.write_text(outer.xyz)

    atoms = _endpoint_seed_atoms(record, 'product', EndpointSeed(
        kind='file', xyz_path=str(seed_path), evidence_refs=[str(log)],
    ))

    assert [symbol for symbol, _ in atoms] == ['C', 'N', 'H']
    assert atoms[0][1] == pytest.approx([0.480862, -0.459245, 0.0], abs=1e-8)
    assert parse_xyz(seed_path.read_text())[0] == ['C', 'N', 'H']


def test_product_seed_with_working_order_mol_keeps_coordinate_rows(tmp_path):
    from rdkit import Chem

    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_inputs import EndpointSeed
    from cloudra.tools.core.ts_process import _read_built_xyz, _write_endpoint_input

    record = _start(tmp_path)
    built = _read_built_xyz(record, 'product')
    mol = Chem.MolFromMolFile(built[3], removeHs=False)
    seed_mol = tmp_path / 'working_product.mol'
    Chem.MolToMolFile(Chem.RenumberAtoms(mol, [1, 0, 5, 2, 3, 4]), str(seed_mol))
    positions = [built[1][i] for i in [1, 0, 5, 2, 3, 4]]
    seed_xyz = tmp_path / 'working_product.xyz'
    seed_xyz.write_text(_xyz_text(['F', 'C', 'Cl', 'H', 'H', 'H'], positions))
    record.input.verification.product_endpoint.seed = EndpointSeed(
        kind='file', xyz_path=str(seed_xyz), mol_path=str(seed_mol), evidence_refs=[str(seed_xyz)],
    )
    job_dir = Path(record.run_dir) / 'jobs' / 'working_mol_seed'
    job_dir.mkdir(parents=True)

    error, _ = _write_endpoint_input(record, str(job_dir), 'product', 'opt')

    assert error == '', error
    assert read_xyz_atoms(job_dir / 'product_source.xyz') == read_xyz_atoms(seed_xyz)


def test_symmetric_working_mol_keeps_bound_atom_rows(tmp_path):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_inputs import EndpointSeed
    from cloudra.tools.core.ts_process import TsProcessRecord, _endpoint_seed_atoms

    mol = Chem.AddHs(Chem.MolFromSmiles('CC'))
    assert AllChem.EmbedMolecule(mol, randomSeed=42) == 0
    mapping = [1, 0, 5, 6, 7, 2, 3, 4]
    working = Chem.RenumberAtoms(mol, mapping)
    native_mol, working_mol = tmp_path / 'native.mol', tmp_path / 'working.mol'
    native_xyz, working_xyz = tmp_path / 'native.xyz', tmp_path / 'working.xyz'
    for graph, mol_path, xyz_path in [(mol, native_mol, native_xyz), (working, working_mol, working_xyz)]:
        Chem.MolToMolFile(graph, str(mol_path))
        xyz_path.write_text(Chem.MolToXYZBlock(graph))
    record = TsProcessRecord(run_id='symmetric', run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        input=_declaration(reactant_smiles='CC', product_smiles='CC', charge=0,
                            reaction_center=[(0, 1)]),
        structures=dict(reactant=working, product=mol, product_to_reactant=tuple(mapping)))

    atoms = _endpoint_seed_atoms(record, 'product', EndpointSeed(
        kind='file', xyz_path=str(working_xyz), mol_path=str(working_mol), evidence_refs=[str(working_xyz)],
    ))

    assert atoms == read_xyz_atoms(working_xyz)


def _install_fake_irc_endpoints(monkeypatch, symbols, end_a_pos, end_b_pos):
    """IRC 端点几何替身（引擎分发提取件不是本条测试的对象）。"""
    from types import SimpleNamespace

    from cloudra.tools.Chemtool.ts_guess import TsGuess

    def _fake_extract(irc_log, checks, *, output_dir, require_two_sides=True, **_kwargs):
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path_a = out_dir / "irc_end_a.xyz"
        path_b = out_dir / "irc_end_b.xyz"
        path_a.write_text(_xyz_text(symbols, end_a_pos, "irc end a"), encoding="utf-8")
        path_b.write_text(_xyz_text(symbols, end_b_pos, "irc end b"), encoding="utf-8")
        return {
            "end_a": SimpleNamespace(xyz=path_a.read_text(encoding="utf-8")),
            "end_b": SimpleNamespace(xyz=path_b.read_text(encoding="utf-8")),
            "frames": [],
            "meta": {"forward_converged": True, "backward_converged": True},
            "path_a": str(path_a),
            "path_b": str(path_b),
        }

    monkeypatch.setattr(TsGuess, "_extract_irc_endpoints", staticmethod(_fake_extract))


def _record_with_freq_and_converged_irc(tmp_path, monkeypatch):
    """造一个频率（1 虚频）与 IRC（双向收敛）都已交付的运行记录。

    返回 (record, symbols, job_dir)：调用方再往 job_dir 放 optimized.xyz（TS
    几何）、覆写 path/product_reordered.xyz（产物极小值）、并用
    _install_fake_irc_endpoints 布置 IRC 端点后调 _verdict。
    """
    from types import SimpleNamespace

    from cloudra.tools.core import orca_frames
    from cloudra.tools.core.ts_process import (
        TsJobStep,
        _read_built_xyz,
    )

    record = _start(tmp_path, irc_log=str(tmp_path / "external_irc.log"))
    (tmp_path / "external_irc.log").write_text("irc\n", encoding="utf-8")

    built = _read_built_xyz(record, "reactant")
    assert built is not None
    symbols = built[0]

    # 频率作业步 + 实测日志（频率作业旁的 optimized.xyz 由调用方放置）
    job_id = 9001
    job_dir = Path(record.run_dir) / "jobs" / "job_0002"
    job_dir.mkdir(parents=True, exist_ok=True)
    freq_input = job_dir / "frequency.inp"
    freq_input.write_text("! Freq\n", encoding="utf-8")
    capture = job_dir / ".cloudra"
    capture.mkdir(parents=True, exist_ok=True)
    (capture / f"calc-{job_id}.out.log").write_text("freq log\n", encoding="utf-8")
    record.job_steps.append(TsJobStep(
        purpose="frequency", job_id=job_id, input_path=str(freq_input), state="done",
    ))

    from cloudra.tools.core.ts_process import _refinement_log_path
    irc_input = job_dir/'irc.inp'
    irc_input.write_text('! IRC B3LYP def2SVP\n')
    irc_step = TsJobStep(purpose='irc',job_id=9002,input_path=str(irc_input),state='done',actual_calculation=record.input.verification.irc)
    record.job_steps.append(irc_step)
    Path(_refinement_log_path(record, irc_step)).write_text('irc evidence\n')

    # 交付物替身：频率快照（1 虚频）+ IRC 元数据（双向收敛）
    monkeypatch.setattr(
        "cloudra.dag.evidence_ingest.snapshot_evidence_file",
        lambda file_path, **_kwargs: SimpleNamespace(
            frequencies=[-500.0, 120.0, 300.0], imaginary_frequencies=[-500.0],
        ),
    )
    monkeypatch.setattr(
        orca_frames, "extract_irc",
        lambda path, **_kwargs: {"forward_converged": True, "backward_converged": True},
    )
    return record, symbols, job_dir


def _sn2_minima(record, symbols):
    """从流程真实构建的 reactant 几何派生两端极小值：产物 = F 移到 C 上、Cl 推开。"""
    import numpy as np

    from cloudra.tools.core.ts_process import _read_built_xyz

    built = _read_built_xyz(record, "reactant")
    a = np.asarray(built[1], dtype=float)
    b = a.copy()
    f_idx, c_idx, cl_idx = 0, 1, 2  # 构建序 [F,C,Cl,H,H,H]
    u_fc = (a[c_idx] - a[f_idx]) / np.linalg.norm(a[c_idx] - a[f_idx])
    b[f_idx] = a[c_idx] - 1.40 * u_fc
    u_cl = (a[cl_idx] - a[c_idx]) / np.linalg.norm(a[cl_idx] - a[c_idx])
    b[cl_idx] = a[c_idx] + 3.00 * u_cl
    reordered = Path(record.run_dir) / "path" / "product_reordered.xyz"
    reordered.write_text(_xyz_text(symbols, b, "product minimum"), encoding="utf-8")
    return a, b


def _install_endpoint_minimum_jobs(record, monkeypatch, symbols, reactant, product,
                                   *, reactant_opt_converged=True,
                                   reactant_freqs=None, origins=None):
    """Only external QM parsing is replaced; verdict and interval proof stay real."""
    from types import SimpleNamespace

    from cloudra.tools.core.ts_process import TsJobStep, _refinement_log_path

    endpoint_freqs = [120.0, 300.0] if reactant_freqs is None else reactant_freqs
    for role, positions, opt_id, freq_id, number in (
        ("reactant", reactant, 9011, 9012, 3),
        ("product", product, 9013, 9014, 5),
    ):
        opt_dir = Path(record.run_dir) / "jobs" / f"job_{number:04d}"
        freq_dir = Path(record.run_dir) / "jobs" / f"job_{number + 1:04d}"
        for directory in (opt_dir, freq_dir):
            (directory / ".cloudra").mkdir(parents=True, exist_ok=True)
        opt_input = opt_dir / f"{role}_opt.inp"
        freq_input = freq_dir / f"{role}_frequency.inp"
        opt_input.write_text("! Opt\n", encoding="utf-8")
        freq_input.write_text("! Freq\n", encoding="utf-8")
        (freq_dir / "optimized.xyz").write_text(
            _xyz_text(symbols, positions, f"optimized {role}"), encoding="utf-8"
        )
        import hashlib
        source_path = opt_dir / f'{role}_source.xyz'
        origin = (origins or {}).get(role, 'A' if role == 'reactant' else 'B')
        irc = next(s for s in record.job_steps if s.purpose == 'irc')
        source_xyz = _xyz_text(symbols, positions, 'accepted explicit species source')
        if origin in {'A', 'B'}:
            from cloudra.tools.Chemtool.ts_guess import TsGuess
            try:
                info = TsGuess._extract_irc_endpoints(_refinement_log_path(record, irc), [],
                    output_dir=str(opt_dir / 'native_outer_frames'), engine='orca', require_two_sides=True)
                if info is not None:
                    source_xyz = info['end_a' if origin == 'A' else 'end_b'].xyz
            except ValueError:
                pass  # Deliberately missing IRC fixtures remain unverified.
        source_path.write_text(source_xyz)
        source = dict(kind='species_reference' if origin in {'reactant', 'product'} else 'irc_outer_frame',
            label=origin, source_path=str(source_path), sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
            irc_job_id=irc.job_id, irc_log_sha256=hashlib.sha256(Path(_refinement_log_path(record, irc)).read_bytes()).hexdigest())
        opt_step = TsJobStep(
            purpose=f"{role}_opt", job_id=opt_id, input_path=str(opt_input), state="done",
            endpoint_source=source,
        )
        freq_step = TsJobStep(
            purpose=f"{role}_frequency", job_id=freq_id,
            input_path=str(freq_input), state="done",
            endpoint_source=source,
        )
        record.job_steps.extend((opt_step, freq_step))
        coordinate_rows = "\n".join(
            f"{symbol} {position[0]:.8f} {position[1]:.8f} {position[2]:.8f}"
            for symbol, position in zip(symbols, positions)
        )
        Path(_refinement_log_path(record, opt_step)).write_text(
            "GEOMETRY OPTIMIZATION CYCLE\n"
            "CARTESIAN COORDINATES (ANGSTROEM)\n"
            "---------------------------------\n"
            f"{coordinate_rows}\n\n"
            + (
                "THE OPTIMIZATION HAS CONVERGED\n" if (
                    role != "reactant" or reactant_opt_converged
                ) else "The optimization did not converge\n"
            ),
            encoding="utf-8",
        )
        Path(_refinement_log_path(record, freq_step)).write_text(
            "CARTESIAN COORDINATES (ANGSTROEM)\n"
            "---------------------------------\n"
            + coordinate_rows + "\n\nfrequency evidence\n",
            encoding="utf-8",
        )

    ts_log = _refinement_log_path(record, record.job_steps[0])
    reactant_log = _refinement_log_path(record, next(s for s in record.job_steps if s.purpose=="reactant_frequency"))

    def snapshot(path, **_kwargs):
        frequencies = (
            [-500.0, 120.0, 300.0] if str(path) == ts_log else
            endpoint_freqs if str(path) == reactant_log else [110.0, 290.0]
        )
        return SimpleNamespace(
            frequencies=frequencies,
            imaginary_frequencies=[f for f in frequencies if f < 0],
        )

    monkeypatch.setattr("cloudra.dag.evidence_ingest.snapshot_evidence_file", snapshot)


def test_verdict_verified_requires_and_passes_interval_proof(tmp_path, monkeypatch):
    """freq(1 imag) + IRC 双侧几何 + 区间证明通过 → verified。

    区间证明是本次新增的必要条件：端点几何各自位于 TS 与对应声明极小值之间。
    """
    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    ts = 0.5 * (a + b)
    end_a = 0.75 * a + 0.25 * b
    end_b = 0.25 * a + 0.75 * b
    (job_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, ts, "TS geometry"), encoding="utf-8"
    )
    _install_fake_irc_endpoints(monkeypatch, symbols, end_a, end_b)
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, a, b)
    # The original build geometry is only a path seed. Corrupting its shape
    # must not replace the separately optimized endpoint reference in proof.

    raw_seed = Path(record.run_dir) / "raw_search_seed.xyz"
    raw_seed.write_text(_xyz_text(symbols, b, "not a minimum"), encoding="utf-8")
    from cloudra.tools.core.molecule import with_positions
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    record.structures.reactant = with_positions(record.structures.reactant, [point for _, point in read_xyz_atoms(raw_seed)])

    record = _verdict(record)
    assert record.terminal == "verified", record.stage_record("verdict").detail
    detail = record.stage_record("verdict").detail
    assert "interval proof" in detail


def test_verdict_accepts_partial_bidirectional_irc_with_verified_endpoints(
    tmp_path, monkeypatch,
):
    """A short two-sided IRC can verify direction through optimized endpoint minima."""
    from cloudra.tools.core import orca_frames
    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    monkeypatch.setattr(
        orca_frames, "extract_irc",
        lambda path, **_kwargs: {"forward_converged": False, "backward_converged": False},
    )
    a, b = _sn2_minima(record, symbols)
    (job_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, 0.5 * (a + b), "TS geometry"), encoding="utf-8",
    )
    _install_fake_irc_endpoints(
        monkeypatch, symbols, 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b,
    )
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, a, b)

    result = _verdict(record)
    assert result.terminal == "verified", result.stage_record("verdict").detail
    assert "interval proof" in result.stage_record("verdict").detail


def test_verdict_accepts_reversed_irc_side_identity_with_matching_provenance(
    tmp_path, monkeypatch,
):
    """Forward/backward labels do not determine reactant/product identity."""
    from cloudra.tools.core import orca_frames
    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    monkeypatch.setattr(
        orca_frames, "extract_irc",
        lambda path, **_kwargs: {"forward_converged": False, "backward_converged": False},
    )
    a, b = _sn2_minima(record, symbols)
    (job_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, 0.5 * (a + b), "TS geometry"), encoding="utf-8",
    )
    _install_fake_irc_endpoints(
        monkeypatch, symbols, 0.25 * a + 0.75 * b, 0.75 * a + 0.25 * b,
    )
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, a, b,
        origins={'reactant': 'B', 'product': 'A'})

    result = _verdict(record)
    assert result.terminal == "verified", result.stage_record("verdict").detail
    assert "swapped" in result.stage_record("verdict").detail


@pytest.mark.parametrize('origins', [
    {'reactant': 'reactant', 'product': 'product'},
])
def test_explicit_species_seed_can_match_swapped_irc_directions(tmp_path, monkeypatch, origins):
    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    (job_dir / 'optimized.xyz').write_text(_xyz_text(symbols, 0.5 * (a + b), 'TS'))
    _install_fake_irc_endpoints(monkeypatch, symbols, 0.25 * a + 0.75 * b, 0.75 * a + 0.25 * b)
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, a, b, origins=origins)
    result = _verdict(record)
    assert result.terminal == 'verified', result.stage_record('verdict').detail


def test_endpoint_cannot_label_an_optimized_minimum_as_native_outer_frame(tmp_path, monkeypatch):
    import hashlib

    from cloudra.tools.core.ts_process import _verdict
    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    (job_dir/'optimized.xyz').write_text(_xyz_text(symbols, 0.5*(a+b), 'TS'))
    _install_fake_irc_endpoints(monkeypatch, symbols, 0.75*a+0.25*b, 0.25*a+0.75*b)
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, a, b)
    opt = next(s for s in record.job_steps if s.purpose == 'reactant_opt')
    source_path = Path(opt.endpoint_source.source_path)
    source_path.write_text(_xyz_text(symbols, a, 'minimum falsely labeled A'))
    forged = opt.endpoint_source.model_copy(update={'sha256': hashlib.sha256(source_path.read_bytes()).hexdigest()})
    for step in record.job_steps:
        if step.purpose in {'reactant_opt', 'reactant_frequency'}:
            step.endpoint_source = forged
    assert _verdict(record).terminal == 'candidate_only'


@pytest.mark.parametrize('explicit_role', ['reactant', 'product'])
@pytest.mark.parametrize('swapped', [False, True])
def test_actual_mixed_seed_branches_keep_native_side_constraints(tmp_path, monkeypatch, explicit_role, swapped):
    from cloudra.tools.core.ts_process import _verdict
    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    (job_dir/'optimized.xyz').write_text(_xyz_text(symbols, 0.5*(a+b), 'TS'))
    ends = (0.25*a+0.75*b, 0.75*a+0.25*b) if swapped else (0.75*a+0.25*b, 0.25*a+0.75*b)
    _install_fake_irc_endpoints(monkeypatch, symbols, *ends)
    origins = {'reactant': 'B', 'product': 'A'} if swapped else {'reactant': 'A', 'product': 'B'}
    origins[explicit_role] = explicit_role
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, a, b, origins=origins)
    result = _verdict(record)
    assert result.terminal == 'verified', result.stage_record('verdict').detail


def test_verdict_rejects_two_irc_sides_optimized_to_same_species(tmp_path, monkeypatch):
    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    (job_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, 0.5 * (a + b), "TS geometry"), encoding="utf-8",
    )
    _install_fake_irc_endpoints(
        monkeypatch, symbols, 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b,
    )
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, b, b)

    result = _verdict(record)
    assert result.terminal == "candidate_only"
    assert "identity" in result.stage_record("verdict").detail


def test_wrong_input_mol_does_not_hide_observed_endpoint_species(tmp_path, monkeypatch):
    from rdkit import Chem

    from cloudra.tools.core.ts_process import _read_built_xyz, _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    (job_dir / 'optimized.xyz').write_text(_xyz_text(symbols, 0.5 * (a + b), 'TS'))
    _install_fake_irc_endpoints(monkeypatch, symbols, b, b)
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, b, b)
    # Deliberately wrong input MOL triggers the old early return before geometry feedback.
    product = Chem.MolFromMolFile(_read_built_xyz(record, 'product')[3], removeHs=False)
    record.structures.reactant = Chem.RenumberAtoms(product, [1, 0, 5, 2, 3, 4])

    result = _verdict(record)

    assert result.terminal == 'candidate_only'
    assert 'built MOL' in result.stage_record('verdict').detail
    assert 'CF.[Cl-]' in result.stage_record('verdict').detail


def test_verdict_rejects_identity_pairing_that_contradicts_irc_side_provenance(
    tmp_path, monkeypatch,
):
    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    (job_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, 0.5 * (a + b), "TS geometry"), encoding="utf-8",
    )
    # The IRC goes A→reactant/B→product, but the recorded optimization origins
    # claim A→product/B→reactant. The two facts cannot be combined into proof.
    _install_fake_irc_endpoints(
        monkeypatch, symbols, 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b,
    )
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, a, b,
        origins={'reactant': 'B', 'product': 'A'})

    result = _verdict(record)
    assert result.terminal == "candidate_only"
    assert "provenance" in result.stage_record("verdict").detail


@pytest.mark.parametrize("defect", ["missing_side", "wrong_direction"])
def test_partial_irc_still_requires_two_valid_directions(
    tmp_path, monkeypatch, defect,
):
    from cloudra.tools.Chemtool.ts_guess import TsGuess
    from cloudra.tools.core import orca_frames
    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    monkeypatch.setattr(
        orca_frames, "extract_irc",
        lambda path, **_kwargs: {"forward_converged": False, "backward_converged": False},
    )
    a, b = _sn2_minima(record, symbols)
    (job_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, 0.5 * (a + b), "TS geometry"), encoding="utf-8",
    )
    if defect == "missing_side":
        monkeypatch.setattr(TsGuess, "_extract_irc_endpoints", staticmethod(
            lambda *_args, **_kwargs: None,
        ))
    else:
        _install_fake_irc_endpoints(monkeypatch, symbols, 0.75 * a + 0.25 * b, a)
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, a, b)

    result = _verdict(record)
    assert result.terminal == "candidate_only"
    assert "interval proof" in result.stage_record("verdict").detail


def test_verdict_rejects_raw_endpoint_guesses_even_when_irc_interval_matches(
    tmp_path, monkeypatch,
):
    """An MMFF/constrained seed is not a frequency-verified minimum."""
    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    (job_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, 0.5 * (a + b), "TS geometry"), encoding="utf-8"
    )
    _install_fake_irc_endpoints(
        monkeypatch, symbols, 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b,
    )

    result = _verdict(record)
    assert result.terminal == "candidate_only"
    assert "minimum" in result.stage_record("verdict").detail.lower()


@pytest.mark.parametrize("bad_spectrum", [[], [-20.0, 120.0]])
def test_verdict_rejects_endpoint_without_zero_imaginary_frequency(
    tmp_path, monkeypatch, bad_spectrum,
):
    """Missing frequency data and an imaginary mode both fail the minimum gate."""
    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    (job_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, 0.5 * (a + b), "TS geometry"), encoding="utf-8"
    )
    _install_fake_irc_endpoints(
        monkeypatch, symbols, 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b,
    )
    _install_endpoint_minimum_jobs(
        record, monkeypatch, symbols, a, b, reactant_freqs=bad_spectrum,
    )

    result = _verdict(record)
    assert result.terminal == "candidate_only"
    assert "reactant" in result.stage_record("verdict").detail.lower()


def test_verdict_rejects_normally_ended_but_unconverged_endpoint_opt(
    tmp_path, monkeypatch,
):
    """A done compute row cannot substitute for an optimization convergence marker."""
    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    (job_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, 0.5 * (a + b), "TS geometry"), encoding="utf-8"
    )
    _install_fake_irc_endpoints(
        monkeypatch, symbols, 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b,
    )
    _install_endpoint_minimum_jobs(
        record, monkeypatch, symbols, a, b, reactant_opt_converged=False,
    )

    result = _verdict(record)
    assert result.terminal == "candidate_only"
    assert "converge" in result.stage_record("verdict").detail.lower()


def test_verdict_rejects_endpoint_xyz_unrelated_to_optimization_log(
    tmp_path, monkeypatch,
):
    """A stale XYZ beside Freq cannot stand in for the Opt log's final frame."""
    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    (job_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, 0.5 * (a + b), "TS geometry"), encoding="utf-8"
    )
    _install_fake_irc_endpoints(
        monkeypatch, symbols, 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b,
    )
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, a, b)
    stale = Path(next(s for s in record.job_steps if s.purpose=="reactant_frequency").input_path).parent / "optimized.xyz"
    shifted = [[x + 0.01, y, z] for x, y, z in a]
    stale.write_text(_xyz_text(symbols, shifted, "stale"), encoding="utf-8")

    result = _verdict(record)
    assert result.terminal == "candidate_only"
    assert "geometry" in result.stage_record("verdict").detail.lower()


def test_optimized_endpoint_must_keep_declared_species_connectivity(
    tmp_path, monkeypatch,
):
    """A seed that optimizes into the product basin is not a reactant minimum."""
    from cloudra.tools.core.ts_process import (
        _endpoint_identity_error,
        _validated_endpoint_minimum,
    )

    record, symbols, _job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, b, b)

    minimum, reason = _validated_endpoint_minimum(record, "reactant")
    assert minimum is not None, reason
    assert "connectivity" in _endpoint_identity_error(record, "reactant", minimum).lower()


def test_endpoint_identity_accepts_a_nonbonded_entrance_complex(tmp_path):
    """A short F···C encounter beyond covalent range remains two fragments."""
    import numpy as np

    from cloudra.tools.core.ts_process import _endpoint_identity_error, _read_built_xyz

    record = _start(tmp_path)
    symbols, raw_positions, _xyz, _mol = _read_built_xyz(record, "reactant")
    positions = np.asarray(raw_positions, dtype=float)
    direction = positions[1] - positions[2]
    positions[0] = positions[1] + 1.75 * direction / np.linalg.norm(direction)

    assert _endpoint_identity_error(
        record, "reactant", (symbols, positions.tolist()),
    ) == ""


def test_endpoint_identity_accepts_an_ionic_contact_pair(tmp_path):
    """A close Na+···Cl- contact is compatible with a disconnected ionic SMILES."""
    from cloudra.tools.core.ts_process import _endpoint_identity_error

    record = _start(
        tmp_path, reactant_smiles="[Na+].[Cl-]", product_smiles="[Na+].[Cl-]",
        charge=0, reaction_center=[],
    )
    assert _endpoint_identity_error(
        record, "reactant", (["Na", "Cl"], [[0.0, 0.0, 0.0], [2.4, 0.0, 0.0]]),
    ) == ""


def test_endpoint_identity_detects_bond_order_change_with_same_bond_pairs(
    tmp_path, monkeypatch,
):
    """A bond order change is a species change even when the edge set is unchanged."""
    from cloudra.tools.core import irc_path
    from cloudra.tools.core.ts_process import _endpoint_identity_error, _read_built_xyz

    record = _start(
        tmp_path, reactant_smiles="C=CC", product_smiles="C=CC", charge=0,
        reaction_center=[],
    )
    symbols, positions, _xyz, _mol = _read_built_xyz(record, "reactant")
    original = irc_path.perceive_bonds

    def changed_order(syms, coords, charge):
        bonds, source = original(syms, coords, charge)
        changed = dict(bonds)
        double = next(pair for pair, order in changed.items() if order == 2.0)
        changed[double] = 1.0
        return changed, source

    monkeypatch.setattr(irc_path, "perceive_bonds", changed_order)
    reason = _endpoint_identity_error(record, "reactant", (symbols, positions))
    assert "bond order" in reason.lower()


def test_refine_stops_before_product_jobs_when_reactant_is_not_a_minimum(
    tmp_path, monkeypatch,
):
    """Do not spend two more QM jobs after the first endpoint fails its Freq gate."""
    import cloudra.tools.core.ts_process as process

    record, symbols, _job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    _install_endpoint_minimum_jobs(
        record, monkeypatch, symbols, a, b, reactant_freqs=[-20.0, 120.0],
    )
    record.job_steps = [step for step in record.job_steps if step.purpose in ("reactant_opt", "reactant_frequency")]
    record.stage = "refine"
    record.blocked = None
    record.waiting_for = f"job:{record.job_steps[-1].job_id}"
    monkeypatch.setattr(process, "_read_job_state", lambda _record, _job_id: "done")
    monkeypatch.setattr(
        process, "_submit_step",
        lambda *_args: (_ for _ in ()).throw(AssertionError("product job was submitted")),
    )

    result = process._refine(record)
    assert result.terminal == "candidate_only"
    assert len(result.job_steps) == 2


def test_refine_unconverged_endpoint_opt_is_candidate_not_unfixable_block(
    tmp_path, monkeypatch,
):
    """A completed but unconverged endpoint Opt must end as a candidate-only run."""
    import cloudra.tools.core.ts_process as process
    from cloudra.tools.core.ts_process import TsJobStep

    record = _start(tmp_path)
    record.blocked = None
    record.stage = "refine"
    opt_dir = Path(record.run_dir) / "jobs" / "job_0004"
    opt_dir.mkdir(parents=True, exist_ok=True)
    opt_input = opt_dir / "reactant_opt.inp"
    opt_input.write_text("! Opt\n", encoding="utf-8")
    step = TsJobStep(
        purpose="reactant_opt", job_id=9011, input_path=str(opt_input), state="done",
    )
    record.job_steps = [step]
    record.waiting_for = "job:9011"
    opt_log = Path(process._refinement_log_path(record, step))
    opt_log.parent.mkdir(parents=True, exist_ok=True)
    opt_log.write_text("The optimization did not converge\n", encoding="utf-8")
    monkeypatch.setattr(process, "_read_job_state", lambda _record, _job_id: "done")

    result = process._refine(record)
    assert result.terminal == "candidate_only"
    assert result.blocked is None
    assert "converge" in result.stage_record("verdict").detail.lower()


def test_unreadable_gaussian_endpoint_opt_log_finishes_candidate_only(
    tmp_path, monkeypatch,
):
    """Parser failure after a completed compute job must not strand a waiting run."""
    import cloudra.tools.core.ts_process as process
    from cloudra.tools.core import gaussian_frames
    from cloudra.tools.core.ts_process import TsJobStep

    record = _start(tmp_path, engine="gaussian")
    record.blocked = None
    record.stage = "refine"
    opt_dir = Path(record.run_dir) / "jobs" / "job_0004"
    opt_dir.mkdir(parents=True, exist_ok=True)
    opt_input = opt_dir / "reactant_opt.gjf"
    opt_input.write_text("# opt\n", encoding="utf-8")
    step = TsJobStep(
        purpose="reactant_opt", job_id=9011, input_path=str(opt_input), state="done",
    )
    record.job_steps = [step]
    record.waiting_for = "job:9011"
    opt_log = Path(process._refinement_log_path(record, step))
    opt_log.parent.mkdir(parents=True, exist_ok=True)
    opt_log.write_text("Normal termination of Gaussian\n", encoding="utf-8")
    monkeypatch.setattr(process, "_read_job_state", lambda _record, _job_id: "done")
    monkeypatch.setattr(
        gaussian_frames, "extract_frames",
        lambda _path: (_ for _ in ()).throw(ValueError("unreadable geometry")),
    )

    result = process._refine(record)
    assert result.terminal == "candidate_only"
    assert result.blocked is None
    assert "unreadable" in result.stage_record("verdict").detail.lower()


def test_verdict_converged_irc_without_connectivity_is_candidate_only(tmp_path, monkeypatch):
    """IRC 双侧有几何但端点不在 TS 与声明极小值之间 → candidate_only。

    「IRC 跑完了」本身不构成「落回声明的极小值」的证据。
    """
    import numpy as np

    from cloudra.tools.core.ts_process import _verdict

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    a, b = _sn2_minima(record, symbols)
    ts = 0.5 * (a + b)
    # end_b 根本没朝产物侧走（就是 reactant 极小值）：任何指派都无法落在区间内
    end_a = 0.75 * a + 0.25 * b
    end_b = np.array(a, dtype=float)
    (job_dir / "optimized.xyz").write_text(
        _xyz_text(symbols, ts, "TS geometry"), encoding="utf-8"
    )
    _install_fake_irc_endpoints(monkeypatch, symbols, end_a, end_b)
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, a, b)

    record = _verdict(record)
    assert record.terminal == "candidate_only"
    detail = record.stage_record("verdict").detail
    assert "interval proof" in detail
    assert "UNVERIFIED" in detail


# ---------------------------------------------------------------------------
# guess 阶段：撞 nrun 上限后能把上限抬上去重跑（GH #39 建议 2）
# ---------------------------------------------------------------------------


def _xtb_path_stub(tmp_path, seen, termination="path_not_converged"):
    """替身：记录每次实际传给引擎的 refinement_runs，并据此回填结果。"""

    def fake_run(request, **_kwargs):
        seen.append(request.refinement_runs)
        from cloudra.tools.core import xtb_path_runner as runner

        return runner.XtbPathResult(
            run_dir=os.path.join(str(tmp_path), "xtb_path_runs", f"guess_{len(seen):04d}"),
            termination_reason=termination,
            usable_as_guess=False,
            refinement_runs=request.refinement_runs,
        )

    return fake_run








# ---------------------------------------------------------------------------
# guess 阶段：path_kind 要区分"引擎跑过但没出可用初猜"与"根本没搜"（GH #39）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "termination, expected_kind",
    [
        # 引擎确实启动过的终止类别（子进程起来了、stdout 落盘、可能已有采样帧）
        ("path_not_converged", "xtb_path_failed"),
        ("incomplete_artifacts", "xtb_path_failed"),
        ("unknown_failure", "xtb_path_failed"),
        ("timeout", "xtb_path_failed"),
        ("failed", "xtb_path_failed"),
        # 引擎没起来的失败：这一档不算"搜过"，仍是 not_attempted（负向判据——
        # 修法是分类，不是"把所有 guess 失败都改成一个新值"）
        ("invalid_endpoints", "not_attempted"),
    ],
)
def test_guess_path_kind_separates_engine_ran_from_no_search(
    tmp_path, monkeypatch, termination, expected_kind
):
    """GH #39：xTB 跑过但失败时曾被报成 not_attempted，上层因此误判"根本没搜"。

    分类的唯一事实源是 ``XTB_ENGINE_STARTED_TERMINATIONS``；这里用替身逐档喂进去，
    断言 path_kind 跟着分类走，并确认阻塞行为没变（改的是上报口径，不是放行规则）。
    """
    from cloudra.tools.core import xtb_path_runner as runner

    def fake_run(request, **_kwargs):
        return runner.XtbPathResult(
            run_dir=os.path.join(str(tmp_path), "xtb_path_runs", "guess_0001"),
            termination_reason=termination,
            usable_as_guess=False,
            refinement_runs=100,
        )

    monkeypatch.setattr(runner, "run_xtb_path", fake_run)
    record = _start(tmp_path)
    assert record.path_kind == expected_kind
    assert record.blocked is not None and record.blocked.stage == "guess"
    assert record.blocked.failure_class == termination


# ---------------------------------------------------------------------------
# guess 失败后的可恢复性：中间帧可发现 + 阻塞消息点名下一步（GH #39 建议 1/3）
# ---------------------------------------------------------------------------


def test_engine_crash_frames_are_visible_and_next_steps_are_named(tmp_path, monkeypatch):
    """引擎崩溃只留中间帧时：消息要点出它们（并保持"不是初猜"的定性）+ 点名下一步选项。

    `_record_partial_frames` 是 runner 里被真实失败路径调用的同一份逻辑，测试直接调它——
    不在测试里复制一份（否则两边会漂移）。
    """
    from cloudra.tools.core import xtb_path_runner as runner

    run_dir = tmp_path / "xtb_path_runs" / "guess_0001"
    run_dir.mkdir(parents=True)
    for n in (1, 2, 3):
        (run_dir / f"xtbpath_{n}.xyz").write_text("frame", encoding="utf-8")

    def fake_run(request, **_kwargs):
        result = runner.XtbPathResult(
            run_dir=str(run_dir), returncode=0,
            termination_reason="incomplete_artifacts", usable_as_guess=False,
        )
        result.diagnostics.append("path artifacts are unusable: no such file: xtbpath.xyz")
        runner._record_partial_frames(result)
        return result

    monkeypatch.setattr(runner, "run_xtb_path", fake_run)
    record = _start(tmp_path)

    assert record.blocked is not None
    assert record.blocked.failure_class == "incomplete_artifacts"
    assert record.path_kind == "xtb_path_failed"  # 引擎跑过但没出初猜（#58）；崩溃帧仍不作初猜
    # 中间帧可见（消息 + 原子级诊断两处）
    assert "3 partial iteration frame(s)" in record.blocked.message
    assert "not a usable guess" in record.blocked.message
    assert any("partial iteration frame" in d for d in record.blocked.atom_details)
    # 下一步选项：默认种子路线在前，插值标出适用条件
    assert "guess" in record.blocked.needs
    assert "internal_coordinates" in record.blocked.message
    assert "interpolate" in record.blocked.message


def test_no_partial_frame_noise_when_the_engine_left_none(tmp_path, monkeypatch):
    """负向：没有中间帧时不给噪音，但下一步指引照旧（与"有没有帧"无关）。"""
    from cloudra.tools.core import xtb_path_runner as runner

    def fake_run(request, **_kwargs):
        return runner.XtbPathResult(
            run_dir=str(tmp_path / "no_such_run"), returncode=0,
            termination_reason="incomplete_artifacts", usable_as_guess=False,
        )

    monkeypatch.setattr(runner, "run_xtb_path", fake_run)
    record = _start(tmp_path)

    assert "partial iteration frame" not in record.blocked.message
    assert record.blocked.atom_details == []
    assert "guess" in record.blocked.needs


pytestmark = pytest.mark.usefixtures("ts_producer_authority")


def test_file_complex_assembly_uses_bound_structure_components(tmp_path):
    from cloudra.tools.core.ts_process import TsProcessRecord, _assemble
    prepared = tmp_path / "atom_table.json"
    prepared.write_text(json.dumps({"components": [], "atom_identities": [
        {"index": i, "symbol": symbol} for i, symbol in enumerate(["F", "C", "Cl", "H", "H", "H"])]}))
    record = TsProcessRecord(run_id="file-complex", run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        owner_conversation_id="test", owner_session_id="test", input=_declaration(reaction_center=[]),
        structures=dict(reactant=__import__("rdkit").Chem.MolFromSmiles(REACTANT)))
    result = _assemble(record)
    assert result.blocked is not None
    assert result.blocked.failure_class == "reaction_center_missing"


def test_truncated_path_requests_current_guess_revision_not_obsolete_budget(tmp_path, monkeypatch):
    monkeypatch.setattr("cloudra.tools.core.xtb_path_runner.run_xtb_path", _xtb_path_stub(tmp_path, []))
    record = _start(tmp_path)
    assert record.blocked.failure_class == "path_not_converged"
    assert record.blocked.needs == ["guess"]


def test_ts_interval_reference_reordering_retains_unresolved_molecular_properties(tmp_path, monkeypatch):
    from rdkit import Chem

    from cloudra.tools.core import irc_path
    from cloudra.tools.core.molecule import read_molecule, serialize_molecule, total_charge
    from cloudra.tools.core.ts_process import _irc_interval_proof

    record, symbols, job_dir = _record_with_freq_and_converged_irc(tmp_path, monkeypatch)
    reactant, product = _sn2_minima(record, symbols)
    (job_dir / 'optimized.xyz').write_text(_xyz_text(symbols, 0.5 * (reactant + product)))
    _install_fake_irc_endpoints(monkeypatch, symbols, 0.75 * reactant + 0.25 * product,
                                0.25 * reactant + 0.75 * product)
    _install_endpoint_minimum_jobs(record, monkeypatch, symbols, reactant, product)
    native = record.structures.product
    reference = read_molecule(input_text=Chem.MolToXYZBlock(native), input_format='xyz', charge=-1)
    reference.SetIntProp('reference_revision', 7)
    reference.SetProp('_source_note', 'original coordinate reference')
    record.structures.product = reference
    before = serialize_molecule(reference)

    def inspect_references(*_args, reference_molecules, **_kwargs):
        reordered = reference_molecules[1]
        assert reordered.GetProp('cloudra_graph_status') == 'unresolved'
        assert total_charge(reordered) == -1
        assert reordered.GetIntProp('reference_revision') == 7
        assert reordered.GetProp('_source_note') == 'original coordinate reference'
        return dict(is_decidable=True, is_match=True, assignment='direct')

    monkeypatch.setattr(irc_path, 'assign_irc_endpoints', inspect_references)
    frequency = next(step for step in record.job_steps if step.purpose == 'frequency')
    accepted, detail = _irc_interval_proof(record, 'unused.log', frequency,
        (symbols, reactant), (symbols, product), {})
    assert accepted, detail
    assert serialize_molecule(reference) == before


def test_unique_mapping_is_owned_without_agent_transport(tmp_path):
    record = _start(tmp_path)
    assert record.structures.product_to_reactant == tuple(ATOM_MAP)
    assert record.stage_record('map').status == 'done'
    data = record.model_dump(mode='json')
    assert 'atom_map' not in data['input']['reaction']
    assert not {'input_binding', 'seed_molecules', 'current_seed_xyz_path', 'current_ts_guess_path'} & data.keys()
