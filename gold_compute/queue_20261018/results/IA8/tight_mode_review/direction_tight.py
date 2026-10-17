from pathlib import Path
import json,hashlib,numpy as np
root=Path('/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master');out=Path(__file__).parent
p=root/'ts/ts_0001/jobs/declaration_0007/frequency/frequency.hess';l=p.read_text().splitlines();a=l.index('$atoms');rows=[x.split() for x in l[a+2:a+7]];m=np.array([float(x[1]) for x in rows]);x=np.array([[float(t) for t in r[2:]] for r in rows])*.5291772105638411
n=l.index('$normal_modes');M=np.zeros((15,15));cols=[]
for line in l[n+2:a]:
 t=line.split()
 if t and all(z.isdigit() for z in t) and len(t)==5:cols=list(map(int,t))
 elif len(t)==6 and t[0].isdigit():M[int(t[0]),cols]=list(map(float,t[1:]))
v=M[:,6].reshape(5,3)
print('mass participation', (m[:,None]*v*v).sum(axis=1)/(m[:,None]*v*v).sum())
def align(y):
 xc=np.average(x,axis=0,weights=m);yc=np.average(y,axis=0,weights=m);u,s,vt=np.linalg.svd((y-yc).T@(m[:,None]*(x-xc)));d=np.eye(3);d[-1,-1]=np.linalg.det(u@vt);return (y-yc)@(u@d@vt)+xc
def project(z):
 q=x-np.average(x,axis=0,weights=m);basis=[]
 for ax in np.eye(3):basis.extend([np.tile(ax,(5,1)).reshape(-1),np.cross(np.tile(ax,(5,1)),q).reshape(-1)])
 B=np.array(basis).T;w=np.repeat(np.sqrt(m),3);A=w[:,None]*B;u,s,vt=np.linalg.svd(A,full_matrices=False);u=u[:,s>1e-8];zz=w*z.reshape(-1);return zz-u@(u.T@zz)
def deriv(z,i,j):d=x[j]-x[i];return float(np.dot(z[j]-z[i],d)/np.linalg.norm(d))
vp=project(v);results={'sources':{},'mass_participation':((m[:,None]*v*v).sum(axis=1)/(m[:,None]*v*v).sum()).tolist(),'mode_cartesian':v.tolist(),'mass_weighted_projected_norm':float(np.linalg.norm(vp)),'mode_derivatives_raw':{str((i+1,j+1)):deriv(v,i,j) for i,j in [(0,1),(0,2),(1,2),(3,4)]},'comparisons':[]}
for side in ['F','B']:
 f=root/('ts/ts_0001/jobs/declaration_0007/irc/irc_IRC_'+side+'_trj.xyz');ls=f.read_text().splitlines();frames=[]
 for k in range(0,len(ls),7):frames.append(np.array([[float(z) for z in t.split()[1:]] for t in ls[k+2:k+7]]))
 results['sources'][str(f)]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'frames':len(frames)}
 for k,y in enumerate(frames[:3]):
  delta=align(y)-x;dp=project(delta);cos=float(np.dot(vp,dp)/np.linalg.norm(vp)/np.linalg.norm(dp));cart=float(np.dot(v.reshape(-1),delta.reshape(-1))/np.linalg.norm(v)/np.linalg.norm(delta))
  results['comparisons'].append({'side':side,'frame_1based':k+1,'cos_mass_weighted_no_rigid':cos,'abs_cos':abs(cos),'cos_cartesian_aligned':cart,'cos_heavy_mass_weighted':float(np.dot((v[:3]*np.sqrt(m[:3,None])).reshape(-1),(delta[:3]*np.sqrt(m[:3,None])).reshape(-1))/np.linalg.norm(v[:3]*np.sqrt(m[:3,None]))/np.linalg.norm(delta[:3]*np.sqrt(m[:3,None]))),'bond_changes_A':{str((i+1,j+1)):float(np.linalg.norm(y[j]-y[i])-np.linalg.norm(x[j]-x[i])) for i,j in [(0,1),(0,2),(1,2),(3,4)]}})
results['sources'][str(p)]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest()};results['convention']='ORCA normal_modes Cartesian displacement; multiply sqrt(mass) for mass-weighted comparison, Kabsch mass-weighted align IRC to TS, project translations/rotations in same weighted metric; sign arbitrary. Frames are finite chords, not infinitesimal tangents.'
(out/'direction_tight_results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
