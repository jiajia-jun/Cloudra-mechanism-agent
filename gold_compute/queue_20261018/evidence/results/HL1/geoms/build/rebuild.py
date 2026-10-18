
import numpy as np, os
from scipy.optimize import minimize
B="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/build"
def rd(p):
    L=open(p).read().splitlines(); n=int(L[0])
    els=[l.split()[0] for l in L[2:2+n]]
    co=np.array([[float(x) for x in l.split()[1:4]] for l in L[2:2+n]])
    return els,co
# proper linear HCNO, local frame: C at origin, axis along +x
LC=np.array([0.0,0,0]); LN=np.array([1.158,0,0]); LO=np.array([1.158+1.203,0,0]); LH=np.array([-1.064,0,0])
HC=[LC,LN,LO,LH]
def place(c2, d1, d2, face_n, guess_axis_pt):
    frag=[17,18,19,20]
    def xf(v):
        rot=v[:3]; tr=v[3:]
        th=np.linalg.norm(rot)
        if th<1e-12: R=np.eye(3)
        else:
            k=rot/th; K=np.array([[0,-k[2],k[1]],[k[2],0,-k[0]],[-k[1],k[0],0]])
            R=np.eye(3)+np.sin(th)*K+(1-np.cos(th))*K@K
        return R,tr
    def coords(v):
        R,tr=xf(v); cen=np.array([-0.0,0,0])
        pts=np.array([R@p+tr for p in HC])
        return pts
    def score(v):
        pts=coords(v)
        s=(np.linalg.norm(pts[0]-c2[0])-d1)**2+(np.linalg.norm(pts[2]-c2[1])-d2)**2
        # keep all dipole atoms on the same face side
        for p in pts:
            if np.dot(p-c2[0], face_n) < 0.8: s += 5.0*(0.8-np.dot(p-c2[0], face_n))**2
        return s
    # initial: translate so that mid of C..O sits above alkene midpoint
    mid=(c2[0]+c2[1])/2
    v0=np.array([0,0,0, mid[0]+1.18*0, mid[1], mid[2]])
    best=None
    for trial in range(40):
        v=np.array([np.random.RandomState(trial).normal(0,0.6,3),0,0,0]).ravel() if False else None
        rng=np.random.RandomState(trial)
        v0t=np.concatenate([rng.normal(0,0.35,3), mid+ (rng.normal(0,0.5,3))])
        r=minimize(score, v0t, method="Nelder-Mead", options={"xatol":1e-8,"fatol":1e-12,"maxiter":30000,"maxfev":30000})
        if best is None or r.fun<best.fun: best=r
    pts=coords(best.x)
    out=c2.copy()
    for i,k in enumerate(frag): out[k]=pts[i]
    return out, best.fun
for tag,face in [("exo",+1),("endo",-1)]:
    els,co=rd(os.path.join(B,"TSg_%s.xyz"%tag))
    # frame
    P4=np.array([co[0],co[1],co[2],co[5]]); cc=P4.mean(axis=0)
    _,_,Vt=np.linalg.svd(P4-cc); nn=Vt[2]; nn/=np.linalg.norm(nn)
    if np.dot(co[6]-cc,nn)<0: nn=-nn
    fn = face*nn
    for name,(d1,d2) in [("TSg2",(2.25,2.05)),("RCg2",(3.10,2.95))]:
        base=co.copy()
        if name=="RCg2":
            base=co.copy()
        out,res=place(base, d1, d2, fn, None)
        p=os.path.join(B,"%s_%s.xyz"%(name,tag))
        with open(p,"w") as f:
            f.write("21\nHL1 %s %s (rigid linear HCNO) smiles: C#[N+][O-].C1=CC2CCC1C2\n"%(name,tag))
            for i in range(21):
                f.write("%-2s %14.8f %14.8f %14.8f\n"%(els[i],out[i,0],out[i,1],out[i,2]))
        s1=np.linalg.norm(out[0]-out[17]); s2=np.linalg.norm(out[1]-out[19])
        sdl=[round(float(np.dot(out[k]-cc,nn)),3) for k in [6,17,18,19,20]]
        print("%s_%s res=%.6f d(1,18)=%.3f d(2,20)=%.3f d(18,19)=%.3f d(19,20)=%.3f dC-N=%.3f sdists=%s"%(
            name,tag,res,s1,s2,np.linalg.norm(out[17]-out[18]),np.linalg.norm(out[18]-out[19]),
            np.linalg.norm(out[17]-out[18]), sdl))
