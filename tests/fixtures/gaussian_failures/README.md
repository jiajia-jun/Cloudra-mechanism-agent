# Gaussian failure fixtures (run4, 2026-10-20)

Inputs, logs and delivered graphs copied from the full benchmark run
`f177492c` (commit `f8f8ea434fcd7818ee4e55b1b38a64e260d3cc59`). Every file here
is a case that actually failed during that run; the verbatim engine message is
quoted so a test can pin the behaviour without guessing.

Absolute paths were rewritten (`/home/ly/cloudra-bench-run4-20261020/sandboxes`
→ `/workspace/sandboxes`, `/home/ly/g16` → `/opt/g16`,
`/home/ly/cloudra-bench-20261019` → `/opt/cloudra`). Nothing else was edited,
except the one log noted as trimmed.

## Illegal route that the pipeline generated and submitted

| fixture | route | engine response |
|---|---|---|
| `opt_ts_without_hessian.gjf` | `#p opt=TS B3LYP/def2SVP EmpiricalDispersion=GD3BJ` | `Opt=TS requires force constants or ModRedundant.` (l1) |
| `irc_without_hessian.gjf` | `#p irc B3LYP/def2SVP empiricaldispersion=gd3bj` | `You must use ReadCartesianFC, FCCards, or CalcFC with IRC` (l1), see `irc_l1_force_constant_error.log` |
| `opt_ts_bare_calcfc.gjf` | `#p opt=TS ... CalcFC` (bare keyword, not an Opt option) | `QPErr ... Last state= "GCL"` |
| `opt_ts_modredundant.gjf` | `#p opt=TS B3LYP/def2SVP ModRedundant` (no ModRedundant section) | `QPErr ... Last state= "GCL"` |

`validate_writer_request` is expected to name the in-place fix for these
(`calculation_intent.initial_hessian_unspecified`); see PR #215.

## IRC trajectory that the parser rejects

`irc_l123_no_summary.log` — trimmed copy of
`E1/.../ts/ts_0001/jobs/declaration_0009/irc/irc.log` (21 401 lines → head and
tail blocks, with an explicit `# --- fixture: ... elided ...` marker).

- 56 `Point Number` lines, 27 `CURRENT STRUCTURE` blocks, forward `Path Number: 1` then reverse `2`
- terminated by `Delta-x Convergence NOT Met` → `Error termination via Lnk1e in l123.exe`
- **no** `Summary of reaction path following` section

`gaussian_frames._parse_irc` currently raises when that summary is absent, so
every frame in this file is discarded even though the coordinates are present.
This fixture exists so the parser fix can be tested against the real shape
(and so `SCF Done`-based frame pairing can be shown to mis-align here: the log
does not print one `SCF Done` per `CURRENT STRUCTURE` block).

`irc_endpoints_null_binding.json` — the archived sidecar for the IRC above. It
carries only `log_sha256` and `endpoints`; there is **no `atom_binding` entry at
all**, and both directions are `converged: false` with `filename: null`. The
scorer's "atom binding absent" therefore reports a genuinely missing record, not
a failed comparison.

## Checkpoint declared outside the task workspace

`chk_outside_workspace.gjf` — `%chk=/workspace/sandboxes/jobs/ep4/end_b_optfreq.chk`
(the `<task>/<batch>` level is missing) with `#p opt=Restart freq`.
`chk_outside_workspace_nterr.log` shows the engine restoring state from that
path and then dying:

```
 Restoring state from the checkpoint file "/workspace/sandboxes/jobs/ep4/end_b_optfreq.chk".
 FileIO operation on non-existent file.
 Error termination in NtrErr:
```

`state_chk_outside_workspace.json` / `calc_chk_outside_workspace.exit.json`
record the same outcome (`normal_termination: false`, `exit_code: 1`, no
energy). Before the run, `sandboxes/jobs/` did not exist; the run created both
the directory and a 512 KiB checkpoint there — outside the task sandbox. See
PR #216.

## Delivered graphs whose accuracy was zero

| fixture | task | scoring note |
|---|---|---|
| `mechanism_graph_missing_barrier.json` | D4 | `delivered mechanism_graph.json declares no barrier_kcal_mol on step edge D4_E1; scored 0` |
| `mechanism_graph_ts_unbound.json` | F4 | `no first-order saddle log bound to TS TS1; barrier not derivable from evidence` and `gold edge F4_E1 ... no delivered step matches its endpoint species` |

Both files are the delivered artifacts verbatim; neither contains
`barrier_kcal_mol` anywhere, which is what the accuracy layer reported.
