from pathlib import Path
import json,numpy as np
from scipy.optimize import minimize
from scipy.linalg import null_space
from ase import Atoms,units
from ase.io import read,write
from ase.calculators.mopac import MOPAC
from pyscf import gto,lib
from pyscf.geomopt import as_pyscf_method
lib.num_threads(1)
root=Path(__file__).resolve().parent
exe='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/gold_compute/queue_20261018/results/IB9/mopac_env/bin/mopac'
report={}
for name in ['CH2OO','dioxirane']:
 a=read(str(root.parent/'explore'/('opt_'+name+'.xyz'))); symbols=a.get_chemical_symbols()
 mol=gto.M(atom=list(zip(symbols,a.positions.tolist())),unit='Angstrom',basis={},charge=0,spin=0,verbose=0)
 folder=root/(name+'_minimum');folder.mkdir(exist_ok=True); count=[0]; records=[]
 def cb(m):
  label=folder/('sp_'+str(count[0]).zfill(4));count[0]+=1
  b=Atoms(symbols,positions=m.atom_coords(unit='Angstrom'))
  b.calc=MOPAC(label=str(label),command=exe+' PREFIX.mop > PREFIX.stdout',method='PM7',task='1SCF GRADIENTS SINGLET PRECISE',charge=0)
  e=b.get_potential_energy(); f=b.get_forces();g=-f*units.Bohr/units.Hartree
  t=label.with_suffix('.out').read_text();assert 'SCF FIELD WAS ACHIEVED' in t and 'JOB ENDED NORMALLY' in t
  records.append({'label':str(label),'Hf_eV':float(e),'total_eV':float(b.calc.results['total_energy']),'max_gradient_Eh_Bohr':float(abs(g).max())})
  return e/units.Hartree,g
 scan=as_pyscf_method(mol,cb).nuc_grad_method().as_scanner()
 def fun(x):
  m=mol.copy();m.set_geom_(x.reshape(-1,3),unit='Bohr');e,g=scan(m);return e,g.reshape(-1)
 opt=minimize(fun,mol.atom_coords().reshape(-1),jac=True,method='BFGS',options={'gtol':1e-5,'maxiter':150})
 e,g=fun(opt.x); ok=abs(g).max()<2e-5
 result={'optimizer_success':bool(opt.success),'message':str(opt.message),'nit':int(opt.nit),'max_gradient':float(abs(g).max()),'stationary_tolerance_Eh_Bohr':2e-5,'stationary_pass':bool(ok),'energy_Hf_Eh':float(e)}
 b=Atoms(symbols,positions=opt.x.reshape(-1,3)*units.Bohr);write(str(folder/'final.xyz'),b)
 if ok:
  spectra={}
  for hA in [0.003,0.005]:
   h=hA/units.Bohr;H=np.zeros((15,15))
   for j in range(15):
    xp=opt.x.copy();xm=opt.x.copy();xp[j]+=h;xm[j]-=h
    H[:,j]=(fun(xp)[1]-fun(xm)[1])/(2*h)
   asym=float(abs(H-H.T).max());H=(H+H.T)/2
   masses=b.get_masses(); sm=np.repeat(np.sqrt(masses),3)
   coords=b.positions-np.average(b.positions,axis=0,weights=masses)
   rigid=[]
   for k in range(3):
    v=np.zeros((5,3));v[:,k]=np.sqrt(masses);rigid.append(v.reshape(-1))
   for axis in np.eye(3):rigid.append((np.cross(np.tile(axis,(5,1)),coords)*np.sqrt(masses)[:,None]).reshape(-1))
   Q=null_space(np.array(rigid));mw=H/sm[:,None]/sm[None,:]
   vals=np.linalg.eigvalsh(Q.T@mw@Q)
   # Eh/(amu Bohr^2) -> (cm^-1)^2
   factor=np.sqrt(4.3597447222071e-18/(1.66053906660e-27*(units.Bohr*1e-10)**2))/(2*np.pi*2.99792458e10)
   freqs=np.sign(vals)*np.sqrt(abs(vals))*factor
   np.save(str(folder/('hessian_'+str(hA)+'.npy')),H)
   spectra[str(hA)]={'frequencies_cm':freqs.tolist(),'imaginary_count':int((freqs<0).sum()),'hessian_asymmetry_Eh_Bohr2':asym}
  result['spectra']=spectra
 result['calls']=records
 report[name]=result
 (root/'minimum_results.json').write_text(json.dumps(report,indent=2))
 print(name,{k:v for k,v in result.items() if k!='calls'},flush=True)
print('ORDINARY_MINIMUM_ATTEMPTS_COMPLETE',flush=True)
