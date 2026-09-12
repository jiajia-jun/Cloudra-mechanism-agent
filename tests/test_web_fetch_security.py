"""web_fetch SSRF / 下载路径 / 方法审批 安全闸门。

网络全部打桩：DNS 走假 getaddrinfo，HTTP 走假 httpx.AsyncClient，
测试不需要真实网络。
"""

from types import SimpleNamespace

import pytest

from cloudra.tools.Browsertool.web_fetch import WebFetcher, WebFetcher_input_schema

_PUBLIC_IP = "93.184.216.34"  # example.com 风格的公网地址（打桩返回值）


def _fake_dns(monkeypatch, mapping):
    """hostname → IP 的打桩解析表；未列出的主机按公网地址放行。"""

    def fake_getaddrinfo(host, port, *args, **kwargs):
        ip = mapping.get(host, _PUBLIC_IP)
        return [(2, 1, 6, "", (ip, port or 80))]

    monkeypatch.setattr("cloudra.tools.Browsertool.web_fetch.socket.getaddrinfo", fake_getaddrinfo)


class _FakeResponse:
    def __init__(self, status_code=200, headers=None, content=b"hello", text="hello"):
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content
        self.text = text
        self.is_redirect = status_code in (301, 302, 303, 307, 308) and "location" in self.headers

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """按 URL 路由到预置响应；记录请求序列。"""

    responses = {}
    requests = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def request(self, method, url, headers=None, **kwargs):
        self.requests.append((method, url))
        return self.responses[url]


@pytest.fixture
def fake_httpx(monkeypatch):
    httpx = pytest.importorskip("httpx")
    _FakeClient.responses = {}
    _FakeClient.requests = []
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    return _FakeClient


def _tool(workdir) -> WebFetcher:
    return WebFetcher(subagent=SimpleNamespace(working_directory=str(workdir)))


@pytest.mark.asyncio
async def test_literal_internal_ips_refused(tmp_path):
    for url in (
        "http://127.0.0.1:8080/admin",
        "http://localhost/secret",
        "http://192.168.1.1/",
        "http://10.0.0.5/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
    ):
        result = await _tool(tmp_path).tool_call(
            WebFetcher_input_schema(url=url), session=SimpleNamespace(id="s1"),
        )
        assert result.is_success is False, url
        assert "Refused" in result.error, url


@pytest.mark.asyncio
async def test_dns_pointing_to_internal_refused(tmp_path, monkeypatch):
    """公网外观的 hostname 解析到内网 IP 一样拒绝（防 DNS 重绑定）。"""
    _fake_dns(monkeypatch, {"internal.example": "10.0.0.5"})

    result = await _tool(tmp_path).tool_call(
        WebFetcher_input_schema(url="http://internal.example/data"),
        session=SimpleNamespace(id="s1"),
    )
    assert result.is_success is False
    assert "non-public" in result.error


@pytest.mark.asyncio
async def test_redirect_to_internal_refused(tmp_path, monkeypatch, fake_httpx):
    """每一跳重定向重新过主机闸门：公网入口 302 到内网被拒。"""
    _fake_dns(monkeypatch, {})
    fake_httpx.responses["https://example.com/start"] = _FakeResponse(
        status_code=302, headers={"location": "http://169.254.169.254/latest"}
    )

    result = await _tool(tmp_path).tool_call(
        WebFetcher_input_schema(url="https://example.com/start"),
        session=SimpleNamespace(id="s1"),
    )
    assert result.is_success is False
    assert "redirect" in result.error.lower()
    # 只发出了第一跳请求
    assert fake_httpx.requests == [("GET", "https://example.com/start")]


@pytest.mark.asyncio
async def test_redirect_chain_within_public_hosts_followed(tmp_path, monkeypatch, fake_httpx):
    _fake_dns(monkeypatch, {})
    fake_httpx.responses["https://example.com/a"] = _FakeResponse(
        status_code=302, headers={"location": "https://example.com/b"}
    )
    fake_httpx.responses["https://example.com/b"] = _FakeResponse(
        status_code=200, headers={"content-type": "text/plain"}, content=b"done", text="done"
    )

    result = await _tool(tmp_path).tool_call(
        WebFetcher_input_schema(url="https://example.com/a", extract_text=False),
        session=SimpleNamespace(id="s1"),
    )
    assert result.is_success is True, result.error
    assert result.content == "done"
    assert [u for _m, u in fake_httpx.requests] == [
        "https://example.com/a", "https://example.com/b",
    ]


@pytest.mark.asyncio
async def test_download_path_outside_workdir_refused(tmp_path, monkeypatch, fake_httpx):
    _fake_dns(monkeypatch, {})
    workdir = tmp_path / "ws"
    workdir.mkdir()
    outside = tmp_path / "loot.bin"

    result = await _tool(workdir).tool_call(
        WebFetcher_input_schema(
            url="https://example.com/x", download_path=str(outside),
        ),
        session=SimpleNamespace(id="s1"),
    )
    assert result.is_success is False
    assert "download_path" in result.error
    assert not outside.exists()
    assert fake_httpx.requests == []  # 拒绝发生在发请求之前


@pytest.mark.asyncio
async def test_download_path_inside_workdir_written(tmp_path, monkeypatch, fake_httpx):
    _fake_dns(monkeypatch, {})
    workdir = tmp_path / "ws"
    workdir.mkdir()
    fake_httpx.responses["https://example.com/x"] = _FakeResponse(content=b"\x00\x01payload")

    result = await _tool(workdir).tool_call(
        WebFetcher_input_schema(
            url="https://example.com/x", download_path="dl/payload.bin",
        ),
        session=SimpleNamespace(id="s1"),
    )
    assert result.is_success is True, result.error
    assert (workdir / "dl" / "payload.bin").read_bytes() == b"\x00\x01payload"
    assert result.downloaded_path == str((workdir / "dl" / "payload.bin").resolve())


@pytest.mark.asyncio
async def test_non_get_without_approval_handler_raises(tmp_path, monkeypatch, fake_httpx):
    """无审批 handler 时走现有工具的失败语义：ensure_safety 抛错（runtime_v2 必装 handler）。"""
    _fake_dns(monkeypatch, {})

    with pytest.raises(RuntimeError, match="no approval handler"):
        await _tool(tmp_path).tool_call(
            WebFetcher_input_schema(url="https://example.com/submit", method="POST"),
            session=SimpleNamespace(id="s1"),
        )
    assert fake_httpx.requests == []


@pytest.mark.asyncio
async def test_non_get_approved_proceeds_and_denied_blocks(tmp_path, monkeypatch, fake_httpx):
    _fake_dns(monkeypatch, {})
    fake_httpx.responses["https://example.com/submit"] = _FakeResponse(
        headers={"content-type": "text/plain"}, text="ok",
    )

    async def _approve(self, session, **_kwargs):
        return True, ""

    monkeypatch.setattr(WebFetcher, "ensure_safety", _approve)
    result = await _tool(tmp_path).tool_call(
        WebFetcher_input_schema(url="https://example.com/submit", method="POST"),
        session=SimpleNamespace(id="s1"),
    )
    assert result.is_success is True, result.error
    assert fake_httpx.requests == [("POST", "https://example.com/submit")]

    async def _deny(self, session, **_kwargs):
        return False, "no posting"

    monkeypatch.setattr(WebFetcher, "ensure_safety", _deny)
    fake_httpx.requests = []
    result = await _tool(tmp_path).tool_call(
        WebFetcher_input_schema(url="https://example.com/submit", method="POST"),
        session=SimpleNamespace(id="s1"),
    )
    assert result.is_success is False
    assert "[Safety block]" in result.error
    assert "no posting" in result.error
    assert fake_httpx.requests == []
