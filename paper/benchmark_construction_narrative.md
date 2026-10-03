# Benchmark construction narrative — current manuscript alignment

Updated 3 October 2026. The full previous narrative is retained in `archive/pre_novelty_rewrite_20261003/benchmark_construction_narrative.md`.

Cloudra's benchmark asks whether an agent can deliver a chemically specified mechanism whose graph, stationary points, reaction directions, and quantitative claims are supported by inspectable computational artifacts. Easy, Normal, Hard, and Impossible tasks probe elementary execution, multistep reasoning, stereochemical alternatives, and the validity limits of the allowed methodology. These tiers describe scientific demands; their names do not establish a numerical difficulty calibration.

The 2 October audit covers 52 tasks and 81 edges. Of these edges, 57 have numerical values, ten retain open reference gaps, two carry explicit proton-transfer exemptions, eight involve inaccessible transition states, and four concern properties or state changes. Ten populated numerical entries retain evidence or mechanism caveats. This is a dated reference inventory, not a claim of 52 completed autonomous trials or 57 fully accepted pathways.

The composite uses 0.1 graph agreement, 0.3 binary self-consistency, and 0.6 accuracy. Evidence binding enters graph assessment; there is no global binding-quality multiplier. Reference-edge coverage is withdrawn when its delivered covering step fails self-consistency. Numerical integrity failures clear the self-consistency and accuracy components. The accuracy implementation includes task-specific caps and special handling of selectivity, properties, and absent numerical references; a simple Gaussian kernel is not the full evaluator.

Impossible delivery retains the requested graph and marks unsupported elements `accessible=false`. Refusal text alone is insufficient, and a failed search does not prove methodological inaccessibility. The project intention that a fully correct inaccessible delivery can receive full credit is not yet aligned with the current inaccessible-edge accuracy implementation. This unresolved issue must be settled before cross-tier aggregate performance is claimed.

The new manuscript treats deterministic TS procedures, evidence-governed delivery, and independent artifact evaluation as the three linked contributions. It does not assert that reaction exploration is new, that all methods share one universal computational protocol, or that a planned benchmark has already demonstrated better performance.

Detailed provenance and release requirements are in `supplementary_information.md`; the paper text is in `draft.md` and `main.tex`.
