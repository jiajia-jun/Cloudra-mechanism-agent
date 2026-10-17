from pathlib import Path
import numpy as np,json,hashlib
root=Path('/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master');out=Path(__file__).parent
res={}
def xyz(p):
 l=p.read_text().splitlines();return [t.split()[0] for t in l[2:7]],np.array([[float(z) for z in t.split()[1:]] for t in l[2:7]])
for species,side in [('reactant','B'),('product','F')]:
 src=root/('ts/ts_0001/jobs/declaration_0007/irc/irc_IRC_'+side+'.xyz');fin=out/(species+'_optfreq.xyz');sy,x=xyz(src);sf,y=xyz(fin);assert sy==sf==['C','O','O','H','H'];m=np.array([12.011,15.999,15.999,1.008,1.008]);xc=np.average(x,axis=0,weights=m);yc=np.average(y,axis=0,weights=m);u,s,vt=np.linalg.svd((y-yc).T@(m[:,None]*(x-xc)));d=np.eye(3);d[-1,-1]=np.linalg.det(u@vt);delta=(y-yc)@(u@d@vt)-(x-xc)
 res[species]={'irc_side':side,'source':str(src),'final':str(fin),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'final_sha256':hashlib.sha256(fin.read_bytes()).hexdigest(),'symbols':sy,'mass_weighted_aligned_rmsd_A':float(np.sqrt(np.sum(m[:,None]*delta**2)/sum(m))),'max_aligned_atom_displacement_A':float(np.linalg.norm(delta,axis=1).max()),'pairs':{str((i+1,j+1)):{'irc_A':float(np.linalg.norm(x[j]-x[i])),'opt_A':float(np.linalg.norm(y[j]-y[i]))} for i,j in [(0,1),(0,2),(1,2)]}}
(out/'endpoint_comparison.json').write_text(json.dumps(res,indent=2));print(json.dumps(res,indent=2))
