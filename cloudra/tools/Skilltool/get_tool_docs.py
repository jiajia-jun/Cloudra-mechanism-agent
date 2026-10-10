"""Read exact tool contracts without changing executable capabilities."""
from typing import Any

from pydantic import ConfigDict, Field, StrictStr

from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.tools.documentation import ToolDocument


class GetToolDocs_input_schema(input_schema):
    model_config = ConfigDict(extra='forbid')
    names: list[StrictStr] = Field(description='Exact tool names from the current capability directory.')


class GetToolDocs_output_schema(output_schema):
    is_success: bool = True
    message: str = ''
    documents: list[ToolDocument] = Field(default_factory=list)


class GetToolDocs(Tool):
    tool_id: str = 't-tool-docs'
    tool_name: str = 'get_tool_docs'
    tool_description: str = ('Read the complete current argument and result contracts for exact tool names. '
        'Load a contract before constructing unfamiliar arguments. Reading documentation does not grant permissions. '
        'Additional skill references can be read with get_skill.')
    input_schema: Any = GetToolDocs_input_schema
    output_schema: Any = GetToolDocs_output_schema

    def is_read(self):
        return True

    async def tool_call(self, user_input, session):
        import asyncio
        return await asyncio.to_thread(self._load, user_input)

    def _load(self, user_input):
        from cloudra.runtime_v2.tool_catalog import guest_tool_names
        from cloudra.tools import get_tools_lst
        from cloudra.tools.documentation import build_tool_documents

        try:
            agent = self.subagent._runtime_agent
            if not agent.capabilities.permissions.read:
                raise ValueError('Reading tool documentation requires read permission')
            allowed = guest_tool_names(agent.capabilities.tools, visual_mode=agent.settings.visual_mode,
                orchestration_mode=agent.settings.orchestration_mode, role_id=agent.role_id)
            documents = build_tool_documents(user_input.names, allowed_names=allowed, entries=get_tools_lst())
            return GetToolDocs_output_schema(documents=list(documents))
        except (AttributeError, ValueError) as exc:
            return GetToolDocs_output_schema(is_success=False, message=str(exc))
