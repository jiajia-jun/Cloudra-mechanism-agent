"""评审 5.1 验收「API 返回」层：协议默认经 v2 API 读取与 schema 同口径。

口径（评审 5.1 / AGENTS.md）：
- schema 默认 `javascript`；项目层 patch 语义是「不设置 = 继承」，不写死另一协议；
- 显式 `traditional` 经 API PATCH 生效，且不被默认值覆盖（负向判据）。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command
from cloudra.services.api_v2 import create_v2_app


async def _execute(core: RuntimeCore, type_: str, **kwargs):
    command = Command(
        type=type_, target=kwargs.pop("target", {}), payload=kwargs.pop("payload", {})
    )
    return await CommandBus(core).execute(command)


@pytest.mark.asyncio
async def test_protocol_default_is_consistent_through_the_v2_api():
    core = RuntimeCore(strict_events=True)
    project = (
        await _execute(core, "project.create", payload={"name": "api-default"})
    ).data
    agent = (
        await _execute(
            core,
            "agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "go"},
        )
    ).data

    app = create_v2_app(core)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # 1) 新 Agent 的有效设置：默认 javascript
        body = (await client.get(f"/api/v2/agents/{agent.id}")).json()
        assert body["settings"]["invocation_protocol"] == "javascript"
        # 2) 项目层：patch 语义为继承（defaults 里不写死另一个协议）
        project_body = (await client.get(f"/api/v2/projects/{project.id}")).json()
        assert project_body["settings"]["defaults"]["invocation_protocol"] is None
        # 3) 显式覆盖经 API 生效、不被默认值覆盖（负向判据）
        resp = await client.patch(
            f"/api/v2/agents/{agent.id}/settings",
            json={"invocation_protocol": "traditional"},
        )
        assert resp.status_code == 200
        again = (await client.get(f"/api/v2/agents/{agent.id}")).json()
        assert again["settings"]["invocation_protocol"] == "traditional"
