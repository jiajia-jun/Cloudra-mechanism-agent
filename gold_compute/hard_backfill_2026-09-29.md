# Hard gold backfill: HH1 and HF1 source synchronization

## HH1 — 1,1′-binaphthyl racemization

Calculation: ORCA 5.0.2 B3LYP-D3(BJ)/def2-SVP, RIJCOSX/def2-J,
CPCM(DMF). Values are electronic energy differences from the P minimum,
without ZPE or thermal corrections. The 23.5 kcal/mol experimental estimate
is a free-energy barrier and was not used as a fitted target.

| Structure | Compute job | Electronic energy (Eh) | Frequency result | Barrier (kcal/mol) |
| --- | ---: | ---: | --- | ---: |
| P minimum | 615 | -769.639611670288 | zero imaginary frequencies | reference |
| M minimum | 616 | -769.639692273993 | zero imaginary frequencies | — |
| syn crossing TS (torsion near 0°) | 617 | -769.602950481382 | one relevant imaginary frequency, -41.42 cm⁻¹ | 23.01 |
| anti crossing TS (torsion near 180°) | 618 | -769.588048740881 | one relevant imaginary frequency, -58.11 cm⁻¹ | 32.36 |

The computed syn–anti difference is 9.35 kcal/mol. This replaces the old
“about 1 kcal/mol” qualitative estimate in the curated source. The IRCs
(syn 623; anti 621) each ran in both directions. The frequency-verified
optimized end frames identify opposite enantiomeric wells: syn jobs 626/627
match M/P at atom-corresponding RMSD 0.020/0.015 Å, and anti jobs 624/625
match P/M at 0.009/0.016 Å. The syn endpoint calculations terminated
normally and their lowest nonzero frequencies are +30.71/+30.92 cm⁻¹.
The IRCs themselves stopped on a shallow torsional plateau after a few
steps; the endpoint optimization and frequency checks establish the well
identities. Full inputs, logs, and geometry checks are in the gold workspace
`HH1_gold_20260928/REPORT.md` and its `dft/` directory.

The two paths have the same connectivity and P/M endpoint species. The gold
graph therefore has two parallel edges with distinct TS nodes and `syn` /
`anti` channel labels. Scoring matches these channels separately so one
delivered path cannot satisfy both reference barriers.

## HF1 — preserve the previously approved result

The HF1 TaskSpec was already updated and pushed in commit `279ad606`, but
its generator sources still contained the older 9.2/10.9 kcal/mol estimates.
This change synchronizes the sources to the already accepted 16.82/20.70
kcal/mol electron barriers and 3.87 kcal/mol spread in CPCM(CH2Cl2). The
previous TaskSpec also put provenance metadata under `reference_properties`,
which would select property scoring if the generic accuracy path were used;
the hard selectivity runner currently uses the qualitative channel score.
That metadata is removed from TaskSpec, leaving its barrier and channel
values unchanged.

The earlier reference-frame comparison is retained here: relative to the
lowest reactant-complex minimum `rc_syn`, directed/opposite barriers are
16.82/20.70 kcal/mol; relative to the IRC-connected directed precomplex,
13.96/17.83; relative to separated reactants, 3.40/7.28. The benchmark
reference remains the lowest reactant-complex minimum. Original inputs,
logs, IRCs, and endpoint checks are in `HF1_gold_20260928/` on gold.
