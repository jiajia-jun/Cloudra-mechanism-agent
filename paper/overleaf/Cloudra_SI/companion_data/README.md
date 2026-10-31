# Cloudra SI machine-readable task and score tables

- `cloudrabench_50_task_catalogue.csv`: unchanged original task catalogue, including reactant/product SMILES, charge, multiplicity, conditions, and allowed methods.
- `task_definitions/`: byte-identical copies of the 50 formal JSON task definitions; these preserve complete prompts, method policies, Gold reference graphs, and rubrics.
- `cloudrabench_200_run_scores.csv`: all 200 task/configuration combinations; the four score fields retain their original numeric strings from the publication source. `configuration` adds the readable arm label while `arm` retains the original recorded key.
- `catalogue_score_provenance.json`: source hashes, row counts, and display precision.

PDF tables display composite scores to four decimal places and the three components to six decimal places. The CSV retains full source precision, including exact zero and one values. No scores have been imputed, replaced by missing-value markers, or recomputed for this SI table.
