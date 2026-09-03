"""OpenAlex backend for `search` (source=openalex)."""

from __future__ import annotations

from typing import Dict, List

from cloudra.infra.config import get_config


def _reconstruct_abstract(inverted_index: Dict[str, List[int]]) -> str:
    """OpenAlex 返回的摘要是倒排索引格式，需要手动还原为文本。"""
    if not inverted_index:
        return ""

    max_index = 0
    for indices in inverted_index.values():
        max_index = max(max_index, max(indices))

    abstract_list = [""] * (max_index + 1)
    for word, indices in inverted_index.items():
        for index in indices:
            abstract_list[index] = word

    return " ".join(abstract_list)


async def run(query: str, max_results: int = 8, mode: str = "normal") -> dict:
    import httpx

    api_url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per_page": max_results,
        "page": 1,
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
                return {
                    "is_success": False,
                    "content": [],
                    "message": "",
                    "error": (
                        f"OpenAlex API error: {response.status_code}; "
                        f"detail: {response.text[:200]}"
                    ),
                }

            data = response.json()
            works = data.get("results", [])
            results = []

            for work in works:
                item = {
                    "title": work.get("display_name"),
                    "doi": work.get("doi"),
                    "published_date": work.get("publication_date"),
                    "source": "OpenAlex",
                }

                if mode in ("normal", "weight"):
                    abstract_index = work.get("abstract_inverted_index")
                    if abstract_index:
                        item["abstract"] = _reconstruct_abstract(abstract_index)
                    else:
                        item["abstract"] = "No abstract available"

                if mode == "weight":
                    authorships = work.get("authorships", [])
                    item["authors"] = [a.get("author", {}).get("display_name") for a in authorships]
                    item["concepts"] = [c.get("display_name") for c in work.get("concepts", [])[:5]]
                    best_location = work.get("best_oa_location") or {}
                    item["pdf_url"] = best_location.get("pdf_url") or work.get("doi")

                results.append(item)

            if not results:
                return {
                    "is_success": True,
                    "content": [],
                    "message": "No matching papers found.",
                    "error": "",
                }

            return {"is_success": True, "content": results, "message": "", "error": ""}

    except Exception as e:
        return {
            "is_success": False,
            "content": [],
            "message": "",
            "error": f"OpenAlex request failed: {str(e)}",
        }
