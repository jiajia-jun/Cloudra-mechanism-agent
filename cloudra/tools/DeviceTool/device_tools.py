"""Read-only server Tool proxies backed by the durable Device Broker."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cloudra import session_store
from cloudra.database import ConversationDB
from cloudra.device_broker import DeviceBroker
from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema


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
    broker = DeviceBroker()
    invocation = broker.create_invocation(
        conversation_id=conversation_id,
        session_id=session.id,
        tool_name=tool_name,
        arguments=arguments,
        device_id=device_id or None,
        expected_workspace_revision=expected_workspace_revision,
        ttl_seconds=ttl_seconds,
    )
    tool_call_id = invocation["tool_call_id"]
    changed = session_store.transition_session_state(
        db,
        session.id,
        expected={"running"},
        target="waiting_for_device",
    )
    if changed:
        session_store.insert_session_event(
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
            current = broker.get_invocation(tool_call_id)
            if current["state"] in {
                "succeeded",
                "failed",
                "declined",
                "expired",
                "cancelled",
            }:
                return current
            await asyncio.sleep(0.25)
    except asyncio.CancelledError:
        try:
            broker.finish(
                invocation["device_id"],
                tool_call_id,
                status="cancelled",
                error="服务器 Session 已取消",
            )
        except ValueError:
            pass
        raise
    finally:
        restored = session_store.transition_session_state(
            db,
            session.id,
            expected={"waiting_for_device"},
            target="running",
        )
        if restored:
            session_store.insert_session_event(
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
        description="Android 已授权工作区内的相对目录",
    )
    max_entries: int = Field(default=200, ge=1, le=1_000)
    device_id: str = Field(
        default="",
        description="目标 device_id；留空时选择一个在线兼容设备",
    )
    expected_workspace_revision: int | None = Field(
        default=None,
        ge=0,
        description="可选的 Android 工作区 revision",
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
        "列出一台已配对且在线 Android 设备的授权工作区目录。"
        "适用：浏览手机端工作区结构、定位要读取或修改的文件；"
        "区别于 device.documents.list 的 SAF 授权目录。"
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
    path: str = Field(description="Android 已授权工作区内的相对文件路径")
    max_bytes: int = Field(default=262_144, ge=1, le=1_048_576)
    device_id: str = Field(
        default="",
        description="目标 device_id；留空时选择一个在线兼容设备",
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
        "读取一台已配对且在线 Android 设备授权工作区内的小文件，返回内容与 sha256。"
        "适用：查看手机端工作区文件；也是后续 apply_patch 修改前获取 sha256 的必经步骤。"
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
        description="要读取的公开配置字段；留空返回全部公开字段",
    )
    device_id: str = Field(
        default="",
        description="目标 device_id；留空时选择一个在线兼容设备",
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
        "读取一台已配对 Android 设备公开且不含密钥的运行配置。"
        "适用：查看设备 Runtime 配置与 config_revision；修改配置用 device.config.patch。"
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
    path: str = Field(description="Android 授权工作区内的相对文件路径")
    expected_sha256: str = Field(
        description="最近一次 device.workspace.read 返回的 sha256"
    )
    edits: list[DeviceTextEdit] = Field(
        min_length=1,
        max_length=100,
        description="审批前生成 diff 的精确文本替换",
    )
    device_id: str = Field(
        default="",
        description="目标 device_id；留空时选择一个在线兼容设备",
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
        "在 Android 本地显示候选 diff，经用户批准后原子修改授权工作区文本。"
        "适用：精确修改手机端工作区已有文件；"
        "必须先 device.workspace.read 读取最新 sha256，设备端拒绝或超时都会返回失败。"
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
            "仅允许 display_name 和 max_read_bytes；其余字段会被拒绝"
        )
    )
    expected_config_revision: int = Field(ge=1)
    device_id: str = Field(
        default="",
        description="目标 device_id；留空时选择一个在线兼容设备",
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
        "在 Android 本地显示旧值和新值，经用户批准后修改 Device Runtime 配置。"
        "适用：调整 display_name、max_read_bytes 等公开配置；"
        "需先 device.config.get 拿到当前 config_revision。"
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
        description="SAF 授权目录内的相对目录",
    )
    max_entries: int = Field(default=200, ge=1, le=1_000)
    device_id: str = Field(
        default="",
        description="目标 device_id；留空时选择一个在线兼容设备",
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
        "列出 Android 用户通过系统文档选择器持久授权的目录（SAF）。"
        "适用：浏览用户授权共享出来的文档目录；区别于 device.workspace.list 的应用工作区。"
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
        description="SAF 授权目录内的相对文件路径",
    )
    max_bytes: int = Field(default=262_144, ge=1, le=1_048_576)
    device_id: str = Field(
        default="",
        description="目标 device_id；留空时选择一个在线兼容设备",
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
        "读取 Android SAF 持久授权目录中的小文件；二进制以 base64 返回。"
        "适用：读取用户授权共享的文档；写入前必须先读本工具拿到最新 sha256。"
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
        description="SAF 授权目录内的现有文件路径",
    )
    expected_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9A-Fa-f]{64}$",
        description="最近一次 device.documents.read 返回的 sha256"
    )
    content: str = Field(
        max_length=1_398_104,
        description="审批后覆盖写入的 base64 内容，最大 1 MiB"
    )
    device_id: str = Field(
        default="",
        description="目标 device_id；留空时选择一个在线兼容设备",
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
        "在 Android 显示写入摘要并经用户批准后，按 sha256 前置条件覆盖"
        " SAF 授权目录中的现有文件。"
        "适用：更新用户共享文档的内容；必须先 device.documents.read 获取最新 sha256。"
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
        description="目标 device_id；留空时选择一个在线兼容设备",
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
        "经 Android 本地批准后打开系统文件选择器，并读取用户明确选择的小文件。"
        "适用：请用户在手机上手动挑一个文件交给 Agent（如照片、文档）；不能按路径读任意文件。"
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
        description="目标 device_id；留空时选择一个在线兼容设备",
    )


class DeviceCameraCapture(Tool):
    tool_id: str = "device-t-10"
    tool_name: str = "device.camera.capture"
    tool_description: str = (
        "经 Android 本地批准后打开系统相机，返回本次拍摄的 JPEG 缩略图。"
        "适用：请用户现场拍摄实物（如实验装置、样品、板书）交给 Agent 分析。"
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
        description="目标 device_id；留空时选择一个在线兼容设备",
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
        "在 Android 展示文本预览，经本地批准后打开系统分享面板；"
        "最终发送目标仍由用户选择。"
        "适用：把结果文本交给用户自行分享到微信、邮件等应用；Agent 不直接控制发送对象。"
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
        description="可选稳定 ID；相同 ID 会更新已有通知",
    )
    device_id: str = Field(
        default="",
        description="目标 device_id；留空时选择一个在线兼容设备",
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
        "在 Android 展示通知内容预览，经本地批准且系统通知权限允许后显示通知。"
        "适用：长任务完成或需要用户介入时在手机通知栏提醒用户；只发通知，不能获取用户回复。"
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
