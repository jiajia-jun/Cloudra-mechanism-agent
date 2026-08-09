# Reaction Mapping and Thermochemistry Design

## Goal

Close the two largest remaining gaps in the small-organic-molecule mechanism workflow: turn a reactant/product SMILES pair into explicit, inspectable atom-mapping candidates that can drive concrete XYZ paths, and turn quantum-chemistry outputs into correctly labelled relative thermochemistry. The tools must expose evidence and ambiguity rather than claim a mechanism is absolutely correct.

## Scope and sequencing

The work is split into three independently testable changes. First, add `reaction_mapping`, because atom identities and reaction-centre edits are prerequisites for interpolation, endpoint identity checks, and reactive-conformer selection. Second, change `conformer_search` so reactive candidates are not discarded before `distance_filters` are evaluated. Third, correct `gaussian_log_parser` thermochemistry semantics and add `thermo_analysis` for relative energies and optional GoodVibes-backed corrections.

`ts_guess(strict=True)` remains stateless and unchanged in responsibility: it proves only that partial IRC endpoints lie between the TS and the two supplied optimized intermediates. Endpoint identity with the originally proposed SMILES belongs to `reaction_mapping`, not to `ts_guess`.

## `reaction_mapping` interface

The tool consumes balanced `reactant_smiles` and `product_smiles`. It may additionally consume reactant/product structure paths or texts (`mol`, `sdf`, or `xyz`) and optional total charges. Structures are used only to bind a graph-level mapping to the concrete atom order that downstream XYZ tools see.

The output contains:

- `mapping_status`: `unique`, `ambiguous`, or `inconclusive`;
- `candidates`: ranked mapping candidates, each with product-heavy-atom → reactant-heavy-atom permutation, score components, and bond edits expressed in reactant numbering;
- `heavy_atom_map`: the top candidate in the same 1-based convention as `ts_guess.atom_map`;
- `atom_map`: a full explicit-atom permutation when concrete structures are supplied or when both internally generated explicit-H graphs can be bound safely;
- `formed_bonds`, `broken_bonds`, and `order_changes` for the top candidate;
- `watch_pairs`: the union of forming and breaking pairs suitable for `ts_guess` and `conformer_search`;
- endpoint identity results for any supplied structures;
- an explanatory message stating that ambiguous mappings require agent or user selection.

If input SMILES already carry atom-map numbers on every heavy atom, those labels are authoritative after validation. Otherwise RDKit generates candidates from element-compatible MCS seeds, completes unmatched atoms, and ranks them by bond edits, formal-charge conservation, implicit-hydrogen conservation, and stereochemical consistency. Mechanistic rearrangements can have multiple chemically plausible mappings; ties or near-ties remain `ambiguous` and are returned, never silently collapsed.

Explicit hydrogens are expanded deterministically within each mapped heavy-atom neighbourhood. Unmatched hydrogens, proton transfers, incompatible element counts, or an XYZ graph that cannot be reconciled with its SMILES produce `inconclusive` rather than a fabricated full map. The heavy-atom candidates remain available when possible.

Endpoint identity means graph identity after normalizing explicit hydrogens and atom order. It does not mean conformational identity. A strict IRC result and an endpoint identity match are separate pieces of evidence.

## Reactive conformer preservation

`conformer_search` must evaluate `distance_filters` before selecting a representative from an RMSD cluster. When a cluster contains both reactive and non-reactive members, it keeps the lowest-energy reactive member in addition to the ordinary lowest-energy representative. The output continues to report the conformer's energy relative to the global minimum so the conformational penalty is not hidden. Reactive conformers are not automatically called viable transition-state precursors.

The configured energy window still bounds ordinary ensemble output, but at least the lowest-energy filter-passing conformer is retained and clearly marked even when it lies outside that window. This makes the Curtin–Hammett warning operational rather than documentary.

## Thermochemistry semantics

`gaussian_log_parser` must distinguish corrections from totals. cclib `enthalpy` and `freeenergy` are total thermochemical values and will be exposed as `total_enthalpy_hartree` and `total_gibbs_free_energy_hartree`. `thermal_energy_hartree` will no longer alias enthalpy. Existing misleading fields remain only as deprecated compatibility aliases if a caller still requests them, with corrected descriptions.

`thermo_analysis` consumes named species with frequency logs and optional higher-level single-point energies, stoichiometric coefficients, temperature, concentration/standard-state settings, and a reference species or reaction expression. Its native backend reports raw RRHO values from parsed logs and combines them reproducibly. If GoodVibes is installed, an optional `goodvibes` backend delegates quasi-harmonic, frequency-scaling, concentration, and single-point corrections to GoodVibes and records the exact command/options. Absence of GoodVibes yields `inconclusive` for that backend rather than silently falling back to raw RRHO.

All relative-energy tables state units, temperature, standard state, and whether values are raw RRHO or corrected. Missing conditions are surfaced explicitly; defaults are allowed for benchmark runs but are recorded as assumptions.

## Agent-facing workflow

For a two-SMILES mechanism task the agent calls `reaction_mapping` before generating paths. It selects or confirms a candidate, uses its full `atom_map` and `watch_pairs`, preserves reactive conformers, and later checks optimized IRC intermediates against the original endpoint SMILES. Default `ts_guess verify`, scan profiles, Mayer bond orders, and charge analyses remain advisory evidence. No single tool closes a mechanistic hypothesis by itself.

The Claisen regression uses `C=COCC=C` → `C=CCCC=O`. It must recover the chemically intended [3,3] heavy-atom candidate, expose competing lower-edit mappings as ambiguity when no mechanistic hint is supplied, identify O–allyl bond breaking and terminal C–C bond formation for the selected candidate, expand explicit hydrogens consistently, and round-trip its `atom_map` through `ts_guess(interpolate)` without atom-order errors.

## Failure behavior

Malformed SMILES, unbalanced element inventories, invalid mapped-SMILES labels, unreadable files, or unsupported formats are operational failures (`is_success=False`). Chemically underdetermined mapping, symmetry-equivalent candidates, proton-transfer ambiguity, unavailable GoodVibes, or incomplete thermochemical material are successful tool executions with `ambiguous` or `inconclusive` scientific results. No persistent workflow state is introduced.

## Verification

Tests use real RDKit molecules and repository Gaussian fixtures. They cover authoritative mapped SMILES, the Claisen rearrangement, symmetric ambiguity, explicit-H expansion, endpoint identity/mismatch, reactive-member preservation during clustering, raw thermochemistry labels and arithmetic, missing conditions, and GoodVibes absence. Existing `ts_guess`, conformer, log-parser, Gaussian-frame, and registry tests must remain green.
