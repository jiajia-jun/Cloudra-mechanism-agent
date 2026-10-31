# Contributing to Cloudra

[中文](CONTRIBUTING_CN.md)

Thanks for considering a contribution to Cloudra. Cloudra is research software for computational chemistry. Criticism is welcome in the issue tracker, and we will discuss the problems with you.

Usage feedback, reproduction issues, computational case studies and documentation improvements are also welcome.

## Before you start

- We welcome AI-generated code, but please do not rely on one-shot generation. We look forward to technical discussions.
- We recommend human–AI collaboration: first understand the interfaces, then guide the AI away from overengineering or incomplete implementations.
- **Open an issue before a large change.** Discussing the approach early costs less than discovering disagreements after the code is written.

## Engineering rules

The complete rules are in [AGENTS.md](AGENTS.md). In particular:

- Do not use regular expressions to validate structured data. Use schemas and enums, and report errors explicitly. `re` is reserved for parsing raw text output from quantum-chemistry programs.
- Do not block the asynchronous event loop. Move synchronous database queries, `time.sleep`, `subprocess.run` and blocking network requests to `asyncio.to_thread` or another suitable mechanism.
- Do not arbitrarily terminate running quantum-chemistry jobs. Cancellation is communicated through a database flag; process liveness is determined by file locks.
- Include a unit test that reproduces the bug you are fixing. Where needed, we also appreciate integration tests.

## Development checks

```bash
uv run python -m compileall -q cloudra tests   # syntax checks
uv run ruff check cloudra tests                # code style
uv run pytest -q tests/test_dag_engine.py      # tests for the affected module
```

## Pull requests

- Keep each PR focused on one logical change.
- When behavior changes, update the relevant documentation and module README in the same commit.
- For a large refactor, consider splitting the work into smaller PRs to make review easier.

## Reporting issues

Include the Cloudra version or commit hash, the command you ran and the full error output. For calculation problems, also provide the input geometry and relevant logs from the end of the quantum-chemistry program's output. Actual program output is more useful for diagnosis than a paraphrase of the error.

## Developer Certificate of Origin

Every commit must be signed off under the [Developer Certificate of Origin 1.1](https://developercertificate.org/). Signing off states that you have the right to submit the contribution under the project's AGPL-3.0-or-later license. It does not transfer copyright; you retain copyright to your work.

To sign off:

```bash
git commit -s -m "fix: correct TS optimizer convergence check"
```

This adds the following trailer to the commit message:

```text
Signed-off-by: Your Name <your.email@example.com>
```

The name and email must be real and match the commit author. To add a missing sign-off:

```bash
git commit --amend -s --no-edit     # most recent commit
git rebase --signoff HEAD~n          # last n commits
```

Commits without a valid sign-off will not be merged.
