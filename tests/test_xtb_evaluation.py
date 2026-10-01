import numpy as np
import pytest

from cloudra.tools.core.constrained_optimization import BOHR_ANGSTROM
from cloudra.tools.core.xtb_evaluation import read_gradient, read_hessian


def test_xtb_671_writer_eof_terminated_derivative_formats(tmp_path):
    # Structural fixture derived from official v6.7.1 Fortran writers, not QM.
    gradient=tmp_path/'gradient'
    gradient.write_text('$grad\n cycle = 1 SCF energy = -1.0 |dE/dxyz| = 0.1\n0 0 0 h\n1.4 0 0 h\n1.0D-1 0 0\n-1.0D-1 0 0\n')
    data=read_gradient(gradient,['H','H'])
    assert data['gradient_hartree_per_angstrom'][0][0]==pytest.approx(.1/BOHR_ANGSTROM)
    hessian=tmp_path/'hessian'
    rows=np.eye(6)
    text='$hessian\n'
    for row in rows:
        for start in range(0,6,5):
            text+='     '+''.join(f'{v:15.10f}' for v in row[start:start+5])+'\n'
    hessian.write_text(text)
    assert np.asarray(read_hessian(hessian,2)['hessian_hartree_per_angstrom2'])==pytest.approx(rows/BOHR_ANGSTROM**2)


def test_gradient_requires_actual_same_point_coordinates(tmp_path):
    path=tmp_path/'gradient'
    path.write_text('$grad\n cycle = 1\n0 0 0 h\n1.4 0 0 h\n.1 0 0\n-.1 0 0\n$end\n')
    with pytest.raises(ValueError,match='geometry'):
        read_gradient(path,['H','H'],[[0.,0.,0.],[2.,0.,0.]])


@pytest.mark.parametrize('content',['$hessian\n1\n','$hessian\nnan\n','$hessian\n$end\n'])
def test_truncated_or_nonfinite_hessian_rejected(tmp_path,content):
    path=tmp_path/'hessian'
    path.write_text(content)
    with pytest.raises(ValueError):
        read_hessian(path,2)
