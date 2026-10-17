# Separated-product IRC acceptance implementation plan

**Goal:** Implement the user-approved two-way classification: a real IRC product endpoint matching the declared separated products, with zero-imaginary-frequency evidence for every product component, can establish product-channel connectivity while the bound complex remains unverified.

**Approved scientific constraints:** Keep one-imaginary-mode TS, native IRC lineage, both real IRC directions, atom conservation, product graph/stereochemistry identity and zero imaginary modes for every component. Keep the existing reactant-side interval proof. Do not treat a failed complex optimization as nonexistence, ignore negative frequencies, manufacture a combined minimum geometry, or silently replace complex energies with component sums.

**Representation:** A dot-joined species string is a bound complex (`B.C`). Separate species are a list (`[B, C]`), displayed as `B + C`; SMILES charge signs remain ordinary SMILES. Reuse the existing benchmark smiles list rather than folding every list into a complex. DAG can accept the same distinction in its existing smiles field. No new mode flags, agent-supplied atom maps, hashes, or validation tokens.

**Shared contract:** Implement `verify_separated_product_direction(irc_ends, ts_geometry, source_geometries, product_smiles, component_geometries, *, charge=0, atom_binding=None)` in `irc_evidence.py`, returning the existing verdict shape (`is_decidable`, `is_match`, `details`) and an internal `proof_scope='separated_products'` on success. Product identity is checked from real endpoint coordinates against the complete declared component graph; each declared component requires a matching independent minimum geometry, with multiplicity of components preserved in the endpoint identity. Source direction uses the existing interval criterion, checking both IRC-side assignments. No invented target minimum is assembled from components.

## Tasks

- [x] Shared chemistry representation and IRC classifier: add focused failing tests, implement the shared verifier, and connect single/paired IRC log wrappers. Native log parsing supplies only real zero-imaginary component geometries. Wrappers take optional `product_smiles` without new public tool fields.
- [x] DAG and Benchmark: preserve list-versus-dot semantics, retain the existing full-minimum proof for complex declarations and use the shared verifier for separated declarations. Keep complex minimum pending and separated species supported, and update both evidence-selection paths. Do not change score weights or energy-reference rules.
- [x] TS process: accept product component frequency logs through one optional `verification.product_endpoint.component_logs` list; bind these artifacts using existing provenance mechanisms. Explicit separated declarations and unverified complex minima with supplied component logs use shared separated-product acceptance. The result records that only separated products were verified, leaving complex endpoint optimization/frequency unverified. Update inspection guidance and existing input documentation without additional terminal states.
- [x] Regressions: cover correct separated products, wrong/extra/missing components, missing/nonzero component frequencies, repeated components, real IRC identity/lineage, source-side mismatch, and continued refusal to call a complex minimum verified. Add a scripted Agent scenario using the existing harness.
- [x] Compile/lint, focused module tests and independent review. Deliver all non-ignored workspace changes to `origin/master`, merging remote advancement normally.

## Execution notes

Work in the current checkout as explicitly requested by the user. Preserve ongoing calculation files and processes. Do not run the complete local test suite. Shared-verifier implementation, DAG/Benchmark integration and TS-process integration have disjoint file ownership.

Independent review also exercised the concrete mapping entry point, the public DAG stage-binding path and complete artifact/barrier extraction. Regressions exposed and repaired list input reaching RDKit unchanged, missing component evidence in the older DAG entry point, and full-system minimum evidence bypassing separated-component verification.

Focused TS, IRC, DAG and Benchmark tests, the scripted Agent recovery scenario, frontend browser tests and build passed. Two additional CLI/Web integration tests initially omitted the existing required engine argument; their test scripts now declare Gaussian explicitly and both retests passed. No production engine defaults were added.
