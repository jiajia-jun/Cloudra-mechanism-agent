# Backend runtime transparency

User scope: implement the backend for inspectable tool calls and project activity;
the frontend and scientific decisions are unchanged. Execution: inline in this chat.

1. Add API regressions for complete arguments/results, independent attempts when
   call IDs repeat, pagination, project isolation, interrupted calls and job links.
2. Project existing events into call receipts; expose project activity, paginated
   per-agent calls and a detail endpoint keyed by the request event ID. Retain
   raw-result references, errors, provenance and explicit missing-data states.
3. Add validated, durable `tool.progress` reporting through the invocation scope.
   Instrument effective validated arguments and compute admission/submission.
   Preserve existing event persistence and SSE publication order.
4. Link structured job references to the authoritative compute ledger. Missing
   records and unknown waiting causes stay explicit; never infer process death
   or scientific verification from tool success or elapsed time.
5. Verify progress concurrency, invalid payloads and persistence/replay, then run
   compileall, ruff and only related backend tests. Document the API contract.

Review focus: repeated call IDs across runs/attempts; postprocessing failures after
external effects; raw data outside a UI history window; foreign project job IDs;
active tools when a run terminates; no database/file IO on the event loop.
