from pydantic import Field
from typing import Any

from tools_class import Tool, input_schema, output_schema
from session_class import Session
import arxiv


description = (
    "通过 arXiv API 搜索学术论文，返回结构化结果列表。"
    "支持按相关度、提交时间、更新时间排序，并提供轻量/标准/详细三种展示模式。"
)


class PaperSearcher_input_schema(input_schema):
    query: str = Field(description="搜索关键词")
    max_results: int = Field(default=10, description="最大返回结果数")
    sort_by: str = Field(
        default="Relevance",
        description="排序方式：Relevance（相关度）/ SubmittedDate（提交时间）/ LastUpdatedDate（更新时间）"
    )
    sort_order: str = Field(
        default="Descending",
        description="排序顺序：Ascending（升序）/ Descending（降序）"
    )
    mode: str = Field(
        default="normal",
        description="展示模式：light（仅标题、期刊、DOI）/ normal（加摘要）/ weight（加作者、分类、PDF 链接等全部信息）"
    )


class PaperSearcher_output_schema(output_schema):
    content: list = Field(description="搜索结果列表，每个元素为一个论文信息字典")


class PaperSearcher(Tool):
    tool_id: str = 't-4'
    tool_name: str = 'paper_searcher'
    tool_description: str = description
    input_schema: Any = PaperSearcher_input_schema
    output_schema: Any = PaperSearcher_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: PaperSearcher_input_schema, session: Session) -> PaperSearcher_output_schema:
        try:
            if user_input.sort_by not in ['Relevance', 'SubmittedDate', 'LastUpdatedDate']:
                user_input.sort_by = 'Relevance'
            if user_input.sort_order not in ['Ascending', 'Descending']:
                user_input.sort_order = 'Descending'
            if user_input.mode not in ['light', 'normal', 'weight']:
                user_input.mode = 'light'

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

            return PaperSearcher_output_schema(content=results_list)
        except Exception as e:
            # 捕获所有 arxiv 库抛出的网络异常
            return PaperSearcher_output_schema(content=[{'error': f'arXiv API 暂时不可用: {str(e)}'}])


def get_class():
    return PaperSearcher
