# NI1 chemical objects and electronic energies

This figure uses only the archived Guided/P2c NI1 run. It shows the neutral two-step target pathway (`e1`, `e2`); the original graph also retains a separate explicit-water branch (`e3`), which is outside this figure. Gold supplies no coordinates, energies, steps, or completion claims here.

`energies.csv` contains full-precision energies and curvature counts. The XYZ files contain final native Gaussian coordinates in their original atom order, extracted with cclib; no embedding, geometry optimization, or new quantum-chemical calculation was performed. `provenance.json` identifies each original FULL-archive member, its SHA-256 digest, relevant native-log lines, and the TS–IRC–endpoint links. All source locators are archive-relative.

The two short IRCs stopped at their 24-point-per-direction limit. Their actual outer frames were then independently optimized and frequency-checked to the declared endpoint identities. The common Cloudra native-chain verifier confirmed both links. This is not a claim that the IRC trajectories themselves converged to minima.

I is the lowest verified carbinolamine conformer. I′ is the conformer reached by the e2 IRC and lies 0.708846625 kcal/mol higher. No interconversion path between I and I′ was calculated or drawn. The e2 barrier is 57.923079642 kcal/mol relative to I, or 57.214233018 kcal/mol relative to I′. The graph-bound product minimum and the e2 product endpoint differ by only 0.000062751 kcal/mol; both are zero-imaginary imine–water minima.

Energies are B3LYP-D3(BJ)/def2-SVP gas-phase electronic energies, neutral singlet, without ZPE or thermal corrections. The plotted reaction-progress spacing is schematic. Molecular views are orthographic rotations of the actual coordinates; the dashed TS bonds indicate the changing reaction-center contacts, not an additional optimized path.

Reproduce with Python 3.11+, NumPy, Matplotlib, and RDKit:

```bash
python plot_ni1_chemical_objects.py --output-dir figure_output
```

The command writes the vector PDF and 360-dpi PNG. It needs only the companion CSV, JSON, and XYZ files, not the large calculation archive. Consult the archive locators in `provenance.json` to inspect the original logs independently.
