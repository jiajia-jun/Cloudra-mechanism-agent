import os, json
from pathlib import Path
import numpy as np
import pyscf, ase
from pyscf import gto, lib
from pyscf.geomopt import as_pyscf_method
from ase import Atoms, units
from ase.io import read
from ase.calculators.mopac import MOPAC
lib.num_threads(1)
root=Path(__file__).resolve().parent
exe='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/gold_compute/queue_20261018/results/IB9/mopac_env/bin/mopac'
print('CHAIN PySCF generic scanner -> custom callback -> ASE -> MOPAC PM7',flush=True)
print('versions',pyscf.__version__,ase.__version__,'units',units.Hartree,units.Bohr,flush=True)
results={}
for name in ['CH2OO','dioxirane']:
    source=root.parent/'explore'/('opt_'+name+'.xyz')
    atoms=read(str(source))
    assert atoms.get_chemical_symbols()==['C','O','O','H','H']
    # No ab initio Hamiltonian or basis is used: this Mole is a coordinate/state container.
    mol=gto.Mole()
    mol.atom=list(zip(atoms.get_chemical_symbols(),atoms.positions.tolist()))
    mol.unit='Angstrom'; mol.charge=0; mol.spin=0; mol.basis={}; mol.verbose=0
    mol.build()
    def callback(m, name=name):
        a=Atoms([m.atom_symbol(i) for i in range(m.natm)],positions=m.atom_coords(unit='Angstrom'))
        a.set_initial_charges(np.zeros(m.natm)); a.set_initial_magnetic_moments(np.zeros(m.natm))
        a.calc=MOPAC(label=str(root/name),command=exe+' PREFIX.mop > PREFIX.stdout',method='PM7',task='1SCF GRADIENTS SINGLET PRECISE',charge=0)
        e=a.get_potential_energy(); f=a.get_forces()
        grad=-f*units.Bohr/units.Hartree
        results[name]={'source':str(source),'symbols':a.get_chemical_symbols(),'positions_A':a.positions.tolist(),'energy_eV':float(e),'energy_Eh':float(e/units.Hartree),'forces_eV_A':f.tolist(),'gradient_Eh_Bohr':grad.tolist(),'gradient_norm':float(np.linalg.norm(grad)),'ase_results':{k:np.asarray(v).tolist() for k,v in a.calc.results.items()}}
        return e/units.Hartree,grad
    wrapped=as_pyscf_method(mol,callback)
    e,g=wrapped.nuc_grad_method().as_scanner()(mol)
    assert np.isfinite(e) and np.isfinite(g).all() and np.asarray(g).shape==(5,3)
    print(name,'energy_Eh',e,'gradient_Eh_Bohr',g,'SMOKE_CALLBACK_OK',flush=True)
(root/'results.json').write_text(json.dumps(results,indent=2))
print('BOTH_ENDPOINT_CALLBACKS_OK no optimization no frequencies no TS IRC',flush=True)
