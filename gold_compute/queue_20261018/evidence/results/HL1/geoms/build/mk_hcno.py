
import numpy as np, os
B="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/build"
L=open(os.path.join(B,"TSg2_exo.xyz")).read().splitlines()
els=[l.split()[0] for l in L[2:23]]
co=np.array([[float(x) for x in l.split()[1:4]] for l in L[2:23]])
pts=co[17:21]; c=pts.mean(axis=0); pts=pts-c
p="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/hcno_ref.xyz"
with open(p,"w") as f:
    f.write("4\nHL1 reference monomer HCNO, rigid linear (C#N 1.158, N-O 1.203, C-H 1.064) smiles: C#[N+][O-]\n")
    for i in range(4):
        f.write("%-2s %14.8f %14.8f %14.8f\n"%(els[17+i],pts[i,0],pts[i,1],pts[i,2]))
print(open(p).read())
