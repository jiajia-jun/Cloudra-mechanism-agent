# Target-correspondence postprocessing, 2 November 2026

The final evaluation applies chemical target correspondence before scoring: explicit reaction channels and electronic states distinguish otherwise identical connectivity, and the specified stable-minimum reference selects among energy references of the same native saddle. The task prompts, numerical Gold references, weights and physical conditions are retained.

All 200 organized final graphs were checked. Graph scores and assignments are unchanged. Twelve runs for the affected task definitions were replayed; the old Accuracy values reproduce their previous publication records. The current rules change five Accuracy values. The overlay updates those components and recomputes their composite scores, retaining the recorded Graph and graded self-consistency components. No QM calculation or LLM run was added.

`before/` preserves the previous publication inputs and manifest. `original_task_definitions/` preserves the three previous reference definitions byte for byte. The current definitions are in the root companion `task_definitions/`. `organized_graphs/` contains the 200 final evaluation graphs, recovered from each run's own materials under the existing organization protocol. `scoring_inputs_200.json` locates their original archive sources.

`accuracy_replay.json` retains all twelve old/new Accuracy reports, selected objects, the original native barrier evidence, energies, file hashes and unchanged Graph/SC components. `matching_audit_200_runs.csv` and the detailed JSON describe the complete matching comparison. `scorer_before/` and `scorer_update/` preserve the compared code. The two archived scoring tracks remain separate; the current publication preparation script automatically applies `target_matching_accuracy_corrections.csv`.

Native files remain in `Cloudra-P2-final-20261031-FULL.tar.gz`; archive-relative locations and hashes identify the exact existing outputs. The original campaign archive is preserved. A reproduction helper replays the recorded energy-derived observations and chemical target assignments using the current Cloudra scorer.
