# Cloudra documentation

[中文](README.md) · [Project home](../README.md)

For a first study, start with [installation and your first task](../README.md#install-and-start). For the manuscript and experimental records, start with [Paper, data and reproduction](RESEARCH_DATA.md).

The landing pages, configuration guide and research-data overview are available in both languages. Detailed chemistry, deployment and API references are currently mainly in Chinese.

## Use Cloudra and inspect results

| Guide | What you will find |
| --- | --- |
| [Configuration](CONFIGURATION.md) | Model login, web search, chat commands and server access. |
| [TS workflow and scientific validation](TS_PROCESS_SOP.md) | Transition-state searches, revisions, stopping, frequency and IRC evidence. |
| [DAG orchestration](DAG_ORCHESTRATION.md) | Modes, mechanism graphs, evidence binding and Supervisor review. |
| [Paper, data and reproduction](RESEARCH_DATA.md) | Manuscript sources, figure reproduction, original runs, Gold evidence and new benchmark runs. |

## Deployment and configuration

- [Remote compute over SSH](../deploy/ssh_remote_node.md): run Cloudra locally and send calculations to remote nodes.
- [HPC / Slurm deployment](../deploy/hpc_cluster_deployment.md): cluster setup, environment preparation and operational examples.
- [Node registry](NODE_REGISTRY.md): node configuration, workspace routing and execution semantics.
- [MACE / ORCA external potential](../deploy/mace_omol25_orca_external_setup.md) and [macOS xTB-IFF support](../deploy/xtbiff_macos_shim.md): specialized tool environments.

## Contribute

See [Contributing](../CONTRIBUTING.md) for checks and submissions, and [AGENTS.md](../AGENTS.md) for engineering and collaboration rules.

| Reference | Contents |
| --- | --- |
| [Architecture and repository map](ARCHITECTURE.md) | Agent runtime, scheduling, storage and module responsibilities. |
| [Tool protocols](TOOL_PROTOCOLS.md) | JavaScript / traditional invocation, documentation loading and runtime boundaries. |
| [Runtime observability](RUNTIME_OBSERVABILITY.md) | Agent activity, complete tool receipts and calculation APIs. |
| [Plugin development](PLUGINS.md) | Plugin interfaces, events and knowledge retrieval. |
| [Knowledge tags](KNOWLEDGE_TAGS.md) | Knowledge-base tag conventions. |
| [IDPP modes](IDPP_MODES.md) | Path modes, numerical stopping and evidence semantics. |
| [Script index](../scripts/README.md) | Runtime and data maintenance scripts. |
| [Licenses and attribution](licenses/README.md) | Project and third-party licenses. |

## Historical records

Completed plans, earlier designs and acceptance records remain in `docs/archive/`, `docs/superpowers/`, `gold_compute/archive/`, `paper/archive/` and `ideapool/archive/` for reference. They do not replace the current guides or authorize new calculations. See [CHANGELOG](../CHANGELOG.md) for version history.
