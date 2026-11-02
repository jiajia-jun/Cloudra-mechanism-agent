# Cloudra SI machine-readable task and score tables

`cloudrabench_200_run_scores.csv` is the final evaluation table for all 200 task/configuration pairs. It supplies the 200 composite scores and 600 components used in the manuscript, SI tables, and final figures. Composite scores are displayed to four decimal places; the CSV retains the source precision of the components.

`task_definitions/` contains the 50 final task definitions, including the molecular inputs, conditions, Gold references, and scoring settings. `cloudrabench_50_task_catalogue.csv` is the task catalogue. `evaluation_manifest.json` records the base evaluator, target-correspondence postprocess, final reference-file hashes, final score table, and per-run sources. The final F4 evidence records and a read-only reproduction helper are in `evaluation_records/`.

The scorer uses weights 0.1 for Graph, 0.3 for Self-consistency, and 0.6 for Accuracy. Run artifacts and native calculation logs are preserved. The four F4 deliveries were evaluated against the same final reference definition. The subsequent 2 November target-correspondence postprocess checked all 200 organized graphs and replayed Accuracy on the 12 runs for L2, IA5 and IC3; five Accuracy values and their composites changed. All Graph and Self-consistency components and the remaining 195 Accuracy values retain their organized records. No new quantum-chemical calculations or Agent experiments were run for this final evaluation.

To reproduce the four F4 records, use the Cloudra checkout recorded in the manifest and run:

```bash
python evaluation_records/reproduce_f4.py --campaign-root /path/to/cloudra-p2c-20261025 --output /path/to/separate-output
```

The full study archive supplies the preserved sandboxes. The output directory must be outside the preserved campaign directory.

`publication_reproduction/` contains the final publication source tables and preparation/plotting scripts. `behavioral/`, `behavioral_scripts/`, and `literature/` retain the separate diagnostic experiments and literature evidence. The dated `revision_20261031/` reports are historical audit records; the current formal scores are the final table identified above.

`revision_20261102/target_matching/` is the official target-correspondence Accuracy overlay applied to the publication table. It updates five Accuracy values (and their composites) while retaining Graph and Self-consistency from the organized records; see that directory's README for the replay audit and correction CSV consumed by the publication preparation script. Historical matcher-sensitivity scenarios under `revision_20261031/` are provenance only and are not the published scores. The root `file_manifest.json` lists every payload file except itself, with its byte count and SHA-256.

`revision_20261101/` adds an original-run NI1 chemical-object figure and uncapped barrier-error statistics, with explicit common-subset coverage and archived completion-record inventories. These derived analyses preserve the formal score table and original scientific criteria; edge assignments follow the task-specified reaction and energy-reference definitions used in the final evaluation.
