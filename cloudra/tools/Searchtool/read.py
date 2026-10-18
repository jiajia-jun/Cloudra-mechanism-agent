import os
from pathlib import Path
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import WorkspaceError, resolve_existing_tool_path
from cloudra.tools.Searchtool._document import OFFICE_EXTS, read_pdf
from cloudra.tools.Searchtool._image import read_image
from cloudra.tools.Searchtool._text import IMAGE_EXTS, PDF_EXTS, read_text

description = (
    "Read a file in the Agent working directory: UTF-8 text, images (PNG/JPG/JPEG/WEBP), or PDFs. "
    "Use for: viewing code, logs, configs, papers, and local images. "
    "Do not use bash to read files. "
    "Read existing text you have not yet inspected before changing it. "
    "The runtime remembers versions from successful reads, writes and edits; a file you just wrote or edited needs no extra read. "
    "Page large text with offset/limit (1-based start line and line count)."
)


class Read_input_schema(input_schema):
    path: str = Field(description="File path. Relative paths resolve against the Agent working directory "
                                  "(falling back to the process cwd); absolute paths inside the working "
                                  "directory are accepted. Missing files report every candidate tried.")
    offset: int | None = Field(
        default=None,
        description="1-based start line; omit to start at the first line",
    )
    limit: int | None = Field(
        default=None,
        description="Number of lines to return; omit to read through EOF",
    )
    focus: str = Field(
        default="auto",
        description="Document focus: auto, text, or images (PDFs only)",
    )


class Read_output_schema(output_schema):
    is_success: bool = True
    path: str = ""
    kind: str = ""  # "text" | "image" | "document"
    content: str = ""
    sha256: str = ""
    total_lines: int = 0
    offset: int = 1          # 1-based actual start
    limit: int = 0           # lines actually returned; 0 means unused
    image_path: str = ""     # single image (also set when image_paths has one entry)
    image_paths: list[str] = Field(default_factory=list)  # visual injection list; no cap
    images: list[dict] = Field(default_factory=list)  # inventory: {path, page}
    message: str = ""


class Read(Tool):
    tool_id: str = "t-2"
    tool_name: str = "read"
    tool_description: str = description
    input_schema: Any = Read_input_schema
    output_schema: Any = Read_output_schema

    def is_read(self) -> bool:
        return True

    def _root(self) -> str:
        root = getattr(self.subagent, "working_directory", None)
        if not root:
            root = os.getcwd()
        return root

    def _fail(self, path: str, message: str) -> Read_output_schema:
        return Read_output_schema(is_success=False, path=path, message=message)

    async def tool_call(self, user_input: Read_input_schema, session: Session) -> Read_output_schema:
        path = user_input.path
        suffix = Path(path).suffix.lower()
        root = self._root()
        # 存在性兜底：相对路径同时试工作目录与进程 cwd，绝对路径原样；
        # 命中工作区外的候选不读取（read 保持工作区沙箱），但报错要说清它在哪。
        try:
            absolute = Path(resolve_existing_tool_path(self, path))
        except FileNotFoundError as exc:
            return self._fail(path, str(exc))
        try:
            path = absolute.relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return self._fail(
                path,
                f"File exists at {absolute} but is outside the working directory "
                f"{root}; move it into the working directory first.",
            )
        try:
            if suffix in IMAGE_EXTS:
                absolute = read_image(root, path)
                return Read_output_schema(
                    is_success=True,
                    path=path,
                    kind="image",
                    image_path=absolute,
                    image_paths=[absolute],
                    message=f"Image loaded: {absolute}.",
                )
            if suffix in PDF_EXTS:
                data = await read_pdf(
                    root, path, user_input.offset, user_input.limit, user_input.focus
                )
                return Read_output_schema(is_success=True, kind="document", **data)
            if suffix in OFFICE_EXTS:
                return self._fail(path, "Only PDF documents are supported.")
            data = await read_text(root, path, user_input.offset, user_input.limit)
            return Read_output_schema(is_success=True, kind="text", **data)
        except (OSError, WorkspaceError, ValueError) as exc:
            return self._fail(path, str(exc))
