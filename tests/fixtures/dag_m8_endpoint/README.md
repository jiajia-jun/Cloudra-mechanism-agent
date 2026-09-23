# M8 endpoint optimization regression fixtures

These are unmodified ORCA output logs from the M8 cyclohexane ring-flip audit
on 2026-09-23. They test the endpoint minimum gate through the real log parser.

- `boat_optfreq.out.gz`: original IRC B endpoint Opt+Freq, backed up from
  `gold_compute/remote_backups/2026-09-23/M8/.cloudra/calc-117.out.log`.
  Optimization terminates normally but has one imaginary mode, displayed by
  ORCA as -74.94 cm^-1. This must not support an endpoint minimum.
- `twist_boat_tight_optfreq.out.gz`: TightOpt+DefGrid3 Opt+Freq started from the
  same IRC B geometry, backed up from
  `gold_compute/remote_backups/2026-09-23/M8/tight_endpoint_20260923/endB_tight.orca.out`.
  It terminates normally with no imaginary modes; the lowest nonzero frequency
  is 108.03 cm^-1.

The gzip archives decompress to the unmodified ORCA outputs; the test does
not generate their content. SHA-256 of the decompressed `boat_optfreq.out`:
`77f40f6325c1ff902f12b8b3532fc83e7f30aa8873aaa5da426abe1c0a26d983`,
and decompressed `twist_boat_tight_optfreq.out`:
`0381a0419cc6d09d489fc433a99a99705887050a0a8757a5e95fa19346f5c78c`.
