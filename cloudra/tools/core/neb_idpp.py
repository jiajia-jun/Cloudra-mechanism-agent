"""Shared ASE IDPP relaxation for geometric band seeds."""

from ase import Atoms


def relax_standard_idpp(
    images: list[Atoms], *, steps: int = 100, threshold: float = 0.1, mic: bool = False,
) -> dict:
    """Relax image coordinates in place and report the geometric objective's termination."""
    import ase
    import numpy as np
    from ase.mep import NEB
    from ase.mep.neb import idpp_interpolate
    from ase.optimize import MDMin

    report = {
        'method': 'idpp', 'idpp_mode': 'standard', 'max_steps': steps, 'tolerance': threshold,
        'optimizer': 'MDMin', 'objective': 'current_distance^-4', 'neb_method': 'improvedtangent',
        'spring_constant': 0.1, 'criterion': 'max_neb_force_norm', 'ase_version': ase.__version__,
    }
    pairs = np.triu_indices(len(images[0]), k=1)
    if any(np.any(image.get_all_distances(mic=mic)[pairs] == 0) for image in images):
        raise ValueError('standard IDPP cannot start from coincident atoms; inspect endpoint mapping/geometry')
    if len(images) == 2 or len(images[0]) < 2 or all(
        np.array_equal(image.positions, images[0].positions) for image in images[1:]
    ):
        return dict(report, converged=None, termination='not_required', steps=0, residual=None)

    neb = NEB(images, method='improvedtangent', k=0.1)

    class RecordedMDMin(MDMin):
        def run(self, fmax=0.1, steps=100):
            converged = super().run(fmax=fmax, steps=steps)
            residual = float(np.linalg.norm(neb.get_forces(), axis=1).max())
            if not np.isfinite(residual):
                raise ValueError('standard IDPP produced non-finite NEB forces')
            report.update(converged=bool(converged), steps=self.nsteps, residual=residual,
                          termination='converged' if converged else 'max_steps')
            return converged

    idpp_interpolate(neb, optimizer=RecordedMDMin, fmax=threshold, steps=steps,
                     traj=None, log=None, mic=mic)
    if any(not np.isfinite(image.positions).all() for image in images):
        raise ValueError('standard IDPP produced non-finite coordinates')
    return report
