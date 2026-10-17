from pathlib import Path
import json, numpy as np
from ase import Atoms, units
from ase.io import read, write
from ase.calculators.mopac import MOPAC
from pyscf import gto,lib
from pyscf.geomopt import as_pyscf_method
lib.num_threads(1)
root=Path(__file__).resolve().parent
exe='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/gold_compute/queue_20261018/results/IB9/mopac_env/bin/mopac'
report={}
for name in ['CH2OO','dioxirane']:
 a=read(str(root.parent/'explore'/('opt_'+name+'.xyz')))
 mol=gto.M(atom=list(zip(a.get_chemical_symbols(),a.positions.tolist())),unit='Angstrom',basis={},charge=0,spin=0,verbose=0)
 counter=[0]; calls=[]
 def cb(m):
  label=root/(name+'_'+str(counter[0]).zfill(4)); counter[0]+=1
  b=Atoms([m.atom_symbol(i) for i in range(m.natm)],positions=m.atom_coords(unit='Angstrom'))
  b.calc=MOPAC(label=str(label),command=exe+' PREFIX.mop > PREFIX.stdout',method='PM7',task='1SCF GRADIENTS SINGLET PRECISE',charge=0)
  e=b.get_potential_energy(); f=b.get_forces(); g=-f*units.Bohr/units.Hartree
  native=label.with_suffix('.out').read_text()
  assert 'SCF FIELD WAS ACHIEVED' in native and 'JOB ENDED NORMALLY' in native
  calls.append({'label':str(label),'Hf_eV':float(e),'total_eV':float(b.calc.results['total_energy']),'gradient':g.tolist()})
  return e/units.Hartree,g
 scan=as_pyscf_method(mol,cb).nuc_grad_method().as_scanner()
 x=mol.atom_coords(); e,g=scan(mol)
 checks=[]
 for idx in [0,3,8]:
  for hA in [0.001,0.002]:
   h=hA/units.Bohr; vals=[]; totals=[]
   for sign in [-1,1]:
    y=x.copy().reshape(-1); y[idx]+=sign*h
    mm=mol.copy(); mm.set_geom_(y.reshape(-1,3),unit='Bohr')
    ee,gg=scan(mm); vals.append(ee); totals.append(calls[-1]['total_eV']/units.Hartree)
   fd=(vals[1]-vals[0])/(2*h); ft=(totals[1]-totals[0])/(2*h)
   checks.append({'coordinate_0based':idx,'h_A':hA,'analytic_Eh_Bohr':float(g.reshape(-1)[idx]),'fd_Hf':fd,'fd_total':ft,'error_Hf':fd-float(g.reshape(-1)[idx]),'error_total':ft-float(g.reshape(-1)[idx])})
 report[name]={'checks':checks,'calls':calls}
 print(name,checks,flush=True)
(root/'fd_results.json').write_text(json.dumps(report,indent=2))
print('FINITE_DIFFERENCE_COMPLETE',flush=True)
