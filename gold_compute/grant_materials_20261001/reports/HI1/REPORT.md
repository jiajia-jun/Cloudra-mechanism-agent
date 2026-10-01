# HI1 REPORT — (S)-proline aldol, CPCM(DMSO) (hard gold resume)

Engine provenance: OLD campaign = ORCA 5.0.2 (retired Slurm, jobs 650/651/685) — CONTEXT ONLY.
NEW = ORCA 6.1.1 at /opt/cloudra/software/orca-6.1.1 on paratera-cpu. Never mix energies across versions.

## Model (unchanged)
Reactant complex = enamine(C=C(C)N1CCC[C@@H]1C(=O)O) + H2O + PhCHO, 41 atoms, q=0 m=1,
explicit water retained (water-free model needs human decision). Method fixed:
! B3LYP def2-SVP D3BJ def2/J RIJCOSX TightSCF CPCM(DMSO). Atom order (0-based builder order):
0=Ca(enamine beta-C), 1=Cb, 3=N, 8=Ccooh, 9,10=carboxyl O, 23=OH-H; 24-26=water; 27=Od(aldehyde),
28=Cc(aldehyde C), 35=aldehyde-H. Reaction center pair (0,28); existing atom_map in ts/ts_0001.

## Status
- OLD job 650 (ORCA5.0.2) RC Opt+Freq: minimum, 0 imag, E=-938.715728 Ha (context only).
- OLD job 651 OptTS from folded seed: FAILED (233 cycles, ~10 soft wrong Hessian modes) — NOT restarted.
- OLD job 685 scan: NO artifacts survived (server retired) -> scan restarted on new server.
- NEW jobs 5/6/7/8: FAILED — ORCA 6.1.1 CPCM + MPI (nprocs 4) crashes at CPCM/RI-J Cholesky
  (MPI_Type_match_size -> MPI_ERR_ARG). Cross-topic (HE3 CPCM(THF) same). Solvent-free jobs are fine.

## WORKAROUND
Run CPCM jobs at %pal nprocs 1 (serial; no mpirun). Confirmed working (HE3 diag job 13 on their real
CPCM system; HI1 jobs 14/15 pass the Cholesky step). Env agent (a-8) asked via agent_hub for a
nprocs-4 MPI runtime fix.

## ACTIVE JOBS (ORCA 6.1.1, serial, cpus=1, memory_mb=7000, %maxcore 6144)
- job 14 HI1/paratera_20260930/scan_major_np1: relaxed scan d(Ca0-Cc28)=4.5->1.6 A, 8 pts
- job 15 HI1/paratera_20260930/rc_min_np1: RC Opt+Freq (new-version RC minimum + 0-imag check)

## Next
1. Parse scan profile -> highest converged frame -> OptTS+Freq (Calc_Hess true) -> 1 imag on C-C.
2. IRC both directions -> re-opt/freq endpoints -> dE#(E2) = E(TS)-E(RC) at ORCA 6.1.1.
3. Minor-face channel EM1 (second-face candidate) using the existing mapping; then EM1 barrier/difference.

## Constraints
Do NOT change graph/solvent/method/acceptance. No scan peak may be labelled a gold TS. Unsupported
conclusions go to the human. Old energies are context only.
