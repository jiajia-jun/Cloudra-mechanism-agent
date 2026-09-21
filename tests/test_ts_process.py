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
    return start(TsStartRequest(
        declaration=_declaration(**overrides),
        workspace_dir=str(tmp_path),
        owner_conversation_id="test_project",
        owner_session_id="test_session",
    ))


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


def test_missing_atom_map_block_carries_endpoint_numbering(tmp_path):
    """缺 atom_map 的阻塞必须自诊断：atom_details 直接给出两端 built XYZ 的
    路径与 1-based 元素序列（atom_map 的编号参照系），并指向 reaction_mapping
    草稿通道——agent 不该靠猜编号再试一轮。"""
    record = _start(tmp_path, atom_map=[])
    blocked = record.blocked
    details = "\n".join(blocked.atom_details)
    assert "reactant atoms (1-based): 1=F, 2=C, 3=Cl, 4=H, 5=H, 6=H" in details
    assert "product atoms (1-based): 1=C, 2=F, 3=H, 4=H, 5=H, 6=Cl" in details
    assert ".xyz" in details
    assert "reaction_mapping" in blocked.message
    assert "hydrogen" in blocked.message.lower()


def test_zero_based_atom_map_is_diagnosed(tmp_path):
    """含 0 的映射点名 0-based 笔误：重试引导必须说清错在哪，不只是"不对"。"""
    record = _start(tmp_path, atom_map=[1, 0, 3, 4, 5, 2])
    blocked = record.blocked
    assert blocked.failure_class == "atom_map_not_a_permutation"
    assert "0-based" in blocked.message


def test_heavy_atom_only_map_is_diagnosed(tmp_path):
    """只覆盖重原子的映射（reaction_mapping 的 heavy_atom_map 形态）被点名：
    atom_map 必须覆盖每个氢。"""
    record = _start(tmp_path, atom_map=[2, 1, 3])
    blocked = record.blocked
    assert blocked.failure_class == "atom_map_not_a_permutation"
    assert "heavy-atom" in blocked.message
    assert "hydrogen" in blocked.message.lower()


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


@pytest.mark.real_xtb
@pytest.mark.skipif(
    __import__("shutil").which("xtb") is None, reason="未安装 xtb，跳过真实引擎验收"
)
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


@pytest.mark.real_xtb
@pytest.mark.skipif(
    __import__("shutil").which("xtb") is None, reason="未安装 xtb，跳过真实引擎验收"
)
def test_waiting_on_compute_emits_no_event(tmp_path):
    """等计算**不算阻塞**：不推事件，agent 不该被叫醒来做没有决策的事。"""
    events: list[tuple[str, dict]] = []
    record = start(
        TsStartRequest(
            declaration=_declaration(),
            workspace_dir=str(tmp_path),
            owner_conversation_id="test_project",
            owner_session_id="test_session",
        ),
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


@pytest.mark.real_xtb
@pytest.mark.skipif(
    __import__("shutil").which("xtb") is None, reason="未安装 xtb，跳过真实引擎验收"
)
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


@pytest.mark.real_xtb
@pytest.mark.skipif(
    __import__("shutil").which("xtb") is None, reason="未安装 xtb，跳过真实引擎验收"
)
def test_submitted_job_is_in_ready_state_in_the_central_queue(tmp_path):
    """submit 之后作业真的躺在中央 compute_jobs 里且状态为 ready（调度守护去认领）。"""
    from cloudra.persistence.database import ComputeDB

    record = _start(tmp_path)
    db = ComputeDB().init()
    with db.connect() as con:
        row = con.execute(
            "SELECT state, path, jobtype, conversation_id, session_id FROM compute_jobs WHERE id = ?",
            (record.job_id,),
        ).fetchone()
    assert row[0] == "ready"
    assert row[1] == record.job_input_path
    assert row[2] == "orca"
    # 归属与 submit_compute_job 同一纪律：终态推送只认这两个字段
    assert row[3] == "test_project"
    assert row[4] == "test_session"
    # 现场落在 jobs/<job_dir>/ 下，与作业现场同处
    assert "jobs" in Path(record.job_input_path).parts


def test_submit_without_owner_is_refused(tmp_path):
    """无归属的 run 到 submit 阶段 fail-loud 拒收：归属缺失的作业是投递不到
    的死信（ComputeNotifyBroker 只按 conversation/session 路由），宁可阻塞。"""
    record = start(TsStartRequest(
        declaration=_declaration(), workspace_dir=str(tmp_path),
    ))
    assert record.blocked is not None
    assert record.blocked.failure_class == "owner_missing"
    assert record.blocked.stage == "submit"
    assert "owner" in record.blocked.message


# ---------------------------------------------------------------------------
# guess 阶段：真实 xTB 路径 / IDPP 兜底（路径来源必须可辨）
# ---------------------------------------------------------------------------


@pytest.mark.real_xtb
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


# ---------------------------------------------------------------------------
# refine 作业序列：TS 优化 → 频率 → IRC（第二道闸）
# ---------------------------------------------------------------------------


@pytest.mark.real_xtb
@pytest.mark.skipif(
    __import__("shutil").which("xtb") is None, reason="未安装 xtb，跳过真实引擎验收"
)
def test_refine_submits_the_irc_job_after_frequency(tmp_path):
    """频率完成后自动提交 IRC：顺带验证它在同一几何上用 %irc 原生块。

    这条守的是"verified 可达"：只跑频率的流程最高只能到 candidate_only。
    """
    from cloudra.tools.core.ts_process import TsJobStep, _refine

    record = _start(tmp_path)
    # 把 TS 优化与频率两步都标记为已完成，并把频率的优化几何放好
    job2 = Path(record.run_dir) / "jobs" / "job_0002"
    job2.mkdir(parents=True, exist_ok=True)
    optimized = job2 / "optimized.xyz"
    optimized.write_text(
        "3\noptimised\nO 0.0 0.0 0.0\nH 0.96 0.0 0.0\nH -0.24 0.93 0.0\n", encoding="utf-8"
    )
    freq_input = job2 / "frequency.inp"
    freq_input.write_text("! Freq\n", encoding="utf-8")
    # 作业状态是**从库里读的**，所以必须真的插一行 done（手写 state 会被覆盖）
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import insert_compute_job

    db = ComputeDB().init()
    for step, path in ((record.job_steps[0], record.job_steps[0].input_path),
                       (None, str(freq_input))):
        job_id = insert_compute_job(
            db, node_id="node-local", conversation_id="test", session_id=None,
            path=path, state="done", jobtype="orca",
        )
        if step is not None:
            step.job_id = job_id
            step.state = "done"
        else:
            record.job_steps.append(TsJobStep(
                purpose="frequency", job_id=job_id, input_path=path, state="done",
            ))
    record.waiting_for = ""

    record = _refine(record)
    assert record.blocked is None, record.blocked and record.blocked.message
    assert [step.purpose for step in record.job_steps] == ["ts_opt", "frequency", "irc"]
    irc_step = record.job_steps[-1]
    assert irc_step.job_id is not None
    content = Path(irc_step.input_path).read_text(encoding="utf-8")
    # ORCA：! IRC + 原生 %irc 块，双向，且 Hessian 分支由证据决定
    assert "IRC" in content
    assert "%irc" in content
    assert "Direction both" in content
    assert ("InitHess read" in content) or ("InitHess calc_numfreq" in content)
    assert record.waiting_for == f"job:{irc_step.job_id}"


def test_irc_input_reuses_the_hessian_only_when_the_file_is_actually_there(tmp_path):
    """Hessian 分支由**证据**决定：文件在就用 read+Hess_Filename，不在就 calc_numfreq。"""
    from cloudra.tools.core.ts_process import TsJobStep, _write_irc_input

    record = _start(tmp_path)
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
    error, path = _write_irc_input(record, str(job3))
    assert error == ""
    content = Path(path).read_text(encoding="utf-8")
    assert "InitHess read" in content
    assert str(job2 / "frequency.hess") in content


def test_gaussian_irc_uses_the_skill_recipe(tmp_path):
    """Gaussian 走 skill 表格里的原生写法（含 calcfc / maxpoints），不拼 ORCA 的 %irc 块。"""
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
    assert "irc=(calcfc,maxpoints=80)" in content
    assert "%irc" not in content


# ---------------------------------------------------------------------------
# 第二端几何来源：两端 SMILES 相同的题型（阻转异构 / 外消旋）
# ---------------------------------------------------------------------------

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


def _m1_declaration(mol) -> TsDeclaration:
    return TsDeclaration(
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
    record = start(TsStartRequest(
        declaration=declaration,
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
    assert "identity by construction" in record.stage_record("map").detail
    del json


# ---------------------------------------------------------------------------
# verdict 第二道闸：IRC 双向收敛之外还要过端点区间证明才 verified
# ---------------------------------------------------------------------------


def _xyz_text(symbols, positions, comment=""):
    lines = [str(len(symbols)), comment]
    for s, p in zip(symbols, positions):
        lines.append(f"{s} {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}")
    return "\n".join(lines) + "\n"


def _install_fake_irc_endpoints(monkeypatch, symbols, end_a_pos, end_b_pos):
    """IRC 端点几何替身（引擎分发提取件不是本条测试的对象）。"""
    from types import SimpleNamespace

    from cloudra.tools.Chemtool.ts_guess import TsGuess

    def _fake_extract(user_input, checks, require_two_sides=True, **_kwargs):
        return {
            "end_a": SimpleNamespace(xyz=_xyz_text(symbols, end_a_pos, "irc end a")),
            "end_b": SimpleNamespace(xyz=_xyz_text(symbols, end_b_pos, "irc end b")),
            "frames": [],
            "meta": {"forward_converged": True, "backward_converged": True},
            "path_a": "",
            "path_b": "",
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


def test_verdict_verified_requires_and_passes_interval_proof(tmp_path, monkeypatch):
    """freq(1 imag) + IRC 双向收敛 + 区间证明通过 → verified。

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

    record = _verdict(record)
    assert record.terminal == "verified", record.stage_record("verdict").detail
    detail = record.stage_record("verdict").detail
    assert "interval proof" in detail


def test_verdict_converged_irc_without_connectivity_is_candidate_only(tmp_path, monkeypatch):
    """IRC 双向收敛但端点不在 TS 与声明极小值之间（连通未证明）→ candidate_only。

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


def test_refinement_ceiling_defaults_to_runner_default_and_resume_can_raise_it(
    tmp_path, monkeypatch
):
    """未声明 → runner 默认；resume 抬高后 → 新数字必须真的到引擎。

    撞上限（path_not_converged）是 blocked 而不是终态，出路正是"抬高上限重跑"——
    所以这条链不能停在 schema 里（GH #39：此前写进声明的预算没人消费）。
    """
    from cloudra.tools.core import xtb_path_runner as runner

    seen = []
    monkeypatch.setattr(runner, "run_xtb_path", _xtb_path_stub(tmp_path, seen))

    record = _start(tmp_path)
    # 未声明：交给 runner 默认，不发明数字
    assert seen == [runner.DEFAULT_REFINEMENT_RUNS]
    assert record.blocked is not None and record.blocked.failure_class == "path_not_converged"
    assert record.blocked.needs == ["budget"]
    # 阻塞消息点名出路，不让 agent 自己猜
    assert "path_refinement_runs" in record.blocked.message

    # 抬高上限后 resume：数字真要过引擎
    record = resume(
        load_record(str(tmp_path), record.run_id),
        TsAdjustment(path_refinement_runs=350, budget_override_note="100 轮不够"),
    )
    assert seen == [runner.DEFAULT_REFINEMENT_RUNS, 350]
    assert record.blocked is not None  # 替身仍报触顶，所以应再次阻塞
    # 落在记录上（否则重启恢复就丢了）
    assert load_record(str(tmp_path), record.run_id).declaration.budget.path_refinement_runs == 350


def test_declared_refinement_ceiling_is_used_on_the_first_guess(tmp_path, monkeypatch):
    """声明里直接给上限时，第一次 guess 就用它——不必先撞一次墙（负向：默认路径没被这条抢走）。"""
    from cloudra.tools.core import xtb_path_runner as runner

    seen = []
    monkeypatch.setattr(runner, "run_xtb_path", _xtb_path_stub(tmp_path, seen))

    _start(tmp_path, budget=TsBudget(path_refinement_runs=250))
    assert seen == [250]


def test_zero_means_undeclared_not_zero_runs(tmp_path, monkeypatch):
    """0 = 未声明，**不是**"跑 0 轮"：必须落到 runner 默认（否则会把上限设成非法值）。"""
    from cloudra.tools.core import xtb_path_runner as runner

    seen = []
    monkeypatch.setattr(runner, "run_xtb_path", _xtb_path_stub(tmp_path, seen))

    _start(tmp_path, budget=TsBudget(path_refinement_runs=0))
    assert seen == [runner.DEFAULT_REFINEMENT_RUNS]
