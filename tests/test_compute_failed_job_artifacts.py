"""Task 6：失败计算作业的日志定位与几何中间产物。

覆盖三条要求：

1. 日志一律经**已登记**的 ``compute_jobs.log_path`` / ``resolve_log_path`` 定位实测的
   ``.cloudra/calc-<id>.out.log``，不新增任何文件名猜测链；
2. 进程中途死亡（本仓库用 ORCA 退出 139 的段错误形态）后作业状态必须保持 ``failed``，
   但该失败日志里的几何中间产物仍可提取、且带来源；
3. 从失败日志提取几何**不得**让频率/TS 验证被伪标完成：没有频率数据就是"未验证"，
   不是"已验证的驻点极小值"。

固定日志样本 ``tests/fixtures/orca/segfault_mid_opt/dvb_opt_truncated_no_termination.out``
是**真实** ORCA 日志 ``dvb_opt_orca42.out`` 在第 3 个 ``GEOMETRY OPTIMIZATION CYCLE`` 之前
逐字截断的结果（保留前两个优化步的全部坐标与能量，之后没有任何输出、也没有正常终止横幅），
用于复现"进程死在优化中途"的形态。**未复现项**：issue #33 报告者那次段错误的原始完整日志、
其引擎版本与最小输入均不在本仓库内，因此本文件不对"macOS 上必现"或"拆分作业必治"作任何断言。
"""

import json
import os
from pathlib import Path

import pytest

TRUNCATED_LOG = str(
    Path(__file__).parent
    / "fixtures" / "orca" / "segfault_mid_opt" / "dvb_opt_truncated_no_termination.out"
)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """使用临时数据目录隔离数据库和上下文。"""
    data_dir = tmp_path / "cloudra_data"
    data_dir.mkdir()

    from cloudra.infra.config import _reset_for_tests, get_config

    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    _reset_for_tests()
    cfg = get_config()
    cfg.data_dir = data_dir
    cfg._ensure_dirs()
    return cfg


# ---------------------------------------------------------------------------
# 固定日志样本的形态自检（先证明样本确实是"死在优化中途"）
# ---------------------------------------------------------------------------


def test_truncated_log_fixture_shape():
    """样本形态：有两个优化步的坐标，没有任何正常终止/收敛/频率标记。"""
    text = open(TRUNCATED_LOG, encoding="utf-8", errors="replace").read()
    assert text.count("GEOMETRY OPTIMIZATION CYCLE") == 2
    assert "ORCA TERMINATED NORMALLY" not in text
    assert "THE OPTIMIZATION HAS CONVERGED" not in text
    assert "VIBRATIONAL FREQUENCIES" not in text
    assert text.rstrip().endswith("|") or text.rstrip()[-1] not in "Zz"  # 最后一行是被硬截断的


# ---------------------------------------------------------------------------
# 1. 日志定位：走已登记的 log_path / resolve_log_path
# ---------------------------------------------------------------------------


def test_failed_job_log_is_found_through_the_registered_capture(tmp_path):
    """失败作业的日志经 resolve_log_path 找到 guard 实测的 .cloudra/calc-<id>.out.log。"""
    from cloudra.infra.compute_utils import resolve_log_path

    workdir = tmp_path / "job"
    (workdir / ".cloudra").mkdir(parents=True)
    inp = workdir / "job.inp"
    inp.write_text("! opt\n", encoding="utf-8")
    captured = workdir / ".cloudra" / "calc-7.out.log"
    captured.write_text(open(TRUNCATED_LOG, encoding="utf-8").read(), encoding="utf-8")

    resolved = resolve_log_path(str(inp), job_type="orca", task_id=7)
    assert resolved == str(captured)
    assert Path(resolved).is_file()
    # 不允许退回按后缀猜出来的预测路径
    assert resolved != str(workdir / "job.out")

    # guard 记录的 state json 优先于 calc 落盘文件（同一事实来源，仍然不是猜测）
    state = workdir / "state_7.json"
    state.write_text(json.dumps({"log_file": str(captured)}), encoding="utf-8")
    assert resolve_log_path(str(inp), job_type="orca", task_id=7) == str(captured)


# ---------------------------------------------------------------------------
# 2. 失败作业保持失败，但几何中间产物仍可提取且有来源
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crashed_job_stays_failed_and_geometry_is_still_extractable(isolated_db, tmp_path):
    """段错误形态的作业：状态保持 failed，但日志里的优化中间几何仍可提取。"""
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime.monitor import _mark_failed
    from cloudra.tools.core import orca_frames
    from cloudra.tools.core.qm_engine import detect_qm_engine

    workdir = tmp_path / "job"
    (workdir / ".cloudra").mkdir(parents=True)
    inp = workdir / "job.inp"
    inp.write_text("! opt\n", encoding="utf-8")
    log = workdir / ".cloudra" / "calc-11.out.log"
    log.write_text(open(TRUNCATED_LOG, encoding="utf-8").read(), encoding="utf-8")

    assert detect_qm_engine(str(log)) == "orca"
    assert orca_frames.normal_termination(log.read_text(encoding="utf-8")) is False

    frames = orca_frames.extract_frames(str(log))
    assert len(frames) == 2, "失败作业的优化中间几何必须仍然可提取"
    assert [f.frame for f in frames] == [0, 1]
    for frame in frames:
        assert frame.xyz.splitlines()[0].strip().isdigit()
    # 中间帧带各自那一步的能量（来源可追溯），且作业本身仍标记失败
    assert frames[0].electronic_energy_hartree is not None
    assert frames[1].electronic_energy_hartree is not None

    db = ComputeDB().init()
    async with db.aconnect() as con:
        cur = await con.execute(
            "INSERT INTO compute_jobs (conversation_id, session_id, path, state, start_timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            ("conv", "s1", str(inp), "running", 1.0),
        )
        await con.commit()
        task_id = cur.lastrowid
    await _mark_failed(db, task_id, "calculator exited with code 139 (SIGSEGV)")
    async with db.aconnect() as con:
        row = await (await con.execute(
            "SELECT state, last_error FROM compute_jobs WHERE id = ?", (task_id,),
        )).fetchone()
    assert row[0] == "failed"
    assert "139" in row[1]


@pytest.mark.asyncio
async def test_format_converter_extracts_provenance_from_the_crashed_log(tmp_path):
    """Chemtool 读取入口：从失败日志提取几何，返回里带上来源日志路径。"""
    from cloudra.tools.Chemtool.format_converter import FormatConverter, FormatConverter_input_schema

    result = await FormatConverter().tool_call(
        FormatConverter_input_schema(
            input_path=TRUNCATED_LOG,
            input_format="log",
            output_format="xyz",
            output_path=str(tmp_path / "final_frame.xyz"),
        ),
        session=None,
    )
    assert result.is_success is True, result.message
    text = open(result.output_path, encoding="utf-8").read()
    assert text.splitlines()[0].strip().isdigit()
    # 展平代理检测到的任务类型与帧数，来源即所给的失败日志
    assert "opt" in result.message.lower()
    assert os.path.basename(TRUNCATED_LOG) in result.message or TRUNCATED_LOG in result.message


# ---------------------------------------------------------------------------
# 3. 频率/TS 验证不得被伪标完成
# ---------------------------------------------------------------------------


def test_missing_frequency_data_is_unverified_not_valid():
    """核心回归：没有频率数据 = 未验证，绝不能判成"有效的驻点极小值"。"""
    from cloudra.dag.evidence_ingest import validate_species_minimum, validate_ts_mode

    species = validate_species_minimum(None, imaginary_freqs=None)
    assert species.frequency_count_valid is False, "无频率数据被判成有效极小值 = 频率验证被伪标完成"
    assert species.frequency_data_present is False
    assert "UNVERIFIED" in species.message

    ts = validate_ts_mode(None, imaginary_freqs=None)
    assert ts.frequency_count_valid is False
    assert ts.frequency_data_present is False
    assert "UNVERIFIED" in ts.message

    # 有数据的两条路径仍然给出"已验证"的判定
    ok_min = validate_species_minimum([100.0, 500.0])
    assert (ok_min.frequency_count_valid, ok_min.frequency_data_present) == (True, True)
    bad_min = validate_species_minimum([-50.0, 100.0])
    assert (bad_min.frequency_count_valid, bad_min.frequency_data_present) == (False, True)
    ok_ts = validate_ts_mode([-521.0, 100.0, 500.0])
    assert (ok_ts.frequency_count_valid, ok_ts.frequency_data_present) == (True, True)


def test_crashed_job_log_yields_unverified_stationary_point(tmp_path):
    """把失败日志当证据：快照有几何/能量，但频率为空 → 驻点判定必须是"未验证"。"""
    from cloudra.dag.evidence_ingest import snapshot_evidence_file, validate_species_minimum

    workspace = tmp_path / "ws"
    workspace.mkdir()
    log = workspace / "crashed.log"
    log.write_text(open(TRUNCATED_LOG, encoding="utf-8").read(), encoding="utf-8")

    snapshot = snapshot_evidence_file(log, workspace_root=workspace)
    assert snapshot.is_qm_log is True
    assert snapshot.engine == "orca"
    assert snapshot.frequencies is None, "截断日志里没有频率块，不得凭空给出频率"
    assert snapshot.final_energy_hartree is not None

    verdict = validate_species_minimum(
        snapshot.frequencies, imaginary_freqs=snapshot.imaginary_frequencies,
    )
    assert verdict.frequency_count_valid is False
    assert verdict.frequency_data_present is False


@pytest.mark.asyncio
async def test_dag_species_evidence_rejects_opt_only_evidence(isolated_db, tmp_path):
    """端到端：只有 opt 日志（无频率数据）时，物种证据不得被接受为已验证驻点。"""
    from cloudra.dag.evidence_ingest import snapshot_evidence_file, validate_species_minimum

    workspace = tmp_path / "ws"
    workspace.mkdir()
    opt = workspace / "species_opt.log"
    opt.write_text(open(TRUNCATED_LOG, encoding="utf-8").read(), encoding="utf-8")

    opt_snap = snapshot_evidence_file(opt, workspace_root=workspace)
    check_freqs = opt_snap.frequencies
    check_imag = opt_snap.imaginary_frequencies
    val = validate_species_minimum(check_freqs, imaginary_freqs=check_imag)

    # 这正是 dag_submit_species_evidence 的判定点：旧语义下 is_valid=True 会让该物种
    # 被登记为"已验证的驻点极小值"，而作业其实是中途崩溃的 opt-only 计算。
    assert val.frequency_count_valid is False, "opt-only 证据被接受 = 图里出现伪已完成的物种"
    assert val.frequency_data_present is False
