# MLIP via external engines (Gaussian g16-mlips / ORCA ExtOpt)

Two supported ways to drive a machine-learned interatomic potential (MLIP)
from a mainstream QM engine, so that the engine keeps doing what it does best
(opt, freq, IRC, scan) while the MLIP replaces the electronic-structure part:

- **Gaussian**: the `External` keyword offloads energy/gradient/Hessian to an
  external program; `g16-mlips` is the Python plugin that wraps MACE / UMA /
  ORB / AIMNet2 into that interface.
  Plugin: https://github.com/t-0hmura/g16-mlips (t-0hmura/g16-mlips).
- **ORCA**: the equivalent built-in route when g16/g16-mlips are not
  available — `ExtOpt` plus a `%method` block pointing at the MACE python
  executable (section below).

Pick by what is actually installed on the deployment host: a g16+g16-mlips
machine runs the Gaussian route; a machine with ORCA + `orca-mlips-mace` runs
the ORCA route. Both engines share the "when to use", charge discipline and
accuracy/fallback caveats further down.

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

## ORCA route (`ExtOpt` + `%method` ProgExt)

ORCA's MLIP external interface: `ExtOpt` switches the engine, and a
`%method` block points ORCA at the **mace python executable** with the
model/device arguments (`orca-mlips-mace` on PATH, MACE installed as a Python
package — `command -v mace` will NOT find it). End-to-end environment setup
for one deployment (binary paths, model weights, probe artifacts, verified
opt/freq convergence) is recorded in
`deploy/mace_omol25_orca_external_setup.md` — resolve `<mace python
executable>`, `<model .model path>`, `--device` and `--dtype` from that
document or the host's environment; nothing here is host-specific.

### Build with qm_input_writer (engine="orca")

Same builder as the Gaussian route — no dedicated MLIP parameter. The
`%method` block goes into `orca_blocks` (the writer appends it verbatim
between `%pal/%maxcore` and the coordinate block):

```json
{
  "engine": "orca",
  "source_type": "smiles",
  "source_value": "C=CC=C.C=C",
  "method": "ExtOpt",
  "basis_set": "",
  "task_type": [{"opt": null}],
  "charge": 0,
  "multiplicity": 1,
  "nproc": 4,
  "mem": "4GB",
  "orca_blocks": "%method\n  ProgExt \"<mace python executable, absolute path>\"\n  Ext_Params \"--model <absolute path to .model weights> --device <cpu|gpu> --dtype float64\"\nend",
  "output_dir": "/abs/path/job.inp"
}
```

Parameter notes:

- `engine="orca"` + `method="ExtOpt"` — the `ExtOpt` token on the `!` line;
  `basis_set=""` because an MLIP has no basis. Task keywords still map
  automatically (`opt` → `Opt`, `opt ts` → `OptTS`, `irc` → `IRC`), so an
  MLIP TS search is `task_type: [{"opt": "ts"}]` with the same `%method` block.
  The deployment doc's verification record covers plain opt + numerical
  frequencies only; treat `OptTS`/`IRC` over an external MLIP as unverified
  until a probe converges.
- `orca_blocks` — `ProgExt` must be the **mace python executable** (ORCA
  shells out to it), and `Ext_Params` must carry `--model <path> --device ...
  --dtype float64` (float64 is required for reliable gradients). Swap the
  model path to change backends. Both values are deployment-specific.
- `mem`/`nproc` become `%maxcore <per-core MB>` and `%pal` automatically.
- **Numerical frequencies only**: MACE supplies no analytic Hessian, so a
  freq task must request `NumFreq`, which the task map cannot express — leave
  `task_type` empty and pass `extra_keywords="NumFreq"` instead
  (`! ExtOpt Freq` would ask for the analytic Hessian and fail).
- `charge`/`multiplicity` — set them correctly; they land on the
  `* xyz <charge> <multiplicity>` line and are the only charge information the
  MLIP receives (same discipline as the Gaussian route below).

Then submit as usual: `submit_compute_job` with `job_type="orca"` and
`input_file` pointing at the generated `.inp`.

### Resulting file shape (verification only)

`qm_input_writer` should produce files equivalent to the following — read the
generated file to confirm, do not write it yourself:

Geometry optimization (`!` keyword order may vary; ORCA does not care):

```
! Opt ExtOpt
%pal nprocs 4 end
%maxcore 1024
%method
  ProgExt "<mace python executable, absolute path>"
  Ext_Params "--model <absolute path to .model weights> --device <cpu|gpu> --dtype float64"
end
* xyz 0 1
<coordinates>
*
```

Optimization + numerical frequencies (opt and NumFreq may be combined in
one job or split into two; the two standalone shapes below are the verified
ones):

```
! ExtOpt NumFreq
%pal nprocs 4 end
%maxcore 1024
%method
  ProgExt "<mace python executable, absolute path>"
  Ext_Params "--model <absolute path to .model weights> --device <cpu|gpu> --dtype float64"
end
* xyz 0 1
<coordinates>
*
```

### MLIP runtime environment (wrapper-injected, do not script it yourself)

Driving MACE/ASE from ORCA needs two environment variables on macOS
(duplicate libomp loads then raise OMP Error #15):
`KMP_DUPLICATE_LIB_OK=TRUE` and `OMP_NUM_THREADS=1`. The repo's job wrapper
(`cloudra/calculator.sh`, orca branch) detects an `ExtOpt`/`ProgExt` input and
exports both before launching ORCA — submit through `submit_compute_job` and
let the wrapper handle it. Running ORCA outside the wrapper (interactive
probe) still requires exporting them yourself.

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
