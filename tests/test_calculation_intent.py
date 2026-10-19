"""Native calculation settings are preserved and questionable options warn."""

import pytest

pytest.importorskip("rdkit", reason="qm_input_writer requires RDKit (chem extra)")

from cloudra.runtime_v2.method_policy import check_input_content
from cloudra.runtime_v2.schemas import MethodPolicy
from cloudra.services.compute_admission import resource_underestimate
from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema
from cloudra.tools.core.calculation_intent import (
    TASK_VOCABULARY,
    compare_calculation_input,
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


def test_explicit_native_orca_scan_is_not_advised_to_use_itself():
    issues = validate_writer_request(dict(engine='orca', method='HF', basis_set='STO-3G',
        task_type=[{'opt': None}], orca_blocks='%geom Scan B 0 1 = 1.0, 2.0, 5 end end'))
    assert 'scan_requires_ts_guess' not in _codes(issues)


def _writer(tmp_path, **overrides):
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    args = {
        "engine": "orca",
        "method": "ExtOpt" if overrides.get('external_program') else "b3lyp",
        "basis_set": "" if overrides.get('external_program') else "6-31g(d)",
        "source_type": "xyz_file",
        "source_value": str(xyz),
        "charge": 0,
        "output_path": str(tmp_path / "job.inp"),
    }
    args.update(overrides)
    return QmInputWriter().tool_call(QmInputWriter_input_schema(**args), session=None)


# --- validate_writer_request：结构化可见建议 ---


def test_validate_entries_shape_and_empty_means_no_conflict():
    entries = validate_writer_request({"engine": "orca", "task_type": [{"FutureTask": None}]})
    assert entries
    for entry in entries:
        assert set(entry) == {"code", "field", "message", "severity"}
        assert entry['severity'] == 'warning'
    assert validate_writer_request(
        {"engine": "orca", "task_type": [{"opt": None}, {"freq": None}]}
    ) == []


def test_native_numfreq_key_is_accepted_without_alias_rewrite():
    entries = validate_writer_request({"engine": "orca", "task_type": [{"numfreq": None}]})
    assert entries == []
    assert intent_from_writer({'engine': 'orca', 'task_type': [{'NumFreq': None}]}).tasks == {'frequency'}


def test_gaussian_opt_suboptions_warn_for_orca():
    entries = validate_writer_request(
        {"engine": "orca", "task_type": [{"opt": "ts,calcfc,noeigen"}]}
    )
    assert "gaussian_only_suboption" in _codes(entries)
    assert "orca_blocks" in entries[0]["message"]


def test_orca_end_setting_warns():
    entries = validate_writer_request(
        {"engine": "orca", "task_type": [{"opt": None}], "end_setting": "B 1 34 S 15 0.02"}
    )
    assert "gaussian_only_field" in _codes(entries)


def test_conflicting_and_duplicate_task_blocks_warn():
    conflicting = validate_writer_request(
        {"engine": "orca", "task_type": [{"opt": "ts"}, {"opt": None}]}
    )
    assert "conflicting_task" in _codes(conflicting)
    duplicate = validate_writer_request(
        {"engine": "gaussian", "task_type": [{"freq": None}, {"freq": None}]}
    )
    assert "duplicate_task" in _codes(duplicate)


def test_frequency_mode_without_frequency_task_warns():
    entries = validate_writer_request(
        {"engine": "orca", "task_type": [{"opt": None}], "frequency_mode": "numeric"}
    )
    assert "frequency_mode_without_frequency" in _codes(entries)


def test_bare_orca_scan_without_geom_block_warns():
    entries = validate_writer_request({"engine": "orca", "task_type": [{"scan": None}]})
    assert "scan_requires_ts_guess" in _codes(entries)


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


def test_unknown_task_key_warns_without_guessing_a_replacement():
    entries = validate_writer_request({"engine": "orca", "task_type": [{"singlepoint": None}]})
    assert "unknown_task_key" in _codes(entries)
    assert entries[0]['severity'] == 'warning'
    assert 'preserved' in entries[0]['message']


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


# --- writer 行为：保留参数并返回 warning；成功时 unapplied_options 为空 ---


@pytest.mark.asyncio
async def test_writer_questionable_options_are_written_with_warnings(tmp_path):
    result = await _writer(tmp_path, task_type=[{"opt": "ts,calcfc,noeigen"}])
    assert result.is_success, result.message
    assert not result.unapplied_options
    assert result.warnings
    assert 'calcfc,noeigen' in (tmp_path / 'job.inp').read_text()


@pytest.mark.asyncio
async def test_writer_warning_does_not_skip_coordinate_work(tmp_path, monkeypatch):
    original = QmInputWriter._get_molecule
    calls = []

    def record_build(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(QmInputWriter, "_get_molecule", staticmethod(record_build))
    result = await _writer(tmp_path, task_type=[{"opt": "ts,calcfc,noeigen"}])

    assert result.is_success, result.message
    assert calls
    assert 'gaussian_only_suboption' in _codes(result.warnings)


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


@pytest.mark.parametrize('route,expected', [
    ('# HF/STO-3G Opt ! IRC Opt=TS\n', {'minimum_opt'}),
    ('# HF/STO-3G Opt\n ! IRC Opt=TS\n Freq\n', {'minimum_opt', 'frequency'}),
    ('# HF/STO-3G Opt\n ! unmatched quote " and parenthesis ( are comments\n Freq\n',
     {'minimum_opt', 'frequency'}),
    ('# HF/STO-3G\n ! IRC is a comment\n Opt=(TS,CalcFC)\n', {'ts_opt'}),
    ('# HF/STO-3G Opt=(TS,\n ! IRC and unmatched ( are comments\n CalcFC)\n', {'ts_opt'}),
])
def test_gaussian_route_comments_do_not_create_tasks_or_hide_continuation(route, expected):
    text = route + '\n# IRC and Opt=TS are title text!\n\n0 1\nH 0 0 0\n\n'

    intent = inspect_input(text, engine='gaussian')

    assert intent.tasks == expected
    assert (intent.charge, intent.multiplicity) == (0, 1)


@pytest.mark.parametrize('quote', ['"', "'"])
def test_gaussian_route_comments_preserve_bang_in_quoted_external_path(quote):
    from cloudra.tools.core.native_input_sections import gaussian_sections

    external = f'external={quote}/tmp/driver!native{quote}'
    text = (f'# {external} Opt ! IRC Opt=TS are comments\n'
            '\n# IRC Opt=TS is still title text!\n\n-1 2\nH 0 0 0\n\nkeep this trailing!\n')

    intent = inspect_input(text, engine='gaussian')
    section, = gaussian_sections(text)

    assert intent.tasks == {'minimum_opt'}
    assert intent.provider == 'driver!native'
    assert external in section.route
    assert section.charge == (-1, 2)
    assert section.geometry == ['H 0 0 0']
    assert 'keep this trailing!' in section.trailing


@pytest.mark.parametrize('second_route,expected', [
    ('# HF/STO-3G Freq ! Opt=TS is a comment\n', {'minimum_opt', 'frequency'}),
    ('# HF/STO-3G\n ! IRC is a comment\n Opt=TS\n', {'minimum_opt', 'ts_opt'}),
])
def test_gaussian_route_comments_preserve_link1_section_boundaries(second_route, expected):
    from cloudra.tools.core.native_input_sections import gaussian_sections

    first = '# HF/STO-3G Opt ! IRC is a comment\n\nfirst title!\n\n0 1\nH 0 0 0\n\n'
    second = second_route + '\nsecond title!\n\n-1 2\nH 0 0 1\n\n'
    text = first + '--Link1--\n' + second

    intent = inspect_input(text, engine='gaussian')
    sections = gaussian_sections(text)

    assert intent.tasks == expected
    assert [section.charge for section in sections] == [(0, 1), (-1, 2)]
    assert [section.geometry for section in sections] == [['H 0 0 0'], ['H 0 0 1']]


@pytest.mark.parametrize('comment', [
    '! basis selection (previous run',
    '! basis selection "previous run',
])
def test_gaussian_tail_comments_do_not_erase_explicit_gen_ts(comment):
    from cloudra.tools.core.native_input_sections import gaussian_sections

    tail = comment + '\nH 0\nSTO-3G\n****\n'
    text = '#p HF/Gen Opt=(TS,CalcFC)\n\nTS trial\n\n0 1\nH 0 0 0\n\n' + tail

    assert inspect_input(text, engine='gaussian').tasks == {'ts_opt'}
    section, = gaussian_sections(text)
    assert comment in section.trailing  # Native tail evidence retains its original text.


def test_gaussian_tail_comments_preserve_real_modredundant_scan_cards():
    tail = '! IRC Opt=TS are not tasks, and "( is just a comment\nB 1 2 S 5 0.1 ! old range (\n'
    arguments = dict(engine='gaussian', method='HF', basis_set='STO-3G',
        task_type=[{'opt': 'modredundant'}], end_setting=tail)
    text = '# HF/STO-3G Opt=ModRedundant\n\nscan\n\n0 1\nH 0 0 0\nH 0 0 1\n\n' + tail

    assert inspect_input(text, engine='gaussian').tasks == {'relaxed_scan'}
    assert intent_from_writer(arguments).tasks == {'relaxed_scan'}


@pytest.mark.parametrize('changed_basis', [False, True])
def test_gaussian_tail_comments_compare_settings_without_hiding_basis_changes(changed_basis):
    expected_tail = '! declared basis (\nH 0\nSTO-3G\n****\n'
    actual_tail = '! observed basis "\nH 0\n' + ('6-31G' if changed_basis else 'STO-3G') + '\n****\n'
    expected = dict(engine='gaussian', method='HF', basis_set='Gen', end_setting=expected_tail)
    text = '# HF/Gen Opt=TS\n\ntrial\n\n0 1\nH 0 0 0\n\n' + actual_tail

    differences = compare_calculation_input(text, expected, charge=0, multiplicity=1)

    assert {difference.field for difference in differences} == ({'end_setting'} if changed_basis else set())


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['gen_ts', 'modredundant_scan'])
async def test_gaussian_tail_comments_survive_writer_and_semantic_round_trip(tmp_path, kind):
    if kind == 'gen_ts':
        tail = '! basis selection (previous run\nO H 0\nSTO-3G\n****\n'
        task, basis, expected_tasks = 'ts', 'Gen', {'ts_opt'}
    else:
        tail = '! IRC and unmatched "( are comments\nB 1 2 S 5 0.1 ! old range (\n'
        task, basis, expected_tasks = 'modredundant', 'STO-3G', {'relaxed_scan'}

    result = await _writer(tmp_path, engine='gaussian', method='HF', basis_set=basis,
        task_type=[{'opt': task}], end_setting=tail, output_path=str(tmp_path / 'job.gjf'))

    assert result.is_success, result.message
    assert result.unapplied_options == []
    assert 'malformed_native_end_setting' not in _codes(result.warnings)
    content = (tmp_path / 'job.gjf').read_text()
    assert tail in content
    assert inspect_input(content, engine='gaussian').tasks == expected_tasks


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
