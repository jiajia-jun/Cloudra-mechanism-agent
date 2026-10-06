"""Benchmark 方法与基组拦截；普通项目即使残留策略也不拦截。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.method_policy import check_input_content
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    InvocationProtocol,
    MethodPolicy,
    ProjectSettings,
    RuntimeSettings,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

_POLICY = {
    "allowed_methods": ["mace-omol25", "xtb"],
    "intercept_layers": ["bash", "submit_compute_job", "qm_input_writer"],
}
_BASH_B3LYP = "cat > ts.gjf <<'EOF'\n#p b3lyp/6-31g* opt\n\nt\n\n0 1\nC 0 0 0\nEOF\n"
_BASH_MACE = 'cat > ts.gjf <<\'EOF\'\n#p external="mace" opt freq\n\nt\n\n0 1\nC 0 0 0\nEOF\n'


def test_project_settings_method_policy_field():
    # 缺省不启用（live 侧绝不默认塞白名单）
    assert ProjectSettings().method_policy is None
    settings = ProjectSettings.model_validate({"method_policy": _POLICY})
    assert settings.method_policy is not None
    assert settings.method_policy.allowed_methods == ["mace-omol25", "xtb"]
    # extra="forbid" 仍然成立
    with pytest.raises(ValidationError):
        ProjectSettings.model_validate({"no_such_field": 1})


class _FakeLLM:
    def __init__(self, response: LLMResponse) -> None:
        self.response = response

    async def complete(self, agent, messages, tools, **_kwargs):
        return self.response


class _RecordingTools:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(self, agent, call: ToolCall) -> ToolResult:
        self.calls.append(call.name)
        return ToolResult(is_success=True, summary="ok")


async def _spawn(core: RuntimeCore, tmp_path, settings: dict | None = None):
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    payload: dict = {"name": "p", "workspace_dir": str(tmp_path)}
    if settings:
        payload["settings"] = settings
    await CommandBus(core).execute(Command(type="project.create", payload=payload))
    project = next(iter(core.projects.values()))
    await CommandBus(core).execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"})
    )
    agent = next(iter(core.agents.values()))
    # 本文件测试用 FakeLLM 直接发业务工具调用，固定传统协议；
    # 默认 javascript 协议只放 js_exec + 直接控制类。
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    return project, agent


async def _run_tool_turn(core: RuntimeCore, agent, tmp_path, call: ToolCall, run_id: str = "run_t"):
    tools = _RecordingTools()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=_FakeLLM(LLMResponse(content="", tool_calls=[call], stop_requested=False)),
        tools=tools,
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id=run_id,
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=agent.capabilities.permissions, tools=["*"]),
        inbox_messages=[{"content": "go"}],
        workspace_dir=str(tmp_path),
    )
    return outcome, tools


def _blocked_events(core: RuntimeCore, session_id: str):
    return [
        e
        for e in core.event_log.query_session(session_id)
        if e.type == "tool.blocked" and e.data.get("stage") == "method_policy"
    ]


@pytest.mark.asyncio
async def test_policy_project_blocks_non_whitelisted_bash(tmp_path):
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path, settings={"benchmark_task_id": "method-policy-fixture", "method_policy": _POLICY})
    outcome, tools = await _run_tool_turn(
        core, agent, tmp_path, ToolCall(id="t1", name="bash", arguments={"command": _BASH_B3LYP})
    )
    # 拦截不罚分：原因作为工具反馈回投，turn 继续
    assert outcome.decision == "continue"
    assert tools.calls == []
    blocked = _blocked_events(core, agent.id)
    assert blocked and "b3lyp" in blocked[0].data.get("message", "")


@pytest.mark.asyncio
async def test_policy_project_allows_whitelisted_bash(tmp_path):
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path, settings={"benchmark_task_id": "method-policy-fixture", "method_policy": _POLICY})
    outcome, tools = await _run_tool_turn(
        core, agent, tmp_path, ToolCall(id="t1", name="bash", arguments={"command": _BASH_MACE})
    )
    assert outcome.decision == "continue"
    assert tools.calls == ["bash"]
    assert _blocked_events(core, agent.id) == []


@pytest.mark.asyncio
async def test_policy_project_submit_compute_job_layer(tmp_path):
    (tmp_path / "evil.gjf").write_text("#p b3lyp/6-31g* opt\n\nt\n\n0 1\nC 0 0 0\n")
    (tmp_path / "ok.gjf").write_text('#p external="mace" opt\n\nt\n\n0 1\nC 0 0 0\n')
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path, settings={"benchmark_task_id": "method-policy-fixture", "method_policy": _POLICY})

    _, tools = await _run_tool_turn(
        core, agent, tmp_path,
        ToolCall(id="t1", name="submit_compute_job", arguments={"input_file": "evil.gjf"}),
        run_id="run_evil",
    )
    assert tools.calls == []
    assert _blocked_events(core, agent.id)

    _, tools = await _run_tool_turn(
        core, agent, tmp_path,
        ToolCall(id="t2", name="submit_compute_job", arguments={"input_file": "ok.gjf"}),
        run_id="run_ok",
    )
    assert tools.calls == ["submit_compute_job"]


@pytest.mark.asyncio
async def test_policy_project_bash_referencing_disk_input(tmp_path):
    """bash 层引用磁盘已有 QM 输入（`g16 foo.gjf`）走 referenced_input_paths +
    check_input_files 接线（stage 侧；纯函数覆盖在 test_benchmark.py）。"""
    (tmp_path / "evil.gjf").write_text("#p b3lyp/6-31g* opt\n\nt\n\n0 1\nC 0 0 0\n")
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path, settings={"benchmark_task_id": "method-policy-fixture", "method_policy": _POLICY})

    _, tools = await _run_tool_turn(
        core, agent, tmp_path,
        ToolCall(id="t1", name="bash", arguments={"command": "g16 evil.gjf"}),
        run_id="run_evil",
    )
    assert tools.calls == []
    blocked = _blocked_events(core, agent.id)
    assert blocked and "b3lyp" in blocked[0].data.get("message", "")


@pytest.mark.asyncio
async def test_project_without_policy_unaffected(tmp_path):
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path)
    outcome, tools = await _run_tool_turn(
        core, agent, tmp_path, ToolCall(id="t1", name="bash", arguments={"command": _BASH_B3LYP})
    )
    assert outcome.decision == "continue"
    assert tools.calls == ["bash"]
    assert _blocked_events(core, agent.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,args", [
    ("bash", {"command": _BASH_B3LYP}),
    ("qm_input_writer", {"method": "PBE0", "basis_set": "def2-TZVP"}),
    ("submit_compute_job", {"input_file": "ordinary.gjf"}),
])
async def test_ordinary_project_ignores_stored_method_policy(tmp_path, tool, args):
    (tmp_path / "ordinary.gjf").write_text("#p PBE0/def2TZVP opt\n\nt\n\n0 1\nO 0 0 0\n")
    core = RuntimeCore(strict_events=True)
    _, agent = await _spawn(core, tmp_path, settings={"method_policy": _POLICY})
    _, tools = await _run_tool_turn(core, agent, tmp_path, ToolCall(id="ordinary", name=tool, arguments=args))
    assert tools.calls == [tool]
    assert _blocked_events(core, agent.id) == []


@pytest.mark.asyncio
async def test_benchmark_settings_save_keeps_method_restrictions(tmp_path):
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    core = RuntimeCore(strict_events=True)
    project, agent = await _spawn(core, tmp_path, settings={"benchmark_task_id": "fixture", "method_policy": _POLICY})
    await CommandBus(core).execute(Command(type="project.update", target={"project_id": project.id},
        payload={"settings": {"orchestration_mode": "standard", "defaults": {}}}))
    _, tools = await _run_tool_turn(core, agent, tmp_path, ToolCall(id="after-save", name="bash", arguments={"command": _BASH_B3LYP}))
    assert tools.calls == []
    assert _blocked_events(core, agent.id)

    result = await CommandBus(core).execute(Command(type="project.update", target={"project_id": project.id},
        payload={"settings": {"benchmark_task_id": None}}))
    assert result.data["error"]["code"] == "invalid_request"
    assert core.projects[project.id].settings.benchmark_task_id == "fixture"


# ---------------------------------------------------------------------------
# Task 4（P1）：白名单三入口与原生 xTB 词表契约（现状特征化）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("method", "allowed"),
    [
        ("xtb", True),
        ("xTB2", True),          # 族粒度匹配：含 xtb 即命中（原生 xTB2 关键字）
        ("XTB GFN2", True),
        ("GFN2-xTB", True),
        ("xtb --gfn 2", True),
        ("b3lyp", False),
        ("wB97X-V", False),
        ("mace-omol25", False),  # 不在白名单的 MLIP 同样拦
        ("???", False),          # 无法解析的方法 fail-closed
        ("", False),
    ],
)
def test_method_whitelist_token_contract(method, allowed):
    """白名单按方法族匹配；无法解析的方法一律 fail-closed。"""
    from cloudra.runtime_v2.method_policy import check_method
    from cloudra.runtime_v2.schemas import MethodPolicy

    policy = MethodPolicy(allowed_methods=["xtb"])
    assert check_method(method, policy).allowed is allowed


def test_pm7_gaussian_scan_allowed_only_when_whitelisted():
    from cloudra.runtime_v2.method_policy import check_input_content
    from cloudra.runtime_v2.schemas import MethodPolicy

    content = "# opt=(modredundant,maxstep=10) pm7\n\nscan\n\n0 1\nH 0 0 0\nH 0 0 1\n\nB 1 2 S 10 0.1\n"
    assert check_input_content(
        content, MethodPolicy(allowed_methods=["xtb", "pm7", "b3lyp/def2svp"]), filename="scan.gjf"
    ).allowed is True
    assert check_input_content(
        content, MethodPolicy(allowed_methods=["xtb"]), filename="scan.gjf"
    ).allowed is False


def test_method_whitelist_three_layers_fail_closed(tmp_path):
    """三个拦截层（qm_input_writer / submit_compute_job / bash 内容）对无法
    解析的方法一致 fail-closed，且带空格目录里的磁盘输入同样被解析到。"""
    from cloudra.runtime_v2.method_policy import intercept
    from cloudra.runtime_v2.schemas import MethodPolicy

    policy = MethodPolicy(allowed_methods=["xtb"], intercept_layers=[
        "bash", "submit_compute_job", "qm_input_writer",
    ])
    space_dir = tmp_path / "Application Support" / "中文 C1"
    space_dir.mkdir(parents=True)

    # 1) qm_input_writer：显式方法字段
    assert intercept("qm_input_writer", {"method": "b3lyp"}, policy).allowed is False
    assert intercept("qm_input_writer", {"method": "xTB2"}, policy).allowed is True
    assert intercept("qm_input_writer", {"method": "???"}, policy).allowed is False
    assert intercept("qm_input_writer", {"external_program": "/opt/mace"}, policy).allowed is False

    # 2) submit_compute_job：按磁盘文件内容判定（含空格目录的相对/绝对引用）
    good = space_dir / "ok.inp"
    good.write_text("! XTB2 OPT FREQ\n* xyz 0 1\nC 0 0 0\n*\n", encoding="utf-8")
    bad = space_dir / "bad.gjf"
    bad.write_text("#p b3lyp/6-31g* opt\n\nt\n\n0 1\nC 0 0 0\n", encoding="utf-8")
    unparseable = space_dir / "weird.inp"
    unparseable.write_text("! ???\n* xyz 0 1\nC 0 0 0\n*\n", encoding="utf-8")

    assert intercept("submit_compute_job", {"input_file": str(good)}, policy).allowed is True
    assert intercept("submit_compute_job", {"input_file": str(bad)}, policy).allowed is False
    verdict = intercept("submit_compute_job", {"input_file": str(unparseable)}, policy)
    assert verdict.allowed is False and "not in allowed_methods" in verdict.reason
    # 相对路径按 sandbox root 解析（带空格目录）
    assert intercept(
        "submit_compute_job", {"input_file": "ok.inp"}, policy, base_dir=space_dir
    ).allowed is True
    assert intercept(
        "submit_compute_job", {"input_file": "bad.gjf"}, policy, base_dir=space_dir
    ).allowed is False

    # 3) bash：只按它写出的 QM 输入内容判定，不扫命令文本
    bash_ok = "cat > ts.inp <<'EOF'\n! XTB2 OPT\n* xyz 0 1\nC 0 0 0\n*\nEOF\n"
    bash_bad = "cat > ts.gjf <<'EOF'\n#p b3lyp/6-31g* opt\n\nt\n\n0 1\nC 0 0 0\nEOF\n"
    bash_unparseable = "cat > ts.inp <<'EOF'\n! ???\n* xyz 0 1\nC 0 0 0\n*\nEOF\n"
    assert intercept("bash", {"command": bash_ok}, policy).allowed is True
    assert intercept("bash", {"command": bash_bad}, policy).allowed is False
    assert intercept("bash", {"command": bash_unparseable}, policy).allowed is False
    # 与拦截层无关的工具不受影响
    assert intercept("write", {"path": "x.txt", "content": "b3lyp"}, policy).allowed is True


# ---------------------------------------------------------------------------
# 安全修复：mace 前缀撞名不再命中；畸形 external= 值 fail-closed
# ---------------------------------------------------------------------------


def test_family_mace_prefix_impostor_rejected():
    """`macefoo` 之类的前缀撞名不属于 mace 族（候选是外部程序 basename，
    startswith 会让同名恶意二进制过审）；连字符变体（mace-off 等）仍按族放行。"""
    from cloudra.runtime_v2.method_policy import check_method
    from cloudra.runtime_v2.schemas import MethodPolicy

    policy = MethodPolicy(allowed_methods=["mace", "xtb"])
    assert check_method("mace", policy).allowed is True
    assert check_method("mace-off", policy).allowed is True
    assert check_method("macefoo", policy).allowed is False
    assert check_method("macemania", policy).allowed is False


def test_malformed_gaussian_external_value_fail_closed():
    """畸形 external= 值（空格/引号注入）计入占位候选：即使同一张路由卡带
    合法 slash 方法也整体拦截，绝不静默丢弃后 fail-open。"""
    from cloudra.runtime_v2.method_policy import check_input_content
    from cloudra.runtime_v2.schemas import MethodPolicy

    policy = MethodPolicy(allowed_methods=["mace", "b3lyp/def2svp"])
    good = '#p external="mace" opt\n\nt\n\n0 1\nC 0 0 0\n'
    assert check_input_content(good, policy, filename="t.gjf").allowed is True
    injected = '#p b3lyp/def2svp external="mace --model x" opt\n\nt\n\n0 1\nC 0 0 0\n'
    verdict = check_input_content(injected, policy, filename="t.gjf")
    assert verdict.allowed is False
    assert "external" in verdict.matched_forbidden


def test_orca_progext_basename_prefix_impostor_rejected(tmp_path):
    """ORCA ExtOpt 路由：ProgExt basename 为 macefoo 时不再按 mace 放行。"""
    from cloudra.runtime_v2.method_policy import check_input_content
    from cloudra.runtime_v2.schemas import MethodPolicy

    policy = MethodPolicy(allowed_methods=["mace"])
    content = (
        "! ExtOpt Opt\n"
        '%method\n  ProgExt "/opt/bin/macefoo"\nend\n'
        "* xyz 0 1\nC 0 0 0\n*\n"
    )
    assert check_input_content(content, policy, filename="t.inp").allowed is False


# ---------------------------------------------------------------------------
# 误杀修复：ORCA 计算控制修饰词（优化等级/积分网格）不是方法候选
# ---------------------------------------------------------------------------


def test_orca_control_modifiers_not_method_candidates():
    """`! OptTS Freq TightOpt b3lyp def2-svp` 的唯一方法候选是 b3lyp/def2svp：
    OptTS/Freq/TightOpt 与基组 token 都不产出候选，白名单内放行。"""
    from cloudra.runtime_v2.method_policy import _extract_orca_methods, check_input_content
    from cloudra.runtime_v2.schemas import MethodPolicy

    content = "! OptTS Freq TightOpt b3lyp def2-svp\n* xyz 0 1\nC 0 0 0\n*\n"
    assert _extract_orca_methods(content) == ["b3lyp/def2svp"]
    policy = MethodPolicy(allowed_methods=["xtb", "b3lyp/def2svp"])
    assert check_input_content(content, policy, filename="t.inp").allowed is True


def test_orca_grid_modifier_out_of_whitelist_basis_still_blocked():
    """Grid5 不算方法候选，但 def2-tzvp 超白名单（只许 def2svp）仍 fail-closed。"""
    from cloudra.runtime_v2.method_policy import _extract_orca_methods, check_input_content
    from cloudra.runtime_v2.schemas import MethodPolicy

    content = "! Opt Grid5 B3LYP def2-TZVP\n* xyz 0 1\nC 0 0 0\n*\n"
    assert _extract_orca_methods(content) == ["b3lyp/def2tzvp"]
    policy = MethodPolicy(allowed_methods=["xtb", "b3lyp/def2svp"])
    verdict = check_input_content(content, policy, filename="t.inp")
    assert verdict.allowed is False
    assert "b3lyp/def2tzvp" in verdict.matched_forbidden


def test_orca_dashless_basis_spelling_pairs_with_functional():
    """Gaussian 风格的无连字符基组拼写（`def2svp`）出现在 ORCA `!` 行时同样
    识别为基组、与泛函配对成组合候选——否则 `! OPT b3lyp def2svp`（组合条目
    拼写直接进输入文件）会被拆成 b3lyp + def2svp 两个未授权候选而误杀。"""
    from cloudra.runtime_v2.method_policy import _extract_orca_methods, check_input_content
    from cloudra.runtime_v2.schemas import MethodPolicy

    content = "! OPT b3lyp def2svp\n* xyz 0 1\nC 0 0 0\n*\n"
    assert _extract_orca_methods(content) == ["b3lyp/def2svp"]
    policy = MethodPolicy(allowed_methods=["xtb", "b3lyp/def2svp"])
    assert check_input_content(content, policy, filename="t.inp").allowed is True


def test_orca_auxiliary_fit_basis_does_not_displace_orbital_basis():
    from cloudra.runtime_v2.method_policy import _extract_orca_methods, check_input_content
    from cloudra.runtime_v2.schemas import MethodPolicy

    policy = MethodPolicy(allowed_methods=["b3lyp/def2svp"])
    content = "! Opt B3LYP D3BJ def2-SVP RIJCOSX def2/J\n* xyz 0 1\nH 0 0 0\n*\n"
    assert _extract_orca_methods(content) == ["b3lyp/def2svp"]
    assert check_input_content(content, policy, filename="t.inp").allowed is True


def test_orca_auxiliary_fit_basis_does_not_allow_missing_or_ambiguous_orbital_basis():
    from cloudra.runtime_v2.method_policy import check_input_content
    from cloudra.runtime_v2.schemas import MethodPolicy

    policy = MethodPolicy(allowed_methods=["b3lyp/def2svp"])
    for route in (
        "! B3LYP def2/J",
        "! B3LYP def2-SVP def2-TZVP def2/J",
        "! PBE0 def2-SVP def2/J",
    ):
        content = route + "\n* xyz 0 1\nH 0 0 0\n*\n"
        assert check_input_content(content, policy, filename="t.inp").allowed is False


def test_orca_non_whitelisted_functional_still_blocked():
    """真正的非法泛函（pbe0）在修饰词扩充后仍被拦：白名单只放行 b3lyp/def2svp。"""
    from cloudra.runtime_v2.method_policy import check_input_content
    from cloudra.runtime_v2.schemas import MethodPolicy

    content = "! Opt PBE0 def2-svp\n* xyz 0 1\nC 0 0 0\n*\n"
    policy = MethodPolicy(allowed_methods=["xtb", "b3lyp/def2svp"])
    verdict = check_input_content(content, policy, filename="t.inp")
    assert verdict.allowed is False
    assert "pbe0/def2svp" in verdict.matched_forbidden


@pytest.mark.parametrize('solvent', ['DCM', 'Water', 'DMSO'])
def test_orca_cpcm_option_is_not_a_second_method(solvent):
    policy = MethodPolicy(allowed_methods=['b3lyp/def2svp'])
    content = (
        '! OptTS B3LYP def2-SVP D3BJ RIJCOSX def2/J TightSCF '
        f'CPCM({solvent})\n%pal nprocs 1 end\n'
        '* xyz 0 1\nO 0 0 0\n*\n'
    )
    verdict = check_input_content(content, policy, filename='refine.inp', strict=True)
    assert verdict.allowed, verdict.reason


@pytest.mark.parametrize('route', [
    'B3LYP def2-SVP CPCM(DCM) PBE0',
    'B3LYP def2-SVP CPCM(DCM',
    'B3LYP def2-SVP CPCM(DCM)PBE0',
    'B3LYP def2-SVP CPCM(DCM)(PBE0)',
    'B3LYP def2-SVP CPCM()',
    'def2-SVP CPCM(DCM)',
])
def test_orca_cpcm_option_does_not_hide_unverifiable_methods(route):
    policy = MethodPolicy(allowed_methods=['b3lyp/def2svp'])
    content = f'! OptTS {route}\n* xyz 0 1\nO 0 0 0\n*\n'
    assert not check_input_content(content, policy, filename='refine.inp', strict=True).allowed
