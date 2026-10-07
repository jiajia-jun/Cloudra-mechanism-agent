"""Independent Codex OAuth session and device login for Cloudra.

These functions perform synchronous network/file operations. Async callers must use
``asyncio.to_thread``. This module never borrows or modifies Codex CLI credentials.
Protocol reference: NousResearch/hermes-agent, commit cc75e8f4021f7efab99158f57601be4d691a6da9.
"""

from __future__ import annotations

import base64
import json
import math
import os
import secrets
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, ValidationError, field_validator

from cloudra.infra.flocks import locked
from cloudra.persistence.paths import codex_auth_epoch_path, codex_auth_lock_path, codex_auth_path

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
_ISSUER = "https://auth.openai.com"
_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_TOKEN_URL = f"{_ISSUER}/oauth/token"
_REFRESH_SKEW_SECONDS = 120
_LOGIN_LIFETIME_SECONDS = 900
_AUTH_HTTP_TIMEOUT_SECONDS = 20.0

_NonemptyString = Annotated[StrictStr, Field(min_length=1)]
_PositiveSeconds = Annotated[StrictInt | StrictFloat, Field(gt=0, allow_inf_nan=False)]


class CodexAuthError(RuntimeError):
    """Safe authentication failure whose message never contains upstream payloads."""

    def __init__(
        self, message: str, *, code: str, status_code: int | None = None, relogin_required: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.relogin_required = relogin_required


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @field_validator("*", mode="before")
    @classmethod
    def strip_nonempty_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            if not value.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError("invalid character in field")
            value = value.strip()
            if not value:
                raise ValueError("empty field")
        return value


class _DeviceCode(_ResponseModel):
    device_auth_id: _NonemptyString = Field(repr=False)
    user_code: _NonemptyString
    interval: StrictInt = Field(default=5, gt=0)
    expires_in: _PositiveSeconds = _LOGIN_LIFETIME_SECONDS

    @field_validator("interval", mode="before")
    @classmethod
    def numeric_interval(cls, value: Any) -> Any:
        if isinstance(value, str) and value.isdecimal():
            return int(value)
        return value


class _AuthorizationCode(_ResponseModel):
    authorization_code: _NonemptyString = Field(repr=False)
    code_verifier: _NonemptyString = Field(repr=False)


class _TokenResponse(_ResponseModel):
    access_token: _NonemptyString = Field(repr=False)
    refresh_token: _NonemptyString | None = Field(default=None, repr=False)
    id_token: _NonemptyString | None = Field(default=None, repr=False)
    expires_in: _PositiveSeconds | None = None


class _Credentials(_ResponseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: _NonemptyString = Field(repr=False)
    refresh_token: _NonemptyString = Field(repr=False)
    expires_at: _PositiveSeconds | None = None
    account_id: _NonemptyString | None = None
    residency: _NonemptyString | None = None


@dataclass
class _DeviceFlow:
    device_auth_id: str = field(repr=False)
    user_code: str
    interval: int
    expires_at: float
    next_poll_at: float
    store_path: Path
    lock_path: Path
    epoch_path: Path
    logout_epoch: int
    poll_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


_pending_flows: dict[str, _DeviceFlow] = {}
_flow_lock = threading.Lock()
_logout_generation = 0


def is_codex_url(url: str) -> bool:
    """Accept only the official HTTPS base URL before attaching OAuth credentials."""
    if not isinstance(url, str) or url != url.strip() or any(ord(char) < 32 for char in url):
        return False
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "chatgpt.com"
            and parsed.port in (None, 443)
            and parsed.path in {"/backend-api/codex", "/backend-api/codex/"}
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and "?" not in url
            and "#" not in url
        )
    except ValueError:
        return False


def _http_client() -> httpx.Client:
    return httpx.Client(
        timeout=_AUTH_HTTP_TIMEOUT_SECONDS,
        headers={"Accept": "application/json", "User-Agent": "Cloudra OAuth"},
        follow_redirects=False,
    )


def _post(url: str, **kwargs: Any) -> httpx.Response:
    try:
        with _http_client() as client:
            return client.post(url, **kwargs)
    except httpx.HTTPError:
        raise CodexAuthError("无法连接 OpenAI 认证服务，请稍后重试。", code="network_error") from None


def _check_response(response: httpx.Response, *, refreshing: bool = False) -> None:
    if response.status_code == 200:
        return
    relogin = refreshing and response.status_code in {401, 403}
    if refreshing and response.status_code == 400:
        try:
            payload = response.json()
            error = payload.get("error") if isinstance(payload, dict) else None
            error = error.get("code") if isinstance(error, dict) else error
            relogin = isinstance(error, str) and error in {"invalid_grant", "invalid_token", "refresh_token_reused"}
        except (ValueError, TypeError):
            pass
    if response.status_code == 429:
        message, code = "OpenAI 认证服务暂时限流，请稍后重试。", "rate_limited"
    elif relogin:
        message, code = "Codex 登录已失效，请重新登录。", "reauthentication_required"
    else:
        message, code = f"OpenAI 认证请求失败（HTTP {response.status_code}），请稍后重试。", "auth_http_error"
    raise CodexAuthError(message, code=code, status_code=response.status_code, relogin_required=relogin)


def _parse_response(response: httpx.Response, schema: type[BaseModel]) -> Any:
    try:
        return schema.model_validate(response.json())
    except (ValueError, ValidationError):
        raise CodexAuthError("OpenAI 认证服务返回了无效数据。", code="invalid_response") from None


def _jwt_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        return payload if isinstance(payload, dict) else {}
    except (ValueError, UnicodeError):
        return {}


def _token_identity(token: str, *, invalid_code: str = "invalid_credentials") -> tuple[str | None, str | None, float | None]:
    claims = _jwt_claims(token)
    exp = claims.get("exp")
    expires = float(exp) if isinstance(exp, (int, float)) and not isinstance(exp, bool) and math.isfinite(exp) and exp > 0 else None
    auth = claims.get("https://api.openai.com/auth")
    auth = auth if isinstance(auth, dict) else {}
    account_id = auth.get("chatgpt_account_id")
    residency = auth.get("chatgpt_data_residency") or auth.get("chatgpt_compute_residency")
    for value in (account_id, residency):
        if isinstance(value, str) and (not value.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise CodexAuthError("Codex 登录中的账户信息无效。", code=invalid_code)
    account_id = account_id.strip() if isinstance(account_id, str) and account_id.strip() else None
    residency = residency.strip() if isinstance(residency, str) and residency.strip() else None
    return account_id, residency, expires


def _credentials_from_response(tokens: _TokenResponse, previous: _Credentials | None = None) -> _Credentials:
    refresh = tokens.refresh_token or (previous.refresh_token if previous else None)
    if refresh is None:
        raise CodexAuthError("OpenAI 认证服务未返回完整的登录凭据。", code="invalid_response")
    account_id, residency, expires_at = _token_identity(tokens.access_token, invalid_code="invalid_response")
    if tokens.id_token:
        id_account, id_residency, _ = _token_identity(tokens.id_token, invalid_code="invalid_response")
        account_id, residency = account_id or id_account, residency or id_residency
    if previous:
        prev_account, prev_residency, _ = _token_identity(previous.access_token)
        account_id = account_id or previous.account_id or prev_account
        residency = residency or previous.residency or prev_residency
    if tokens.expires_in is not None:
        response_expiry = time.time() + float(tokens.expires_in)
        expires_at = min(expires_at, response_expiry) if expires_at is not None else response_expiry
    return _Credentials(
        access_token=tokens.access_token, refresh_token=refresh, expires_at=expires_at,
        account_id=account_id, residency=residency,
    )


def _load_credentials(path: Path) -> _Credentials | None:
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UnicodeError:
        raise CodexAuthError("Cloudra 的 Codex 登录凭据格式无效，请重新登录。", code="invalid_credentials") from None
    except OSError:
        raise CodexAuthError("无法读取 Cloudra 的 Codex 登录凭据。", code="credentials_unreadable") from None
    try:
        return _Credentials.model_validate(json.loads(content))
    except (ValueError, ValidationError):
        raise CodexAuthError("Cloudra 的 Codex 登录凭据格式无效，请重新登录。", code="invalid_credentials") from None


def _save_private_json(path: Path, value: dict[str, Any] | int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".codex_oauth-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(value, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _save_credentials(path: Path, credentials: _Credentials) -> None:
    _save_private_json(path, credentials.model_dump())


def _read_logout_epoch(path: Path) -> int:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0
    except (OSError, ValueError):
        raise CodexAuthError("无法读取 Codex 登录注销记录，请稍后重试。", code="invalid_logout_epoch") from None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CodexAuthError("Codex 登录注销记录格式无效。", code="invalid_logout_epoch")
    return value


def start_device_login() -> dict[str, Any]:
    """Create a device-code challenge; expose only an opaque local login handle."""
    with _flow_lock:
        generation = _logout_generation
    store_path, lock_path, epoch_path = codex_auth_path(), codex_auth_lock_path(), codex_auth_epoch_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    with locked(str(lock_path)):
        logout_epoch = _read_logout_epoch(epoch_path)
    response = _post(f"{_ISSUER}/api/accounts/deviceauth/usercode", json={"client_id": _CLIENT_ID})
    _check_response(response)
    challenge = _parse_response(response, _DeviceCode)
    now = time.time()
    interval = max(3, challenge.interval)
    expires_at = now + min(float(challenge.expires_in), _LOGIN_LIFETIME_SECONDS)
    login_id = secrets.token_urlsafe(32)
    flow = _DeviceFlow(
        device_auth_id=challenge.device_auth_id, user_code=challenge.user_code,
        interval=interval, expires_at=expires_at, next_poll_at=now,
        store_path=store_path, lock_path=lock_path, epoch_path=epoch_path, logout_epoch=logout_epoch,
    )
    with _flow_lock:
        if generation != _logout_generation:
            raise CodexAuthError("Codex 登录已取消。", code="login_not_found")
        for expired_id in [key for key, item in _pending_flows.items() if item.expires_at <= now]:
            del _pending_flows[expired_id]
        _pending_flows[login_id] = flow
    return {
        "login_id": login_id, "user_code": challenge.user_code,
        "verification_uri": f"{_ISSUER}/codex/device", "interval": interval, "expires_at": expires_at,
    }


def _require_current_flow(login_id: str, flow: _DeviceFlow) -> None:
    """Called under the flow lock, including immediately before token persistence."""
    if _pending_flows.get(login_id) is not flow:
        raise CodexAuthError("Codex 登录不存在或已取消，请重新开始登录。", code="login_not_found")
    if flow.expires_at <= time.time():
        del _pending_flows[login_id]
        raise CodexAuthError("Codex 登录已超时，请重新开始登录。", code="login_expired")


def poll_device_login(login_id: str) -> dict[str, str]:
    """Perform at most one authorization poll and save tokens once authorized."""
    with _flow_lock:
        flow = _pending_flows.get(login_id) if isinstance(login_id, str) else None
        if flow is None:
            raise CodexAuthError("Codex 登录不存在或已取消，请重新开始登录。", code="login_not_found")
    with flow.poll_lock:
        with _flow_lock:
            _require_current_flow(login_id, flow)
            now = time.time()
            if now < flow.next_poll_at:
                return {"status": "pending"}
            flow.next_poll_at = now + flow.interval
        response = _post(
            f"{_ISSUER}/api/accounts/deviceauth/token",
            json={"device_auth_id": flow.device_auth_id, "user_code": flow.user_code},
        )
        with _flow_lock:
            _require_current_flow(login_id, flow)
        if response.status_code in {403, 404}:
            return {"status": "pending"}
        _check_response(response)
        authorized = _parse_response(response, _AuthorizationCode)
        response = _post(_TOKEN_URL, data={
            "grant_type": "authorization_code", "code": authorized.authorization_code,
            "redirect_uri": f"{_ISSUER}/deviceauth/callback", "client_id": _CLIENT_ID,
            "code_verifier": authorized.code_verifier,
        })
        _check_response(response)
        credentials = _credentials_from_response(_parse_response(response, _TokenResponse))
        with _flow_lock:
            _require_current_flow(login_id, flow)
            flow.store_path.parent.mkdir(parents=True, exist_ok=True)
            with locked(str(flow.lock_path)):
                if _read_logout_epoch(flow.epoch_path) != flow.logout_epoch:
                    del _pending_flows[login_id]
                    raise CodexAuthError("Codex 登录不存在或已取消，请重新开始登录。", code="login_not_found")
                _save_credentials(flow.store_path, credentials)
            del _pending_flows[login_id]
        return {"status": "authorized"}


def codex_auth_status() -> dict[str, Any]:
    """Read token availability without performing refresh or creating lock files."""
    credentials = _load_credentials(codex_auth_path())
    if credentials is None:
        return {"authenticated": False, "expires_at": None, "account_id": None}
    account_id, _, expires_at = _token_identity(credentials.access_token)
    return {
        "authenticated": True,
        "expires_at": credentials.expires_at or expires_at,
        "account_id": credentials.account_id or account_id,
    }


def logout_codex() -> None:
    """Remove Cloudra's session and invalidate login flows, including in-flight ones."""
    global _logout_generation
    with _flow_lock:
        _logout_generation += 1
        _pending_flows.clear()
        path = codex_auth_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with locked(str(codex_auth_lock_path())):
            epoch_path = codex_auth_epoch_path()
            _save_private_json(epoch_path, _read_logout_epoch(epoch_path) + 1)
            path.unlink(missing_ok=True)


def resolve_codex_credentials(
    force_refresh: bool = False, rejected_access_token: str | None = None,
) -> dict[str, Any]:
    """Resolve/refresh the independent session; returned secrets are runtime-internal."""
    path = codex_auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(str(codex_auth_lock_path())):
        credentials = _load_credentials(path)
        if credentials is None:
            raise CodexAuthError("请先登录 Codex OAuth。", code="authentication_required", relogin_required=True)
        _, _, jwt_expiry = _token_identity(credentials.access_token)
        expiry = credentials.expires_at or jwt_expiry
        peer_rotated = rejected_access_token is not None and credentials.access_token != rejected_access_token
        expiring = expiry is not None and expiry <= time.time() + _REFRESH_SKEW_SECONDS
        if (force_refresh and not peer_rotated) or expiring:
            response = _post(_TOKEN_URL, data={
                "grant_type": "refresh_token", "refresh_token": credentials.refresh_token, "client_id": _CLIENT_ID,
            })
            _check_response(response, refreshing=True)
            credentials = _credentials_from_response(_parse_response(response, _TokenResponse), credentials)
            _save_credentials(path, credentials)
        account_id, residency, jwt_expiry = _token_identity(credentials.access_token)
        return {
            "access_token": credentials.access_token,
            "account_id": credentials.account_id or account_id,
            "residency": credentials.residency or residency,
            "expires_at": credentials.expires_at or jwt_expiry,
        }
