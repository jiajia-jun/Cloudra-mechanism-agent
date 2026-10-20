# Historical native endpoint lineage: L1 and M17

These are complete, unchanged ORCA outputs from the real calculations in
`batch_33673755b17b4a55`, run on 2026-10-20 with Cloudra `fae430ab`.
They are historical calculation replays, **not a new calculation, a simulated
quantum result, or a new end-to-end model Benchmark run**.

The package retains 22 complete TS Opt/Freq, IRC, and endpoint Opt/Freq logs,
the three original frozen IRC bundles (including their original endpoint
sidecars, atom correspondence and XYZ bytes), and the original delivered
mechanism graphs. There are no cropped native logs or edited calculations.
The existing `dag_m8_endpoint/*.out.gz` fixtures use the same lossless gzip
convention.

`manifest.json` records every source path, original SHA256, archive SHA256,
byte count, job number, formal task snapshot and original scoring result.
Decompression restores the exact original sandbox-relative paths. Native
archive bytes total 998,787 bytes; decompressed evidence totals 5,920,280 bytes.

| Case | Actual failure in the original delivery | Historical correct chain |
| --- | --- | --- |
| L1 | `BD_opening` selects the torsional IRC's jobs 16/17, so the ring-opening step cannot use its own endpoint; the two torsional edges pass. | Ring opening: source jobs 6/7, target 8/9. Forward torsion: source 16/17, target 14/15. Reverse torsion uses 14/15 to 16/17. |
| M17 | Product `P` selects independent seed optimization job 24 rather than the actual IRC product endpoint. | Source jobs 29/30, target 31/32, from IRC job 28 and TS jobs 26/27. |

The negative tests retain the original delivered graph bytes and reproduce
strict scientific rejection and the original composite score of 0.6667.
The positive tests use the same original graphs and unchanged native files,
then publish the current internal per-step endpoint index from the historical
chains above. This index is a **diagnostic reconstruction**, not an artifact
that existed in the original run. Its paths and hashes identify existing
native calculations; it supplies no scientific verdict. The production
scientific validator must still prove the same-TS IRC to native Opt to
zero-imaginary Freq chain for every step. The current `87685c5e` fix accepts
both cases, including all three L1 edges, without changing Gold, rubric,
native files, graph nodes, or graph edges.

The source run's original complete archive remains separate from this small
test package. These fixtures retain all native evidence needed by these
regressions, rather than the run's unrelated trial calculations and binary
working files. Running the tests never launches a QM executable.
