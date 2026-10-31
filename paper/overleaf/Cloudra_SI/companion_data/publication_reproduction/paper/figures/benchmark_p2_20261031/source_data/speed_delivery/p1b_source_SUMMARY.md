# P1b campaign summary

Generated: 2026-10-24T18:12:39

Manifest: `campaign=P1b tasks=E1,NB1,HA1,IA1 arms=guided,record,standard,brief-errors repeats=3 concurrency=2 isolation=masked-mount-namespace started=2026-10-24T03:42:31+08:00
ALL_DONE 2026-10-24T18:11:33+08:00`

## Per-arm commits
- guided: 9e0388807eb7907888dd3ed47923ba65a635bfad
- record: 221fd310bca33b818ead09533c2d5224a2e02116
- standard: 3d1934812af9fe8237787f29c7dbf6d5b86a6408
- brief-errors: bb11742fff5bc27c11cfa5ba963f9fa1985e16e6

## Aggregate (all completed runs)

| arm | n | mean final | mean acc | selfc pass | delivered |
|---|---|---|---|---|---|
| guided | 12 | 0.938 | 0.750 | 100% | 0% |
| record | 12 | 0.549 | 0.500 | 67% | 0% |
| standard | 12 | 0.437 | 0.500 | 75% | 0% |
| brief-errors | 12 | 0.552 | 0.500 | 58% | 0% |

## By tier (mean final, n)

| arm | easy | normal | hard | impossible |
|---|---|---|---|---|
| guided | +1.000 (3) | +1.000 (3) | +0.750 (3) | +1.000 (3) |
| record | +0.917 (3) | +0.806 (3) | +0.472 (3) | +0.000 (3) |
| standard | +0.508 (3) | +0.872 (3) | +0.250 (3) | +0.117 (3) |
| brief-errors | +1.000 (3) | +0.958 (3) | +0.250 (3) | +0.000 (3) |

## Per-run detail

| arm | round | tier | task | graph | selfc | selfc score | acc | final | undelivered |
|---|---|---|---|---|---|---|---|---|---|
| brief-errors | r1 | easy | E1 | 1.000 | 1 | 1.00 | 1.000 | +1.0000 | 0 |
| brief-errors | r1 | hard | HA1 | 1.000 | 0 | 0.75 | 0.000 | +0.3250 | 1 |
| brief-errors | r1 | impossible | IA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| brief-errors | r1 | normal | NB1 | 0.600 | 1 | 1.00 | 1.000 | +0.9600 | 1 |
| brief-errors | r2 | easy | E1 | 1.000 | 1 | 1.00 | 1.000 | +1.0000 | 1 |
| brief-errors | r2 | hard | HA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| brief-errors | r2 | impossible | IA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| brief-errors | r2 | normal | NB1 | 0.967 | 1 | 1.00 | 1.000 | +0.9966 | 1 |
| brief-errors | r3 | easy | E1 | 1.000 | 1 | 1.00 | 1.000 | +1.0000 | 1 |
| brief-errors | r3 | hard | HA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| brief-errors | r3 | impossible | IA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| brief-errors | r3 | normal | NB1 | 0.600 | 0 | 0.88 | 1.000 | +0.9225 | 1 |
| guided | r1 | easy | E1 | 1.000 | 1 | 1.00 | 1.000 | +1.0000 | 0 |
| guided | r1 | hard | HA1 | 1.000 | 0 | 0.75 | 0.000 | +0.3250 | 1 |
| guided | r1 | impossible | IA1 | 1.000 | 1 | 1.00 | 1.000 | +1.0000 | 0 |
| guided | r1 | normal | NB1 | 0.967 | 1 | 1.00 | 1.000 | +0.9966 | 0 |
| guided | r2 | easy | E1 | 1.000 | 1 | 1.00 | 1.000 | +1.0000 | 0 |
| guided | r2 | hard | HA1 | 1.000 | 0 | 0.75 | 0.000 | +0.3250 | 0 |
| guided | r2 | impossible | IA1 | 1.000 | 1 | 1.00 | 1.000 | +1.0000 | 1 |
| guided | r2 | normal | NB1 | 1.000 | 1 | 1.00 | 1.000 | +1.0000 | 0 |
| guided | r3 | easy | E1 | 1.000 | 1 | 1.00 | 1.000 | +1.0000 | 0 |
| guided | r3 | hard | HA1 | 1.000 | 0 | 0.75 | 0.000 | +0.3250 | 0 |
| guided | r3 | impossible | IA1 | 1.000 | 0 | 1.00 | 1.000 | +1.0000 | 0 |
| guided | r3 | normal | NB1 | 0.762 | 1 | 1.00 | 1.000 | +0.9762 | 0 |
| record | r1 | easy | E1 | 1.000 | 1 | 1.00 | 1.000 | +1.0000 | 1 |
| record | r1 | hard | HA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| record | r1 | impossible | IA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| record | r1 | normal | NB1 | 0.600 | 1 | 1.00 | 1.000 | +0.9600 | 1 |
| record | r2 | easy | E1 | 1.000 | 1 | 1.00 | 1.000 | +1.0000 | 1 |
| record | r2 | hard | HA1 | 1.000 | 0 | 0.75 | 0.000 | +0.3250 | 1 |
| record | r2 | impossible | IA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| record | r2 | normal | NB1 | 0.967 | 0 | 0.75 | 1.000 | +0.9216 | 1 |
| record | r3 | easy | E1 | 0.917 | 0 | 0.75 | 1.000 | +0.9167 | 1 |
| record | r3 | hard | HA1 | 1.000 | 0 | 0.67 | 0.000 | +0.3000 | 1 |
| record | r3 | impossible | IA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| record | r3 | normal | NB1 | 0.600 | 0 | 0.67 | 1.000 | +0.8600 | 1 |
| standard | r1 | easy | E1 | 1.000 | 0 | 0.35 | 1.000 | +0.8050 | 1 |
| standard | r1 | hard | HA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| standard | r1 | impossible | IA1 | 0.667 | 0 | 0.35 | 0.000 | +0.1717 | 1 |
| standard | r1 | normal | NB1 | 0.767 | 1 | 1.00 | 1.000 | +0.9766 | 1 |
| standard | r2 | easy | E1 | 1.000 | 0 | 0.68 | 1.000 | +0.9025 | 1 |
| standard | r2 | hard | HA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| standard | r2 | impossible | IA1 | 0.000 | 0 | 0.00 | 0.000 | -1.0000 | 1 |
| standard | r2 | normal | NB1 | 0.629 | 0 | 0.78 | 1.000 | +0.8978 | 1 |
| standard | r3 | easy | E1 | 1.000 | 0 | 0.50 | 1.000 | +0.8500 | 1 |
| standard | r3 | hard | HA1 | 1.000 | 0 | 0.75 | 0.000 | +0.3250 | 1 |
| standard | r3 | impossible | IA1 | 0.667 | 0 | 0.00 | 0.000 | +0.0667 | 1 |
| standard | r3 | normal | NB1 | 0.967 | 0 | 0.83 | 1.000 | +0.9466 | 1 |
