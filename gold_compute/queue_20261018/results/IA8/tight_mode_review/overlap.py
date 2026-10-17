exec((__import__('pathlib').Path(__file__).parent/'direction.py').read_text().split("for side in ['F','B']:")[0])
oldx=x.copy();oldv=v.copy();oldm=m.copy()
p2=root/'ts/ts_0001/jobs/declaration_0007/frequency/frequency.hess';ll=p2.read_text().splitlines();aa=ll.index('$atoms');rr=[t.split() for t in ll[aa+2:aa+7]];xx=np.array([[float(z) for z in r[2:]] for r in rr])*.5291772105638411
nn=ll.index('$normal_modes');MM=np.zeros((15,15));cols=[]
for line in ll[nn+2:aa]:
 t=line.split()
 if t and len(t)==5 and all(z.isdigit() for z in t):cols=list(map(int,t))
 elif len(t)==6 and t[0].isdigit():MM[int(t[0]),cols]=list(map(float,t[1:]))
vv=MM[:,6].reshape(5,3);xc=np.average(oldx,axis=0,weights=m);yc=np.average(xx,axis=0,weights=m);u,sv,vt=np.linalg.svd((xx-yc).T@(m[:,None]*(oldx-xc)));D=np.eye(3);D[-1,-1]=np.linalg.det(u@vt);R=u@D@vt;vv=vv@R
v1=project(oldv);v2=project(vv)
def cosine(a,b):return float(abs(np.dot(a,b)/np.linalg.norm(a)/np.linalg.norm(b)))
r={'full_abs_cos':cosine(v1,v2),'heavy_abs_cos_after_same_rigid_projection':cosine(v1[:9],v2[:9]),'new_to_old_mass_weighted_rmsd_A':float(np.sqrt(np.sum(m[:,None]*((xx-yc)@R-(oldx-xc))**2)/sum(m))),'old_mode_index':6,'new_mode_index':6,'old_frequency_cm':float(l[l.index('$vibrational_frequencies')+2+6].split()[1]),'new_frequency_cm':float(ll[ll.index('$vibrational_frequencies')+2+6].split()[1]),'note':'Cartesian modes rotated with mass-weighted Kabsch geometries; both projected at old TS onto complement of same six mass-weighted rigid vectors; compare absolute normalized dot product, no H relabeling.'}
(out/'mode_overlap.json').write_text(json.dumps(r,indent=2));print(r)
