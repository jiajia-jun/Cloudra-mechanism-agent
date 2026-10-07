"""Codex OAuth protocol and token-store regressions, without live credentials."""

from __future__ import annotations

import base64
import importlib
import json
import multiprocessing
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest


def _auth():
    try:
        return importlib.import_module("cloudra.infra.codex_auth")
    except ModuleNotFoundError:
        pytest.fail("Cloudra has no Codex OAuth implementation")


def _jwt(exp: int, account_id: str = "workspace-1") -> str:
    claims = {
        "exp": exp,
        "https://api.openai.com/auth": {
            "chatgpt_account_id": account_id,
            "chatgpt_data_residency": "eu",
        },
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{payload}.test-signature"


def _use_http(monkeypatch, auth, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(auth, "_http_client", lambda: httpx.Client(transport=transport, timeout=20.0))


def _write_credentials(auth, *, access_token, refresh_token="refresh-1", expires_at=None):
    from cloudra.persistence.paths import codex_auth_path

    path = codex_auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
    }), encoding="utf-8")
    return path


def _device_code(request):
    assert request.method == "POST"
    assert str(request.url) == "https://auth.openai.com/api/accounts/deviceauth/usercode"
    assert json.loads(request.content) == {"client_id": "app_EMoamEEZ73f0CkXaXp7hrann"}
    return httpx.Response(200, json={"device_auth_id": "secret-device-id", "user_code": "ABCD-EFGH", "interval": "5"})


def _logout_in_separate_process(data_dir: str) -> None:
    from cloudra.infra.codex_auth import logout_codex
    from cloudra.infra.config import get_config

    get_config().data_dir = Path(data_dir)
    logout_codex()


def test_device_login_returns_only_public_challenge(monkeypatch):
    auth = _auth()
    _use_http(monkeypatch, auth, _device_code)
    challenge = auth.start_device_login()
    assert set(challenge) == {"login_id", "user_code", "verification_uri", "interval", "expires_at"}
    assert challenge["user_code"] == "ABCD-EFGH"
    assert challenge["verification_uri"] == "https://auth.openai.com/codex/device"
    assert challenge["interval"] == 5
    assert challenge["login_id"] != "secret-device-id"
    assert time.time() < challenge["expires_at"] <= time.time() + 901
    assert auth.codex_auth_status() == {"authenticated": False, "expires_at": None, "account_id": None}


@pytest.mark.parametrize("pending_status", [403, 404])
def test_device_pending_does_not_persist_tokens(monkeypatch, pending_status):
    auth = _auth()
    _use_http(monkeypatch, auth, _device_code)
    challenge = auth.start_device_login()

    def pending(request):
        assert str(request.url) == "https://auth.openai.com/api/accounts/deviceauth/token"
        assert json.loads(request.content) == {"device_auth_id": "secret-device-id", "user_code": "ABCD-EFGH"}
        return httpx.Response(pending_status)

    _use_http(monkeypatch, auth, pending)
    assert auth.poll_device_login(challenge["login_id"]) == {"status": "pending"}
    assert auth.codex_auth_status()["authenticated"] is False


def test_authorized_device_exchange_writes_private_independent_tokens(monkeypatch, tmp_path):
    auth = _auth()
    _use_http(monkeypatch, auth, _device_code)
    challenge = auth.start_device_login()
    token = _jwt(int(time.time()) + 3600)
    codex_dir = tmp_path / "unrelated-codex"
    codex_dir.mkdir()
    external = codex_dir / "auth.json"
    external.write_text("unrelated login", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_dir))

    def authorize(request):
        if request.url.path == "/api/accounts/deviceauth/token":
            return httpx.Response(200, json={"authorization_code": "exchange-code", "code_verifier": "verifier"})
        assert str(request.url) == "https://auth.openai.com/oauth/token"
        from urllib.parse import parse_qs
        assert parse_qs(request.content.decode()) == {
            "grant_type": ["authorization_code"], "code": ["exchange-code"], "code_verifier": ["verifier"],
            "redirect_uri": ["https://auth.openai.com/deviceauth/callback"],
            "client_id": ["app_EMoamEEZ73f0CkXaXp7hrann"],
        }
        return httpx.Response(200, json={"access_token": token, "refresh_token": "new-refresh", "expires_in": 3600})

    _use_http(monkeypatch, auth, authorize)
    assert auth.poll_device_login(challenge["login_id"]) == {"status": "authorized"}
    from cloudra.persistence.paths import codex_auth_path
    assert os.stat(codex_auth_path()).st_mode & 0o777 == 0o600
    assert json.loads(codex_auth_path().read_text())["refresh_token"] == "new-refresh"
    assert external.read_text() == "unrelated login"
    credentials = auth.resolve_codex_credentials()
    assert credentials["access_token"] == token
    assert credentials["account_id"] == "workspace-1"
    assert credentials["residency"] == "eu"
    with pytest.raises(auth.CodexAuthError):
        auth.poll_device_login(challenge["login_id"])


def test_device_poll_honors_interval_and_expiration(monkeypatch):
    auth = _auth()
    now = [1_900_000_000.0]
    monkeypatch.setattr(auth.time, "time", lambda: now[0])
    _use_http(monkeypatch, auth, _device_code)
    challenge = auth.start_device_login()
    calls = []

    def pending(request):
        calls.append(request)
        return httpx.Response(403)

    _use_http(monkeypatch, auth, pending)
    assert auth.poll_device_login(challenge["login_id"]) == {"status": "pending"}
    assert auth.poll_device_login(challenge["login_id"]) == {"status": "pending"}
    assert len(calls) == 1
    now[0] = challenge["expires_at"] + 1
    with pytest.raises(auth.CodexAuthError) as error:
        auth.poll_device_login(challenge["login_id"])
    assert error.value.code == "login_expired"
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [[], {"user_code": "code"}, {"device_auth_id": "id", "user_code": "code", "interval": True}])
def test_invalid_device_challenge_fails_loud_without_secrets(monkeypatch, payload):
    auth = _auth()
    _use_http(monkeypatch, auth, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(auth.CodexAuthError) as error:
        auth.start_device_login()
    assert error.value.code == "invalid_response"
    assert "access_token" not in str(error.value)


def test_status_is_read_only_even_when_access_token_expired(monkeypatch):
    auth = _auth()
    path = _write_credentials(auth, access_token=_jwt(1), expires_at=1)
    before = path.read_bytes()
    _use_http(monkeypatch, auth, lambda request: pytest.fail("status must not call auth service"))
    from cloudra.persistence.paths import codex_auth_lock_path
    assert not codex_auth_lock_path().exists()
    assert auth.codex_auth_status() == {"authenticated": True, "expires_at": 1.0, "account_id": "workspace-1"}
    assert path.read_bytes() == before
    assert not codex_auth_lock_path().exists()


def test_status_rejects_corrupt_credentials_without_overwriting():
    auth = _auth()
    path = _write_credentials(auth, access_token="access-token")
    path.write_text("{bad-json", encoding="utf-8")
    with pytest.raises(auth.CodexAuthError) as error:
        auth.codex_auth_status()
    assert error.value.code == "invalid_credentials"
    assert path.read_text() == "{bad-json"


def test_refresh_rotates_token_pair_and_accepts_opaque_access_token(monkeypatch):
    auth = _auth()
    path = _write_credentials(auth, access_token=_jwt(1), expires_at=1)

    def refresh(request):
        assert str(request.url) == "https://auth.openai.com/oauth/token"
        from urllib.parse import parse_qs
        assert parse_qs(request.content.decode()) == {
            "grant_type": ["refresh_token"], "refresh_token": ["refresh-1"],
            "client_id": ["app_EMoamEEZ73f0CkXaXp7hrann"],
        }
        return httpx.Response(200, json={"access_token": "opaque-new-access", "refresh_token": "refresh-2", "expires_in": 3600})

    _use_http(monkeypatch, auth, refresh)
    result = auth.resolve_codex_credentials()
    assert result["access_token"] == "opaque-new-access"
    assert time.time() + 3599 < result["expires_at"] <= time.time() + 3601
    assert json.loads(path.read_text())["refresh_token"] == "refresh-2"
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_refresh_preserves_refresh_token_when_server_omits_replacement(monkeypatch):
    auth = _auth()
    path = _write_credentials(auth, access_token=_jwt(1), expires_at=1)
    _use_http(monkeypatch, auth, lambda request: httpx.Response(200, json={"access_token": "opaque", "expires_in": 3600}))
    assert auth.resolve_codex_credentials()["access_token"] == "opaque"
    assert json.loads(path.read_text())["refresh_token"] == "refresh-1"


def test_concurrent_resolvers_rotate_refresh_token_once(monkeypatch):
    auth = _auth()
    _write_credentials(auth, access_token=_jwt(1), expires_at=1)
    calls = []
    entered = threading.Event()
    release = threading.Event()

    def refresh(request):
        calls.append(request)
        entered.set()
        assert release.wait(timeout=5)
        return httpx.Response(200, json={"access_token": "fresh", "refresh_token": "rotated", "expires_in": 3600})

    _use_http(monkeypatch, auth, refresh)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(auth.resolve_codex_credentials)
        assert entered.wait(timeout=5)
        second = executor.submit(auth.resolve_codex_credentials)
        release.set()
        assert first.result(timeout=5)["access_token"] == "fresh"
        assert second.result(timeout=5)["access_token"] == "fresh"
    assert len(calls) == 1


def test_rejected_token_already_rotated_does_not_refresh_again(monkeypatch):
    auth = _auth()
    _write_credentials(auth, access_token="fresh", expires_at=time.time() + 3600)
    _use_http(monkeypatch, auth, lambda request: pytest.fail("must adopt peer's rotated token"))
    assert auth.resolve_codex_credentials(force_refresh=True, rejected_access_token="old")["access_token"] == "fresh"


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_refresh_http_failure_keeps_stored_tokens_and_hides_response_body(monkeypatch, status):
    auth = _auth()
    path = _write_credentials(auth, access_token=_jwt(1), expires_at=1)
    before = path.read_bytes()
    _use_http(monkeypatch, auth, lambda request: httpx.Response(status, json={"error": "stolen-secret-material"}))
    with pytest.raises(auth.CodexAuthError) as error:
        auth.resolve_codex_credentials()
    assert "stolen-secret-material" not in str(error.value)
    assert path.read_bytes() == before


def test_refresh_network_failure_is_sanitized_and_keeps_credentials(monkeypatch):
    auth = _auth()
    path = _write_credentials(auth, access_token=_jwt(1), expires_at=1)
    before = path.read_bytes()

    def fail(request):
        raise httpx.ConnectError("refresh-1 should not escape", request=request)

    _use_http(monkeypatch, auth, fail)
    with pytest.raises(auth.CodexAuthError) as error:
        auth.resolve_codex_credentials()
    assert error.value.code == "network_error"
    assert "refresh-1" not in str(error.value)
    assert path.read_bytes() == before


@pytest.mark.parametrize("payload", [{"access_token": 12}, {"access_token": ""}, {"access_token": "x", "expires_in": True}])
def test_malformed_refresh_payload_keeps_old_credentials(monkeypatch, payload):
    auth = _auth()
    path = _write_credentials(auth, access_token=_jwt(1), expires_at=1)
    before = path.read_bytes()
    _use_http(monkeypatch, auth, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(auth.CodexAuthError):
        auth.resolve_codex_credentials()
    assert path.read_bytes() == before


@pytest.mark.parametrize("field_name", ["access_token", "refresh_token"])
@pytest.mark.parametrize("control", ["\r", "\n", "\x1b", "\x7f"])
def test_token_response_rejects_controls_before_trimming(monkeypatch, field_name, control):
    auth = _auth()
    path = _write_credentials(auth, access_token=_jwt(1), expires_at=1)
    before = path.read_bytes()
    payload = {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}
    payload[field_name] += control
    _use_http(monkeypatch, auth, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(auth.CodexAuthError) as error:
        auth.resolve_codex_credentials()
    assert error.value.code == "invalid_response"
    assert path.read_bytes() == before
    assert "new-access" not in str(error.value)
    assert "new-refresh" not in str(error.value)


@pytest.mark.parametrize("field_name", ["access_token", "refresh_token", "account_id", "residency"])
def test_stored_credentials_reject_control_characters(field_name):
    auth = _auth()
    path = _write_credentials(auth, access_token="existing-access")
    payload = json.loads(path.read_text())
    payload[field_name] = "private-value\n"
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(auth.CodexAuthError) as error:
        auth.codex_auth_status()
    assert error.value.code == "invalid_credentials"
    assert "private-value" not in str(error.value)
    assert path.read_bytes() == before


@pytest.mark.parametrize("field_name", ["chatgpt_account_id", "chatgpt_data_residency"])
def test_jwt_account_headers_reject_control_characters(monkeypatch, field_name):
    auth = _auth()
    path = _write_credentials(auth, access_token=_jwt(1), expires_at=1)
    claims = {"exp": int(time.time()) + 3600, "https://api.openai.com/auth": {field_name: "private-value\n"}}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    bad_token = f"e30.{payload}.signature"
    _use_http(monkeypatch, auth, lambda request: httpx.Response(200, json={"access_token": bad_token, "expires_in": 3600}))
    before = path.read_bytes()
    with pytest.raises(auth.CodexAuthError) as error:
        auth.resolve_codex_credentials()
    assert error.value.code == "invalid_response"
    assert path.read_bytes() == before
    path = _write_credentials(auth, access_token=bad_token)
    with pytest.raises(auth.CodexAuthError) as error:
        auth.codex_auth_status()
    assert error.value.code == "invalid_credentials"


def test_device_challenge_rejects_terminal_control_characters(monkeypatch):
    auth = _auth()
    _use_http(monkeypatch, auth, lambda request: httpx.Response(200, json={
        "device_auth_id": "device-id", "user_code": "ABCD\x1b", "interval": 5,
    }))
    with pytest.raises(auth.CodexAuthError) as error:
        auth.start_device_login()
    assert error.value.code == "invalid_response"
    assert "ABCD" not in str(error.value)


@pytest.mark.parametrize("field_name", ["access_token", "refresh_token"])
def test_non_ascii_oauth_tokens_fail_before_header_encoding(monkeypatch, field_name):
    auth = _auth()
    path = _write_credentials(auth, access_token=_jwt(1), expires_at=1)
    before = path.read_bytes()
    payload = {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}
    payload[field_name] = "秘密-token"
    _use_http(monkeypatch, auth, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(auth.CodexAuthError) as error:
        auth.resolve_codex_credentials()
    assert error.value.code == "invalid_response"
    assert "秘密-token" not in str(error.value)
    assert path.read_bytes() == before


@pytest.mark.parametrize("field_name", ["access_token", "refresh_token", "account_id", "residency"])
def test_non_ascii_stored_credentials_fail_safely(field_name):
    auth = _auth()
    path = _write_credentials(auth, access_token="existing-access")
    payload = json.loads(path.read_text())
    payload[field_name] = "秘密-value"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(auth.CodexAuthError) as error:
        auth.codex_auth_status()
    assert error.value.code == "invalid_credentials"
    assert "秘密-value" not in str(error.value)


@pytest.mark.parametrize("field_name", ["chatgpt_account_id", "chatgpt_data_residency"])
def test_non_ascii_jwt_account_headers_fail_safely(monkeypatch, field_name):
    auth = _auth()
    _write_credentials(auth, access_token=_jwt(1), expires_at=1)
    claims = {"exp": int(time.time()) + 3600, "https://api.openai.com/auth": {field_name: "秘密-value"}}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    bad_token = f"e30.{payload}.signature"
    _use_http(monkeypatch, auth, lambda request: httpx.Response(200, json={"access_token": bad_token, "expires_in": 3600}))
    with pytest.raises(auth.CodexAuthError) as error:
        auth.resolve_codex_credentials()
    assert error.value.code == "invalid_response"
    _write_credentials(auth, access_token=bad_token)
    with pytest.raises(auth.CodexAuthError) as error:
        auth.codex_auth_status()
    assert error.value.code == "invalid_credentials"


def test_non_ascii_user_code_fails_safely(monkeypatch):
    auth = _auth()
    _use_http(monkeypatch, auth, lambda request: httpx.Response(200, json={
        "device_auth_id": "device-id", "user_code": "秘密-code", "interval": 5,
    }))
    with pytest.raises(auth.CodexAuthError) as error:
        auth.start_device_login()
    assert error.value.code == "invalid_response"


def test_non_utf8_credential_file_reports_safe_corruption():
    auth = _auth()
    path = _write_credentials(auth, access_token="opaque")
    path.write_bytes(b'{"access_token": "secret-\xff"}')
    before = path.read_bytes()
    with pytest.raises(auth.CodexAuthError) as error:
        auth.codex_auth_status()
    assert error.value.code == "invalid_credentials"
    assert "secret" not in str(error.value)
    assert path.read_bytes() == before


def test_logout_removes_only_cloudra_credentials_and_cancels_pending_login(monkeypatch):
    auth = _auth()
    path = _write_credentials(auth, access_token="opaque")
    _use_http(monkeypatch, auth, _device_code)
    challenge = auth.start_device_login()
    auth.logout_codex()
    assert not path.exists()
    assert auth.codex_auth_status()["authenticated"] is False
    with pytest.raises(auth.CodexAuthError):
        auth.poll_device_login(challenge["login_id"])
    auth.logout_codex()


def test_logout_during_token_exchange_prevents_credentials_resurrection(monkeypatch):
    auth = _auth()
    _use_http(monkeypatch, auth, _device_code)
    challenge = auth.start_device_login()
    entered = threading.Event()
    release = threading.Event()

    def authorize(request):
        if request.url.path == "/api/accounts/deviceauth/token":
            return httpx.Response(200, json={"authorization_code": "exchange-code", "code_verifier": "verifier"})
        entered.set()
        assert release.wait(timeout=5)
        return httpx.Response(200, json={"access_token": "opaque-new", "refresh_token": "refresh-new", "expires_in": 3600})

    _use_http(monkeypatch, auth, authorize)
    with ThreadPoolExecutor(max_workers=1) as executor:
        polling = executor.submit(auth.poll_device_login, challenge["login_id"])
        assert entered.wait(timeout=5)
        auth.logout_codex()
        release.set()
        with pytest.raises(auth.CodexAuthError):
            polling.result(timeout=5)
    assert auth.codex_auth_status()["authenticated"] is False


def test_logout_in_other_process_invalidates_pending_device_login(monkeypatch):
    auth = _auth()
    _use_http(monkeypatch, auth, _device_code)
    challenge = auth.start_device_login()
    from cloudra.persistence.paths import codex_auth_path

    process = multiprocessing.get_context("spawn").Process(
        target=_logout_in_separate_process, args=(str(codex_auth_path().parent),),
    )
    process.start()
    try:
        process.join(timeout=10)
        assert process.exitcode == 0, "separate logout process did not finish successfully"
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)

    def authorize(request):
        if request.url.path == "/api/accounts/deviceauth/token":
            return httpx.Response(200, json={"authorization_code": "exchange-code", "code_verifier": "verifier"})
        return httpx.Response(200, json={"access_token": "synthetic-access", "refresh_token": "synthetic-refresh", "expires_in": 3600})

    _use_http(monkeypatch, auth, authorize)
    with pytest.raises(auth.CodexAuthError) as error:
        auth.poll_device_login(challenge["login_id"])
    assert error.value.code == "login_not_found"
    assert not codex_auth_path().exists()
    assert auth.codex_auth_status()["authenticated"] is False


@pytest.mark.parametrize("url,want", [
    ("https://chatgpt.com/backend-api/codex", True),
    ("https://chatgpt.com:443/backend-api/codex/", True),
    ("https://CHATGPT.COM/backend-api/codex", True),
    ("http://chatgpt.com/backend-api/codex", False),
    ("https://chatgpt.com:444/backend-api/codex", False),
    ("https://chatgpt.com.evil.test/backend-api/codex", False),
    ("https://user@chatgpt.com/backend-api/codex", False),
    ("https://chatgpt.com/backend-api/codex/responses", False),
    ("https://chatgpt.com/backend-api/codex?account=other", False),
    ("https://chatgpt.com/backend-api/codex#fragment", False),
    ("https://chatgpt.com:bad/backend-api/codex", False),
])
def test_codex_url_does_not_send_oauth_token_to_other_hosts(url, want):
    assert _auth().is_codex_url(url) is want
