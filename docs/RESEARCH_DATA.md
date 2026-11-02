# Paper, data and reproduction

[中文](RESEARCH_DATA_CN.md) · [Documentation](README_EN.md)

The manuscript **Cloudra: Geometric Reasoning and Scientific Validation for Autonomous Reaction Mechanism Exploration** has been submitted to arXiv and is awaiting announcement. Start with the [English and Chinese manuscript sources and SI](../paper/overleaf/README.md).

## Choose what to reproduce

| Your aim | Starting point | What it involves |
| --- | --- | --- |
| Reproduce paper tables and figures | [SI reproduction package](benchmarks/P2_DELIVERY.md#si-配套复现包); read the instructions in the extracted `companion_data/` | Use the bundled data and analysis scripts, without rerunning agents or quantum-chemical calculations. |
| Inspect formal experiment trajectories and native logs | [Full P2 archive](benchmarks/P2_DELIVERY.md) | 50 tasks across four configurations, with 200 retained runs. The 14.9 GB archive is publicly available with read-only access. |
| Inspect the repeated pilot experiments | [P1b packages](benchmarks/P1B_DELIVERY.md) | 48 runs; original records, historical rescoring and Standard offline reconstruction are kept separately. |
| Inspect behavioral analysis and activation interventions | [Full Chapter 3 source archives](benchmarks/P2_DELIVERY.md#行为实验与激活原始档案) | Use alongside the compact SI package. |
| Review or rerun Gold reference calculations | [Gold download and reproduction](../gold_compute/evidence/REPRODUCE.md) and [per-task index](../gold_compute/evidence/README.md) | Reading archived outputs submits no calculations. Reruns require the recorded engines, methods, dependencies and compute resources. |
| Rerun the agent benchmark | [Benchmark guide](../cloudra/benchmark/README.md) | Requires models, compute nodes and quantum-chemistry software, and incurs new model and compute usage. |

Packages are collected in the [public research-data directory](https://drive.google.com/drive/folders/1yZo3eJuCUuAgedQztgCtLyJcc8MZipf7). Each delivery page owns its package version, filenames, checksums, permissions and upload status. Detailed delivery and benchmark instructions are currently in Chinese; commands and filenames are provided verbatim.

## Interpreting the released results

Formal scores use offline organization of records already present in each run. This can recover missing graph files, repair file references and convert existing numerical values; it cannot introduce scientific conclusions or calculation evidence absent from the original run. Original graph delivery, offline scores and scientific validation are recorded separately. See the [benchmark definitions](../cloudra/benchmark/README.md).

Missing Gold originals, limitations in IRC provenance and manual acceptance exceptions are documented in the [reference status](../gold_compute/queue_20261018/REFERENCE_STATUS.md). A downloadable archive or successful checksum verification does not establish complete independent reproduction of every reference reaction.

## Versions and citation

Use the code snapshot recorded in the relevant package when inspecting published results. For a new run, record the commit, model and calculation settings; the current branch may include subsequent development changes.

Use [CITATION.bib](../CITATION.bib) for the manuscript citation and [CITATION.cff](../CITATION.cff) for GitHub citation metadata. The arXiv identifier will be added after publication.
