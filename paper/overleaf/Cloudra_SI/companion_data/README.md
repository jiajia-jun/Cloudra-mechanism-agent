# Cloudra SI machine-readable task and score tables

- `cloudrabench_50_task_catalogue.csv`: unchanged original task catalogue, including reactant/product SMILES, charge, multiplicity, conditions, and allowed methods.
- `task_definitions/`: byte-identical copies of the 50 formal JSON task definitions; these preserve complete prompts, method policies, Gold reference graphs, and rubrics.
- `cloudrabench_200_run_scores.csv`: all 200 task/configuration combinations; the four score fields retain their original numeric strings from the publication source. `configuration` adds the readable arm label while `arm` retains the original recorded key.
- `catalogue_score_provenance.json`: source hashes, row counts, and display precision.

PDF tables display composite scores to four decimal places and the three components to six decimal places. The CSV retains full source precision, including exact zero and one values. No scores have been imputed, replaced by missing-value markers, or recomputed for this SI table.

## Package inventory

| Directory | Files | Contents |
|---|---:|---|
| `task_definitions/` | 50 | Original formal task JSON files |
| `behavioral/` | 347 | Frozen inputs, saved responses, activation records, provenance, and results |
| `behavioral_scripts/` | 12 | Scripts for the archived behavioral experiments |
| `literature/` | 7 | Source register, screening records, and citation checks |
| `publication_reproduction/` | 57 | Standalone publication source tables and preparation/plotting scripts |
| `revision_20261031/` | 5 | Safe model metadata, Easy-case evidence audit, matcher audit, methods audit, and conditional sensitivity CSV |

The root contains this README, the two task/score CSVs, provenance JSON, and `file_manifest.json`. The manifest lists every payload file except itself, with its byte count and SHA-256; its `count` and `total_bytes` use that same scope.

## Revision evidence and conditional sensitivity

`revision_20261031/p2_model_metadata.json` separates the author-reported deployment **deepseek-v4.1-flash, version 1017** from the archive-recorded API alias **deepseek-v4-flash**. It contains only selected public experiment settings and source locators, without configurations, databases, credentials, or private sharing links. The three audit reports use archive-relative and repository-relative source references.

`matcher_sensitivity_scenarios.csv` retains the original publication track as P0 and labels S1/S2/S3 as conditional Accuracy-only calculations. Assigning target credit to one specified case changes its composite by +0.6, that configuration's ten-task Impossible mean by +0.06, and its 50-task mean by +0.012. Graph and self-consistency remain fixed at their released values. These scenario rows do not overwrite any of the 200 formal scores.

All pre-existing payload files other than this README remain byte-identical to the prior package, including original CSV line endings, the 200-run/800-value score table, source snapshots, task definitions, and provenance.
