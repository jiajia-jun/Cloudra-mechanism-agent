"""受工作区约束的文本文件读取、变更预览与原子写入。"""

from __future__ import annotations

import codecs
import difflib
import hashlib
import os
import stat
import tempfile
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024
MAX_DIFF_CHARS = 200_000


def resolve_working_directory(value: str | None = None) -> str:
    """把工作目录收成绝对路径；缺省用当前进程 cwd。

    隔离 TUI 的 runtime 进程 cwd 可能与用户启动目录不同。客户端应传入
    自己的目录，而不是让 runtime 用 getcwd 兜底。
    """
    raw = (value or "").strip() or os.getcwd()
    return str(Path(raw).expanduser().resolve())


def resolve_tool_path(tool: Any, value: str) -> str:
    """把工具收到的文件路径参数统一到 agent 工作目录语义。

    绝对路径原样保留（科研节点上的显式访问是既有权限语义，不擅自收紧）；
    相对路径解析到绑定 agent 的 working_directory（per-project 沙箱），
    与 read/write/bash 的既有契约一致——修复相对路径落到进程 cwd 串目录
    的缺陷（C1：qm_input_writer/submit_compute_job 未走此原语）。仅在没有
    agent 桥（直接 CLI/单测调用）时回退进程 cwd。

    只对“文件路径字段”调用本函数；SMILES、文件名透传串等非路径语义由
    调用方自行甄别，禁止混用。
    """
    raw = (value or "").strip()
    if not raw:
        return value or ""
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    subagent = getattr(tool, "subagent", None)
    root = getattr(subagent, "working_directory", None) or os.getcwd()
    return str((Path(root) / p).resolve())


def resolve_existing_tool_path(tool: Any, value: str) -> str:
    """输入文件路径的存在性兜底解析（只用于“必须已存在”的输入路径字段）。

    候选按序展开为绝对路径：
    1. value 本身是绝对路径 → 唯一候选（保持既有绝对路径权限语义）
    2. agent 工作目录 / value —— resolve_tool_path 的既有语义，优先
    3. 进程 cwd / value       —— agent 从引擎日志/输出抄来的相对路径常相对它

    返回第一个存在的候选；两个候选都存在时取工作目录版（既有语义优先）。
    都不存在抛 FileNotFoundError，消息列出全部尝试过的候选，让 agent 一次
    说清“哪里没有这个文件”，不再盲目换基准目录重试。
    """
    raw = (value or "").strip()
    p = Path(raw)
    subagent = getattr(tool, "subagent", None)
    root = getattr(subagent, "working_directory", None) or os.getcwd()
    if p.is_absolute():
        candidates = [str(p)]
    else:
        candidates = [
            str((Path(root) / p).resolve()),
            str((Path(os.getcwd()) / p).resolve()),
        ]
    candidates = list(dict.fromkeys(candidates))
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    tried = "\n".join(f"  - {c}" for c in candidates)

    suggestions: list[str] = []
    seen_dirs: set[Path] = set()
    for candidate in candidates:
        cand_path = Path(candidate)
        parent_dir = cand_path.parent
        if parent_dir not in seen_dirs and parent_dir.is_dir():
            seen_dirs.add(parent_dir)
            try:
                dir_files = [f.name for f in parent_dir.iterdir() if f.is_file()]
                matches = difflib.get_close_matches(cand_path.name, dir_files, n=3, cutoff=0.4)
                for m in matches:
                    matched_file = str(parent_dir / m)
                    if matched_file not in suggestions:
                        suggestions.append(matched_file)
            except OSError:
                pass

    sugg_text = ""
    if suggestions:
        sugg_text = "\nDid you mean:\n" + "\n".join(f"  - {s}" for s in suggestions)
    raise FileNotFoundError(f"File not found: {raw!r}. Tried:\n{tried}{sugg_text}")


class WorkspaceError(ValueError):
    """工作区操作不满足路径、文本或编辑约束。"""


class WorkspaceConflictError(WorkspaceError):
    """文件状态与 Agent 读取时不一致，需要重新读取。"""


@dataclass(frozen=True)
class TextEdit:
    old_text: str
    new_text: str
    replace_all: bool = False


@dataclass(frozen=True)
class TextSnapshot:
    relative_path: str
    absolute_path: Path
    content: str
    sha256: str
    mode: int
    newline: str
    has_utf8_bom: bool


@dataclass(frozen=True)
class PreparedFileChange:
    change_id: str
    root: Path
    relative_path: str
    absolute_path: Path
    kind: str
    before_content: str | None
    after_content: str
    before_sha256: str | None
    after_sha256: str
    before_mode: int | None
    newline: str
    has_utf8_bom: bool
    diff: str
    additions: int
    deletions: int

    def event_data(self, status: str, message: str = "") -> dict:
        return {
            "change_id": self.change_id,
            "path": self.relative_path,
            "kind": self.kind,
            "status": status,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "additions": self.additions,
            "deletions": self.deletions,
            "diff": self.diff,
            "message": message,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _newline_style(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def _normalize_newlines(text: str, newline: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)


def _has_final_newline(text: str) -> bool:
    return text.endswith(("\n", "\r"))


def _preserve_final_newline(text: str, had_final_newline: bool, newline: str) -> str:
    has_final_newline = _has_final_newline(text)
    if had_final_newline and not has_final_newline:
        return text + newline
    if not had_final_newline and has_final_newline:
        if text.endswith("\r\n"):
            return text[:-2]
        return text[:-1]
    return text


def _encode_text(text: str, has_utf8_bom: bool) -> bytes:
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise WorkspaceError("Text contains characters that cannot be encoded as UTF-8") from exc
    return codecs.BOM_UTF8 + encoded if has_utf8_bom else encoded


def _unified_diff(relative_path: str, before: str | None, after: str) -> str:
    before_lines = [] if before is None else before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    from_file = "/dev/null" if before is None else f"a/{relative_path}"
    diff_lines = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=from_file,
        tofile=f"b/{relative_path}",
    )
    diff = "".join(
        line if line.endswith(("\n", "\r")) else line + "\n"
        for line in diff_lines
    )
    return diff


def _diff_counts(diff: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return additions, deletions


class WorkspaceService:
    """把所有文本文件变更限制在单一工作目录内。"""

    def __init__(self, root: str | os.PathLike[str], max_file_bytes: int = MAX_TEXT_FILE_BYTES):
        root_path = Path(root).expanduser().resolve()
        if not root_path.is_dir():
            raise WorkspaceError(f"Working directory does not exist or is not a directory: {root_path}")
        self.root = root_path
        self.max_file_bytes = max_file_bytes

    def resolve_path(self, relative_path: str) -> Path:
        if not relative_path or "\x00" in relative_path:
            raise WorkspaceError("File path must not be empty or contain NUL characters")
        requested = Path(relative_path)
        if requested.is_absolute():
            raise WorkspaceError("File tools only accept paths relative to the working directory")

        unresolved = self.root / requested
        current = self.root
        for part in requested.parts:
            if part in ("", "."):
                continue
            current = current / part
            if current.exists() and current.is_symlink():
                raise WorkspaceError(f"Modifying files through a symlink is not allowed: {relative_path}")

        resolved = unresolved.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceError(f"Path escapes the working directory: {relative_path}") from exc
        if resolved == self.root:
            raise WorkspaceError("Target must be a file inside the working directory")
        return resolved

    def _relative_label(self, absolute_path: Path) -> str:
        return absolute_path.relative_to(self.root).as_posix()

    def snapshot(self, relative_path: str) -> TextSnapshot:
        absolute_path = self.resolve_path(relative_path)
        if not absolute_path.exists():
            raise WorkspaceError(f"File does not exist: {relative_path}")
        if not absolute_path.is_file():
            raise WorkspaceError(f"Target is not a regular file: {relative_path}")

        raw = absolute_path.read_bytes()
        if len(raw) > self.max_file_bytes:
            raise WorkspaceError(
                f"File is too large to edit as text ({len(raw)} > {self.max_file_bytes} bytes)"
            )
        has_utf8_bom = raw.startswith(codecs.BOM_UTF8)
        body = raw[len(codecs.BOM_UTF8):] if has_utf8_bom else raw
        if b"\x00" in body:
            raise WorkspaceError(f"Target looks like a binary file: {relative_path}")
        try:
            content = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceError(f"File is not valid UTF-8 text: {relative_path}") from exc

        return TextSnapshot(
            relative_path=self._relative_label(absolute_path),
            absolute_path=absolute_path,
            content=content,
            sha256=_sha256(raw),
            mode=stat.S_IMODE(absolute_path.stat().st_mode),
            newline=_newline_style(content),
            has_utf8_bom=has_utf8_bom,
        )

    def read_text(
        self,
        relative_path: str,
        start_line: int = 0,
        end_line: int = -1,
    ) -> tuple[TextSnapshot, str, int, int, int]:
        snapshot = self.snapshot(relative_path)
        lines = snapshot.content.splitlines(keepends=True)
        total_lines = len(lines)
        actual_start = min(max(start_line, 0), total_lines)
        actual_end = total_lines if end_line == -1 else min(max(end_line, 0), total_lines)
        if actual_start > actual_end:
            raise WorkspaceError(f"Invalid slice range: [{actual_start}:{actual_end}]")
        return snapshot, "".join(lines[actual_start:actual_end]), total_lines, actual_start, actual_end

    def prepare_edit(
        self,
        relative_path: str,
        expected_sha256: str,
        edits: Sequence[TextEdit],
    ) -> PreparedFileChange:
        if not edits:
            raise WorkspaceError("At least one text edit is required")
        snapshot = self.snapshot(relative_path)
        if expected_sha256 != snapshot.sha256:
            raise WorkspaceConflictError(
                f"File has changed; re-read before editing. Current sha256={snapshot.sha256}"
            )

        content = snapshot.content
        had_final_newline = _has_final_newline(content)
        for edit in edits:
            old_text = _normalize_newlines(edit.old_text, snapshot.newline)
            new_text = _normalize_newlines(edit.new_text, snapshot.newline)
            if not old_text:
                raise WorkspaceError("old_text must not be empty")
            matches = content.count(old_text)
            if matches == 0:
                raise WorkspaceConflictError("old_text did not match; re-read the target file")
            if not edit.replace_all and matches != 1:
                raise WorkspaceConflictError(
                    f"old_text matched {matches} times; provide more precise context or set replace_all"
                )
            content = content.replace(old_text, new_text, -1 if edit.replace_all else 1)

        content = _preserve_final_newline(content, had_final_newline, snapshot.newline)
        return self._prepare_change(snapshot, content)

    def prepare_write(
        self,
        relative_path: str,
        content: str,
        expected_sha256: str,
    ) -> PreparedFileChange:
        absolute_path = self.resolve_path(relative_path)
        if absolute_path.exists():
            snapshot = self.snapshot(relative_path)
            if expected_sha256 == "missing":
                raise WorkspaceConflictError(
                    "File already exists; read it before overwriting."
                )
            if expected_sha256 != snapshot.sha256:
                raise WorkspaceConflictError(
                    f"File has changed; re-read before overwriting. Current sha256={snapshot.sha256}"
                )
            normalized = _normalize_newlines(content, snapshot.newline)
            normalized = _preserve_final_newline(
                normalized,
                _has_final_newline(snapshot.content),
                snapshot.newline,
            )
            return self._prepare_change(snapshot, normalized)

        if expected_sha256 != "missing":
            raise WorkspaceConflictError(
                "File was removed after it was read; inspect the target before creating it again."
            )
        normalized = _normalize_newlines(content, "\n")
        after_bytes = _encode_text(normalized, False)
        self._check_output_size(after_bytes)
        diff = _unified_diff(self._relative_label(absolute_path), None, normalized)
        additions, deletions = _diff_counts(diff)
        return PreparedFileChange(
            change_id=uuid4().hex,
            root=self.root,
            relative_path=self._relative_label(absolute_path),
            absolute_path=absolute_path,
            kind="add",
            before_content=None,
            after_content=normalized,
            before_sha256=None,
            after_sha256=_sha256(after_bytes),
            before_mode=None,
            newline="\n",
            has_utf8_bom=False,
            diff=diff,
            additions=additions,
            deletions=deletions,
        )

    def _prepare_change(
        self,
        snapshot: TextSnapshot,
        after_content: str,
    ) -> PreparedFileChange:
        if after_content == snapshot.content:
            raise WorkspaceError("The edit produced no changes")
        after_bytes = _encode_text(after_content, snapshot.has_utf8_bom)
        self._check_output_size(after_bytes)
        diff = _unified_diff(snapshot.relative_path, snapshot.content, after_content)
        additions, deletions = _diff_counts(diff)
        return PreparedFileChange(
            change_id=uuid4().hex,
            root=self.root,
            relative_path=snapshot.relative_path,
            absolute_path=snapshot.absolute_path,
            kind="update",
            before_content=snapshot.content,
            after_content=after_content,
            before_sha256=snapshot.sha256,
            after_sha256=_sha256(after_bytes),
            before_mode=snapshot.mode,
            newline=snapshot.newline,
            has_utf8_bom=snapshot.has_utf8_bom,
            diff=diff,
            additions=additions,
            deletions=deletions,
        )

    def _check_output_size(self, payload: bytes) -> None:
        if len(payload) > self.max_file_bytes:
            raise WorkspaceError(
                f"Edit result is too large to write ({len(payload)} > {self.max_file_bytes} bytes)"
            )

    def _assert_precondition(self, change: PreparedFileChange) -> None:
        if change.before_sha256 is None:
            if change.absolute_path.exists():
                raise WorkspaceConflictError("File was created during approval; re-read it")
            return

        current = self.snapshot(change.relative_path)
        if current.sha256 != change.before_sha256:
            raise WorkspaceConflictError(
                f"File changed during approval; current sha256={current.sha256}"
            )

    def apply(self, change: PreparedFileChange) -> None:
        if change.root != self.root:
            raise WorkspaceError("Change does not belong to the current working directory")
        absolute_path = self.resolve_path(change.relative_path)
        if absolute_path != change.absolute_path:
            raise WorkspaceConflictError("Target path changed during approval")

        self._assert_precondition(change)

        parent = absolute_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        try:
            parent.resolve().relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceConflictError("Parent directory escaped the workspace during approval") from exc

        payload = _encode_text(change.after_content, change.has_utf8_bom)
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".cloudra-edit-",
                dir=parent,
                delete=False,
            ) as temp_file:
                temp_path = temp_file.name
                temp_file.write(payload)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.chmod(temp_path, change.before_mode if change.before_mode is not None else 0o644)
            # 临时文件写入可能耗时；替换前再检查一次，缩小覆盖并发用户编辑的窗口。
            self._assert_precondition(change)
            os.replace(temp_path, absolute_path)
            temp_path = None
            if hasattr(os, "O_DIRECTORY"):
                try:
                    directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                except OSError:
                    # 替换本身已经完成；部分文件系统不支持目录 fsync。
                    pass
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass


class TurnDiffTracker:
    """按 Session 保存首次触碰快照，并生成不混入用户旧改动的聚合 diff。"""

    def __init__(self, max_sessions: int = 128):
        self.max_sessions = max_sessions
        self._lock = threading.Lock()
        self._bases: OrderedDict[tuple[str, str], dict[str, str | None]] = OrderedDict()

    def record_applied(
        self,
        session_key: str,
        service: WorkspaceService,
        change: PreparedFileChange,
    ) -> str:
        key = (str(service.root), session_key)
        with self._lock:
            if key not in self._bases and len(self._bases) >= self.max_sessions:
                self._bases.popitem(last=False)
            bases = self._bases.setdefault(key, {})
            bases.setdefault(change.relative_path, change.before_content)
            self._bases.move_to_end(key)
            snapshot_bases = dict(bases)

        parts: list[str] = []
        for relative_path, before_content in sorted(snapshot_bases.items()):
            try:
                current_content = service.snapshot(relative_path).content
            except WorkspaceError:
                current_content = ""
            diff = _unified_diff(relative_path, before_content, current_content)
            if diff:
                parts.append(diff)
        aggregate = "".join(parts)
        if len(aggregate) > MAX_DIFF_CHARS:
            return aggregate[:MAX_DIFF_CHARS] + "\n... this-turn diff truncated ...\n"
        return aggregate


turn_diff_tracker = TurnDiffTracker()
