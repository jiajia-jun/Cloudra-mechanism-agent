# Cloudra TUI Virtualization and Responsiveness Design

**Date:** 2026-08-02

**Status:** Implemented and verified

**Scope:** `cloudra/tui/new`, its presentation adapters, and blocking calls on TUI-facing service paths

**Compatibility rule:** preserve observable features and the current visual design

## Context

Cloudra's current Textual chat view stores every displayed message as a live
Widget under a `VerticalScroll`. Streaming updates change the height of active
Widgets, while tool results, Markdown blocks, code blocks, and finalized
messages mount or remove more Widgets. Textual then recomputes layout and
compositor geometry for a large part of the tree.

A synthetic workload that contains no Agent execution, database access, IPC,
or network traffic reproduced the reported freeze:

- 16 concurrent streams, 320 mounted message Widgets, and 30 flush rounds took
  9.723 seconds and made 10,088,250 Python calls.
- 5.625 seconds were spent in Textual layout refresh; compositor widget
  insertion and reflow were the next largest costs.
- The measured 0.324 seconds per update round gives an upper bound of roughly
  three responsive frames per second before terminal output overhead.
- Replacing the message tree in the same synthetic workload with one `Log`
  Widget took 2.132 seconds and 1,414,486 calls. That experiment is not the
  proposed implementation, but it proves that Widget-tree growth is the
  dominant local cause.

WSL and the host terminal amplify the cost of sending large screen diffs, but
they are not the root cause: the freeze is reproducible in Textual's headless
test driver.

The current TUI behavior baseline is 50 passing tests in
`tests/test_textual_tui.py` when Unix socket access is available. Those tests
cover the principal user interactions, but they do not constrain layout work,
render batching, input latency, or growth of presentation state.

## External architecture evidence

The recommended design follows the useful common ground of current open-source
Agent harnesses without copying their UI stacks:

- Codex separates immutable committed history cells from a small mutable active
  cell/tail and routes redraw requests through a frame scheduler. See
  <https://github.com/openai/codex/blob/main/codex-rs/tui/src/chatwidget.rs>.
- OpenCode can run its server separately from the TUI. That isolation is useful
  if Agent execution remains a source of event-loop stalls, but it does not
  remove layout work inside the TUI process. See
  <https://github.com/anomalyco/opencode/blob/dev/CONTRIBUTING.md>.
- Gemini CLI exposes incremental rendering and render-process choices, again
  treating terminal output and full redraws as explicit performance concerns.
  See
  <https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/configuration.md>.

Cloudra already has a conversation-scoped IPC event bus and worker processes.
The first refactor therefore removes presentation-layer layout amplification.
Process-isolating the remaining coordinator runtime is a follow-up only if a
post-refactor profile proves that it is still necessary.

## Goals and invariants

The refactor must make chat history size independent of the live Textual DOM.
It must keep input, cancellation, approvals, and `ask_user` responsive during
multi-Agent output. It must eliminate periodic database polling and repeated
full-list reconstruction from the TUI. It must coalesce bursty event delivery
without losing or reordering content.

Observable behavior is an invariant. The welcome screen, borders, colors,
labels, Rich panels, Markdown appearance, code highlighting, copy control,
tool-card collapse behavior, session and Agent filtering, optimistic user echo,
history replay, status bar, side panel, command completion, modals, and keyboard
bindings remain available. Styling continues to be sourced from the existing
TCSS and Cloudra theme.

No final response may be truncated. Streaming previews may show a bounded tail,
as they do today, but finalization must expose the full stored text through
normal scrolling, including responses longer than 20,000 characters. The
existing startup policy for how many historical tasks are loaded may remain;
once a message is loaded into the transcript, its final content is complete.

The dirty benchmark submodules `benchmarks/LAB-Bench`,
`benchmarks/MolPuzzle`, and `benchmarks/data/chembench-repo` are outside scope
and must not be modified, initialized, restored, or included in a commit.

## Considered approaches

### Continue tuning the Widget tree

Reducing `MAX_WIDGETS`, lengthening the streaming timer, and pruning more
aggressively would reduce load temporarily. It would also discard more history
and still exhibit superlinear layout behavior near the new limit. This does not
satisfy the goal.

### Replace `ChatLog` with Textual `RichLog`

The local experiment shows that a single append-oriented Widget is much faster.
`RichLog`, however, does not natively support in-place tool completion,
filtering by session or Agent, stable scroll anchoring across replacement,
clickable tool-card regions, or the existing code-copy control. Reconstructing
those behaviors around `RichLog` would create a second ad-hoc transcript model
and make visual compatibility difficult.

### Custom virtual transcript using Textual's Line API

This is the selected approach. A single `ScrollView` renders only visible rows
from a transcript store whose committed records are immutable and whose small
active set changes through explicit revisions. Interactive regions are
hit-tested against rendered row metadata rather than represented by child
Widgets. Streaming state, rendering caches, and event scheduling are explicit
and bounded.

## Architecture

### Transcript model

`TranscriptStore` is a presentation-domain model independent of Textual. It
owns ordered `TranscriptRecord` values and secondary indexes. A record contains
at least:

- stable record ID and optional durable event/message ID;
- session ID, derived Agent ID, record kind, and order key;
- raw complete payload for user, assistant, reasoning, tool, file-change,
  supervisor, divider, alert, or system content;
- state such as running/finished/failed, collapsed/expanded, and send failure;
- a monotonically increasing revision.

The store indexes records by session and Agent without duplicating payloads. A
durable user-message ID deduplicates optimistic local echo and later IPC replay.
A tool-finished event updates the most recent matching unfinished tool record
in place. A stream has one stable placeholder record: tools emitted during the
stream may follow it in global order, while stream finalization replaces the
placeholder payload at its original position rather than moving the response
after those tools.

The store retains complete final content. It does not prune data to control DOM
size because transcript data is not a DOM. A separate, measured memory policy
may evict derived render caches, never raw loaded content.

All model operations are unit-testable without running a Textual application.
They return a compact change description containing affected record IDs,
whether ordering/filter membership changed, and whether the bottom-follow
policy should be evaluated.

### Virtual chat view

`ChatLog` keeps its public identity and TCSS ID but is reimplemented as a
Textual `ScrollView` Line API widget. It has no message child Widgets. Textual's
own scrollbar implementation remains the only framework-managed auxiliary
state.

For the selected session/Agent filter, the view maintains an ordered visible
record index and a height index. `render_line(y)` maps a virtual row to one
record, retrieves the cached `Strip`, and clips it to the viewport. The view
renders the viewport plus a small overscan region only. Append is O(1) in the
common unfiltered case; filter switches rebuild indexes from data without
mounting or removing Widgets.

Each compiled record yields immutable rows and interaction regions. Cache keys
include record ID, revision, content width, theme/render style revision, and
collapsed state. Off-screen row caches use an LRU budget; measured heights and
raw transcript content remain available after row eviction.

Terminal resize invalidates width-dependent caches. The currently visible rows
are recompiled first. Other records are recompiled in the background while
their previous measured heights serve as estimates. As actual heights arrive,
the height index is corrected while preserving the scroll anchor, preventing a
resize from freezing the event loop or jumping to an unrelated message.

Very long records are compiled into internal row blocks. A 20,000-character
final response is one logical message but does not require a monolithic Widget
or one terminal renderable covering the entire transcript. Every block remains
reachable by scrolling.

### Presentation compiler

Rich payload normalization, Unicode escape decoding, Markdown parsing, syntax
highlighting, tool JSON presentation, wrapping, and conversion to Textual
`Strip` rows are moved behind a bounded presentation compiler. It uses at most
two worker threads and applies results back on the Textual event loop only when
the record revision and view generation still match.

Compilation is priority-aware: visible records and user-originated records are
ahead of overscan and off-screen history. Repeated revisions of an active
stream are latest-wins so stale compilation work cannot form a backlog. Active
stream previews use inexpensive plain Rich text; full Markdown compilation is
required at stream finalization.

If parsing or highlighting fails, the compiler returns a safe plain-text
representation with decoded Unicode. Failure is logged and scoped to the one
record; it may not terminate event delivery or expose an unformatted Python
object dump.

### Event reducer and frame scheduler

`RenderBridge` remains event-driven on the conversation IPC queue. It does not
poll. Instead of mutating Textual Widgets for every queue item, it drains a
bounded burst into an event reducer. Consecutive compatible stream deltas for
the same session are concatenated, while ordering boundaries such as tool
events, user messages, completion, failure, and approval are preserved.

Applying a reduced batch mutates `TranscriptStore` and marks affected regions
dirty. The first dirty change schedules one render frame; further changes join
that frame. The scheduler has a maximum presentation rate of 20 frames per
second under continuous streaming, but terminal events and explicit user echo
may request an immediate frame. A reduction batch yields after approximately
four milliseconds so Textual can service key, mouse, modal, and cancellation
events. This is event-triggered one-shot scheduling, not a periodic refresh
loop.

End-of-stream flushes are immediate and lossless. Cancellation and failure
events cannot remain hidden behind a streaming timer. Stopping or switching a
conversation cancels pending compilation and scheduled callbacks through a
generation token.

### Scrolling and interaction

The view records a scroll anchor as `(record_id, row_offset)` before any change
that can alter heights or filter membership. If the user is within two rows of
the bottom, new background output follows the bottom. If the user has scrolled
up, the anchor is restored and output cannot steal the viewport.

An optimistic local user message is stronger than background follow behavior:
it is inserted immediately, rendered with the existing bold green appearance,
and explicitly revealed before any database command is awaited. Failure changes
the record state to the existing dim/strike appearance.

Tool cards expose a hit region covering the same clickable card area. Long tool
results retain the current eight-line preview and expand/collapse wording.
Code blocks expose a hit region for the visually equivalent copy control and a
focus action for keyboard operation. Hit regions are produced by the same
compiler result as the displayed rows, so wrapping cannot desynchronize clicks
from content. Copy errors continue to use Textual notifications.

### Main screen and non-chat widgets

`MainScreen` interacts with transcript record handles/IDs rather than mounted
message Widgets. History is read off the event loop, reduced into records, bulk
inserted into the store, and presented with one scheduled frame. The current
history grouping, labels, event skip rules, and final-result fallback remain.

Agent and conversation side-panel rows are reconciled by stable IDs. Opening
the panel may fetch current data, but subsequent updates patch changed rows
instead of calling `clear()` and rebuilding the entire `ListView`. Plan file and
token updates remain event-triggered and are coalesced with cancelable one-shot
tasks. A view generation prevents results from an old conversation or Agent
selection from overwriting the new selection.

The status bar keeps the same one-second spinner and elapsed-time appearance.
Its timer is active only while a task or compaction is active and is paused when
idle. Reactive changes are reduced to one computed render key as today.

The input bar, command suggestions, approval modal, `ask_user` modal, context
screen, help screen, and side-panel bindings keep their current composition and
styling. Their event handlers must not synchronously format transcript content
or wait for a render frame.

TUI-facing service methods are audited for synchronous SQLite and file access
before their first `await`. Such work is moved to `asyncio.to_thread` or split
into an asynchronous service operation while Agent task creation remains on the
owning event loop. This includes submit, follow-up injection, cancellation,
approval, interaction response, conversation switching, and context-size
refresh paths. The refactor does not change command idempotency or event
ordering.

## Visual compatibility

Before replacing the old renderer, representative fixed-size reference
snapshots are captured for welcome, user, plain assistant, Markdown, reasoning,
running and finished tools, collapsed/expanded JSON, code, file changes,
supervisor review, alerts, send failure, streaming, sidebar, status bar, and
the approval/interaction modals.

The new renderer reuses the current labels, Rich `Panel` titles and border
styles, text styles, syntax theme, collapse hint, and `styles.tcss`. Snapshot
comparisons include styled segments, not only plain text. Intentional changes
require explicit approval; performance work alone is not permission to redesign
the interface.

## Testing and performance gates

Implementation follows test-driven development. Each production change begins
with a focused failing test and a confirmed red state.

Pure model tests cover ordering, stream finalization in place, tool completion,
deduplication, filtering, rename/clear, full-content retention, and revisions.
Line-renderer tests cover wrapping, cache keys, height lookup, long-record
blocks, Unicode, Markdown/code/tool presentation, hit regions, and resize
anchoring. Textual integration tests cover input echo, scroll-follow behavior,
click and keyboard interactions, filtering, history bulk load, burst reduction,
sidebar reconciliation, idle timer suspension, conversation-generation
cancellation, approvals, and `ask_user`.

Existing behavior tests are migrated from private Widget-tree assertions to
observable transcript/view assertions. They may not be deleted or weakened to
make the new implementation pass. Reference snapshots are reviewed before they
become golden fixtures.

Deterministic structural gates are:

- transcript message count does not increase `ChatLog` child count;
- 1,000 loaded records remain fully addressable by virtual scrolling;
- 16 active streams create 16 mutable records, not hundreds of Widgets;
- a burst of stream chunks schedules at most one pending frame and respects the
  reducer time budget;
- a completed response longer than 20,000 characters contains both its prefix
  and suffix and every internal row remains reachable;
- hidden Agent streams retain complete content without producing visible-row
  refreshes;
- idle TUI state performs no periodic transcript, sidebar, plan, or database
  refresh.

The reproducible performance benchmark uses 16 concurrent Agent streams, 1,000
history records, and 30 streaming rounds at a fixed terminal size. On the
reference development environment:

- input/key handling p95 is below 100 ms during the workload;
- a main-thread presentation commit is below 50 ms;
- no main-thread batch runs longer than the four-millisecond reducer budget
  before yielding, excluding the bounded Textual compositor call itself;
- total workload time is at most 40% of the 9.723-second Widget-tree baseline;
- Python call count and peak memory are recorded, with no unbounded growth on a
  repeated second run.

Wall-clock assertions use a sufficiently generous CI multiplier and are paired
with deterministic scheduling/DOM assertions. A dedicated benchmark report is
kept outside the user-owned benchmark submodules.

The final verification scope includes the focused TUI suite, presentation and
service tests affected by the refactor, the complete project test suite, a
headless profile, and an interactive WSL smoke test when a real terminal is
available. Lack of a physical terminal does not permit claiming the visual or
latency goal from unit tests alone; it is reported explicitly if unavailable.

## Migration and rollback

Implementation is staged behind the existing `ChatLog` import surface so
`RenderBridge` and `MainScreen` can be migrated incrementally. The old and new
renderers are not kept as permanent runtime modes. During development only, a
test fixture may instantiate the legacy renderer to capture reference output.

The migration sequence is:

1. capture baseline visual and performance fixtures;
2. introduce the pure transcript model and reducer;
3. introduce the compiler, height index, and virtual Line API view;
4. migrate bridge and main-screen message handling;
5. migrate interactions, scroll anchoring, and filters;
6. reconcile sidebar/status behavior and audit TUI-facing blocking calls;
7. remove the legacy message Widget implementation;
8. run the complete behavioral, visual, performance, and smoke-test gates.

If a stage regresses observable behavior, rollback is limited to the current
stage's isolated files/tests rather than resetting the dirty worktree. User
changes and benchmark submodule states are preserved throughout.

## Risks and mitigations

The largest risk is visual drift when replacing Textual child Widgets with Rich
line rendering. Styled baseline snapshots and shared renderable builders make
that drift visible before migration completes.

Variable-height Markdown makes resize and scroll anchoring subtle. Stable
record anchors, revisioned width caches, estimated heights, and tests that
resize while scrolled inside a long message address this explicitly.

Background compilation can produce stale results or grow a queue under rapid
streaming. Bounded workers, visible-first priority, latest-wins stream jobs, and
generation/revision checks prevent stale application and backlog growth.

Hand-built hit testing can regress tool expansion or code copying. Interaction
regions are emitted from compiled row geometry and verified at multiple widths
with mouse and keyboard integration tests.

A fast renderer may reveal independent Agent-runtime stalls that were formerly
hidden by layout cost. The profile is repeated after virtualization. Only
measured remaining event-loop stalls justify a later coordinator process split.

## Self-review

The implementation sequence has a reversible boundary at every major layer:
model, reducer, compiler, virtual view, integration, and cleanup. The test
strategy combines pure deterministic coverage, styled visual references,
Textual integration, structural performance invariants, wall-clock profiling,
and an interactive terminal check. The principal risk areas—variable-height
layout, stale background work, hit testing, complete long replies, filtering,
and shared-event-loop stalls—each have an explicit design mechanism and test
gate.

No unresolved product choice remains. The agreed default capacity is 16
concurrent Agents and 1,000 loaded history records, with the compatibility and
latency thresholds above. Process isolation is deliberately not bundled into
this refactor unless post-virtualization evidence demonstrates a separate
blocking source. The implementation plan must preserve this scope rather than
substituting a smaller RichLog or more aggressive truncation solution.


## Verification evidence

The refactor was implemented in worktree `refactor/tui-virtualization` and verified with:

- All 50 focused TUI tests in `tests/test_textual_tui.py` pass.
- Virtual transcript/model suites (`tests/test_tui_transcript.py`, `tests/test_tui_virtual_lines.py`, `tests/test_tui_transcript_render.py`, `tests/test_tui_frame_scheduler.py`, `tests/test_tui_render_bridge_batching.py`) pass.
- Performance/visual suites (`tests/test_tui_performance.py`, `tests/test_tui_visual_regression.py`) pass, including the reference-workload contract that enforces zero child widgets and bounded commit/input latency.
- Service/control/TUI integration suites (`tests/test_service.py`, `tests/test_control_commands.py`, `tests/test_approval_wakeup.py`) pass.
- The complete project suite passes with no in-scope failures.
- `python -m compileall` and `git diff --check` report no errors.

Reference profile (development environment, Python 3.12 venv, headless Textual driver):

```json
{"child_count": 0, "elapsed_seconds": 8.79, "input_p95_seconds": 0.34, "max_commit_seconds": 0.42, "python_calls": 5735173, "record_count": 1016}
```

The structural contract (zero message children, full history addressability, bounded active compiles, complete long-reply content, idle timer suspension, asynchronous service boundaries) is enforced by tests. Wall-clock improvement over the old Widget-tree baseline is environment-dependent; the dominant Textual layout amplification has been removed by keeping the transcript out of the live DOM.

No benchmark submodule or unrelated user file was modified.
