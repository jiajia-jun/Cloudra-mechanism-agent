"""Typed Python boundary for Cloudra's bundled Android native extension."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    import flet as ft
except ImportError:  # pragma: no cover - Android and desktop UI install Flet
    ft = None


class NativeBridgeError(RuntimeError):
    """A native operation failed with a structured, user-displayable status."""

    def __init__(self, status: str, message: str, payload: dict | None = None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


def _normalized_server_url(server_url: str) -> str:
    parsed = urlsplit(server_url.strip())
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            "",
        )
    )


def credential_key(kind: str, server_url: str, device_id: str = "") -> str:
    """Return a non-secret, server-scoped Android Keystore record name."""

    if kind not in {"server", "device"}:
        raise ValueError("credential kind must be server or device")
    scope = "\n".join(
        (_normalized_server_url(server_url), device_id.strip())
    ).encode("utf-8")
    digest = hashlib.sha256(scope).hexdigest()
    return f"cloudra.{kind}.credential.{digest}"


_TRANSPORT_ENC = b"cloudra-transport-v1:enc:"
_TRANSPORT_TAG = b"cloudra-transport-v1:tag:"


def _mgf1(seed: bytes, length: int, hash_name: str = "sha1") -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(
            hashlib.new(
                hash_name,
                seed + counter.to_bytes(4, "big"),
            ).digest()
        )
        counter += 1
    return bytes(output[:length])


def _xor(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def _rsa_oaep_sha256_wrap(
    plaintext: bytes,
    modulus: int,
    exponent: int,
) -> bytes:
    """RSA-OAEP(SHA-256, MGF1-SHA1), matching AndroidKeyStore."""

    size = (modulus.bit_length() + 7) // 8
    digest_size = hashlib.sha256().digest_size
    if len(plaintext) > size - 2 * digest_size - 2:
        raise ValueError("安全传输密钥超过 RSA-OAEP 上限")
    label_hash = hashlib.sha256(b"").digest()
    padding = b"\x00" * (
        size - len(plaintext) - 2 * digest_size - 2
    )
    data_block = label_hash + padding + b"\x01" + plaintext
    seed = secrets.token_bytes(digest_size)
    masked_data = _xor(
        data_block,
        _mgf1(seed, size - digest_size - 1),
    )
    masked_seed = _xor(
        seed,
        _mgf1(masked_data, digest_size),
    )
    encoded = b"\x00" + masked_seed + masked_data
    message = int.from_bytes(encoded, "big")
    if message >= modulus:
        raise ValueError("RSA-OAEP 编码超出模数")
    return pow(message, exponent, modulus).to_bytes(size, "big")


def _transport_stream(
    key: bytes | bytearray,
    nonce: bytes,
    length: int,
) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(
            hmac.digest(
                key,
                _TRANSPORT_ENC
                + nonce
                + counter.to_bytes(4, "big"),
                "sha256",
            )
        )
        counter += 1
    return bytes(output[:length])


def _transport_tag_payload(
    aad: bytes,
    nonce: bytes,
    ciphertext: bytes,
) -> bytes:
    return (
        _TRANSPORT_TAG
        + len(aad).to_bytes(4, "big")
        + aad
        + nonce
        + ciphertext
    )


def _seal_transport(
    key: bytes | bytearray,
    plaintext: bytes,
    *,
    aad: bytes = b"",
) -> dict[str, str]:
    nonce = secrets.token_bytes(16)
    ciphertext = _xor(
        plaintext,
        _transport_stream(key, nonce, len(plaintext)),
    )
    tag = hmac.digest(
        key,
        _transport_tag_payload(aad, nonce, ciphertext),
        "sha256",
    )
    return {
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
    }


def _open_transport(
    key: bytes | bytearray,
    envelope: dict,
    *,
    aad: bytes = b"",
) -> bytes:
    try:
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        ciphertext = base64.b64decode(
            envelope["ciphertext"],
            validate=True,
        )
        tag = base64.b64decode(envelope["tag"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise NativeBridgeError(
            "protocol_error",
            "Android 安全传输信封无效",
        ) from exc
    expected = hmac.digest(
        key,
        _transport_tag_payload(aad, nonce, ciphertext),
        "sha256",
    )
    if len(nonce) != 16 or not hmac.compare_digest(tag, expected):
        raise NativeBridgeError(
            "integrity_error",
            "Android 安全传输信封校验失败",
        )
    return _xor(
        ciphertext,
        _transport_stream(key, nonce, len(ciphertext)),
    )


if ft is not None:

    @ft.control("CloudraNative")
    class CloudraNative(ft.Service):
        """Keystore, foreground service, SAF and Android intent service."""

        # ``repr=False`` matters here: Flet correctly skips these fields while
        # patching controls, but the default dataclass repr would still expose
        # the transport key to an exception/debug log.
        _secure_session_id: str | None = field(
            default=None,
            repr=False,
            metadata={"skip": True},
        )
        _secure_session_key: bytearray | None = field(
            default=None,
            repr=False,
            metadata={"skip": True},
        )

        async def _call(
            self,
            method: str,
            arguments: dict[str, Any] | None = None,
            *,
            timeout: float = 30,
            accepted: set[str] | None = None,
        ) -> dict:
            try:
                response = await self._invoke_method(
                    method,
                    arguments or {},
                    timeout=timeout,
                )
            except Exception as exc:
                raise NativeBridgeError(
                    "bridge_error",
                    f"Android 原生桥调用失败：{exc}",
                ) from exc
            if not isinstance(response, dict):
                raise NativeBridgeError(
                    "protocol_error",
                    "Android 原生桥返回了无效响应",
                )
            payload = dict(response)
            status = str(payload.get("status", "failed"))
            accepted = accepted or {"ok"}
            if status not in accepted:
                raise NativeBridgeError(
                    status,
                    str(payload.get("error") or f"Android 操作失败：{status}"),
                    payload,
                )
            return payload

        async def ping(self) -> dict:
            return await self._call("ping")

        async def _ensure_secure_session(
            self,
            *,
            force: bool = False,
        ) -> tuple[str, bytearray]:
            if force:
                if self._secure_session_key is not None:
                    self._secure_session_key[:] = b"\x00" * len(
                        self._secure_session_key
                    )
                self._secure_session_id = None
                self._secure_session_key = None
            if self._secure_session_id and self._secure_session_key:
                return self._secure_session_id, self._secure_session_key
            public = await self._call("secure_transport_public_key")
            try:
                modulus = int.from_bytes(
                    base64.b64decode(
                        str(public["modulus"]),
                        validate=True,
                    ),
                    "big",
                )
                exponent = int(public["exponent"])
            except (KeyError, TypeError, ValueError) as exc:
                raise NativeBridgeError(
                    "protocol_error",
                    "Android Keystore 公钥响应无效",
                ) from exc
            transport_key = bytearray(secrets.token_bytes(32))
            wrapped = _rsa_oaep_sha256_wrap(
                bytes(transport_key),
                modulus,
                exponent,
            )
            try:
                opened = await self._call(
                    "secure_transport_open",
                    {
                        "wrapped_key": base64.b64encode(wrapped).decode(
                            "ascii"
                        )
                    },
                )
            except Exception:
                transport_key[:] = b"\x00" * len(transport_key)
                raise
            session_id = str(opened.get("session_id", ""))
            if not session_id:
                transport_key[:] = b"\x00" * len(transport_key)
                raise NativeBridgeError(
                    "protocol_error",
                    "Android 安全传输会话响应无效",
                )
            self._secure_session_id = session_id
            self._secure_session_key = transport_key
            return session_id, transport_key

        async def secure_set(self, key: str, value: str) -> None:
            aad = f"set:{key}".encode("utf-8")
            for attempt in range(2):
                session_id, transport_key = (
                    await self._ensure_secure_session(
                        force=attempt > 0,
                    )
                )
                try:
                    await self._call(
                        "secure_set_encrypted",
                        {
                            "key": key,
                            "session_id": session_id,
                            **_seal_transport(
                                transport_key,
                                value.encode("utf-8"),
                                aad=aad,
                            ),
                        },
                    )
                    return
                except NativeBridgeError as exc:
                    if exc.status != "session_expired" or attempt:
                        raise

        async def secure_get(self, key: str) -> str | None:
            aad = f"get:{key}".encode("utf-8")
            for attempt in range(2):
                session_id, transport_key = (
                    await self._ensure_secure_session(
                        force=attempt > 0,
                    )
                )
                try:
                    payload = await self._call(
                        "secure_get_encrypted",
                        {
                            "key": key,
                            "session_id": session_id,
                        },
                    )
                except NativeBridgeError as exc:
                    if exc.status == "session_expired" and not attempt:
                        continue
                    raise
                if not payload.get("found"):
                    return None
                try:
                    return _open_transport(
                        transport_key,
                        payload,
                        aad=aad,
                    ).decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise NativeBridgeError(
                        "protocol_error",
                        "Keystore 凭据不是有效 UTF-8",
                    ) from exc
            raise NativeBridgeError(
                "session_expired",
                "Android 安全传输会话已过期",
            )

        async def secure_remove(self, key: str) -> bool:
            payload = await self._call("secure_remove", {"key": key})
            return bool(payload.get("removed"))

        async def secure_contains(self, key: str) -> bool:
            payload = await self._call("secure_contains", {"key": key})
            return bool(payload.get("contains"))

        async def notification_permission_status(self) -> dict:
            return await self._call(
                "notification_permission_status",
                accepted={"granted", "permission_denied"},
            )

        async def request_notification_permission(self) -> dict:
            return await self._call(
                "request_notification_permission",
                timeout=120,
                accepted={"granted", "permission_denied"},
            )

        async def start_foreground_runtime(
            self,
            *,
            text: str,
            route: str = "cloudra://runtime/status",
        ) -> dict:
            return await self._call(
                "start_foreground_runtime",
                {
                    "title": "Cloudra 设备 Runtime",
                    "text": text,
                    "route": route,
                },
                accepted={"granted", "permission_denied"},
            )

        async def update_foreground_runtime(
            self,
            *,
            text: str,
            route: str = "cloudra://runtime/status",
        ) -> dict:
            return await self._call(
                "update_foreground_runtime",
                {
                    "title": "Cloudra 设备 Runtime",
                    "text": text,
                    "route": route,
                },
                accepted={"granted", "permission_denied"},
            )

        async def stop_foreground_runtime(self) -> None:
            await self._call("stop_foreground_runtime")

        async def show_approval_notification(
            self,
            *,
            tool_call_id: str,
            tool_name: str,
        ) -> dict:
            return await self._call(
                "show_notification",
                {
                    "notification_id": tool_call_id,
                    "title": "Cloudra 等待本地审批",
                    "text": f"{tool_name} 等待你在 Android 上确认",
                    "route": f"cloudra://runtime/approval/{tool_call_id}",
                },
            )

        async def cancel_notification(self, notification_id: str) -> None:
            await self._call(
                "cancel_notification",
                {"notification_id": notification_id},
            )

        async def select_document_tree(self) -> dict:
            return await self._call(
                "select_document_tree",
                timeout=300,
                accepted={"ok", "cancelled"},
            )

        async def get_document_tree(self) -> dict:
            return await self._call(
                "get_document_tree",
                accepted={
                    "ok",
                    "not_authorized",
                    "provider_unavailable",
                },
            )

        async def revoke_document_tree(self) -> dict:
            return await self._call("revoke_document_tree")

        async def execute(self, action: str, arguments: dict) -> dict:
            methods = {
                "documents.list": "documents_list",
                "documents.read": "documents_read",
                "documents.write": "documents_write",
                "file.pick": "pick_file",
                "camera.capture": "capture_photo",
                "share.text": "share_text",
                "notification.show": "show_notification",
            }
            try:
                method = methods[action]
            except KeyError as exc:
                raise NativeBridgeError(
                    "unsupported",
                    f"未注册 Android 原生动作：{action}",
                ) from exc
            interactive = action in {
                "file.pick",
                "camera.capture",
                "share.text",
            }
            return await self._call(
                method,
                arguments,
                timeout=300 if interactive else 60,
                accepted={"ok", "applied", "launched", "cancelled"},
            )

else:

    @dataclass
    class CloudraNative:  # pragma: no cover - import-only fallback
        """Import-time fallback used when Flet is unavailable."""

        def __post_init__(self):
            raise RuntimeError("Flet 未安装，Android 原生桥不可用")


__all__ = [
    "CloudraNative",
    "NativeBridgeError",
    "credential_key",
]
