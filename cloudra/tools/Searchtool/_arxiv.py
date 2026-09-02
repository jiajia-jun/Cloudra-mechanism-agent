"""arXiv backend for `search` (source=arxiv)."""

from __future__ import annotations

_VALID_SORT_BY = ("Relevance", "SubmittedDate", "LastUpdatedDate")
_VALID_SORT_ORDER = ("Ascending", "Descending")
_VALID_MODES = ("light", "normal", "weight")
_ARXIV_PAGE_CAP = 2000


def _fetch_arxiv(query: str, max_results: int, sort_by: str, sort_order: str) -> list:
    """同步拉取 arXiv；由 run 经 to_thread 卸载，避免冻住事件循环。

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


def _format_paper(result, mode: str) -> dict:
    item = {
        "title": result.title,
        "journal_ref": result.journal_ref,
        "doi": result.doi,
    }
    if mode in ("normal", "weight"):
        item["abstract"] = (result.summary or "").strip("\n")
    if mode == "weight":
        item["authors"] = [author.name for author in result.authors]
        item["categories"] = list(result.categories)
        item["primary_category"] = result.primary_category
        item["pdf_url"] = result.pdf_url
        item["comment"] = result.comment
        item["links"] = [str(link) for link in result.links]
    return item


async def run(
    query: str,
    max_results: int = 8,
    mode: str = "normal",
    sort_by: str = "Relevance",
    sort_order: str = "Descending",
) -> dict:
    import asyncio

    try:
        message = ""
        sort_by = sort_by if sort_by in _VALID_SORT_BY else "Relevance"
        sort_order = sort_order if sort_order in _VALID_SORT_ORDER else "Descending"
        if mode not in _VALID_MODES:
            message = f"Unknown mode '{mode}'; falling back to the default 'normal'."
            mode = "normal"

        raw = await asyncio.to_thread(_fetch_arxiv, query, max_results, sort_by, sort_order)
        results_list = [_format_paper(result, mode) for result in raw]
        if not results_list:
            return {
                "is_success": True,
                "content": [],
                "message": message or "No matching papers found.",
                "error": "",
            }
        return {"is_success": True, "content": results_list, "message": message, "error": ""}
    except Exception as e:
        return {
            "is_success": False,
            "content": [],
            "message": "",
            "error": f"arXiv API temporarily unavailable: {str(e)}",
        }
