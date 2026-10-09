"""calculation_intent + qm_input_writer 严格化（Task 2）：无法实现的选项
明确拒绝、不静默丢参；生成文本可重新 inspect 出一致意图。"""

import pytest

pytest.importorskip("rdkit", reason="qm_input_writer requires RDKit (chem extra)")

from cloudra.runtime_v2.method_policy import check_input_content
from cloudra.runtime_v2.schemas import MethodPolicy
from cloudra.services.compute_admission import resource_underestimate
from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.core.calculation_intent import (
    TASK_VOCABULARY,
    inspect_input,
    intent_from_writer,
    validate_writer_request,
)

_WATER_XYZ = (
    "3\nwater\n"
    "O  0.000000  0.000000  0.117300\n"
    "H  0.000000  0.757200 -0.469200\n"
    "H  0.000000 -0.757200 -0.469200\n"
)

_MACE = "/opt/conda/envs/chemai/bin/mace"
_MACE_PARAMS = "--model /opt/MACE-omol-0.model --device cpu --dtype float64"


@pytest.fixture(scope="module")
def mace_exe(tmp_path_factory):
    """writer 层现在要求 ProgExt 可执行文件真实存在、可执行、且在 agent 工作目录
    与 data_dir 之外——造一个真文件代替过去的虚构 /opt 路径。"""
    exe = tmp_path_factory.mktemp("sysbin") / "mace"
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(0o755)
    return str(exe)


def _codes(entries):
    return [e["code"] for e in entries]


def _writer(tmp_path, **overrides):
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    args = {
        "engine": "orca",
        "method": "ExtOpt" if overrides.get('external_program') else "b3lyp",
        "basis_set": "" if overrides.get('external_program') else "6-31g(d)",
        "source_type": "xyz_file",
        "source_value": str(xyz),
        "output_path": str(tmp_path / "job.inp"),
    }
    args.update(overrides)
    return QmInputWriter().tool_call(QmInputWriter_input_schema(**args), session=None)


# --- validate_writer_request：固定 code/field/message 形状 ---


def test_validate_entries_shape_and_empty_means_no_conflict():
    entries = validate_writer_request({"engine": "orca", "task_type": [{"numfreq": None}]})
    assert entries
    for entry in entries:
        assert set(entry) == {"code", "field", "message"}
    assert validate_writer_request(
        {"engine": "orca", "task_type": [{"opt": None}, {"freq": None}]}
    ) == []


def test_unknown_numfreq_key_rejected_with_suggestion():
    entries = validate_writer_request({"engine": "orca", "task_type": [{"numfreq": None}]})
    assert "unknown_task_key" in _codes(entries)
    assert "frequency_mode='numeric'" in entries[0]["message"]


def test_gaussian_opt_suboptions_rejected_for_orca():
    entries = validate_writer_request(
        {"engine": "orca", "task_type": [{"opt": "ts,calcfc,noeigen"}]}
    )
    assert "gaussian_only_suboption" in _codes(entries)
    assert "orca_blocks" in entries[0]["message"]


def test_orca_end_setting_rejected():
    entries = validate_writer_request(
        {"engine": "orca", "task_type": [{"opt": None}], "end_setting": "B 1 34 S 15 0.02"}
    )
    assert "gaussian_only_field" in _codes(entries)


def test_conflicting_and_duplicate_task_blocks_rejected():
    conflicting = validate_writer_request(
        {"engine": "orca", "task_type": [{"opt": "ts"}, {"opt": None}]}
    )
    assert "conflicting_task" in _codes(conflicting)
    duplicate = validate_writer_request(
        {"engine": "gaussian", "task_type": [{"freq": None}, {"freq": None}]}
    )
    assert "duplicate_task" in _codes(duplicate)


def test_frequency_mode_without_frequency_task_rejected():
    entries = validate_writer_request(
        {"engine": "orca", "task_type": [{"opt": None}], "frequency_mode": "numeric"}
    )
    assert "frequency_mode_without_frequency" in _codes(entries)


def test_bare_orca_scan_without_geom_block_rejected():
    entries = validate_writer_request({"engine": "orca", "task_type": [{"scan": None}]})
    assert "scan_requires_orca_blocks" in _codes(entries)


# --- single_point / sp 拼写统一（规范词汇是 TASK_VOCABULARY 的 single_point） ---


def test_single_point_key_accepted_and_normalized():
    """writer 边界接受 'single_point' 与 'sp' 两种拼写，统一映射到规范词汇
    'single_point'（TASK_VOCABULARY / DAG 阶段模型同款）。"""
    assert validate_writer_request({"engine": "orca", "task_type": [{"single_point": None}]}) == []
    assert validate_writer_request({"engine": "gaussian", "task_type": [{"single_point": None}]}) == []
    for key in ("single_point", "sp"):
        intent = intent_from_writer({"engine": "orca", "task_type": [{key: None}]})
        assert intent.tasks == {"single_point"}
        assert intent.tasks <= TASK_VOCABULARY
        assert intent.certainty == "known"


def test_unknown_task_key_error_lists_both_sp_spellings():
    entries = validate_writer_request({"engine": "orca", "task_type": [{"singlepoint": None}]})
    assert "unknown_task_key" in _codes(entries)
    assert "single_point" in entries[0]["message"]
    assert "'sp'" in entries[0]["message"]
    assert "Did you mean 'single_point'?" in entries[0]["message"]


def test_sp_and_single_point_spelling_conflict_detected():
    """两种拼写指向同一任务，同请求里参数冲突/重复不能借拼写绕过。"""
    conflicting = validate_writer_request(
        {"engine": "gaussian", "task_type": [{"sp": "a"}, {"single_point": "b"}]}
    )
    assert "conflicting_task" in _codes(conflicting)
    duplicate = validate_writer_request(
        {"engine": "gaussian", "task_type": [{"sp": None}, {"single_point": None}]}
    )
    assert "duplicate_task" in _codes(duplicate)


# --- writer 行为：拒绝不落盘；成功时 unapplied_options 为空 ---


@pytest.mark.asyncio
async def test_writer_refusal_writes_no_file(tmp_path):
    result = await _writer(tmp_path, task_type=[{"opt": "ts,calcfc,noeigen"}])
    assert result.is_success is False
    assert result.unapplied_options
    assert not (tmp_path / "job.inp").exists()


@pytest.mark.asyncio
async def test_writer_rejects_invalid_options_before_building_coordinates(tmp_path, monkeypatch):
    def unexpected_build(*_args, **_kwargs):
        raise AssertionError("invalid request must not start coordinate generation")

    monkeypatch.setattr(QmInputWriter, "_get_coordinates", staticmethod(unexpected_build))
    result = await _writer(tmp_path, task_type=[{"opt": "ts,calcfc,noeigen"}])

    assert result.is_success is False
    assert result.unapplied_options
    assert "gaussian_only_suboption" in result.message


@pytest.mark.asyncio
async def test_writer_success_reports_intent_and_empty_unapplied(tmp_path):
    result = await _writer(
        tmp_path, method="b3lyp", basis_set="def2-svp", task_type=[{"opt": None}]
    )
    assert result.is_success is True, result.message
    assert result.unapplied_options == []
    assert result.generation_path.startswith("orca:")
    assert result.interpreted_intent["tasks"] == ["minimum_opt"]


@pytest.mark.asyncio
async def test_numeric_frequency_generates_numfreq_without_default_opt(tmp_path, mace_exe):
    result = await _writer(
        tmp_path,
        external_program=mace_exe,
        external_params=_MACE_PARAMS,
        task_type=[{"freq": None}],
        frequency_mode="numeric",
        nproc=1,
    )
    assert result.is_success is True, result.message
    content = (tmp_path / "job.inp").read_text()
    bang = next(line for line in content.splitlines() if line.startswith("!"))
    assert "NumFreq" in bang
    assert "Opt" not in bang.replace("ExtOpt", "")
    assert result.interpreted_intent["frequency_mode"] == "numeric"


# --- ExtOpt golden 输入：OptTS / NumFreq / IRC ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "task_type,frequency_mode,expected",
    [
        ([{"opt": "ts"}], "auto", "OptTS"),
        ([{"freq": None}], "numeric", "NumFreq"),
        ([{"irc": None}], "auto", "IRC"),
    ],
)
async def test_extopt_golden_inputs(tmp_path, mace_exe, task_type, frequency_mode, expected):
    result = await _writer(
        tmp_path,
        external_program=mace_exe,
        external_params=_MACE_PARAMS,
        task_type=task_type,
        frequency_mode=frequency_mode,
        nproc=1,
    )
    assert result.is_success is True, result.message
    content = (tmp_path / "job.inp").read_text()
    bang = next(line for line in content.splitlines() if line.startswith("!"))
    assert bang == f"! ExtOpt {expected}"
    # 外部势路由不带默认 DFT method/basis
    assert "b3lyp" not in content.lower()
    assert "6-31g" not in content.lower()
    assert f'ProgExt "{mace_exe}"' in content
    # 无继承的扫描约束
    assert "Constraints" not in content
    # 回读意图一致
    intent = inspect_input(content, engine="orca")
    assert intent.provider == "mace"
    assert intent.method_signature == "external:mace"


@pytest.mark.asyncio
async def test_constrained_ts_declares_limitation(tmp_path, mace_exe):
    result = await _writer(
        tmp_path,
        external_program=mace_exe,
        task_type=[{"opt": "ts"}],
        orca_blocks="%geom\n  Constraints\n    { B 0 1 1.30 C }\n  end\nend",
        nproc=1,
    )
    assert result.is_success is True, result.message
    assert "CONSTRAINED" in result.message
    assert result.interpreted_intent["constraints"], (
        "declared constraints must show up in the interpreted intent"
    )


# --- inspect_input 回读：不信 writer 自述 ---


def test_inspect_round_trip_matches_writer_intent(tmp_path):
    args = {
        "engine": "orca",
        "external_program": _MACE,
        "task_type": [{"opt": "ts"}, {"freq": None}],
        "frequency_mode": "numeric",
        "charge": -1,
        "multiplicity": 1,
    }
    requested = intent_from_writer(args)
    assert requested.tasks == {"ts_opt", "frequency"}
    assert requested.tasks <= TASK_VOCABULARY


def test_inspect_orca_reads_constraints_and_charge():
    text = (
        "! ExtOpt Opt\n"
        "%pal nprocs 1 end\n"
        "%geom\n  Constraints\n    { B 0 8 1.30 C }\n  end\nend\n"
        "* xyz -1 1\nO 0 0 0\n*\n"
    )
    intent = inspect_input(text, engine="orca")
    assert intent.tasks == {"minimum_opt"}
    assert intent.charge == -1 and intent.multiplicity == 1
    assert intent.constraints == [
        {"type": "bond", "atoms": [0, 8], "value": 1.30}
    ]
    assert intent.certainty == "known"


def test_inspect_orca_relaxed_scan_uses_geom_block_instead_of_opt_keyword():
    text = (
        "! Opt B3LYP def2-SVP\n"
        "%geom\n  Scan B 0 1 = 2.0, 3.0, 10 end\nend\n"
        "* xyz 0 1\nH 0 0 0\nH 0 0 2\n*\n"
    )
    intent = inspect_input(text, engine="orca")
    assert intent.tasks == {"relaxed_scan"}


def test_inspect_incomplete_input_is_not_guessed():
    intent = inspect_input("# nothing recognizable here\n", engine="orca")
    assert intent.tasks == set()
    assert intent.certainty == "unknown"


# --- MethodPolicy fail-closed 不因意图模型放宽 ---


def test_generated_extopt_input_respects_method_policy(tmp_path):
    content = (
        "! ExtOpt NumFreq\n"
        "%pal nprocs 1 end\n"
        f'%method\n  ProgExt "{_MACE}"\nend\n'
        "* xyz 0 1\nO 0 0 0\n*\n"
    )
    policy = MethodPolicy(allowed_methods=["mace"])
    assert check_input_content(content, policy, filename="x.inp", strict=True).allowed
    strict_policy = MethodPolicy(allowed_methods=["b3lyp"])
    verdict = check_input_content(content, strict_policy, filename="x.inp", strict=True)
    assert not verdict.allowed
    bare = "! ExtOpt NumFreq\n* xyz 0 1\nO 0 0 0\n*\n"
    assert not check_input_content(bare, policy, filename="x.inp", strict=True).allowed


# --- provenance：期望身份 ≠ 已验证身份 ---


@pytest.mark.asyncio
async def test_smiles_provenance_comment_is_unverified(tmp_path):
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="orca",
            method="b3lyp", basis_set="6-31g(d)",
            source_type="smiles",
            source_value="O",
            task_type=[{"opt": None}],
            output_path=str(tmp_path / "w.inp"),
        ),
        session=None,
    )
    assert result.is_success is True, result.message
    content = (tmp_path / "w.inp").read_text()
    assert "expected_smiles: O" in content
    assert "NOT an evidence-verified identity" in content
    assert "verified_smiles" not in content


# --- mem 总量 vs maxcore 每核；submit 低估诊断 ---


@pytest.mark.asyncio
async def test_mem_total_translates_to_per_core_maxcore(tmp_path):
    result = await _writer(
        tmp_path, task_type=[{"opt": None}], mem="8GB", nproc=8
    )
    assert result.is_success is True, result.message
    assert "%maxcore 1024" in (tmp_path / "job.inp").read_text()


def test_submit_resource_underestimate_diagnostic(tmp_path):
    inp = tmp_path / "job.inp"
    inp.write_text(
        "! Opt b3lyp def2-svp\n%pal nprocs 8 end\n%maxcore 2048\n* xyz 0 1\nO 0 0 0\n*\n"
    )
    low_cpus = resource_underestimate("orca", str(inp), cpus=4, memory_mb=None)
    assert low_cpus and "8 cores" in low_cpus
    low_mem = resource_underestimate("orca", str(inp), cpus=8, memory_mb=8192)
    assert low_mem and "16384 MB" in low_mem
    assert resource_underestimate("orca", str(inp), cpus=8, memory_mb=16384) is None
    gjf = tmp_path / "job.gjf"
    gjf.write_text("%nprocshared=16\n%mem=32GB\n#p opt b3lyp/6-31g(d)\n\nt\n\n0 1\nO 0 0 0\n\n")
    assert resource_underestimate("gaussian", str(gjf), cpus=4, memory_mb=None)
    assert resource_underestimate("gaussian", str(gjf), cpus=16, memory_mb=32768) is None
    # 未声明资源的输入不猜
    plain = tmp_path / "plain.inp"
    plain.write_text("! Opt b3lyp def2-svp\n* xyz 0 1\nO 0 0 0\n*\n")
    assert resource_underestimate("orca", str(plain), cpus=1, memory_mb=None) is None
