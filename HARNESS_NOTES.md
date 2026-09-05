# HARNESS_NOTES — NA1 simulation run (pipeline defect log)

Run date: 2026-09-05. Coordinator: as_637d... (this session). Purpose: record any tool/scheduler/parser anomalies encountered while executing NA1 (acetaldehyde self-aldol -> 3-hydroxybutanal; methods: MACE-OMol25 + xtb only). Each entry: reproduction steps + log/file path + judgment.

## HN-001 [scheduler/xtb] xtb job_type channel cannot declare run-level flags — only bare default single point
- Repro: inspect cloudra/calculator.sh run_xtb() (lines 194-207): the scheduler runs `xtb <input.xyz>` with NO flags; stdout+stderr -> <stem>.out. The file's own comment states the --opt/--hess declaration path is a later design item (GH #26 follow-up).
- Impact: through the scheduler you cannot request --opt/--hess/--ts, a solvent (--alpb), or charge/multiplicity (--chrg/--uhf). Our species are charge -1, so a scheduler-submitted xtb job computes the wrong charge state by default. Any xtb geometry/TS work must bypass to bash, where the method-policy bash guard may fail-closed.
- Judgment: GH #26 is only partially fixed (job_type='xtb' + log_parser xtb frames + calculator.sh redirect exist; run-level/charge declaration missing). Candidate fix: calculator.sh xtb branch parsing a settings sidecar or extended-xyz keywords (e.g. xtb reads charge from an .inp/.args file), or extending qm_input_writer with engine='xtb'.
- Confirmation path: evidence/env_probe_report.md (a-8 live probe).

## HN-002 [engine/platform] ORCA macOS build writes no .out; canonical log is .cloudra/calc-<id>.out.log
- Repro basis: deploy/mace_omol25_orca_external_setup.md §3.4 (empirically verified 2026-09-03): 'orca x.inp' produces NO x.out on this macOS arm64 6.1.1 build; main output goes to stdout. The infra computes log path as state-file log_file > .cloudra/calc-<id>.out.log (GH #20 fix); parsers/notifications that assume <stem>.out will miss the real log.
- Impact: sub-agents must query job state and read the .cloudra/calc-<id>.out.log; the engine's own <stem>.out may never exist.
- Live re-confirmation: a-4 pilot MACE single point (this run).

## HN-003 [writer] qm_input_writer engine enum = gaussian|orca only; no xtb writer
- Repro: cloudra/tools/Chemtool/qm_input_writer.py — engine Literal['gaussian','orca']; description says 'Gaussian .gjf or ORCA .inp'. xtb inputs are plain .xyz that no writer emits.
- Impact: xtb coordinate inputs must be hand-written (xyz + smiles comment), and run flags passed via bash. Consistent with HN-001.
- Judgment: pipeline gap to close together with HN-001 (writer xtb support was listed as 'subsequent' in calculator.sh comments).

## HN-004 [deliverable hygiene] workspace-root mechanism_graph.json was a leftover P1 (Cope) deliverable
- Observed: before this run, ./mechanism_graph.json (2098 B, dated 2026-09-03) contained task P1 (1,5-hexadiene Cope). Backed up to NA1_sim_20260905/_backup_root_mechanism_graph_P1.json. This run's NA1 deliverable overwrites the root file as instructed ('workspace root is the landing spot').
- Judgment: per-run sandboxing of root deliverables would avoid cross-task overwrite; noted for process, not a code defect.

# HARNESS_NOTES - NA1 sim (acetaldehyde self-aldol -> 3-hydroxybutanal), coordinator execution log

Append-only anomaly log from the coordinator run. Deliverable of the simulation.

## A1 [2026-09-05] Pilot evidence gate never cleared (sessions produced no files)
- Repro: two pilots dispatched (small_mol rc evidence, env probe) writing to evidence/pilot_rc_report.md and evidence/env_probe_report.md under NA1_sim_20260905. Gate check_command: test -f on both files. Polled across the 40-min gate and a round-2 bounded gate (120 s interval, deadline ~14:09:37+08:00). Files still absent at every wake; final wake reason check_timeout.
- Logs: NA1_sim_20260905/coord_state.md (poll notes), NA1_sim_20260905/evidence/ (target dir).
- Sessions polled: as_87039ce841f642d9 (small_mol), as_93574b61c56041e9 (env).
- Judgment: pilots did not write canonical report paths inside budget. Cause not confirmed (running-vs-failed vs path mismatch). Action: re-dispatched both pilots fresh with explicit canonical output paths and isolated work dirs evidence/redispatch_rc/ and evidence/redispatch_env/ (2026-09-05).

## A2 [2026-09-05] js_exec tool-output channel is opaque to the coordinator
- Repro: js_exec text("HELLO...") and final-value expressions return only "JavaScript program completed: N output(s)" with no content visible to the caller; a 4-call probe reported 1 call "not completed" (hung get_subagent_report).
- Judgment: in this session the coordinator cannot read tool outputs via js_exec; orchestration must rely on file side effects and schedule check_command exit codes. Recorded as a tool/UI layer anomaly; root cause unknown.

## A3 [2026-09-05] get_subagent_report inside js_exec can hang
- Repro: polling as_87039ce841f642d9 inside js_exec left one tool call unresolved; a bounded race (8 s) was needed to keep the program from hanging.
- Judgment: treat sub-agent report polling as non-terminating; prefer file-based evidence or bounded races.

## A4 [2026-09-05] DAG gate + earlier tool-surface issues (from previous rounds, kept for the record)
- dag_propose_mechanism first attempt failed: missing required field operations (input_value={}); resolved once schema was found via repo grep (see coord_state.md).
- Legacy read/write/edit/bash calls earlier in the run failed parameter-name validation (invalid arguments); write via js_exec tools.bash printf worked.
- Known stack gaps (prior NA1 post-mortems, still relevant): ORCA external-MLIP Opt/scan can print ORCA TERMINATED NORMALLY without optimizer convergence (GH#21); final_energy_hartree may return initial-geometry energy on non-converged external-MLIP Opt (GH#22); xtb has no scheduler job_type channel (GH#26) so xtb must run via bash; log path canonicalization via compute_utils resolve_log_path (.cloudra/calc-<id>.out.log, GH#20).

### ROUND3 — fresh-pilot failure, campaign proceeds unverified  [2026-09-05T06:26:57.962Z]
Phenomenon: two independently re-dispatched pilot agents (rc + env probe) again failed to produce
their canonical evidence files within a 600 s gate (2 extra cycles consumed, round-2 and round-3).
Sessions polled: as_87039ce841f642d9 (pilot rc), as_93574b61c56041e9 (env probe) — re-dispatch done round-2.
Evidence paths expected but never created:
  NA1_sim_20260905/evidence/pilot_rc_report.md
  NA1_sim_20260905/evidence/env_probe_report.md
Coordinator judgement: pilot agents are unreliable in this harness environment (tool-output invisibility /
file-tool arg rejection observed in earlier rounds); treated as a harness/sub-agent anomaly, NOT as chemistry.
Mitigation: full campaign dispatched to a-4 small_mol in NA1_sim_20260905/campaign_xtb/ producing ALL species
fresh (nothing reused from evidence/). Pilot ground truth marked UNVERIFIED in final report.
\n### ROUND4 — campaign gate TIMEOUT + systemic child-runner blockage  [2026-09-05T07:35:00.427Z]\nWake: campaign gate check_timeout (3600 s budget; deadline 2026-09-05T15:27:07+08:00).\nCampaign session as_067bd4408b974a8d STILL 'queued' at wake; campaign_xtb/ EMPTY.\n\nDIAGNOSIS (evidence from ~/Library/Application Support/cloudra/runtime-v2.db):\n1. All 5 children ever dispatched from this coordinator (as_d400dc7399c240d5, project\n   prj_65e1dff983b24fca) are stuck in state='queued' with NO run.started event after\n   agent.spawned: as_87039ce841f642d9 (rc pilot), as_93574b61c56041e9 (env probe),\n   as_6e08265d9d344131 (rc re-dispatch), as_a9810c71ac074ceb (env re-dispatch),\n   as_067bd4408b974a8d (full campaign). Spawned 04:57-06:26 UTC.\n2. By contrast, children of a parallel fresh coordinator as_e5d1ea2c872a42c6 (project\n   prj_93a682b8ea3b429b, user-created 06:51 UTC, same chemistry in NA2_aldol_20260905)\n   transitioned queued->running within ~3 ms of spawn (as_4dd5c93afde34644 supervisor,\n   as_e6d2ebcc3d074a2a explorer, as_730042b30d6c4297 small_mol). So sub-agent execution\n   works in the runtime for that project.\n3. A runtime restart is visible in events (state_changed succeeded->queued reason=restart\n   on as_4dd5c93afde34644 at 07:02:53 UTC). All of MY children predate that restart and\n   were never resumed; children spawned after it (the other project) run.\n4. as_e5d1ea2c872a42c6 was cancelled by user at 07:27:40 UTC (same minute as this gate\n   timeout) - the fresh parallel attempt is gone; this coordinator remains responsible.\nJudgment: blockage is at the sub-agent wake/scheduling layer for pre-restart queued\nchildren (or per-project agent-runner servicing), NOT chemistry, NOT DAG policy.\nAction: run child-channel liveness probe (fresh spawn now); if it runs, re-dispatch full\ncampaign; if it stays queued, execute the campaign directly from the coordinator session\n(only working execution plane) and log this deviation.\n\n### ROUND4b — blockage CLEARED: root cause + fresh campaign running  [2026-09-05T07:36:30Z]\nLiveness probe: explorer as_fc0786fd08dc4f0c (spawned 07:35:03) -> running -> succeeded,\nwrote NA1_sim_20260905/campaign_xtb/child_liveness_probe.txt = "child-probe-ok ...".\n=> The sub-agent execution plane works for children spawned AFTER the ~07:02 UTC restart.\n   The five earlier children (spawned 04:57-06:26 UTC, pre-restart) were orphaned in\n   'queued' and are unrecoverable via polling; they will never run.\nFull campaign re-dispatched FRESH: small_mol as_45f63e56d51d4c38 (spawned 07:36:04 UTC,\nimmediately queued->running, run.started present). Working dir campaign_xtb/.\nCampaign gate re-armed (check CAMPAIGN_REPORT.md).\n

### ROUND5 — campaign gate TIMEOUT #2; campaign child interrupted by process restart  [2026-09-05T08:4x UTC]
Wake: campaign gate check_timeout (3600 s budget, deadline 2026-09-05T16:37 local). Success file CAMPAIGN_REPORT.md still absent.
Fresh campaign as_45f63e56d51d4c38 (spawned 07:36:04 UTC, ran immediately) was making real progress: loaded skill,
read spec, created campaign_xtb/{rc,i1,i2,p,ts1,ts2,ts3,scans,mace} and produced rc/confs.xyz + rc/confs.sdf
(conformer_search for [OH-].CC=O.CC=O, charge -1) at 15:39 local — then DIED with event
  run.finished {outcome: failed, error: "interrupted by process restart"}  2026-09-05 07:39:37 UTC.
=> NOT a chemistry/tool failure: the runtime process restarted mid-run and killed the in-flight child.
Pattern: runtime restarts at ~07:02:53 UTC (orphaned 5 pre-restart children in 'queued' forever, ROUND4),
07:39:37 UTC (killed this campaign), 08:26 local / 16:26 +08 (new uvicorn PID 15836, current). Each restart
interrupts running children and never resumes pre-restart queued ones. The 'blockage' is process-restart
instability of the execution plane (dev iteration / server relaunch), NOT DAG policy and NOT chemistry.
Additional anomalies this round:
- A2/A3 revisited: js_exec tool-output channel works in current API (uvicorn :8001, PID 15836, since 16:26);
  earlier opacity/hangs (ROUND1-3) coincided with the pre-restart runtime. File tools (read/write) also function now.
- api.log shows repeated review_worker recovery errors: sqlite3.OperationalError "no such table:
  dag_review_notifications" (cloudra/dag/store.py pending_review_notifications) for projects
  prj_6339f4303064407c / prj_ba004333327346d0 / prj_eaed477a54d345ba / prj_df9e1659dead437f at 14:50:57
  (log: ~/Library/Application Support/cloudra/logs/api.log). Judgment: DAG review-notification store table
  missing in those projects' DB -> review_worker recovery loop; possible impact on dag_guided review delivery.
- compute.db paths: ~/.cloudra/compute.db is a 0-byte DECOY; the live scheduler DB is
  ~/Library/Application Support/cloudra/compute.db (table compute_jobs; newest job id 102, 2026-09-04 16:04,
  project prj_1ad04cd49e9841d9/NA1_exam). query_compute_queue today: 0 running / 0 queued, capacity
  18 cpus/2 slots free. NO compute jobs submitted since 2026-09-04 16:05 -> no campaign reached the scheduler.
- coord_state.md + progress.md in NA1_sim_20260905/ are MISSING (were present per earlier handover); the dir
  now holds only dispatch files / campaign_xtb / evidence / dag_notes / P1 backup. coord_state.md recreated
  this round with the current note; disappearance itself logged as housekeeping anomaly.
Action: campaign RE-DISPATCHED fresh (session captured in coord_state.md) with resilience instruction to
checkpoint per-species outputs to disk as it goes; gate re-armed +3600s once. Old zombie sessions
(as_067bd4408b974a8d, as_6e08265d9d344131, as_87039ce841f642d9, as_93574b61c56041e9, as_a9810c71ac074ceb)
remain permanently 'queued' (pre-restart orphans) and are abandoned.