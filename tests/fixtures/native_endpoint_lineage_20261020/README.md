# Historical native endpoint lineage: L1, M17 and M3

These are complete, unchanged ORCA outputs from real calculations on
2026-10-20. L1/M17 originated in `batch_33673755b17b4a55` with Cloudra
`fae430ab`; M3 originated in `batch_06889167511143ee` with `81def568`.
They are historical calculation replays, **not a new calculation, a simulated
quantum result, or a new end-to-end model Benchmark run**.

The package retains 27 complete TS Opt/Freq, IRC, and endpoint Opt/Freq logs,
the four original frozen IRC bundles (including their original endpoint
sidecars, atom correspondence and XYZ bytes), and the original delivered
mechanism graphs. There are no cropped native logs or edited calculations.
The existing `dag_m8_endpoint/*.out.gz` fixtures use the same lossless gzip
convention.

`manifest.json` records every source path, original SHA256, archive SHA256,
byte count, job number, formal task snapshot and original scoring result.
Decompression restores the exact original sandbox-relative paths. Native
archive bytes total 1,134,900 bytes; decompressed evidence totals 6,546,038 bytes.
The manifest's original top-level batch/revision describe L1/M17; the M3 case
records its separate original batch and source revision explicitly.

| Case | Actual failure in the original delivery | Historical correct chain |
| --- | --- | --- |
| L1 | `BD_opening` selects the torsional IRC's jobs 16/17, so the ring-opening step cannot use its own endpoint; the two torsional edges pass. | Ring opening: source jobs 6/7, target 8/9. Forward torsion: source 16/17, target 14/15. Reverse torsion uses 14/15 to 16/17. |
| M17 | Product `P` selects independent seed optimization job 24 rather than the actual IRC product endpoint. | Source jobs 29/30, target 31/32, from IRC job 28 and TS jobs 26/27. |

The negative tests retain the original delivered graph bytes and reproduce
strict scientific rejection and the original composite score of 0.6667.
The diagnostic positive tests use the same original graphs and unchanged native files,
then publish the current internal per-step endpoint index from the historical
chains above. This index is a **diagnostic reconstruction**, not an artifact
that existed in the original run. Its paths and hashes identify existing
native calculations; it supplies no scientific verdict. The production
scientific validator must still prove the same-TS IRC to native Opt to
zero-imaginary Freq chain for every step. The current `87685c5e` fix accepts
both cases, including all three L1 edges, without changing Gold, rubric,
native files, graph nodes, or graph edges.

`L1/automatic/` is a separate **actual automatic delivery**, captured after
the real L1 continuation completed. Its `mechanism_graph.json` and
`mechanism_evidence.json` are copied byte-for-byte from
`archives/continuation-stalled-seq-20261020/raw-evidence.tar`; the source archive
SHA256, archive member names, capture time and running program revision are
recorded under `cases.L1.automatic_delivery` in the manifest. No writer or
diagnostic reconstruction produces this sidecar in the regression test.
Its four referenced native snapshots are byte-identical to existing jobs
6, 8, 14 and 16, so the test restores them at the actual automatic sidecar's
relative paths from the existing gzip files. This actual delivery passes
formal L1 Gold scoring at 1.0 and all three scientific edge checks.

`M17/automatic/` adds the corresponding actual M17 delivery after the original
project continuation finished at `2026-10-20T11:04:29.617664+00:00`.
Its graph and sidecar are copied byte-for-byte from
`continuation-fixedseq-20261020/returned.tar`; the archive SHA256, original
member names, running revision and continuation timestamps are recorded under
`cases.M17.automatic_delivery`. Its three referenced snapshots reuse existing
jobs 29, 30 and 31 by exact SHA256. Formal M17 Gold scoring and its scientific
edge check both pass, with final score 1.0. The test restores each actual graph
and sidecar as captured, rather than assuming that the new graph must equal
the original failed delivery.

`M3/automatic/` preserves the actual automatic NH3 umbrella-inversion delivery
from `vm-three-20261020-81def568/m3-formal/raw-m3.tar`, retrieved at
`2026-10-20T13:56:07.551102+00:00`. The manifest records the original archive
SHA256 and member paths, all native and gzip hashes, the fixed formal task,
and the existing formal score report's SHA256. Its graph and endpoint index
are original bytes from the archive, without a metadata writer or diagnostic
reconstruction. Only the successful M3 delivery is represented; no earlier
failed M3 delivery is invented.

The five complete M3 native logs are TS Opt job 3, independent TS Freq job 4,
IRC job 5, and endpoint Opt/Freq jobs 6/8. The latter two already contain their
native frequency analyses, so the separate endpoint Freq jobs 7/9 are not
needed by the captured successful evidence chain. The original frozen IRC
bundle retains both actual endpoint files, both frozen endpoint frames, its
atom correspondence and sidecar. Duplicate original evidence snapshots are
restored by SHA256 from the same gzip files. M3 adds 136,113 compressed native
bytes plus 10,415 bytes for its original graph, endpoint index and formal task.

Formal M3 Gold scoring gives graph 1.0, self-consistency true, accuracy
0.9999998175672095 and composite 1.0. Both endpoints are NH3 and the edge has
no bond changes: the geometric distance-interval check is only advisory,
while the genuine same-TS IRC outer-frame to converged zero-imaginary
Opt/Freq chain establishes direction. Its automatic-delivery regression
checks both the advisory and the accepted endpoint proof using the production
scientific validator. This replays historical real QM; it launches no new QM.

The three distinct categories are therefore preserved: L1/M17 original failed
deliveries, their diagnostic endpoint-index reconstructions, and the three
real automatic exports. M3 participates only in the automatic-export test.

The source run's original complete archive remains separate from this small
test package. These fixtures retain all native evidence needed by these
regressions, rather than the run's unrelated trial calculations and binary
working files. Running the tests never launches a QM executable.
