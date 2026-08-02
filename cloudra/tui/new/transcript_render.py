"""Pure Rich compilation for virtualized transcript records.

The compiler deliberately owns only derived rows.  ``TranscriptStore`` remains
the durable source of every complete record; callers may discard compiled rows
whenever a width or record revision changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rich.console import Console, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.segment import Segment
from rich.syntax import Syntax
from rich.text import Text
from textual.strip import Strip

from cloudra.tool_presentation import format_tool_payload
from cloudra.tui.new.transcript import RecordKind, TranscriptRecord


_TOOL_COLLAPSE_LINES = 8
_STREAM_CONTENT_WINDOW = 2_000
_STREAM_REASONING_WINDOW = 800
_ROW_BLOCK_SIZE = 128


class InteractionAction(StrEnum):
    TOGGLE_TOOL = "toggle_tool"
    COPY_CODE = "copy_code"


@dataclass(frozen=True, slots=True)
class InteractionRegion:
    action: InteractionAction
    x: int
    y: int
    width: int
    height: int
    payload: str = ""


@dataclass(frozen=True, slots=True)
class RenderContext:
    console: Console

    def for_worker(self) -> "RenderContext":
        """Make an isolated console suitable for off-thread compilation."""
        return RenderContext(
            Console(
                width=self.console.width,
                force_terminal=True,
                color_system=self.console.color_system,
                legacy_windows=False,
            )
        )


@dataclass(frozen=True, slots=True)
class CompiledRecord:
    record_id: int
    revision: int
    width: int
    blocks: tuple[tuple[Strip, ...], ...]
    regions: tuple[InteractionRegion, ...] = ()

    @property
    def strips(self) -> tuple[Strip, ...]:
        return tuple(strip for block in self.blocks for strip in block)

    def row(self, index: int) -> Strip:
        block, offset = divmod(index, _ROW_BLOCK_SIZE)
        return self.blocks[block][offset]


def render_rows(
    renderable: RenderableType, width: int, context: RenderContext
) -> tuple[Strip, ...]:
    """Render one Rich renderable into fixed-width immutable Textual rows."""
    options = context.console.options.update_width(width)
    lines = list(Segment.split_lines(context.console.render(renderable, options)))
    strips = Strip.from_lines(lines)
    return tuple(strip.crop_extend(0, width, None) for strip in strips) or (Strip.blank(width),)


def compile_record(
    record: TranscriptRecord, width: int, context: RenderContext
) -> CompiledRecord:
    """Compile one complete record without mutating it or retaining its history."""
    if width < 1:
        raise ValueError("width must be positive")

    rendered: list[Strip] = []
    regions: list[InteractionRegion] = []

    def append(renderable: RenderableType) -> int:
        start = len(rendered)
        rendered.extend(render_rows(renderable, width, context))
        return start

    if record.kind is RecordKind.SYSTEM:
        append(Panel(record.content, border_style="blue", title="系统"))
    elif record.kind is RecordKind.USER:
        style = "bold green"
        if record.send_failed:
            style = "bold green dim strike"
        append(Text(f"» {record.content}", style=style))
    elif record.kind is RecordKind.DIVIDER:
        append(Text(record.content, style="bright_black"))
    elif record.kind is RecordKind.ALERT:
        body = format_tool_payload(record.content) if record.content else record.title
        if record.content:
            append(Panel(Text(body), title=record.title, border_style=record.status or "red"))
        else:
            append(Panel(record.title, border_style=record.status or "red"))
    elif record.kind is RecordKind.ASSISTANT:
        _compile_assistant(record, append, rendered, regions, width)
    elif record.kind is RecordKind.TOOL:
        _compile_tool(record, append, rendered, regions, width)
    elif record.kind is RecordKind.FILE_CHANGE:
        _compile_file_change(record, append)
    elif record.kind is RecordKind.SUPERVISOR:
        append(
            Panel(
                f"结论: {record.status}\n理由: {record.content}",
                title="Supervisor 审查",
                border_style="magenta",
            )
        )
    else:  # Defensive fallback for records introduced after this compiler.
        append(Text(record.content))

    blocks = tuple(
        tuple(rendered[start : start + _ROW_BLOCK_SIZE])
        for start in range(0, len(rendered), _ROW_BLOCK_SIZE)
    )
    return CompiledRecord(record.record_id, record.revision, width, blocks, tuple(regions))


def semantic_segments(
    compiled: CompiledRecord,
) -> tuple[tuple[tuple[str, str], ...], ...]:
    """Return stable text/style pairs for fixture-oriented semantic comparison."""
    return tuple(
        tuple((segment.text, str(segment.style or "")) for segment in strip if segment.text)
        for strip in compiled.strips
    )


def _compile_assistant(
    record: TranscriptRecord,
    append,
    rendered: list[Strip],
    regions: list[InteractionRegion],
    width: int,
) -> None:
    if record.status == "streaming":
        reasoning, reasoning_clipped = _tail(record.reasoning, _STREAM_REASONING_WINDOW)
        content, content_clipped = _tail(record.content, _STREAM_CONTENT_WINDOW)
        streaming = Text()
        if reasoning:
            if reasoning_clipped:
                streaming.append("… 较早的思考过程已暂时折叠 …\n", style="bright_black")
            streaming.append(f"[思考] {reasoning}\n", style="bright_black italic")
        if content_clipped:
            streaming.append("… 正在生成，仅显示末尾 …\n", style="bright_black")
        streaming.append(content)
        append(streaming)
        return

    if record.reasoning:
        append(
            Panel(
                Text(record.reasoning, style="bright_black italic"),
                title="思考过程",
                border_style="bright_black",
            )
        )
    _compile_message(record.content, append, rendered, regions, width)


def _compile_message(
    content: str,
    append,
    rendered: list[Strip],
    regions: list[InteractionRegion],
    width: int,
) -> None:
    stripped = content.strip()
    if stripped and stripped[0] in ("{", "["):
        formatted = format_tool_payload(stripped)
        if formatted != stripped:
            append(Text(formatted))
            return
    if "```" not in content:
        append(Markdown(content) if _looks_like_markdown(content) else Text(content))
        return

    for index, part in enumerate(content.split("```")):
        if not part.strip():
            continue
        if index % 2 == 0:
            append(Markdown(part) if _looks_like_markdown(part) else Text(part))
            continue
        language, separator, code = part.partition("\n")
        code = (code if separator else "").rstrip("`").rstrip()
        append(
            Panel(Syntax(code, language.strip() or "text", theme="monokai", word_wrap=True), title=language.strip() or "code")
        )
        # The virtual surface has no Button widget.  Place its primary-coloured
        # label in the old right-side affordance area and expose an exact hit box.
        label_y = len(rendered)
        append(Text("复制", style="bold white on #0178D4", justify="right"))
        regions.append(
            InteractionRegion(
                InteractionAction.COPY_CODE,
                max(0, width - 4),
                label_y,
                min(4, width),
                1,
                code,
            )
        )


def _compile_tool(
    record: TranscriptRecord,
    append,
    rendered: list[Strip],
    regions: list[InteractionRegion],
    width: int,
) -> None:
    arguments = format_tool_payload(record.arguments)
    body = f"{record.tool_name}({arguments})"
    collapsible = False
    if record.status == "finished" and record.result is not None:
        result = format_tool_payload(record.result, is_result=True)
        full_body = f"{body}\n\n{result}"
        result_lines = result.splitlines()
        collapsible = len(result_lines) > _TOOL_COLLAPSE_LINES
        # Older records decide ``collapsed`` from raw line breaks.  A nested
        # JSON result can gain lines only after presentation formatting, so it
        # still needs the default collapsed view unless an already-long raw
        # record was explicitly expanded by the user.
        show_collapsed = record.collapsed or (
            len(record.result.splitlines()) <= _TOOL_COLLAPSE_LINES and collapsible
        )
        if show_collapsed:
            preview = "\n".join(result_lines[:_TOOL_COLLAPSE_LINES])
            body = f"{body}\n\n{preview}\n… 共 {len(result_lines)} 行，点击展开/收起"
        else:
            body = full_body

    finished = record.status == "finished"
    start = len(rendered)
    append(
        Panel(
            Text(body),
            title=f"{'√' if finished else '▶'} {record.tool_name}",
            border_style="green" if finished else "yellow",
        )
    )
    if collapsible:
        regions.append(
            InteractionRegion(
                InteractionAction.TOGGLE_TOOL,
                0,
                start,
                width,
                len(rendered) - start,
                str(record.record_id),
            )
        )


def _compile_file_change(record: TranscriptRecord, append) -> None:
    style = {
        "applied": "green",
        "proposed": "yellow",
        "declined": "dim",
        "failed": "red",
    }.get(record.status, "blue")
    icon = {
        "applied": "√",
        "proposed": "※",
        "declined": "○",
        "failed": "×",
    }.get(record.status, "•")
    body = record.content
    if not body or body == record.status:
        body = f"状态: {record.status}"
    append(Panel(body, title=f"{icon} {record.title}", border_style=style))


def _tail(text: str, limit: int) -> tuple[str, bool]:
    """Return a bounded trailing view without applying stream clipping to finals."""
    return text[-limit:], len(text) > limit


def _looks_like_markdown(text: str) -> bool:
    return any(marker in text for marker in ("#", "```", "- ", "* ", "> ", "| ", "[", "**", "__"))
