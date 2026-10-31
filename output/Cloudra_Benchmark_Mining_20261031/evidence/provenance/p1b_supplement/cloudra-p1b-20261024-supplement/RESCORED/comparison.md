# P1b rescored results

Generated 2026-10-24T23:11:35

Scorer fixes: `fix/benchmark-scoring-fairness` (PR #243),
see docs/benchmarks/SCORING_FAIRNESS_FIXES.md in the repository.

## Old vs new per arm

| arm | n | old mean | new mean | old sd | new sd |
|---|---|---|---|---|---|
| guided | 12 | 0.829 | 0.979 | 0.291 | 0.032 |
| record | 12 | 0.190 | 0.729 | 0.871 | 0.365 |
| standard | 12 | 0.245 | 0.534 | 0.778 | 0.574 |
| brief-errors | 12 | 0.100 | 0.907 | 0.947 | 0.224 |

## By tier (new)

| arm | easy | normal | hard | impossible |
|---|---|---|---|---|
| guided | 1.000 ± 0.000 | 0.991 ± 0.011 | 0.925 ± 0.000 | 1.000 ± 0.000 |
| record | 0.972 ± 0.039 | 0.914 ± 0.041 | 0.929 ± 0.026 | 0.102 ± 0.049 |
| standard | 0.853 ± 0.040 | 0.940 ± 0.032 | 0.243 ± 0.881 | 0.102 ± 0.049 |
| brief-errors | 1.000 ± 0.000 | 0.960 ± 0.030 | 0.943 ± 0.026 | 0.724 ± 0.390 |

## Per-run

| arm | round | task | old | new | seconds |
|---|---|---|---|---|---|
| brief-errors | r1 | E1 | +1.000 | +1.000 | 9.4 |
| brief-errors | r1 | NB1 | +0.960 | +0.960 | 121.8 |
| brief-errors | r1 | IA1 | -1.000 | +1.000 | 4.2 |
| brief-errors | r1 | HA1 | +0.325 | +0.925 | 852.1 |
| brief-errors | r2 | E1 | +1.000 | +1.000 | 5.8 |
| brief-errors | r2 | HA1 | -1.000 | +0.980 | 43.1 |
| brief-errors | r2 | NB1 | +0.997 | +0.997 | 132.8 |
| brief-errors | r2 | IA1 | -1.000 | +0.172 | 10.2 |
| brief-errors | r3 | E1 | +1.000 | +1.000 | 52.0 |
| brief-errors | r3 | NB1 | +0.922 | +0.922 | 41.6 |
| brief-errors | r3 | HA1 | -1.000 | +0.925 | 459.1 |
| brief-errors | r3 | IA1 | -1.000 | +1.000 | 4.4 |
| guided | r1 | E1 | +1.000 | +1.000 | 5.9 |
| guided | r1 | HA1 | +0.325 | +0.925 | 36.0 |
| guided | r1 | NB1 | +0.997 | +0.997 | 17.9 |
| guided | r1 | IA1 | +1.000 | +1.000 | 6.2 |
| guided | r2 | E1 | +1.000 | +1.000 | 4.9 |
| guided | r2 | HA1 | +0.325 | +0.925 | 685.4 |
| guided | r2 | NB1 | +1.000 | +1.000 | 28.2 |
| guided | r2 | IA1 | +1.000 | +1.000 | 3.9 |
| guided | r3 | E1 | +1.000 | +1.000 | 5.3 |
| guided | r3 | NB1 | +0.976 | +0.976 | 35.8 |
| guided | r3 | IA1 | +1.000 | +1.000 | 3.4 |
| guided | r3 | HA1 | +0.325 | +0.925 | 175.6 |
| record | r1 | E1 | +1.000 | +1.000 | 18.3 |
| record | r1 | NB1 | +0.960 | +0.960 | 68.3 |
| record | r1 | IA1 | -1.000 | +0.172 | 2.3 |
| record | r1 | HA1 | -1.000 | +0.963 | 64.8 |
| record | r2 | E1 | +1.000 | +1.000 | 39.5 |
| record | r2 | NB1 | +0.922 | +0.922 | 136.3 |
| record | r2 | IA1 | -1.000 | +0.067 | 19.4 |
| record | r2 | HA1 | +0.325 | +0.925 | 153.6 |
| record | r3 | E1 | +0.917 | +0.917 | 14.4 |
| record | r3 | NB1 | +0.860 | +0.860 | 54.7 |
| record | r3 | IA1 | -1.000 | +0.067 | 11.7 |
| record | r3 | HA1 | +0.300 | +0.900 | 46.9 |
| standard | r1 | E1 | +0.805 | +0.805 | 8.6 |
| standard | r1 | HA1 | -1.000 | +0.805 | 123.3 |
| standard | r1 | IA1 | +0.172 | +0.172 | 1.2 |
| standard | r1 | NB1 | +0.977 | +0.977 | 105.2 |
| standard | r2 | E1 | +0.902 | +0.902 | 20.9 |
| standard | r2 | NB1 | +0.898 | +0.898 | 42.8 |
| standard | r2 | HA1 | -1.000 | -1.000 | 0.0 |
| standard | r2 | IA1 | -1.000 | +0.067 | 11.6 |
| standard | r3 | E1 | +0.850 | +0.850 | 9.5 |
| standard | r3 | NB1 | +0.947 | +0.947 | 61.4 |
| standard | r3 | IA1 | +0.067 | +0.067 | 2.9 |
| standard | r3 | HA1 | +0.325 | +0.925 | 72.7 |
