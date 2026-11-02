# NI1 chemical objects and electronic energies

This figure uses only the archived Guided/P2c NI1 run. It shows the neutral two-step target pathway (`e1`, `e2`); the original graph also retains a separate explicit-water branch (`e3`), which is outside this figure. Gold supplies no coordinates, energies, steps, or completion claims here.

`energies.csv` contains full-precision energies and curvature counts. The XYZ files contain final native Gaussian coordinates in their original atom order, extracted with cclib; no embedding, geometry optimization, or new quantum-chemical calculation was performed. `provenance.json` identifies each original FULL-archive member, its SHA-256 digest, relevant native-log lines, and the TS–IRC–endpoint links. All source locators are archive-relative.

The two short IRCs stopped at their 24-point-per-direction limit. Their actual outer frames were then independently optimized and frequency-checked to the declared endpoint identities. The common Cloudra native-chain verifier confirmed both links. This is not a claim that the IRC trajectories themselves converged to minima.

I is the lowest verified carbinolamine conformer. I′ is the conformer reached by the e2 IRC and lies 0.708846625 kcal/mol higher. No interconversion path between I and I′ was calculated or drawn. The e2 barrier is 57.923079642 kcal/mol relative to I, or 57.214233018 kcal/mol relative to I′. The graph-bound product minimum and the e2 product endpoint differ by only 0.000062751 kcal/mol; both are zero-imaginary imine–water minima.

Energies are B3LYP-D3(BJ)/def2-SVP gas-phase electronic energies, neutral singlet, without ZPE or thermal corrections. The plotted reaction-progress spacing is schematic. The two energy panels share the RC zero and the same scale. Molecular views are PyMOL ray traces in a CYLview-inspired ball-and-cylinder style, using orthographic rotations of the actual coordinates; the dashed TS bonds indicate the changing reaction-center contacts, not an additional optimized path.

Reproduce the molecular ray traces with Python 3.11+, PyMOL, NumPy, and RDKit, then compose the figure with NumPy and Matplotlib:

```bash
python render_ni1_pymol.py
python plot_ni1_chemical_objects.py --output-dir figure_output
```

The bundled `pymol_renders/` PNGs can be used directly for figure composition without re-running PyMOL. The renderer uses one common orthographic camera scale, gray cylinders, colored atomic spheres, and dashed reaction-center contacts. The two carbinolamine conformers share a heavy-atom viewpoint, obtained by a proper rigid rotation that preserves all interatomic distances. `pymol_renders/render_manifest.json` records the actual PyMOL version, rendering settings, source hashes, and rigid-transform checks; it uses package-relative locators.

The plotting command writes a PDF with vector text and axes plus 600-dpi molecular images, and a 360-dpi PNG. It uses the archived CSV, XYZ and provenance files, the bundled PyMOL renders, and the publication style in `../../publication_reproduction/scripts/model_semantics/figure_style.py`; the large calculation archive is not required. Consult the archive locators in `provenance.json` to inspect the original logs independently.
