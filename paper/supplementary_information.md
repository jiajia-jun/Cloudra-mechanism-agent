# Supplementary Information

For **Cloudra: An Evidence-Gated Harness for Autonomous Organic Reaction Mechanism Elucidation**
Revision: 3 October 2026. This supplement records source provenance and evidence limits; it is not a completed experimental dataset.

## S1. Manuscript source map

| Manuscript claim | Repository source | Scope of support |
|---|---|---|
| Harness delegation, chemical evidence DAG, formal benchmark as headline contributions | `docs/novelty.md` | Narrative positioning; its older scoring and refusal language is superseded by current project instructions. |
| Persistent prepare / inspect / resume interface | `docs/TS_PROCESS_SOP.md` | Current interface and verification contract; explicitly marks native ORCA/Gaussian full-chain acceptance as incomplete. |
| Granular stage vocabulary and derived evidence levels | `cloudra/dag/models.py` | Schema and stage semantics; not an empirical success rate. |
| Three-component weights, clawback, integrity short circuit | `cloudra/benchmark/runner.py` | Implemented scoring behavior. |
| Gaussian kernel, caps, missing references, inaccessible-edge handling | `cloudra/benchmark/accuracy.py` | Important qualifications to the simple headline score. |
| Bound-element physical coverage and short-IRC direction semantics | `cloudra/benchmark/selfconsistency.py` | Distinguishes valid bound artifacts from unrelated or superseded attempts. |
| Log-derived barriers | `cloudra/benchmark/barrier_evidence.py` | Numerical provenance; no blanket claim of complete parser robustness. |
| Coordinate-writing guidance | `cloudra/runtime_v2/policies/guidance.py` | Guidance is not described as an absolute coordinate firewall. |
| 52 tasks / 81 edges and reference limitations | `gold_compute/library_audit_20261002/README.md` | Dated inventory, not a freshly repeated scientific audit or autonomous benchmark run. |

## S2. Reference inventory

The audit identifies reference commit `3ec62c55c8e3433854246ea50f889668b2659cc4`. Its inventory is:

| Tier | Tasks | Edges | Numerical values | Open gaps | Explicit PT exemptions | Inaccessible TS edges | Property/state edges |
|---|---:|---:|---:|---:|---:|---:|---:|
| Easy | 20 | 20 | 20 | 0 | 0 | 0 | 0 |
| Normal | 10 | 26 | 17 | 7 | 2 | 0 | 0 |
| Hard | 10 | 22 | 19 | 3 | 0 | 0 | 0 |
| Impossible | 12 | 13 | 1 | 0 | 0 | 8 | 4 |
| Total | 52 | 81 | 57 | 10 | 2 | 8 | 4 |

Ten populated values have recorded scientific or mechanistic caveats. The audit's caveats are carried forward as unresolved source limitations; this rewrite does not independently adjudicate whether each caveat changes acceptance under the latest short-IRC protocol. Later supplementation must be reconciled against a new fixed snapshot before changing these counts.

## S3. Scientific protocol disclosure

Each empirical release must identify the reaction model, atom mapping, charge and multiplicity, conformer sources, stage-specific engine/method/basis/keywords, solvent treatment, energy reference, frequency protocol, direction evidence, and thermochemical conventions actually used. Electronic barriers and free-energy barriers must remain distinct. A conformer window, temperature, standard state, frequency cutoff, or level of theory must not be copied from an old draft and presented as a protocol actually executed.

The native TS process requires evidence for a first-order saddle and verified endpoint minima with matching identity and stereochemistry. Partial IRC trajectories can support direction when the defined geometric criterion is satisfied. This does not mean an unconverged endpoint optimization or absent endpoint frequency calculation is automatically acceptable.

## S4. Scoring discrepancy requiring scientific resolution

Project instructions state that correctly delivered inaccessible mechanisms may receive full credit. The current `accuracy.py` instead assigns zero barrier-accuracy credit to inaccessible reference edges without barriers, while `runner.py` retains the common 0.1/0.3/0.6 weights. Thus the manuscript does not claim that this intention is already realized by every Impossible task.

Accessible edges without numerical references currently receive nominal accuracy credit. Hard tasks with a favored-channel anchor use qualitative selectivity in the accuracy slot. These behaviors must accompany any released aggregate score. This rewrite changes neither the implementation nor the scientific scoring policy.

## S5. Evidence required for performance claims

A results release needs a frozen task and evaluator revision, model configuration, matched allowed methods and resources, repeated-run design, per-run artifacts, component scores, reference coverage, failures, and uncertainty estimates. Tests with substitute calculators cannot establish native-engine chemical validity. Reference-generation jobs cannot be relabeled as autonomous-agent benchmark trials.

The proposed comparisons concern evidence gating, automatic progression, and diagnostic retrieval. No efficiency gain, hallucination rate, quantitative selectivity prediction, or completed HFIP/radical research application is reported as a measured result in this revision.

## S6. Literature verification

The rewrite checked the primary ARCHE abstract and public repository, the YARP publisher page, and the autodE publisher page. The El Agente publisher full text could not be retrieved; its use is restricted to the general published system identity rather than a detailed negative comparison.

- El Agente: <https://doi.org/10.1016/j.matt.2025.102263>
- YARP: <https://doi.org/10.1038/s43588-021-00101-3>
- autodE: <https://doi.org/10.1002/anie.202011941>
- ARCHE: <https://arxiv.org/abs/2609.11147>
- ARCHE repository: <https://github.com/JetAstra/Arche-Harness>

The standalone LaTeX manuscript embeds its four cited references so that it can compile in the native editor without an external bibliography file. `references.bib` retains the broader historical collection; uncited entries have not all been reverified.
