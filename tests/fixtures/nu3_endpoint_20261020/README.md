# NU3 native endpoint qualification replay

These are complete, unchanged ORCA outputs and their original inputs, geometries,
status records and endpoint sidecars from the 2026-10-20 blind NU3 run. The source
commit, batch, run times, source paths and compressed/uncompressed SHA-256 values
are recorded in `manifest.json`. Gzip is only a storage wrapper; the tests restore
the exact original bytes to a temporary directory.

IRC job 108 supplies the archived forward endpoint used to start Opt job 124.
The native Opt terminated normally and converged. Freq job 125 also terminated
normally at the Opt final geometry, but reports one imaginary frequency,
**-84.93 cm^-1**. The shared native endpoint verifier must therefore reject this
Opt/Freq pair as a zero-imaginary minimum, independently of its valid IRC source.

The tests replay existing facts; they do not run QM, construct a mechanism graph,
or change scientific criteria. **TightOpt was not attempted in this evidence set.**
This unsuccessful endpoint qualification does not establish that the physical
reaction pathway is absent.
