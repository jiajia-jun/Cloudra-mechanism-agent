# Repository scripts

Run supported commands from the repository root unless the script documents another working directory. These are development and data-maintenance helpers, not the installed `cloudra` package. Root `install.sh` and `web.sh` remain the installation/startup entrypoints.

## Runtime and setup

- `setup-dev.sh`, `setup_flower.sh`: development and optional FlowER setup
- `run_cluster_server.sh`: cluster web startup
- `kg_vec_service.py`: vector search service, also launched by Cloudra's daemon supervisor; keep this path stable
- `safe_start.sh`: legacy startup helper with a broad `pkill` command; inspect before use, and prefer the documented `cloudra` / `cloudra stop` lifecycle

## Evaluation and diagnostics

- `analyze_dag_efficiency.py`: DAG event/job metrics, imported by its regression tests
- `analyze_cache_probe.py`, `replay_cache_probe.py`: cache probe analysis and replay
- `eval_real_model.py`: real-provider evaluation; requires the user's provider setup
- `smoke_compaction.py`: compaction smoke test
- `benchmarks/tool_document_selection.py`: eight-task document selection report, with estimated document tokens and separate live-service coverage; no science tools execute. `--output PATH` alone makes no network calls; repeat `--run llm|jev|reranker` to evaluate configured services.

## Knowledge and benchmark data

- `kg_merge_organic.py`: knowledge graph merging
- `gen_normal_tagging.py`, `gen_hard_tagging.py`, `gen_impossible_tagging.py`: task tagging views
- `normal_essence_mining.py`, `tag_vocab_mine.py`: mining/tagging helpers

These helpers retain their current paths and working-directory assumptions. Benchmark task generators remain in `cloudra/benchmark/gen_*_tasks.py`; generated task JSON remains in `ideapool/tasks/`.

## Documents and external deliverables

- `gen_copyright_source.py`: maintained source-listing generator; reads `cloudra/` and writes the ignored local `软著申请材料/` output tree
- [`application_docs/`](application_docs/): one-off DOCX/figure editing scripts retained together for historical reproducibility

The application scripts contain job-specific filenames, Desktop paths and optional document/image dependencies. They are not general-purpose CLIs and may overwrite the referenced document. Inspect and adapt their targets before running them. Keep sibling helpers together: `revise_application_conservative.py` imports `revise_application_ai4s.py`. Their supported invocation style remains a direct script path, for example `python scripts/application_docs/revise_application_conservative.py SOURCE OUTPUT ASSET_DIR CJC_EMF_PNG REPORT_RENDER_DIR` after checking its inputs.

Keep new reusable helpers in this directory; group one-off document workflows under `application_docs/` rather than adding more root-level scripts. Do not commit local calculation runs, credentials, caches or generated build directories.
