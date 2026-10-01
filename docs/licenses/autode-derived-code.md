# autodE numerical references and license

Reference commit: `e7e71b33d8659fe921c16f877f9c1adddc4f9cff` of [duartegroup/autodE](https://github.com/duartegroup/autodE/tree/e7e71b33d8659fe921c16f877f9c1adddc4f9cff).

Cloudra's constrained optimizer adapts the augmented-Hessian RFO step, BFGSPD/Null Hessian update and normal convergence preset from `autode/opt/optimisers/rfo.py`, `hessian_update.py` and `base.py`. Trust-radius ratios (0.25/0.75/1.25/1.75), initial/minimum/maximum radius (0.1/0.01/0.2) and maximum per-atom move (0.12 Å) reference `crfo.py`. Equality residual tolerance (1e-4 Å) references constrained primitives. Normal convergence uses the source preset and its documented overachievement combinations, without relaxing them to pass fixtures.

This implementation uses Cartesian coordinates with rigid motions and explicitly frozen atoms removed and distance constraints represented by their Jacobian in a KKT system. It does **not** claim to transplant autodE's DIC class, Hessian initialization, executable wrappers, executor or iteration budget. The initial Hessian must be supplied as same-method evidence; it is not replaced by an invented unit matrix. Inequality windows are a Cloudra extension: only violated or impending boundary constraints are active, and interior geometries are not pulled to a midpoint. Molecular and constraint qualification remains separate from numerical convergence.

The upstream MIT permission notice is preserved below. No runtime `autode` import or dependency is introduced.


The MIT License (MIT)

Copyright (c) 2018

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## xTB derivative format boundary

The derivative reader is implemented against the official xTB v6.7.1 writers: [gradient writer](https://github.com/grimme-lab/xtb/blob/v6.7.1/src/io/writer/turbomole.f90) and [Hessian writer](https://github.com/grimme-lab/xtb/blob/v6.7.1/src/freq/io.f90). Both permit EOF termination without a `$end` marker; exact atom/matrix counts still reject truncated output. Raw gradients use Ha/Bohr and Hessians use Ha/Bohr²; converted values preserve raw units and artifacts. The gradient coordinates must match the submitted geometry at file precision. xTB's `--hess` file is projected and not mass weighted; this provenance is retained, and no exact unprojected Cartesian curvature or scientific equivalence claim is made. Gradient and Hessian jobs are separate to avoid assuming a Hessian run's final displaced gradient belongs to the central point.
