# Declared open-shell support

User-confirmed scientific contract: charge and total multiplicity are supplied by the input. Total electron count determines the possible alpha/beta counts through parity and range. RDKit's localized radical count is retained as graph information, never forced equal to multiplicity minus one. Explicit open-shell singlets and declared metal/delocalized systems are supported as inputs. The program must not select a ground state, broken-symmetry/multireference method, initial spin distribution or new scientific acceptance threshold.

## Implementation

- [x] Shared electronic-state facts and input validation; preserve radical identity and isotope/hydrogen accounting.
- [x] Explicit electronic-character input through builder/public tools and TS records; unoptimized ETKDG seeds, no spin-blind MMFF/UFF or fabricated energies.
- [x] Common declaration and concrete-source gates, independent geometric bond-pair validation, preserved explicit atom bindings and source digests.
- [x] Exhaustively proven, open-shell-only symmetric representative where no trusted explicit binding exists; incomplete proof remains a checkpoint.
- [x] Verify native input charge/multiplicity and final frequency/IRC gates remain intact; no automatic wavefunction choices.
- [x] Focused regressions, syntax/lint and independent review.

Delivery scope: integrate and push only task-owned changes, retaining unrelated work and all running calculations. The focused regression selection passed 964 tests with 22 optional-engine skips; final standalone-path forwarding adds three regressions and was checked separately. Scientific TS/IRC acceptance remains unverified.

The earlier high-spin-only implementation was paused before integration and is superseded by this confirmed general contract. Geometry preparation and graph binding do not certify a calculated electronic state or a transition state.

The current GFN-xTB/CREST interfaces cannot represent declared open-shell singlets via `--uhf 0`; capability checks run before engine probes, artifacts or compute admission. Non-singlet total-spin settings are forwarded without choosing spin polarization or wavefunction settings. User-supplied QM settings remain authoritative.
