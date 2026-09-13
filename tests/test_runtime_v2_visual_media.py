"""Visual mode: image re-injection, user image upload linkage, artifact registration.

Covers the media half of the visual-mode feature (the settings/schema half
lives in test_runtime_v2_visual_mode.py): tool-result image re-injection into
LLM history, text fallback when the model has no vision support, compaction
downgrade of image parts, user-attached images through agent.message, the
upload endpoint, and artifact registration at tool.finished.
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest

from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import Command, InvocationProtocol
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

# 1x1 transparent PNG
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class RecordingLLM:
    """Scripted responses; records every request's messages."""

    def __init__(self, responses: list[LLMResponse], *, supports_vision=None) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict]] = []
        self._supports_vision = supports_vision

    async def complete(self, agent, messages, tools, **_kwargs):
        self.calls.append(list(messages))
        assert self.responses, "no scripted LLM response left"
        return self.responses.pop(0)

    def supports_vision(self, agent) -> bool:
        if self._supports_vision is None:
            return True
        return self._supports_vision(agent)


class ImageTools:
    def __init__(self, image_path: str, *, data: dict | None = None) -> None:
        self.image_path = image_path
        self._data = data

    async def execute(self, agent, call: ToolCall, **_kwargs) -> ToolResult:
        data = self._data if self._data is not None else {"image_path": self.image_path}
        return ToolResult(is_success=True, summary=f"rendered: {self.image_path}", data=data)


async def _setup(llm, tools, *, workspace_dir: str | None = None):
    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=tools,
    )
    core.runner = AgentRunner(core, pipeline)
    bus = CommandBus(core)
    payload = {"name": "visual demo"}
    if workspace_dir:
        payload["workspace_dir"] = workspace_dir
    await bus.execute(Command(type="project.create", payload=payload))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "render it"},
        )
    )
    agent = result.data
    # RecordingLLM 直接发业务工具调用（pymol_render 等），固定传统协议；
    # 默认 javascript 协议只放 js_exec + 直接控制类。
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    return core, project, agent


async def _wait_for(predicate, timeout: float = 2.0, message: str = "condition not met"):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(message)
        await asyncio.sleep(0.01)


def _write_png(tmp_path, name: str = "render.png") -> str:
    path = tmp_path / name
    path.write_bytes(_PNG_BYTES)
    return str(path)


def _scripted_tool_turn(llm: RecordingLLM, tool_name: str = "pymol_render") -> None:
    llm.responses.extend(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name=tool_name, arguments={"x": 1})],
            ),
            LLMResponse(content="done", stop_requested=True),
        ]
    )


@pytest.mark.asyncio
async def test_tool_result_image_reinjected_as_parts(tmp_path):
    image = _write_png(tmp_path)
    llm = RecordingLLM([])
    _scripted_tool_turn(llm)
    core, _, agent = await _setup(llm, ImageTools(image))
    await _wait_for(lambda: len(llm.calls) >= 2, message="second LLM call never happened")
    tool_messages = [m for m in llm.calls[1] if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    content = tool_messages[0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": f"rendered: {image}"}
    assert content[1]["type"] == "image_url"
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == _PNG_BYTES


@pytest.mark.asyncio
async def test_tool_result_image_text_fallback_when_no_vision(tmp_path):
    image = _write_png(tmp_path)
    llm = RecordingLLM([], supports_vision=lambda agent: False)
    _scripted_tool_turn(llm)
    core, _, agent = await _setup(llm, ImageTools(image))
    await _wait_for(lambda: len(llm.calls) >= 2, message="second LLM call never happened")
    content = [m for m in llm.calls[1] if m.get("role") == "tool"][0]["content"]
    assert isinstance(content, str)
    assert image in content
    assert "no vision support" in content


@pytest.mark.asyncio
async def test_tool_result_image_plain_text_when_visual_mode_off(tmp_path):
    # visual_mode=False 时 visual 工具在 permission stage 就被拦（见
    # policies/permission.py），所以这里用一个普通工具验证 runner 侧的回退：
    # 带 image_path 的结果保持纯文本，每条路径一行 fallback，不回注图片。
    image = _write_png(tmp_path)
    llm = RecordingLLM([])
    _scripted_tool_turn(llm, tool_name="echo")
    core, _, agent = await _setup(llm, ImageTools(image))
    agent.settings = agent.settings.model_copy(update={"visual_mode": False})
    await _wait_for(lambda: len(llm.calls) >= 2, message="second LLM call never happened")
    content = [m for m in llm.calls[1] if m.get("role") == "tool"][0]["content"]
    assert isinstance(content, str)
    assert content.startswith(f"rendered: {image}")
    assert "Image rendered at:" in content
    assert image in content


@pytest.mark.asyncio
async def test_tool_result_without_image_stays_text(tmp_path):
    llm = RecordingLLM([])
    _scripted_tool_turn(llm)
    core, _, agent = await _setup(llm, ImageTools("", data={"other": 1}))
    await _wait_for(lambda: len(llm.calls) >= 2, message="second LLM call never happened")
    content = [m for m in llm.calls[1] if m.get("role") == "tool"][0]["content"]
    assert isinstance(content, str)


@pytest.mark.asyncio
async def test_user_images_flow_into_event_and_parts(tmp_path):
    image = _write_png(tmp_path)
    llm = RecordingLLM([LLMResponse(content="first", stop_requested=True)])
    core, project, agent = await _setup(llm, ImageTools(""))
    await _wait_for(lambda: len(llm.calls) >= 1, message="first LLM call never happened")
    llm.responses.append(LLMResponse(content="second", stop_requested=True))
    bus = CommandBus(core)
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "look at this", "images": [image]},
        )
    )
    await _wait_for(lambda: len(llm.calls) >= 2, message="second LLM call never happened")
    injected = [
        e for e in core.event_log.query_session(agent.id)
        if e.type == "agent.message_injected" and e.data.get("images")
    ]
    assert injected and injected[-1].data["images"] == [image]
    user_messages = [
        m for m in llm.calls[1]
        if m.get("role") == "user" and isinstance(m.get("content"), list)
    ]
    assert user_messages, "user message with image parts not found"
    content = user_messages[-1]["content"]
    assert content[0] == {"type": "text", "text": "look at this"}
    assert any(p.get("type") == "image_url" for p in content)


@pytest.mark.asyncio
async def test_user_images_text_fallback_when_no_vision(tmp_path):
    image = _write_png(tmp_path)
    llm = RecordingLLM(
        [LLMResponse(content="first", stop_requested=True)],
        supports_vision=lambda agent: False,
    )
    core, project, agent = await _setup(llm, ImageTools(""))
    await _wait_for(lambda: len(llm.calls) >= 1, message="first LLM call never happened")
    llm.responses.append(LLMResponse(content="second", stop_requested=True))
    bus = CommandBus(core)
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "look at this", "images": [image]},
        )
    )
    await _wait_for(lambda: len(llm.calls) >= 2, message="second LLM call never happened")
    user_texts = [
        m["content"] for m in llm.calls[1]
        if m.get("role") == "user" and isinstance(m.get("content"), str)
    ]
    assert any(f"[User attached image: {image}]" in text for text in user_texts)


@pytest.mark.asyncio
async def test_compaction_downgrades_image_parts():
    """图像在摘要输入里降级为既有文本描述/可回读引用——base64 绝不进
    摘要调用；投影里的 image_ref 用创建时写入的 fallback 文本。"""
    from cloudra.runtime_v2.compaction import compact_context

    data_url = "data:image/png;base64," + base64.b64encode(_PNG_BYTES).decode()
    history = [
        {"role": "user", "content": "render the molecule"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "tc1", "name": "render", "arguments": {}}],
        },
        {
            "role": "tool",
            "tool_call_id": "tc1",
            "content": [
                {"type": "text", "text": "rendered: /tmp/render.png"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "tc2",
            "content": [
                {"type": "text", "text": "rendered again"},
                {
                    "type": "image_ref",
                    "path": "/tmp/render2.png",
                    "fallback": "[Image rendered at: /tmp/render2.png]",
                },
            ],
        },
        {"role": "assistant", "content": "done"},
    ]
    # 让轨迹真实长于摘要：大 assistant 段 + 第二条指令（把尾部收窄到最后
    # 一章），否则活动章节覆盖一切、没有可压缩的轨迹
    history.insert(1, {"role": "assistant", "content": "y" * 5000})
    history.insert(-1, {"role": "user", "content": "next step"})
    seen: list[list[dict]] = []

    async def fake_summarize(messages, **_kwargs):
        import json as _json

        seen.append(messages)
        return _json.dumps(
            {
                "objective": {"text": "SUMMARY", "sources": []},
                "active_requests": [], "corrections": [], "constraints": [],
                "pending": [], "completed": [], "failed_attempts": [],
                "evidence": [], "next_actions": [],
            },
            ensure_ascii=False,
        )

    new_context, stats = await compact_context(
        history,
        head=[],
        notices=[],
        keep_recent=1,
        summarize=fake_summarize,
        context_window=200_000,
        max_output=32_768,
    )
    assert stats["compacted"] is True
    serialized = seen[0][1]["content"]
    assert "base64" not in serialized
    assert "[Image: image/png attachment omitted during compaction]" in serialized
    assert "[Image rendered at: /tmp/render2.png]" in serialized
    assert "rendered: /tmp/render.png" in serialized
    # 逐字尾部保持部件原样（只有被摘要的轨迹段做文本降级）
    assert new_context[-1]["content"] == "done"


@pytest.mark.asyncio
async def test_tool_image_registered_as_artifact(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    image = workspace / "render.png"
    image.write_bytes(_PNG_BYTES)
    llm = RecordingLLM([])
    _scripted_tool_turn(llm)
    core, project, agent = await _setup(llm, ImageTools(str(image)), workspace_dir=str(workspace))
    await _wait_for(lambda: agent.state.value == "succeeded", message="run never finished")
    finished = [
        e for e in core.event_log.query_session(agent.id)
        if e.type == "tool.finished" and e.data.get("is_success")
    ]
    assert finished, "tool.finished not found"
    artifact_id = finished[-1].data.get("artifact_id")
    assert artifact_id, "artifact_id missing from tool.finished"

    from cloudra.infra.config import get_config
    from cloudra.persistence.artifacts import ArtifactService

    service = ArtifactService(Path(get_config().data_dir))
    artifacts = await asyncio.to_thread(service.list, project.id)
    assert [a.artifact_id for a in artifacts] == [artifact_id]
    assert artifacts[0].name == "render.png"


@pytest.mark.asyncio
async def test_tool_finished_event_includes_all_image_paths(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    pngs = []
    for i in range(3):
        path = workspace / f"{i}.png"
        path.write_bytes(_PNG_BYTES)
        pngs.append(str(path))
    llm = RecordingLLM([])
    _scripted_tool_turn(llm)
    core, project, agent = await _setup(
        llm,
        ImageTools(pngs[0], data={"image_paths": pngs, "image_path": pngs[0]}),
        workspace_dir=str(workspace),
    )
    await _wait_for(lambda: agent.state.value == "succeeded", message="run never finished")
    finished = [
        e for e in core.event_log.query_session(agent.id)
        if e.type == "tool.finished" and e.data.get("is_success")
    ]
    assert finished, "tool.finished not found"
    data = finished[-1].data
    assert data["image_path"] == pngs[0]
    assert data["image_paths"] == pngs
    assert data.get("artifact_id")

    from cloudra.infra.config import get_config
    from cloudra.persistence.artifacts import ArtifactService

    artifacts = await asyncio.to_thread(ArtifactService(Path(get_config().data_dir)).list, project.id)
    assert len(artifacts) == 3


@pytest.mark.asyncio
async def test_tool_image_outside_workspace_not_registered(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = _write_png(tmp_path)  # outside the workspace root
    llm = RecordingLLM([])
    _scripted_tool_turn(llm)
    core, project, agent = await _setup(llm, ImageTools(outside), workspace_dir=str(workspace))
    await _wait_for(lambda: agent.state.value == "succeeded", message="run never finished")
    finished = [
        e for e in core.event_log.query_session(agent.id)
        if e.type == "tool.finished" and e.data.get("is_success")
    ]
    assert finished and "artifact_id" not in finished[-1].data


# ---------------------------------------------------------------------- uploads


def _upload_client(tmp_path, *, with_workspace: bool = True):
    from fastapi.testclient import TestClient

    from cloudra.services.api_v2 import create_v2_app

    client = TestClient(create_v2_app())
    payload = {"name": "uploads demo"}
    if with_workspace:
        payload["workspace_dir"] = str(tmp_path / "ws")
    created = client.post("/api/v2/projects", json=payload)
    assert created.status_code == 201, created.text
    project_id = created.json()["data"]["id"]
    return client, project_id


def test_upload_endpoint_stores_file_and_artifact(tmp_path):
    client, project_id = _upload_client(tmp_path)
    response = client.post(
        f"/api/v2/projects/{project_id}/uploads",
        files={"file": ("structure.png", _PNG_BYTES, "image/png")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    path = Path(body["path"])
    assert path.is_file()
    assert path.read_bytes() == _PNG_BYTES
    workspace = tmp_path / "ws"
    assert path.parent == workspace / ".cloudra" / "uploads"
    assert body["artifact_id"]

    artifacts = client.get(f"/api/v2/projects/{project_id}/artifacts").json()
    assert [a["artifact_id"] for a in artifacts] == [body["artifact_id"]]


def test_upload_endpoint_rejects_unsupported_type(tmp_path):
    client, project_id = _upload_client(tmp_path)
    response = client.post(
        f"/api/v2/projects/{project_id}/uploads",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_upload_endpoint_rejects_oversize(tmp_path):
    client, project_id = _upload_client(tmp_path)
    response = client.post(
        f"/api/v2/projects/{project_id}/uploads",
        files={"file": ("big.png", b"\x00" * (20 * 1024 * 1024 + 1), "image/png")},
    )
    assert response.status_code == 413


def test_upload_endpoint_without_workspace_falls_back_to_default_workspace(tmp_path):
    """未显式指定 workspace 的项目：上传落到 per-project 默认工作区的
    .cloudra/uploads（与 read/write/bash 同一根，GH #24），不再走 data_dir/uploads 旁路。"""
    client, project_id = _upload_client(tmp_path, with_workspace=False)
    response = client.post(
        f"/api/v2/projects/{project_id}/uploads",
        files={"file": ("structure.jpg", _PNG_BYTES, "image/jpeg")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    path = Path(body["path"])
    assert path.is_file()

    from cloudra.infra.config import get_config

    default_ws = Path(get_config().data_dir) / "workspaces" / project_id
    assert path.parent == default_ws / ".cloudra" / "uploads"
