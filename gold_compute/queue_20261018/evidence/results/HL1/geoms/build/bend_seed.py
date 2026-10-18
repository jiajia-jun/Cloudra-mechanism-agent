
import numpy as np
from scipy.spatial.transform import Rotation as Rot
p="/home/ly/Cloudra-mechanism-agent/ts/ts_0036/jobs/declaration_0006/reactant_opt/reactant_opt.log"
L=open(p).read().splitlines()
idx=[i for i,l in enumerate(L) if 'Standard orientation' in l] or [i for i,l in enumerate(L) if 'Input orientation' in l]
st=idx[-1]; j=st+5; co=[]; els=[]
Z={1:'H',6:'C',7:'N',8:'O'}
while not L[j].strip().startswith('---'):
    f=L[j].split(); co.append([float(f[3]),float(f[4]),float(f[5])]); els.append(Z[int(f[1])]); j+=1
co=np.array(co); print("last-orientation block at L%d, %d atoms"%(st+1,len(co)))
print("bend before: ang(19,18,21)=%.2f deg"%np.degrees(np.arccos(np.dot(co[18]-co[17],co[20]-co[17])/np.linalg.norm(co[18]-co[17])/np.linalg.norm(co[20]-co[17]))))
# rotate H21 about C18 by 16 deg to break the linearity
axis_vec = co[18]-co[17]; axis_vec/=np.linalg.norm(axis_vec)
perp = np.cross(axis_vec, [0.0,0.0,1.0]); 
if np.linalg.norm(perp)<1e-6: perp=np.cross(axis_vec,[1.0,0,0])
perp/=np.linalg.norm(perp)
for ang in [16.0, -16.0]:
    R = Rot.from_rotvec(np.radians(ang)*perp).as_matrix()
    v = co[20]-co[17]
    newh = co[17] + R@v
    c2 = co.copy(); c2[20]=newh
    a=np.degrees(np.arccos(np.dot(c2[18]-c2[17],c2[20]-c2[17])/np.linalg.norm(c2[18]-c2[17])/np.linalg.norm(c2[20]-c2[17])))
    # min separation sanity
    mn=9e9
    for i in range(21):
        for k in range(i+1,21):
            d=np.linalg.norm(c2[i]-c2[k])
            if d<mn and d>0.4: mn=d
    print("  rot %+0.0f deg -> ang(19,18,21)=%.2f deg, min pair dist %.3f"%(ang,a,mn))
    out="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/RCend_seed_bent%+d.xyz"%ang
    with open(out,"w") as f:
        f.write("21\nHL1 endpoint seed: IRC reverse outer frame of ts_0036, HCNO H bent %+0.0f deg off the C-N axis to remove the linear-angle degeneracy | smiles: C#[N+][O-].C1=CC2CCC1C2\n"%ang)
        for i in range(21):
            f.write("%-2s %14.8f %14.8f %14.8f\n"%(els[i],c2[i,0],c2[i,1],c2[i,2]))
    print("   wrote", out)
