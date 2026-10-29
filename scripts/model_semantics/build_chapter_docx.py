"""Build the standalone Chinese and English Results and Discussion chapters.

Use the Codex bundled Python. The Markdown files remain the prose authority;
the builder supplies typography, full-width figures and native heading styles.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Mm, Pt

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/Cloudra_论文当前稿/01_正文"
sys.path.insert(0, str(ROOT / "paper/word"))
from build_methods_docx import configure_document, fonts  # noqa: E402


def add_inline(paragraph, text: str):
    """Preserve prose while translating the small inline Markdown vocabulary."""
    position = 0
    while position < len(text):
        candidates = [(text.find(token, position), token) for token in ("**", "*", "`", "[")]
        candidates = [(start, token) for start, token in candidates if start >= 0]
        if not candidates:
            paragraph.add_run(text[position:])
            return
        start, token = min(candidates, key=lambda candidate: (candidate[0], -len(candidate[1])))
        paragraph.add_run(text[position:start])
        if token == "[":
            label_end = text.find("](", start + 1)
            link_end = text.find(")", label_end + 2) if label_end >= 0 else -1
            if label_end >= 0 and link_end >= 0:
                paragraph.add_run(text[start + 1:label_end])
                position = link_end + 1
                continue
        else:
            end = text.find(token, start + len(token))
            if end >= 0:
                run = paragraph.add_run(text[start + len(token):end])
                run.bold = token == "**"
                run.italic = token == "*"
                position = end + len(token)
                continue
        paragraph.add_run(token)
        position = start + len(token)


def blocks(source: str):
    """Read headings, standalone images and prose without changing their order."""
    for block in source.strip().split("\n\n"):
        text = block.strip()
        if not text or text.startswith("<!--"):
            continue
        first, _, rest = text.partition(" ")
        if first and set(first) == {"#"}:
            yield "heading", len(first), rest
        elif text.startswith("![") and "](" in text and text.endswith(")"):
            label, path = text[2:-1].split("](", 1)
            yield "image", label, path
        else:
            yield "paragraph", None, " ".join(text.splitlines())


def configure_chapter(doc):
    configure_document(doc)
    section = doc.sections[0]
    section._sectPr.find(qn("w:cols")).set(qn("w:num"), "1")
    fonts(doc.styles["Caption"], 8.5, east_asia="Songti SC")
    caption = doc.styles["Caption"].paragraph_format
    caption.first_line_indent = Mm(0)
    caption.line_spacing = Pt(10.5)
    caption.space_before, caption.space_after = Pt(0), Pt(7)
    caption.keep_together = True
    caption.keep_with_next = False


def build_chapter(language: str) -> Path:
    source = ROOT / "paper/sections" / (
        "03_benchmarks_and_results_zh.md" if language == "zh" else "03_benchmarks_and_results.md"
    )
    doc = Document()
    configure_chapter(doc)
    title_level = None
    first_paragraph = True
    awaiting_caption = False
    references = False
    title = ""
    for kind, detail, value in blocks(source.read_text(encoding="utf-8")):
        if kind == "heading":
            references = value in {
                "本节参考文献", "参考文献", "References", "References for this section"
            }
            if title_level is None:
                title_level, title = detail, value
                paragraph = doc.add_paragraph(value, style="Title")
                paragraph.paragraph_format.space_before = Pt(0)
                paragraph.paragraph_format.space_after = Pt(9)
            else:
                level = min(max(detail - title_level, 1), 2)
                doc.add_paragraph(value, style=f"Heading {level}")
            first_paragraph = True
        elif kind == "image":
            image = (source.parent / value).resolve()
            paragraph = doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            fmt = paragraph.paragraph_format
            fmt.first_line_indent = Mm(0)
            fmt.space_before, fmt.space_after = Pt(6), Pt(3)
            fmt.line_spacing = 1.0
            fmt.keep_with_next = True
            shape = paragraph.add_run().add_picture(str(image), width=Mm(170))
            shape._inline.docPr.set("descr", detail)
            awaiting_caption = True
        else:
            paragraph = doc.add_paragraph(style="Caption" if awaiting_caption else "Normal")
            paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if first_paragraph or awaiting_caption:
                paragraph.paragraph_format.first_line_indent = Mm(0)
            add_inline(paragraph, value)
            if references:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                fmt = paragraph.paragraph_format
                fmt.left_indent, fmt.first_line_indent = Mm(3.5), Mm(-3.5)
                fmt.line_spacing, fmt.space_after = Pt(10.5), Pt(4)
                for run in paragraph.runs:
                    run.font.size = Pt(8.5)
            if not awaiting_caption:
                first_paragraph = False
            awaiting_caption = False

    doc.core_properties.title = title
    doc.core_properties.author = "Cloudra Team"
    doc.core_properties.subject = "Cloudra Results and Discussion"
    doc.core_properties.language = "zh-CN" if language == "zh" else "en-US"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT / f"Cloudra_Results_and_Discussion_{language.upper()}.docx"
    doc.save(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("zh", "en", "both"), default="both")
    args = parser.parse_args()
    for language in (("zh", "en") if args.language == "both" else (args.language,)):
        print(build_chapter(language))


if __name__ == "__main__":
    main()
