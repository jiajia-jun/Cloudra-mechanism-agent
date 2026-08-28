# MLIP via Gaussian External (g16-mlips)

Community-standard way to drive a machine-learned interatomic potential (MLIP)
from Gaussian: the `External` keyword offloads energy/gradient/Hessian to an
external program; `g16-mlips` is the Python plugin that wraps MACE / UMA / ORB /
AIMNet2 into that interface. Gaussian keeps doing what it does best (opt, freq,
IRC, scan), the MLIP replaces the electronic-structure engine.

Plugin: https://github.com/t-0hmura/g16-mlips (t-0hmura/g16-mlips).

## When to use

- Fast pre-screening of TS guesses / conformer ensembles before expensive DFT.
- Barriers for small closed-shell organics where an OMol25-class MACE model is
  in-distribution.
- NOT a replacement for the final DFT/DFT-level single points unless the task
  explicitly targets MLIP-level accuracy.

## Build the input with qm_input_writer (never hand-write the .gjf)

There is no dedicated MLIP parameter — `qm_input_writer` can already emit the
`external` route because `extra_keywords` is appended verbatim and an empty
`basis_set` selects the no-basis branch. Call the tool with:

```json
{
  "source_type": "smiles",
  "source_value": "C=CC=C.C=C",
  "method": "external",
  "basis_set": "",
  "extra_keywords": "external=\"mace\"",
  "task_type": [{"opt": "ts,noeigen,calcfc"}, {"freq": null}],
  "charge": 0,
  "multiplicity": 1,
  "nproc": 8,
  "mem": "8GB",
  "chk_name": "<same dir as output_dir>/job.chk",
  "output_dir": "/abs/path/job.gjf"
}
```

Parameter notes:

- `method="external"` + `basis_set=""` — placeholder occupying the method slot
  in the no-basis branch of the route builder; the authoritative engine
  selection is the `external="mace"` keyword.
- `extra_keywords='external="mace"'` — appended verbatim to the route; the
  quotes around `mace` are required by Gaussian (they delimit the external
  command). Swap `mace` for `uma` / `orbmol` / `aimnet2` to switch backends
  (each must be installed and on PATH by g16-mlips).
- `charge` / `multiplicity` — **must be set correctly here**: this `q m` line
  is the only charge information Gaussian forwards to the MLIP (see below).
- For plain geometry optimizations the plugin docs recommend `nomicro`
  (`{"opt": "nomicro"}`) when Gaussian's microiterations misbehave on a MLIP
  PES.

Then submit as usual: `submit_compute_job` with `job_type="gaussian"` and
`input_file` pointing at the generated `.gjf` — no other pipeline change.

## Resulting file shape (for verification only)

`qm_input_writer` should produce a route equivalent to the following — read the
generated file to confirm, do not write it yourself:

```
%nprocshared=8
%mem=8GB
#p opt=(ts,noeigen,calcfc) freq external external="mace"

title

0 1
<coordinates>
```

(The placeholder `external` method token plus the real `external="mace"`
keyword both appear; Gaussian keys on the keyword. If this ever proves
fragile in practice, `method=""` also yields a clean
`#p opt=(...) freq external="mace"` route.)

## Charge and spin pass-through (verified in plugin source)

Gaussian's External protocol passes `NAtoms, IGrd, ICharg, Multip` on the first
line of the external input file; g16-mlips parses it (`g16_extio.py`) and the
MACE backend writes it onto the ASE atoms object:

```python
atoms.info["charge"] = int(charge)        # total charge from the .gjf `q m` line
atoms.info["spin"]   = int(multiplicity)  # multiplicity
```

MACE-OMol25 consumes `atoms.info["charge"/"spin"]` as a global scalar
embedding, so a `-1 1` input file is computed with the charged embedding.
Consequences:

- **The `charge`/`multiplicity` arguments of `qm_input_writer` are authoritative** —
  always set them correctly; the plugin does not infer charge from the structure.
- Only the *total* charge/multiplicity are passed. Per-atom charges (the
  MMCharge column) are only meaningful for ONIOM QM/MM and are not used by MACE.
- **All wavefunction-derived analyses disappear**: with `external`, Gaussian has
  no orbitals, so no Mulliken/NBO charges, no bond orders, no stability check.
  If those are needed, run a normal DFT single point on the optimized geometry
  and analyze that log.

## Accuracy caveats

- MACE is a short-range model. Closed-shell neutrals and simple anions
  (F−, OH−, CN−, carbanions of moderate size) are inside the OMol25 training
  distribution; large delocalized anions, strong charge separation, zwitterions
  with long-range Coulomb tails, and transition metals are risk zones.
- OMol25 reference data is ωB97M-V/def2-TZVPD (includes diffuse functions), so
  anions are covered at the data level; error still grows with anion size and
  charge delocalization. Benchmark before trusting barriers quantitatively.
- Light multireference character (e.g. electrocyclic allowed pathways) is
  inherited from the reference functional; strong MR systems are out of scope
  for any single-determinant-trained MLIP.

## Fallback discipline

- If the MLIP opt/TS misbehaves (oscillating, no convergence, imaginary mode
  unstable between steps), fall back to the standard DFT path
  (`qm_input_writer` with e.g. `b3lyp/6-31g(d)`) — do not tune Gaussian keywords
  indefinitely against a MLIP PES.
- A TS found at MLIP level should be confirmed at the production DFT level
  before entering any quantitative barrier table, unless the benchmark itself
  is the MLIP-vs-DFT comparison.
