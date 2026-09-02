"""paper_searcher：arxiv 4.x 已删除 Search.results()，必须走 Client.results()。

钉板：
- 4.x 形态（Search 无 results）时仍能返回论文
- 空结果给明确 message，而不是静默空列表
- 非法 sort/mode 回落到默认值
"""

from types import SimpleNamespace

import pytest

from cloudra.tools.Searchtool.paper_searcher import (
    PaperSearcher,
    PaperSearcher_input_schema,
)


class FakePaper:
    def __init__(self, **overrides):
        self.title = "Density functional theory of catalysis"
        self.journal_ref = "J. Fake 1, 1 (2024)"
        self.doi = "10.1234/arxiv.2401.00001"
        self.summary = "An abstract.\nSecond line."
        self.authors = [SimpleNamespace(name="Jane Doe")]
        self.categories = ["cond-mat.mtrl-sci"]
        self.primary_category = "cond-mat.mtrl-sci"
        self.pdf_url = "https://arxiv.org/pdf/2401.00001"
        self.comment = "12 pages"
        self.links = ["https://arxiv.org/abs/2401.00001"]
        for key, value in overrides.items():
            setattr(self, key, value)


def _install_client(monkeypatch, papers, *, explode=None):
    """模拟 arxiv 4.x：Client.results() 是唯一取结果入口；Search 没有 results()。"""
    import arxiv

    captured: dict = {}

    class Client:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def results(self, search, offset=0):
            captured["search"] = search
            captured["offset"] = offset
            if explode is not None:
                raise explode
            return iter(papers)

    monkeypatch.setattr(arxiv, "Client", Client)
    # 4.x 已删除 Search.results；显式摘掉，避免测试机若装 2.x 漏检回归
    if hasattr(arxiv.Search, "results"):
        monkeypatch.delattr(arxiv.Search, "results")
    return captured


@pytest.mark.asyncio
async def test_returns_papers_via_client_results(mock_session, monkeypatch):
    captured = _install_client(monkeypatch, [FakePaper()])
    out = await PaperSearcher().tool_call(
        PaperSearcher_input_schema(query="DFT catalysis", max_results=3),
        mock_session,
    )
    assert out.is_success is True
    assert out.error == ""
    assert len(out.content) == 1
    item = out.content[0]
    assert item["title"] == "Density functional theory of catalysis"
    assert item["doi"] == "10.1234/arxiv.2401.00001"
    assert item["abstract"] == "An abstract.\nSecond line."
    assert captured["search"].query == "DFT catalysis"
    assert captured["search"].max_results == 3


@pytest.mark.asyncio
async def test_empty_results_are_success_with_message(mock_session, monkeypatch):
    _install_client(monkeypatch, [])
    out = await PaperSearcher().tool_call(
        PaperSearcher_input_schema(query="zzzz-no-such-paper"),
        mock_session,
    )
    assert out.is_success is True
    assert out.content == []
    assert "no matching" in out.message.lower()


@pytest.mark.asyncio
async def test_weight_mode_includes_authors_and_pdf(mock_session, monkeypatch):
    _install_client(monkeypatch, [FakePaper()])
    out = await PaperSearcher().tool_call(
        PaperSearcher_input_schema(query="DFT", mode="weight"),
        mock_session,
    )
    item = out.content[0]
    assert item["authors"] == ["Jane Doe"]
    assert item["pdf_url"] == "https://arxiv.org/pdf/2401.00001"
    assert item["categories"] == ["cond-mat.mtrl-sci"]


@pytest.mark.asyncio
async def test_invalid_sort_and_mode_fall_back(mock_session, monkeypatch):
    captured = _install_client(monkeypatch, [FakePaper()])
    out = await PaperSearcher().tool_call(
        PaperSearcher_input_schema(
            query="DFT",
            sort_by="NotASort",
            sort_order="Sideways",
            mode="verbose",
        ),
        mock_session,
    )
    assert out.is_success is True
    assert "normal" in out.message
    search = captured["search"]
    import arxiv

    assert search.sort_by == arxiv.SortCriterion.Relevance
    assert search.sort_order == arxiv.SortOrder.Descending


@pytest.mark.asyncio
async def test_client_failure_is_reported(mock_session, monkeypatch):
    _install_client(monkeypatch, [], explode=RuntimeError("connection reset"))
    out = await PaperSearcher().tool_call(
        PaperSearcher_input_schema(query="DFT"),
        mock_session,
    )
    assert out.is_success is False
    assert out.content == []
    assert "connection reset" in out.error
    assert "results" not in out.error
