# HARNESS_NOTES.md - tool/scheduler/parser anomaly log (THIS RUN)

Run: acetaldehyde self-aldol -> 3-hydroxybutanal (fresh simulation, workdir aldol_selfcond_mech/).
Method whitelist: ONLY MACE-OMol25 and xtb (GFN2-xTB). Date: 2026-09-06/07.
Scope: every tool/scheduler/parser anomaly met during this run: symptom -> repro -> judgment.
Prior-run root notes archived untouched at .archive_prevrun/HARNESS_NOTES_prevrun_20260905.md.
Sub-agent entries appended in aldol_selfcond_mech/HARNESS_NOTES.md are merged here at run end.

## HN-001 [dag gate] bash QM probing is blocked before mechanism acceptance (by design, observed)
- Symptom: pre-acceptance, a bash call intended to check xtb CLI help failed with '[DAG gate] In dag_guided mode, no compute before the mechanism is accepted'.
- Repro: while draft_2cca436fc69c43c8bf9a8aa2041e7d3a was open, run bash containing any xtb invocation.
- Judgment: intended behavior (compute gate). After dag_accept_mechanism the same class of command is allowed. Non-compute bash (mkdir/ls/which) was allowed even pre-acceptance.

## HN-002 [subagent] get_subagent_report on a RUNNING session returns is_success=true with empty report
- Symptom: get_subagent_report(session_id='as_0f70433d728347bc') (researcher, state=running) returned is_success true but report_content empty and message empty.
- Repro: poll any still-running follower session.
- Judgment: empty report is ambiguous - caller cannot distinguish 'running, no report yet' from 'crashed with no report'. Workaround: agent_hub action=directory to confirm session state.

## HN-003 [subagent] subagent_launcher(is_wait=false) response did not surface session_id/act_agent in returned fields
- Symptom: after dispatch, launcher result fields session_id/act_agent were undefined in the tool result consumed by the coordinator program (only is_success true).
- Repro: subagent_launcher with is_wait=false for a-4 and a-3.
- Judgment: session ids were recoverable via agent_hub action=directory. If launcher is meant to return session_id for async launches, it was missing in this result payload.

## HN-004 [scheduler/xtb] submit_compute_job(job_type='xtb') CHANNEL EXISTS and ran a job (task_id=129, state=done)
- Symptom/observation: xtb probe job on structures/probe_acetaldehyde.xyz finished; stdout log at structures/probe_acetaldehyde.out (input xyz + .out log naming, not a .log).
- Repro: submit_compute_job(job_type='xtb', input_file=<file>.xyz, is_async=true).
- Judgment: the xtb scheduler channel is present in this harness generation (unlike an earlier NA1 generation). Flag-passing semantics (SP vs opt) are being characterized by small_mol; see aldol_selfcond_mech/HARNESS_NOTES.md.

(More entries appended as encountered.)