# Cloudra memory and issue repair plan

Goal: bound long-session memory while preserving durable evidence, then resolve reproducible issues without inventing scientific policies.

Architecture: SQLite remains the complete event authority. Durable history is queried on demand with finite resident state; replay is streamed. Event delivery uses bounded queues with reconnect recovery. Project deletion removes associated runtime projections.

Constraints: POSIX; no regex validation; no blocking SQLite or network calls on async loops; no quantum process termination; preserve unrelated dirty work; only focused tests locally.

## Tasks

- [x] Event storage: regression for append/restore memory bounds, complete historical queries and event-id lookups, monotonic sequences, write-ahead failure and reentrant publication. Implement persisted-history reads and incremental replay without losing evidence.
- [x] Service lifecycle: reproduce queue overflow and deletion orphans; bound SSE buffering and reliably release subscriptions; clean session contexts, pending work and notice state; test replay after reconnect and restart.
- [x] Issue #109 and #110: reproduce input identity bypass and failed-scan resubmission; enforce existing identity and diagnostic evidence before expensive side effects; preserve final scientific acceptance.
- [x] Audit #48, #108, #111, #127, #128, #135 against current code and tests; repair only confirmed engineering defects within user authorization, report scientific choices that need confirmation.
- [x] Frontend: bound loaded history and live queues without losing the ability to retrieve earlier evidence; test page navigation and project switching.
- [x] Verify syntax, lint, focused regressions and memory measurements; review integrated diff and preserve all pre-existing work.

Review focus: durable commit with lost acknowledgement; sparse interleaved project sequences; orphan sessions on restart; slow/never-started stream clients; old historical event lookup after eviction; no production job side effect on identity or retry refusal.

## Delivery evidence

Changes are integrated into the original checkout, preserving its pre-existing work. Final focused Python validation: 1098 passed, 4 skipped, 7 library warnings; 13 frontend test scripts and 6 mocked browser regressions passed. Syntax, lint, typecheck, production frontend build and integrated review passed. No complete Python suite or real quantum calculation was run.

The same isolated 221776-event database restored with retained Python heap of 1363.19 MiB before and 141.42 MiB after; peak heap changed from 1962.71 to 409.76 MiB. These are instrumented isolated measurements, not the current live services' RSS. Complete durable history, 50 projects, 225 agents and 146 contexts were preserved.

Issue audit: #109's existing pre-compute identity gate is verified, including mirrored XYZ regressions; #110 now requires scoped recovery artifacts and persists exact changes; #128's native nonconvergence diagnosis is repaired. Existing #48, #111 and #127 fixes passed their relevant checks. #108's explicit read-only role and delegation restrictions are tested; prose-only task intent is not a permission grant or revocation. #135 remains a scientific design decision requiring human confirmation. Recovery artifact integrity does not certify scientific adequacy.

Production services were not restarted during implementation. Both old API instances must be replaced by a single updated service before the backend memory changes and ownership lock take effect; quantum job processes are independent and were untouched. The user subsequently authorized a targeted commit and push, excluding all pre-existing unrelated work.
