# Tool surface native corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge overlapping I/O and search tools into `read` / `search`, and rename the remaining high-frequency wire names so they match model-native verbs (`bash`, `write`, `edit`, `get_skill`, `web_fetch`, `browser`, `subagent_launcher`, `subagent_swarm`).

**Architecture:** New surface Tool classes dispatch to private implementation modules. Old Tool classes and registry wire names are deleted in the same commit as their replacement. Unknown old names get a hint string only — they are never executed. Native provider `web_search` in `llm_client.py` is untouched; when native search is on, the `search` function schema drops `web` from `source` instead of hiding the whole tool.

**Tech Stack:** Existing Cloudra tools (`cloudra.base.tools_class.Tool`), PyMuPDF (`fitz`) for PDF, pydantic v2 schemas, pytest, runtime_v2 adapters.

**Spec:** `docs/superpowers/specs/2026-09-03-tool-surface-native-corpus-design.md`

## File map

**Create**
- `cloudra/tools/name_hints.py` — retired-name → hint string
- `cloudra/tools/core/observation_offload.py` — huge observation → `.cloudra/tool_output/` (shared by `read` and later `bash`)
- `cloudra/tools/Searchtool/read.py` — `read` surface
- `cloudra/tools/Searchtool/_text.py` — UTF-8 workspace text slice
- `cloudra/tools/Searchtool/_image.py` — png/jpg/jpeg/webp
- `cloudra/tools/Searchtool/_document.py` — PDF extract + scan render + extract cache
- `cloudra/tools/Searchtool/search.py` — `search` surface
- `cloudra/tools/Searchtool/_web.py` — current `web_search.py` backends, no Tool class
- `cloudra/tools/Searchtool/_arxiv.py` — current arXiv fetch, no Tool class
- `cloudra/tools/Searchtool/_openalex.py` — current OpenAlex fetch, no Tool class
- `cloudra/tools/Bashtool/bash.py` — moved from `bashtools.py`
- `cloudra/tools/Writetool/write.py` — moved from `text_writer.py`
- `cloudra/tools/Writetool/edit.py` — moved from `edit_file.py`
- `cloudra/tools/Browsertool/web_fetch.py` — moved from `web_fetcher.py`
- `cloudra/tools/Browsertool/browser.py` — moved from `headless_browser.py`
- `tests/test_tool_name_hints.py`
- `tests/test_read.py`
- `tests/test_search.py`

**Delete** (after the replacement commit that removes them from `registry.py`)
- `cloudra/tools/Searchtool/text_reader.py`
- `cloudra/tools/Searchtool/image_reader.py`
- `cloudra/tools/Searchtool/pdf2md.py`
- `cloudra/tools/Searchtool/pdf2image.py`
- `cloudra/tools/Searchtool/web_search.py`
- `cloudra/tools/Searchtool/paper_searcher.py`
- `cloudra/tools/Searchtool/openalex_searcher.py`
- `cloudra/tools/Bashtool/bashtools.py`
- `cloudra/tools/Writetool/text_writer.py`
- `cloudra/tools/Writetool/edit_file.py`
- `cloudra/tools/Browsertool/web_fetcher.py`
- `cloudra/tools/Browsertool/headless_browser.py`

**Modify (wiring)**
- `cloudra/tools/registry.py`
- `cloudra/runtime_v2/adapters.py` — unknown-tool hint; native-search mutates `search` schema; `web_search` in tool_names → `search`
- `cloudra/runtime_v2/agent_runner.py` — inject `image_path` or `image_paths` (no cap)
- `cloudra/runtime_v2/turn_pipeline.py` — register every path in `image_paths`
- `cloudra/runtime_v2/subagent_bridge.py` — `_LAUNCHER` / `_SWARM` strings
- `cloudra/runtime_v2/policies/dag_stage.py` — launcher/swarm name set
- `cloudra/runtime_v2/policies/schedule_stage.py` — `delay_seconds` / `message`
- `cloudra/core/agent.py` — `"search" in tool_names`; stop stripping the whole search tool
- `cloudra/tools/Skilltool/get_skill.py` — `get_skill` / `reference`
- `cloudra/tools/Managetool/subagent_launcher.py` / `subagent_swarm.py` — `tool_name` only
- `cloudra/benchmark/method_policy.py` — drop `bashtools` dual-name
- `cloudra/tools/core/bash_habit_guard.py`, `coord_guard.py` — copy
- `frontend/src/timeline.ts` / `timeline.test.ts` — display accepts old and new names
- prompts, skills, `AGENTS.md`, tool descriptions that cite old names

## Global Constraints

- No backward-compat aliases: old wire names are never executed.
- No silent truncation inside `read`: only caller `offset`/`limit` windows content; oversized observations offload to `.cloudra/tool_output/` with the full body on disk.
- Scanned PDFs: every page rendered and, when visual is on, every page injected. No N-page cap.
- `read` is `is_read()` and is **not** in `visual_tools()`. `pymol_render` stays visual-gated.
- `runtime_profiles` follow the pre-rename entry (do not put `bash` / `browser` on android).
- Provider-protocol `web_search` in `llm_client.py` / `web_search_native.py` is not renamed.
- Python >= 3.11. Do not add dependencies. PDF path uses existing optional PyMuPDF (`cloudra[pdf]`).
- Tests: `uv run pytest -q tests/test_<area>*` then `uv run pytest -q tests/` before claiming a task done. `conftest.py` already isolates `data_dir`.
- After each task: `uv run python -m compileall -q` on touched files.
- Do not leave dead Tool classes or registry entries.

---

### Task 1: Unknown-tool hint table

**Files:**
- Create: `cloudra/tools/name_hints.py`
- Modify: `cloudra/runtime_v2/adapters.py` (unknown-tool branch around line 410)
- Test: `tests/test_tool_name_hints.py`
- Modify: `tests/test_runtime_v2_adapters.py` (`test_legacy_tool_executor_reports_unknown_tool`)

**Interfaces:**
- Consumes: nothing
- Produces: `hint_unknown_tool(name: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tool_name_hints.py
from cloudra.tools.name_hints import hint_unknown_tool

def test_retired_names_point_at_new_surface():
    assert "read" in hint_unknown_tool("text_reader")
    assert "read" in hint_unknown_tool("pdf2md")
    assert "search" in hint_unknown_tool("web_search")
    assert "source=" in hint_unknown_tool("paper_searcher")
    assert "bash" in hint_unknown_tool("bashtools")
    assert "write" in hint_unknown_tool("text_writer")
    assert "edit" in hint_unknown_tool("edit_file")
    assert "get_skill" in hint_unknown_tool("getskill")
    assert "web_fetch" in hint_unknown_tool("web_fetcher")
    assert "browser" in hint_unknown_tool("headless_browser")
    assert "subagent_launcher" in hint_unknown_tool("SubAgentLauncher")
    assert "subagent_swarm" in hint_unknown_tool("SubAgentSwarm")

def test_unknown_name_has_no_retired_mapping():
    msg = hint_unknown_tool("does_not_exist")
    assert "does_not_exist" in msg
    assert "read" not in msg.split("Did you mean")[0] if "Did you mean" in msg else True
```

Also extend `test_legacy_tool_executor_reports_unknown_tool` so `name="text_reader"` yields a summary containing `read` and `is_success is False`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_tool_name_hints.py tests/test_runtime_v2_adapters.py::test_legacy_tool_executor_reports_unknown_tool -v`

Expected: FAIL with `ModuleNotFoundError: cloudra.tools.name_hints` (or import error).

- [ ] **Step 3: Implement the hint table and wire it**

```python
# cloudra/tools/name_hints.py
"""Retired wire names → hint only. Never executed."""

_RETIRED: dict[str, str] = {
    "text_reader": "read",
    "image_reader": "read",
    "pdf2md": "read",
    "pdf2image": "read",
    "read_file": "read",
    "web_search": "search (source=web)",
    "paper_searcher": "search (source=arxiv)",
    "openalex_searcher": "search (source=openalex)",
    "bashtools": "bash",
    "shell": "bash",
    "text_writer": "write",
    "write_file": "write",
    "edit_file": "edit",
    "str_replace": "edit",
    "getskill": "get_skill",
    "web_fetcher": "web_fetch",
    "headless_browser": "browser",
    "SubAgentLauncher": "subagent_launcher",
    "SubAgentSwarm": "subagent_swarm",
}

def hint_unknown_tool(name: str) -> str:
    target = _RETIRED.get(name)
    if target:
        return (
            f"[Tool error] unknown tool {name!r}. "
            f"Use `{target}` instead."
        )
    return (
        f"[Tool error] unknown tool {name!r}. "
        "Choose an available tool and retry."
    )
```

In `adapters.py` `LegacyToolExecutor.execute`, replace the unknown-tool `ToolResult` summary with `hint_unknown_tool(call.name)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/test_tool_name_hints.py tests/test_runtime_v2_adapters.py::test_legacy_tool_executor_reports_unknown_tool -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloudra/tools/name_hints.py cloudra/runtime_v2/adapters.py tests/test_tool_name_hints.py tests/test_runtime_v2_adapters.py
git commit -m "$(cat <<'EOF'
Add retired tool-name hints without executing aliases.

EOF
)"
```

---

### Task 2: `read` for text and images

**Files:**
- Create: `cloudra/tools/core/observation_offload.py`
- Create: `cloudra/tools/Searchtool/_text.py`
- Create: `cloudra/tools/Searchtool/_image.py`
- Create: `cloudra/tools/Searchtool/read.py`
- Modify: `cloudra/tools/registry.py` — replace `text_reader` and `image_reader` registrations with one `read` entry (`runtime_profiles=frozenset({'desktop', 'android'})`, `visual=False`)
- Delete: `cloudra/tools/Searchtool/text_reader.py`, `image_reader.py`
- Test: `tests/test_read.py` (new), rewrite `tests/test_workspace.py` text_reader tests, `tests/test_runtime_v2_visual_mode.py` (gated tool becomes `pymol_render` only; `read` must remain visible when visual_mode is off)
- Modify: `tests/test_tool_semantics.py` — drop `image_reader` from `visual_tools` expectation

**Interfaces:**
- Consumes: `WorkspaceService.read_text(relative_path, start_line, end_line)` (0-based, end exclusive)
- Produces: class `Read` with `tool_name="read"`; `Read_input_schema(path, offset=None, limit=None, focus="auto")`; `Read_output_schema` fields below

Output schema fields (all tasks from here on use these names):

```python
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
    image_paths: list[str] = []  # visual injection list; no cap
    images: list[dict] = []  # inventory: {path, page}
    message: str = ""
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_read.py — text + image cases
import pytest
from cloudra.tools.Searchtool.read import Read, Read_input_schema

def _subagent(root):
    return type("A", (), {"working_directory": str(root)})()

@pytest.mark.asyncio
async def test_read_text_relative_path_returns_sha256(tmp_path, mock_session):
    (tmp_path / "readme.md").write_text("hello\n", encoding="utf-8")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="readme.md"), mock_session)
    assert result.is_success
    assert result.kind == "text"
    assert result.content == "hello\n"
    assert result.path == "readme.md"
    assert len(result.sha256) == 64
    assert result.offset == 1

@pytest.mark.asyncio
async def test_read_rejects_absolute_path(tmp_path, mock_session):
    (tmp_path / "readme.md").write_text("hello\n", encoding="utf-8")
    tool = Read(subagent=_subagent(tmp_path))
    rejected = await tool.tool_call(
        Read_input_schema(path=str(tmp_path / "readme.md")), mock_session
    )
    assert rejected.is_success is False
    assert "relative" in rejected.message.lower()

@pytest.mark.asyncio
async def test_read_offset_limit_are_one_based(tmp_path, mock_session):
    (tmp_path / "n.txt").write_text("a\nb\nc\nd\n", encoding="utf-8")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(
        Read_input_schema(path="n.txt", offset=2, limit=2), mock_session
    )
    assert result.content == "b\nc\n"
    assert result.offset == 2
    assert result.limit == 2
    assert result.total_lines == 4

@pytest.mark.asyncio
async def test_read_does_not_silently_truncate_text(tmp_path, mock_session):
    body = ("line-of-text\n" * 4000)
    (tmp_path / "big.log").write_text(body, encoding="utf-8")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="big.log"), mock_session)
    assert result.is_success
    assert "[Truncated" not in result.content
    # Either full body in content, or offloaded with a workspace path and full file intact
    if result.content != body:
        assert ".cloudra/tool_output/" in result.message or ".cloudra/tool_output/" in result.content
        assert (tmp_path / "big.log").read_text(encoding="utf-8") == body

@pytest.mark.asyncio
async def test_read_png_sets_image_path(tmp_path, mock_session):
    png = tmp_path / "s.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="s.png"), mock_session)
    assert result.is_success
    assert result.kind == "image"
    assert result.image_path.endswith("s.png")
    assert result.image_paths == [result.image_path]
```

Replace `tests/test_workspace.py` `TextReader` imports/usages with `Read` / `path=`. Delete `test_text_reader_truncates_oversized_slice` (behavior is forbidden).

In `tests/test_runtime_v2_visual_mode.py`:
- `visual_tools() == frozenset({"pymol_render"})`
- `_FAKE_SCHEMAS` gated name is `pymol_render` only; include a `read` schema and assert `read` **stays** in the sent tools when `visual_mode=False`
- Permission stage: block `pymol_render` when visual off; **allow** `read`

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_read.py tests/test_workspace.py tests/test_runtime_v2_visual_mode.py -v`

Expected: FAIL importing `cloudra.tools.Searchtool.read`.

- [ ] **Step 3: Implement text/image `read`**

`observation_offload.py` — copy the bash `_cap_observation` logic into:

```python
async def cap_observation(text: str, *, root: str | None, stem: str) -> str:
    """If text exceeds 30_000 chars, write all of it under .cloudra/tool_output/ and
    return a head + path. Never drop the file. Caller must mention read+offset/limit."""
```

Head = 4_000 chars. Message must say: full output at the relative path; page with `read` `offset`/`limit`.

`_text.py`:

```python
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
PDF_EXTS = {".pdf"}

def offset_limit_to_slice(offset: int | None, limit: int | None) -> tuple[int, int]:
    if offset is not None and offset < 1:
        raise ValueError("offset is 1-based")
    start_0 = 0 if offset is None else offset - 1
    end_0 = -1 if limit is None else start_0 + limit
    return start_0, end_0
```

Use `WorkspaceService.read_text` then convert `actual_start` (0-based) → output `offset = actual_start + 1`, `limit = actual_end - actual_start`.

`_image.py`: resolve `path` through the same workspace root (relative only). Supported exts: png/jpg/jpeg/webp. Return absolute path string for visual injection (existing `encode_image_data_url` wants a real filesystem path).

`read.py` `Read.tool_call`: branch on suffix. `is_read() -> True`. `tool_name = "read"`, `tool_id = "t-2"`. Description: one tool for text, images, and PDFs; do not mention deleted tool names except as “do not use bash to read files”.

Registry: remove the `text_reader` and `image_reader` `ToolRegistration` rows; add:

```python
ToolRegistration(
    module="cloudra.tools.Searchtool.read",
    class_name="Read",
    tool_name="read",
    runtime_profiles=frozenset({"desktop", "android"}),
)
```

Leave `pdf2md` / `pdf2image` registered until Task 3 (PDF not handled yet: `read` on `.pdf` should fail with a clear “not implemented” only if Task 3 is not in the same commit). **Prefer implementing Task 3 immediately after in the same session; if committing Task 2 alone, make `.pdf` return a failure that says PDF support lands in the document branch — do not route to pdf2md.**

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/test_read.py tests/test_workspace.py tests/test_runtime_v2_visual_mode.py tests/test_tool_semantics.py tests/test_pymol_render.py -v`

Fix `test_pymol_render.py` message assertion: `image_reader` → `read`.

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloudra/tools/Searchtool/read.py cloudra/tools/Searchtool/_text.py cloudra/tools/Searchtool/_image.py cloudra/tools/core/observation_offload.py cloudra/tools/registry.py tests/test_read.py tests/test_workspace.py tests/test_runtime_v2_visual_mode.py tests/test_tool_semantics.py tests/test_pymol_render.py
git rm cloudra/tools/Searchtool/text_reader.py cloudra/tools/Searchtool/image_reader.py
git commit -m "$(cat <<'EOF'
Replace text_reader and image_reader with a single read tool.

EOF
)"
```

---

### Task 3: `read` PDF document branch (no silent truncation)

**Files:**
- Create: `cloudra/tools/Searchtool/_document.py`
- Modify: `cloudra/tools/Searchtool/read.py` — dispatch `.pdf`
- Modify: `cloudra/tools/registry.py` — delete `pdf2md` and `pdf2image` registrations
- Delete: `pdf2md.py`, `pdf2image.py`
- Test: `tests/test_read.py` (PDF cases)

**Interfaces:**
- Consumes: `Read_input_schema.path/focus/offset/limit`; PyMuPDF `fitz`
- Produces: `extract_pdf(source: Path, cache_dir: Path) -> ExtractResult` with `text: str`, `images: list[dict]` (`path`, `page`), `chars_per_page: list[int]`; `render_pages(source: Path, cache_dir: Path) -> list[str]` (one PNG per page, all pages)

Cache dir: `{workspace}/.cloudra/extract/{sha256(source_bytes)[:16]}/` with `content.md`, `images/`, `pages/`. Reuse if `content.md` exists and the source hash still matches (hash is the directory name). Write cache with ordinary file IO (not `WorkspaceService.prepare_write`) so explorer (`is_read`) can populate it.

Scan if `sum(chars_per_page) < 200` or (pages and `sum(chars_per_page)/pages < 50`).

- [ ] **Step 1: Write the failing PDF tests**

Skip the module if `fitz` is missing: `fitz = pytest.importorskip("fitz")`.

```python
def _pdf_with_text(path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello paper body")
    doc.save(str(path))
    doc.close()

def _pdf_scan(path):
    doc = fitz.open()
    page = doc.new_page()
    # 1x1 pixmap painted, no text layer
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), False)
    pix.clear_with(127)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(str(path))
    doc.close()

@pytest.mark.asyncio
async def test_read_pdf_auto_returns_text_and_figure_inventory(tmp_path, mock_session):
    _pdf_with_text(tmp_path / "p.pdf")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="p.pdf"), mock_session)
    assert result.is_success
    assert result.kind == "document"
    assert "Hello paper body" in result.content
    assert result.image_paths == []  # auto + text layer: do not inject figures
    # images inventory may be empty if insert_text created no xrefs; that's fine

@pytest.mark.asyncio
async def test_read_pdf_docx_is_rejected(tmp_path, mock_session):
    (tmp_path / "x.docx").write_bytes(b"PK\x03\x04not-a-pdf")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="x.docx"), mock_session)
    assert result.is_success is False
    assert "pdf" in result.message.lower()

@pytest.mark.asyncio
async def test_read_scan_pdf_injects_every_page(tmp_path, mock_session):
    _pdf_scan(tmp_path / "s.pdf")
    # make 3 pages
    doc = fitz.open(tmp_path / "s.pdf")
    doc.new_page(); doc.new_page()
    doc.save(tmp_path / "s3.pdf"); doc.close()
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="s3.pdf", focus="auto"), mock_session)
    assert result.is_success
    assert len(result.image_paths) == 3
    assert len(result.images) == 3
    assert result.image_path == result.image_paths[0]

@pytest.mark.asyncio
async def test_read_scan_focus_text_does_not_inject_images(tmp_path, mock_session):
    _pdf_scan(tmp_path / "s.pdf")
    tool = Read(subagent=_subagent(tmp_path))
    result = await tool.tool_call(Read_input_schema(path="s.pdf", focus="text"), mock_session)
    assert result.is_success
    assert result.image_paths == []
    assert "text layer" in result.message.lower() or "no text" in result.message.lower()

@pytest.mark.asyncio
async def test_explorer_can_read_pdf(tmp_path, mock_session):
    _pdf_with_text(tmp_path / "p.pdf")
    tool = Read(subagent=_subagent(tmp_path))
    assert tool.is_read() is True
    assert tool.is_script() is False
    result = await tool.tool_call(Read_input_schema(path="p.pdf"), mock_session)
    assert result.is_success
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_read.py -v`

Expected: FAIL on PDF cases (`kind != document` or error message about unsupported format).

- [ ] **Step 3: Implement `_document.py` and dispatch**

Port `_convert_sync` from `pdf2md.py` (text blocks + xref images) and the pixmap loop from `pdf2image.py` (all pages, `fitz.Matrix(2,2)`). Do not take `output_path` from the model.

`read.py` for `.pdf`:
1. Resolve relative path inside workspace.
2. Hash file bytes, cache under `.cloudra/extract/<16 hex>/`.
3. Extract (or reuse cache).
4. Apply `focus` per spec table.
5. Apply `offset`/`limit` to extracted markdown lines (same 1-based helper as text).
6. `cap_observation` on `content` only — never drop `images` / `image_paths`.

`.docx` and other non-pdf binaries: `is_success=False`, message that only PDF documents are supported.

Remove pdf registrations; `git rm` the two modules.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/test_read.py tests/test_tool_semantics.py -v`

Expected: PASS (PDF tests skipped if PyMuPDF missing).

- [ ] **Step 5: Commit**

```bash
git add cloudra/tools/Searchtool/_document.py cloudra/tools/Searchtool/read.py cloudra/tools/registry.py tests/test_read.py
git rm cloudra/tools/Searchtool/pdf2md.py cloudra/tools/Searchtool/pdf2image.py
git commit -m "$(cat <<'EOF'
Fold PDF extract and scan render into read.

EOF
)"
```

---

### Task 4: Visual injection for `image_paths`

**Files:**
- Modify: `cloudra/runtime_v2/agent_runner.py` `_tool_result_content` (~385–407)
- Modify: `cloudra/runtime_v2/turn_pipeline.py` `_register_tool_image` (~465–481)
- Test: `tests/test_runtime_v2_visual_mode.py` or new tests in `tests/test_read.py` against a small fake runner helper — prefer a focused unit test of `_tool_result_content` by instantiating `AgentRunner` with a dummy pipeline

**Interfaces:**
- Consumes: `ToolResult.data["image_path"]` and `data["image_paths"]`
- Produces: history content as a parts list `[text, image_url...]` with **every** path; artifact registration for every path

- [ ] **Step 1: Write the failing test**

Add in `tests/test_runtime_v2_visual_mode.py`:

```python
@pytest.mark.asyncio
async def test_tool_result_injects_all_image_paths(tmp_path, monkeypatch):
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.policies.base import ToolResult
    pngs = []
    for i in range(3):
        p = tmp_path / f"{i}.png"
        p.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        pngs.append(str(p))
    runner = AgentRunner(pipeline=SimpleNamespace(llm=SimpleNamespace(supports_vision=lambda _a: True)))
    agent = _visual_agent(True)
    content = await runner._tool_result_content(
        agent,
        ToolResult(is_success=True, summary="scan", data={"image_paths": pngs, "image_path": pngs[0]}),
    )
    assert isinstance(content, list)
    urls = [p for p in content if p.get("type") == "image_url"]
    assert len(urls) == 3
```

Monkeypatch `encode_image_data_url` to return `"data:image/png;base64,xx"` if the real encoder rejects the tiny PNG.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest -q tests/test_runtime_v2_visual_mode.py::test_tool_result_injects_all_image_paths -v`

Expected: FAIL (`content` is a string because only `image_path` is read).

- [ ] **Step 3: Implement multi-path injection**

```python
paths = []
data = result.data if isinstance(result.data, dict) else {}
raw = data.get("image_paths")
if isinstance(raw, list):
    paths.extend(p for p in raw if isinstance(p, str) and p)
elif isinstance(data.get("image_path"), str) and data["image_path"]:
    paths.append(data["image_path"])
# no max(len(paths), N)
```

If visual off or no vision: append one fallback line **per path**, do not drop extras.

`_register_tool_image`: loop all paths, return the last artifact id (or join — current `tool.finished` stores a single `image_path`; put `image_paths` on the event data as well so the UI can show them). Keep the first path as `image_path` for backward event shape.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/test_runtime_v2_visual_mode.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloudra/runtime_v2/agent_runner.py cloudra/runtime_v2/turn_pipeline.py tests/test_runtime_v2_visual_mode.py
git commit -m "$(cat <<'EOF'
Inject every image_paths entry from read results.

EOF
)"
```

---

### Task 5: `search` surface and native-search schema

**Files:**
- Create: `cloudra/tools/Searchtool/_web.py`, `_arxiv.py`, `_openalex.py`, `search.py`
- Modify: `cloudra/tools/registry.py` — one `search` entry with android profile; delete the three old search registrations
- Delete: `web_search.py`, `paper_searcher.py`, `openalex_searcher.py`
- Modify: `cloudra/runtime_v2/adapters.py` — `legacy_tool_schemas` / `complete`: if native adapter set, **keep** `search` and rewrite its `source` enum to `["arxiv","openalex"]` with default `arxiv`; do not drop the function. `"search" in tool_names` for `web_search_available` (native adapter still counts as available).
- Modify: `cloudra/core/agent.py` — same: `"search" in tool_names`; stop filtering out the whole function. Do not touch `llm_client.py` protocol `web_search`.
- Move tests: `tests/test_web_search.py` → keep file but import `search` internals; `tests/test_paper_searcher.py` / `test_openalex_searcher.py` retargeted to `Search` + `source=`
- Test: `tests/test_search.py` (new, schema + dispatch + native mutation)

**Interfaces:**
- Consumes: existing fetch helpers (move functions, delete Tool classes)
- Produces: class `Search`, `tool_name="search"`, `tool_id="t-4"`

```python
class Search_input_schema(input_schema):
    query: str
    source: Literal["web", "arxiv", "openalex"] = "web"
    max_results: int = 8
    mode: Literal["light", "normal", "weight"] = "normal"
```

When `source=="web"`: ignore `mode`. When native search is on and the model still passes `source="web"`: `is_success=False` with a message that web search is provided natively.

Helper in adapters (so tests can call it without a full LLM):

```python
def apply_native_search_to_schemas(schemas: list[dict], native_on: bool) -> list[dict]:
    """If native_on, mutate search.source to arxiv|openalex (default arxiv). Never drop the tool."""
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_search.py
from cloudra.runtime_v2.adapters import apply_native_search_to_schemas
from cloudra.tools.Searchtool.search import Search, Search_input_schema

def test_search_schema_default_source_is_web():
    schema = Search().tool_schema_json()["function"]["parameters"]
    assert schema["properties"]["source"]["default"] == "web"
    assert set(schema["properties"]["source"]["enum"]) == {"web", "arxiv", "openalex"}
    assert "mode" in schema["properties"]

def test_native_search_drops_web_from_source_not_the_tool():
    schemas = [Search().tool_schema_json(), {"type": "function", "function": {"name": "bash"}}]
    out = apply_native_search_to_schemas(schemas, native_on=True)
    names = [s["function"]["name"] for s in out]
    assert "search" in names and "bash" in names
    search = next(s for s in out if s["function"]["name"] == "search")
    enum = search["function"]["parameters"]["properties"]["source"]["enum"]
    assert set(enum) == {"arxiv", "openalex"}
    assert search["function"]["parameters"]["properties"]["source"]["default"] == "arxiv"

@pytest.mark.asyncio
async def test_executor_rejects_search_web_when_native_on(monkeypatch):
    from types import SimpleNamespace
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.policies.base import ToolCall
    from cloudra.runtime_v2.schemas import Command

    ran = {"web": False}

    async def _fake_web(*_a, **_k):
        ran["web"] = True
        return {"is_success": True, "results": []}

    monkeypatch.setattr("cloudra.tools.Searchtool._web.run", _fake_web)
    monkeypatch.setattr(
        "cloudra.runtime_v2.adapters._native_search_adapter_for",
        lambda _settings: SimpleNamespace(transport="chat"),
    )
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    spawned = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "go"},
        )
    )
    output = await LegacyToolExecutor(core).execute(
        spawned.data,
        ToolCall(id="tc1", name="search", arguments={"query": "q", "source": "web"}),
    )
    assert output.is_success is False
    assert ran["web"] is False
    assert "native" in output.summary.lower() or "arxiv" in output.summary.lower()
```

Keep backend unit tests on `_web.run` / `_arxiv.run` / `_openalex.run`. `Search.tool_call` is a thin switch. In `LegacyToolExecutor.execute`, if `call.name == "search"` and `source` is `web` (or omitted) and `_native_search_adapter_for(agent.settings)` is not None, return the error `ToolResult` without instantiating Search.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_search.py -v`

Expected: FAIL on missing `search` module / `apply_native_search_to_schemas`.

- [ ] **Step 3: Move backends and add `Search`**

- `_web.py`: everything in `web_search.py` except the Tool class; `async def run(query, max_results) -> dict`
- `_arxiv.py`: `_fetch_arxiv` + formatting by `mode` from `paper_searcher.py`
- `_openalex.py`: HTTP client + abstract rebuild from `openalex_searcher.py`; map `max_results` → old `limit`, `page=1`

`Search.tool_call`: switch on `source`. `is_read() -> True`.

Registry android profile like the old `web_search` row.

`apply_native_search_to_schemas`: deep-copy the search function dict, patch `properties.source`. Call it from `LegacyLLMProvider.complete` instead of the list-comprehension that dropped `web_search`.

`web_search_available = native_adapter is not None or "search" in tool_names` in both `adapters.py` and `core/agent.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/test_search.py tests/test_web_search.py tests/test_paper_searcher.py tests/test_openalex_searcher.py tests/test_web_search_native.py tests/test_runtime_v2_adapters.py -v`

Update `test_web_search_native.py` if it asserts a function named `web_search` in the **agent** tool list (not the provider protocol). Provider protocol tests must still see `type: web_search`.

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloudra/tools/Searchtool/search.py cloudra/tools/Searchtool/_web.py cloudra/tools/Searchtool/_arxiv.py cloudra/tools/Searchtool/_openalex.py cloudra/tools/registry.py cloudra/runtime_v2/adapters.py cloudra/core/agent.py tests/test_search.py tests/test_web_search.py tests/test_paper_searcher.py tests/test_openalex_searcher.py tests/test_web_search_native.py
git rm cloudra/tools/Searchtool/web_search.py cloudra/tools/Searchtool/paper_searcher.py cloudra/tools/Searchtool/openalex_searcher.py
git commit -m "$(cat <<'EOF'
Merge web/arxiv/openalex search into search with source=.

EOF
)"
```

---

### Task 6: 1:1 wire-name renames

**Files:**
- Create (git mv + class/tool_name edits):
  - `cloudra/tools/Bashtool/bash.py` (class `Bash`, `tool_name="bash"`, `tool_id="t-1"`)
  - `cloudra/tools/Writetool/write.py` (class `Write`, `tool_name="write"`, field `path`)
  - `cloudra/tools/Writetool/edit.py` (class `Edit`, `tool_name="edit"`, field `path`; `old_string`/`new_string` via `AliasChoices`)
  - `cloudra/tools/Browsertool/web_fetch.py` (`tool_name="web_fetch"`)
  - `cloudra/tools/Browsertool/browser.py` (`tool_name="browser"`)
- Modify: `get_skill.py` (`tool_name="get_skill"`, rename field `other` → `reference`)
- Modify: `subagent_launcher.py` / `subagent_swarm.py` (`tool_name` snake_case only)
- Modify: `registry.py` module/class_name/tool_name for all of the above; `bash` keeps `dag_compute_predicate`
- Modify: `subagent_bridge.py` `_LAUNCHER="subagent_launcher"`, `_SWARM="subagent_swarm"`
- Modify: `dag_stage.py` the two sets `{"subagent_launcher", "subagent_swarm"}`
- Modify: `observation_offload.py` / bash cap message: tell the model to `read` with `offset`/`limit`
- Modify: `benchmark/method_policy.py` — match only `"bash"` (delete the `bashtools` dual-name comment)
- Modify: `tools/core/bash_habit_guard.py`, `coord_guard.py` — copy only
- Tests: every file under `tests/` that imports the old classes or asserts old `tool_name`

**Interfaces:**
- Consumes: Task 2 `cap_observation` (bash should call it instead of its private `_cap_observation`)
- Produces: wire names exactly as the spec table

`Edit` field:

```python
from pydantic import AliasChoices, Field

class EditOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    old_text: str = Field(
        validation_alias=AliasChoices("old_string", "old_str", "old_text"),
        serialization_alias="old_string",
        description="Original text to replace; must match uniquely by default",
    )
    new_text: str = Field(
        validation_alias=AliasChoices("new_string", "new_str", "new_text"),
        serialization_alias="new_string",
        description="Replacement text",
    )
```

JSON schema properties must be `old_string` / `new_string`. Input `path` not `filepath`.

- [ ] **Step 1: Write failing assertions for the new names**

Add to `tests/test_tool_semantics.py` (or `tests/test_read.py` sibling `test_tool_wire_names.py`):

```python
from cloudra.tools import get_tools_lst

GONE = {
    "text_reader", "image_reader", "pdf2md", "pdf2image",
    "web_search", "paper_searcher", "openalex_searcher",
    "bashtools", "text_writer", "edit_file", "getskill",
    "web_fetcher", "headless_browser", "SubAgentLauncher", "SubAgentSwarm",
}
REQUIRED = {
    "read", "search", "bash", "write", "edit", "get_skill",
    "web_fetch", "browser", "subagent_launcher", "subagent_swarm",
}

def test_registry_wire_names():
    names = {e.tool_name for e in get_tools_lst()}
    assert GONE.isdisjoint(names)
    assert REQUIRED <= names

def test_edit_schema_uses_path_and_old_string():
    edit = next(e for e in get_tools_lst() if e.tool_name == "edit")
    props = edit.instantiate().tool_schema_json()["function"]["parameters"]["properties"]
    assert "path" in props and "filepath" not in props
    edit_item = props["edits"]["items"]
    keys = edit_item.get("properties") or edit_item
    # $ref unwrap if needed
    assert "old_string" in str(props)

def test_get_skill_schema_has_reference_not_other():
    skill = next(e for e in get_tools_lst() if e.tool_name == "get_skill")
    props = skill.instantiate().tool_schema_json()["function"]["parameters"]["properties"]
    assert "reference" in props and "other" not in props
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest -q tests/test_tool_semantics.py::test_registry_wire_names -v`

Expected: FAIL (`bashtools` still present).

- [ ] **Step 3: git mv + rename classes/fields + fix imports**

Mechanical but complete. After moves, `grep -n` these strings under `cloudra/` and `tests/` and replace (do not replace provider `web_search` in `llm_client.py` / `web_search_native.py` / config comments about the native protocol):

| find | replace |
|---|---|
| `tool_name: str = 'bashtools'` | `bash` |
| `class Bashtools` | `class Bash` |
| `from cloudra.tools.Bashtool.bashtools import Bashtools` | `from cloudra.tools.Bashtool.bash import Bash` |
| `text_writer` wire | `write` |
| `edit_file` wire | `edit` |
| `filepath` on Read/Write/Edit schemas | `path` |
| `getskill` | `get_skill` |
| `user_input.other` | `user_input.reference` |
| `web_fetcher` tool_name | `web_fetch` |
| `headless_browser` tool_name | `browser` |
| `SubAgentLauncher` as **tool_name / call.name** | `subagent_launcher` |
| `SubAgentSwarm` as **tool_name / call.name** | `subagent_swarm` |

Leave Python class names `SubAgentLauncher` / `SubAgentSwarm` if you want less churn; spec only requires the **wire** name to change. Prefer keeping the class names and only changing `tool_name` plus interceptor string constants.

`method_policy.py`: `if tool_name == "bash"` only. Update `tests/test_benchmark.py::test_method_policy_bashtools_real_tool_name` to `test_method_policy_bash_tool_name` asserting `"bash"`.

Clear `cloudra.tools._TOOL_ENTRIES_CACHE` is process-level; pytest collection after file change is a new import — no extra reset.

- [ ] **Step 4: Run the focused suites**

Run: `uv run pytest -q tests/test_tool_semantics.py tests/test_tools_core.py tests/test_coord_guard.py tests/test_yolo_guard.py tests/test_benchmark.py tests/test_runtime_v2_subagent_bridge.py tests/test_dag_substantive_gate.py tests/test_prompt_assembler.py -v`

Fix remaining import failures until green.

- [ ] **Step 5: Commit**

```bash
git add -A cloudra/tools cloudra/runtime_v2 cloudra/benchmark cloudra/core tests
git commit -m "$(cat <<'EOF'
Rename bash/write/edit/get_skill/web_fetch/browser/subagent wire names.

EOF
)"
```

---

### Task 7: Prompts, skills, schedule copy, frontend display

**Files:**
- `cloudra/prompts/*.md` (coordinator, explorer, writer, researcher, dft, small_mol, md)
- `cloudra/skills/literature-search/SKILL.md`, `subagent-prompting/SKILL.md`, `dft-calculation/SKILL.md`, `first-principles-calculation/SKILL.md` and its `references/reaction-class-geometry.md`
- `cloudra/runtime/prompt_assembler.py` (filepath/`text_reader`/`bashtools` sentence → `path` / `read` / `write` / `edit` / `bash`)
- `cloudra/runtime_v2/policies/schedule_stage.py` — `delay_seconds` / `message` (not `DurationSeconds` / `Prompt`)
- `cloudra/tools/**` descriptions that still cite old names (`molecule_drawer`, `pymol_render`, `image_to_smiles`, `update_memory`, `web_fetch`, `browser`, `bash`, `write`, `edit`)
- `frontend/src/timeline.ts` — display: treat `read`/`write`/`edit`/`bash` like the old names; **keep** the old names in the `||` so historical events still summarize
- `frontend/src/timeline.test.ts`
- `AGENTS.md` — any tool-name mentions in the tools/`runtime_v2` map

**Interfaces:**
- Consumes: new wire names from Task 6
- Produces: no leftover `DurationSeconds` / `text_reader` / `getskill` in agent-facing copy (provider docs may still say native `web_search`)

- [ ] **Step 1: Write a failing grep-based test**

```python
# tests/test_tool_copy_mentions.py
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_IN_PROMPTS = re.compile(
    r"\b(text_reader|image_reader|pdf2md|pdf2image|paper_searcher|"
    r"openalex_searcher|bashtools|text_writer|edit_file|getskill|"
    r"web_fetcher|headless_browser|DurationSeconds)\b"
)

def test_prompts_use_new_tool_names():
    hits = []
    for path in (ROOT / "cloudra" / "prompts").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if FORBIDDEN_IN_PROMPTS.search(text):
            hits.append(path.name)
    assert hits == []

def test_schedule_stage_uses_real_fields():
    text = (ROOT / "cloudra/runtime_v2/policies/schedule_stage.py").read_text(encoding="utf-8")
    assert "DurationSeconds" not in text
    assert "delay_seconds" in text
    assert "message" in text
```

Do **not** ban `web_search` in this test — native-search copy and `web_search_native.py` still use it.

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest -q tests/test_tool_copy_mentions.py -v`

Expected: FAIL with prompt filenames in `hits`.

- [ ] **Step 3: Rewrite copy**

Typical replacements in prompts/skills/descriptions:

- `text_reader` / `image_reader` / `pdf2md` / `pdf2image` → `read`
- `web_search` **in agent tool instructions** (researcher.md, explorer) → `search` (`source=web`); keep “native_search” explanations
- `paper_searcher` → `search` with `source=arxiv`
- `openalex_searcher` → `search` with `source=openalex`
- `bashtools` → `bash`
- `text_writer` → `write`
- `edit_file` → `edit`
- `getskill` → `get_skill`
- `web_fetcher` → `web_fetch`
- `headless_browser` → `browser`
- `SubAgentLauncher` / `SubAgentSwarm` in **user-facing prompt text** → `subagent_launcher` / `subagent_swarm`
- `filepath` in assembler workspace sentence → `path`
- `start_line`/`end_line` in bash offload / dft paging → `offset`/`limit`
- schedule: ``schedule(delay_seconds=<seconds>, message='<wake up instruction>')``

`timeline.ts` `formatToolArgs`:

```typescript
if (toolName === 'bashtools' || toolName === 'bash') {
  return String(data.command ?? data.cmd ?? fullText(value));
}
if (
  toolName === 'text_writer' || toolName === 'edit_file' || toolName === 'text_reader' ||
  toolName === 'write' || toolName === 'edit' || toolName === 'read'
) {
  return String(data.filepath ?? data.path ?? fullText(value));
}
```

Update `timeline.test.ts` fixtures: add a case for `read` + `path`; keep one old `text_reader` + `filepath` case so history still formats.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q tests/test_tool_copy_mentions.py tests/test_prompt_assembler.py -v` and `npm --prefix frontend run test:timeline`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloudra/prompts cloudra/skills cloudra/runtime/prompt_assembler.py cloudra/runtime_v2/policies/schedule_stage.py cloudra/tools frontend/src/timeline.ts frontend/src/timeline.test.ts AGENTS.md tests/test_tool_copy_mentions.py
git commit -m "$(cat <<'EOF'
Update prompts, skills, and timeline copy to the new tool names.

EOF
)"
```

---

### Task 8: Full-suite sweep

**Files:** whatever still greps as old **wire** names under `cloudra/` and `tests/` except `name_hints.py`, `test_tool_name_hints.py`, `timeline.ts` historical branches, `llm_client.py`, `web_search_native.py`, and this plan/spec.

**Interfaces:** none new

- [ ] **Step 1: Fail-loud inventory**

Run:

```bash
rg -n --glob '!docs/superpowers/**' --glob '!**/name_hints.py' --glob '!**/test_tool_name_hints.py' \
  -e "tool_name=.bashtools" -e "tool_name=.text_reader" -e "tool_name=.getskill" \
  -e "tool_name=.SubAgentLauncher" -e "tool_name=.web_fetcher" \
  cloudra tests
```

Expected before the sweep: leftover hits. Each hit is either a missed rename or a comment. Fix code; comments that document the *old* name as history can stay if they also say the new name.

- [ ] **Step 2: Run the full suite**

Run: `uv run pytest -q tests/` and `uv run ruff check cloudra tests`

Expected: all pass. If ruff wants import-order fixes on the new modules, apply them.

- [ ] **Step 3: Compile**

Run: `uv run python -m compileall -q cloudra/tools cloudra/runtime_v2/adapters.py cloudra/runtime_v2/agent_runner.py`

Expected: silent success.

- [ ] **Step 4: Commit leftover fixes if any**

```bash
git add -A
git commit -m "$(cat <<'EOF'
Finish leftover old tool-name references.

EOF
)"
```

Only commit if there are changes.

---

## Self-review (spec coverage)

| Spec section | Task |
|---|---|
| Line-name table (merge + rename) | 2, 3, 5, 6 |
| `read` params, 1-based offset, `path` | 2 |
| No 30k silent truncate; tool_output offload | 2 (`cap_observation`) |
| Image branch; `read` not in `visual_tools` | 2, 4 |
| PDF auto / scan / focus=text; all pages; cache; explorer | 3 |
| `.docx` rejected | 3 |
| `image_paths` inject uncapped | 4 |
| `search` source/mode; web ignores mode | 5 |
| Native search mutates source, does not drop tool; `source=web` errors | 5 |
| Provider `web_search` untouched | 5 (explicit non-edit) |
| bash/write/edit/get_skill/web_fetch/browser/subagent names | 6 |
| `old_string` / `reference` / `path` | 6 |
| Unknown-tool hints, no execute | 1 |
| `runtime_profiles` not expanded | 2, 5, 6 registry rows |
| schedule `delay_seconds`/`message` | 7 |
| Prompts/skills/AGENTS/timeline history | 7 |
| Tests first-red then green; no “old name still works” | 1–8 |
| `pdf2md`/`pdf2image`/`text_reader` deleted | 2, 3 |
