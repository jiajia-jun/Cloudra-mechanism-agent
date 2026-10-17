"""prompt_assembler 的装配面回归（角色 prompt、快照段、技能清单、读盘缓存）。

legacy 执行栈（``cloudra/core/agent.py`` 的 ``Agent``/``Coordinator``/``Follower``
与 ``core/message_history.py``）已随评审 5.4 删除：原先经 Agent 构造的
"身份/快照/能力 revision 随请求刷新"用例一并移除——那套语义现在活在在线路径的
``ContextPrefix`` 上，回归在 ``tests/test_runtime_v2_context_cache.py``
（workspace/memory/AGENTS.md 变更、静态前缀稳定、重试复用同一请求）与
``tests/test_runtime_v2_adapters.py``（provider 与 js 指令安装）。

这里只留 ``PromptAssembler`` 自身的装配与读盘缓存契约——它是在线路径
``runtime_v2/adapters.py`` 的 ``LegacyPromptProvider`` 真实调用面。
"""

from types import SimpleNamespace

import pytest


@pytest.fixture
def isolated_prompt_sources(tmp_path, monkeypatch):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    config = SimpleNamespace(config_file=config_dir / "config.toml")

    monkeypatch.setattr(
        "cloudra.runtime.prompt_assembler.PROMPTS_DIR",
        prompts_dir,
    )
    monkeypatch.setattr(
        "cloudra.runtime.prompt_assembler.get_config",
        lambda: config,
    )
    return prompts_dir, workspace

def test_web_search_guidance_gated_by_availability(isolated_prompt_sources):
    """联网搜索引导仅在声明有搜索能力时注入。"""
    from cloudra.runtime.prompt_assembler import PromptAssembler

    prompts_dir, workspace = isolated_prompt_sources
    (prompts_dir / "probe.md").write_text("# 角色", encoding="utf-8")
    assembler = PromptAssembler(
        prompt_name="probe",
        custom_prompt=None,
        conversation_id="c",
        working_directory=str(workspace),
        include_memory=False,
    )

    with_guidance = assembler.assemble(
        ["web_search"], web_search_available=True
    )
    assert "Web search" in with_guidance.identity_messages[0]["content"]

    without = assembler.assemble(
        ["web_search"], web_search_available=False
    )
    assert "Web search" not in without.identity_messages[0]["content"]

def test_clean_context_filters_real_memory_and_agents_but_keeps_role_and_skills(
    tmp_path, isolated_prompt_sources, monkeypatch
):
    from cloudra.runtime import prompt_assembler as module
    from cloudra.runtime.prompt_assembler import PromptAssembler

    prompts_dir, workspace = isolated_prompt_sources
    (prompts_dir / "probe.md").write_text("ROLE_SENTINEL", encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "AGENTS.md").write_text("GLOBAL_AGENTS_SENTINEL", encoding="utf-8")
    memory_path = tmp_path / "MEMORY.md"
    memory_path.write_text("GLOBAL_MEMORY_SENTINEL", encoding="utf-8")
    monkeypatch.setattr(module, "get_config", lambda: SimpleNamespace(config_file=config_dir / "config.yaml"))
    monkeypatch.setattr(
        module, "get_memory_manager", lambda **_: SimpleNamespace(memory_path=memory_path)
    )

    def assemble(clean: bool):
        return PromptAssembler(
            prompt_name="probe", custom_prompt=None, conversation_id="c",
            working_directory=str(workspace), include_memory=not clean,
            include_agents_md=not clean,
        ).assemble(["get_skill"])

    def observed(assembly) -> str:
        return "\n\n".join(
            str(message.get("content") or "")
            for message in assembly.observation_messages
        )

    clean_asm = assemble(True)
    dirty_asm = assemble(False)
    clean = clean_asm.identity_messages[0]["content"]
    dirty = dirty_asm.identity_messages[0]["content"]
    assert "ROLE_SENTINEL" in clean and "get_skill" in clean
    # MEMORY/AGENTS.md 是带来源的动态快照（observation 侧），不进 identity。
    assert "GLOBAL_MEMORY_SENTINEL" not in clean
    assert "GLOBAL_AGENTS_SENTINEL" not in clean
    assert "GLOBAL_MEMORY_SENTINEL" not in observed(clean_asm)
    assert "GLOBAL_AGENTS_SENTINEL" not in observed(clean_asm)
    assert "GLOBAL_MEMORY_SENTINEL" not in dirty
    assert "GLOBAL_AGENTS_SENTINEL" not in dirty
    assert "GLOBAL_MEMORY_SENTINEL" in observed(dirty_asm)
    assert "GLOBAL_AGENTS_SENTINEL" in observed(dirty_asm)
    assert [s.kind for s in dirty_asm.observation_sources][:2] == ["memory", "agents_md"]

def test_agent_hub_guidance_injected_when_tool_present(isolated_prompt_sources):
    """有 agent_hub 工具时注入并行共享引导，否则不注入。"""
    from cloudra.runtime.prompt_assembler import PromptAssembler

    prompts_dir, workspace = isolated_prompt_sources
    (prompts_dir / "probe.md").write_text("# 角色", encoding="utf-8")
    assembler = PromptAssembler(
        prompt_name="probe",
        custom_prompt=None,
        conversation_id="c",
        working_directory=str(workspace),
        include_memory=False,
    )

    with_hub = assembler.assemble(["bash", "agent_hub"])
    assert "agent_hub_guidance" in {source.kind for source in with_hub.sources}
    assert "AgentHub" in with_hub.identity_messages[0]["content"]
    assert "agent_hub" in with_hub.identity_messages[0]["content"]
    assert "handoff" in with_hub.identity_messages[0]["content"]
    assert "directory" in with_hub.identity_messages[0]["content"]
    assert "call" in with_hub.identity_messages[0]["content"]
    assert "[Incoming call]" in with_hub.identity_messages[0]["content"]

    without_hub = assembler.assemble(["bash"])
    assert "agent_hub_guidance" not in {source.kind for source in without_hub.sources}
    assert "handoff" in without_hub.identity_messages[0]["content"]

def test_skill_manifest_collapses_multiline_description(
    tmp_path,
    isolated_prompt_sources,
    monkeypatch,
):
    """YAML 多行块标量 description 在 manifest 里压成单行，不渲染成断裂列表。"""
    from cloudra.runtime.prompt_assembler import PromptAssembler

    prompts_dir, workspace = isolated_prompt_sources
    (prompts_dir / "probe.md").write_text("# 角色", encoding="utf-8")
    skills = tmp_path / "skills"
    skill = skills / "multiline" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: multiline\ndescription: >\n  第一行\n  第二行\n---\n正文",
        encoding="utf-8",
    )
    monkeypatch.setattr("cloudra.runtime.prompt_assembler.SKILLS_DIR", skills)

    assembler = PromptAssembler(
        prompt_name="probe",
        custom_prompt=None,
        conversation_id="c",
        working_directory=str(workspace),
        include_memory=False,
    )
    content = assembler.assemble([]).identity_messages[0]["content"]

    assert "- multiline: 第一行 第二行" in content
    assert "第一行\n" not in content

def test_supervisor_prompt_follows_mtime_cache(tmp_path, monkeypatch):
    """load_supervisor_prompt 走 load_role_prompt 的 mtime 缓存，改文件即生效。"""
    import cloudra.runtime.prompt_assembler as assembler_mod
    from cloudra.dag.models import load_supervisor_prompt

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "supervisor.md").write_text("督导第一版", encoding="utf-8")
    monkeypatch.setattr(assembler_mod, "PROMPTS_DIR", prompts_dir)

    assert load_supervisor_prompt() == "督导第一版"
    (prompts_dir / "supervisor.md").write_text("督导第二版", encoding="utf-8")
    assert load_supervisor_prompt() == "督导第二版"

    (prompts_dir / "supervisor.md").unlink()
    assert "graph-planning Supervisor" in load_supervisor_prompt()

def test_same_size_rewrite_within_one_mtime_tick_is_visible(tmp_path, monkeypatch):
    """同刻度 + 同字节长度的改写必须立即生效：签名不动不代表内容没变。

    直接构造文件系统给出的那种签名——改写后把 mtime 复位成第一次写入的值，
    两版内容字节长度相同。这正是 (mtime_ns, size) 签名失效的形态：旧实现会
    把第二版判成"未变"并返回第一版（本机实测偶发红）。
    """
    import os

    import cloudra.runtime.prompt_assembler as assembler_mod
    from cloudra.dag.models import load_supervisor_prompt

    first, second = "督导第一版", "督导第二版"
    # 长度必须相同，否则 size 就能察觉变化、这条用例失去判别力。
    assert len(first.encode("utf-8")) == len(second.encode("utf-8"))

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    prompt_file = prompts_dir / "supervisor.md"
    prompt_file.write_text(first, encoding="utf-8")
    monkeypatch.setattr(assembler_mod, "PROMPTS_DIR", prompts_dir)
    first_tick = prompt_file.stat().st_mtime_ns
    first_size = prompt_file.stat().st_size

    assert load_supervisor_prompt() == first

    prompt_file.write_text(second, encoding="utf-8")
    # 模拟"同一时间戳刻度内改写"：mtime 不推进，字节长度也不变。
    assert prompt_file.stat().st_size == first_size
    os.utime(prompt_file, ns=(first_tick, first_tick))
    assert prompt_file.stat().st_mtime_ns == first_tick

    assert load_supervisor_prompt() == second

def test_same_size_rewrite_within_one_mtime_tick_is_visible_in_skill_manifest(
    tmp_path, isolated_prompt_sources, monkeypatch
):
    """skills manifest 缓存与文件内容缓存同源，同刻度同长度的 SKILL.md 同样必须生效。"""
    import os

    from cloudra.runtime.prompt_assembler import PromptAssembler

    prompts_dir, workspace = isolated_prompt_sources
    (prompts_dir / "probe.md").write_text("# 角色", encoding="utf-8")
    skills = tmp_path / "skills"
    skill_file = skills / "review" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: review\ndescription: 第一版\n---\n正文 v1", encoding="utf-8"
    )
    monkeypatch.setattr("cloudra.runtime.prompt_assembler.SKILLS_DIR", skills)
    first_tick = skill_file.stat().st_mtime_ns
    first_size = skill_file.stat().st_size

    assembler = PromptAssembler(
        prompt_name="probe",
        custom_prompt=None,
        conversation_id="c",
        working_directory=str(workspace),
        include_memory=False,
    )
    assert "第一版" in assembler.assemble([]).identity_messages[0]["content"]

    skill_file.write_text(
        "---\nname: review\ndescription: 第二版\n---\n正文 v2", encoding="utf-8"
    )
    assert skill_file.stat().st_size == first_size
    os.utime(skill_file, ns=(first_tick, first_tick))

    assert "第二版" in assembler.assemble([]).identity_messages[0]["content"]

def test_stable_signature_reuses_cache_without_rereading(tmp_path, monkeypatch):
    """负向判据：窗口外的稳定文件必须命中缓存（只读一次盘）——修签名不许拆掉缓存。"""
    import os
    import time as _time
    from pathlib import Path

    import cloudra.runtime.prompt_assembler as assembler_mod

    target = tmp_path / "MEMORY.md"
    target.write_text("稳定内容", encoding="utf-8")
    # 把 mtime 推到不稳定窗口之外，模拟"长期未被改写"的稳定文件。
    stale_ns = _time.time_ns() - 60_000_000_000
    os.utime(target, ns=(stale_ns, stale_ns))

    reads = []
    real_read_text = Path.read_text

    def counting_read_text(self, *args, **kwargs):
        reads.append(self)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    assert assembler_mod._read_file_cached(target) == "稳定内容"
    assert assembler_mod._read_file_cached(target) == "稳定内容"
    assert len(reads) == 1, f"稳定文件应只读一次盘（命中缓存），实际读了 {len(reads)} 次"
