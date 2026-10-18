
import numpy as np, os
B="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/build"
L=open(os.path.join(B,"RCg_exo.xyz")).read().splitlines()
els=[l.split()[0] for l in L[2:23]]
co=[[float(x) for x in l.split()[1:4]] for l in L[2:23]]
def w(path, sel, comment, shift=None):
    pts=[co[i] for i in sel]
    if shift is not None:
        c=np.mean(pts,axis=0); pts=[[p[k]-c[k] for k in range(3)] for p in pts]
    with open(path,"w") as f:
        f.write("%d\n%s\n"%(len(sel),comment))
        for i,p in zip(sel,pts):
            f.write("%-2s %14.8f %14.8f %14.8f\n"%(els[i],p[0],p[1],p[2]))
w("/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/norbornene_ref.xyz", list(range(17)),
  "HL1 reference monomer norbornene C7H10 (MMFF geometry) smiles: C1=CC2CCC1C2", shift=True)
w("/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/hcno_ref.xyz", [17,18,19,20],
  "HL1 reference monomer HCNO smiles: C#[N+][O-] (extracted from build geometry, recentred)", shift=True)
print(open("/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/hcno_ref.xyz").read())
