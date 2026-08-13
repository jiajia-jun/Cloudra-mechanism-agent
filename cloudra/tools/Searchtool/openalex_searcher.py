from typing import Any, Dict, List

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.infra.config import get_config

description = (
    "Search the full OpenAlex scholarly corpus (preprints and published papers) via the open API. "
    "OpenAlex covers 200M+ records. An API key is optional: set openalex_api_key / "
    "OPENALEX_API_KEY for a higher daily budget; without a key the request is anonymous. "
    "Optional openalex_mailto / OPENALEX_MAILTO puts your email in the User-Agent polite pool. "
    "Keyword search returns title, DOI, abstract, and PDF download links."
)

class OpenAlexSearcher_input_schema(input_schema):
    query: str = Field(description="Search keywords")
    limit: int = Field(default=10, description="Maximum number of results")
    page: int = Field(default=1, description="Page number")
    mode: str = Field(
        default="normal",
        description="Display mode: light (title, DOI, date only) / normal (plus abstract) / weight (plus authors, PDF links, and other details)"
    )

class OpenAlexSearcher_output_schema(output_schema):
    content: list = Field(description="Search results; each item is a paper-info dict")

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
        api_key = (get_config().openalex_api_key or "").strip()
        if api_key:
            params["api_key"] = api_key

        mailto = (get_config().openalex_mailto or "").strip()
        if mailto.lower().startswith("mailto:"):
            mailto = mailto[7:].strip()
        user_agent = f"Cloudra/1.0 (mailto:{mailto})" if mailto else "Cloudra/1.0"
        headers = {"User-Agent": user_agent}

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
