from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.tools.Searchtool import _arxiv, _openalex, _web

description = (
    "Search the web, arXiv preprints, or the OpenAlex scholarly corpus. "
    "source=web returns title/URL/snippet for screening (fetch full text separately). "
    "source=arxiv tracks preprints; source=openalex searches the full published literature. "
    "mode (light/normal/weight) applies to arxiv and openalex only and is ignored for web. "
    "If native web search is enabled, do not call this tool with source=web — the model already searches the web."
)


class Search_input_schema(input_schema):
    query: str = Field(description="Search query")
    source: Literal["web", "arxiv", "openalex"] = Field(
        default="web",
        description="Corpus: web (general pages) / arxiv (preprints) / openalex (published literature)",
    )
    max_results: int = Field(default=8, description="Maximum number of results")
    mode: Literal["light", "normal", "weight"] = Field(
        default="normal",
        description="Display mode for arxiv/openalex; ignored when source=web",
    )


class Search_output_schema(output_schema):
    is_success: bool = True
    results: list = Field(default_factory=list, description="Web hits: [{title, url, snippet, source}]")
    content: list = Field(default_factory=list, description="Paper hits when source is arxiv or openalex")
    backend_used: str = ""
    message: str = ""
    error: str = ""


class Search(Tool):
    tool_id: str = "t-4"
    tool_name: str = "search"
    tool_description: str = description
    input_schema: Any = Search_input_schema
    output_schema: Any = Search_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: Search_input_schema, session: Session) -> Search_output_schema:
        source = user_input.source
        if source == "web":
            data = await _web.run(user_input.query, user_input.max_results)
        elif source == "arxiv":
            data = await _arxiv.run(user_input.query, user_input.max_results, user_input.mode)
        else:
            data = await _openalex.run(user_input.query, user_input.max_results, user_input.mode)
        return Search_output_schema(**data)
