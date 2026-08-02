# Cloudra Virtualized TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Cloudra's message-per-Widget Textual TUI with an event-driven virtual transcript while preserving every observable feature and the current visual design.

**Architecture:** A pure `TranscriptStore` owns complete ordered records, a bounded compiler converts records to cached Rich/Textual rows, and one Line API `ScrollView` renders only the viewport. `RenderBridge` reduces event bursts into store mutations and a one-shot frame scheduler coalesces repaint work; the rest of the TUI is migrated so synchronous history, layout, list, and SQLite bursts cannot monopolize the UI loop.

**Tech Stack:** Python 3.11+, asyncio, Textual 8.x-compatible Line API, Rich renderables and `Strip`, pytest, pytest-asyncio, cProfile.

## Global Constraints

- Preserve observable features and the current visual design, including the existing TCSS, theme, labels, panels, Markdown, code highlighting, tool collapse wording, copy control, filters, modals, and keyboard bindings.
- Keep complete final responses scrollable, including responses longer than 20,000 characters; only an active streaming preview may be bounded.
- Target 16 concurrent Agent streams and 1,000 loaded history records.
- Input/key handling p95 must be below 100 ms; a main-thread presentation commit must be below 50 ms; event reduction must yield after approximately four milliseconds.
- Continuous streaming schedules at most 20 presentation frames per second through one-shot event-triggered scheduling, never polling.
- Loaded transcript data is never pruned to control DOM size; only derived row caches may be evicted. Message count must not increase `ChatLog` child count.
- Do not modify, initialize, restore, stage, or commit `benchmarks/LAB-Bench`, `benchmarks/MolPuzzle`, or `benchmarks/data/chembench-repo`.
- Preserve all pre-existing dirty changes. Never use `git add -A`, `git add .`, checkout, reset, or clean. Every task checks explicit paths and commits with `git commit --only -- <paths>`.
- Use `.venv/bin/python -m pytest`; Textual integration tests require a writable `XDG_RUNTIME_DIR` and Unix-socket permission.
- Follow red-green-refactor: observe every new behavior test fail for the intended reason before adding its production implementation.

## File Structure

Create `cloudra/tui/new/transcript.py` for pure state, `virtual_lines.py` for variable-height indexing, `transcript_render.py` for Rich row compilation and hit regions, `frame_scheduler.py` for repaint coalescing, `clipboard.py` for the platform copy primitive, and `widgets/virtual_chat_log.py` for the Line API view. Create `scripts/profile_textual_tui.py` outside the user-owned benchmark tree.

Modify `widgets/chat_log.py` into the stable compatibility import, then migrate `render_bridge.py`, `screens/main_screen.py`, `widgets/side_panel.py`, `widgets/status_bar.py`, and the TUI-facing asynchronous paths in `service.py`. Delete `widgets/code_block.py` only after no live import remains.

Create focused tests in `tests/test_tui_transcript.py`, `test_tui_virtual_lines.py`, `test_tui_transcript_render.py`, `test_tui_frame_scheduler.py`, `test_tui_render_bridge_batching.py`, `test_tui_performance.py`, and `test_tui_visual_regression.py`. Put deterministic visual builders in `tests/tui_visual_cases.py` and the reviewed fixed-width contract in `tests/fixtures/tui_visual_baseline.json`. Migrate `tests/test_textual_tui.py` and extend `tests/test_service.py` without weakening existing observable assertions.

---

### Task 1: Freeze the Current Visual and Performance Baseline

**Files:**
- Create: `tests/tui_visual_cases.py`
- Create: `tests/test_tui_visual_regression.py`
- Create: `tests/fixtures/tui_visual_baseline.json`
- Create: `scripts/profile_textual_tui.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Consumes: the current `ChatLog.append_*` API and Cloudra theme.
- Produces: `VISUAL_CASES`, `semantic_snapshot(app) -> list[dict]`, and `run_profile(history_count=1000, stream_count=16, rounds=30) -> ProfileResult`.

- [ ] **Step 1: Write the fixture-backed characterization test before its fixture exists**

```python
FIXTURE = Path(__file__).parent / "fixtures" / "tui_visual_baseline.json"

@pytest.mark.asyncio
async def test_current_chat_visual_contract():
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actual = {}
    for name, build in VISUAL_CASES.items():
        app = VisualCaseApp(build)
        async with app.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            actual[name] = semantic_snapshot(app)
    assert actual == expected
```

Normalize each row to ordered `{"text": str, "style": str}` segments and omit cursor/blink state. Include welcome, user, failed user, plain assistant, Markdown, reasoning, running/finished/collapsed/expanded tools, decoded JSON, code/copy, file states, supervisor, alert, stream preview, sidebar, status, approval, and `ask_user` cases.

- [ ] **Step 2: Confirm the missing-fixture red state**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-plan .venv/bin/python -m pytest tests/test_tui_visual_regression.py -v`

Expected: FAIL with `FileNotFoundError` for the baseline JSON.

- [ ] **Step 3: Capture the baseline through an explicit writer**

```python
def write_snapshot(path: Path, snapshots: dict[str, list[dict]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

Only `CLOUDRA_UPDATE_TUI_SNAPSHOT=1` may invoke the writer; normal pytest must be read-only. Add an empty `tests/__init__.py`, run `CLOUDRA_UPDATE_TUI_SNAPSHOT=1 XDG_RUNTIME_DIR=/tmp/cloudra-tui-plan .venv/bin/python -m tests.tui_visual_cases`, inspect every named case, then rerun the test and expect PASS.

- [ ] **Step 4: Add the deterministic profile harness**

```python
@dataclass(frozen=True)
class ProfileResult:
    elapsed_seconds: float
    python_calls: int
    max_commit_seconds: float
    input_p95_seconds: float
    child_count: int
    record_count: int

async def run_profile(history_count: int = 1_000, stream_count: int = 16, rounds: int = 30) -> ProfileResult:
    """Run one fixed-size ChatLog workload under Textual.run_test."""
```

Measure calls with cProfile, elapsed/commit time with `perf_counter`, and an event-loop callback latency sample per streaming round. Print one JSON object. Run `XDG_RUNTIME_DIR=/tmp/cloudra-tui-profile .venv/bin/python scripts/profile_textual_tui.py --history 320 --streams 16 --rounds 30`; record the approximately 9.7-second/10-million-call legacy result in task notes.

- [ ] **Step 5: Verify and commit only baseline artifacts**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-tests .venv/bin/python -m pytest -s tests/test_textual_tui.py tests/test_tui_visual_regression.py -q`

Expected: the 50 existing TUI tests plus the visual contract pass.

```bash
git status --short -- tests/__init__.py tests/tui_visual_cases.py tests/test_tui_visual_regression.py tests/fixtures/tui_visual_baseline.json scripts/profile_textual_tui.py
git commit --only -m "test(tui): freeze visual and performance baseline" -- tests/__init__.py tests/tui_visual_cases.py tests/test_tui_visual_regression.py tests/fixtures/tui_visual_baseline.json scripts/profile_textual_tui.py
```

---

### Task 2: Introduce the Ordered Transcript Store

**Files:**
- Create: `cloudra/tui/new/transcript.py`
- Create: `tests/test_tui_transcript.py`

**Interfaces:**
- Consumes: session IDs such as `a-0_run_*`, `a-3_task*`, and `_pending`.
- Produces: `RecordKind`, `TranscriptRecord`, `TranscriptHandle`, `TranscriptChange`, and `TranscriptStore.append`, `append_system`, `append_user`, `append_divider`, `append_alert`, `append_file_change`, `append_supervisor_review`, `get`, `records`, `records_for_session`, `visible_records`, `rename_session`, `mark_send_failed`, `clear_session`, and `clear`.

- [ ] **Step 1: Write failing tests for order, filters, deduplication, rename, failure, and clear**

```python
def test_store_preserves_order_and_filters_without_copying_payloads():
    store = TranscriptStore()
    first = store.append_user("a-0_run_1", "主消息", message_id="m-1")
    duplicate = store.append_user("a-0_run_1", "主消息", message_id="m-1")
    child = store.append_user("a-3_task_1", "子消息")
    assert duplicate == first
    assert [r.record_id for r in store.records] == [first.record_id, child.record_id]
    assert [r.content for r in store.visible_records(agent_prefix="a-3")] == ["子消息"]
    store.mark_send_failed(first)
    assert store.get(first).send_failed and store.get(first).revision == 1
    store.rename_session("a-0_run_1", "a-0_run_2")
    assert [r.content for r in store.records_for_session("a-0_run_2")] == ["主消息"]
    store.clear_session("a-3_task_1")
    assert [r.content for r in store.records] == ["主消息"]
    store.clear()
    assert store.records == ()
```

- [ ] **Step 2: Confirm the missing-module red state**

Run: `.venv/bin/python -m pytest tests/test_tui_transcript.py -v`

Expected: FAIL because `cloudra.tui.new.transcript` does not exist.

- [ ] **Step 3: Implement immutable values and centralized revision replacement**

```python
class RecordKind(StrEnum):
    SYSTEM = "system"; USER = "user"; DIVIDER = "divider"; ALERT = "alert"
    ASSISTANT = "assistant"; TOOL = "tool"; FILE_CHANGE = "file_change"; SUPERVISOR = "supervisor"

@dataclass(frozen=True, slots=True)
class TranscriptHandle:
    record_id: int

@dataclass(frozen=True, slots=True)
class TranscriptRecord:
    record_id: int
    session_id: str
    agent_id: str | None
    kind: RecordKind
    content: str = ""
    reasoning: str = ""
    title: str = ""
    tool_name: str = ""
    arguments: str = ""
    result: str | None = None
    status: str = ""
    message_id: str | None = None
    collapsed: bool = False
    send_failed: bool = False
    revision: int = 0

@dataclass(frozen=True, slots=True)
class TranscriptChange:
    record_ids: tuple[int, ...] = ()
    order_changed: bool = False
    visibility_changed: bool = False
```

Store one record list, ID-to-position map, session-to-ID index, and durable-message-ID map. Return tuples from reads. All updates use `dataclasses.replace(record, revision=record.revision + 1, **changes)` exactly once.

The typed convenience methods call `append` with these exact mappings: system → `(SYSTEM, title="系统", content=content)`; user → `(USER, content=content, message_id=message_id)`; divider → `(DIVIDER, content=text)`; alert → `(ALERT, title=title, content=body, status=style)`; file change → `(FILE_CHANGE, title=path, content=diff or status, status=status)`; supervisor → `(SUPERVISOR, title="Supervisor 审查", content=reason, status=conclusion)`.

- [ ] **Step 4: Run and commit the store**

Run: `.venv/bin/python -m pytest tests/test_tui_transcript.py -v`

Expected: PASS.

```bash
git status --short -- cloudra/tui/new/transcript.py tests/test_tui_transcript.py
git commit --only -m "feat(tui): add ordered transcript store" -- cloudra/tui/new/transcript.py tests/test_tui_transcript.py
```

---

### Task 3: Add Lossless Stream and Tool Transitions

**Files:**
- Modify: `cloudra/tui/new/transcript.py`
- Modify: `tests/test_tui_transcript.py`

**Interfaces:**
- Consumes: Task 2's store and immutable replacement.
- Produces: `start_stream`, `append_stream_chunk`, `append_reasoning_chunk`, `end_stream`, `active_stream`, `append_tool`, `toggle_collapsed`, and `batch()`.

- [ ] **Step 1: Write failing stable-position and full-content tests**

```python
def test_stream_finalizes_in_place_around_tools_and_keeps_full_content():
    store = TranscriptStore()
    stream = store.start_stream("a-0_run_1", "coordinator")
    store.append_stream_chunk("a-0_run_1", "BEGIN-" + "x" * 25_000)
    store.append_tool("a-0_run_1", "Bash", "pwd")
    store.append_reasoning_chunk("a-0_run_1", "check")
    store.append_stream_chunk("a-0_run_1", "-END")
    store.end_stream("a-0_run_1")
    record = store.records[0]
    assert record.record_id == stream.record_id
    assert record.content.startswith("BEGIN-") and record.content.endswith("-END")
    assert len(record.content) == 25_010 and record.reasoning == "check"
    assert store.records[1].kind is RecordKind.TOOL

def test_tool_finish_updates_one_record_and_toggle_revisions_it():
    store = TranscriptStore()
    handle = store.append_tool("s1", "Bash", "pwd")
    assert store.append_tool("s1", "Bash", "pwd", finished=True, result="/tmp") == handle
    assert len(store.records) == 1 and store.get(handle).status == "finished"
```

- [ ] **Step 2: Confirm missing-method failures**

Run: `.venv/bin/python -m pytest tests/test_tui_transcript.py -k "stream_finalizes or tool_finish" -v`

Expected: FAIL on absent stream/tool methods.

- [ ] **Step 3: Implement one active record per session and one tool record per call**

```python
def append_stream_chunk(self, session_id: str, delta: str, agent_name: str = "Agent") -> TranscriptHandle:
    record_id = self._active_streams.get(session_id)
    if record_id is None:
        record_id = self.start_stream(session_id, agent_name).record_id
    record = self.get(record_id)
    self._replace(record_id, content=record.content + delta)
    return TranscriptHandle(record_id)

def end_stream(self, session_id: str) -> TranscriptHandle | None:
    record_id = self._active_streams.pop(session_id, None)
    if record_id is None:
        return None
    self._replace(record_id, status="finished")
    return TranscriptHandle(record_id)
```

Reasoning uses the same path. Finished tools search the session index backward for a matching unfinished tool and replace it; only unmatched finishes append. Results over eight formatted lines begin collapsed. The outermost `batch()` exit emits one unioned `TranscriptChange`.

- [ ] **Step 4: Verify and commit transitions**

Run: `.venv/bin/python -m pytest tests/test_tui_transcript.py -v`

Expected: PASS, including exact 25,010-character retention.

```bash
git status --short -- cloudra/tui/new/transcript.py tests/test_tui_transcript.py
git commit --only -m "feat(tui): model lossless streams and tools" -- cloudra/tui/new/transcript.py tests/test_tui_transcript.py
```

---

### Task 4: Implement Variable-Height Indexing and Anchors

**Files:**
- Create: `cloudra/tui/new/virtual_lines.py`
- Create: `tests/test_tui_virtual_lines.py`

**Interfaces:**
- Consumes: positive estimated/compiled row heights.
- Produces: `HeightIndex` with `total`, `height`, `append`, `replace`, `rebuild`, `row_start`, and `locate`; plus `ScrollAnchor` and `restore_anchor(anchor, ids, index) -> int`.

- [ ] **Step 1: Write failing boundary and correction tests**

```python
def test_height_index_maps_rows_and_updates_prefixes():
    index = HeightIndex([2, 3, 1])
    assert index.total == 6
    assert [index.locate(row) for row in range(6)] == [(0, 0), (0, 1), (1, 0), (1, 1), (1, 2), (2, 0)]
    index.replace(1, 5)
    assert index.row_start(2) == 7 and index.total == 8

def test_anchor_restores_same_record_offset():
    index = HeightIndex([3, 4, 2])
    anchor = ScrollAnchor(record_id=20, row_offset=2)
    index.replace(0, 7)
    assert restore_anchor(anchor, [10, 20, 30], index) == 9
```

- [ ] **Step 2: Confirm missing-module failure**

Run: `.venv/bin/python -m pytest tests/test_tui_virtual_lines.py -v`

Expected: FAIL because `virtual_lines` does not exist.

- [ ] **Step 3: Implement a Fenwick-backed index**

```python
@dataclass(frozen=True, slots=True)
class ScrollAnchor:
    record_id: int
    row_offset: int

class HeightIndex:
    @property
    def total(self) -> int:
        return self._prefix(len(self._heights))

    def replace(self, index: int, height: int) -> None:
        if height < 1:
            raise ValueError("record height must be positive")
        delta = height - self._heights[index]
        self._heights[index] = height
        self._add(index + 1, delta)

    def height(self, index: int) -> int:
        return self._heights[index]

    def locate(self, row: int) -> tuple[int, int]:
        if row < 0 or row >= self.total:
            raise IndexError(row)
        record_index = self._lower_bound(row + 1)
        return record_index, row - self.row_start(record_index)
```

Implement `append`, `rebuild`, `row_start`, Fenwick binary lifting, and anchor clamping. Add a seeded 500-operation randomized oracle against plain prefix sums.

- [ ] **Step 4: Verify and commit indexing**

Run: `.venv/bin/python -m pytest tests/test_tui_virtual_lines.py -v`

Expected: PASS.

```bash
git status --short -- cloudra/tui/new/virtual_lines.py tests/test_tui_virtual_lines.py
git commit --only -m "feat(tui): add virtual row height index" -- cloudra/tui/new/virtual_lines.py tests/test_tui_virtual_lines.py
```

---

### Task 5: Compile Records into Styled Rows and Hit Regions

**Files:**
- Create: `cloudra/tui/new/transcript_render.py`
- Create: `tests/test_tui_transcript_render.py`
- Modify: `tests/test_tui_visual_regression.py`
- Read-only reference: `tests/fixtures/tui_visual_baseline.json`

**Interfaces:**
- Consumes: `TranscriptRecord`, `format_tool_payload`, a width, and a Rich `Console`.
- Produces: `InteractionAction`, `InteractionRegion`, `CompiledRecord`, `RenderContext`, `compile_record(record, width, context)`, and `semantic_segments(compiled)`.

- [ ] **Step 1: Write failing rendering tests for JSON and code regions**

```python
def test_tool_json_is_decoded_collapsed_and_clickable():
    store = TranscriptStore()
    handle = store.append_tool("s1", "SubAgentLauncher", '{"query":"调研"}', finished=True,
        result='{"result":"\\u6211\\u5b8c\\u6210\\u4e86\\n' + "x\\n" * 12 + '"}')
    compiled = compile_record(store.get(handle), 92, render_context())
    text = "\n".join(strip.text for strip in compiled.strips)
    assert "我完成了" in text and "\\u" not in text and "点击展开/收起" in text
    assert any(region.action is InteractionAction.TOGGLE_TOOL for region in compiled.regions)

def test_code_block_has_highlighted_rows_and_copy_region():
    store = TranscriptStore()
    handle = store.start_stream("s1", "Agent")
    store.append_stream_chunk("s1", "```python\nprint('hi')\n```")
    store.end_stream("s1")
    compiled = compile_record(store.get(handle), 92, render_context())
    assert any("print" in strip.text for strip in compiled.strips)
    regions = [r for r in compiled.regions if r.action is InteractionAction.COPY_CODE]
    assert len(regions) == 1 and regions[0].payload == "print('hi')"
```

The test file defines the context explicitly:

```python
def render_context() -> RenderContext:
    return RenderContext(Console(width=92, force_terminal=True, color_system="truecolor"))
```

Add exact semantic assertions for system, user/failed user, divider, alert, assistant reasoning, Markdown, all file statuses, supervisor, running tool, short result, and expanded long result.

- [ ] **Step 2: Confirm the missing-module red state**

Run: `.venv/bin/python -m pytest tests/test_tui_transcript_render.py -v`

Expected: FAIL because `transcript_render` does not exist.

- [ ] **Step 3: Implement immutable compiled rows and regions**

```python
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
        return RenderContext(Console(width=self.console.width, force_terminal=True,
            color_system=self.console.color_system, legacy_windows=False))

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
        block, offset = divmod(index, 128)
        return self.blocks[block][offset]

def render_rows(renderable: RenderableType, width: int, context: RenderContext) -> tuple[Strip, ...]:
    options = context.console.options.update_width(width)
    lines = list(Segment.split_lines(context.console.render(renderable, options)))
    strips = Strip.from_lines(lines)
    return tuple(strip.crop_extend(0, width) for strip in strips) or (Strip.blank(width),)
```

Reuse the legacy `Text`, `Panel`, `Markdown`, and `Syntax(theme="monokai", word_wrap=True)` construction. Tool results run through `format_tool_payload(..., is_result=True)` before the eight-line collapse rule. Render a primary-colored `复制` region in the same right-side space as the current button. While `status == "streaming"`, compile only the last 2,000 content and 800 reasoning characters with the existing clipping labels; a finished record compiles its full strings. Split results over 256 rows into immutable 128-row blocks.

- [ ] **Step 4: Compare every compiled case to the reviewed fixture**

Adapt `test_tui_visual_regression.py` to compare compiler semantic segments with the legacy fixture normalization. Do not regenerate the fixture. Run `.venv/bin/python -m pytest tests/test_tui_transcript_render.py tests/test_tui_visual_regression.py -v` and expect PASS.

- [ ] **Step 5: Commit without changing the fixture**

```bash
git diff --exit-code -- tests/fixtures/tui_visual_baseline.json
git status --short -- cloudra/tui/new/transcript_render.py tests/test_tui_transcript_render.py tests/test_tui_visual_regression.py
git commit --only -m "feat(tui): compile transcript records to styled rows" -- cloudra/tui/new/transcript_render.py tests/test_tui_transcript_render.py tests/test_tui_visual_regression.py
```

---

### Task 6: Bound Background Compilation and Coalesce Frames

**Files:**
- Modify: `cloudra/tui/new/transcript_render.py`
- Create: `cloudra/tui/new/frame_scheduler.py`
- Modify: `tests/test_tui_transcript_render.py`
- Create: `tests/test_tui_frame_scheduler.py`

**Interfaces:**
- Consumes: synchronous `compile_record`, a Textual owner, record revision, width, and generation.
- Produces: `CompilationResult`, `PresentationCompiler.compile(...) -> Awaitable[CompilationResult]`, `close`, and `FrameScheduler.request`, `flush`, `cancel`, `pending`.

- [ ] **Step 1: Write failing scheduler/compiler tests**

```python
class FakeTimer:
    def __init__(self, owner, callback):
        self.owner, self.callback, self.stopped = owner, callback, False
    def stop(self):
        self.stopped = True

class FakeTimerOwner:
    def __init__(self):
        self.timers, self.next_callbacks = [], []
    @property
    def pending_timer_count(self):
        return sum(not timer.stopped for timer in self.timers)
    def set_timer(self, delay, callback):
        timer = FakeTimer(self, callback); self.timers.append(timer); return timer
    def call_next(self, callback, *args):
        self.next_callbacks.append(lambda: callback(*args))
    def run_next_callbacks(self):
        for callback in self.next_callbacks[:]: callback()
        self.next_callbacks.clear()

def test_repeated_requests_keep_one_pending_frame():
    owner = FakeTimerOwner()
    calls = []
    scheduler = FrameScheduler(owner, lambda: calls.append("frame"), max_fps=20)
    scheduler.request(); scheduler.request(); scheduler.request()
    assert owner.pending_timer_count == 1 and scheduler.pending
    scheduler.request(immediate=True)
    owner.run_next_callbacks()
    assert calls == ["frame"] and not scheduler.pending

@pytest.mark.asyncio
async def test_compilation_result_carries_stale_rejection_identity():
    store = TranscriptStore()
    handle = store.append_user("s1", "hello")
    record = store.get(handle)
    context = RenderContext(Console(width=80, force_terminal=True, color_system="truecolor"))
    compiler = PresentationCompiler(max_workers=2)
    result = await compiler.compile(record, 80, context, generation=7)
    assert (result.record_id, result.revision, result.width, result.generation) == (record.record_id, record.revision, 80, 7)
    await compiler.close()
```

- [ ] **Step 2: Confirm missing-type failures**

Run: `.venv/bin/python -m pytest tests/test_tui_frame_scheduler.py tests/test_tui_transcript_render.py -k "pending_frame or stale_rejection" -v`

Expected: FAIL for absent `FrameScheduler` and `PresentationCompiler`.

- [ ] **Step 3: Implement a one-shot 20 FPS scheduler**

```python
class FrameScheduler:
    def __init__(self, owner, callback, max_fps: int = 20) -> None:
        self._owner, self._callback = owner, callback
        self._interval, self._last_flush = 1.0 / max_fps, 0.0
        self._timer, self._immediate_pending, self._generation = None, False, 0

    @property
    def pending(self) -> bool:
        return self._timer is not None or self._immediate_pending

    def request(self, *, immediate: bool = False) -> None:
        if immediate:
            self.cancel()
            if not self._immediate_pending:
                self._immediate_pending = True
                generation = self._generation
                self._owner.call_next(self._flush_if_current, generation)
            return
        if self._timer is None and not self._immediate_pending:
            delay = max(0.0, self._interval - (time.monotonic() - self._last_flush))
            generation = self._generation
            self._timer = self._owner.set_timer(delay, lambda: self._flush_if_current(generation))

    def _flush_if_current(self, generation: int) -> None:
        if generation == self._generation:
            self.flush()

    def flush(self) -> None:
        self._timer = None
        self._immediate_pending = False
        self._last_flush = time.monotonic()
        self._callback()

    def cancel(self) -> None:
        self._generation += 1
        if self._timer is not None:
            self._timer.stop()
        self._timer, self._immediate_pending = None, False
```

- [ ] **Step 4: Implement a two-worker compiler with deterministic shutdown**

```python
@dataclass(frozen=True, slots=True)
class CompilationResult:
    compiled: CompiledRecord
    generation: int

    @property
    def record_id(self): return self.compiled.record_id
    @property
    def revision(self): return self.compiled.revision
    @property
    def width(self): return self.compiled.width

class PresentationCompiler:
    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="cloudra-tui-render")
        self._closed = False

    async def compile(self, record, width, context, generation) -> CompilationResult:
        if self._closed:
            raise RuntimeError("presentation compiler is closed")
        loop = asyncio.get_running_loop()
        compiled = await loop.run_in_executor(self._executor, compile_record, record, width, context.for_worker())
        return CompilationResult(compiled=compiled, generation=generation)

    async def close(self) -> None:
        self._closed = True
        await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=True)
```

The blocking thread join occurs in the default executor, so the Textual event loop stays runnable while shutdown becomes deterministic.

- [ ] **Step 5: Verify and commit the bounded asynchronous layer**

Run: `.venv/bin/python -m pytest tests/test_tui_frame_scheduler.py tests/test_tui_transcript_render.py -v`

Expected: PASS and no `cloudra-tui-render` thread remains after cleanup.

```bash
git status --short -- cloudra/tui/new/frame_scheduler.py cloudra/tui/new/transcript_render.py tests/test_tui_frame_scheduler.py tests/test_tui_transcript_render.py
git commit --only -m "feat(tui): bound row compilation and frame scheduling" -- cloudra/tui/new/frame_scheduler.py cloudra/tui/new/transcript_render.py tests/test_tui_frame_scheduler.py tests/test_tui_transcript_render.py
```

---

### Task 7: Build the Single-Widget Virtual Chat View

**Files:**
- Create: `cloudra/tui/new/widgets/virtual_chat_log.py`
- Create: `tests/test_tui_performance.py`

**Interfaces:**
- Consumes: Tasks 2–6.
- Produces: `ChatLog(ScrollView)`, append/filter/rename/clear facades, `has_records`, `record_count`, `records_for_session`, `text_for_session`, `visible_record_ids`, `batch_update`, `request_frame`, `ensure_compiled`, and `reveal`.

- [ ] **Step 1: Write the failing constant-DOM/addressability test**

```python
from cloudra.tui.new.widgets.virtual_chat_log import ChatLog as VirtualChatLog

class ChatOnlyApp(App):
    def compose(self):
        yield VirtualChatLog(id="chat-log")

@pytest.mark.asyncio
async def test_virtual_chat_dom_is_constant_for_one_thousand_records():
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)) as pilot:
        chat = app.query_one("#chat-log", VirtualChatLog)
        for index in range(1_000):
            chat.append_system(f"a-{index % 16}_task", f"event-{index}")
        await pilot.pause()
        assert chat.record_count == 1_000
        assert len(chat.children) == 0
        assert chat.virtual_size.height >= 1_000
        assert "event-999" in "\n".join(r.content for r in chat.store.records)
```

Add a test that scrolls to first, middle, and last virtual positions and reads the expected row through `render_line`.

- [ ] **Step 2: Confirm the missing-view red state**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-tests .venv/bin/python -m pytest tests/test_tui_performance.py -v`

Expected: FAIL because `cloudra.tui.new.widgets.virtual_chat_log` does not exist.

- [ ] **Step 3: Implement Line API state and row lookup**

```python
class ChatLog(ScrollView, can_focus=True):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.store = TranscriptStore()
        self._visible_ids: list[int] = []
        self._positions: dict[int, int] = {}
        self._heights = HeightIndex()
        self._compiled: OrderedDict[tuple[int, int, int], CompiledRecord] = OrderedDict()
        self._compile_tasks: dict[int, asyncio.Task] = {}
        self._generation = 0
        self._frame_scheduler = FrameScheduler(self, self._flush_frame, max_fps=20)

    MAX_CACHED_ROWS = 4_096
    OVERSCAN_ROWS = 24

    def render_line(self, y: int) -> Strip:
        width = self.scrollable_content_region.width
        absolute_y = int(self.scroll_y) + y
        try:
            index, row = self._heights.locate(absolute_y)
        except IndexError:
            return Strip.blank(width, self.rich_style)
        compiled = self._compiled_for(self._visible_ids[index], width)
        return Strip.blank(width, self.rich_style) if compiled is None else compiled.row(row).crop_extend(0, width, self.rich_style)
```

Unknown records start at estimated height one. `_rebuild_visible` filters store records, rebuilds positions/heights, updates `virtual_size`, and schedules the viewport plus 24 overscan rows. Valid results update one height and a 4,096-row LRU budget; stale revision/width/generation results are ignored. A newer revision cancels the older pending compile for that record, so active streams are latest-wins. Resize bumps generation, prioritizes the visible rows, and preserves old measured heights until replacements arrive. Refresh uses `layout=False`.

- [ ] **Step 4: Add the current append/filter/clear facade**

```python
def append_user(self, session_id: str, content: str, *, message_id: str | None = None) -> TranscriptHandle:
    handle = self.store.append_user(session_id, content, message_id=message_id)
    self._accept_change(self.store.last_change, immediate=True)
    return handle

def append_system(self, session_id: str, content: str) -> TranscriptHandle:
    return self._accept_handle(self.store.append_system(session_id, content))

def append_tool(self, session_id: str, tool: str, arguments: str, finished: bool = False, result: str | None = None) -> TranscriptHandle:
    return self._accept_handle(self.store.append_tool(session_id, tool, arguments, finished=finished, result=result))

def append_stream_chunk(self, session_id: str, delta: str, agent_name: str | None = None) -> TranscriptHandle:
    return self._accept_handle(self.store.append_stream_chunk(session_id, delta, agent_name or "Agent"))

def end_stream(self, session_id: str) -> TranscriptHandle | None:
    handle = self.store.end_stream(session_id)
    return None if handle is None else self._accept_handle(handle, immediate=True)

def show_agent(self, agent_id: str | None) -> None:
    self._view_agent_prefix, self._view_session_id = agent_id, None
    self._rebuild_visible(preserve_anchor=True)

@contextmanager
def batch_update(self):
    self._batch_depth += 1
    try:
        with self.store.batch():
            yield self
    finally:
        self._batch_depth -= 1
        if self._batch_depth == 0 and self._batched_change is not None:
            self._apply_batched_change()
```

`append_reasoning_chunk`, `append_divider`, `append_alert`, `append_file_change`, and `append_supervisor_review` use their same-named store methods through `_accept_handle`. `show_session` mirrors `show_agent`; `rename_session`, `clear_session`, and `clear_all` invoke the same-named store mutation and then `_accept_change`. None may mount a child.

`on_unmount` cancels the frame scheduler and every compile task, then awaits `PresentationCompiler.close()` through a Textual worker/task that cannot block teardown.

- [ ] **Step 5: Verify and commit the independent view**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-tests .venv/bin/python -m pytest tests/test_tui_performance.py tests/test_tui_transcript.py tests/test_tui_virtual_lines.py tests/test_tui_transcript_render.py -v`

Expected: PASS.

```bash
git status --short -- cloudra/tui/new/widgets/virtual_chat_log.py tests/test_tui_performance.py
git commit --only -m "feat(tui): add single-widget virtual chat view" -- cloudra/tui/new/widgets/virtual_chat_log.py tests/test_tui_performance.py
```

---

### Task 8: Preserve Scroll, Tool, Code-Copy, and Long-Reply Interactions

**Files:**
- Create: `cloudra/tui/new/clipboard.py`
- Modify: `cloudra/tui/new/widgets/virtual_chat_log.py`
- Modify: `tests/test_tui_performance.py`

**Interfaces:**
- Consumes: `InteractionRegion`, `ScrollAnchor`, and current clipboard command order.
- Produces: anchor capture/restore, click and keyboard activation, `reveal`, and `copy_to_clipboard(text) -> None`.

- [ ] **Step 1: Write failing interaction, anchor, and long-response tests**

```python
@pytest.mark.asyncio
async def test_virtual_tool_toggle_and_code_copy(monkeypatch):
    copied = []
    monkeypatch.setattr("cloudra.tui.new.widgets.virtual_chat_log.copy_to_clipboard", copied.append)
    app = ChatOnlyApp()
    async with app.run_test(size=(100, 36)):
        chat = app.query_one(VirtualChatLog)
        tool = chat.append_tool("s1", "Bash", "ls", finished=True, result="\n".join(map(str, range(30))))
        code = chat.start_stream("s1", "Agent")
        chat.append_stream_chunk("s1", "```python\nprint('hi')\n```"); chat.end_stream("s1")
        await chat.ensure_compiled(tool); await chat.ensure_compiled(code)
        await chat.activate_region(tool, InteractionAction.TOGGLE_TOOL)
        assert not chat.store.get(tool).collapsed
        await chat.activate_region(code, InteractionAction.COPY_CODE)
        assert copied == ["print('hi')"]
```

Add tests for append while scrolled up, resize while anchored inside a long record, forced optimistic-user reveal, and reachability of both ends of a 25,000-character final response.

- [ ] **Step 2: Confirm absent interaction behavior**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-tests .venv/bin/python -m pytest tests/test_tui_performance.py -k "tool_toggle or anchor or long" -v`

Expected: FAIL on missing activation/anchor methods.

- [ ] **Step 3: Move copying off the UI loop**

```python
def copy_to_clipboard(text: str) -> None:
    commands = (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["pbcopy"], ["clip"])
    for command in commands:
        try:
            subprocess.run(command, input=text, text=True, check=True)
            return
        except (FileNotFoundError, subprocess.CalledProcessError, OSError):
            continue
    raise RuntimeError("未找到可用的剪贴板工具（xclip/xsel/pbcopy/clip）")
```

Tool activation toggles synchronously. Code activation uses `await asyncio.to_thread(copy_to_clipboard, payload)` and current notification text.

- [ ] **Step 4: Implement anchor-aware updates and hit testing**

```python
def capture_anchor(self) -> ScrollAnchor | None:
    if self.scroll_y >= self.max_scroll_y - 2 or not self._visible_ids:
        return None
    index, offset = self._heights.locate(int(self.scroll_y))
    return ScrollAnchor(self._visible_ids[index], offset)

def _restore_or_follow(self, anchor: ScrollAnchor | None) -> None:
    if anchor is None:
        self.scroll_end(animate=False, immediate=True, x_axis=False)
    else:
        self.scroll_to(y=restore_anchor(anchor, self._visible_ids, self._heights), animate=False, immediate=True)

async def reveal(self, handle: TranscriptHandle, *, force: bool = True) -> None:
    await self.ensure_compiled(handle)
    index = self._positions[handle.record_id]
    region = Region(0, self._heights.row_start(index), self.size.width, self._heights.height(index))
    self.scroll_to_region(region, force=force, immediate=True, x_axis=False)
    await asyncio.sleep(0)
```

Mouse coordinates use `event.offset.y + int(scroll_y)` through `HeightIndex`; subtract the record start before checking regions. Tab/Shift+Tab cycle visible regions and Enter calls `activate_region`; no focus marker is rendered while the chat itself lacks focus.

- [ ] **Step 5: Verify and commit interactions**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-tests .venv/bin/python -m pytest tests/test_tui_performance.py tests/test_tui_transcript_render.py tests/test_tui_visual_regression.py -v`

Expected: PASS with unchanged visual fixture and fully reachable long content.

```bash
git status --short -- cloudra/tui/new/clipboard.py cloudra/tui/new/widgets/virtual_chat_log.py tests/test_tui_performance.py
git commit --only -m "feat(tui): preserve virtual transcript interactions" -- cloudra/tui/new/clipboard.py cloudra/tui/new/widgets/virtual_chat_log.py tests/test_tui_performance.py
```

---

### Task 9: Reduce IPC Bursts Without Crossing Ordering Boundaries

**Files:**
- Modify: `cloudra/tui/new/render_bridge.py`
- Create: `tests/test_tui_render_bridge_batching.py`
- Modify: `tests/test_textual_tui.py`

**Interfaces:**
- Consumes: the conversation event queue and existing synchronous `_dispatch` behavior.
- Produces: `reduce_event_batch(messages) -> list[dict]`, `MAX_BATCH_SECONDS = 0.004`, `MAX_BATCH_MESSAGES = 256`, and a bounded `_loop`.

- [ ] **Step 1: Write the failing adjacency/order test**

```python
def chunk(session_id: str, stream: str, delta: str) -> dict:
    return {"kind":"session_event", "session_id":session_id, "event_type":"llm_chunk",
        "data":{"agent_name":"Agent", "stream":stream, "delta":delta}}

def tool_started(session_id: str, tool: str) -> dict:
    return {"kind":"session_event", "session_id":session_id, "event_type":"tool_started",
        "data":{"tool":tool, "arguments":""}}

def event_type(message: dict) -> str:
    return str(message.get("event_type") or message.get("kind"))

def test_reducer_merges_only_adjacent_compatible_chunks():
    messages = [
        chunk("s1", "content", "a"), chunk("s1", "content", "b"),
        tool_started("s1", "Bash"), chunk("s1", "content", "c"),
        chunk("s2", "reasoning", "d"), chunk("s2", "reasoning", "e"),
    ]
    reduced = reduce_event_batch(messages)
    assert [event_type(m) for m in reduced] == ["llm_chunk", "tool_started", "llm_chunk", "llm_chunk"]
    assert [m["data"].get("delta") for m in (reduced[0], reduced[2], reduced[3])] == ["ab", "c", "de"]
```

Add approval, interaction, user-message, stream-end, failure, completion, tool, and session-state cases; their relative order must be byte-for-byte unchanged.

- [ ] **Step 2: Confirm missing reducer failure**

Run: `.venv/bin/python -m pytest tests/test_tui_render_bridge_batching.py -v`

Expected: FAIL because `reduce_event_batch` is absent.

- [ ] **Step 3: Implement adjacency-preserving chunk reduction**

```python
def stream_key(message: dict) -> tuple[str, str, str] | None:
    if message.get("kind") != "session_event" or message.get("event_type") != "llm_chunk":
        return None
    data = message.get("data") or {}
    return str(message.get("session_id") or ""), str(data.get("stream") or "content"), str(data.get("agent_name") or "Agent")

def reduce_event_batch(messages: Iterable[dict]) -> list[dict]:
    reduced: list[dict] = []
    for message in messages:
        key = stream_key(message)
        if reduced and key is not None and stream_key(reduced[-1]) == key:
            merged = copy.deepcopy(reduced[-1])
            merged["data"]["delta"] = str(merged["data"].get("delta", "")) + str((message.get("data") or {}).get("delta", ""))
            reduced[-1] = merged
        else:
            reduced.append(message)
    return reduced
```

- [ ] **Step 4: Bound queue draining by time and count**

```python
async def _loop(self) -> None:
    while True:
        batch = [await self._queue.get()]
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.MAX_BATCH_SECONDS
        while len(batch) < self.MAX_BATCH_MESSAGES and loop.time() < deadline:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        for message in reduce_event_batch(batch):
            try:
                self._dispatch(message)
            except Exception:
                logger.exception("TUI event dispatch failed: %s", message.get("event_type") or message.get("kind"))
        if not self._queue.empty():
            await asyncio.sleep(0)
```

Keep `_dispatch` immediate for replay/tests. `stop` cancels the task and sets both queue and task references to `None`.

- [ ] **Step 5: Verify and commit batching**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-tests .venv/bin/python -m pytest tests/test_tui_render_bridge_batching.py tests/test_textual_tui.py -k "render_bridge or routes_token or user_message_event" -v`

Expected: PASS; a permanently non-empty fake queue proves control is yielded between batches.

```bash
git status --short -- cloudra/tui/new/render_bridge.py tests/test_tui_render_bridge_batching.py tests/test_textual_tui.py
git commit --only -m "perf(tui): reduce IPC bursts within frame budgets" -- cloudra/tui/new/render_bridge.py tests/test_tui_render_bridge_batching.py tests/test_textual_tui.py
```

---

### Task 10: Switch MainScreen to the Virtual Transcript and Bulk History

**Files:**
- Modify: `cloudra/tui/new/widgets/chat_log.py`
- Modify: `cloudra/tui/new/screens/main_screen.py`
- Modify: `cloudra/tui/new/widgets/__init__.py`
- Modify: `tests/test_textual_tui.py`
- Modify: `tests/test_tui_visual_regression.py`
- Modify: `tests/test_tui_performance.py`

**Interfaces:**
- Consumes: virtual `ChatLog`, `TranscriptHandle`, `batch_update`, `has_records`, `reveal`, and `RenderBridge.replay_event`.
- Produces: the existing `ChatLog` import, immediate optimistic echo, one-frame history replay, and tests that observe data/rows rather than child Widgets.

- [ ] **Step 1: Rewrite selected tests to the new observable contract**

```python
@pytest.mark.asyncio
async def test_bridge_keeps_one_assistant_result_and_one_finished_tool():
    class ChatOnlyApp(App):
        def compose(self):
            yield ChatLog(id="chat-log")

    app = ChatOnlyApp()
    async with app.run_test() as pilot:
        chat = app.query_one(ChatLog)
        bridge = RenderBridge("conv-test", chat)
        def dispatch(event_type, data):
            bridge._dispatch({"kind":"session_event", "session_id":"s1", "event_type":event_type, "data":data})
        dispatch("llm_chunk", {"agent_name":"Agent", "stream":"content", "delta":"你好"})
        dispatch("llm_stream_end", {})
        dispatch("tool_started", {"tool":"Bash", "arguments":"ls"})
        dispatch("tool_finished", {"tool":"Bash", "arguments":"ls", "result":"file.txt"})
        dispatch("completed", {"result":"你好"})
        await pilot.pause()
        records = chat.records_for_session("s1")
        assert sum("你好" in r.content for r in records) == 1
        assert any(r.kind is RecordKind.TOOL and r.result == "file.txt" for r in records)
```

Replace every `_messages`, `_order`, `_stream_widget`, `ToolCard`, `CodeBlock`, and child-`display` assertion with record content/kind/state, compiled segments, visible IDs, hit activation, or constant children. Preserve the original user-visible assertion in each test.

- [ ] **Step 2: Confirm migrated tests fail against the legacy import**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-tests .venv/bin/python -m pytest tests/test_textual_tui.py -k "bridge_keeps or send_echoes or history_replay or sidebar_agent or tool_card or code_block" -v`

Expected: FAIL because the legacy view lacks the virtual contract.

- [ ] **Step 3: Export the virtual class and migrate record handles**

```python
# cloudra/tui/new/widgets/chat_log.py
from cloudra.tool_presentation import format_tool_payload
from cloudra.tui.new.widgets.virtual_chat_log import ChatLog

_format_tool_payload = format_tool_payload
__all__ = ["ChatLog", "_format_tool_payload"]
```

In MainScreen use `chat_log.has_records`, call `chat_log.mark_send_failed(handle)` on send failure, and replace Widget reveal code with:

```python
@staticmethod
async def _present_user_echo(chat_log: ChatLog, handle: TranscriptHandle) -> None:
    await chat_log.reveal(handle, force=True)
```

- [ ] **Step 4: Bulk-read and bulk-apply history**

```python
async def _load_history(self) -> None:
    generation = self._view_generation
    snapshot = await asyncio.to_thread(self._read_history_snapshot, self.conversation_id)
    if generation != self._view_generation or snapshot.conversation_id != self.conversation_id:
        return
    chat_log = self.query_one("#chat-log", ChatLog)
    with chat_log.batch_update():
        for task in snapshot.tasks:
            chat_log.append_divider(task.root_session_id, task.label)
            if task.query:
                chat_log.append_user(task.root_session_id, task.query)
            for session_id, event_type, data in task.events:
                self._render_bridge.replay_event(session_id, event_type, data)
    chat_log.request_frame(immediate=True)
    chat_log.scroll_end(animate=False, immediate=True, x_axis=False)
```

`_read_history_snapshot` preserves the current grouping, per-session/total limits, labels, skip rules, and chronology, and returns frozen snapshot dataclasses rather than live database objects.

- [ ] **Step 5: Run complete TUI/visual/performance tests**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-tests .venv/bin/python -m pytest -s tests/test_textual_tui.py tests/test_tui_visual_regression.py tests/test_tui_performance.py -q`

Expected: PASS; no message children, user echo appears before backend resolution, history requests one frame, and fixture is unchanged.

- [ ] **Step 6: Commit the renderer switch**

```bash
git status --short -- cloudra/tui/new/widgets/chat_log.py cloudra/tui/new/screens/main_screen.py cloudra/tui/new/widgets/__init__.py tests/test_textual_tui.py tests/test_tui_visual_regression.py tests/test_tui_performance.py
git commit --only -m "refactor(tui): switch main screen to virtual transcript" -- cloudra/tui/new/widgets/chat_log.py cloudra/tui/new/screens/main_screen.py cloudra/tui/new/widgets/__init__.py tests/test_textual_tui.py tests/test_tui_visual_regression.py tests/test_tui_performance.py
```

---

### Task 11: Reconcile the Side Panel and Pause Idle Status Work

**Files:**
- Modify: `cloudra/tui/new/widgets/side_panel.py`
- Modify: `cloudra/tui/new/widgets/status_bar.py`
- Modify: `cloudra/tui/new/screens/main_screen.py`
- Modify: `tests/test_textual_tui.py`
- Modify: `tests/test_tui_performance.py`

**Interfaces:**
- Consumes: current panel row data, selected IDs, reactive status, and MainScreen view generation.
- Produces: stable-ID reconciliation, idle-paused status timer, cancelable one-shot side/plan tasks, and stale-result rejection.

- [ ] **Step 1: Write failing identity, idle, and stale-generation tests**

```python
class SidePanelApp(App):
    def compose(self):
        yield SidePanel(id="side-panel")

class StatusApp(App):
    def compose(self):
        yield StatusBar(id="status-bar")

@pytest.mark.asyncio
async def test_side_panel_keeps_row_when_only_state_changes():
    app = SidePanelApp()
    async with app.run_test() as pilot:
        panel = app.query_one(SidePanel)
        panel.set_agents([{"agent_id":"a-1", "name":"worker", "state":"queued"}]); await pilot.pause()
        original = panel.agent_item("a-1")
        panel.set_agents([{"agent_id":"a-1", "name":"worker", "state":"running"}]); await pilot.pause()
        assert panel.agent_item("a-1") is original
        assert "运行中" in str(original.query_one(Label).content)

@pytest.mark.asyncio
async def test_status_timer_pauses_while_idle():
    app = StatusApp()
    async with app.run_test():
        bar = app.query_one(StatusBar)
        assert not bar._timer._active.is_set()
        bar.session_state = "running"; assert bar._timer._active.is_set()
        bar.session_state = "completed"; assert not bar._timer._active.is_set()
```

Add a test releasing an old `_refresh_agents` result after `_activate_conversation`; it must not mutate the new panel.

- [ ] **Step 2: Confirm row replacement and active-idle-timer failures**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-tests .venv/bin/python -m pytest tests/test_textual_tui.py tests/test_tui_performance.py -k "keeps_row or status_timer or stale" -v`

Expected: FAIL for current full-list rebuild and always-active interval.

- [ ] **Step 3: Reconcile rows by stable IDs**

```python
def _reconcile(self, list_view: ListView, specs: list[RowSpec], cache: dict[str | None, ListItem]) -> None:
    incoming = [spec.key for spec in specs]
    current = [getattr(item, "row_key") for item in list_view.children]
    if incoming != current:
        items = [self._item_for(spec, cache) for spec in specs]
        list_view.clear()
        list_view.extend(items)
    else:
        for spec in specs:
            item = cache[spec.key]
            label = item.query_one(Label)
            if str(label.content) != spec.text:
                label.update(spec.text)
```

Use separate Agent and conversation caches, restore selected index by key after a structural rebuild, expose `agent_item(agent_id)`, and skip `set_plan` when its text is identical.

- [ ] **Step 4: Pause status and make one-shot refreshes generation-safe**

```python
def on_mount(self) -> None:
    self._timer = self.set_interval(_REFRESH_INTERVAL, self._tick, pause=True)
    self._sync_timer()
    self._refresh()

def _sync_timer(self) -> None:
    active = self.session_state in _ACTIVE_STATES or bool(self.compaction_info)
    (self._timer.resume if active else self._timer.pause)()

def _schedule_plan_refresh(self) -> None:
    if self._plan_refresh_task and not self._plan_refresh_task.done():
        return
    generation = self._view_generation
    self._plan_refresh_task = asyncio.create_task(self._refresh_plan_later(generation))
```

`_refresh_plan_later` and the equivalent sidebar task check generation and `is_mounted` after debounce/read. Cancel stored handles on unmount and conversation activation.

- [ ] **Step 5: Verify and commit peripheral responsiveness**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-tests .venv/bin/python -m pytest -s tests/test_textual_tui.py tests/test_tui_performance.py -q`

Expected: PASS and five simulated idle seconds cause zero transcript/sidebar/plan/status repaint.

```bash
git status --short -- cloudra/tui/new/widgets/side_panel.py cloudra/tui/new/widgets/status_bar.py cloudra/tui/new/screens/main_screen.py tests/test_textual_tui.py tests/test_tui_performance.py
git commit --only -m "perf(tui): reconcile panels and suspend idle work" -- cloudra/tui/new/widgets/side_panel.py cloudra/tui/new/widgets/status_bar.py cloudra/tui/new/screens/main_screen.py tests/test_textual_tui.py tests/test_tui_performance.py
```

---

### Task 12: Remove Synchronous Store Work from Live TUI Commands

**Files:**
- Modify: `cloudra/service.py`
- Modify: `cloudra/tui/new/screens/main_screen.py`
- Modify: `tests/test_service.py`
- Modify: `tests/test_textual_tui.py`

**Interfaces:**
- Consumes: current idempotent control-store operations and event-loop ownership of `SessionRunner._execute`.
- Produces: `SessionRunner.submit_async`, `CloudraService.submit_session_async`, `PreparedAppend`, and nonblocking TUI paths for submit, follow-up, cancel, approval, interaction response, listing, and context refresh.

- [ ] **Step 1: Write failing loop-progress tests with deliberately slow stores**

```python
@pytest.mark.asyncio
async def test_submit_session_async_does_not_block_event_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path / "data"))
    reload_config()
    get_config()._ensure_dirs()
    service = CloudraService()
    original = service.session_runner._prepare_submission
    def slow_prepare(*args, **kwargs):
        time.sleep(0.15)
        return original(*args, **kwargs)
    monkeypatch.setattr(service.session_runner, "_prepare_submission", slow_prepare)
    progressed = asyncio.Event()
    asyncio.get_running_loop().call_later(0.02, progressed.set)
    submit = asyncio.create_task(service.submit_session_async("hello", "conv_async"))
    await asyncio.wait_for(progressed.wait(), timeout=0.08)
    _, record = await submit
    assert record.session_id.startswith("a-0_run_")
```

For append, cancel, and interaction response, patch their synchronous control-store phase to sleep 150 ms and assert a 20 ms loop callback runs first. Add the same progress assertion around the already-async approval path without converting it back to synchronous SQLite. Retain all existing idempotency assertions.

- [ ] **Step 2: Confirm missing asynchronous boundaries**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-service-tests .venv/bin/python -m pytest tests/test_service.py -k "does_not_block_event_loop" -v`

Expected: FAIL because asynchronous submission and isolated synchronous phases are absent.

- [ ] **Step 3: Split submission preparation from loop-owned scheduling**

```python
def _prepare_submission(self, query: str, conversation_id: str, session_id: str, **route) -> tuple[SessionRecord, bool]:
    db = ConversationDB(conversation_id).init()
    existing = self.get(conversation_id, session_id)
    if existing is not None:
        return existing, False
    session_store.insert_queued_session(db, session_id=session_id, agent_id="a-0", agent_type="coordinator",
        query=query, node_id=route.get("node_id"), workspace_id=route.get("workspace_id"),
        working_directory=route.get("working_directory"))
    self._emit(conversation_id, session_id, "queued", {"query": query, "yolo": route.get("yolo", False)})
    return self.get(conversation_id, session_id), True

async def submit_async(self, query: str, conversation_id: str, **kwargs) -> SessionRecord:
    session_id = kwargs.pop("session_id", None) or f"a-0_run_{uuid.uuid4().hex}"
    record, created = await asyncio.to_thread(self._prepare_submission, query, conversation_id, session_id, **kwargs)
    if created:
        task = asyncio.create_task(self._execute(query, conversation_id, session_id,
            kwargs.get("working_directory"), kwargs.get("yolo", False)))
        self._running[(conversation_id, session_id)] = task
    return record
```

Keep synchronous `submit` for non-TUI callers using the same preparation helper. Preserve `sqlite3.IntegrityError` duplicate recovery.

```python
async def submit_session_async(self, query: str, conversation_id: str | None = None,
    working_directory: str | None = None, yolo: bool = False) -> tuple[str, SessionRecord]:
    if conversation_id is None:
        conversation = await asyncio.to_thread(self.create_conversation)
        conversation_id = conversation.id
    else:
        validate_conversation_id(conversation_id)
    record = await self.session_runner.submit_async(query, conversation_id,
        working_directory=working_directory, yolo=yolo)
    return conversation_id, record
```

- [ ] **Step 4: Isolate each synchronous control-store phase**

```python
@dataclass(frozen=True, slots=True)
class PreparedAppend:
    conversation_id: str
    session_id: str
    agent_id: str
    command_id: str
    mode: Literal["inject", "resume", "existing"]
    content: str
    working_directory: str | None
    node_id: str | None
    workspace_id: str | None
    existing_record: SessionRecord | None

async def append_session_message_command(self, **request):
    prepared = await asyncio.to_thread(self._prepare_append_message, request)
    if prepared.mode == "existing":
        return await asyncio.to_thread(self._existing_append_result, prepared)
    if prepared.mode == "resume":
        record = await self.session_runner.submit_async(prepared.content, prepared.conversation_id,
            session_id=prepared.session_id, working_directory=prepared.working_directory,
            node_id=prepared.node_id, workspace_id=prepared.workspace_id)
    else:
        await ContextManager.inject_event(conversation_id=prepared.conversation_id,
            agent_id=prepared.agent_id, event_type="user_message",
            content=f"用户从远程控制台补充要求：{prepared.content}")
        record = await asyncio.to_thread(self.session_runner.get, prepared.conversation_id, prepared.session_id)
    return await asyncio.to_thread(self._finish_append_message, prepared, record)
```

Create equivalent `_prepare_cancel_sync`/`_finish_cancel_sync` and `_respond_interaction_sync` helpers. Each opens and closes its own database connection and returns frozen dataclasses/IDs; no connection crosses a thread boundary or `await`. Keep `ContextManager.inject_event`, the existing async approval method, `events.aemit`, and Agent task creation on the owning loop.

Update MainScreen to await `submit_session_async`, move `/list`'s direct `session_runner.list` to `asyncio.to_thread`, and retain immediate visual feedback before every live command await.

- [ ] **Step 5: Verify service/control/TUI behavior**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-service-tests .venv/bin/python -m pytest -s tests/test_service.py tests/test_control_commands.py tests/test_approval_wakeup.py tests/test_textual_tui.py -q`

Expected: PASS; every synthetic 150 ms store delay permits the event-loop callback to run.

- [ ] **Step 6: Commit asynchronous service boundaries**

```bash
git status --short -- cloudra/service.py cloudra/tui/new/screens/main_screen.py tests/test_service.py tests/test_textual_tui.py
git commit --only -m "perf(tui): offload live command store work" -- cloudra/service.py cloudra/tui/new/screens/main_screen.py tests/test_service.py tests/test_textual_tui.py
```

---

### Task 13: Remove Legacy Widgets and Prove the Full Contract

**Files:**
- Delete: `cloudra/tui/new/widgets/code_block.py`
- Modify: `cloudra/tui/new/widgets/chat_log.py`
- Modify: `cloudra/tui/new/widgets/virtual_chat_log.py`
- Modify: `scripts/profile_textual_tui.py`
- Modify: `tests/test_tui_performance.py`
- Modify: `tests/test_tui_visual_regression.py`
- Modify: `tests/test_textual_tui.py`
- Modify: `docs/superpowers/specs/2026-08-02-tui-virtualization-design.md`

**Interfaces:**
- Consumes: all preceding virtual TUI layers plus Task 1 baseline evidence.
- Produces: no legacy message Widgets/imports, enforced performance thresholds, complete verification evidence, and final implemented design status.

- [ ] **Step 1: Add the final failing workload contract**

```python
@pytest.mark.asyncio
async def test_reference_workload_meets_virtual_tui_contract():
    result = await run_profile(history_count=1_000, stream_count=16, rounds=30)
    assert result.child_count == 0
    assert result.record_count >= 1_016
    assert result.max_commit_seconds < 0.050
    assert result.input_p95_seconds < 0.100
    assert result.elapsed_seconds < 3.8892
```

Add deterministic assertions that 16 streams create exactly 16 active records, 30 rounds leave at most one pending frame, hidden streams refresh no visible row, repeated runs leave no compiler task/thread growth, five idle seconds perform zero periodic data refresh, and both ends of 25,000-character content remain reachable.

- [ ] **Step 2: Run the contract before cleanup and inspect the red evidence**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-profile .venv/bin/python -m pytest tests/test_tui_performance.py::test_reference_workload_meets_virtual_tui_contract -v`

Expected: FAIL if any remaining legacy work/cache/scheduler behavior misses the agreed target. Diagnose the measured cause; do not relax thresholds or truncate content.

- [ ] **Step 3: Remove all legacy message-Widget code**

Delete `code_block.py`, `ToolCard`, `Static` message mounting, `MAX_WIDGETS`, `_messages`, `_order`, `_stream_widget`, stream refresh timers, and pruning. Run `rg -n "ToolCard|CodeBlock|MAX_WIDGETS|_stream_widget|_prune_widgets|VerticalScroll" cloudra/tui/new` and expect no matches.

- [ ] **Step 4: Run and enforce the reference profile**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-profile .venv/bin/python scripts/profile_textual_tui.py --history 1000 --streams 16 --rounds 30 --assert-contract`

Expected JSON: elapsed below 3.8892 seconds, max commit below 0.050 seconds, input p95 below 0.100 seconds, child count zero, and no live compiler work after shutdown. If cProfile reports a main-thread function above 50 ms, write a focused failing test for that function and correct the measured cause before rerunning.

- [ ] **Step 5: Run focused behavior, visual, performance, and style checks**

```bash
XDG_RUNTIME_DIR=/tmp/cloudra-tui-tests .venv/bin/python -m pytest -s tests/test_tui_transcript.py tests/test_tui_virtual_lines.py tests/test_tui_transcript_render.py tests/test_tui_frame_scheduler.py tests/test_tui_render_bridge_batching.py tests/test_tui_performance.py tests/test_tui_visual_regression.py tests/test_textual_tui.py -q
.venv/bin/python -m compileall -q cloudra/tui/new cloudra/service.py tests scripts/profile_textual_tui.py
git diff --check -- cloudra/tui/new cloudra/service.py tests/test_tui_*.py tests/test_textual_tui.py scripts/profile_textual_tui.py docs/superpowers/specs/2026-08-02-tui-virtualization-design.md
```

Expected: all tests pass, the fixture is unchanged, bytecode compilation succeeds, and `git diff --check` reports no whitespace errors.

- [ ] **Step 6: Run the complete project suite**

Run outside the socket-restricted sandbox when required: `XDG_RUNTIME_DIR=/tmp/cloudra-full-tests .venv/bin/python -m pytest -s -q`

Expected: full suite passes. For a genuinely unrelated pre-existing failure, capture its exact test/traceback and reproduce it without the TUI patch; every in-scope failure must be fixed.

- [ ] **Step 7: Perform the interactive WSL terminal smoke test**

Run: `XDG_RUNTIME_DIR=/tmp/cloudra-tui-smoke .venv/bin/python -m cloudra.cli`

At 100x36 and after resizing, verify all reviewed visual cases, input during 16-Agent output, upward scroll, forced user echo, Agent/session filters, tool expand/collapse, keyboard code copy, approvals, `ask_user`, Esc cancel, sidebar switching, `/compact`, and a final response longer than 20,000 characters. Record terminal/WSL version and observed latency. If a real interactive terminal is unavailable, keep the goal incomplete and report the missing evidence.

- [ ] **Step 8: Record evidence and commit final cleanup**

Change the design status to `Implemented and verified`; append measured before/after JSON and test counts.

```bash
git status --short -- cloudra/tui/new/widgets/code_block.py cloudra/tui/new/widgets/chat_log.py cloudra/tui/new/widgets/virtual_chat_log.py scripts/profile_textual_tui.py tests/test_tui_performance.py tests/test_tui_visual_regression.py tests/test_textual_tui.py docs/superpowers/specs/2026-08-02-tui-virtualization-design.md
git commit --only -m "perf(tui): complete virtual renderer migration" -- cloudra/tui/new/widgets/code_block.py cloudra/tui/new/widgets/chat_log.py cloudra/tui/new/widgets/virtual_chat_log.py scripts/profile_textual_tui.py tests/test_tui_performance.py tests/test_tui_visual_regression.py tests/test_textual_tui.py docs/superpowers/specs/2026-08-02-tui-virtualization-design.md
```

Expected: no benchmark submodule or unrelated user file appears.

---

## Plan Self-Review

Every design requirement has an implementation task and an authoritative gate. Task 1 freezes current visuals and the profiler. Tasks 2–4 make complete content, ordering, filters, revisions, and geometry independent of Textual. Tasks 5–8 preserve styling and interactions while bounding background work and DOM. Task 9 constrains event bursts. Task 10 migrates history and user echo. Task 11 removes list/timer churn. Task 12 removes synchronous live-command store work. Task 13 deletes the old implementation and requires focused, full-suite, profile, and interactive evidence.

Cross-task names are consistent: `TranscriptHandle` and `TranscriptRecord` identify state; `CompiledRecord` and `InteractionRegion` identify presentation; `HeightIndex` and `ScrollAnchor` identify geometry; `PresentationCompiler` and `FrameScheduler` identify bounded work; the public view remains `ChatLog`; and the service boundary is `submit_session_async`.

The principal risks each have a rejection test: visual drift, variable-height jumps, stale compiler generations, burst backlog, incorrect hit regions, lost long content, stale conversation results, idle work, blocking SQLite phases, and hidden legacy imports. Process isolation stays outside this plan because measured Textual layout amplification is the dominant cause; only the post-refactor profile may justify a separate specification.
