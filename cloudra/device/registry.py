"""Explicit Android tool manifest and local/native implementations."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from cloudra.persistence.workspace import (
    TextEdit,
    WorkspaceConflictError,
    WorkspaceService,
)


class DeviceToolError(ValueError):
    pass


@dataclass(frozen=True)
class DeviceToolSpec:
    name: str
    description: str
    risk: str
    requires_approval: bool
    handler: Callable[[dict, "DeviceToolContext"], dict] | None
    prepare: (
        Callable[[dict, "DeviceToolContext"], tuple[dict, object]] | None
    ) = None
    apply: Callable[[object, "DeviceToolContext"], dict] | None = None
    native_action: str | None = None

    def manifest(self) -> dict:
        return {
            "name": self.name,
            "schema_version": 1,
            "execution_target": "device",
            "risk": self.risk,
            "requires_approval": self.requires_approval,
            "available": True,
        }


@dataclass(frozen=True)
class DeviceToolContext:
    workspace: Path
    workspace_revision: int
    config_revision: int
    device_id: str
    display_name: str
    state_store: object | None = None


def _resolve_workspace_path(
    context: DeviceToolContext,
    raw_path: str,
    *,
    require_file: bool = False,
    require_dir: bool = False,
) -> Path:
    root = context.workspace.expanduser().resolve(strict=True)
    relative = Path(raw_path or ".")
    if relative.is_absolute() or ".." in relative.parts or "\x00" in raw_path:
        raise DeviceToolError("设备工作区路径越界")
    current = root
    for part in relative.parts:
        if part in {"", "."}:
            continue
        current = current / part
        if current.is_symlink():
            raise DeviceToolError("设备工作区路径包含符号链接")
    resolved = (root / relative).resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DeviceToolError("设备工作区路径越界") from exc
    if require_file and not resolved.is_file():
        raise DeviceToolError("目标不是普通文件")
    if require_dir and not resolved.is_dir():
        raise DeviceToolError("目标不是目录")
    return resolved


def _workspace_list(arguments: dict, context: DeviceToolContext) -> dict:
    raw_path = str(arguments.get("path", "."))
    max_entries = min(max(int(arguments.get("max_entries", 200)), 1), 1_000)
    directory = _resolve_workspace_path(
        context,
        raw_path,
        require_dir=True,
    )
    root = context.workspace.resolve(strict=True)
    entries = []
    for child in sorted(directory.iterdir(), key=lambda item: item.name):
        if len(entries) >= max_entries:
            break
        if child.is_symlink():
            kind = "symlink"
            size = None
        elif child.is_dir():
            kind = "directory"
            size = None
        elif child.is_file():
            kind = "file"
            size = child.stat().st_size
        else:
            kind = "other"
            size = None
        entries.append(
            {
                "name": child.name,
                "path": child.relative_to(root).as_posix(),
                "kind": kind,
                "size": size,
            }
        )
    return {
        "path": directory.relative_to(root).as_posix() or ".",
        "entries": entries,
        "truncated": len(entries) >= max_entries,
        "workspace_revision": context.workspace_revision,
    }


def _workspace_read(arguments: dict, context: DeviceToolContext) -> dict:
    raw_path = str(arguments.get("path", ""))
    configured_limit = 1_048_576
    if context.state_store is not None:
        configured_limit = int(
            context.state_store.public_config(
                context.display_name
            ).get("max_read_bytes", configured_limit)
        )
    max_bytes = min(
        max(int(arguments.get("max_bytes", 262_144)), 1),
        1_048_576,
        configured_limit,
    )
    source = _resolve_workspace_path(
        context,
        raw_path,
        require_file=True,
    )
    size = source.stat().st_size
    if size > max_bytes:
        raise DeviceToolError(
            f"文件大小 {size} bytes，超过本次读取上限 {max_bytes} bytes"
        )
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    try:
        decoded = content.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        decoded = base64.b64encode(content).decode("ascii")
        encoding = "base64"
    return {
        "path": source.relative_to(context.workspace.resolve()).as_posix(),
        "content": decoded,
        "encoding": encoding,
        "size": len(content),
        "sha256": digest,
        "workspace_revision": context.workspace_revision,
    }


def _config_get(arguments: dict, context: DeviceToolContext) -> dict:
    requested = arguments.get("keys")
    public = {
        "device_id": context.device_id,
        "display_name": context.display_name,
        "workspace_name": context.workspace.name,
        "workspace_authorized": True,
        "workspace_revision": context.workspace_revision,
        "config_revision": context.config_revision,
    }
    if context.state_store is not None:
        public.update(
            context.state_store.public_config(context.display_name)
        )
    if requested is None:
        return {"config": public, "config_revision": context.config_revision}
    if not isinstance(requested, list) or not all(
        isinstance(item, str) for item in requested
    ):
        raise DeviceToolError("keys 必须是字符串列表")
    unknown = sorted(set(requested) - set(public))
    if unknown:
        raise DeviceToolError(
            "请求了未公开的设备配置字段：" + ", ".join(unknown)
        )
    return {
        "config": {key: public[key] for key in requested},
        "config_revision": context.config_revision,
    }


def _workspace_patch_prepare(
    arguments: dict,
    context: DeviceToolContext,
) -> tuple[dict, object]:
    raw_edits = arguments.get("edits")
    if not isinstance(raw_edits, list) or not raw_edits or len(raw_edits) > 100:
        raise DeviceToolError("edits 必须是 1–100 项文本替换列表")
    edits = []
    for raw in raw_edits:
        if not isinstance(raw, dict):
            raise DeviceToolError("每项 edit 必须是对象")
        old_text = raw.get("old_text")
        new_text = raw.get("new_text")
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            raise DeviceToolError("edit 的 old_text/new_text 必须是字符串")
        edits.append(
            TextEdit(
                old_text=old_text,
                new_text=new_text,
                replace_all=bool(raw.get("replace_all", False)),
            )
        )
    service = WorkspaceService(context.workspace)
    try:
        change = service.prepare_edit(
            str(arguments.get("path", "")),
            str(arguments.get("expected_sha256", "")),
            edits,
        )
    except WorkspaceConflictError as exc:
        raise DeviceToolError(str(exc)) from exc
    preview = {
        "tool": "device.workspace.apply_patch",
        "path": change.relative_path,
        "risk_summary": "修改 Android 授权工作区文件",
        "before_sha256": change.before_sha256,
        "after_sha256": change.after_sha256,
        "additions": change.additions,
        "deletions": change.deletions,
        "diff": change.diff,
        "workspace_revision": context.workspace_revision,
    }
    return preview, (service, change)


def _workspace_patch_apply(
    prepared: object,
    context: DeviceToolContext,
) -> dict:
    service, change = prepared
    service.apply(change)
    if context.state_store is None:
        raise DeviceToolError("设备状态存储不可用")
    revision = context.state_store.bump_workspace_revision(
        change.relative_path
    )
    return {
        "path": change.relative_path,
        "before_sha256": change.before_sha256,
        "after_sha256": change.after_sha256,
        "diff": change.diff,
        "workspace_revision": revision,
        "status": "applied",
    }


def _config_patch_prepare(
    arguments: dict,
    context: DeviceToolContext,
) -> tuple[dict, object]:
    if context.state_store is None:
        raise DeviceToolError("设备状态存储不可用")
    patch = arguments.get("patch")
    if not isinstance(patch, dict) or not patch:
        raise DeviceToolError("patch 必须是非空对象")
    allowed = {"display_name", "max_read_bytes"}
    unknown = sorted(set(patch) - allowed)
    if unknown:
        raise DeviceToolError("不允许修改配置字段：" + ", ".join(unknown))
    normalized = {}
    if "display_name" in patch:
        display_name = str(patch["display_name"]).strip()
        if not display_name or len(display_name) > 100:
            raise DeviceToolError("display_name 长度必须为 1–100")
        normalized["display_name"] = display_name
    if "max_read_bytes" in patch:
        max_read_bytes = int(patch["max_read_bytes"])
        if not 1_024 <= max_read_bytes <= 1_048_576:
            raise DeviceToolError(
                "max_read_bytes 必须在 1024–1048576 之间"
            )
        normalized["max_read_bytes"] = max_read_bytes
    expected = int(
        arguments.get(
            "expected_config_revision",
            context.config_revision,
        )
    )
    if expected != context.config_revision:
        raise DeviceToolError(
            "设备配置 revision 不匹配，请重新读取后再修改"
        )
    old_config = context.state_store.public_config(context.display_name)
    new_config = dict(old_config)
    new_config.update(normalized)
    preview = {
        "tool": "device.config.patch",
        "risk_summary": "修改 Android Device Runtime 配置",
        "old_values": {
            key: old_config.get(key) for key in normalized
        },
        "new_values": normalized,
        "config_revision": context.config_revision,
    }
    return preview, {
        "expected_config_revision": expected,
        "patch": normalized,
        "old_values": {
            key: old_config.get(key) for key in normalized
        },
        "new_config": new_config,
    }


def _config_patch_apply(
    prepared: object,
    context: DeviceToolContext,
) -> dict:
    if context.state_store is None:
        raise DeviceToolError("设备状态存储不可用")
    return context.state_store.apply_config_patch(
        prepared["expected_config_revision"],
        prepared["patch"],
        prepared["old_values"],
    )


def _document_path(raw_path: object, *, allow_root: bool = False) -> str:
    path = str(raw_path or ".").strip()
    if path in {"", "."}:
        if allow_root:
            return "."
        raise DeviceToolError("文档路径不能为空")
    relative = Path(path)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or "\\" in path
        or "\x00" in path
        or any(ord(char) < 32 for char in path)
    ):
        raise DeviceToolError("Android 文档路径越界")
    parts = [part for part in relative.parts if part not in {"", "."}]
    if not parts or len(parts) > 64 or any(len(part) > 255 for part in parts):
        raise DeviceToolError("Android 文档路径无效")
    return Path(*parts).as_posix()


def _documents_write_prepare(
    arguments: dict,
    context: DeviceToolContext,
) -> tuple[dict, object]:
    path = _document_path(arguments.get("path"))
    expected = str(arguments.get("expected_sha256", "")).lower().strip()
    if len(expected) != 64 or any(
        character not in "0123456789abcdef" for character in expected
    ):
        raise DeviceToolError("expected_sha256 必须是 64 位十六进制摘要")
    content = arguments.get("content")
    if not isinstance(content, str):
        raise DeviceToolError("content 必须是 base64 字符串")
    if len(content) > 1_398_104:
        raise DeviceToolError("写入内容超过 1 MiB")
    try:
        decoded = base64.b64decode(content, validate=True)
    except (ValueError, TypeError) as exc:
        raise DeviceToolError("content 不是有效 base64") from exc
    if len(decoded) > 1_048_576:
        raise DeviceToolError("写入内容超过 1 MiB")
    after = hashlib.sha256(decoded).hexdigest()
    normalized = {
        "path": path,
        "expected_sha256": expected,
        "content": content,
    }
    return (
        {
            "tool": "device.documents.write",
            "path": path,
            "risk_summary": "覆盖 Android 持久授权文档目录中的文件",
            "before_sha256": expected,
            "after_sha256": after,
            "size": len(decoded),
        },
        normalized,
    )


def _file_pick_prepare(
    arguments: dict,
    context: DeviceToolContext,
) -> tuple[dict, object]:
    max_bytes = min(
        max(int(arguments.get("max_bytes", 262_144)), 1),
        1_048_576,
    )
    mime_type = str(arguments.get("mime_type", "*/*")).strip() or "*/*"
    if len(mime_type) > 100 or re.fullmatch(
        r"(?:\*/\*|[\w.+-]+/[\w.+*-]+)",
        mime_type,
        flags=re.ASCII,
    ) is None:
        raise DeviceToolError("mime_type 无效")
    normalized = {"max_bytes": max_bytes, "mime_type": mime_type}
    return (
        {
            "tool": "device.file.pick",
            "risk_summary": "打开 Android 文件选择器并把所选小文件交给服务器",
            "mime_type": mime_type,
            "max_bytes": max_bytes,
        },
        normalized,
    )


def _camera_prepare(
    arguments: dict,
    context: DeviceToolContext,
) -> tuple[dict, object]:
    if arguments:
        unknown = ", ".join(sorted(map(str, arguments)))
        raise DeviceToolError(f"相机工具不接受参数：{unknown}")
    return (
        {
            "tool": "device.camera.capture",
            "risk_summary": "打开 Android 相机并把本次拍摄的缩略图交给服务器",
        },
        {},
    )


def _share_prepare(
    arguments: dict,
    context: DeviceToolContext,
) -> tuple[dict, object]:
    text = arguments.get("text")
    if not isinstance(text, str) or not 1 <= len(text) <= 100_000:
        raise DeviceToolError("分享文本长度必须为 1–100000")
    title = str(arguments.get("title", "通过…分享")).strip()[:120]
    subject = str(arguments.get("subject", "")).strip()[:200]
    normalized = {"text": text, "title": title, "subject": subject}
    return (
        {
            "tool": "device.share.text",
            "risk_summary": "打开 Android 系统分享面板并预填以下文本",
            "text_preview": text[:20_000],
            "truncated": len(text) > 20_000,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "title": title,
            "subject": subject,
        },
        normalized,
    )


def _notification_prepare(
    arguments: dict,
    context: DeviceToolContext,
) -> tuple[dict, object]:
    title = str(arguments.get("title", "")).strip()
    text = str(arguments.get("text", "")).strip()
    if not 1 <= len(title) <= 120:
        raise DeviceToolError("通知 title 长度必须为 1–120")
    if not 1 <= len(text) <= 240:
        raise DeviceToolError("通知 text 长度必须为 1–240")
    notification_id = str(
        arguments.get("notification_id")
        or hashlib.sha256(
            f"{title}\n{text}".encode("utf-8")
        ).hexdigest()[:32]
    ).strip()
    if not notification_id or len(notification_id) > 200:
        raise DeviceToolError("notification_id 长度必须为 1–200")
    normalized = {
        "title": title,
        "text": text,
        "notification_id": notification_id,
        "route": "cloudra://runtime/status",
    }
    return (
        {
            "tool": "device.notify",
            "risk_summary": "在 Android 系统通知栏显示以下内容",
            "title": title,
            "text": text,
            "notification_id": notification_id,
        },
        normalized,
    )


DEVICE_TOOLS: dict[str, DeviceToolSpec] = {
    "device.workspace.list": DeviceToolSpec(
        name="device.workspace.list",
        description="列出用户授权的 Android 工作区目录",
        risk="read",
        requires_approval=False,
        handler=_workspace_list,
    ),
    "device.workspace.read": DeviceToolSpec(
        name="device.workspace.read",
        description="读取用户授权的 Android 工作区文件",
        risk="read",
        requires_approval=False,
        handler=_workspace_read,
    ),
    "device.config.get": DeviceToolSpec(
        name="device.config.get",
        description="读取 Android 公开且不含密钥的运行配置",
        risk="read",
        requires_approval=False,
        handler=_config_get,
    ),
    "device.workspace.apply_patch": DeviceToolSpec(
        name="device.workspace.apply_patch",
        description="审批后修改 Android 授权工作区内的 UTF-8 文本文件",
        risk="write",
        requires_approval=True,
        handler=None,
        prepare=_workspace_patch_prepare,
        apply=_workspace_patch_apply,
    ),
    "device.config.patch": DeviceToolSpec(
        name="device.config.patch",
        description="审批后修改 Android Device Runtime 的公开配置",
        risk="write",
        requires_approval=True,
        handler=None,
        prepare=_config_patch_prepare,
        apply=_config_patch_apply,
    ),
    "device.documents.list": DeviceToolSpec(
        name="device.documents.list",
        description="列出 Android SAF 持久授权文档目录",
        risk="read",
        requires_approval=False,
        handler=None,
        native_action="documents.list",
    ),
    "device.documents.read": DeviceToolSpec(
        name="device.documents.read",
        description="读取 Android SAF 持久授权文档目录中的小文件",
        risk="read",
        requires_approval=False,
        handler=None,
        native_action="documents.read",
    ),
    "device.documents.write": DeviceToolSpec(
        name="device.documents.write",
        description="本地审批后按 sha256 前置条件覆盖 Android SAF 文档",
        risk="write",
        requires_approval=True,
        handler=None,
        prepare=_documents_write_prepare,
        native_action="documents.write",
    ),
    "device.file.pick": DeviceToolSpec(
        name="device.file.pick",
        description="本地审批后打开 Android 文件选择器并读取所选小文件",
        risk="read",
        requires_approval=True,
        handler=None,
        prepare=_file_pick_prepare,
        native_action="file.pick",
    ),
    "device.camera.capture": DeviceToolSpec(
        name="device.camera.capture",
        description="本地审批后打开 Android 相机并返回本次照片缩略图",
        risk="sensor",
        requires_approval=True,
        handler=None,
        prepare=_camera_prepare,
        native_action="camera.capture",
    ),
    "device.share.text": DeviceToolSpec(
        name="device.share.text",
        description="本地审批后打开 Android 系统分享面板并预填文本",
        risk="external",
        requires_approval=True,
        handler=None,
        prepare=_share_prepare,
        native_action="share.text",
    ),
    "device.notify": DeviceToolSpec(
        name="device.notify",
        description="本地审批后在 Android 系统通知栏显示消息",
        risk="external",
        requires_approval=True,
        handler=None,
        prepare=_notification_prepare,
        native_action="notification.show",
    ),
}


def capability_manifest() -> list[dict]:
    return [DEVICE_TOOLS[name].manifest() for name in sorted(DEVICE_TOOLS)]


def capability_revision() -> int:
    encoded = json.dumps(
        capability_manifest(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return max(1, int(hashlib.sha256(encoded).hexdigest()[:8], 16))
