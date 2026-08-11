from typing import Any, Dict, List

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

description = (
    "通过 OpenAlex 开放 API 检索全库学术文献（预印本及正式发表论文）。"
    "OpenAlex 覆盖 2 亿+ 文献记录，无需 API key，稳定无反爬。"
    "支持按关键词搜索，返回包含标题、DOI、摘要及 PDF 下载链接的结果。"
)

class OpenAlexSearcher_input_schema(input_schema):
    query: str = Field(description="搜索关键词")
    limit: int = Field(default=10, description="最大返回结果数")
    page: int = Field(default=1, description="页码")
    mode: str = Field(
        default="normal",
        description="展示模式：light（仅标题、DOI、日期）/ normal（加摘要）/ weight（加作者、PDF 链接等详细信息）"
    )

class OpenAlexSearcher_output_schema(output_schema):
    content: list = Field(description="搜索结果列表，每个元素为一个论文信息字典")

class OpenAlexSearcher(Tool):
    tool_id: str = 't-26'
    tool_name: str = 'openalex_searcher'
    tool_description: str = description
    input_schema: Any = OpenAlexSearcher_input_schema
    output_schema: Any = OpenAlexSearcher_output_schema

    def is_read(self) -> bool:
        return True

    def _reconstruct_abstract(self, inverted_index: Dict[str, List[int]]) -> str:
        """OpenAlex 返回的摘要是倒排索引格式，需要手动还原为文本。"""
        if not inverted_index:
            return ""

        # 找到最大的索引位置
        max_index = 0
        for indices in inverted_index.values():
            max_index = max(max_index, max(indices))

        # 创建一个空列表并填入单词
        abstract_list = [""] * (max_index + 1)
        for word, indices in inverted_index.items():
            for index in indices:
                abstract_list[index] = word

        return " ".join(abstract_list)

    async def tool_call(self, user_input: OpenAlexSearcher_input_schema, session: Session) -> OpenAlexSearcher_output_schema:
        import httpx
        # OpenAlex API 地址
        api_url = "https://api.openalex.org/works"

        # 构建查询参数：不加来源过滤，直接检索 OpenAlex 全库
        params = {
            "search": user_input.query,
            "per_page": user_input.limit,
            "page": user_input.page,
        }

        # 建议在 Header 中加入一个邮箱（选填），这会让你的请求进入 OpenAlex 的“礼貌池”，速度更快更稳
        headers = {
            "User-Agent": "Cloudra/1.0 (mailto:951899550@qq.com)"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(api_url, params=params, headers=headers)

                if response.status_code != 200:
                    return OpenAlexSearcher_output_schema(content=[{
                        "error": f"OpenAlex API 异常: {response.status_code}",
                        "detail": response.text[:200]
                    }])

                data = response.json()
                works = data.get("results", [])
                results = []

                for work in works:
                    # 1. 基础信息 (light)
                    item = {
                        "title": work.get("display_name"),
                        "doi": work.get("doi"),
                        "published_date": work.get("publication_date"),
                        "source": "OpenAlex"
                    }

                    # 2. 还原摘要 (normal)
                    if user_input.mode in ["normal", "weight"]:
                        abstract_index = work.get("abstract_inverted_index")
                        if abstract_index:
                            item["abstract"] = self._reconstruct_abstract(abstract_index)
                        else:
                            item["abstract"] = "暂无摘要"

                    # 3. 详细信息 (weight)
                    if user_input.mode == "weight":
                        # 作者处理
                        authorships = work.get("authorships", [])
                        item["authors"] = [a.get("author", {}).get("display_name") for a in authorships]

                        # 概念/分类
                        item["concepts"] = [c.get("display_name") for c in work.get("concepts", [])[:5]]

                        # PDF 下载链接 (OpenAlex 直接提供最佳 OA 链接)
                        best_location = work.get("best_oa_location") or {}
                        item["pdf_url"] = best_location.get("pdf_url") or work.get("doi")

                    results.append(item)

                if not results:
                    return OpenAlexSearcher_output_schema(content=[{"message": "未找到相关论文。"}])

                return OpenAlexSearcher_output_schema(content=results)

        except Exception as e:
            return OpenAlexSearcher_output_schema(content=[{"error": f"OpenAlex 访问失败: {str(e)}"}])

def get_class():
    return OpenAlexSearcher
