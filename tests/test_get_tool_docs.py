"""The real document reader preserves authority and on-demand contracts."""
import importlib
import importlib.util
from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import AgentCapabilities, AgentSession, PermissionSet
from cloudra.runtime_v2.tool_catalog import javascript_instructions


def reader():
    assert importlib.util.find_spec('cloudra.tools.Skilltool.get_tool_docs') is not None, 'Document reader is missing'
    return importlib.import_module('cloudra.tools.Skilltool.get_tool_docs')


def agent(role='coordinator', names=None, read=True):
    return AgentSession(id='docs-agent', project_id='docs-project', role_id=role, display_name=role,
        capabilities=AgentCapabilities(permissions=PermissionSet(read=read), tools=names if names is not None else ['*']))


@pytest.mark.asyncio
async def test_reader_preserves_full_contract_for_unpreloaded_tool():
    mod = reader()
    a = agent(names=['ts_inspect', 'get_tool_docs'])
    tool = mod.GetToolDocs()
    object.__setattr__(tool, 'subagent', SimpleNamespace(_runtime_agent=a))
    result = await tool.tool_call(mod.GetToolDocs_input_schema(names=['ts_inspect']), None)
    assert result.is_success
    assert [doc.name for doc in result.documents] == ['ts_inspect']
    assert 'run_id' in result.documents[0].content
    assert a.capabilities.tools == ['ts_inspect', 'get_tool_docs']


@pytest.mark.asyncio
async def test_reader_rejects_whole_request_when_one_name_is_hidden():
    mod = reader()
    tool = mod.GetToolDocs()
    object.__setattr__(tool, 'subagent', SimpleNamespace(_runtime_agent=agent('explorer')))
    result = await tool.tool_call(mod.GetToolDocs_input_schema(names=['read', 'ts_prepare']), None)
    assert not result.is_success
    assert result.documents == []


@pytest.mark.asyncio
async def test_reader_requires_read_permission():
    mod = reader()
    tool = mod.GetToolDocs()
    object.__setattr__(tool, 'subagent', SimpleNamespace(_runtime_agent=agent(read=False)))
    result = await tool.tool_call(mod.GetToolDocs_input_schema(names=['read']), None)
    assert not result.is_success
    assert result.documents == []


def test_js_bootstrap_keeps_briefs_and_reader_but_not_business_types():
    instructions = javascript_instructions(['ts_prepare', 'ts_inspect', 'get_tool_docs'], role_id='coordinator')
    assert 'ts_prepare' in instructions
    assert 'ts_inspect' in instructions
    assert 'get_tool_docs(args:' in instructions
    assert 'ts_prepare(args:' not in instructions
    assert 'ts_inspect(args:' not in instructions


@pytest.mark.asyncio
async def test_real_executor_binds_document_scope(tmp_path):
    a = agent(names=['ts_inspect', 'get_tool_docs'])
    core = SimpleNamespace(require_project=lambda _: SimpleNamespace(workspace_dir=str(tmp_path)))
    result = await LegacyToolExecutor(core).execute(a, ToolCall('doc-call', 'get_tool_docs', {'names': ['ts_inspect']}))
    assert result.is_success
    assert result.data['documents'][0]['name'] == 'ts_inspect'
