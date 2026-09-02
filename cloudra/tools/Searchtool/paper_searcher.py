from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

description = (
    "Search arXiv preprints via the arXiv API; returns structured title, DOI, abstract, etc. "
    "Use for: tracking new preprints or monitoring a topic by submit/update time. "
    "Do not use for: full-corpus search of published literature (use openalex_searcher), non-academic web pages (use web_search), "
    "or extracting content from a known PDF (download with web_fetcher then pdf2md)."
)

_VALID_SORT_BY = ("Relevance", "SubmittedDate", "LastUpdatedDate")
_VALID_SORT_ORDER = ("Ascending", "Descending")
_VALID_MODES = ("light", "normal", "weight")
_ARXIV_PAGE_CAP = 2000


def _fetch_arxiv(query: str, max_results: int, sort_by: str, sort_order: str) -> list:
    """同步拉取 arXiv；由 tool_call 经 to_thread 卸载，避免冻住事件循环。

    arxiv 2.0+ 用 Client.results(Search)；4.0 删除了 Search.results()。
    """
    import arxiv

    page_size = max(1, min(int(max_results), _ARXIV_PAGE_CAP))
    client = arxiv.Client(page_size=page_size)
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=getattr(arxiv.SortCriterion, sort_by),
        sort_order=getattr(arxiv.SortOrder, sort_order),
    )
    return list(client.results(search))


class PaperSearcher_input_schema(input_schema):
    query: str = Field(description="Search keywords")
    max_results: int = Field(default=10, description="Maximum number of results")
    sort_by: str = Field(
        default="Relevance",
        description="Sort by: Relevance / SubmittedDate / LastUpdatedDate"
    )
    sort_order: str = Field(
        default="Descending",
        description="Sort order: Ascending / Descending"
    )
    mode: str = Field(
        default="normal",
        description="Display mode: light (title, journal, DOI only) / normal (plus abstract) / weight (plus authors, categories, PDF links, and all other fields)"
    )


class PaperSearcher_output_schema(output_schema):
    is_success: bool = Field(default=True, description="Whether the search succeeded")
    content: list = Field(default_factory=list, description="Search results; each item is a paper-info dict")
    message: str = Field(default="", description="Status note (e.g. no results, or an invalid parameter was reset to its default)")
    error: str = Field(default="", description="Error message on failure")


class PaperSearcher(Tool):
    tool_id: str = 't-4'
    tool_name: str = 'paper_searcher'
    tool_description: str = description
    input_schema: Any = PaperSearcher_input_schema
    output_schema: Any = PaperSearcher_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: PaperSearcher_input_schema, session: Session) -> PaperSearcher_output_schema:
        import asyncio

        try:
            message = ""
            sort_by = user_input.sort_by if user_input.sort_by in _VALID_SORT_BY else "Relevance"
            sort_order = user_input.sort_order if user_input.sort_order in _VALID_SORT_ORDER else "Descending"
            mode = user_input.mode
            if mode not in _VALID_MODES:
                message = f"Unknown mode '{user_input.mode}'; falling back to the default 'normal'."
                mode = "normal"

            raw = await asyncio.to_thread(
                _fetch_arxiv, user_input.query, user_input.max_results, sort_by, sort_order
            )

            results_list = []
            for result in raw:
                item = {
                    'title': result.title,
                    'journal_ref': result.journal_ref,
                    'doi': result.doi
                }

                if mode in ['normal', 'weight']:
                    item['abstract'] = (result.summary or "").strip('\n')

                if mode == 'weight':
                    item['authors'] = [author.name for author in result.authors]
                    item['categories'] = list(result.categories)
                    item['primary_category'] = result.primary_category
                    item['pdf_url'] = result.pdf_url
                    item['comment'] = result.comment
                    item['links'] = [str(link) for link in result.links]

                results_list.append(item)

            if not results_list:
                return PaperSearcher_output_schema(
                    content=[],
                    message=message or "No matching papers found.",
                )
            return PaperSearcher_output_schema(content=results_list, message=message)
        except Exception as e:
            return PaperSearcher_output_schema(is_success=False, error=f'arXiv API temporarily unavailable: {str(e)}')


def get_class():
    return PaperSearcher
