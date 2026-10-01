# Contributing to Cloudra

Thanks for considering a contribution. Cloudra is research software for computational
organic chemistry, so the bar for a change is not only "does it work" but "is the
scientific claim it supports actually justified by evidence".

## Developer Certificate of Origin

Every commit you contribute must be signed off under the
[Developer Certificate of Origin 1.1](https://developercertificate.org/). Signing off is a
statement that you have the right to submit the contribution under this project's license
(AGPL-3.0-or-later). It is not a copyright assignment — you keep the copyright to your work.

Sign off with:

```bash
git commit -s -m "fix: correct TS optimizer convergence check"
```

That appends a trailer to your commit message:

```
Signed-off-by: Your Name <your.email@example.com>
```

The name and email must be real and must match the commit author. To fix a commit that is
missing the trailer:

```bash
git commit --amend -s --no-edit     # most recent commit
git rebase --signoff HEAD~n          # the last n commits
```

Commits without a valid sign-off will not be merged.

> Because contributions arrive under the DCO rather than a contributor license agreement,
> the project license is not expected to change again. Make sure you are comfortable with
> AGPL-3.0-or-later before contributing.

## Before you start

- **Science-affecting changes need a human decision first.** Thresholds for barrier
  eligibility, the choice of quantum-chemistry method, functional or basis set, conformer
  scoring cutoffs, benchmark scoring weights, and unreachable-path criteria are not
  engineering choices. Open an issue and get an explicit decision before writing code.
- **Open an issue before a large change.** It is cheaper to disagree about an approach
  than about a finished patch.

## Engineering rules

The project's engineering rules live in [AGENTS.md](AGENTS.md). The ones that most often
trip up a first contribution:

- Validation never uses regular expressions. Structured data is checked with schemas and
  enums and fails loud; `re` is reserved for parsing quantum-chemistry program output.
- Never block the event loop. No synchronous SQLite, `time.sleep`, `subprocess.run` or
  blocking network call inside an `async` function — offload with `asyncio.to_thread`.
- Never kill a running quantum-chemistry job. Cancellation is a database flag; process
  liveness is decided only by the file lock in `infra/flocks.py`.
- No compatibility shims or legacy fallbacks. Fix the architecture.
- A bug fix ships with a unit test that reproduces the bug.

## Development workflow

```bash
uv run python -m compileall -q cloudra tests   # syntax
uv run ruff check cloudra tests                # lint
uv run pytest -q tests/test_dag_engine.py      # run the tests for the module you touched
```

Run only the tests for the module you changed locally; CI owns the full suite.

## Pull requests

- Keep one logical change per pull request.
- Update the documentation and the module README in the same commit as the behavior.
- Describe the evidence behind a scientific change: what was computed, at what level of
  theory, and what it shows.

## Reporting issues

Include the Cloudra version or commit hash, the command you ran, the full traceback, and —
for calculation problems — the input geometry and the quantum-chemistry output tail. A
report that includes the actual program output is far more actionable than one that
paraphrases it.

## Language

Issues and pull requests are welcome in English or Chinese.
