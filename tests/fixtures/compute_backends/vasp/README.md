# VASP fixture boundary

This directory intentionally contains no `POTCAR`: pseudopotential files are
license-controlled and must not be committed. The scenario test verifies the
VASP submission contract without executing the engine. `POSCAR`, `INCAR`, and
`KPOINTS` are validated structurally; a licensed environment must supply the
matching helium `POTCAR` before an execution smoke test.
