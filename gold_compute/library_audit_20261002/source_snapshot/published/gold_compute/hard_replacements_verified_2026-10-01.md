# Verified hard replacements — 2026-10-01

User instruction: “是难算还是根本没算，难算就换题”. HE3 and HG2 were actually computed over multiple attempts; remaining declared-channel failures are preserved, and those tasks are retired from the active ten-task list. They are replaced by **HA8 (H6PI)** and **HB10 (HDA_CN)**. Historical source rows and registry entries remain; the retired TaskSpecs are copied to `gold_compute/archive/retired_tasks_20261001/`.

## Method and acceptance

All quoted energies use ORCA **6.1.1**, gas phase, **B3LYP-D3BJ/def2-SVP RIJCOSX/def2/J TightSCF**, q=0, multiplicity=1, 8 CPU, maxcore1536. The electronic barriers use one known-lowest qualified reactant reference per reaction. No ORCA5/Gaussian/xTB energies are mixed. These are electronic energies, without ZPE/thermal corrections or experimental fitting.

Each TS converged normally and has exactly one final imaginary frequency on the forming bonds. Bidirectional IRC intervals were followed by unconstrained endpoint OptFreq and actual geometry identity/stereochemistry verification. **All replacement IRC directions reached ORCA's native 20-point limit; none is claimed to have self-converged.** Their interval trajectories plus optimized, frequency-verified endpoints establish the observed branch identities. No conformational search is claimed exhaustive.

## HA8 / H6PI: E,Z,E octatriene thermal 6π closure

20 atoms, C8H12; only the first thermally allowed disrotatory closure. The forbidden conrotatory alternative, later hydrogen shifts, and photochemistry are excluded.

| Species | Job | E / Eh | Final imaginary frequencies |
|---|---:|---:|---|
| Known-lowest qualified E,Z,E extended reference | 80 | -311.621082862658 | 0 / 60 |
| Related C2–C7 closure TS | 77 | -311.574110153506 | 1 / 60, -496.14 cm⁻¹ |
| IRC-derived cisoid E,Z,E minimum | 90 | -311.606719389873 | 0 / 60 |
| cis/meso product minimum | 89 | -311.638020093060 | 0 / 60 |

**Headline ΔE‡ = 29.48 kcal/mol vs80.** The higher cisoid conformer is +9.01 kcal/mol; its own barrier20.46 is a diagnostic value and does not replace the common reference. Product reaction energy vs80 = -10.63 kcal/mol.

Actual90 geometry retains all three E/Z values E,Z,E and no ring. Actual89 contains one six-membered ring and cis/meso centers (2S,7R), equivalently (2R,7S); its canonical graph is identical under global inversion. The original draft trans seed was rejected and retained as preparation history. Initial endpoint88 had a -45.19 cm⁻¹ methyl-rotor soft mode, so it was not accepted; one perturbed-rotor TightOpt repair90 produced the zero-frequency endpoint. The original worker and workstream owner independently accepted the final chain; owner final verification14:50Z explicitly corrected “global minimum” to “known-lowest qualified reference”.

Primary experimental identity source: [Marvell et al., Tetrahedron1973, DOI10.1016/0040-4020(73)80195-4](https://www.sciencedirect.com/science/article/abs/pii/0040402073801954). Solution activation parameters are background, not the gas-phase electronic gold.

## HB10 / HDA_CN: cyclopentadiene + acrylonitrile DA

18 atoms, C8H9N. Both concerted asynchronous forming-bond modes involve C2–C6 and C4–C7. Actual endo and exo branch identities are taken from atom-map-free 3D stereochemistry and CN orientation relative to methano bridgeC3, not stale input labels.

| Species | Job | E / Eh | Final imaginary frequencies |
|---|---:|---:|---|
| endo IRC reactant conformer(a) | 84 | -364.463148404206 | 0 / 54 |
| Known-lowest qualified shared RC(b) | 86 | -364.463879936760 | 0 / 54 |
| endo TS | 75 | -364.441022024494 | 1 / 54, -457.47 cm⁻¹ |
| exo TS | 76 | -364.441377753618 | 1 / 54, -455.01 cm⁻¹ |
| endo product | 85 | -364.500710605618 | 0 / 54 |
| exo product | 87 | -364.500467423863 | 0 / 54 |

**Shared-reference electronic barriers: endo14.34, exo14.12 kcal/mol vs86.** TS difference exo−endo = -0.2232 kcal/mol. This is near degeneracy; **no robust favored-channel answer is scored**. Both barriers and both stereochemical graph branches remain scored/recorded. Each own-reactant diagnostic is kept separate: endo13.88 vs84, exo14.12 vs86.

84 and86 are the same neutral cyclopentadiene+acrylonitrile species in distinct noncovalent conformer minima. Their interconversion barrier was not computed; the common reference is an energy convention, not proof of fast population equilibration. 84 matches RC74 within0.00043 kcal/mol. Product85 is one intact bicyclic molecule, unmapped3D CIP(2S,4S,7S), CN antiC3 = endo. Product87 is (2S,4S,7R), CN synC3 = exo. Both normal zero-frequency minima were independently checked. Original worker's final report14:36Z accepted the same shared-reference protocol.

Primary source: [James et al., J. Org. Chem.2013, DOI10.1021/jo400900x](https://pmc.ncbi.nlm.nih.gov/articles/PMC3731169/). No literature barrier was substituted for the present calculations.

## Evidence and preservation

Remote work root: `/data/cloudra/workspace/hard_resume_20260930/hard_replacements_20261001/`. Actual final geometries and independent atom-map-free graph/CIP audit are in `gold_compute/hard_replacements_20261001/verified/`. Raw input/log/GBW/Hessian/trajectory files remain in the private verified backup, not Git:

`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/gold_compute/remote_backups/paratera_final_20261001_0830/post_recovery_20261001/`

Each job backup has a file-size/SHA-256 manifest and verification record. H6PI77/80/81/88/89/90 and HDA74/75/76/78/79/84/85/86/87 are all preserved. Independent final geometry/energy audit: `hard_replacements_20261001/FINAL_INDEPENDENT_AUDIT.json`; initial rejected-label audit is retained separately. These incremental copies are not the whole-machine final archive or platform billing-stop.

HI1 and HL1 are separate workstreams. Replacing these two tasks does not declare the entire hard set scientifically complete, and does not remove the still documented HL1/HI1 gaps or IRC caveats.
