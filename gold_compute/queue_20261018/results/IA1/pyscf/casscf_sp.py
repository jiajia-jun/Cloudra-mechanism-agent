# smiles: C1=CC=C1
import os,json
import numpy as np
import pyscf
from pyscf import gto,scf,mcscf,lib,fci
lib.num_threads(4)
for tag,src in [('rectangle','../rect_optfreq.xyz'),('square','../square_constrained.xyz')]:
 rows=open(src).read().splitlines()[2:10]
 atom=[(r.split()[0],tuple(map(float,r.split()[1:4]))) for r in rows]
 xyz=np.array([a[1] for a in atom]); xyz-=xyz[:4].mean(axis=0)
 _,_,v=np.linalg.svd(xyz[:4]); normal=v[-1]; axis=np.cross(normal,[1.,0.,0.]); axis/=np.linalg.norm(axis); other=np.cross(normal,axis)
 rotated=xyz@np.array([axis,other,normal]).T
 mol=gto.M(atom=[(a[0],r) for a,r in zip(atom,rotated)],basis='cc-pvdz',charge=0,spin=0,symmetry=False,verbose=4,output=tag+'.log',max_memory=3500)
 mf=scf.RHF(mol); mf.conv_tol=1e-10; mf.max_cycle=100; mf.kernel()
 # Select two occupied and two virtual orbitals by overlap-metric weight in all carbon out-of-plane pz AOs.
 S=mf.get_ovlp(); labels=mol.ao_labels(fmt=False)
 ids=[i for i,l in enumerate(labels) if l[0]<4 and l[2].endswith('p') and l[3]=='z']
 Q=S[:,ids]; weights=np.einsum('ij,ij->j',mf.mo_coeff,Q@np.linalg.solve(S[np.ix_(ids,ids)],Q.T@mf.mo_coeff))
 nocc=mol.nelectron//2
 occ=sorted(range(nocc),key=lambda i:weights[i],reverse=True)[:2]
 vir=sorted(range(nocc,len(weights)),key=lambda i:weights[i],reverse=True)[:2]
 active=sorted(occ+vir)
 mc=mcscf.CASSCF(mf,4,(2,2)); mc.fcisolver=fci.direct_spin0.FCI(mol); mc.conv_tol=1e-9; mc.max_cycle_macro=100
 mo=mc.sort_mo(active,base=0); mc.kernel(mo)
 dm=mc.fcisolver.make_rdm1(mc.ci,4,(2,2)); no=np.linalg.eigvalsh(dm)[::-1]
 grad=mc.nuc_grad_method().kernel()
 result=dict(pyscf=pyscf.__version__,method='state-specific singlet CASSCF(4,4)',basis='cc-pVDZ',geometry_source=src,rhf_converged=bool(mf.converged),casscf_converged=bool(mc.converged),energy_Eh=float(mc.e_tot),selected_mo_1based=[i+1 for i in active],selected_pi_weights=[float(weights[i]) for i in active],natural_occupations=no.tolist(),spin_square=list(map(float,mc.fcisolver.spin_square(mc.ci,4,(2,2)))),gradient_Eh_Bohr=grad.tolist(),gradient_norm=float(np.linalg.norm(grad)))
 json.dump(result,open(tag+'_diagnostics.json','w'),indent=2); print(tag,json.dumps(result),flush=True)
 mol.stdout.close()
