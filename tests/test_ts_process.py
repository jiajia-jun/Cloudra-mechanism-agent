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

from cloudra.tools.core.ts_process import (  # noqa: E402
    TsAdjustment,
    TsBudget,
    TsDeclaration,
    TsStartRequest,
    advance,
    evidence_binding_candidates,
    load_record,
    resume,
    start,
)

# 简单可用的两端：SN2 类（F- + CH3Cl → CH3F + Cl-）。原子序号与 SMILES 顺序一致。
REACTANT = "[F-].CCl"
PRODUCT = "CF.[Cl-]"
REACTION_CENTER = [(0, 1)]  # F(0) 进攻 C(1)
# 反应物构建顺序 [F,C,Cl,H,H,H]，产物构建顺序 [C,F,H,H,H,Cl]（各自按连通分量拼装）：
# 产物第 k 个原子 → 反应物第 atom_map[k] 个（1-based）
ATOM_MAP = [2, 1, 4, 5, 6, 3]


def _declaration(**overrides) -> TsDeclaration:
    payload = {
        "reactant_smiles": REACTANT,
        "product_smiles": PRODUCT,
        "charge": -1,
        "multiplicity": 1,
        "method": "b3lyp/def2svp",
        "reaction_center": REACTION_CENTER,
        "atom_map": ATOM_MAP,
    }
    payload.update(overrides)
    return TsDeclaration(**payload)


def _start(tmp_path, **overrides):
    return start(TsStartRequest(declaration=_declaration(**overrides), workspace_dir=str(tmp_path)))


# ---------------------------------------------------------------------------
# 声明校验：方法必须显式声明，缺项即 invalid_input（终态）
# ---------------------------------------------------------------------------


def test_missing_method_is_invalid_input_because_method_is_a_scientific_decision(tmp_path):
    """方法/基组属科学决策：不接受工具默认值，缺了就是 invalid_input（终态）。"""
    record = _start(tmp_path, method="")
    assert record.terminal == "invalid_input"
    assert "method is empty" in record.stage_record("declare").detail
    # 终态不再可推进
    assert advance(record).terminal == "invalid_input"


def test_empty_endpoints_are_invalid_input(tmp_path):
    record = _start(tmp_path, reactant_smiles="")
    assert record.terminal == "invalid_input"


def test_nonpositive_multiplicity_is_invalid_input(tmp_path):
    record = _start(tmp_path, multiplicity=0)
    assert record.terminal == "invalid_input"


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
    assert on_disk["declaration"]["method"] == "b3lyp/def2svp"
    # declare.json 单独可读（便于人核对声明，不用解析整份状态）
    declare = json.loads((run_dir / "declare.json").read_text(encoding="utf-8"))
    assert declare["reactant_smiles"] == REACTANT


def test_run_ids_are_numbered_and_isolated(tmp_path):
    first = _start(tmp_path)
    second = _start(tmp_path)
    assert (first.run_id, second.run_id) == ("ts_0001", "ts_0002")
    assert first.run_dir != second.run_dir


def test_per_iteration_frames_are_confined_to_build_trajectories(tmp_path):
    """目录整洁：逐迭代帧只允许出现在 build/trajectories/ 下，绝不平铺。"""
    record = _start(tmp_path)
    run_dir = Path(record.run_dir)
    frame_files = sorted(run_dir.rglob("frames.*"))
    assert frame_files, "构建阶段必须留下轨迹（否则说明没跑）"
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
    assert all(path.endswith((".xyz", ".mol")) for path in candidates)


# ---------------------------------------------------------------------------
# 阻塞：点名到原子 / 需要改哪一项声明
# ---------------------------------------------------------------------------


def test_missing_atom_map_blocks_with_an_actionable_request(tmp_path):
    """原子映射歧义必须显式呈现：缺 atom_map 就阻塞，并要求补齐——不猜。"""
    record = _start(tmp_path, atom_map=[])
    assert record.terminal is None
    blocked = record.blocked
    assert blocked is not None
    assert blocked.stage == "map"
    assert blocked.failure_class == "atom_map_missing"
    assert blocked.needs == ["atom_map"]
    assert "ambiguous" in blocked.message


def test_missing_reaction_center_blocks_with_a_reason(tmp_path):
    """没有反应中心 → 普通复合物模式；不能当成"反应复合物已生成"，因此阻塞。"""
    record = _start(tmp_path, reaction_center=[])
    assert record.terminal is None
    assert record.blocked.stage == "assemble"
    assert record.blocked.failure_class == "reaction_center_missing"
    assert record.blocked.needs == ["reaction_center"]


def test_charge_mismatch_is_invalid_input_not_a_block(tmp_path):
    """形式电荷与声明不符是**输入不成立**（终态），不是可以靠改组装绕过的阻塞。"""
    record = _start(tmp_path, charge=0)
    assert record.terminal == "invalid_input"
    assert "charge" in record.stage_record("build").detail.lower()


def test_built_endpoints_are_delivered_through_the_shared_builder(tmp_path):
    """build 阶段必须真的走共享构建器（留下 prepared_structure.json + 轨迹）。"""
    record = _start(tmp_path)
    build_dir = Path(record.run_dir) / "build"
    assert (build_dir / "reactant" / "prepared_structure.json").is_file()
    assert (build_dir / "product" / "prepared_structure.json").is_file()


# ---------------------------------------------------------------------------
# resume：局部覆盖 + 干预计数 + 有界
# ---------------------------------------------------------------------------


def test_resume_supplies_the_missing_declaration_and_continues(tmp_path):
    """resume 只接受局部覆盖：补上 atom_map 后从阻塞处继续。"""
    record = _start(tmp_path, atom_map=[])
    assert record.blocked.stage == "map"
    record = resume(record, TsAdjustment(atom_map=ATOM_MAP))
    assert record.intervention_count == 1
    assert record.stage_record("map").status == "done"
    # map 通过后前端 + 提交一路跑完，在 refine 等作业终态
    assert record.blocked is None
    assert record.waiting_for.startswith("job:")
    assert record.job_id is not None


def test_resume_is_recorded_and_bounded(tmp_path):
    """干预次数计入记录；超预算即落终态，不无限续。"""
    record = _start(tmp_path, atom_map=[], budget=TsBudget(max_interventions=1))
    record = resume(record, TsAdjustment(atom_map=ATOM_MAP))
    assert record.intervention_count == 1
    # 再阻塞一次（把反应中心清空），resume 后预算耗尽
    record = resume(record, TsAdjustment(reaction_center=[]))
    assert record.intervention_count == 2
    assert record.terminal == "search_failed"
    detail = record.stage_record(record.stage).detail
    assert "budget" in detail
    # 搜索失败绝不等于反应不可能
    assert "NOT a claim" in detail


def test_terminal_run_is_not_resumed(tmp_path):
    record = _start(tmp_path, method="")
    assert record.terminal == "invalid_input"
    with pytest.raises(ValueError):
        resume(record, TsAdjustment(atom_map=ATOM_MAP))


def test_load_record_round_trips_from_disk(tmp_path):
    record = _start(tmp_path, atom_map=[])
    reloaded = load_record(str(tmp_path), record.run_id)
    assert reloaded.blocked.stage == "map"
    assert reloaded.run_id == record.run_id


# ---------------------------------------------------------------------------
# 只推两类事件：阻塞与终态
# ---------------------------------------------------------------------------


def test_only_blocked_and_terminal_events_are_emitted(tmp_path):
    """阶段推进不推事件（避免污染上下文）；阻塞与终态才推。"""
    events: list[tuple[str, dict]] = []
    start(
        TsStartRequest(declaration=_declaration(atom_map=[]), workspace_dir=str(tmp_path)),
        event_sink=lambda name, payload: events.append((name, payload)),
    )
    assert [name for name, _ in events] == ["ts.blocked"]
    payload = events[0][1]
    assert payload["needs"] == ["atom_map"]
    assert payload["failure_class"] == "atom_map_missing"


def test_terminal_event_carries_evidence_candidates(tmp_path):
    events: list[tuple[str, dict]] = []
    start(
        TsStartRequest(declaration=_declaration(method=""), workspace_dir=str(tmp_path)),
        event_sink=lambda name, payload: events.append((name, payload)),
    )
    assert [name for name, _ in events] == ["ts.terminal"]
    assert events[0][1]["terminal"] == "invalid_input"


def test_waiting_on_compute_emits_no_event(tmp_path):
    """等计算**不算阻塞**：不推事件，agent 不该被叫醒来做没有决策的事。"""
    events: list[tuple[str, dict]] = []
    record = start(
        TsStartRequest(declaration=_declaration(), workspace_dir=str(tmp_path)),
        event_sink=lambda name, payload: events.append((name, payload)),
    )
    # declare/build/map/assemble/guess/validate/submit 跑完后在 refine 等作业终态
    assert record.blocked is None
    assert record.terminal is None
    assert record.waiting_for.startswith("job:")
    assert record.stage_record("refine").status == "waiting"
    # 只推阻塞与终态两类事件 -> 等待一个都不推
    assert events == []


# ---------------------------------------------------------------------------
# 未接线阶段：如实标注并停下
# ---------------------------------------------------------------------------


def test_submit_submits_a_ready_job_and_refine_waits_for_it(tmp_path):
    """submit 阶段真的提交一个 ready 作业；refine 进入 waiting 等它的终态（不轮询）。"""
    record = _start(tmp_path)
    statuses = {r.stage: r.status for r in record.stage_records}
    assert statuses["submit"] == "done"
    assert record.job_id is not None and record.job_id > 0
    assert os.path.isfile(record.job_input_path)
    detail = record.stage_record("submit").detail
    assert "submitted as 'ready'" in detail
    # refine 在等这个作业，且说明走的是既有通知路径（不是轮询）
    assert statuses["refine"] == "waiting"
    assert record.waiting_for == f"job:{record.job_id}"
    assert "never polls" in record.stage_record("refine").detail
    assert record.terminal is None
    # verdict 还没轮到（作业没到终态）
    assert "verdict" not in statuses


def test_submitted_job_is_in_ready_state_in_the_central_queue(tmp_path):
    """submit 之后作业真的躺在中央 compute_jobs 里且状态为 ready（调度守护去认领）。"""
    from cloudra.persistence.database import ComputeDB

    record = _start(tmp_path)
    db = ComputeDB().init()
    with db.connect() as con:
        row = con.execute(
            "SELECT state, path, jobtype FROM compute_jobs WHERE id = ?", (record.job_id,),
        ).fetchone()
    assert row[0] == "ready"
    assert row[1] == record.job_input_path
    assert row[2] == "orca"
    # 现场落在 jobs/<job_dir>/ 下，与作业现场同处
    assert "jobs" in Path(record.job_input_path).parts


# ---------------------------------------------------------------------------
# guess 阶段：真实 xTB 路径 / IDPP 兜底（路径来源必须可辨）
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    __import__("shutil").which("xtb") is None, reason="未安装 xtb，跳过真实引擎验收"
)
def test_front_half_with_real_xtb_records_xtb_path_kind(tmp_path):
    """真实引擎跑完整前端：两端构建 → 映射重排 → MTD 路径 → 校验通过。

    这条同时验证了一件必需的事：构建器按连通分量拼装两端，**原子顺序本来不同**
    （实测反应物 [F,C,Cl,H,H,H]、产物 [C,F,H,H,H,H]→重排后同序），路径搜索要求同序，
    所以 map 阶段的重排是必需的，不是形式。
    """
    record = _start(tmp_path)
    statuses = {r.stage: r.status for r in record.stage_records}
    assert statuses.get("build") == "done"
    assert statuses.get("map") == "done"
    assert statuses.get("guess") == "done"
    assert statuses.get("validate") == "done"
    assert record.path_kind == "xtb_path"
    # 重排后的产物可复查（否则 agent 无法核对重排是否合理）
    reordered = Path(record.run_dir) / "path" / "product_reordered.xyz"
    assert reordered.is_file()
    # 提交后在 refine 等作业终态，且不伪造终态
    assert record.blocked is None
    assert record.stage_record("refine").status == "waiting"
    assert record.terminal is None
    assert record.job_id is not None
    # TS 候选进了证据候选（小产物），逐迭代帧没有
    assert any("xtbpath_ts.xyz" in path for path in evidence_binding_candidates(record))


def test_guess_reports_idpp_fallback_when_xtb_is_absent(tmp_path, monkeypatch):
    """xTB 缺失：前端仍走完，但 path_kind 必须标成降级路线——不静默。"""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    record = _start(tmp_path)
    assert record.path_kind == "idpp_fallback"
    detail = record.stage_record("guess").detail
    assert "idpp_fallback" in detail
    assert "degraded" in detail.lower()


def test_wrong_atom_map_blocks_with_element_level_detail(tmp_path):
    """错映射必须点名到原子地报出来，而不是让路径搜索拿着错序去跑。"""
    record = _start(tmp_path, atom_map=[1, 2, 3, 4, 5, 6])
    assert record.terminal is None
    blocked = record.blocked
    assert blocked.stage == "map"
    assert blocked.failure_class == "atom_map_element_mismatch"
    assert blocked.needs == ["atom_map"]
    # 每个错配都要说清是哪个原子对不上哪个元素
    assert blocked.atom_details
    assert any("but the map points it at reactant atom" in d for d in blocked.atom_details)


def test_atom_map_must_be_a_permutation(tmp_path):
    record = _start(tmp_path, atom_map=[1, 1, 2, 3, 4, 5])
    assert record.blocked.failure_class == "atom_map_not_a_permutation"


def test_atom_count_mismatch_blocks_before_any_path_search(tmp_path):
    """两端原子数不一致（电荷对得上，所以不是 invalid_input）：在 map 阶段就拦下。

    注意顺序：电荷不符会在 build 阶段先落 invalid_input（那是"输入不成立"），
    这里刻意用一个电荷正确、原子数不同的产物，才能单独测原子数这条。
    """
    record = _start(tmp_path, product_smiles="[F-]", atom_map=[1])
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
    判定函数要求 freq(1 imag) **且** IRC 双向收敛才给 verified；缺 IRC 一律 candidate_only。
    """
    from cloudra.tools.core.ts_process import _verdict

    record = _start(tmp_path)
    # 没有频率作业 → 未验证
    record = _verdict(record)
    assert record.terminal == "candidate_only"
    assert "no frequency job was run" in record.stage_record("verdict").detail
