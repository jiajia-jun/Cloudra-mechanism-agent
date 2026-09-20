"""本地 API bearer 认证与 Host 校验（DNS rebinding 防护）。

红队背景：未设 CLOUDRA_API_TOKEN 时 authorize 全放行 + 无 Host 校验，
恶意网页 JS 可读写本地 API。本文件钉死：
- env 设具体 token：无头/错头 401，对头 200，?token= query 兜底等价；
- env=off：全放行（conftest 已默认 off，各用例内显式覆盖）；
- env 未设：data_dir/.api_token 自动生成（0600）且复用；
- 有 token 时只验 token（头或 ?token=，不限方法、不验 Host）；
- token=off 时 Host 头不在回环白名单 → 400。

在旧实现上全红：旧 authorize 未设 env 直接放行、无 query 兜底、无 Host 校验、
无 token 文件概念。
"""

from __future__ import annotations

import stat

import pytest
from fastapi.testclient import TestClient

from cloudra.infra.config import _reset_for_tests
from cloudra.persistence import paths
from cloudra.services.api_token import resolve_api_token
from cloudra.services.api_v2 import create_v2_app

_PROBE = "/api/v2/projects"


@pytest.fixture
def _env_token(monkeypatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "test-secret-token")
    yield
    _reset_for_tests()


@pytest.fixture
def _file_token(monkeypatch):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    yield
    _reset_for_tests()


# ---------------------------------------------------------------- env token 模式


def test_missing_and_wrong_token_rejected(_env_token):
    client = TestClient(create_v2_app())
    assert client.get(_PROBE).status_code == 401
    assert client.get(_PROBE, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_correct_token_accepted(_env_token):
    client = TestClient(create_v2_app())
    resp = client.get(_PROBE, headers={"Authorization": "Bearer test-secret-token"})
    assert resp.status_code == 200


def test_query_token_fallback_accepted(_env_token):
    client = TestClient(create_v2_app())
    assert client.get(f"{_PROBE}?token=test-secret-token").status_code == 200
    assert client.get(f"{_PROBE}?token=wrong").status_code == 401


def test_query_token_accepted_on_mutating_methods(_env_token):
    """有 token 就过，不限方法。"""
    client = TestClient(create_v2_app())
    created = client.post(f"{_PROBE}?token=test-secret-token", json={"name": "from-query"})
    assert created.status_code == 201


def test_referrer_policy_header(_env_token):
    client = TestClient(create_v2_app())
    resp = client.get(_PROBE, headers={"Authorization": "Bearer test-secret-token"})
    assert resp.headers.get("referrer-policy") == "no-referrer"


# ---------------------------------------------------------------- Host 校验


def test_valid_token_ignores_host(_env_token):
    client = TestClient(create_v2_app())
    resp = client.get(
        _PROBE,
        headers={"Authorization": "Bearer test-secret-token", "Host": "evil.attacker.com"},
    )
    assert resp.status_code == 200


def test_loopback_hosts_accepted(_env_token):
    client = TestClient(create_v2_app())
    for host in ("127.0.0.1:8000", "localhost", "[::1]:8000", "testserver"):
        resp = client.get(
            _PROBE,
            headers={"Authorization": "Bearer test-secret-token", "Host": host},
        )
        assert resp.status_code == 200, host


def test_token_passes_on_any_bind_host(monkeypatch, _env_token):
    monkeypatch.setenv("CLOUDRA_API_BIND_HOST", "192.168.1.5")
    client = TestClient(create_v2_app())

    resp = client.get(
        _PROBE,
        headers={"Authorization": "Bearer test-secret-token", "Host": "192.168.1.5:8000"},
    )
    assert resp.status_code == 200
    assert client.get(_PROBE, headers={"Authorization": "Bearer test-secret-token"}).status_code == 200
    forged = client.get(
        _PROBE,
        headers={"Authorization": "Bearer test-secret-token", "Host": "proxy.example"},
    )
    assert forged.status_code == 200


def test_wildcard_bind_host_disables_host_check(monkeypatch, _env_token):
    """通配绑定（--host 0.0.0.0）下客户端名字无法枚举：Host 校验整体关闭，
    但认证闸门不变——token 才是访问控制。"""
    monkeypatch.setenv("CLOUDRA_API_BIND_HOST", "0.0.0.0")
    client = TestClient(create_v2_app())

    resp = client.get(
        _PROBE,
        headers={"Authorization": "Bearer test-secret-token", "Host": "10.0.0.7:8000"},
    )
    assert resp.status_code == 200
    assert client.get(_PROBE, headers={"Host": "10.0.0.7:8000"}).status_code == 401
    assert client.get(_PROBE, headers={"Host": "evil.attacker.com"}).status_code == 401


# ---------------------------------------------------------------- off 模式


def test_off_disables_auth(monkeypatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "off")
    try:
        client = TestClient(create_v2_app())
        assert client.get(_PROBE).status_code == 200
    finally:
        _reset_for_tests()


def test_off_forged_host_rejected(monkeypatch):
    """token=off 没有秘密可验，仍用 Host 白名单挡 DNS rebinding。"""
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "off")
    try:
        client = TestClient(create_v2_app())
        resp = client.get(_PROBE, headers={"Host": "evil.attacker.com"})
        assert resp.status_code == 400
    finally:
        _reset_for_tests()


def test_off_refuses_non_loopback_bind(monkeypatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "off")
    monkeypatch.setenv("CLOUDRA_API_BIND_HOST", "0.0.0.0")
    try:
        with pytest.raises(RuntimeError, match="loopback"):
            create_v2_app()
    finally:
        _reset_for_tests()


def test_off_rejects_non_loopback_client_when_bind_host_unset(monkeypatch):
    """工厂路径不设 CLOUDRA_API_BIND_HOST 时，token=off 只能给回环客户端。

    uvicorn --factory --host 0.0.0.0 不会写 BIND_HOST：Host: 127.0.0.1 能骗过
    白名单，但 ASGI client 仍是局域网地址，必须 401。
    """
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "off")
    monkeypatch.delenv("CLOUDRA_API_BIND_HOST", raising=False)
    try:
        app = create_v2_app()
        loopback = TestClient(app)
        assert loopback.get(_PROBE).status_code == 200
        lan = TestClient(app, client=("10.1.2.3", 50000))
        forged = lan.get(_PROBE, headers={"Host": "127.0.0.1:8000"})
        assert forged.status_code == 401
    finally:
        _reset_for_tests()


# ---------------------------------------------------------------- token 文件模式


def test_token_file_generated_once_and_reused(_file_token, tmp_path):
    token_file = paths.api_token_path()
    assert not token_file.exists()

    first = resolve_api_token()
    assert first
    assert token_file.is_file()
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600

    # 服务端与 CLI 调用方再次解析必须拿到同一个 token
    assert resolve_api_token() == first
    assert create_v2_app() is not None  # app 构建路径同样经 resolve_api_token

    client = TestClient(create_v2_app())
    assert client.get(_PROBE).status_code == 401
    assert client.get(_PROBE, headers={"Authorization": f"Bearer {first}"}).status_code == 200


def test_token_file_repairs_world_readable_mode(_file_token):
    token_file = paths.api_token_path()
    first = resolve_api_token()
    token_file.chmod(0o644)
    assert resolve_api_token() == first
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


def test_empty_token_file_treated_as_missing(_file_token):
    token_file = paths.api_token_path()
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text("  \n", encoding="utf-8")

    token = resolve_api_token()
    assert token
    assert token_file.read_text(encoding="utf-8").strip() == token


def test_render_smiles_requires_token(_env_token):
    client = TestClient(create_v2_app())
    path = "/api/v2/chem/render-smiles?smiles=C"
    assert client.get(path).status_code == 401
    resp = client.get(path, headers={"Authorization": "Bearer test-secret-token"})
    assert resp.status_code == 200
    assert "svg" in resp.headers.get("content-type", "")
