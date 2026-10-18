import math, numpy as np
TS="/home/ly/Cloudra-mechanism-agent/ts/ts_0042/jobs/declaration_0004/"
NR="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/NR1/geoms/"
def rd(fp):
    L=open(fp).read().split("\n"); n=int(L[0]); out=[]
    for l in L[2:2+n]:
        q=l.split(); out.append((q[0],np.array([float(q[1]),float(q[2]),float(q[3])])))
    return out
def dih(a,b,c,d):
    b1=c-b; b0=a-b; b2=d-c; b1n=b1/np.linalg.norm(b1)
    v=b0-np.dot(b0,b1n)*b1n; w=b2-np.dot(b2,b1n)*b1n
    return math.degrees(math.atan2(np.dot(np.cross(b1n,v),w),np.dot(v,w)))
def kabsch(A,B):
    A=A-A.mean(0); B=B-B.mean(0); H=A.T@B; U,S,Vt=np.linalg.svd(H)
    d=np.sign(np.linalg.det(Vt.T@U.T)); R=Vt.T@np.diag([1,1,d])@U.T
    Ar=(R@A.T).T; return np.sqrt(((Ar-B)**2).sum(1).mean())
def rmsd(a,b,syms=None):
    A=np.array([p[1] for p in a]); B=np.array([p[1] for p in b])
    allr=kabsch(A.copy(),B.copy())
    hv=[i for i,p in enumerate(a) if p[0]!="H"]
    hr=kabsch(A[hv].copy(),B[hv].copy())
    return allr,hr
re_=rd(TS+"reactant_frequency/optimized.xyz"); init=rd(NR+"opt/INT1c.xyz")
pe=rd(TS+"product_frequency/optimized.xyz"); pc=rd(NR+"E4_P_complex.xyz")
print("reactant endpoint syms",[p[0] for p in re_])
print("product endpoint syms",[p[0] for p in pe])
print("INT1c syms",[p[0] for p in init],"P syms",[p[0] for p in pc])
a,h=rmsd(re_,init); print("reactant_opt vs INT1c : RMSD all=%.4f heavy=%.4f"%(a,h))
print("  dih(H4-N1-C2-O3)=%.2f  dih(H6-O3-C2-N1)=%.2f"%(dih(re_[3][1],re_[0][1],re_[1][1],re_[2][1]),dih(re_[5][1],re_[2][1],re_[1][1],re_[0][1])))
print("  INT1c dih4=%.2f dih6=%.2f"%(dih(init[3][1],init[0][1],init[1][1],init[2][1]),dih(init[5][1],init[2][1],init[1][1],init[0][1])))
pmap=[2,1,4,6,3,5]  # TS index i (0-based) <- P index
pcm=[pc[i-1] for i in pmap]
a,h=rmsd(pe,pcm); print("product_opt vs P_complex(mapped) : RMSD all=%.4f heavy=%.4f"%(a,h))
print("  dih(H4-N1-C2-O3)=%.2f  dih(H6-O3-C2-N1)=%.2f"%(dih(pe[3][1],pe[0][1],pe[1][1],pe[2][1]),dih(pe[5][1],pe[2][1],pe[1][1],pe[0][1])))
def d(a,b): return float(np.linalg.norm(a-b))
print("product endpoint: N1-C2=%.4f C2-H5=%.4f O3-H4=%.4f O3-H6=%.4f | C2-O3=%.4f N1-O3=%.4f shortest inter-frag=%.4f"%(d(pe[0][1],pe[1][1]),d(pe[1][1],pe[4][1]),d(pe[2][1],pe[3][1]),d(pe[2][1],pe[5][1]),d(pe[1][1],pe[2][1]),d(pe[0][1],pe[2][1]),min(d(pe[i][1],pe[j][1]) for i in (0,1,4) for j in (2,3,5))))
# IRC forward terminal frame (TS order) from job 1301 log
import re, json
L=open(TS+"irc/irc.log").read().split("\n")
blocks=[]
for i,l in enumerate(L):
    if "Input orientation:" in l:
        j=i+5; at=[]
        while j<len(L) and re.match(r"\s*-+\s*$",L[j])==None:
            q=L[j].split()
            if len(q)==6: at.append((int(q[0]),float(q[3]),float(q[4]),float(q[5])))
            j+=1
        blocks.append((i+1,at))
sym=["N","C","O","H","H","H"]
g=[(sym[k],np.array([blocks[-2][1][k][1],blocks[-2][1][k][2],blocks[-2][1][k][3]])) for k in range(6)]
print("last block line",blocks[-2][0])
a,h=rmsd(g,pe); print("IRC-forward terminal frame vs product_opt : RMSD all=%.4f heavy=%.4f"%(a,h))
D1=np.array([[d(g[i][1],g[j][1]) for j in range(6)] for i in range(6)])
D2=np.array([[d(pe[i][1],pe[j][1]) for j in range(6)] for i in range(6)])
iu=np.triu_indices(6,1)
print("distance-matrix RMSD (IRC terminal vs product_opt) = %.4f A"%(np.sqrt(((D1[iu]-D2[iu])**2).mean())))
D3=np.array([[d(pc[i][1],pc[j][1]) for j in range(6)] for i in range(6)])
D4=np.array([[d(pcm[i][1],pcm[j][1]) for j in range(6)] for i in range(6)])
print("distance-matrix RMSD (P_complex vs P_complex mapped) = %.4f A (sanity 0)"%np.sqrt(((D3[iu]-D4[iu])**2).mean()))
