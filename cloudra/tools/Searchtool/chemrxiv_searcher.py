from typing import Any, Dict, List

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "通过 OpenAlex 开放 API 搜索 ChemRxiv 及其他学术平台的论文。"
    "该工具能够绕过复杂的反爬验证，稳定获取化学领域最新的预印本及正式发表论文。"
    "支持按关键词搜索，返回包含标题、DOI、摘要及 PDF 下载链接的结果。"
)

class ChemRxivSearcher_input_schema(input_schema):
    query: str = Field(description="搜索关键词")
    limit: int = Field(default=10, description="最大返回结果数")
    page: int = Field(default=1, description="页码")
    mode: str = Field(
        default="normal",
        description="展示模式：light（仅标题、DOI、日期）/ normal（加摘要）/ weight（加作者、PDF 链接等详细信息）"
    )

class ChemRxivSearcher_output_schema(output_schema):
    content: list = Field(description="搜索结果列表，每个元素为一个论文信息字典")

class ChemRxivSearcher(Tool):
    tool_id: str = 't-26'
    tool_name: str = 'chemrxiv_searcher'
    tool_description: str = description
    input_schema: Any = ChemRxivSearcher_input_schema
    output_schema: Any = ChemRxivSearcher_output_schema

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

    async def tool_call(self, user_input: ChemRxivSearcher_input_schema, session: Session) -> ChemRxivSearcher_output_schema:
        import httpx
        # OpenAlex API 地址
        api_url = "https://api.openalex.org/works"

        # 构建查询参数
        # 过滤条件：我们专门指定来源为 ChemRxiv (OpenAlex ID: S4306400032)
        # 如果你想搜索全网，可以去掉 filter 参数
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
                    return ChemRxivSearcher_output_schema(content=[{
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
                        "source": "ChemRxiv (via OpenAlex)"
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
                    return ChemRxivSearcher_output_schema(content=[{"message": "未找到相关论文。"}])

                return ChemRxivSearcher_output_schema(content=results)

        except Exception as e:
            return ChemRxivSearcher_output_schema(content=[{"error": f"OpenAlex 访问失败: {str(e)}"}])

def get_class():
    return ChemRxivSearcher
