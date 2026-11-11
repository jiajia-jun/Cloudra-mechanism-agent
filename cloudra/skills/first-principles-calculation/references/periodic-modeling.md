# Modeling from an existing crystal

Use `get_tool_docs` for the live contracts of `periodic_model` and `format_converter`. Paths resolve relative to the agent's working directory. Use a new output path for each build and pass that file to the next step.

| `operation.type` | Arguments and behavior |
| --- | --- |
| `inspect` | Reports composition, cell vectors, their lengths and the shortest periodic translation. Returns 1-based atom numbers and fractional positions. Filter with `element` or page with `start_atom` and `limit`. |
| `supercell` | Give one of `repeat`, a 3×3 integer `matrix`, or `min_lengths_angstrom`. The last option rounds up the repeats along each input vector. Null entries keep that axis unchanged. A slab can be expanded along its periodic axes. |
| `slab` | Give `miller`, `layers` and `vacuum_angstrom`. The Miller indices refer to the supplied cell. Use a conventional cell when working with conventional indices. `layers` counts geometric atomic planes. Vacuum is the total gap along the normal. |
| `edit_sites` | Provide an `edits` list. A `remove` needs `atom_index`, a `replace` also needs the new `element`, and an `add` needs `element` and `fractional`. Numbers always refer to the input file for that call. |
| `adsorption_sites` | Give `side`. Preview `ontop`, `bridge` and `hollow` candidates with 1-based site numbers, Cartesian positions and supporting atoms. |
| `adsorb` | Give `side`, `site`, `adsorbate` and `height_angstrom`. Place the anchor above the chosen reference along the outward normal. |

For a slab, omit `output_path` to preview cut numbers, outer-plane compositions, cleavage gaps and predicted slab thicknesses. The preview covers geometrical cuts and can include symmetry-equivalent candidates. Supply the selected `termination` and a new `output_path` to build. A single cut can be written without its number. Choose Miller indices, slab dimensions, termination and defect sites based on the task. Structural output describes initial geometries. Relaxation, charge states, surface polarity, and size convergence require separate scientific evaluation.

These JavaScript tool calls illustrate the same arguments accepted by the traditional tool protocol.

```javascript
const cut = {type: "slab", miller: [1, 1, 1], layers: 5, vacuum_angstrom: 16}
const preview = await tools.periodic_model({input_path: "Ag.cif", operation: cut})
text(preview.data.terminations)
```

After reviewing the candidates, use the selected cut. For example, cut 1 followed by a 3×3 in-plane repeat uses these calls.

```javascript
const slab = await tools.periodic_model({
  input_path: "Ag.cif",
  operation: {type: "slab", miller: [1, 1, 1], layers: 5, vacuum_angstrom: 16, termination: 1},
  output_path: "Ag111.extxyz"
})
const wide = await tools.periodic_model({
  input_path: slab.data.output_path,
  operation: {type: "supercell", repeat: [3, 3, 1]},
  output_path: "Ag111-3x3.extxyz"
})
text(wide.data.summary)
```

For a vacancy, expand the parent, inspect the expanded file, then remove the chosen atom. A substitution can be submitted in the same call as the vacancy with its own input-file atom number. Report the selected sites along with the output file.

## Adsorption on a slab

Use `side: "top"` for the face along the out-of-plane lattice vector and `"bottom"` for the other face. For a three-periodic slab file such as POSCAR, specify the out-of-plane vector with `vacuum_axis: "a"`, `"b"` or `"c"`. For a three-periodic input, candidate enumeration unwraps the slab through its largest gap along that vector. When multiple gaps are equally large, select a known face with `surface_atoms` or use an explicit atop atom. Placement preserves the input cell and boundary flags.

Preview sites on a clean outermost plane or give `surface_atoms` with the selected substrate atom numbers. Use that selection again when building from a candidate number. For a slab that already has an adsorbate, `surface_atoms` can identify the exposed substrate explicitly. The periodic Voronoi construction describes geometrical candidates. A support list can repeat a number when distinct periodic images of the same input atom support a site.

```javascript
const sites = await tools.periodic_model({
  input_path: "Ag111-3x3.extxyz",
  operation: {type: "adsorption_sites", side: "top", kind: "ontop"}
})
text(sites.data.adsorption_sites)
```

Suppose the selected candidate is site 2 and the anchor and direction atoms in the molecule file are 4 and 5. Use the chosen height and orientation for the initial geometry.

```javascript
const adsorbed = await tools.periodic_model({
  input_path: "Ag111-3x3.extxyz",
  output_path: "Ag111-adsorbate.extxyz",
  operation: {
    type: "adsorb", side: "top", site: 2, height_angstrom: 2.4,
    adsorbate: {
      path: "molecule.xyz", anchor_atom: 4,
      orientation: {axis_atom: 5, direction: "outward", twist_degrees: 30}
    }
  }
})
text(adsorbed.data)
```

`orientation.direction` also accepts a Cartesian vector in the slab frame. Omit `orientation` to use the pose in the file. For atomic placement give an element symbol such as `adsorbate: "Li"`. To place above a particular atom in an existing complex, give `site: {atom_index: 12}` using the current structure's atom number. Placement reports the shortest distance to an input atom using the input periodic boundaries.

For geometry optimization after placement, load `surface-modeling-sop.md` and use [the staged relaxation workflow](surface-modeling-sop.md#33-staged-relaxation-of-molecular-adsorbates).

## Periodic structure exchange

Use EXTXYZ between operations to retain lattice vectors, per-axis periodicity and contiguous molecular coordinates. CIF wraps atoms individually into the cell. Export to POSCAR for VASP. POSCAR uses three periodic axes and groups atoms by element. Inspect the exported file when you need its atom numbers. Model summaries describe the geometry before target-format export. Ordered, explicit occupations are required for modeling.

| `format_converter` format | Support |
| --- | --- |
| `cif`, `poscar` / `vasp`, `extxyz`, `xsf`, `gen` | Read and write. CIF, POSCAR and GEN use three periodic axes for these cells. XSF supports X, XY and XYZ. |
| `contcar` | Read the VASP structure. |
| `espresso-in` / `espresso-out` | Extract geometry from Quantum ESPRESSO input with `ibrav=0` and explicit cell vectors or from the last output frame with results. Use explicit Å or Bohr units for cell vectors. Electrostatic boundary settings and magnetic assignments require separate handling. |
| `abacus-stru` | Extract geometry from ABACUS STRU with explicit lattice vectors. Supports Direct, Cartesian, Cartesian_au and Cartesian_angstrom positions. |
| `cp2k-geometry` | Write an include fragment containing `&CELL` and `&COORD` for CP2K `&SUBSYS`. Supply KIND, DFT and POISSON settings for the calculation. |
