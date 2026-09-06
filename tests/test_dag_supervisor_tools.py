"""Supervisor 受限工具执行层（dag/supervisor_tools.py）的执行级测试。

不断言工具出现在 prompt，而是真实调用：get_skill 经 loader 成功、Hub
search 进入 runtime_v2 原生 bridge、解析引用可读；科研文件写、越界
symlink、compute 提交、未知工具在执行层被拒绝。
"""

import shutil
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from cloudra.dag.supervisor_tools import SupervisorToolExecutor
from cloudra.tools import capabilities

WORKSPACE = None  # set per-test via tmp_path


def _executor(tmp_path, *, core=None, project_id="prj_test", artifact_root=None):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    artifacts = artifact_root or (tmp_path / "artifacts")
    artifacts.mkdir(exist_ok=True)
    return SupervisorToolExecutor(
        core=core,
        project_id=project_id,
        workspace_root=str(workspace),
        artifact_root=str(artifacts),
    )


# --- capability 投影：registry 是唯一名单来源 ---


def test_capability_projection_matches_registry_declarations():
    assert capabilities.supervisor_access_for("get_skill") == "skill_read"
    assert capabilities.supervisor_access_for("read") == "evidence_read"
    assert capabilities.supervisor_access_for("log_parser") == "evidence_read"
    assert capabilities.supervisor_access_for("reaction_mapping") == "evidence_read"
    assert capabilities.supervisor_access_for("agent_hub") == "hub"
    assert capabilities.supervisor_access_for("dag_review_call") == "review_decision"
    assert capabilities.supervisor_access_for("bash") == "none"
    assert capabilities.supervisor_access_for("write") == "none"
    assert capabilities.supervisor_access_for("submit_compute_job") == "none"
    assert capabilities.supervisor_access_for("no_such_tool") == "none"
    allowed = capabilities.supervisor_allowed_tools()
    assert "bash" not in allowed and "get_skill" in allowed


def test_dag_message_supervisor_is_not_on_the_supervisor_wire():
    """dag_message_supervisor 是研究 Agent/Coordinator → Supervisor 的请求入口，
    工具本身硬拒 Supervisor 调用；它绝不能出现在 Supervisor 的工具投影里
    （督导的回复路径是裁决工具 + 运行结束报告，不是给自己发消息）。"""
    assert capabilities.supervisor_access_for("dag_message_supervisor") == "none"
    assert "dag_message_supervisor" not in capabilities.supervisor_allowed_tools()
    assert "dag_message_supervisor" not in capabilities.supervisor_tool_names()


# --- 拒绝路径：写操作、compute 提交、未知工具 ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,arguments",
    [
        ("write", {"path": "notes.md", "content": "x"}),
        ("edit", {"path": "notes.md", "edits": []}),
        ("bash", {"command": "echo hi"}),
        ("submit_compute_job", {"input_file": "x.inp"}),
        ("qm_input_writer", {"engine": "orca"}),
        ("definitely_not_a_tool", {}),
    ],
)
async def test_write_compute_and_unknown_tools_are_rejected(tmp_path, name, arguments):
    executor = _executor(tmp_path)
    result = await executor.execute(name, arguments, session_id="sup")
    assert result["is_success"] is False
    assert "permission denied" in result["message"]


# --- skill 读取 ---


@pytest.mark.asyncio
async def test_get_skill_loads_skill_and_reference(tmp_path):
    executor = _executor(tmp_path)
    result = await executor.execute(
        "get_skill", {"skill_name": "dft-calculation"}, session_id="sup"
    )
    assert result["is_success"] is True
    assert "mechanism" in result["content"].lower()

    ref = await executor.execute(
        "get_skill",
        {"skill_name": "dft-calculation", "reference": "supervisor-review.md"},
        session_id="sup",
    )
    assert ref["is_success"] is True
    assert "Judgment table" in ref["content"]


# --- 证据读取：受限文本读取与越界拒绝 ---


@pytest.mark.asyncio
async def test_read_inside_workspace_returns_content_and_reference(tmp_path):
    executor = _executor(tmp_path)
    target = tmp_path / "workspace" / "evidence.log"
    target.write_text("line1\nline2\nline3\n")

    result = await executor.execute("read", {"path": "evidence.log"}, session_id="sup")
    assert result["is_success"] is True
    assert result["content"] == "line1\nline2\nline3\n"
    assert result["total_lines"] == 3
    assert result["sha256"]
    assert result["path"].endswith("evidence.log")

    paged = await executor.execute(
        "read", {"path": "evidence.log", "offset": 2, "limit": 1}, session_id="sup"
    )
    assert paged["is_success"] is True
    assert paged["content"] == "line2\n"
    assert paged["offset"] == 2


@pytest.mark.asyncio
async def test_read_inside_artifact_root_allowed(tmp_path):
    from cloudra.infra.config import get_config
    from cloudra.persistence.artifacts import ArtifactService
    from cloudra.persistence.database import ConversationDB

    get_config().data_dir = tmp_path
    db = ConversationDB("prj_test", data_dir=tmp_path).init()
    with db.connect() as con:
        con.execute("INSERT INTO session(session_id, created_at) VALUES ('sup', '2026-01-01')")
    executor = _executor(tmp_path)
    source = tmp_path / "workspace" / "snapshot.log"
    source.write_text("artifact line\n")
    artifact = ArtifactService(data_dir=tmp_path).register_file(
        conversation_id="prj_test", session_id="sup", source=source,
        allowed_root=tmp_path / "workspace",
    )
    stored = tmp_path / "artifacts" / artifact.storage_path
    result = await executor.execute("read", {"path": str(stored)}, session_id="sup")
    assert result["is_success"] is True
    assert "artifact line" in result["content"]


@pytest.mark.asyncio
async def test_artifact_path_must_belong_to_current_project(tmp_path):
    from cloudra.infra.config import get_config
    from cloudra.persistence.artifacts import ArtifactService
    from cloudra.persistence.database import ConversationDB

    get_config().data_dir = tmp_path
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    source = workspace / "foreign.log"
    source.write_text("foreign\n")
    db = ConversationDB("project-b", data_dir=tmp_path).init()
    with db.connect() as con:
        con.execute("INSERT INTO session(session_id, created_at) VALUES ('sup-b', '2026-01-01')")
    artifact = ArtifactService(data_dir=tmp_path).register_file(
        conversation_id="project-b", session_id="sup-b", source=source,
        allowed_root=workspace,
    )
    foreign_path = tmp_path / "artifacts" / artifact.storage_path
    executor = _executor(tmp_path, project_id="project-a")
    result = await executor.execute("read", {"path": str(foreign_path)}, session_id="sup-a")
    assert result["is_success"] is False
    assert "not registered for this project" in result["message"]


@pytest.mark.asyncio
async def test_read_path_escape_and_outside_absolute_rejected(tmp_path):
    executor = _executor(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret\n")

    relative_escape = await executor.execute(
        "read", {"path": "../secret.txt"}, session_id="sup"
    )
    assert relative_escape["is_success"] is False
    assert "permission denied" in relative_escape["message"]

    absolute_outside = await executor.execute(
        "read", {"path": str(outside)}, session_id="sup"
    )
    assert absolute_outside["is_success"] is False
    assert "permission denied" in absolute_outside["message"]


@pytest.mark.asyncio
async def test_read_symlink_escape_rejected(tmp_path):
    executor = _executor(tmp_path)
    outside = tmp_path / "outside.log"
    outside.write_text("outside\n")
    link = tmp_path / "workspace" / "linked.log"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink not permitted on this platform")

    result = await executor.execute("read", {"path": "linked.log"}, session_id="sup")
    assert result["is_success"] is False


# --- 解析工具：路径门控 + 真实解析可读 ---


@pytest.mark.asyncio
async def test_log_parser_outside_root_rejected(tmp_path):
    executor = _executor(tmp_path)
    outside = tmp_path / "job.out"
    outside.write_text("fake\n")
    result = await executor.execute(
        "log_parser", {"log_path": str(outside)}, session_id="sup"
    )
    assert result["is_success"] is False
    assert "permission denied" in result["message"]


@pytest.mark.asyncio
async def test_log_parser_parses_fixture_inside_workspace(tmp_path):
    executor = _executor(tmp_path)
    fixture = tmp_path / "workspace" / "co2_freq.out"
    shutil.copy("tests/fixtures/orca/co2_freq_orca42.out", fixture)

    result = await executor.execute(
        "log_parser", {"log_path": "co2_freq.out"}, session_id="sup"
    )
    assert result["is_success"] is True
    assert result.get("engine") == "orca"
    assert result.get("scf_energy_hartree") is not None


@pytest.mark.asyncio
async def test_reaction_mapping_structure_path_escape_rejected(tmp_path):
    executor = _executor(tmp_path)
    outside = tmp_path / "mol.xyz"
    outside.write_text("2\nx\nH 0 0 0\nH 0 0 1\n")
    result = await executor.execute(
        "reaction_mapping",
        {
            "reactant_smiles": "C",
            "product_smiles": "C",
            "reactant_path": str(outside),
        },
        session_id="sup",
    )
    assert result["is_success"] is False
    assert "permission denied" in result["message"]


# --- AgentHub：原生 bridge、动作限权、call 不隐式 spawn ---


class _FakeEventLog:
    def __init__(self):
        self.envelopes = []
        self._seq = 0

    def query_project(self, project_id, *, types=None, limit=500):
        rows = [
            env
            for env in self.envelopes
            if env.project_id == project_id and (types is None or env.type in types)
        ]
        return rows[-limit:]

    def append(self, type_, *, stream, project_id, session_id, data):
        self._seq += 1
        env = SimpleNamespace(
            event_id=f"evt_{self._seq:04d}",
            seq=self._seq,
            type=type_,
            project_id=project_id,
            session_id=session_id,
            created_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
            data=data,
        )
        self.envelopes.append(env)
        return env


def _fake_core():
    return SimpleNamespace(
        event_log=_FakeEventLog(),
        agents={},
        project_id="prj_test",
    )


@pytest.mark.asyncio
async def test_hub_search_reaches_native_bridge(tmp_path):
    core = _fake_core()
    core.event_log.append(
        "hub.posted",
        stream="project",
        project_id="prj_test",
        session_id="as_researcher",
        data={
            "topic": "NumFreq on ExtOpt",
            "kind": "finding",
            "author_agent": "small_mol",
            "author_session": "as_researcher",
            "to_agent": None,
            "parent_id": None,
            "content": "ExtOpt Freq silently skips frequencies; use NumFreq explicitly.",
        },
    )
    executor = _executor(tmp_path, core=core)
    result = await executor.execute(
        "agent_hub", {"action": "search", "keyword": "NumFreq"}, session_id="sup"
    )
    assert result["is_success"] is True
    assert result["posts"], "hub search must surface the forum post from the event log"
    assert result["posts"][0]["topic"] == "NumFreq on ExtOpt"
    assert "library" in result


@pytest.mark.asyncio
async def test_hub_post_appends_event_via_bridge(tmp_path):
    core = _fake_core()
    executor = _executor(tmp_path, core=core)
    result = await executor.execute(
        "agent_hub",
        {"action": "post", "topic": "review note", "kind": "finding", "content": "verdict rationale"},
        session_id="sup",
    )
    assert result["is_success"] is True
    posted = [e for e in core.event_log.envelopes if e.type == "hub.posted"]
    assert len(posted) == 1
    assert posted[0].data["author_agent"] == "supervisor"


@pytest.mark.asyncio
async def test_hub_call_to_missing_target_is_target_not_found_no_spawn(tmp_path):
    core = _fake_core()
    executor = _executor(tmp_path, core=core)
    result = await executor.execute(
        "agent_hub",
        {"action": "call", "to": "small_mol", "message": "ping"},
        session_id="sup",
    )
    assert result["is_success"] is False
    assert "target_not_found" in result["message"]
    assert core.agents == {}, "supervisor hub call must never spawn an agent"


@pytest.mark.asyncio
async def test_hub_disallowed_action_rejected(tmp_path):
    executor = _executor(tmp_path, core=_fake_core())
    result = await executor.execute(
        "agent_hub", {"action": "delete", "topic": "x"}, session_id="sup"
    )
    assert result["is_success"] is False
    assert "permission denied" in result["message"]


@pytest.mark.asyncio
async def test_hub_without_core_reports_unavailable(tmp_path):
    executor = _executor(tmp_path, core=None)
    result = await executor.execute(
        "agent_hub", {"action": "search", "keyword": "irc"}, session_id="sup"
    )
    assert result["is_success"] is False
    assert "unavailable" in result["message"]
