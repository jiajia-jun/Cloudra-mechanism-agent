
import numpy as np
p="/home/ly/Cloudra-mechanism-agent/ts/ts_0036/jobs/declaration_0006/irc/irc.log"
L=open(p).read().splitlines()
cands=[i for i,l in enumerate(L) if ('Standard orientation' in l or 'Input orientation' in l)]
# forward arm last point block: our table says L5173
st=5172
j=st+5; co=[]; els=[]
Z={1:'H',6:'C',7:'N',8:'O'}
while not L[j].strip().startswith('---'):
    f=L[j].split(); co.append([float(f[3]),float(f[4]),float(f[5])]); els.append(Z[int(f[1])]); j+=1
co=np.array(co); r=lambda a,b: np.linalg.norm(co[a-1]-co[b-1])
print("block L%d: r(18,1)=%.3f r(20,2)=%.3f r(1,2)=%.3f"%(st+1, r(18,1), r(20,2), r(1,2)))
out="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/HL1_ts0036_prodarm_end.xyz"
with open(out,"w") as f:
    f.write("21\nHL1 ts_0036 product-side (FORWARD) IRC outer frame, r(18,1)=1.741 A | smiles: C1=NO[C@H]2[C@@H]3CC[C@@H](C3)[C@@H]12\n")
    for i in range(21):
        f.write("%-2s %14.8f %14.8f %14.8f\n"%(els[i],co[i,0],co[i,1],co[i,2]))
print("wrote",out)
