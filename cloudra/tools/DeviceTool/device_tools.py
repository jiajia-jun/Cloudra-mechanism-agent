"""Read-only server Tool proxies backed by the durable Device Broker."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store
from cloudra.services.device_broker import DeviceBroker


async def _invoke_device(
    tool: Tool,
    session: Session,
    tool_name: str,
    arguments: dict,
    *,
    device_id: str = "",
    expected_workspace_revision: int | None = None,
    ttl_seconds: int = 120,
) -> dict:
    conversation_id = getattr(tool.subagent, "conversation_id", "default")
    db = ConversationDB(conversation_id)
    # DeviceBroker 是独立库的同步类（整体异步化不在本次范围），构造与方法
    # 调用一律包 asyncio.to_thread，避免在事件循环线程上同步 sqlite 忙等。
    broker = await asyncio.to_thread(DeviceBroker)
    invocation = await asyncio.to_thread(
        broker.create_invocation,
        conversation_id=conversation_id,
        session_id=session.id,
        tool_name=tool_name,
        arguments=arguments,
        device_id=device_id or None,
        expected_workspace_revision=expected_workspace_revision,
        ttl_seconds=ttl_seconds,
    )
    tool_call_id = invocation["tool_call_id"]
    changed = await session_store.atransition_session_state(
        db,
        session.id,
        expected={"running"},
        target="waiting_for_device",
    )
    if changed:
        await session_store.ainsert_session_event(
            db,
            session.id,
            "waiting_for_device",
            {
                "tool_call_id": tool_call_id,
                "device_id": invocation["device_id"],
                "tool": tool_name,
                "state": "waiting_for_device",
            },
        )
    try:
        while True:
            current = await asyncio.to_thread(broker.get_invocation, tool_call_id)
            if current["state"] in {
                "succeeded",
                "failed",
                "declined",
                "expired",
                "cancelled",
            }:
                return current
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        try:
            await asyncio.to_thread(
                broker.finish,
                invocation["device_id"],
                tool_call_id,
                status="cancelled",
                error="Server session has been cancelled",
            )
        except ValueError:
            pass
        raise
    finally:
        restored = await session_store.atransition_session_state(
            db,
            session.id,
            expected={"waiting_for_device"},
            target="running",
        )
        if restored:
            await session_store.ainsert_session_event(
                db,
                session.id,
                "running",
                {
                    "tool_call_id": tool_call_id,
                    "state": "running",
                },
            )


class DeviceWorkspaceListInput(input_schema):
    path: str = Field(
        default=".",
        description="Relative directory inside the authorized Android workspace",
    )
    max_entries: int = Field(default=200, ge=1, le=1_000)
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )
    expected_workspace_revision: int | None = Field(
        default=None,
        ge=0,
        description="Optional Android workspace revision",
    )


class DeviceWorkspaceListOutput(output_schema):
    is_success: bool
    device_id: str = ""
    path: str = ""
    entries: list[dict] = Field(default_factory=list)
    workspace_revision: int | None = None
    message: str = ""


class DeviceWorkspaceList(Tool):
    tool_id: str = "device-t-1"
    tool_name: str = "device.workspace.list"
    tool_description: str = (
        "List the authorized workspace directory of a paired, online Android device. "
        "Use for: browsing the phone workspace and locating files to read or edit; "
        "distinct from the SAF-authorized directory of device.documents.list."
    )
    input_schema: Any = DeviceWorkspaceListInput
    output_schema: Any = DeviceWorkspaceListOutput

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceWorkspaceListInput,
        session: Session,
    ) -> DeviceWorkspaceListOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {
                "path": user_input.path,
                "max_entries": user_input.max_entries,
            },
            device_id=user_input.device_id,
            expected_workspace_revision=(
                user_input.expected_workspace_revision
            ),
        )
        result = current.get("result") or {}
        return DeviceWorkspaceListOutput(
            is_success=current["state"] == "succeeded",
            device_id=current["device_id"],
            path=str(result.get("path", user_input.path)),
            entries=result.get("entries", []),
            workspace_revision=result.get("workspace_revision"),
            message=current.get("error") or "",
        )


class DeviceWorkspaceReadInput(input_schema):
    path: str = Field(description="Relative file path inside the authorized Android workspace")
    max_bytes: int = Field(default=262_144, ge=1, le=1_048_576)
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )
    expected_workspace_revision: int | None = Field(default=None, ge=0)


class DeviceWorkspaceReadOutput(output_schema):
    is_success: bool
    device_id: str = ""
    path: str = ""
    content: str = ""
    encoding: str = ""
    size: int = 0
    sha256: str = ""
    workspace_revision: int | None = None
    message: str = ""


class DeviceWorkspaceRead(Tool):
    tool_id: str = "device-t-2"
    tool_name: str = "device.workspace.read"
    tool_description: str = (
        "Read a small file from the authorized workspace of a paired, online Android device; returns content and sha256. "
        "Use for: viewing phone-workspace files; also required to get sha256 before a later apply_patch."
    )
    input_schema: Any = DeviceWorkspaceReadInput
    output_schema: Any = DeviceWorkspaceReadOutput

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceWorkspaceReadInput,
        session: Session,
    ) -> DeviceWorkspaceReadOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {
                "path": user_input.path,
                "max_bytes": user_input.max_bytes,
            },
            device_id=user_input.device_id,
            expected_workspace_revision=(
                user_input.expected_workspace_revision
            ),
        )
        result = current.get("result") or {}
        return DeviceWorkspaceReadOutput(
            is_success=current["state"] == "succeeded",
            device_id=current["device_id"],
            path=str(result.get("path", user_input.path)),
            content=str(result.get("content", "")),
            encoding=str(result.get("encoding", "")),
            size=int(result.get("size", 0)),
            sha256=str(result.get("sha256", "")),
            workspace_revision=result.get("workspace_revision"),
            message=current.get("error") or "",
        )


class DeviceConfigGetInput(input_schema):
    keys: list[str] | None = Field(
        default=None,
        description="Public config keys to read; leave empty to return all public fields",
    )
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )


class DeviceConfigGetOutput(output_schema):
    is_success: bool
    device_id: str = ""
    config: dict = Field(default_factory=dict)
    config_revision: int | None = None
    message: str = ""


class DeviceConfigGet(Tool):
    tool_id: str = "device-t-3"
    tool_name: str = "device.config.get"
    tool_description: str = (
        "Read the public, non-secret runtime config of a paired Android device. "
        "Use for: inspecting Device Runtime config and config_revision; patch config with device.config.patch."
    )
    input_schema: Any = DeviceConfigGetInput
    output_schema: Any = DeviceConfigGetOutput

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceConfigGetInput,
        session: Session,
    ) -> DeviceConfigGetOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {"keys": user_input.keys},
            device_id=user_input.device_id,
        )
        result = current.get("result") or {}
        return DeviceConfigGetOutput(
            is_success=current["state"] == "succeeded",
            device_id=current["device_id"],
            config=result.get("config", {}),
            config_revision=result.get("config_revision"),
            message=current.get("error") or "",
        )


class DeviceTextEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_text: str
    new_text: str
    replace_all: bool = False


class DeviceWorkspaceApplyPatchInput(input_schema):
    path: str = Field(description="Relative file path inside the authorized Android workspace")
    expected_sha256: str = Field(
        description="sha256 returned by the latest device.workspace.read"
    )
    edits: list[DeviceTextEdit] = Field(
        min_length=1,
        max_length=100,
        description="Exact text replacements used to build the diff shown before approval",
    )
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )
    expected_workspace_revision: int | None = Field(default=None, ge=0)


class DeviceWorkspaceApplyPatchOutput(output_schema):
    is_success: bool
    device_id: str = ""
    path: str = ""
    status: str = ""
    before_sha256: str | None = None
    after_sha256: str | None = None
    diff: str = ""
    workspace_revision: int | None = None
    message: str = ""


class DeviceWorkspaceApplyPatch(Tool):
    tool_id: str = "device-t-4"
    tool_name: str = "device.workspace.apply_patch"
    tool_description: str = (
        "Show a candidate diff on the Android device and, after user approval, atomically edit authorized workspace text. "
        "Use for: precise edits to existing phone-workspace files; "
        "must call device.workspace.read first for the latest sha256; device-side reject or timeout returns failure."
    )
    input_schema: Any = DeviceWorkspaceApplyPatchInput
    output_schema: Any = DeviceWorkspaceApplyPatchOutput

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceWorkspaceApplyPatchInput,
        session: Session,
    ) -> DeviceWorkspaceApplyPatchOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {
                "path": user_input.path,
                "expected_sha256": user_input.expected_sha256,
                "edits": [
                    edit.model_dump(mode="json")
                    for edit in user_input.edits
                ],
            },
            device_id=user_input.device_id,
            expected_workspace_revision=(
                user_input.expected_workspace_revision
            ),
            ttl_seconds=600,
        )
        result = current.get("result") or {}
        return DeviceWorkspaceApplyPatchOutput(
            is_success=current["state"] == "succeeded",
            device_id=current["device_id"],
            path=str(result.get("path", user_input.path)),
            status=str(result.get("status", current["state"])),
            before_sha256=result.get("before_sha256"),
            after_sha256=result.get("after_sha256"),
            diff=str(result.get("diff", "")),
            workspace_revision=result.get("workspace_revision"),
            message=current.get("error") or "",
        )


class DeviceConfigPatchInput(input_schema):
    patch: dict = Field(
        description=(
            "Only display_name and max_read_bytes are allowed; other fields are rejected"
        )
    )
    expected_config_revision: int = Field(ge=1)
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )


class DeviceConfigPatchOutput(output_schema):
    is_success: bool
    device_id: str = ""
    status: str = ""
    old_values: dict = Field(default_factory=dict)
    new_values: dict = Field(default_factory=dict)
    config_revision: int | None = None
    message: str = ""


class DeviceConfigPatch(Tool):
    tool_id: str = "device-t-5"
    tool_name: str = "device.config.patch"
    tool_description: str = (
        "Show old and new values on the Android device and, after user approval, patch Device Runtime config. "
        "Use for: adjusting public settings such as display_name and max_read_bytes; "
        "call device.config.get first to obtain the current config_revision."
    )
    input_schema: Any = DeviceConfigPatchInput
    output_schema: Any = DeviceConfigPatchOutput

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceConfigPatchInput,
        session: Session,
    ) -> DeviceConfigPatchOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {
                "patch": user_input.patch,
                "expected_config_revision": (
                    user_input.expected_config_revision
                ),
            },
            device_id=user_input.device_id,
            ttl_seconds=600,
        )
        result = current.get("result") or {}
        return DeviceConfigPatchOutput(
            is_success=current["state"] == "succeeded",
            device_id=current["device_id"],
            status=str(result.get("status", current["state"])),
            old_values=result.get("old_values", {}),
            new_values=result.get("new_values", {}),
            config_revision=result.get("config_revision"),
            message=current.get("error") or "",
        )


class DeviceDocumentsListInput(input_schema):
    path: str = Field(
        default=".",
        max_length=4_096,
        description="Relative directory inside the SAF-authorized folder",
    )
    max_entries: int = Field(default=200, ge=1, le=1_000)
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )


class DeviceDocumentsListOutput(output_schema):
    is_success: bool
    device_id: str = ""
    path: str = ""
    entries: list[dict] = Field(default_factory=list)
    status: str = ""
    message: str = ""


class DeviceDocumentsList(Tool):
    tool_id: str = "device-t-6"
    tool_name: str = "device.documents.list"
    tool_description: str = (
        "List directories the Android user persistently authorized via the system document picker (SAF). "
        "Use for: browsing user-shared document folders; distinct from the app workspace of device.workspace.list."
    )
    input_schema: Any = DeviceDocumentsListInput
    output_schema: Any = DeviceDocumentsListOutput

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceDocumentsListInput,
        session: Session,
    ) -> DeviceDocumentsListOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {
                "path": user_input.path,
                "max_entries": user_input.max_entries,
            },
            device_id=user_input.device_id,
        )
        result = current.get("result") or {}
        return DeviceDocumentsListOutput(
            is_success=current["state"] == "succeeded",
            device_id=current["device_id"],
            path=str(result.get("path", user_input.path)),
            entries=result.get("entries", []),
            status=str(result.get("status", current["state"])),
            message=current.get("error") or "",
        )


class DeviceDocumentsReadInput(input_schema):
    path: str = Field(
        max_length=4_096,
        description="Relative file path inside the SAF-authorized folder",
    )
    max_bytes: int = Field(default=262_144, ge=1, le=1_048_576)
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )


class DeviceDocumentsReadOutput(output_schema):
    is_success: bool
    device_id: str = ""
    status: str = ""
    path: str = ""
    name: str = ""
    mime_type: str = ""
    content: str = ""
    encoding: str = ""
    size: int = 0
    sha256: str = ""
    message: str = ""


class DeviceDocumentsRead(Tool):
    tool_id: str = "device-t-7"
    tool_name: str = "device.documents.read"
    tool_description: str = (
        "Read a small file from an Android SAF persistently authorized directory; binaries are returned as base64. "
        "Use for: reading user-shared documents; you must read with this tool first to get the latest sha256 before writing."
    )
    input_schema: Any = DeviceDocumentsReadInput
    output_schema: Any = DeviceDocumentsReadOutput

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceDocumentsReadInput,
        session: Session,
    ) -> DeviceDocumentsReadOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {
                "path": user_input.path,
                "max_bytes": user_input.max_bytes,
            },
            device_id=user_input.device_id,
        )
        result = current.get("result") or {}
        return DeviceDocumentsReadOutput(
            is_success=current["state"] == "succeeded",
            device_id=current["device_id"],
            status=str(result.get("status", current["state"])),
            path=str(result.get("path", user_input.path)),
            name=str(result.get("name", "")),
            mime_type=str(result.get("mime_type", "")),
            content=str(result.get("content", "")),
            encoding=str(result.get("encoding", "")),
            size=int(result.get("size", 0)),
            sha256=str(result.get("sha256", "")),
            message=current.get("error") or "",
        )


class DeviceDocumentsWriteInput(input_schema):
    path: str = Field(
        max_length=4_096,
        description="Existing file path inside the SAF-authorized folder",
    )
    expected_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9A-Fa-f]{64}$",
        description="sha256 returned by the latest device.documents.read"
    )
    content: str = Field(
        max_length=1_398_104,
        description="Base64 content to overwrite after approval, max 1 MiB"
    )
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )


class DeviceDocumentsWriteOutput(output_schema):
    is_success: bool
    device_id: str = ""
    status: str = ""
    path: str = ""
    before_sha256: str | None = None
    after_sha256: str | None = None
    size: int = 0
    message: str = ""


class DeviceDocumentsWrite(Tool):
    tool_id: str = "device-t-8"
    tool_name: str = "device.documents.write"
    tool_description: str = (
        "Show a write summary on Android and, after user approval, overwrite an existing file "
        "in the SAF-authorized directory subject to a sha256 precondition. "
        "Use for: updating user-shared document content; must call device.documents.read first for the latest sha256."
    )
    input_schema: Any = DeviceDocumentsWriteInput
    output_schema: Any = DeviceDocumentsWriteOutput

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceDocumentsWriteInput,
        session: Session,
    ) -> DeviceDocumentsWriteOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {
                "path": user_input.path,
                "expected_sha256": user_input.expected_sha256,
                "content": user_input.content,
            },
            device_id=user_input.device_id,
            ttl_seconds=600,
        )
        result = current.get("result") or {}
        return DeviceDocumentsWriteOutput(
            is_success=current["state"] == "succeeded",
            device_id=current["device_id"],
            status=str(result.get("status", current["state"])),
            path=str(result.get("path", user_input.path)),
            before_sha256=result.get("before_sha256"),
            after_sha256=result.get("after_sha256"),
            size=int(result.get("size", 0)),
            message=current.get("error") or "",
        )


class DeviceFilePickInput(input_schema):
    mime_type: str = Field(default="*/*", max_length=100)
    max_bytes: int = Field(default=262_144, ge=1, le=1_048_576)
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )


class DeviceBinaryCaptureOutput(output_schema):
    is_success: bool
    device_id: str = ""
    status: str = ""
    name: str = ""
    mime_type: str = ""
    content: str = ""
    encoding: str = ""
    size: int = 0
    sha256: str = ""
    width: int | None = None
    height: int | None = None
    message: str = ""


class DeviceFilePick(Tool):
    tool_id: str = "device-t-9"
    tool_name: str = "device.file.pick"
    tool_description: str = (
        "After local Android approval, open the system file picker and read the small file the user explicitly selects. "
        "Use for: asking the user to pick a file on the phone for the Agent (e.g. a photo or document); cannot read arbitrary paths."
    )
    input_schema: Any = DeviceFilePickInput
    output_schema: Any = DeviceBinaryCaptureOutput

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceFilePickInput,
        session: Session,
    ) -> DeviceBinaryCaptureOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {
                "mime_type": user_input.mime_type,
                "max_bytes": user_input.max_bytes,
            },
            device_id=user_input.device_id,
            ttl_seconds=600,
        )
        return _binary_capture_output(current)


class DeviceCameraCaptureInput(input_schema):
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )


class DeviceCameraCapture(Tool):
    tool_id: str = "device-t-10"
    tool_name: str = "device.camera.capture"
    tool_description: str = (
        "After local Android approval, open the system camera and return a JPEG thumbnail of this shot. "
        "Use for: asking the user to photograph a physical object (apparatus, sample, whiteboard) for the Agent to analyze."
    )
    input_schema: Any = DeviceCameraCaptureInput
    output_schema: Any = DeviceBinaryCaptureOutput

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceCameraCaptureInput,
        session: Session,
    ) -> DeviceBinaryCaptureOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {},
            device_id=user_input.device_id,
            ttl_seconds=600,
        )
        return _binary_capture_output(current)


def _binary_capture_output(current: dict) -> DeviceBinaryCaptureOutput:
    result = current.get("result") or {}
    return DeviceBinaryCaptureOutput(
        is_success=current["state"] == "succeeded",
        device_id=current["device_id"],
        status=str(result.get("status", current["state"])),
        name=str(result.get("name", "")),
        mime_type=str(result.get("mime_type", "")),
        content=str(result.get("content", "")),
        encoding=str(result.get("encoding", "")),
        size=int(result.get("size", 0)),
        sha256=str(result.get("sha256", "")),
        width=result.get("width"),
        height=result.get("height"),
        message=current.get("error") or "",
    )


class DeviceShareTextInput(input_schema):
    text: str = Field(min_length=1, max_length=100_000)
    title: str = Field(default="通过…分享", max_length=120)
    subject: str = Field(default="", max_length=200)
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )


class DeviceShareTextOutput(output_schema):
    is_success: bool
    device_id: str = ""
    status: str = ""
    message: str = ""


class DeviceShareText(Tool):
    tool_id: str = "device-t-11"
    tool_name: str = "device.share.text"
    tool_description: str = (
        "Show a text preview on Android and, after local approval, open the system share sheet; "
        "the user still chooses the final destination. "
        "Use for: handing result text to the user to share via WeChat, email, etc.; the Agent does not control the recipient."
    )
    input_schema: Any = DeviceShareTextInput
    output_schema: Any = DeviceShareTextOutput

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceShareTextInput,
        session: Session,
    ) -> DeviceShareTextOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {
                "text": user_input.text,
                "title": user_input.title,
                "subject": user_input.subject,
            },
            device_id=user_input.device_id,
            ttl_seconds=600,
        )
        result = current.get("result") or {}
        return DeviceShareTextOutput(
            is_success=current["state"] == "succeeded",
            device_id=current["device_id"],
            status=str(result.get("status", current["state"])),
            message=current.get("error") or "",
        )


class DeviceNotifyInput(input_schema):
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=240)
    notification_id: str = Field(
        default="",
        max_length=200,
        description="Optional stable ID; the same ID updates an existing notification",
    )
    device_id: str = Field(
        default="",
        description="Target device_id; leave empty to pick an online compatible device",
    )


class DeviceNotifyOutput(output_schema):
    is_success: bool
    device_id: str = ""
    status: str = ""
    message: str = ""


class DeviceNotify(Tool):
    tool_id: str = "device-t-12"
    tool_name: str = "device.notify"
    tool_description: str = (
        "Show a notification preview on Android and, after local approval and if notification permission is granted, display it. "
        "Use for: reminding the user in the notification shade when a long task finishes or needs intervention; send-only, cannot collect a reply."
    )
    input_schema: Any = DeviceNotifyInput
    output_schema: Any = DeviceNotifyOutput

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: DeviceNotifyInput,
        session: Session,
    ) -> DeviceNotifyOutput:
        current = await _invoke_device(
            self,
            session,
            self.tool_name,
            {
                "title": user_input.title,
                "text": user_input.text,
                "notification_id": user_input.notification_id,
            },
            device_id=user_input.device_id,
            ttl_seconds=600,
        )
        result = current.get("result") or {}
        return DeviceNotifyOutput(
            is_success=current["state"] == "succeeded",
            device_id=current["device_id"],
            status=str(result.get("status", current["state"])),
            message=current.get("error") or "",
        )


def get_class():
    """Legacy discovery marker; the explicit registry lists all proxy classes."""

    return DeviceWorkspaceList
