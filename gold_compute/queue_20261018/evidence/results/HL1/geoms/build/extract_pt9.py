
import numpy as np
p="/home/ly/Cloudra-mechanism-agent/ts/ts_0037/jobs/declaration_0001/irc/irc.log"
L=open(p).read().splitlines()
# find orientation block that starts before L10101 (1-based) and is the last one before it
cands=[i for i,l in enumerate(L) if ('Standard orientation' in l or 'Input orientation' in l) and i+1 < 10101]
st=cands[-1]
j=st+5; co=[]; els=[]
Z={1:'H',6:'C',7:'N',8:'O'}
while not L[j].strip().startswith('---'):
    f=L[j].split(); co.append([float(f[3]),float(f[4]),float(f[5])]); els.append(Z[int(f[1])]); j+=1
co=np.array(co)
r=lambda a,b: np.linalg.norm(co[a-1]-co[b-1])
print("block at L%d, r(18,1)=%.3f r(20,2)=%.3f r(1,2)=%.3f r(18,19)=%.3f"%(st+1, r(18,1), r(20,2), r(1,2), r(18,19)))
out="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/HL1_IRCrev_pt9_relax.xyz"
with open(out,"w") as f:
    f.write("21\nHL1 free relaxation of ts_0037 IRC Path-2 point 9 (E=-441.024624547, below the declared reactant endpoint by 2.8 kcal/mol) | smiles: C#[N+][O-].C1=CC2CCC1C2\n")
    for i in range(21):
        f.write("%-2s %14.8f %14.8f %14.8f\n"%(els[i],co[i,0],co[i,1],co[i,2]))
print("wrote", out)
