"""PDF extract + scan render + extract cache for `read`."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cloudra.persistence.workspace import WorkspaceError, WorkspaceService
from cloudra.tools.core.observation_offload import cap_observation
from cloudra.tools.Searchtool._text import offset_limit_to_slice

try:
    import fitz

    _PYMUPDF_AVAILABLE = True
except Exception:
    fitz = None
    _PYMUPDF_AVAILABLE = False

SCAN_TOTAL_CHAR_THRESHOLD = 200
SCAN_AVG_CHAR_THRESHOLD = 50
OFFICE_EXTS = {
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".odt",
    ".ods",
    ".odp",
    ".rtf",
    ".epub",
}
_META_NAME = "meta.json"
_CONTENT_NAME = "content.md"


@dataclass
class ExtractResult:
    text: str
    images: list[dict]
    chars_per_page: list[int]


def is_scan(chars_per_page: list[int]) -> bool:
    pages = len(chars_per_page)
    if pages == 0:
        return True
    total = sum(chars_per_page)
    return total < SCAN_TOTAL_CHAR_THRESHOLD or (total / pages) < SCAN_AVG_CHAR_THRESHOLD


def extract_pdf(source: Path, cache_dir: Path) -> ExtractResult:
    cache_dir.mkdir(parents=True, exist_ok=True)
    content_path = cache_dir / _CONTENT_NAME
    meta_path = cache_dir / _META_NAME
    if content_path.is_file() and meta_path.is_file():
        return _load_extract_cache(cache_dir)
    if not _PYMUPDF_AVAILABLE:
        raise WorkspaceError(
            "PyMuPDF is not installed. Install it with: pip install 'cloudra[pdf]'."
        )
    images_dir = cache_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    result = _convert_sync(source, images_dir)
    meta_path.write_text(
        json.dumps(
            {
                "chars_per_page": result.chars_per_page,
                "images": [
                    {
                        "path": str(Path(img["path"]).relative_to(cache_dir)),
                        "page": img["page"],
                    }
                    for img in result.images
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    content_path.write_text(result.text, encoding="utf-8")
    return result


def render_pages(source: Path, cache_dir: Path) -> list[str]:
    if not _PYMUPDF_AVAILABLE:
        raise WorkspaceError(
            "PyMuPDF is not installed. Install it with: pip install 'cloudra[pdf]'."
        )
    cache_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = cache_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(source))
    try:
        page_count = len(doc)
        expected = [pages_dir / f"page_{i}.png" for i in range(1, page_count + 1)]
        if expected and all(path.is_file() for path in expected):
            return [str(path) for path in expected]
        paths: list[str] = []
        for page_num in range(page_count):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_path = pages_dir / f"page_{page_num + 1}.png"
            pix.save(str(img_path))
            paths.append(str(img_path))
        return paths
    finally:
        doc.close()


def _load_extract_cache(cache_dir: Path) -> ExtractResult:
    text = (cache_dir / _CONTENT_NAME).read_text(encoding="utf-8")
    meta = json.loads((cache_dir / _META_NAME).read_text(encoding="utf-8"))
    images = [
        {"path": str((cache_dir / item["path"]).resolve()), "page": int(item["page"])}
        for item in meta.get("images", [])
    ]
    chars_per_page = [int(n) for n in meta.get("chars_per_page", [])]
    return ExtractResult(text=text, images=images, chars_per_page=chars_per_page)


def _convert_sync(source: Path, images_dir: Path) -> ExtractResult:
    doc = fitz.open(str(source))
    md_lines: list[str] = []
    images: list[dict] = []
    chars_per_page: list[int] = []
    image_counter = 0
    seen_image_xrefs: set[int] = set()
    try:
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            md_lines.append(f"\n## 第 {page_num + 1} 页\n")
            page_chars = 0
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (b[1], b[0]))
            for block in blocks:
                _x0, _y0, _x1, _y1, text, _block_no, block_type = block[:7]
                if block_type != 0 or not text.strip():
                    continue
                paragraph = text.strip().replace("\n", " ")
                if paragraph:
                    md_lines.append(f"{paragraph}\n")
                    page_chars += len(paragraph)
            chars_per_page.append(page_chars)

            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen_image_xrefs:
                    continue
                seen_image_xrefs.add(xref)
                try:
                    base_image = doc.extract_image(xref)
                    image_counter += 1
                    image_filename = f"image_{image_counter:04d}.{base_image['ext']}"
                    image_path = images_dir / image_filename
                    with open(image_path, "wb") as handle:
                        handle.write(base_image["image"])
                    md_lines.append(f"\n![image_{image_counter}](images/{image_filename})\n")
                    images.append({"path": str(image_path.resolve()), "page": page_num + 1})
                except Exception as exc:
                    md_lines.append(f"\n<!-- 图片提取失败: {exc} -->\n")
    finally:
        doc.close()
    return ExtractResult(
        text="\n".join(md_lines),
        images=images,
        chars_per_page=chars_per_page,
    )


def _apply_focus(
    source: Path,
    cache_dir: Path,
    extracted: ExtractResult,
    focus: str,
) -> tuple[str, list[dict], list[str], str]:
    kind = (focus or "auto").strip().lower()
    if kind not in {"auto", "text", "images"}:
        raise ValueError("focus must be auto, text, or images")
    scan = is_scan(extracted.chars_per_page)
    if kind == "text":
        message = ""
        if scan:
            message = (
                "No text layer in this PDF (scanned pages). "
                "Use focus=auto or focus=images to render pages."
            )
        return extracted.text, [], [], message
    if kind == "images":
        if scan or not extracted.images:
            rendered = render_pages(source, cache_dir)
            inventory = [{"path": p, "page": i} for i, p in enumerate(rendered, start=1)]
            return "", inventory, rendered, ""
        paths = [str(img["path"]) for img in extracted.images]
        return "", list(extracted.images), paths, ""
    if scan:
        rendered = render_pages(source, cache_dir)
        inventory = [{"path": p, "page": i} for i, p in enumerate(rendered, start=1)]
        return extracted.text, inventory, rendered, ""
    return extracted.text, list(extracted.images), [], ""


def _slice_markdown(text: str, offset: int | None, limit: int | None) -> tuple[str, int, int, int]:
    lines = text.splitlines(keepends=True)
    total = len(lines)
    start_0, end_0 = offset_limit_to_slice(offset, limit)
    actual_start = min(max(start_0, 0), total)
    actual_end = total if end_0 == -1 else min(max(end_0, 0), total)
    if actual_start > actual_end:
        raise WorkspaceError(f"Invalid slice range: [{actual_start}:{actual_end}]")
    return "".join(lines[actual_start:actual_end]), total, actual_start, actual_end


def _read_pdf_sync(
    root: str,
    absolute: Path,
    focus: str,
) -> tuple[str, list[dict], list[str], str, str]:
    digest = hashlib.sha256(absolute.read_bytes()).hexdigest()
    cache_dir = Path(root) / ".cloudra" / "extract" / digest[:16]
    extracted = extract_pdf(absolute, cache_dir)
    content, images, image_paths, message = _apply_focus(absolute, cache_dir, extracted, focus)
    return content, images, image_paths, message, digest


async def read_pdf(
    root: str,
    path: str,
    offset: int | None,
    limit: int | None,
    focus: str,
) -> dict:
    if not _PYMUPDF_AVAILABLE:
        raise WorkspaceError(
            "PyMuPDF is not installed. Install it with: pip install 'cloudra[pdf]'."
        )
    service = WorkspaceService(root)
    absolute = service.resolve_path(path)
    if not absolute.is_file():
        raise WorkspaceError(f"File does not exist: {path}")
    content, images, image_paths, message, digest = await asyncio.to_thread(
        _read_pdf_sync, root, absolute, focus
    )
    sliced, total, actual_start, actual_end = _slice_markdown(content, offset, limit)
    capped = await cap_observation(sliced, root=root, stem="read")
    if capped != sliced:
        offload = "Full output at .cloudra/tool_output/; page with `read` `offset`/`limit`."
        message = f"{message} {offload}".strip() if message else offload
    return {
        "path": path,
        "content": capped,
        "sha256": digest,
        "total_lines": total,
        "offset": actual_start + 1,
        "limit": actual_end - actual_start,
        "image_path": image_paths[0] if image_paths else "",
        "image_paths": image_paths,
        "images": images,
        "message": message,
    }
