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
        import arxiv
        try:
            message = ""
            if user_input.sort_by not in ['Relevance', 'SubmittedDate', 'LastUpdatedDate']:
                user_input.sort_by = 'Relevance'
            if user_input.sort_order not in ['Ascending', 'Descending']:
                user_input.sort_order = 'Descending'
            if user_input.mode not in ['light', 'normal', 'weight']:
                message = f"Unknown mode '{user_input.mode}'; falling back to the default 'normal'."
                user_input.mode = 'normal'

            sort_by = getattr(arxiv.SortCriterion, user_input.sort_by)
            sort_order = getattr(arxiv.SortOrder, user_input.sort_order)

            arxiv_search = arxiv.Search(
                query=user_input.query,
                max_results=user_input.max_results,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            results_list = []
            # 核心优化：只迭代一次 search.results()，获取所有数据
            for result in arxiv_search.results():
                item = {
                    'title': result.title,
                    'journal_ref': result.journal_ref,
                    'doi': result.doi
                }

                if user_input.mode in ['normal', 'weight']:
                    item['abstract'] = result.summary.strip('\n')

                if user_input.mode == 'weight':
                    item['authors'] = [author.name for author in result.authors]
                    item['categories'] = list(result.categories)
                    item['primary_category'] = result.primary_category
                    item['pdf_url'] = result.pdf_url
                    item['comment'] = result.comment
                    item['links'] = [str(link) for link in result.links]

                results_list.append(item)

            return PaperSearcher_output_schema(content=results_list, message=message)
        except Exception as e:
            # 捕获所有 arxiv 库抛出的网络异常
            return PaperSearcher_output_schema(is_success=False, error=f'arXiv API temporarily unavailable: {str(e)}')


def get_class():
    return PaperSearcher
