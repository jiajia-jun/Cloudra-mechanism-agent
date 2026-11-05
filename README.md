# Cloudra

<p align="center">
  <img src="docs/assets/Cloudra-logo.svg" alt="Cloudra logo" width="180" />
</p>

[![CI](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml)
[![Python ≥ 3.11](https://img.shields.io/badge/python-%E2%89%A53.11-blue)](pyproject.toml)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

[中文](README_CN.md) · [Documentation](docs/README_EN.md) · [Paper & data](docs/RESEARCH_DATA.md) · [Contributing](CONTRIBUTING.md)

Meet Cloudra, an agent for theoretical and experimental chemists.

The previous version focused on **computational exploration of organic small-molecule reaction mechanisms**.

We will continue maintaining Cloudra, improving agent performance and exploring support for periodic systems, molecular dynamics and other widely needed applications. Our goal is a general-purpose chemistry agent, and we are working toward it.

The Cloudra preprint is available on [arXiv](https://arxiv.org/abs/2611.02909).

## What you can do

Cloudra currently provides a web UI. Follow the instructions below to start it.

Create a project and describe your computational chemistry task in natural language. For example:

> Investigate the reaction pathway between ... as the reactants and ... as the products. Keep me informed of your progress, and ask questions whenever something is unclear.
>
> Find literature on ..., focusing on ...
>
> Help me write a script or code for ...

In the console, you can follow agent discussions in the agent forum, inspect tool results, view the calculation queue managed by Cloudra's own small HPC scheduler, and read native logs. In mechanism-graph mode (`dag_guided`), you can also inspect species, 3D structures, reaction steps and their evidence status.

## Install and start

Download the installer for your system, double-click it, then open Cloudra from your applications or desktop. Packages include Python, Node.js, core dependencies and the built interface, so you do not need to install developer tools first. See the [beginner installation guide](docs/INSTALL.md).

| System | Installation |
| --- | --- |
| macOS | Double-click the `.pkg`, then open Cloudra in Applications. See the [macOS guide](docs/INSTALL.md#install-on-macos). |
| Linux | Install the `.deb` or extract the portable `.tar.gz`, then open Cloudra. See the [Linux guide](docs/INSTALL.md#install-on-linux). |
| Windows, running natively | Install `Setup.exe`, then open Cloudra from the Start menu or desktop. See the [guide on the `windows` branch](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/windows/docs/INSTALL_WINDOWS.md). |

macOS and Linux packages are available from the [v0.1.1rc release](https://github.com/yyywaa/Cloudra-mechanism-agent/releases/tag/v0.1.1rc). macOS packages are not developer-signed or notarized yet. Developers and people managing their own deployments can use the existing scripts via [source installation](docs/INSTALL.md#install-from-source).

1. Configure the coordinator and follower models in Global Settings. You can use an OpenAI-compatible endpoint or select ChatGPT / Codex account login. You can also choose your preferred UI style.
2. Configure the software and compute nodes needed for your study. See the [deployment guides](docs/README_EN.md#deployment-and-configuration) for remote computation, including Slurm-based clusters.
3. Create a project, select its working directory, add structures or existing calculation files, and describe the task and calculation scope.

You can also use Cloudra as a general research assistant for literature searches, research and coding.

See [Configuration](docs/CONFIGURATION.md) for model login, web search, common commands and remote access.

### Source installation remains available

With Python ≥ 3.11, Node.js ≥ 22.12 and npm installed, you can continue using the existing source workflow:

```bash
git clone --branch master https://github.com/yyywaa/Cloudra-mechanism-agent.git
cd Cloudra-mechanism-agent
bash install.sh
source .venv/bin/activate
cloudra
```

You can also run `bash web.sh`. See the [source installation guide](docs/INSTALL.md#install-from-source).

### If macOS blocks the first launch

The macOS download includes [Unblock-Cloudra.command](packaging/macos/Unblock-Cloudra.command) next to the installer. Use it only for Cloudra downloads you trust from this repository.

Open Terminal, type `bash ` with a trailing space, drag the script into the terminal, and press Return. It handles Cloudra `.pkg` files beside the script and the installed `Cloudra.app`. If prompted, enter your Mac login password. Then reopen the installer or application.

You can also provide an explicit path:

```bash
bash /path/to/Unblock-Cloudra.command /Applications/Cloudra.app
```

## Three working modes

Choose a mode in project settings:

| Mode | How it organizes the work |
| --- | --- |
| `standard` (default) | General tasks. |
| `dag_record` | Record species, reaction steps and evidence in a mechanism graph; the executing agent binds results. |
| `dag_guided` | Explore the mechanism of a single reaction and complete delivery autonomously. |

Note that the current `standard` mode is not the same implementation as the Backbone baseline discussed in the paper.

See the [DAG guide](docs/DAG_ORCHESTRATION.md) for graph delivery and the [TS guide](docs/TS_PROCESS_SOP.md) for transition-state workflows and evidence requirements.

## Paper, data and reproduction

**Cloudra: Geometric Reasoning and Scientific Validation for Autonomous Reaction Mechanism Exploration** is available as [arXiv:2611.02909](https://arxiv.org/abs/2611.02909) [cs.MA], with DOI [10.48550/arXiv.2611.02909](https://doi.org/10.48550/arXiv.2611.02909).

The [research data and reproduction guide](docs/RESEARCH_DATA.md) separates reproducing paper figures, inspecting original agent runs, reviewing Gold reference calculations and rerunning the benchmark. The formal bank contains 50 tasks; P2 comprises four configurations and 200 retained runs. The full P2 archive (14.9 GB) is publicly available with read-only access; filenames, checksums and download instructions are on the [P2 delivery page](docs/benchmarks/P2_DELIVERY.md).

## Contribute and cite

The default protocol is `javascript`; `traditional` is a per-agent opt-in.

Issues, experience reports and improvements are welcome. For calculation problems, include software versions, the environment, the task description, input files and relevant logs so we can investigate the cause. See [CONTRIBUTING.md](CONTRIBUTING.md) for development conventions and [Architecture](docs/ARCHITECTURE.md) for the system structure.

If you use Cloudra in research, please cite the manuscript and record the software commit used:

> Chengyi Yang, Qianxin Zhou, and Yang Li. *Cloudra: Geometric Reasoning and Scientific Validation for Autonomous Reaction Mechanism Exploration*. arXiv:2611.02909 [cs.MA], 2026. [doi:10.48550/arXiv.2611.02909](https://doi.org/10.48550/arXiv.2611.02909).

[BibTeX](CITATION.bib) · [GitHub citation metadata](CITATION.cff) · [arXiv preprint](https://arxiv.org/abs/2611.02909).

## License

Cloudra is licensed under [AGPL-3.0-or-later](LICENSE). Skills in `cloudra/skills/` that declare MIT use the MIT license. Bundled third-party components retain their own licenses; see [third-party attribution](docs/licenses/README.md). Contributions use the Developer Certificate of Origin; sign off commits with `git commit -s`.
